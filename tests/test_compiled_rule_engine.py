import pytest
from django.test import TestCase

from eval_engine.compiled_rule_engine import (
    RuleCompiler, CompiledDecisionTable, CompiledDecisionRow,
    CompiledChecker, RuleRegistry,
)


def _make_compiled_table(rule_id='test_rule', rule_name='Test Rule',
                         priority=1, rule_type='push_decision',
                         rows=None):
    if rows is None:
        checker = CompiledChecker('level', lambda ctx: ctx.get('level') == 'critical')
        rows = [
            CompiledDecisionRow('r0', [checker], {'should_push': False, 'action': 'suppress'}),
            CompiledDecisionRow('r_default', [], {'should_push': True, 'action': 'send'}, is_passthrough=True),
        ]
    return CompiledDecisionTable(rule_id, rule_name, priority, rows, rule_type)


class TestRuleCompiler(TestCase):

    def test_compiler_produces_consistent_results(self):
        table = {
            "inputs": [
                {"name": "level", "field": "level", "type": "string"},
                {"name": "predicted_weight", "field": "predicted_weight", "type": "number"},
                {"name": "bk_app_code", "field": "bk_app_code", "type": "string"},
            ],
            "rules": [
                {"id": "r0", "when": {"level": "critical", "predicted_weight": ">0.7"},
                 "then": {"should_push": True, "action": "send"}},
                {"id": "r1", "when": {"bk_app_code": ["order-api", "payment-api"], "level": "warning"},
                 "then": {"should_push": True, "action": "send"}},
                {"id": "r_default", "when": {},
                 "then": {"should_push": False, "action": "suppress"}},
            ]
        }
        compiled = RuleCompiler.compile_table('integration_test', 'Integration Test', 1, table, 'push_decision')

        ctx_critical = {'level': 'critical', 'predicted_weight': 0.85, 'bk_app_code': 'other'}
        result = compiled.evaluate(ctx_critical)
        self.assertEqual(result, {'should_push': True, 'action': 'send'})

        ctx_fallback = {'level': 'info', 'predicted_weight': 0.1, 'bk_app_code': 'other'}
        result = compiled.evaluate(ctx_fallback)
        self.assertEqual(result, {'should_push': False, 'action': 'suppress'})

    def test_compiler_or_condition(self):
        table = {
            "rules": [
                {"id": "r0", "when": {"or": [{"level": "fatal"}, {"level": "critical"}]},
                 "then": {"action": "urgent"}},
                {"id": "r_default", "when": {}, "then": {"action": "normal"}},
            ]
        }
        compiled = RuleCompiler.compile_table('or_test', 'OR Test', 1, table, 'push_decision')

        self.assertEqual(compiled.evaluate({'level': 'fatal'}), {'action': 'urgent'})
        self.assertEqual(compiled.evaluate({'level': 'critical'}), {'action': 'urgent'})
        self.assertEqual(compiled.evaluate({'level': 'warning'}), {'action': 'normal'})

    def test_compiler_range_condition(self):
        table = {
            "rules": [
                {"id": "r0", "when": {"predicted_weight": [0.5, 0.9]},
                 "then": {"action": "delay"}},
                {"id": "r_default", "when": {}, "then": {"action": "send"}},
            ]
        }
        compiled = RuleCompiler.compile_table('range_test', 'Range Test', 1, table, 'push_decision')

        self.assertEqual(compiled.evaluate({'predicted_weight': 0.7}), {'action': 'delay'})
        self.assertEqual(compiled.evaluate({'predicted_weight': 0.3}), {'action': 'send'})
        self.assertEqual(compiled.evaluate({'predicted_weight': 0.5}), {'action': 'delay'})
        self.assertEqual(compiled.evaluate({'predicted_weight': 0.9}), {'action': 'delay'})

    def test_compiler_comparison_operators(self):
        table = {
            "rules": [
                {"id": "r0", "when": {"val": ">=10"}, "then": {"result": "high"}},
                {"id": "r1", "when": {"val": "<=3"}, "then": {"result": "low"}},
                {"id": "r2", "when": {"val": "!=5"}, "then": {"result": "not5"}},
                {"id": "r_default", "when": {}, "then": {"result": "mid"}},
            ]
        }
        compiled = RuleCompiler.compile_table('ops_test', 'Ops Test', 1, table, 'push_decision')

        self.assertEqual(compiled.evaluate({'val': 15}), {'result': 'high'})
        self.assertEqual(compiled.evaluate({'val': 2}), {'result': 'low'})
        self.assertEqual(compiled.evaluate({'val': 6}), {'result': 'not5'})
        self.assertEqual(compiled.evaluate({'val': 5}), {'result': 'mid'})

    def test_compiler_missing_field_returns_fallback(self):
        table = {
            "rules": [
                {"id": "r0", "when": {"level": "critical"}, "then": {"should_push": True, "action": "send"}},
                {"id": "r_default", "when": {}, "then": {"should_push": False, "action": "suppress"}},
            ]
        }
        compiled = RuleCompiler.compile_table('missing_test', 'Missing Test', 1, table, 'push_decision')

        result = compiled.evaluate({})
        self.assertEqual(result, {'should_push': False, 'action': 'suppress'})


