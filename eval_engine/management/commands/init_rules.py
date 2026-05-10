import json
import os
import logging
from django.core.management.base import BaseCommand
from django.conf import settings
from eval_engine.models import RuleConfig, RuleVersionHistory

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = ['rule_id', 'rule_name', 'rule_type', 'engine_type']

DEFAULTS_MAP = {
    'engine_type': 'simpleeval',
    'scope': 'global',
    'priority': 0,
    'is_active': True,
    'business_id': '',
    'business_group': '',
    'category_key': '',
    'user_id': '',
    'threshold_value': None,
    'description': '',
    'version': 1,
    'created_by': 'system',
}


class Command(BaseCommand):
    help = 'Initialize default rules from fixtures'

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true', help='Force overwrite existing rules')
        parser.add_argument('--dry-run', action='store_true', help='Validate only, do not write to database')
        parser.add_argument('--fixture', type=str, default=None, help='Custom fixture file path')

    def handle(self, *args, **options):
        fixtures_path = options.get('fixture') or os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            'fixtures', 'default_rules.json'
        )

        if not os.path.exists(fixtures_path):
            self.stdout.write(self.style.ERROR(f'Fixtures file not found: {fixtures_path}'))
            return

        with open(fixtures_path, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)

        if isinstance(raw_data, list):
            rules_data = raw_data
            meta = {}
        elif isinstance(raw_data, dict):
            meta = raw_data.get('_meta', {})
            rules_data = raw_data.get('rules', [])
        else:
            self.stdout.write(self.style.ERROR('Invalid fixture format: expected list or dict with "rules" key'))
            return

        if meta:
            self.stdout.write(f"Fixture version: {meta.get('version', 'unknown')}")
            self.stdout.write(f"Description: {meta.get('description', 'N/A')}")

        validation_errors = self._validate_rules(rules_data)
        if validation_errors:
            self.stdout.write(self.style.ERROR(f'Validation failed with {len(validation_errors)} error(s):'))
            for err in validation_errors:
                self.stdout.write(self.style.ERROR(f'  - {err}'))
            return

        self.stdout.write(self.style.SUCCESS(f'Validation passed: {len(rules_data)} rule(s) found'))

        if options['dry_run']:
            self.stdout.write(self.style.WARNING('Dry run mode - no changes written to database'))
            return

        force = options['force']
        created_count = 0
        updated_count = 0
        skipped_count = 0

        for rule_data in rules_data:
            rule_id = rule_data['rule_id']

            if not force and RuleConfig.objects.filter(rule_id=rule_id).exists():
                self.stdout.write(f"Rule {rule_id} already exists, skipping (use --force to overwrite)")
                skipped_count += 1
                continue

            if force:
                deleted_count, _ = RuleVersionHistory.objects.filter(rule_id=rule_id).delete()
                if deleted_count:
                    self.stdout.write(f"Deleted {deleted_count} version history records for rule {rule_id}")

            RuleVersionHistory.objects.create(
                rule_id=rule_id,
                version=1,
                rule_content=rule_data.get('rule_content'),
                changed_by='system',
                change_comment='Initial import (force overwrite)' if force else 'Initial import'
            )

            defaults = {}
            for field, default_val in DEFAULTS_MAP.items():
                defaults[field] = rule_data.get(field, default_val)

            defaults['rule_content'] = rule_data.get('rule_content')
            defaults['rule_name'] = rule_data.get('rule_name', rule_id)
            defaults['rule_type'] = rule_data.get('rule_type', 'custom')
            defaults['description'] = rule_data.get('description', '')

            rule, created = RuleConfig.objects.update_or_create(
                rule_id=rule_id,
                defaults=defaults
            )

            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f"Created rule: {rule_id}"))
            else:
                updated_count += 1
                self.stdout.write(self.style.SUCCESS(f"Updated rule: {rule_id}"))

        self.stdout.write(self.style.SUCCESS(
            f"\nSummary: {created_count} created, {updated_count} updated, {skipped_count} skipped"
        ))

    def _validate_rules(self, rules_data):
        errors = []
        warnings = []
        seen_ids = set()

        valid_types = [choice[0] for choice in RuleConfig.RULE_TYPE_CHOICES]
        valid_scopes = [choice[0] for choice in RuleConfig.SCOPE_CHOICES]

        for i, rule_data in enumerate(rules_data):
            prefix = f"Rule #{i + 1}"
            rule_id = rule_data.get('rule_id', '')

            if isinstance(rule_data, str):
                continue

            for field in REQUIRED_FIELDS:
                if field not in rule_data:
                    errors.append(f"{prefix}: missing required field '{field}'")

            if rule_id in seen_ids:
                errors.append(f"{prefix}: duplicate rule_id '{rule_id}'")
            seen_ids.add(rule_id)

            engine_type = rule_data.get('engine_type', 'simpleeval')
            if engine_type == 'simpleeval' and not rule_data.get('rule_content'):
                errors.append(f"{prefix} ({rule_id}): engine_type=simpleeval requires rule_content")

            rule_type = rule_data.get('rule_type', '')
            if rule_type and rule_type not in valid_types:
                errors.append(
                    f"{prefix} ({rule_id}): invalid rule_type '{rule_type}', "
                    f"must be one of {valid_types}"
                )

            scope = rule_data.get('scope', 'global')
            if scope not in valid_scopes:
                errors.append(f"{prefix} ({rule_id}): invalid scope '{scope}', must be one of {valid_scopes}")

            self._validate_rule_content_structure(rule_data, prefix, rule_id, errors, warnings)

        for w in warnings:
            self.stdout.write(self.style.WARNING(f'  {w}'))

        return errors

    def _validate_rule_content_structure(self, rule_data, prefix, rule_id, errors, warnings):
        engine_type = rule_data.get('engine_type', 'simpleeval')
        rule_content = rule_data.get('rule_content')

        if engine_type != 'simpleeval' or not rule_content:
            return

        if not isinstance(rule_content, dict):
            errors.append(f"{prefix} ({rule_id}): rule_content must be a JSON object")
            return

        if 'format' not in rule_content:
            errors.append(
                f"{prefix} ({rule_id}): rule_content missing 'format' field "
                f"(expected 'decision_table' or 'simpleeval')"
            )
            return

        content_format = rule_content.get('format', '')
        if content_format == 'decision_table':
            table = rule_content.get('table')
            if not table or not isinstance(table, dict):
                errors.append(
                    f"{prefix} ({rule_id}): rule_content.format='decision_table' "
                    f"requires 'table' field as a JSON object"
                )
                return
            rules = table.get('rules', [])
            if not rules or not isinstance(rules, list):
                errors.append(
                    f"{prefix} ({rule_id}): decision_table.table must contain "
                    f"a non-empty 'rules' array"
                )
                return
            for r_idx, rule in enumerate(rules):
                if not isinstance(rule, dict):
                    errors.append(
                        f"{prefix} ({rule_id}): table.rules[{r_idx}] must be a JSON object"
                    )
                    continue
                if 'when' not in rule:
                    errors.append(
                        f"{prefix} ({rule_id}): table.rules[{r_idx}] missing 'when' field"
                    )
                if 'then' not in rule:
                    errors.append(
                        f"{prefix} ({rule_id}): table.rules[{r_idx}] missing 'then' field"
                    )
        elif content_format == 'simpleeval':
            expression = rule_content.get('conditions', {}).get('expression', '')
            if not expression:
                errors.append(
                    f"{prefix} ({rule_id}): rule_content.format='simpleeval' "
                    f"requires conditions.expression field"
                )
        else:
            errors.append(
                f"{prefix} ({rule_id}): unknown rule_content.format '{content_format}', "
                f"expected 'decision_table' or 'simpleeval'"
            )