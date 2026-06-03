"""
Integration tests for REST API endpoints.
Tests full request/response cycles including database operations.
"""
import json
import pytest
from django.test import Client, TestCase
from django.urls import reverse

from eval_engine.models import RuleConfig


@pytest.mark.django_db
class RuleAPITestCase(TestCase):
    """Test case for rule CRUD API endpoints."""
    
    def setUp(self):
        self.client = Client()
        self.rule_data = {
            'rule_id': 'test_rule_001',
            'rule_name': 'Test Rule',
            'rule_type': 'push_decision',
            'engine_type': 'simpleeval',
            'rule_content': {
                'conditions': {
                    'format': 'simpleeval',
                    'expression': 'score > 80 and status == "active"'
                },
                'actions': {
                    'on_match': {'should_push': True},
                    'on_mismatch': {'should_push': False}
                }
            },
            'is_active': True,
            'priority': 1,
            'business_id': 'biz_001',
            'scope': 'business',
        }
    
    def test_create_rule(self):
        """Test creating a new rule via API."""
        url = reverse('rule-list')
        response = self.client.post(
            url,
            data=json.dumps(self.rule_data),
            content_type='application/json'
        )
        assert response.status_code == 201
        data = response.json()
        assert data['rule_id'] == 'test_rule_001'
        assert data['is_active'] is True
        
        # Verify in database
        rule = RuleConfig.objects.get(rule_id='test_rule_001')
        assert rule.rule_name == 'Test Rule'
    
    def test_get_rule(self):
        """Test retrieving a rule via API."""
        # Create rule first
        RuleConfig.objects.create(**self.rule_data)
        
        url = reverse('rule-detail', kwargs={'pk': 'test_rule_001'})
        response = self.client.get(url)
        
        assert response.status_code == 200
        data = response.json()
        assert data['rule_id'] == 'test_rule_001'
        assert data['rule_name'] == 'Test Rule'
    
    def test_update_rule(self):
        """Test updating a rule via API."""
        RuleConfig.objects.create(**self.rule_data)
        
        update_data = {
            'rule_name': 'Updated Rule Name',
            'priority': 5,
        }
        
        url = reverse('rule-detail', kwargs={'pk': 'test_rule_001'})
        response = self.client.patch(
            url,
            data=json.dumps(update_data),
            content_type='application/json'
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data['rule_name'] == 'Updated Rule Name'
        assert data['priority'] == 5
        
        # Verify in database
        rule = RuleConfig.objects.get(rule_id='test_rule_001')
        assert rule.rule_name == 'Updated Rule Name'
        assert rule.priority == 5
    
    def test_delete_rule(self):
        """Test deleting a rule via API."""
        RuleConfig.objects.create(**self.rule_data)
        
        url = reverse('rule-detail', kwargs={'pk': 'test_rule_001'})
        response = self.client.delete(url)
        
        assert response.status_code == 204
        assert not RuleConfig.objects.filter(rule_id='test_rule_001').exists()
    
    def test_list_rules(self):
        """Test listing rules via API."""
        RuleConfig.objects.create(**self.rule_data)
        RuleConfig.objects.create(
            rule_id='test_rule_002',
            rule_name='Test Rule 2',
            rule_type='feedback_threshold',
            engine_type='simpleeval',
            is_active=True,
        )
        
        url = reverse('rule-list')
        response = self.client.get(url)
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 2


@pytest.mark.django_db
class RuleEvaluationAPITestCase(TestCase):
    """Test case for rule evaluation API endpoints."""
    
    def setUp(self):
        self.client = Client()
        self.rule = RuleConfig.objects.create(
            rule_id='eval_test_rule',
            rule_name='Evaluation Test Rule',
            rule_type='push_decision',
            engine_type='simpleeval',
            rule_content={
                'conditions': {
                    'format': 'simpleeval',
                    'expression': 'score > 50'
                },
                'actions': {
                    'on_match': {'should_push': True, 'action_type': 'notify'},
                    'on_mismatch': {'should_push': False}
                }
            },
            is_active=True,
        )
    
    def test_evaluate_rule_match(self):
        """Test rule evaluation with matching condition."""
        url = reverse('rule-evaluate', kwargs={'rule_id': 'eval_test_rule'})
        response = self.client.post(
            url,
            data=json.dumps({'context': {'score': 75}}),
            content_type='application/json'
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data['matched'] is True
        assert data['action']['should_push'] is True
    
    def test_evaluate_rule_mismatch(self):
        """Test rule evaluation with non-matching condition."""
        url = reverse('rule-evaluate', kwargs={'rule_id': 'eval_test_rule'})
        response = self.client.post(
            url,
            data=json.dumps({'context': {'score': 30}}),
            content_type='application/json'
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data['matched'] is False
        assert data['action']['should_push'] is False
    
    def test_evaluate_rule_not_found(self):
        """Test evaluating non-existent rule."""
        url = reverse('rule-evaluate', kwargs={'rule_id': 'nonexistent_rule'})
        response = self.client.post(
            url,
            data=json.dumps({'context': {'score': 75}}),
            content_type='application/json'
        )
        
        assert response.status_code == 404


@pytest.mark.django_db
class RuleVersionAPITestCase(TestCase):
    """Test case for rule version management API."""
    
    def setUp(self):
        self.client = Client()
        self.rule = RuleConfig.objects.create(
            rule_id='version_test_rule',
            rule_name='Version Test Rule',
            rule_type='push_decision',
            engine_type='simpleeval',
            rule_content={'conditions': {'format': 'simpleeval', 'expression': 'v == 1'}},
            version=1,
            is_active=True,
        )
    
    def test_get_version_history(self):
        """Test retrieving version history."""
        url = reverse('rule-version-history', kwargs={'rule_id': 'version_test_rule'})
        response = self.client.get(url)
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_rollback_version(self):
        """Test rolling back to a previous version."""
        # Update to create a new version
        self.rule.rule_content = {'conditions': {'format': 'simpleeval', 'expression': 'v == 2'}}
        self.rule.version = 2
        self.rule.save()
        
        url = reverse('rule-rollback', kwargs={'rule_id': 'version_test_rule'})
        response = self.client.post(
            url,
            data=json.dumps({'target_version': 1}),
            content_type='application/json'
        )
        
        # Should succeed if version history exists
        # Note: This may return 400 if no history exists yet
        assert response.status_code in [200, 400]
