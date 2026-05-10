import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction
from django.utils import timezone

from .models import RuleConfig, RuleVersionHistory
from .simple_rule_engine import SimpleRuleEngine
from .configurable_rule_engine import (
    ConfigurableRuleEngine,
    RuleNotFoundError,
    RuleValidationError,
    RuleEngineError,
    RuleExecutionMonitor,
)
from .cache_keys import CacheKeys
from .cache import get_cache
from .registry_watcher import RegistryWatcher

logger = logging.getLogger(__name__)

engine = ConfigurableRuleEngine()
_cache = get_cache()

FIELD_SCHEMA = {
    "Common Fields": [
        {"name": "alarm_storage_time", "field": "alarm_storage_time", "type": "string", "label": "Alarm Storage Time"},
        {"name": "object", "field": "object", "type": "string", "label": "Alert Object"},
        {"name": "item", "field": "item", "type": "string", "label": "Alert Metric"},
        {"name": "source_name", "field": "source_name", "type": "string", "label": "Alert Source Name"},
        {"name": "bkbizname", "field": "bkbizname", "type": "string", "label": "CMDB Business Name"},
        {"name": "event_level", "field": "event_level", "type": "string", "label": "Event Level"},
        {"name": "bk_app_code", "field": "bk_app_code", "type": "string", "label": "App Code"},
    ],
    "Alert Info": [
        {"name": "alarm_id", "field": "alarm_id", "type": "string", "label": "Alert ID"},
        {"name": "alarm_time", "field": "alarm_time", "type": "string", "label": "Alert Time"},
        {"name": "level", "field": "level", "type": "string", "label": "Alert Level"},
        {"name": "alarm_level_num", "field": "alarm_level_num", "type": "number", "label": "Numeric Level"},
        {"name": "action", "field": "action", "type": "string", "label": "Alert Action"},
        {"name": "duration", "field": "duration", "type": "number", "label": "Duration (s)"},
        {"name": "associate_count", "field": "associate_count", "type": "number", "label": "Associated Alerts"},
        {"name": "content", "field": "content", "type": "string", "label": "Alert Content"},
    ],
    "CMDB Info": [
        {"name": "cmdb_business_name", "field": "cmdb_business_name", "type": "string", "label": "CMDB Business Name (alt)"},
        {"name": "bksetname", "field": "bksetname", "type": "string", "label": "Set Name"},
        {"name": "bkmodulename", "field": "bkmodulename", "type": "string", "label": "Module Name"},
    ],
    "Source Info": [
        {"name": "source_id", "field": "source_id", "type": "string", "label": "Source ID"},
        {"name": "data_center", "field": "data_center", "type": "string", "label": "Data Center"},
        {"name": "belong_unit", "field": "belong_unit", "type": "string", "label": "Unit"},
    ],
    "Weight & Stats": [
        {"name": "predicted_weight", "field": "predicted_weight", "type": "number", "label": "Predicted Weight"},
        {"name": "alert_count_1h", "field": "alert_count_1h", "type": "number", "label": "1h Alert Count"},
        {"name": "alert_count_1d", "field": "alert_count_1d", "type": "number", "label": "1d Alert Count"},
        {"name": "useful_rate", "field": "useful_rate", "type": "number", "label": "Useful Rate"},
        {"name": "severity", "field": "severity", "type": "string", "label": "Severity"},
        {"name": "user_role", "field": "user_role", "type": "string", "label": "User Role"},
        {"name": "user_id", "field": "user_id", "type": "string", "label": "User ID"},
        {"name": "business_id", "field": "business_id", "type": "string", "label": "Business ID"},
        {"name": "category_key", "field": "category_key", "type": "string", "label": "Alert Category Key"},
    ],
}

