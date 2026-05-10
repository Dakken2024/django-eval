from django.urls import path
from .views import (
    ConfigurableRuleEvaluateView, ConfigurableRuleListView, ConfigurableRuleDetailView,
    ConfigurableRuleTestView, ConfigurableRuleTestSuiteView, ConfigurableRuleValidateView,
    ConfigurableRulePublishView, ConfigurableRuleRollbackView, ConfigurableRuleVersionView,
    ConfigurableRuleEngineHealthView,
    RuleConfigListView, RuleConfigDetailView,
    RuleFieldSchemaView, RuleTestAllView,
    RuleHistoryView, RuleValidateView,
    RuleTemplateView,
)

urlpatterns = [
    path('evaluate', ConfigurableRuleEvaluateView.as_view(), name='ee-evaluate'),
    path('health', ConfigurableRuleEngineHealthView.as_view(), name='ee-health'),

    path('rules', ConfigurableRuleListView.as_view(), name='ee-rule-list'),
    path('rules/validate', ConfigurableRuleValidateView.as_view(), name='ee-rule-validate'),
    path('rules/<str:rule_id>', ConfigurableRuleDetailView.as_view(), name='ee-rule-detail'),
    path('rules/<str:rule_id>/test', ConfigurableRuleTestView.as_view(), name='ee-rule-test'),
    path('rules/<str:rule_id>/test-suite', ConfigurableRuleTestSuiteView.as_view(), name='ee-rule-test-suite'),
    path('rules/<str:rule_id>/publish', ConfigurableRulePublishView.as_view(), name='ee-rule-publish'),
    path('rules/<str:rule_id>/rollback', ConfigurableRuleRollbackView.as_view(), name='ee-rule-rollback'),
    path('rules/<str:rule_id>/versions', ConfigurableRuleVersionView.as_view(), name='ee-rule-versions'),

    path('rule-config', RuleConfigListView.as_view(), name='ee-rule-config-list'),
    path('rule-config/', RuleConfigListView.as_view(), name='ee-rule-config-list-slash'),
    path('rule-config/field-schema', RuleFieldSchemaView.as_view(), name='ee-field-schema'),
    path('rule-config/templates', RuleTemplateView.as_view(), name='ee-templates'),
    path('rule-config/validate', RuleValidateView.as_view(), name='ee-validate'),
    path('rule-config/test-all', RuleTestAllView.as_view(), name='ee-test-all'),
    path('rule-config/<str:rule_id>', RuleConfigDetailView.as_view(), name='ee-rule-config-detail'),
    path('rule-config/<str:rule_id>/history', RuleHistoryView.as_view(), name='ee-history'),
]