class TestRuleRegistry(TestCase):

    def setUp(self):
        self.registry = RuleRegistry()
        self.registry._tables.clear()
        self.registry._versions.clear()
        self.registry._loaded = False

    def tearDown(self):
        self.registry._tables.clear()
        self.registry._versions.clear()
        self.registry._loaded = False

    def test_register_and_get(self):
        compiled = _make_compiled_table(rule_id='test_reg')
        self.registry.register('test_reg', compiled, version=1)

        result = self.registry.get('test_reg')
        self.assertIsNotNone(result)
        self.assertEqual(result.rule_id, 'test_reg')

    def test_get_nonexistent_returns_none(self):
        self.assertIsNone(self.registry.get('nonexistent'))

    def test_get_all_active_filters_by_type(self):
        push_table = _make_compiled_table(rule_id='push_1', rule_type='push_decision')
        feedback_table = _make_compiled_table(rule_id='fb_1', rule_type='feedback_threshold')
        self.registry.register('push_1', push_table, version=1)
        self.registry.register('fb_1', feedback_table, version=1)

        push_rules = self.registry.get_all_active(rule_type='push_decision')
        self.assertEqual(len(push_rules), 1)
        self.assertEqual(push_rules[0].rule_id, 'push_1')

    def test_get_all_active_sorted_by_priority(self):
        low = _make_compiled_table(rule_id='low', priority=10)
        high = _make_compiled_table(rule_id='high', priority=1)
        mid = _make_compiled_table(rule_id='mid', priority=5)
        self.registry.register('low', low, version=1)
        self.registry.register('high', high, version=1)
        self.registry.register('mid', mid, version=1)

        all_rules = self.registry.get_all_active()
        self.assertEqual([r.rule_id for r in all_rules], ['high', 'mid', 'low'])

    def test_invalidate(self):
        compiled = _make_compiled_table(rule_id='to_remove')
        self.registry.register('to_remove', compiled, version=1)
        self.assertIsNotNone(self.registry.get('to_remove'))

        self.registry.invalidate('to_remove')
        self.assertIsNone(self.registry.get('to_remove'))

    def test_is_loaded_flag(self):
        self.assertFalse(self.registry.is_loaded)
        self.registry._loaded = True
        self.assertTrue(self.registry.is_loaded)

    def test_version_map(self):
        compiled = _make_compiled_table(rule_id='v_test')
        self.registry.register('v_test', compiled, version=3)
        vmap = self.registry.version_map
        self.assertEqual(vmap.get('v_test'), 3)