TEMPLATES = [
    {
        "id": "biz_critical_push",
        "name": "Business App Alert - Core App Urgent Push",
        "description": "Immediately push to IM urgent group when critical alert occurs for core apps (order-api/payment-api/user-center)",
        "group": "Business App",
        "rule_type": "push_decision",
        "rule_content": {
            "format": "decision_table",
            "table": {
                "kind": "DecisionTable",
                "hitPolicy": "first",
                "inputs": [
                    {"name": "bk_app_code", "field": "bk_app_code", "type": "string"},
                    {"name": "level", "field": "level", "type": "string"}
                ],
                "outputs": [
                    {"name": "should_push", "field": "should_push", "type": "boolean"},
                    {"name": "action", "field": "action", "type": "string"},
                    {"name": "channel", "field": "channel", "type": "string"}
                ],
                "rules": [
                    {"id": "rule_0", "description": "Core app critical -> urgent push", "when": {"bk_app_code": ["order-api", "payment-api", "user-center"], "level": "critical"}, "then": {"should_push": True, "action": "send", "channel": "im_urgent"}},
                    {"id": "rule_default", "description": "Default fallback", "when": {}, "then": {"should_push": True, "action": "send", "channel": "im_normal"}}
                ]
            }
        }
    },
    {
        "id": "biz_noise_suppress",
        "name": "Business App Alert - Noise Suppression",
        "description": "Suppress remind-level alerts for non-core businesses to reduce noise",
        "group": "Business App",
        "rule_type": "push_decision",
        "rule_content": {
            "format": "decision_table",
            "table": {
                "kind": "DecisionTable",
                "hitPolicy": "first",
                "inputs": [
                    {"name": "bk_app_code", "field": "bk_app_code", "type": "string"},
                    {"name": "level", "field": "level", "type": "string"}
                ],
                "outputs": [
                    {"name": "should_push", "field": "should_push", "type": "boolean"},
                    {"name": "action", "field": "action", "type": "string"},
                    {"name": "channel", "field": "channel", "type": "string"}
                ],
                "rules": [
                    {"id": "rule_0", "description": "Non-core app remind -> suppress", "when": {"bk_app_code": "", "level": "remind"}, "then": {"should_push": False, "action": "suppress", "channel": "suppressed"}},
                    {"id": "rule_default", "description": "Default fallback", "when": {}, "then": {"should_push": True, "action": "send", "channel": "im_normal"}}
                ]
            }
        }
    },
    {
        "id": "infra_storm_suppress",
        "name": "Infrastructure Alert - Storm Suppression",
        "description": "Suppress push when associated alert count exceeds threshold to avoid alert storm",
        "group": "Infrastructure",
        "rule_type": "push_decision",
        "rule_content": {
            "format": "decision_table",
            "table": {
                "kind": "DecisionTable",
                "hitPolicy": "first",
                "inputs": [
                    {"name": "associate_count", "field": "associate_count", "type": "number"}
                ],
                "outputs": [
                    {"name": "should_push", "field": "should_push", "type": "boolean"},
                    {"name": "action", "field": "action", "type": "string"},
                    {"name": "channel", "field": "channel", "type": "string"}
                ],
                "rules": [
                    {"id": "rule_0", "description": "Associate count > 10 -> suppress", "when": {"associate_count": ">10"}, "then": {"should_push": False, "action": "suppress", "channel": "suppressed"}},
                    {"id": "rule_default", "description": "Default fallback", "when": {}, "then": {"should_push": True, "action": "send", "channel": "im_normal"}}
                ]
            }
        }
    }
]


def _rule_to_dict(rule):
    return {
        "rule_id": rule.rule_id,
        "rule_name": rule.rule_name,
        "rule_type": rule.rule_type,
        "engine_type": rule.engine_type,
        "scope": rule.scope,
        "priority": rule.priority,
        "is_active": rule.is_active,
        "business_id": rule.business_id,
        "description": rule.description or "",
        "rule_content": rule.rule_content,
        "created_at": rule.created_at.isoformat() if rule.created_at else "",
        "updated_at": rule.updated_at.isoformat() if rule.updated_at else "",
    }


