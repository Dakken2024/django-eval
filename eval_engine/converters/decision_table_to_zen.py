"""
Decision Table to Zen Engine Converter

Converts internal decision table format to Zen Engine compatible JSON/YAML.
"""

from typing import Any, Dict, List, Optional
import json
import logging

logger = logging.getLogger(__name__)


class DecisionTableToZen:
    """
    Converts decision tables to Zen Engine format.
    
    Supports:
    - Simple condition-action rules
    - Priority-based execution
    - Hit policies (FIRST, ALL, UNIQUE)
    """
    
    def __init__(self):
        self.warnings: List[str] = []
        
    def convert(
        self,
        decision_table: Dict[str, Any],
        output_format: str = "json"
    ) -> str:
        """
        Convert decision table to Zen Engine format.
        
        Args:
            decision_table: Internal decision table definition
            output_format: 'json' or 'yaml'
            
        Returns:
            Zen Engine rule definition string
        """
        self.warnings = []
        
        zen_rule = {
            "name": decision_table.get("name", "Unnamed Rule"),
            "description": decision_table.get("description", ""),
            "version": decision_table.get("version", "1.0"),
            "hitPolicy": self._map_hit_policy(decision_table.get("hit_policy", "FIRST")),
            "rules": self._convert_rules(decision_table.get("rules", []))
        }
        
        if output_format.lower() == "yaml":
            try:
                import yaml
                return yaml.dump(zen_rule, default_flow_style=False, allow_unicode=True)
            except ImportError:
                logger.warning("PyYAML not installed, falling back to JSON")
                return json.dumps(zen_rule, indent=2, ensure_ascii=False)
        else:
            return json.dumps(zen_rule, indent=2, ensure_ascii=False)
    
    def _map_hit_policy(self, hit_policy: str) -> str:
        """Map internal hit policy to Zen Engine format"""
        policy_map = {
            "FIRST": "FIRST",
            "ALL": "ALL",
            "UNIQUE": "UNIQUE",
            "PRIORITY": "PRIORITY"
        }
        return policy_map.get(hit_policy.upper(), "FIRST")
    
    def _convert_rules(self, rules: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert rule rows to Zen Engine format"""
        zen_rules = []
        
        for idx, rule in enumerate(rules):
            zen_rule = {
                "id": rule.get("id", f"rule_{idx}"),
                "description": rule.get("description", ""),
                "condition": self._build_condition(rule.get("conditions", {})),
                "action": self._build_action(rule.get("actions", {})),
                "priority": rule.get("priority", idx)
            }
            
            # Check for short-circuit dependencies
            if self._has_short_circuit_dependency(rule.get("conditions", {})):
                self.warnings.append(
                    f"Rule {zen_rule['id']}: Contains logic that may depend on "
                    "short-circuit evaluation. Zen Engine evaluates all conditions."
                )
            
            zen_rules.append(zen_rule)
            
        return zen_rules
    
    def _build_condition(self, conditions: Dict[str, Any]) -> Dict[str, Any]:
        """Build Zen Engine condition object"""
        zen_conditions = []
        
        for field, value in conditions.items():
            if isinstance(value, dict):
                # Complex condition with operator
                operator = value.get("op", "==")
                zen_op = self._map_operator(operator)
                zen_conditions.append({
                    "field": field,
                    "operator": zen_op,
                    "value": value.get("value")
                })
            else:
                # Simple equality
                zen_conditions.append({
                    "field": field,
                    "operator": "==",
                    "value": value
                })
                
        return {
            "logic": "AND",
            "conditions": zen_conditions
        }
    
    def _build_action(self, actions: Dict[str, Any]) -> Dict[str, Any]:
        """Build Zen Engine action object"""
        zen_actions = []
        
        for field, value in actions.items():
            zen_actions.append({
                "type": "ASSIGN",
                "field": field,
                "value": value
            })
            
        return {
            "actions": zen_actions
        }
    
    def _map_operator(self, op: str) -> str:
        """Map Python operators to Zen Engine operators"""
        op_map = {
            "==": "==",
            "!=": "!=",
            ">": ">",
            ">=": ">=",
            "<": "<",
            "<=": "<=",
            "in": "IN",
            "contains": "CONTAINS",
            "startswith": "STARTS_WITH",
            "endswith": "ENDS_WITH",
            "regex": "MATCHES"
        }
        return op_map.get(op, "==")
    
    def _has_short_circuit_dependency(self, conditions: Dict[str, Any]) -> bool:
        """
        Detect if conditions rely on short-circuit evaluation.
        
        This is a heuristic check for patterns like:
        - user.is_authenticated and user.has_permission()
        - amount > 0 and calculate_tax(amount)
        """
        # Check for function calls in conditions
        condition_str = json.dumps(conditions)
        function_patterns = ["(", ")", "lambda"]
        
        return any(pattern in condition_str for pattern in function_patterns)
    
    def convert_with_validation(
        self,
        decision_table: Dict[str, Any],
        output_format: str = "json"
    ) -> Dict[str, Any]:
        """
        Convert and validate the result.
        
        Returns:
            Dictionary with converted rule, warnings, and validation status
        """
        converted = self.convert(decision_table, output_format)
        
        result = {
            "success": True,
            "converted_rule": converted,
            "warnings": self.warnings.copy(),
            "errors": []
        }
        
        # Basic validation
        try:
            parsed = json.loads(converted) if output_format == "json" else converted
            if not parsed.get("rules"):
                result["warnings"].append("Converted rule has no rules defined")
        except Exception as e:
            result["success"] = False
            result["errors"].append(f"Conversion validation failed: {str(e)}")
            
        return result
