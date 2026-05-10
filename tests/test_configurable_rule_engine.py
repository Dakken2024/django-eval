import pytest
from unittest.mock import Mock, patch, MagicMock
from django.core.cache import cache
from django.test import TestCase, override_settings

from eval_engine.configurable_rule_engine import (
    ConfigurableRuleEngine,
    ExpressionValidator,
    RuleFunctionRegistry,
    RuleExecutionMonitor,
    RuleEvaluationResult,
    RuleSecurityError,
    RuleValidationError,
    RuleNotFoundError,
    FORBIDDEN_PATTERNS,
    ALLOWED_FUNCTIONS,
)


class TestExpressionValidator(TestCase):

    def test_valid_simple_expression(self):
        is_valid, error = ExpressionValidator.validate("severity == 'critical'")
        self.assertTrue(is_valid)
        self.assertIsNone(error)

    def test_valid_complex_expression(self):
        expr = "(severity == 'critical' and alert_count_1h > 10) or business_priority == 'P0'"
        is_valid, error = ExpressionValidator.validate(expr)
        self.assertTrue(is_valid)
        self.assertIsNone(error)

    def test_forbidden_import(self):
        is_valid, error = ExpressionValidator.validate("__import__('os').system('ls')")
        self.assertFalse(is_valid)
        self.assertIn('Forbidden', error)

    def test_forbidden_eval(self):
        is_valid, error = ExpressionValidator.validate("eval('1+1')")
        self.assertFalse(is_valid)
        self.assertIn('Forbidden', error)

    def test_forbidden_os_module(self):
        is_valid, error = ExpressionValidator.validate("os.system('ls')")
        self.assertFalse(is_valid)

    def test_empty_expression(self):
        is_valid, error = ExpressionValidator.validate("")
        self.assertFalse(is_valid)
        self.assertIn('non-empty', error)

    def test_sanitize_context(self):
        context = {
            'severity': 'critical',
            'api_key': 'secret123',
            'password': 'mypassword',
            'user_id': 'user001',
        }
        sanitized = ExpressionValidator.sanitize_context(context)
        self.assertEqual(sanitized['severity'], 'critical')
        self.assertEqual(sanitized['api_key'], '***REDACTED***')
        self.assertEqual(sanitized['password'], '***REDACTED***')
        self.assertEqual(sanitized['user_id'], 'user001')


class TestRuleFunctionRegistry(TestCase):

    def test_builtin_functions_exist(self):
        funcs = RuleFunctionRegistry.get_all()
        self.assertIn('in_business_hours', funcs)
        self.assertIn('is_weekend', funcs)
        self.assertIn('severity_score', funcs)
        self.assertIn('priority_score', funcs)
        self.assertIn('between', funcs)

    def test_severity_score(self):
        func = RuleFunctionRegistry.get('severity_score')
        self.assertEqual(func('critical'), 3)
        self.assertEqual(func('warning'), 2)
        self.assertEqual(func('info'), 1)
        self.assertEqual(func('unknown'), 1)

    def test_priority_score(self):
        func = RuleFunctionRegistry.get('priority_score')
        self.assertEqual(func('P0'), 5)
        self.assertEqual(func('P3'), 2)
        self.assertEqual(func('unknown'), 1)

    def test_between_function(self):
        func = RuleFunctionRegistry.get('between')
        self.assertTrue(func(5, 1, 10))
        self.assertFalse(func(15, 1, 10))
        self.assertTrue(func(1, 1, 10))

    def test_custom_function_registration(self):
        def custom_func(x):
            return x * 2

        RuleFunctionRegistry.register('double', custom_func)
        func = RuleFunctionRegistry.get('double')
        self.assertEqual(func(5), 10)