def _validate_rule_content(rule_content):
    errors = []
    if not isinstance(rule_content, dict):
        return ["rule_content must be a JSON object"]
    fmt = rule_content.get("format")
    if fmt != "decision_table":
        errors.append("rule_content.format must be 'decision_table'")
    table = rule_content.get("table")
    if not isinstance(table, dict):
        errors.append("rule_content.table is required")
        return errors
    if table.get("kind") != "DecisionTable":
        errors.append("table.kind must be 'DecisionTable'")
    inputs = table.get("inputs", [])
    if not isinstance(inputs, list) or len(inputs) == 0:
        errors.append("table.inputs must be a non-empty array")
    outputs = table.get("outputs", [])
    if not isinstance(outputs, list) or len(outputs) == 0:
        errors.append("table.outputs must be a non-empty array")
    rules = table.get("rules", [])
    if not isinstance(rules, list) or len(rules) == 0:
        errors.append("table.rules must be a non-empty array")
    for i, inp in enumerate(inputs):
        if not inp.get("name") or not inp.get("field"):
            errors.append(f"table.inputs[{i}] requires name and field")
    for i, out in enumerate(outputs):
        if not out.get("name") or not out.get("field"):
            errors.append(f"table.outputs[{i}] requires name and field")
    for i, r in enumerate(rules):
        if not r.get("id"):
            errors.append(f"table.rules[{i}] requires id")
        if "when" not in r or "then" not in r:
            errors.append(f"table.rules[{i}] requires when and then")
    return errors


def _auto_group(rule):
    table = (rule.rule_content or {}).get("table", {})
    rules = table.get("rules", [])
    if not rules:
        return "General"
    first_when = rules[0].get("when", {})
    first_key = next(iter(first_when), "") if first_when else ""
    if first_key == "bk_app_code":
        if isinstance(first_when.get(first_key), str) and first_when.get(first_key) == "":
            return "Infrastructure"
        return "Business App"
    if first_key in ("data_center", "source_name", "item", "object", "asset_code"):
        return "Infrastructure"
    return "General"


# ==================== Configurable Rule Engine API ====================

class ConfigurableRuleEvaluateView(APIView):
    def post(self, request):
        rule_id = request.data.get('rule_id')
        context = request.data.get('context', {})
        business_group = request.data.get('business_group') or request.headers.get('X-Business-Group')

        if not rule_id:
            return Response(
                {"error": "rule_id is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            result = engine.evaluate(rule_id, context, business_group)
            return Response(result.to_dict())
        except RuleNotFoundError as e:
            return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)
        except RuleEngineError as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ConfigurableRuleListView(APIView):
    def get(self, request):
        business_group = request.query_params.get('business_group') or request.headers.get('X-Business-Group')
        rule_type = request.query_params.get('rule_type')
        engine_type = request.query_params.get('engine_type')

        queryset = RuleConfig.objects.all().order_by('priority')
        if rule_type:
            queryset = queryset.filter(rule_type=rule_type)
        if engine_type:
            queryset = queryset.filter(engine_type=engine_type)
        if business_group:
            from django.db import models as django_models
            queryset = queryset.filter(
                django_models.Q(business_group=business_group) | django_models.Q(business_group='')
            )

        rules = [{
            'rule_id': r.rule_id,
            'rule_name': r.rule_name,
            'rule_type': r.rule_type,
            'engine_type': r.engine_type,
            'scope': r.scope,
            'is_active': r.is_active,
            'priority': r.priority,
            'version': r.version,
            'description': r.description,
        } for r in queryset]

        return Response({"rules": rules})

    def post(self, request):
        try:
            result = engine.create_rule(request.data, created_by=request.data.get('created_by', ''))
            return Response(result, status=status.HTTP_201_CREATED)
        except RuleValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Failed to create rule: {e}")
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ConfigurableRuleDetailView(APIView):
    def get(self, request, rule_id):
        try:
            rule = RuleConfig.objects.get(rule_id=rule_id)
            return Response({
                'rule_id': rule.rule_id,
                'rule_name': rule.rule_name,
                'rule_type': rule.rule_type,
                'engine_type': rule.engine_type,
                'scope': rule.scope,
                'business_group': rule.business_group,
                'category_key': rule.category_key,
                'priority': rule.priority,
                'is_active': rule.is_active,
                'version': rule.version,
                'description': rule.description,
                'rule_content': rule.rule_content,
                'created_at': rule.created_at.isoformat(),
                'updated_at': rule.updated_at.isoformat(),
            })
        except RuleConfig.DoesNotExist:
            return Response({"error": "Rule not found"}, status=status.HTTP_404_NOT_FOUND)

    def put(self, request, rule_id):
        try:
            result = engine.update_rule(
                rule_id,
                request.data,
                changed_by=request.data.get('changed_by', ''),
                change_comment=request.data.get('change_comment', '')
            )
            return Response(result)
        except RuleNotFoundError as e:
            return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)
        except RuleValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, rule_id):
        try:
            rule = RuleConfig.objects.get(rule_id=rule_id)
            rule.is_active = False
            rule.save()
            return Response({"status": "deactivated", "rule_id": rule_id})
        except RuleConfig.DoesNotExist:
            return Response({"error": "Rule not found"}, status=status.HTTP_404_NOT_FOUND)


