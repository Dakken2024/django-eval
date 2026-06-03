"""
Rule import/export utilities.
Supports JSON and YAML formats for rule configuration export and import.
"""
import json
from typing import Dict, List, Any, Optional
from datetime import datetime

from ..models import RuleConfig


class RuleExporter:
    """Export rules to JSON or YAML format."""
    
    @staticmethod
    def export_rule_to_dict(rule: RuleConfig) -> Dict[str, Any]:
        """
        Export a single rule to dictionary format.
        
        Args:
            rule: RuleConfig instance to export
            
        Returns:
            Dictionary representation of the rule
        """
        return {
            'rule_id': rule.rule_id,
            'rule_name': rule.rule_name,
            'rule_type': rule.rule_type,
            'engine_type': rule.engine_type,
            'rule_content': rule.rule_content,
            'version': rule.version,
            'is_active': rule.is_active,
            'priority': rule.priority,
            'business_id': rule.business_id,
            'business_group': rule.business_group,
            'category_key': rule.category_key,
            'threshold_value': rule.threshold_value,
            'scope': rule.scope,
            'user_id': rule.user_id,
            'description': rule.description,
            'created_by': rule.created_by,
            'created_at': rule.created_at.isoformat() if rule.created_at else None,
            'updated_at': rule.updated_at.isoformat() if rule.updated_at else None,
        }
    
    @staticmethod
    def export_rules_to_dict(rules: List[RuleConfig]) -> Dict[str, Any]:
        """
        Export multiple rules to dictionary format.
        
        Args:
            rules: List of RuleConfig instances to export
            
        Returns:
            Dictionary with metadata and rules list
        """
        return {
            'exported_at': datetime.now().isoformat(),
            'count': len(rules),
            'rules': [RuleExporter.export_rule_to_dict(rule) for rule in rules],
        }
    
    @staticmethod
    def export_rule_to_json(rule: RuleConfig, indent: int = 2) -> str:
        """
        Export a single rule to JSON string.
        
        Args:
            rule: RuleConfig instance to export
            indent: JSON indentation level
            
        Returns:
            JSON string representation
        """
        return json.dumps(
            RuleExporter.export_rule_to_dict(rule),
            indent=indent,
            ensure_ascii=False
        )
    
    @staticmethod
    def export_rules_to_json(rules: List[RuleConfig], indent: int = 2) -> str:
        """
        Export multiple rules to JSON string.
        
        Args:
            rules: List of RuleConfig instances to export
            indent: JSON indentation level
            
        Returns:
            JSON string representation
        """
        return json.dumps(
            RuleExporter.export_rules_to_dict(rules),
            indent=indent,
            ensure_ascii=False
        )
    
    @staticmethod
    def export_rule_to_yaml(rule: RuleConfig) -> str:
        """
        Export a single rule to YAML string.
        
        Args:
            rule: RuleConfig instance to export
            
        Returns:
            YAML string representation
        """
        try:
            import yaml
            return yaml.dump(
                RuleExporter.export_rule_to_dict(rule),
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False
            )
        except ImportError:
            raise ImportError("PyYAML is required for YAML export. Install with: pip install pyyaml")
    
    @staticmethod
    def export_rules_to_yaml(rules: List[RuleConfig]) -> str:
        """
        Export multiple rules to YAML string.
        
        Args:
            rules: List of RuleConfig instances to export
            
        Returns:
            YAML string representation
        """
        try:
            import yaml
            return yaml.dump(
                RuleExporter.export_rules_to_dict(rules),
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False
            )
        except ImportError:
            raise ImportError("PyYAML is required for YAML export. Install with: pip install pyyaml")
    
    @staticmethod
    def export_rules_to_file(
        rules: List[RuleConfig],
        filepath: str,
        format: str = 'json',
        indent: int = 2
    ):
        """
        Export rules to a file.
        
        Args:
            rules: List of RuleConfig instances to export
            filepath: Path to the output file
            format: Output format ('json' or 'yaml')
            indent: JSON indentation level (ignored for YAML)
        """
        if format.lower() == 'json':
            content = RuleExporter.export_rules_to_json(rules, indent=indent)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
        elif format.lower() == 'yaml':
            content = RuleExporter.export_rules_to_yaml(rules)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
        else:
            raise ValueError(f"Unsupported format: {format}. Use 'json' or 'yaml'.")