class TestConfigurableRuleEngine(TestCase):

    def setUp(self):
        self.engine = ConfigurableRuleEngine()
        cache.clear()

    def tearDown(self):
        cache.clear()

    @patch('eval_engine.configurable_rule_engine.RuleConfig')
    def test_evaluate_simpleeval_rule(self, MockRuleConfig):
        mock_rule = Mock()
        mock_rule.rule_id = 'test_rule'
        mock_rule.rule_name = 'Test Rule'
        mock_rule.rule_type = 'push_decision'
        mock_rule.engine_type = 'simpleeval'
        mock_rule.scope = 'global'
        mock_rule.business_group = ''
        mock_rule.category_key = ''
        mock_rule.priority = 0
        mock_rule.is_active = True
        mock_rule.rule_content = {
            'conditions': {
                'format': 'simpleeval',
                'expression': "severity == 'critical' and alert_count_1h > 10"
            },
            'actions': {
                'on_match': {'should_push': True, 'channel': 'im_urgent'},
                'on_mismatch': {'should_push': False, 'reason': 'rule_not_matched'}
            },
            'context': {'required_fields': ['severity', 'alert_count_1h']},
            'metadata': {}
        }

        MockRuleConfig.objects.get.return_value = mock_rule

        context = {'severity': 'critical', 'alert_count_1h': 15}
        result = self.engine.evaluate('test_rule', context, use_cache=False)

        self.assertTrue(result.matched)
        self.assertTrue(result.action['should_push'])
        self.assertEqual(result.action['channel'], 'im_urgent')

    @patch('eval_engine.configurable_rule_engine.RuleConfig')
    def test_evaluate_rule_no_match(self, MockRuleConfig):
        mock_rule = Mock()
        mock_rule.rule_id = 'test_rule'
        mock_rule.rule_name = 'Test Rule'
        mock_rule.rule_type = 'push_decision'
        mock_rule.engine_type = 'simpleeval'
        mock_rule.scope = 'global'
        mock_rule.business_group = ''
        mock_rule.category_key = ''
        mock_rule.priority = 0
        mock_rule.is_active = True
        mock_rule.rule_content = {
            'conditions': {
                'format': 'simpleeval',
                'expression': "severity == 'critical'"
            },
            'actions': {
                'on_match': {'should_push': True},
                'on_mismatch': {'should_push': False, 'reason': 'not_critical'}
            },
            'context': {},
            'metadata': {}
        }

        MockRuleConfig.objects.get.return_value = mock_rule

        context = {'severity': 'warning'}
        result = self.engine.evaluate('test_rule', context, use_cache=False)

        self.assertFalse(result.matched)
        self.assertFalse(result.action['should_push'])
        self.assertEqual(result.action['reason'], 'not_critical')

    @patch('eval_engine.configurable_rule_engine.RuleConfig')
    def test_evaluate_decision_table_rule(self, MockRuleConfig):
        mock_rule = Mock()
        mock_rule.rule_id = 'table_rule'
        mock_rule.rule_name = 'Table Rule'
        mock_rule.rule_type = 'push_decision'
        mock_rule.engine_type = 'simpleeval'
        mock_rule.scope = 'global'
        mock_rule.business_group = ''
        mock_rule.category_key = ''
        mock_rule.priority = 0
        mock_rule.is_active = True
        mock_rule.rule_content = {
            'conditions': {
                'format': 'decision_table',
                'table': {
                    'inputs': [
                        {'name': 'severity'},
                        {'name': 'alert_count_1h'}
                    ],
                    'outputs': [
                        {'name': 'should_push'},
                        {'name': 'channel'}
                    ],
                    'rules': [
                        {
                            'when': {'severity': 'critical', 'alert_count_1h': '>= 10'},
                            'then': {'should_push': True, 'channel': 'im_urgent'}
                        }
                    ]
                }
            },
            'actions': {
                'on_match': {},
                'on_mismatch': {'should_push': False}
            },
            'context': {},
            'metadata': {}
        }

        MockRuleConfig.objects.get.return_value = mock_rule

        context = {'severity': 'critical', 'alert_count_1h': 15}
        result = self.engine.evaluate('table_rule', context, use_cache=False)

        self.assertTrue(result.matched)

    def test_evaluate_nonexistent_rule(self):
        with patch('eval_engine.configurable_rule_engine.RuleConfig') as MockRuleConfig:
            MockRuleConfig.DoesNotExist = Exception
            MockRuleConfig.objects.get.side_effect = MockRuleConfig.DoesNotExist

            result = self.engine.evaluate('nonexistent', {}, use_cache=False)

            self.assertTrue(result.fallback)
            self.assertTrue(result.action['should_push'])
            self.assertIn('rule_not_found', result.action['reason'])

    def test_evaluate_security_error(self):
        with patch('eval_engine.configurable_rule_engine.RuleConfig') as MockRuleConfig:
            mock_rule = Mock()
            mock_rule.rule_id = 'bad_rule'
            mock_rule.is_active = True
            mock_rule.rule_content = {
                'conditions': {
                    'format': 'simpleeval',
                    'expression': "__import__('os').system('ls')"
                },
                'actions': {'on_match': {}, 'on_mismatch': {}},
                'context': {},
                'metadata': {}
            }
            MockRuleConfig.objects.get.return_value = mock_rule

            result = self.engine.evaluate('bad_rule', {}, use_cache=False)

            self.assertTrue(result.fallback)
            self.assertIn('security', result.action['reason'])

    def test_validate_expression_syntax(self):
        engine = ConfigurableRuleEngine()

        result = engine.validate_expression_syntax("severity == 'critical'")
        self.assertTrue(result['valid'])

        result = engine.validate_expression_syntax("__import__('os')")
        self.assertFalse(result['valid'])

    def test_rule_merge(self):
        base = {
            'rule_id': 'base_rule',
            'conditions': {'format': 'simpleeval', 'expression': "severity == 'critical'"},
            'actions': {
                'on_match': {'should_push': True, 'channel': 'im_normal'},
                'on_mismatch': {'should_push': False}
            }
        }
        override = {
            'rule_id': 'base_rule@ecommerce',
            'conditions': {'format': 'simpleeval', 'expression': "severity == 'critical' and business_priority == 'P0'"},
            'actions': {
                'on_match': {'should_push': True, 'channel': 'im_urgent'}
            }
        }

        merged = self.engine._merge_rules(base, override)

        self.assertEqual(merged['conditions']['expression'], "severity == 'critical' and business_priority == 'P0'")
        self.assertEqual(merged['actions']['on_match']['channel'], 'im_urgent')
        self.assertTrue(merged['merged'])