class ConfigurableRuleTestView(APIView):
    def post(self, request, rule_id):
        test_context = request.data.get('context', {})
        result = engine.test_rule(rule_id, test_context)
        return Response(result)


class ConfigurableRuleTestSuiteView(APIView):
    def post(self, request, rule_id):
        test_cases = request.data.get('test_cases', [])
        result = engine.run_test_suite(rule_id, test_cases)
        return Response(result)


class ConfigurableRuleValidateView(APIView):
    def post(self, request):
        expression = request.data.get('expression', '')
        result = engine.validate_expression_syntax(expression)
        return Response(result)


class ConfigurableRulePublishView(APIView):
    def post(self, request, rule_id):
        version = request.data.get('version')
        if not version:
            return Response({"error": "version is required"}, status=400)

        try:
            result = engine.publish_rule(rule_id, version, published_by=request.data.get('published_by', ''))
            return Response(result)
        except RuleNotFoundError as e:
            return Response({"error": str(e)}, status=404)


class ConfigurableRuleRollbackView(APIView):
    def post(self, request, rule_id):
        to_version = request.data.get('to_version')
        if not to_version:
            return Response({"error": "to_version is required"}, status=400)

        try:
            result = engine.rollback_rule(rule_id, to_version)
            return Response(result)
        except RuleNotFoundError as e:
            return Response({"error": str(e)}, status=404)


class ConfigurableRuleVersionView(APIView):
    def get(self, request, rule_id):
        versions = RuleVersionHistory.objects.filter(rule_id=rule_id).order_by('-version')
        version_list = [{
            'version': v.version,
            'rule_content': v.rule_content,
            'changed_by': v.changed_by,
            'change_comment': v.change_comment,
            'created_at': v.created_at.isoformat(),
        } for v in versions]
        return Response({"versions": version_list})


class ConfigurableRuleEngineHealthView(APIView):
    def get(self, request):
        health = RuleExecutionMonitor.get_engine_health()
        return Response(health)


# ==================== Rule Config Visual Editor API ====================

class RuleConfigListView(APIView):
    def get(self, request):
        group = request.query_params.get("group", "all")
        rule_type = request.query_params.get("rule_type")
        is_active = request.query_params.get("is_active")

        qs = RuleConfig.objects.all().order_by("priority")
        if rule_type:
            qs = qs.filter(rule_type=rule_type)
        if is_active is not None:
            qs = qs.filter(is_active=(is_active.lower() == "true"))

        rules = []
        for r in qs:
            d = _rule_to_dict(r)
            d["group"] = _auto_group(r)
            rules.append(d)

        if group != "all":
            rules = [r for r in rules if r["group"] == group]

        return Response({"rules": rules, "total": len(rules)})

    def post(self, request):
        data = request.data
        rule_id = data.get("rule_id")
        if not rule_id:
            return Response({"error": "rule_id is required"}, status=400)
        if RuleConfig.objects.filter(rule_id=rule_id).exists():
            return Response({"error": f"rule_id '{rule_id}' already exists"}, status=409)

        rc = data.get("rule_content", {})
        errors = _validate_rule_content(rc)
        if errors:
            return Response({"error": "Validation failed", "details": errors}, status=400)

        with transaction.atomic():
            rule = RuleConfig.objects.create(
                rule_id=rule_id,
                rule_name=data.get("rule_name", rule_id),
                rule_type=data.get("rule_type", "push_decision"),
                engine_type="simpleeval",
                scope=data.get("scope", "global"),
                priority=data.get("priority", 0),
                is_active=data.get("is_active", True),
                business_id=data.get("business_id", ""),
                rule_content=rc,
                description=data.get("description", ""),
                created_by=data.get("created_by", ""),
            )
            RuleVersionHistory.objects.create(
                rule_id=rule_id,
                version=1,
                rule_content=rc,
                changed_by=data.get("created_by", ""),
                change_comment="Initial creation",
            )

        _cache.delete(CacheKeys.RULE_JDM.format(rule_id=rule_id))
        RegistryWatcher.bump_version()
        return Response(_rule_to_dict(rule), status=201)


