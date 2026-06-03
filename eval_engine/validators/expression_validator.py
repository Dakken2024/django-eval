"""
Expression validator for rule security.
Extracted from configurable_rule_engine.py for better modularity.
"""
import re
from typing import Tuple, Dict, Any, Optional

from django.conf import settings

# Import settings safely
try:
    from eval_engine.settings import EvalEngineSettings
except ImportError:
    EvalEngineSettings = None


# Default forbidden patterns for expression security
DEFAULT_FORBIDDEN_PATTERNS = [
    r'__\w+__',
    r'import\s+',
    r'from\s+\S+\s+import',
    r'eval\s*\(',
    r'exec\s*\(',
    r'compile\s*\(',
    r'open\s*\(',
    r'file\s*\(',
    r'subprocess\.',
    r'os\.',
    r'sys\.',
    r'posix\.',
    r'nt\.',
    r' shutil\.',
    r'urllib',
    r'requests\.',
    r'socket\.',
    r'\bdel\b',
    r'\bglobals\s*\(',
    r'\blocals\s*\(',
    r'\bvars\s*\(',
    r'\bgetattr\s*\(',
    r'\bsetattr\s*\(',
    r'\bhasattr\s*\(',
    r'\bclass\b',
    r'\blambda\b',
    r'\byield\b',
]

# Allowed built-in functions
ALLOWED_FUNCTIONS = {
    'len': len,
    'max': max,
    'min': min,
    'sum': sum,
    'abs': abs,
    'round': round,
    'int': int,
    'float': float,
    'str': str,
    'bool': bool,
    'list': list,
    'dict': dict,
    'set': set,
    'tuple': tuple,
    'any': any,
    'all': all,
    'sorted': sorted,
    'reversed': reversed,
    'enumerate': enumerate,
    'zip': zip,
    'map': map,
    'filter': filter,
    'range': range,
}


class ExpressionValidator:
    """Validates and sanitizes expressions for safe evaluation."""
    
    @staticmethod
    def validate(expression: str) -> Tuple[bool, Optional[str]]:
        """
        Validate an expression for security and syntax.
        
        Args:
            expression: The expression string to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not expression or not isinstance(expression, str):
            return False, 'Expression must be a non-empty string'

        # Get patterns from settings or use defaults
        if EvalEngineSettings and hasattr(EvalEngineSettings, 'get'):
            patterns = EvalEngineSettings.get('FORBIDDEN_PATTERNS') or DEFAULT_FORBIDDEN_PATTERNS
            max_length = EvalEngineSettings.expression_max_length()
        else:
            patterns = DEFAULT_FORBIDDEN_PATTERNS
            max_length = getattr(settings, 'EVAL_EXPRESSION_MAX_LENGTH', 10000)

        # Check for forbidden patterns
        for pattern in patterns:
            if re.search(pattern, expression, re.IGNORECASE):
                return False, f'Forbidden pattern detected: {pattern}'

        # Check length
        if len(expression) > max_length:
            return False, f'Expression exceeds max length ({max_length})'

        # Syntax check
        try:
            compile(expression, '<string>', 'eval')
        except SyntaxError as e:
            return False, f'Syntax error: {e}'

        return True, None

    @staticmethod
    def sanitize_context(context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sanitize context by redacting sensitive fields.
        
        Args:
            context: The context dictionary
            
        Returns:
            Sanitized context dictionary
        """
        sanitized = {}
        forbidden_keys = {'password', 'secret', 'token', 'api_key', 'auth'}
        for key, value in context.items():
            if any(fk in key.lower() for fk in forbidden_keys):
                sanitized[key] = '***REDACTED***'
            else:
                sanitized[key] = value
        return sanitized

    @staticmethod
    def get_allowed_functions() -> Dict[str, callable]:
        """Get the dictionary of allowed built-in functions."""
        return ALLOWED_FUNCTIONS.copy()