class TestRuleTestFramework(TestCase):

    def setUp(self):
        self.engine = ConfigurableRuleEngine()
        cache.clear()

    @patch('eval_engine.configurable_rule_engine.RuleConfig')
    def test_test_rule_single(self, MockRuleConfig):
        mock_rule = Mock()
        mock_rule.rule_id = 'test_rule'
        mock_rule.is_active = True
        mock_rule.rule_content = {
            'conditions': {
                'format': 'simpleeval',
                'expression': "severity == 'critical'"
            },
            'actions': {
                'on_match': {'should_push': True},
                'on_mismatch': {'should_push': False}
            },
            'context': {},
            'metadata': {}
        }
        MockRuleConfig.objects.get.return_value = mock_rule

        result = self.engine.test_rule('test_rule', {'severity': 'critical'})

        self.assertTrue(result['success'])
        self.assertTrue(result['matched'])
        self.assertTrue(result['action']['should_push'])

    @patch('eval_engine.configurable_rule_engine.RuleConfig')
    def test_run_test_suite(self, MockRuleConfig):
        mock_rule = Mock()
        mock_rule.rule_id = 'test_rule'
        mock_rule.is_active = True
        mock_rule.rule_content = {
            'conditions': {
                'format': 'simpleeval',
                'expression': "severity == 'critical' and alert_count_1h > 10"
            },
            'actions': {
                'on_match': {'should_push': True, 'channel': 'im_urgent'},
                'on_mismatch': {'should_push': False}
            },
            'context': {},
            'metadata': {}
        }
        MockRuleConfig.objects.get.return_value = mock_rule

        test_cases = [
            {
                'name': 'critical_high_freq',
                'context': {'severity': 'critical', 'alert_count_1h': 15},
                'expected_matched': True,
                'expected_action': {'should_push': True, 'channel': 'im_urgent'}
            },
            {
                'name': 'warning_low_freq',
                'context': {'severity': 'warning', 'alert_count_1h': 5},
                'expected_matched': False,
                'expected_action': {'should_push': False}
            }
        ]

        result = self.engine.run_test_suite('test_rule', test_cases)

        self.assertEqual(result['total'], 2)
        self.assertEqual(result['passed'], 2)
        self.assertEqual(result['failed'], 0)
        self.assertEqual(result['pass_rate'], 1.0)


class TestRuleExecutionMonitor(TestCase):

    def test_get_engine_health(self):
        health = RuleExecutionMonitor.get_engine_health()

        self.assertIn('status', health)
        self.assertIn('checked_at', health)
        self.assertIn('function_registry_count', health)

        self.assertEqual(health['status'], 'healthy')

    def test_engine_health_function_count(self):
        health = RuleExecutionMonitor.get_engine_health()
        self.assertGreater(health['function_registry_count'], 0)