class RuleConfigDetailView(APIView):
    def get(self, request, rule_id):
        try:
            rule = RuleConfig.objects.get(rule_id=rule_id)
        except RuleConfig.DoesNotExist:
            return Response({"error": "Rule not found"}, status=404)
        d = _rule_to_dict(rule)
        d["group"] = _auto_group(rule)
        return Response(d)

    def put(self, request, rule_id):
        try:
            rule = RuleConfig.objects.get(rule_id=rule_id)
        except RuleConfig.DoesNotExist:
            return Response({"error": "Rule not found"}, status=404)

        data = request.data
        rc = data.get("rule_content")
        if rc is not None:
            errors = _validate_rule_content(rc)
            if errors:
                return Response({"error": "Validation failed", "details": errors}, status=400)

        with transaction.atomic():
            new_version = rule.version + 1
            RuleVersionHistory.objects.create(
                rule_id=rule_id,
                version=new_version,
                rule_content=rc if rc is not None else rule.rule_content,
                changed_by=data.get("changed_by", ""),
                change_comment=data.get("change_comment", "Updated via API"),
            )

            if "rule_name" in data:
                rule.rule_name = data["rule_name"]
            if "rule_type" in data:
                rule.rule_type = data["rule_type"]
            if "scope" in data:
                rule.scope = data["scope"]
            if "priority" in data:
                rule.priority = data["priority"]
            if "is_active" in data:
                rule.is_active = data["is_active"]
            if "business_id" in data:
                rule.business_id = data["business_id"]
            if "description" in data:
                rule.description = data["description"]
            if rc is not None:
                rule.rule_content = rc
            rule.version = new_version
            rule.save()

        _cache.delete(CacheKeys.RULE_JDM.format(rule_id=rule_id))
        RegistryWatcher.bump_version()
        return Response(_rule_to_dict(rule))

    def delete(self, request, rule_id):
        try:
            rule = RuleConfig.objects.get(rule_id=rule_id)
        except RuleConfig.DoesNotExist:
            return Response({"error": "Rule not found"}, status=404)
        rule.delete()
        _cache.delete(CacheKeys.RULE_JDM.format(rule_id=rule_id))
        RegistryWatcher.bump_version()
        return Response({"message": f"Rule '{rule_id}' deleted"}, status=200)


class RuleFieldSchemaView(APIView):
    def get(self, request):
        return Response({"groups": FIELD_SCHEMA})


class RuleTestAllView(APIView):
    def post(self, request):
        context = request.data.get("context", {})
        if not context:
            return Response({"error": "context is required"}, status=400)

        results = []
        rules = RuleConfig.objects.filter(is_active=True).order_by("priority")

        for rule in rules:
            rc = rule.rule_content or {}
            fmt = rc.get("format")
            table = None
            if fmt == "decision_table":
                table = rc.get("table", {})
            elif "conditions" in rc and "table" in rc.get("conditions", {}):
                table = rc["conditions"]["table"]

            matched = False
            result = {}
            if table:
                try:
                    result = SimpleRuleEngine.evaluate_decision_table(table, context)
                    matched = not result.get("fallback", False)
                except Exception:
                    pass

            results.append({
                "rule_id": rule.rule_id,
                "rule_name": rule.rule_name,
                "priority": rule.priority,
                "matched": matched,
                "result": result,
            })

        return Response({"context": context, "results": results})


class RuleHistoryView(APIView):
    def get(self, request, rule_id):
        versions = RuleVersionHistory.objects.filter(rule_id=rule_id).order_by("-version")
        data = [{
            "version": v.version,
            "rule_content": v.rule_content,
            "changed_by": v.changed_by,
            "change_comment": v.change_comment,
            "created_at": v.created_at.isoformat() if v.created_at else "",
        } for v in versions]
        return Response({"rule_id": rule_id, "versions": data})


class RuleValidateView(APIView):
    def post(self, request):
        rule_content = request.data.get("rule_content", {})
        errors = _validate_rule_content(rule_content)
        if errors:
            return Response({"valid": False, "errors": errors})
        return Response({"valid": True})


class RuleTemplateView(APIView):
    def get(self, request):
        return Response({"templates": TEMPLATES})