class RuleImporter:
    """Import rules from JSON or YAML format."""
    
    @staticmethod
    def validate_rule_dict(data: Dict[str, Any]) -> List[str]:
        """
        Validate a rule dictionary.
        
        Args:
            data: Dictionary containing rule data
            
        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []
        
        # Required fields
        required_fields = ['rule_id', 'rule_name', 'rule_type']
        for field in required_fields:
            if field not in data:
                errors.append(f"Missing required field: {field}")
        
        # Validate rule_type
        valid_rule_types = ['push_decision', 'feedback_threshold', 'time_window', 'custom']
        if 'rule_type' in data and data['rule_type'] not in valid_rule_types:
            errors.append(f"Invalid rule_type: {data['rule_type']}. Must be one of {valid_rule_types}")
        
        # Validate engine_type
        valid_engine_types = ['simpleeval']
        if 'engine_type' in data and data['engine_type'] not in valid_engine_types:
            errors.append(f"Invalid engine_type: {data['engine_type']}. Must be one of {valid_engine_types}")
        
        # Validate scope
        valid_scopes = ['global', 'business', 'business_group', 'category', 'user']
        if 'scope' in data and data['scope'] not in valid_scopes:
            errors.append(f"Invalid scope: {data['scope']}. Must be one of {valid_scopes}")
        
        return errors
    
    @staticmethod
    def import_rule_from_dict(
        data: Dict[str, Any],
        overwrite: bool = False
    ) -> RuleConfig:
        """
        Import a rule from dictionary.
        
        Args:
            data: Dictionary containing rule data
            overwrite: Whether to overwrite existing rule with same ID
            
        Returns:
            Created or updated RuleConfig instance
            
        Raises:
            ValueError: If validation fails
        """
        errors = RuleImporter.validate_rule_dict(data)
        if errors:
            raise ValueError(f"Validation failed: {'; '.join(errors)}")
        
        # Check for existing rule
        existing = RuleConfig.objects.filter(rule_id=data['rule_id']).first()
        if existing and not overwrite:
            raise ValueError(f"Rule with ID '{data['rule_id']}' already exists. Set overwrite=True to replace.")
        
        if existing and overwrite:
            # Update existing rule
            for key, value in data.items():
                if key in ['rule_id', 'created_at', 'updated_at']:
                    continue
                if hasattr(existing, key):
                    setattr(existing, key, value)
            existing.save()
            return existing
        
        # Create new rule
        rule_data = {
            'rule_id': data['rule_id'],
            'rule_name': data['rule_name'],
            'rule_type': data['rule_type'],
            'engine_type': data.get('engine_type', 'simpleeval'),
            'rule_content': data.get('rule_content'),
            'version': data.get('version', 1),
            'is_active': data.get('is_active', True),
            'priority': data.get('priority', 0),
            'business_id': data.get('business_id', ''),
            'business_group': data.get('business_group', ''),
            'category_key': data.get('category_key', ''),
            'threshold_value': data.get('threshold_value'),
            'scope': data.get('scope', 'global'),
            'user_id': data.get('user_id', ''),
            'description': data.get('description', ''),
            'created_by': data.get('created_by', ''),
        }
        
        return RuleConfig.objects.create(**rule_data)
    
    @staticmethod
    def import_rules_from_dict(
        data: Dict[str, Any],
        overwrite: bool = False
    ) -> Dict[str, Any]:
        """
        Import multiple rules from dictionary.
        
        Args:
            data: Dictionary with 'rules' list
            overwrite: Whether to overwrite existing rules
            
        Returns:
            Dictionary with import statistics
        """
        if 'rules' not in data:
            raise ValueError("Missing 'rules' key in import data")
        
        results = {
            'total': len(data['rules']),
            'success': 0,
            'failed': 0,
            'errors': [],
        }
        
        for i, rule_data in enumerate(data['rules']):
            try:
                RuleImporter.import_rule_from_dict(rule_data, overwrite=overwrite)
                results['success'] += 1
            except Exception as e:
                results['failed'] += 1
                results['errors'].append(f"Rule {i+1} ({rule_data.get('rule_id', 'unknown')}): {str(e)}")
        
        return results
    
    @staticmethod
    def import_rule_from_json(json_str: str, overwrite: bool = False) -> RuleConfig:
        """
        Import a rule from JSON string.
        
        Args:
            json_str: JSON string containing rule data
            overwrite: Whether to overwrite existing rule
            
        Returns:
            Created or updated RuleConfig instance
        """
        data = json.loads(json_str)
        return RuleImporter.import_rule_from_dict(data, overwrite=overwrite)
    
    @staticmethod
    def import_rules_from_json(json_str: str, overwrite: bool = False) -> Dict[str, Any]:
        """
        Import multiple rules from JSON string.
        
        Args:
            json_str: JSON string containing rules data
            overwrite: Whether to overwrite existing rules
            
        Returns:
            Dictionary with import statistics
        """
        data = json.loads(json_str)
        return RuleImporter.import_rules_from_dict(data, overwrite=overwrite)
    
    @staticmethod
    def import_rules_from_yaml(yaml_str: str, overwrite: bool = False) -> Dict[str, Any]:
        """
        Import multiple rules from YAML string.
        
        Args:
            yaml_str: YAML string containing rules data
            overwrite: Whether to overwrite existing rules
            
        Returns:
            Dictionary with import statistics
        """
        try:
            import yaml
            data = yaml.safe_load(yaml_str)
            return RuleImporter.import_rules_from_dict(data, overwrite=overwrite)
        except ImportError:
            raise ImportError("PyYAML is required for YAML import. Install with: pip install pyyaml")
    
    @staticmethod
    def import_rules_from_file(
        filepath: str,
        overwrite: bool = False
    ) -> Dict[str, Any]:
        """
        Import rules from a file.
        
        Args:
            filepath: Path to the input file
            overwrite: Whether to overwrite existing rules
            
        Returns:
            Dictionary with import statistics
        """
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Detect format by extension
        if filepath.endswith('.json'):
            return RuleImporter.import_rules_from_json(content, overwrite=overwrite)
        elif filepath.endswith('.yaml') or filepath.endswith('.yml'):
            return RuleImporter.import_rules_from_yaml(content, overwrite=overwrite)
        else:
            # Try JSON first, then YAML
            try:
                return RuleImporter.import_rules_from_json(content, overwrite=overwrite)
            except json.JSONDecodeError:
                try:
                    return RuleImporter.import_rules_from_yaml(content, overwrite=overwrite)
                except ImportError:
                    raise ValueError("Unable to detect file format. Use .json or .yaml extension.")
