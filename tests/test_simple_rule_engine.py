from django.test import TestCase

from eval_engine.simple_rule_engine import SimpleRuleEngine
from eval_engine.models import RuleConfig


class TestExpressionEvaluation(TestCase):
    def test_evaluate_equal(self):
        self.assertTrue(SimpleRuleEngine._evaluate_expression("P0", "P0"))
        self.assertFalse(SimpleRuleEngine._evaluate_expression("P0", "P1"))

    def test_evaluate_greater_than(self):
        self.assertTrue(SimpleRuleEngine._evaluate_expression(">0.6", 0.8))
        self.assertFalse(SimpleRuleEngine._evaluate_expression(">0.6", 0.5))

    def test_evaluate_less_than(self):
        self.assertTrue(SimpleRuleEngine._evaluate_expression("<0.3", 0.2))
        self.assertFalse(SimpleRuleEngine._evaluate_expression("<0.3", 0.4))

    def test_evaluate_greater_equal(self):
        self.assertTrue(SimpleRuleEngine._evaluate_expression(">=5", 5))
        self.assertTrue(SimpleRuleEngine._evaluate_expression(">=5", 6))
        self.assertFalse(SimpleRuleEngine._evaluate_expression(">=5", 4))

    def test_evaluate_less_equal(self):
        self.assertTrue(SimpleRuleEngine._evaluate_expression("<=5", 5))
        self.assertTrue(SimpleRuleEngine._evaluate_expression("<=5", 4))
        self.assertFalse(SimpleRuleEngine._evaluate_expression("<=5", 6))

    def test_evaluate_not_equal(self):
        self.assertTrue(SimpleRuleEngine._evaluate_expression("!=P0", "P1"))
        self.assertFalse(SimpleRuleEngine._evaluate_expression("!=P0", "P0"))

    def test_evaluate_equal_operator(self):
        self.assertTrue(SimpleRuleEngine._evaluate_expression("==0.5", 0.5))
        self.assertFalse(SimpleRuleEngine._evaluate_expression("==0.5", 0.6))

    def test_evaluate_string_expression(self):
        self.assertTrue(SimpleRuleEngine._evaluate_expression("critical", "critical"))
        self.assertFalse(SimpleRuleEngine._evaluate_expression("critical", "warning"))


class TestConditionMatching(TestCase):
    def test_match_simple_dict_condition(self):
        conditions = {"severity": "critical"}
        context = {"severity": "critical"}
        self.assertTrue(SimpleRuleEngine._match_conditions(conditions, context))

    def test_match_multiple_conditions(self):
        conditions = {"severity": "critical", "business_id": "P0"}
        context = {"severity": "critical", "business_id": "P0"}
        self.assertTrue(SimpleRuleEngine._match_conditions(conditions, context))

    def test_match_fails_on_one_condition(self):
        conditions = {"severity": "critical", "business_id": "P0"}
        context = {"severity": "critical", "business_id": "P1"}
        self.assertFalse(SimpleRuleEngine._match_conditions(conditions, context))

    def test_match_empty_conditions(self):
        conditions = {}
        context = {"severity": "critical"}
        self.assertTrue(SimpleRuleEngine._match_conditions(conditions, context))

    def test_match_and_logic(self):
        conditions = {"and": [
            {"severity": "critical"},
            {"business_id": "P0"}
        ]}
        context = {"severity": "critical", "business_id": "P0"}
        self.assertTrue(SimpleRuleEngine._match_conditions(conditions, context))

    def test_match_or_logic(self):
        conditions = {"or": [
            {"severity": "critical"},
            {"severity": "warning"}
        ]}
        context = {"severity": "warning"}
        self.assertTrue(SimpleRuleEngine._match_conditions(conditions, context))

    def test_match_with_expression(self):
        conditions = {"weight": ">0.6"}
        context = {"weight": 0.8}
        self.assertTrue(SimpleRuleEngine._match_conditions(conditions, context))

    def test_match_missing_field(self):
        conditions = {"severity": "critical"}
        context = {"weight": 0.8}
        self.assertFalse(SimpleRuleEngine._match_conditions(conditions, context))


