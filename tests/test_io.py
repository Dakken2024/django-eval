"""Tests for rule import/export functionality."""
import json
import pytest
from django.test import TestCase
from eval_engine.models import RuleConfig
from eval_engine.io import RuleExporter, RuleImporter


@pytest.mark.django_db
class TestRuleExporter(TestCase):
    """Test cases for RuleExporter."""
    
    def setUp(self):
        self.rule = RuleConfig.objects.create(
            rule_id='test_rule_001',
            rule_name='Test Rule',
            rule_type='push_decision',
            engine_type='simpleeval',
            rule_content={'format': 'decision_table', 'table': {}},
            version=1,
            is_active=True,
            priority=0,
            business_id='test_biz',
            description='Test rule for export',
        )
    
    def test_export_rule_to_dict(self):
        """Test exporting a single rule to dictionary."""
        result = RuleExporter.export_rule_to_dict(self.rule)
        
        assert result['rule_id'] == 'test_rule_001'
        assert result['rule_name'] == 'Test Rule'
        assert result['rule_type'] == 'push_decision'
        assert result['is_active'] is True
    
    def test_export_rule_to_json(self):
        """Test exporting a single rule to JSON."""
        json_str = RuleExporter.export_rule_to_json(self.rule)
        data = json.loads(json_str)
        
        assert data['rule_id'] == 'test_rule_001'
        assert data['rule_name'] == 'Test Rule'
    
    def test_export_rules_to_json(self):
        """Test exporting multiple rules to JSON."""
        rules = RuleConfig.objects.all()
        json_str = RuleExporter.export_rules_to_json(rules)
        data = json.loads(json_str)
        
        assert 'rules' in data
        assert data['count'] >= 1


@pytest.mark.django_db
class TestRuleImporter(TestCase):
    """Test cases for RuleImporter."""
    
    def test_validate_rule_dict_valid(self):
        """Test validation with valid data."""
        data = {
            'rule_id': 'new_rule',
            'rule_name': 'New Rule',
            'rule_type': 'push_decision',
        }
        errors = RuleImporter.validate_rule_dict(data)
        assert len(errors) == 0
    
    def test_validate_rule_dict_missing_field(self):
        """Test validation with missing required field."""
        data = {
            'rule_id': 'new_rule',
            'rule_name': 'New Rule',
            # Missing rule_type
        }
        errors = RuleImporter.validate_rule_dict(data)
        assert any('rule_type' in e for e in errors)
    
    def test_validate_rule_dict_invalid_type(self):
        """Test validation with invalid rule_type."""
        data = {
            'rule_id': 'new_rule',
            'rule_name': 'New Rule',
            'rule_type': 'invalid_type',
        }
        errors = RuleImporter.validate_rule_dict(data)
        assert any('Invalid rule_type' in e for e in errors)
    
    def test_import_rule_from_dict(self):
        """Test importing a rule from dictionary."""
        data = {
            'rule_id': 'imported_rule',
            'rule_name': 'Imported Rule',
            'rule_type': 'push_decision',
            'engine_type': 'simpleeval',
            'description': 'Imported via test',
        }
        rule = RuleImporter.import_rule_from_dict(data)
        
        assert rule.rule_id == 'imported_rule'
        assert rule.rule_name == 'Imported Rule'
        assert rule.is_active is True
    
    def test_import_rule_duplicate_without_overwrite(self):
        """Test importing duplicate rule without overwrite."""
        data = {
            'rule_id': 'dup_rule',
            'rule_name': 'Duplicate Rule',
            'rule_type': 'push_decision',
        }
        RuleImporter.import_rule_from_dict(data)
        
        with pytest.raises(ValueError) as exc_info:
            RuleImporter.import_rule_from_dict(data, overwrite=False)
        
        assert 'already exists' in str(exc_info.value)
    
    def test_import_rule_duplicate_with_overwrite(self):
        """Test importing duplicate rule with overwrite."""
        data = {
            'rule_id': 'overwrite_rule',
            'rule_name': 'Original Name',
            'rule_type': 'push_decision',
        }
        RuleImporter.import_rule_from_dict(data)
        
        # Update with overwrite
        data['rule_name'] = 'Updated Name'
        rule = RuleImporter.import_rule_from_dict(data, overwrite=True)
        
        assert rule.rule_name == 'Updated Name'
    
    def test_import_rules_from_dict(self):
        """Test importing multiple rules."""
        data = {
            'rules': [
                {
                    'rule_id': 'batch_rule_1',
                    'rule_name': 'Batch Rule 1',
                    'rule_type': 'push_decision',
                },
                {
                    'rule_id': 'batch_rule_2',
                    'rule_name': 'Batch Rule 2',
                    'rule_type': 'feedback_threshold',
                },
            ]
        }
        result = RuleImporter.import_rules_from_dict(data)
        
        assert result['total'] == 2
        assert result['success'] == 2
        assert result['failed'] == 0
    
    def test_import_rules_from_json(self):
        """Test importing rules from JSON string."""
        json_str = json.dumps({
            'rules': [
                {
                    'rule_id': 'json_rule',
                    'rule_name': 'JSON Rule',
                    'rule_type': 'push_decision',
                }
            ]
        })
        result = RuleImporter.import_rules_from_json(json_str)
        
        assert result['success'] == 1
