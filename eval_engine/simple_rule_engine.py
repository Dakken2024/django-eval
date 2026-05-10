import logging
from typing import Optional, Dict, Any
from simpleeval import simple_eval

logger = logging.getLogger(__name__)


class SimpleRuleEngine:
    """Lightweight rule engine for evaluating decision table structures (supports dict and list formats)."""

    @staticmethod
    def evaluate_decision_table(table: dict, context: dict) -> dict:
        rules = table.get("rules", [])
        inputs = table.get("inputs", [])
        outputs = table.get("outputs", [])
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            when = rule.get("when")
            if when is None:
                continue
            if SimpleRuleEngine._match_conditions(when, context, inputs):
                then = rule.get("then", {})
                if isinstance(then, list):
                    result = {}
                    for idx, val in enumerate(then):
                        if idx < len(outputs):
                            out_name = outputs[idx].get('field') or outputs[idx].get('name')
                            if out_name:
                                result[out_name] = val
                    return result if result else {"action": "suppress", "fallback": True}
                return then if then else {"action": "suppress", "fallback": True}
        return {"action": "suppress", "fallback": True}

    @staticmethod
    def _match_conditions(conditions, context: dict, inputs: list = None) -> bool:
        if not conditions:
            return True

        if isinstance(conditions, dict):
            if "and" in conditions:
                return all(SimpleRuleEngine._match_conditions(sub, context, inputs) for sub in conditions["and"])
            if "or" in conditions:
                return any(SimpleRuleEngine._match_conditions(sub, context, inputs) for sub in conditions["or"])

        if isinstance(conditions, list):
            if not inputs:
                logger.warning("List condition without inputs mapping")
                return False
            for idx, expr in enumerate(conditions):
                if idx >= len(inputs):
                    break
                if expr is None:
                    continue
                field_name = inputs[idx].get('field') or inputs[idx].get('name')
                if not field_name:
                    continue
                actual_value = context.get(field_name)
                if actual_value is None:
                    return False
                if not SimpleRuleEngine._evaluate_expression(str(expr), actual_value):
                    return False
            return True

        if isinstance(conditions, dict):
            for field, expr in conditions.items():
                actual_value = context.get(field)
                if actual_value is None:
                    return False
                if isinstance(expr, list):
                    if len(expr) == 2 and all(isinstance(v, (int, float)) for v in expr):
                        min_val, max_val = expr
                        if not (min_val <= actual_value <= max_val):
                            return False
                    elif actual_value not in expr:
                        return False
                elif not SimpleRuleEngine._evaluate_expression(str(expr), actual_value):
                    return False
            return True

        logger.warning(f"Unsupported condition type: {type(conditions)}")
        return False

    @staticmethod
    def _evaluate_expression(expr: str, actual_value) -> bool:
        expr_str = expr.strip()
        if not any(op in expr_str for op in ['>', '<', '=', '!', 'and', 'or', '+', '-', '*', '/', '(', ')']):
            return actual_value == expr_str
        try:
            if expr_str.startswith('>='):
                right = expr_str[2:].strip()
                if right.startswith("'") or right.startswith('"'):
                    return actual_value >= right[1:-1]
                return actual_value >= float(right)
            elif expr_str.startswith('<='):
                right = expr_str[2:].strip()
                if right.startswith("'") or right.startswith('"'):
                    return actual_value <= right[1:-1]
                return actual_value <= float(right)
            elif expr_str.startswith('>'):
                right = expr_str[1:].strip()
                if right.startswith("'") or right.startswith('"'):
                    return actual_value > right[1:-1]
                return actual_value > float(right)
            elif expr_str.startswith('<'):
                right = expr_str[1:].strip()
                if right.startswith("'") or right.startswith('"'):
                    return actual_value < right[1:-1]
                return actual_value < float(right)
            elif expr_str.startswith('!='):
                right = expr_str[2:].strip()
                if right.startswith("'") or right.startswith('"'):
                    return actual_value != right[1:-1]
                try:
                    return actual_value != float(right)
                except ValueError:
                    return actual_value != right
            elif expr_str.startswith('=='):
                right = expr_str[2:].strip()
                if right.startswith("'") or right.startswith('"'):
                    return actual_value == right[1:-1]
                try:
                    return actual_value == float(right)
                except ValueError:
                    return actual_value == right
            else:
                return simple_eval(expr_str, names={"actual": actual_value})
        except Exception as e:
            logger.error(f"Expression error: {expr_str} | {e}")
            return False

    @staticmethod
    def extract_decision_table_from_graph(jdm: dict) -> dict:
        nodes = jdm.get("nodes", [])
        for node in nodes:
            if node.get("type") == "decisionTableNode" and "content" in node:
                return node["content"]
        if jdm.get("kind") == "DecisionTable":
            return jdm
        return {}