class TestDecisionTableEvaluation(TestCase):
    def test_evaluate_push_decision_immediate_send(self):
        table = {
            "name": "test_push",
            "kind": "DecisionTable",
            "hit_policy": "first",
            "inputs": [
                {"name": "alert_count_1h", "type": "number"},
                {"name": "alert_severity", "type": "string"},
                {"name": "predicted_weight", "type": "number"},
                {"name": "business_id", "type": "string"}
            ],
            "outputs": [
                {"name": "action", "type": "string"},
                {"name": "delay_seconds", "type": "number"},
                {"name": "channel", "type": "string"}
            ],
            "rules": [
                {
                    "id": "rule_0",
                    "description": "P0 business + high weight -> immediate push",
                    "when": {"business_id": "P0", "predicted_weight": ">0.6"},
                    "then": {"action": "send", "delay_seconds": 0, "channel": "im_urgent"}
                },
                {
                    "id": "rule_default",
                    "when": {},
                    "then": {"action": "send", "delay_seconds": 0, "channel": "im_normal"}
                }
            ]
        }

        context = {
            "business_id": "P0",
            "predicted_weight": 0.8,
            "alert_count_1h": 1,
            "alert_severity": "critical"
        }

        result = SimpleRuleEngine.evaluate_decision_table(table, context)
        self.assertEqual(result['action'], 'send')
        self.assertEqual(result['delay_seconds'], 0)
        self.assertEqual(result['channel'], 'im_urgent')

    def test_evaluate_push_decision_suppress(self):
        table = {
            "name": "test_push",
            "kind": "DecisionTable",
            "hit_policy": "first",
            "inputs": [
                {"name": "alert_count_1h", "type": "number"}
            ],
            "outputs": [
                {"name": "action", "type": "string"}
            ],
            "rules": [
                {
                    "id": "rule_suppress",
                    "when": {"alert_count_1h": ">5"},
                    "then": {"action": "suppress"}
                },
                {
                    "id": "rule_default",
                    "when": {},
                    "then": {"action": "send"}
                }
            ]
        }

        context = {"alert_count_1h": 10}
        result = SimpleRuleEngine.evaluate_decision_table(table, context)
        self.assertEqual(result['action'], 'suppress')

    def test_evaluate_no_match_returns_fallback(self):
        table = {
            "name": "test",
            "kind": "DecisionTable",
            "rules": [
                {"when": {"severity": "critical"}, "then": {"action": "send"}}
            ]
        }

        context = {"severity": "info"}
        result = SimpleRuleEngine.evaluate_decision_table(table, context)
        self.assertEqual(result['action'], 'suppress')
        self.assertTrue(result['fallback'])


class TestErrorHandling(TestCase):
    def test_evaluate_invalid_expression(self):
        result = SimpleRuleEngine._evaluate_expression("invalid+++expr", 0.5)
        self.assertFalse(result)

    def test_evaluate_type_mismatch(self):
        result = SimpleRuleEngine._evaluate_expression(">0.5", "string_value")
        self.assertFalse(result)

    def test_evaluate_none_context_value(self):
        conditions = {"severity": "critical"}
        context = {"severity": None}
        self.assertFalse(SimpleRuleEngine._match_conditions(conditions, context))

    def test_evaluate_empty_table(self):
        result = SimpleRuleEngine.evaluate_decision_table({}, {})
        self.assertEqual(result['action'], 'suppress')


class TestDecisionTableExtraction(TestCase):
    def test_extract_from_graph_structure(self):
        jdm = {
            "name": "test_rule",
            "nodes": [
                {"id": "input", "type": "inputNode"},
                {
                    "id": "decision",
                    "type": "decisionTableNode",
                    "content": {
                        "name": "test",
                        "kind": "DecisionTable",
                        "inputs": [{"name": "score", "type": "number"}],
                        "outputs": [{"name": "result", "type": "string"}],
                        "rules": [
                            {"when": {"score": ">0.5"}, "then": {"result": "pass"}}
                        ]
                    }
                },
                {"id": "output", "type": "outputNode"}
            ],
            "edges": []
        }

        table = SimpleRuleEngine.extract_decision_table_from_graph(jdm)
        self.assertEqual(table['kind'], 'DecisionTable')
        self.assertEqual(len(table['rules']), 1)

    def test_extract_direct_decision_table(self):
        jdm = {
            "name": "direct_table",
            "kind": "DecisionTable",
            "inputs": [{"name": "x", "type": "number"}],
            "outputs": [{"name": "y", "type": "string"}],
            "rules": [{"when": {}, "then": {"y": "default"}}]
        }

        table = SimpleRuleEngine.extract_decision_table_from_graph(jdm)
        self.assertEqual(table['kind'], 'DecisionTable')

    def test_extract_returns_empty_for_invalid(self):
        jdm = {"name": "no_decision_table"}
        table = SimpleRuleEngine.extract_decision_table_from_graph(jdm)
        self.assertEqual(table, {})