class TestComplexExpressions(TestCase):

    def setUp(self):
        self.engine = ConfigurableRuleEngine()

    @patch('eval_engine.configurable_rule_engine.RuleConfig')
    def test_complex_boolean_logic(self, MockRuleConfig):
        mock_rule = Mock()
        mock_rule.rule_id = 'complex_rule'
        mock_rule.is_active = True
        mock_rule.rule_content = {
            'conditions': {
                'format': 'simpleeval',
                'expression': "(severity == 'critical' and business_priority in ['P0', 'P1']) or (alert_count_1h >= 20 and useful_rate > 0.8)"
            },
            'actions': {
                'on_match': {'should_push': True},
                'on_mismatch': {'should_push': False}
            },
            'context': {},
            'metadata': {}
        }
        MockRuleConfig.objects.get.return_value = mock_rule

        result = self.engine.evaluate('complex_rule', {
            'severity': 'critical',
            'business_priority': 'P0',
            'alert_count_1h': 5,
            'useful_rate': 0.5
        }, use_cache=False)
        self.assertTrue(result.matched)

        result = self.engine.evaluate('complex_rule', {
            'severity': 'warning',
            'business_priority': 'P3',
            'alert_count_1h': 25,
            'useful_rate': 0.9
        }, use_cache=False)
        self.assertTrue(result.matched)

        result = self.engine.evaluate('complex_rule', {
            'severity': 'warning',
            'business_priority': 'P3',
            'alert_count_1h': 5,
            'useful_rate': 0.5
        }, use_cache=False)
        self.assertFalse(result.matched)

    @patch('eval_engine.configurable_rule_engine.RuleConfig')
    def test_math_expressions(self, MockRuleConfig):
        mock_rule = Mock()
        mock_rule.rule_id = 'math_rule'
        mock_rule.is_active = True
        mock_rule.rule_content = {
            'conditions': {
                'format': 'simpleeval',
                'expression': "(alert_count_1h * 0.5 + alert_count_1d * 0.3) / useful_rate > 10"
            },
            'actions': {
                'on_match': {'should_push': True},
                'on_mismatch': {'should_push': False}
            },
            'context': {},
            'metadata': {}
        }
        MockRuleConfig.objects.get.return_value = mock_rule

        result = self.engine.evaluate('math_rule', {
            'alert_count_1h': 20,
            'alert_count_1d': 100,
            'useful_rate': 0.8
        }, use_cache=False)

        self.assertTrue(result.matched)

    @patch('eval_engine.configurable_rule_engine.RuleConfig')
    def test_builtin_functions_in_expression(self, MockRuleConfig):
        mock_rule = Mock()
        mock_rule.rule_id = 'func_rule'
        mock_rule.is_active = True
        mock_rule.rule_content = {
            'conditions': {
                'format': 'simpleeval',
                'expression': "max(alert_count_1h, alert_count_1d) > 50"
            },
            'actions': {
                'on_match': {'should_push': True},
                'on_mismatch': {'should_push': False}
            },
            'context': {},
            'metadata': {}
        }
        MockRuleConfig.objects.get.return_value = mock_rule

        result = self.engine.evaluate('func_rule', {
            'alert_count_1h': 10,
            'alert_count_1d': 100
        }, use_cache=False)

        self.assertTrue(result.matched)


class TestErrorHandling(TestCase):

    def setUp(self):
        self.engine = ConfigurableRuleEngine()

    def test_timeout_handling(self):
        with patch('eval_engine.configurable_rule_engine.RuleConfig') as MockRuleConfig:
            MockRuleConfig.DoesNotExist = Exception
            MockRuleConfig.objects.get.side_effect = MockRuleConfig.DoesNotExist

            result = self.engine.evaluate('missing_rule', {})

            self.assertTrue(result.fallback)
            self.assertTrue(result.action['should_push'])
            self.assertIsNotNone(result.error)

    def test_invalid_expression_handling(self):
        with patch('eval_engine.configurable_rule_engine.RuleConfig') as MockRuleConfig:
            mock_rule = Mock()
            mock_rule.rule_id = 'bad_expr'
            mock_rule.is_active = True
            mock_rule.rule_content = {
                'conditions': {
                    'format': 'simpleeval',
                    'expression': "this is not valid python !!!"
                },
                'actions': {'on_match': {}, 'on_mismatch': {}},
                'context': {},
                'metadata': {}
            }
            MockRuleConfig.objects.get.return_value = mock_rule

            result = self.engine.evaluate('bad_expr', {}, use_cache=False)

            self.assertTrue(result.fallback)
            self.assertIn(result.action['reason'], [
                'rule_fallback_security_error',
                'rule_fallback_execution_error',
            ])