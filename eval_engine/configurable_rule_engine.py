import json
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Callable, Tuple, Union
from functools import lru_cache

from django.db import transaction
from django.utils import timezone
from simpleeval import EvalWithCompoundTypes, InvalidExpression, NameNotDefined

from .models import RuleConfig, RuleVersionHistory
from .simple_rule_engine import SimpleRuleEngine
from .cache_keys import CacheKeys
from .cache import get_cache
from .settings import EvalEngineSettings

logger = logging.getLogger(__name__)


def safe_simple_eval(expression: str, names: dict = None, functions: dict = None):
    evaluator = EvalWithCompoundTypes(
        names=names or {},
        functions=functions or {},
    )
    return evaluator.eval(expression)


# ==================== Exceptions ====================

class RuleEngineError(Exception):
    pass


class RuleNotFoundError(RuleEngineError):
    pass


class RuleParseError(RuleEngineError):
    pass


class RuleExecutionError(RuleEngineError):
    pass


class RuleSecurityError(RuleEngineError):
    pass


class RuleValidationError(RuleEngineError):
    pass


# ==================== Security Config ====================

FORBIDDEN_PATTERNS = [
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


# ==================== Data Models ====================

@dataclass
class RuleEvaluationResult:
    rule_id: str
    matched: bool
    action: Dict[str, Any]
    context: Dict[str, Any]
    latency_ms: float
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    matched_condition: Optional[str] = None
    error: Optional[str] = None
    fallback: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            'trace_id': self.trace_id,
            'rule_id': self.rule_id,
            'matched': self.matched,
            'action': self.action,
            'latency_ms': round(self.latency_ms, 3),
            'matched_condition': self.matched_condition,
            'error': self.error,
            'fallback': self.fallback,
        }


# ==================== Security Validator ====================

class ExpressionValidator:
    @staticmethod
    def validate(expression: str) -> Tuple[bool, Optional[str]]:
        if not expression or not isinstance(expression, str):
            return False, 'Expression must be a non-empty string'

        patterns = EvalEngineSettings.get('FORBIDDEN_PATTERNS') or FORBIDDEN_PATTERNS
        for pattern in patterns:
            if re.search(pattern, expression, re.IGNORECASE):
                return False, f'Forbidden pattern detected: {pattern}'

        max_length = EvalEngineSettings.expression_max_length()
        if len(expression) > max_length:
            return False, f'Expression exceeds max length ({max_length})'

        try:
            compile(expression, '<string>', 'eval')
        except SyntaxError as e:
            return False, f'Syntax error: {e}'

        return True, None

    @staticmethod
    def sanitize_context(context: Dict[str, Any]) -> Dict[str, Any]:
        sanitized = {}
        forbidden_keys = {'password', 'secret', 'token', 'api_key', 'auth'}
        for key, value in context.items():
            if any(fk in key.lower() for fk in forbidden_keys):
                sanitized[key] = '***REDACTED***'
            else:
                sanitized[key] = value
        return sanitized


# ==================== Function Registry ====================

class RuleFunctionRegistry:
    _functions: Dict[str, Callable] = {}
    _initialized = False

    @classmethod
    def _initialize_builtins(cls):
        if cls._initialized:
            return
        cls._initialized = True

        cls.register('in_business_hours', cls._in_business_hours)
        cls.register('is_weekend', cls._is_weekend)
        cls.register('is_workday', cls._is_workday)
        cls.register('current_hour', cls._current_hour)
        cls.register('current_day_of_week', cls._current_day_of_week)

        cls.register('severity_score', cls._severity_score)
        cls.register('priority_score', cls._priority_score)
        cls.register('alert_frequency_trend', cls._alert_frequency_trend)

        cls.register('clamp', cls._clamp)
        cls.register('between', cls._between)

    @classmethod
    def register(cls, name: str, func: Callable):
        cls._functions[name] = func
        logger.debug(f'Registered rule function: {name}')

    @classmethod
    def get(cls, name: str) -> Optional[Callable]:
        cls._initialize_builtins()
        return cls._functions.get(name)

    @classmethod
    def get_all(cls) -> Dict[str, Callable]:
        cls._initialize_builtins()
        return cls._functions.copy()

    @staticmethod
    def _in_business_hours(start_hour: int = 9, end_hour: int = 18) -> bool:
        now = timezone.now()
        hour = now.hour
        weekday = now.weekday()
        if weekday >= 5:
            return False
        return start_hour <= hour < end_hour

    @staticmethod
    def _is_weekend() -> bool:
        return timezone.now().weekday() >= 5

    @staticmethod
    def _is_workday() -> bool:
        return timezone.now().weekday() < 5

    @staticmethod
    def _current_hour() -> int:
        return timezone.now().hour

    @staticmethod
    def _current_day_of_week() -> int:
        return timezone.now().weekday()

    @staticmethod
    def _severity_score(severity: str) -> int:
        mapping = {
            'critical': 3, 'warning': 2, 'info': 1,
            'high': 3, 'average': 2, 'low': 1,
        }
        return mapping.get(str(severity).lower(), 1)

    @staticmethod
    def _priority_score(priority: str) -> int:
        mapping = {'P0': 5, 'P1': 4, 'P2': 3, 'P3': 2, 'P4': 1}
        return mapping.get(str(priority).upper(), 1)

    @staticmethod
    def _alert_frequency_trend(count_1h: int, count_1d: int) -> float:
        if count_1d <= 0:
            return 0.0
        hourly_avg = count_1d / 24.0
        if hourly_avg <= 0:
            return 0.0
        return min(10.0, count_1h / hourly_avg)

    @staticmethod
    def _clamp(value: float, min_val: float, max_val: float) -> float:
        return max(min_val, min(min_val, max_val))

    @staticmethod
    def _between(value: float, min_val: float, max_val: float) -> bool:
        return min_val <= value <= max_val


# ==================== Audition Log Hook ====================

_audit_log_callback: Optional[Callable[[Dict[str, Any]], None]] = None


def set_audit_log_callback(callback: Callable[[Dict[str, Any]], None]):
    global _audit_log_callback
    _audit_log_callback = callback


# ==================== Configurable Rule Engine ====================

class ConfigurableRuleEngine:
    def __init__(self, default_timeout_ms: int = None):
        self.default_timeout_ms = default_timeout_ms or EvalEngineSettings.default_timeout_ms()
        self.simple_engine = SimpleRuleEngine()
        self.validator = ExpressionValidator()
        self.function_registry = RuleFunctionRegistry()
        self._compiled_cache: Dict[str, Any] = {}
        self._cache = get_cache()

    def evaluate(
        self,
        rule_id: str,
        context: Dict[str, Any],
        business_group: Optional[str] = None,
        use_cache: bool = True
    ) -> RuleEvaluationResult:
        start_time = time.time()
        trace_id = str(uuid.uuid4())

        logger.info({
            'event': 'rule_evaluation_started',
            'trace_id': trace_id,
            'rule_id': rule_id,
            'business_group': business_group,
        })

        try:
            rule = self._load_rule(rule_id, business_group, use_cache)
            if not rule:
                raise RuleNotFoundError(f'Rule not found: {rule_id}')

            self._validate_context(rule, context)
            matched, matched_condition = self._execute_evaluation(rule, context)
            action = self._get_action(rule, matched)

            latency_ms = (time.time() - start_time) * 1000

            result = RuleEvaluationResult(
                rule_id=rule_id,
                matched=matched,
                action=action,
                context=context,
                latency_ms=latency_ms,
                trace_id=trace_id,
                matched_condition=matched_condition,
            )

            self._record_audit_log(result)

            logger.info({
                'event': 'rule_evaluation_completed',
                'trace_id': trace_id,
                'rule_id': rule_id,
                'matched': matched,
                'latency_ms': latency_ms,
            })

            return result

        except RuleNotFoundError as e:
            return self._handle_error(rule_id, e, trace_id, start_time, 'rule_not_found')
        except RuleSecurityError as e:
            return self._handle_error(rule_id, e, trace_id, start_time, 'security_error')
        except RuleExecutionError as e:
            return self._handle_error(rule_id, e, trace_id, start_time, 'execution_error')
        except Exception as e:
            logger.exception(f'Unexpected error evaluating rule {rule_id}')
            return self._handle_error(rule_id, e, trace_id, start_time, 'unexpected_error')

    def _load_rule(
        self,
        rule_id: str,
        business_group: Optional[str] = None,
        use_cache: bool = True
    ) -> Optional[Dict[str, Any]]:
        cache_key = CacheKeys.RULE_JDM.format(rule_id=rule_id)

        if use_cache:
            cached = self._cache.get(cache_key)
            if cached:
                logger.debug(f'Rule loaded from cache: {rule_id}')
                return cached

        try:
            rule = RuleConfig.objects.get(rule_id=rule_id, is_active=True)
            rule_data = self._parse_rule_content(rule)
        except RuleConfig.DoesNotExist:
            return None

        if business_group:
            try:
                bg_rule = RuleConfig.objects.get(
                    rule_id=f'{rule_id}@{business_group}',
                    is_active=True
                )
                bg_data = self._parse_rule_content(bg_rule)
                rule_data = self._merge_rules(rule_data, bg_data)
            except RuleConfig.DoesNotExist:
                pass

        if use_cache:
            self._cache.set(cache_key, rule_data, timeout=EvalEngineSettings.cache_ttl())

        return rule_data

    def _parse_rule_content(self, rule: RuleConfig) -> Dict[str, Any]:
        content = rule.rule_content or {}

        return {
            'rule_id': rule.rule_id,
            'rule_name': rule.rule_name,
            'rule_type': rule.rule_type,
            'engine_type': rule.engine_type,
            'scope': rule.scope,
            'business_group': rule.business_group,
            'category_key': rule.category_key,
            'priority': rule.priority,
            'conditions': content.get('conditions', {}),
            'actions': content.get('actions', {}),
            'context': content.get('context', {}),
            'metadata': content.get('metadata', {}),
        }

    def _merge_rules(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        merged = base.copy()

        if override.get('conditions'):
            merged['conditions'] = override['conditions']

        if override.get('actions'):
            merged['actions'] = self._deep_merge(
                merged.get('actions', {}),
                override['actions']
            )

        merged['merged'] = True
        merged['base_rule_id'] = base.get('rule_id')
        merged['override_rule_id'] = override.get('rule_id')

        return merged

    def _deep_merge(self, base: Dict, override: Dict) -> Dict:
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def _validate_context(self, rule: Dict[str, Any], context: Dict[str, Any]):
        required = rule.get('context', {}).get('required_fields', [])
        missing = [f for f in required if f not in context]
        if missing:
            logger.warning(f'Missing required fields in context: {missing}')

    def _execute_evaluation(
        self,
        rule: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        conditions = rule.get('conditions', {})
        condition_format = conditions.get('format', 'simpleeval')

        if condition_format == 'simpleeval':
            return self._evaluate_simpleeval(conditions.get('expression', ''), context)
        elif condition_format == 'decision_table':
            return self._evaluate_decision_table(conditions.get('table', {}), context)
        else:
            raise RuleExecutionError(f'Unknown condition format: {condition_format}')

    def _evaluate_simpleeval(
        self,
        expression: str,
        context: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        if not expression:
            return True, None

        is_valid, error_msg = self.validator.validate(expression)
        if not is_valid:
            raise RuleSecurityError(f'Expression validation failed: {error_msg}')

        try:
            functions = ALLOWED_FUNCTIONS.copy()
            functions.update(self.function_registry.get_all())

            result = safe_simple_eval(
                expression,
                names=context,
                functions=functions,
            )

            matched = bool(result)
            return matched, expression if matched else None

        except (InvalidExpression, NameNotDefined) as e:
            raise RuleExecutionError(f'Expression evaluation failed: {e}')
        except Exception as e:
            raise RuleExecutionError(f'Unexpected error evaluating expression: {e}')

    def _evaluate_decision_table(
        self,
        table: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        result = self.simple_engine.evaluate_decision_table(table, context)

        is_fallback = result.get('fallback', False)
        matched = not is_fallback

        matched_condition = None
        if matched:
            matched_condition = 'decision_table_matched'

        return matched, matched_condition

    def _get_action(self, rule: Dict[str, Any], matched: bool) -> Dict[str, Any]:
        actions = rule.get('actions', {})

        if matched:
            action = actions.get('on_match', {'should_push': True})
        else:
            action = actions.get('on_mismatch', {'should_push': False, 'reason': 'rule_not_matched'})

        return action

    def _handle_error(
        self,
        rule_id: str,
        error: Exception,
        trace_id: str,
        start_time: float,
        reason: str
    ) -> RuleEvaluationResult:
        latency_ms = (time.time() - start_time) * 1000

        logger.error({
            'event': 'rule_evaluation_failed',
            'trace_id': trace_id,
            'rule_id': rule_id,
            'error_type': type(error).__name__,
            'error_message': str(error),
            'reason': reason,
            'latency_ms': latency_ms,
        })

        fallback = EvalEngineSettings.fallback_action()
        fallback_action = fallback.copy()
        fallback_action['reason'] = f'rule_fallback_{reason}'

        return RuleEvaluationResult(
            rule_id=rule_id,
            matched=False,
            action=fallback_action,
            context={},
            latency_ms=latency_ms,
            trace_id=trace_id,
            error=str(error),
            fallback=True,
        )

    def _record_audit_log(self, result: RuleEvaluationResult):
        try:
            callback = EvalEngineSettings.audit_log_callback() or _audit_log_callback
            if callback is not None:
                callback(result.to_dict())
                return
        except Exception as e:
            logger.warning(f'Failed to record audit log via callback: {e}')

    # ==================== Rule Management API ====================

    def create_rule(self, rule_data: Dict[str, Any], created_by: str = '') -> Dict[str, Any]:
        rule_id = rule_data.get('rule_id')
        if not rule_id:
            raise RuleValidationError('rule_id is required')

        if RuleConfig.objects.filter(rule_id=rule_id).exists():
            raise RuleValidationError(f'Rule already exists: {rule_id}')

        self._validate_rule_content(rule_data)

        with transaction.atomic():
            rule = RuleConfig.objects.create(
                rule_id=rule_id,
                rule_name=rule_data.get('rule_name', rule_id),
                rule_type=rule_data.get('rule_type', 'push_decision'),
                engine_type=rule_data.get('engine_type', 'simpleeval'),
                scope=rule_data.get('scope', 'global'),
                business_group=rule_data.get('business_group', ''),
                category_key=rule_data.get('category_key', ''),
                rule_content={
                    'conditions': rule_data.get('conditions', {}),
                    'actions': rule_data.get('actions', {}),
                    'context': rule_data.get('context', {}),
                    'metadata': {
                        **rule_data.get('metadata', {}),
                        'created_by': created_by,
                        'created_at': timezone.now().isoformat(),
                    }
                },
                priority=rule_data.get('priority', 0),
                description=rule_data.get('description', ''),
                created_by=created_by,
            )

            RuleVersionHistory.objects.create(
                rule=rule,
                version=1,
                rule_content=rule.rule_content,
                changed_by=created_by,
                change_comment='Initial creation',
            )

        self._cache.delete(CacheKeys.RULE_JDM.format(rule_id=rule_id))

        return {
            'rule_id': rule.rule_id,
            'version': 1,
            'status': 'created',
        }

    def update_rule(
        self,
        rule_id: str,
        rule_data: Dict[str, Any],
        changed_by: str = '',
        change_comment: str = ''
    ) -> Dict[str, Any]:
        try:
            rule = RuleConfig.objects.get(rule_id=rule_id)
        except RuleConfig.DoesNotExist:
            raise RuleNotFoundError(f'Rule not found: {rule_id}')

        self._validate_rule_content(rule_data)

        with transaction.atomic():
            new_version = rule.version + 1

            RuleVersionHistory.objects.create(
                rule=rule,
                version=new_version,
                rule_content={
                    'conditions': rule_data.get('conditions', {}),
                    'actions': rule_data.get('actions', {}),
                    'context': rule_data.get('context', {}),
                    'metadata': rule_data.get('metadata', {}),
                },
                changed_by=changed_by,
                change_comment=change_comment or 'Updated via API',
            )

            rule.rule_name = rule_data.get('rule_name', rule.rule_name)
            rule.rule_type = rule_data.get('rule_type', rule.rule_type)
            rule.engine_type = rule_data.get('engine_type', rule.engine_type)
            rule.scope = rule_data.get('scope', rule.scope)
            rule.business_group = rule_data.get('business_group', rule.business_group)
            rule.category_key = rule_data.get('category_key', rule.category_key)
            rule.rule_content = {
                'conditions': rule_data.get('conditions', {}),
                'actions': rule_data.get('actions', {}),
                'context': rule_data.get('context', {}),
                'metadata': {
                    **rule_data.get('metadata', {}),
                    'updated_by': changed_by,
                    'updated_at': timezone.now().isoformat(),
                }
            }
            rule.priority = rule_data.get('priority', rule.priority)
            rule.description = rule_data.get('description', rule.description)
            rule.save()

        self._cache.delete(CacheKeys.RULE_JDM.format(rule_id=rule_id))
        self._cache.set(CacheKeys.RULE_VERSION.format(rule_id=rule_id), new_version)

        return {
            'rule_id': rule_id,
            'version': new_version,
            'status': 'updated',
        }

    def publish_rule(self, rule_id: str, version: int, published_by: str = '') -> Dict[str, Any]:
        try:
            version_record = RuleVersionHistory.objects.get(rule_id=rule_id, version=version)
        except RuleVersionHistory.DoesNotExist:
            raise RuleNotFoundError(f'Rule version not found: {rule_id} v{version}')

        logger.info({
            'event': 'rule_published',
            'rule_id': rule_id,
            'version': version,
            'published_by': published_by,
        })

        return {
            'rule_id': rule_id,
            'version': version,
            'status': 'published',
        }

    def rollback_rule(self, rule_id: str, to_version: int) -> Dict[str, Any]:
        try:
            target_version = RuleVersionHistory.objects.get(rule_id=rule_id, version=to_version)
            rule = RuleConfig.objects.get(rule_id=rule_id)
        except (RuleVersionHistory.DoesNotExist, RuleConfig.DoesNotExist):
            raise RuleNotFoundError(f'Rule or version not found: {rule_id} v{to_version}')

        with transaction.atomic():
            new_version = rule.version + 1
            RuleVersionHistory.objects.create(
                rule=rule,
                version=new_version,
                rule_content=target_version.rule_content,
                changed_by='system',
                change_comment=f'Rollback to version {to_version}',
            )

            rule.rule_content = target_version.rule_content
            rule.save()

        self._cache.delete(CacheKeys.RULE_JDM.format(rule_id=rule_id))

        return {
            'rule_id': rule_id,
            'version': new_version,
            'status': 'rolled_back',
            'target_version': to_version,
        }

    def _validate_rule_content(self, rule_data: Dict[str, Any]):
        conditions = rule_data.get('conditions', {})

        if conditions.get('format') == 'simpleeval':
            expression = conditions.get('expression', '')
            is_valid, error_msg = self.validator.validate(expression)
            if not is_valid:
                raise RuleValidationError(f'Invalid expression: {error_msg}')

    # ==================== Test Framework ====================

    def test_rule(
        self,
        rule_id: str,
        test_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        start_time = time.time()

        try:
            result = self.evaluate(rule_id, test_context, use_cache=False)

            return {
                'success': True,
                'matched': result.matched,
                'action': result.action,
                'matched_condition': result.matched_condition,
                'latency_ms': result.latency_ms,
                'trace_id': result.trace_id,
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'error_type': type(e).__name__,
                'latency_ms': (time.time() - start_time) * 1000,
            }

    def run_test_suite(
        self,
        rule_id: str,
        test_cases: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        results = []
        passed_count = 0
        failed_count = 0
        total_latency = 0.0

        for case in test_cases:
            case_name = case.get('name', 'unnamed')
            context = case.get('context', {})
            expected_matched = case.get('expected_matched')
            expected_action = case.get('expected_action')

            start_time = time.time()
            try:
                result = self.evaluate(rule_id, context, use_cache=False)
                latency_ms = (time.time() - start_time) * 1000
                total_latency += latency_ms

                case_passed = True
                failure_reasons = []

                if expected_matched is not None and result.matched != expected_matched:
                    case_passed = False
                    failure_reasons.append(
                        f'matched: expected={expected_matched}, actual={result.matched}'
                    )

                if expected_action is not None:
                    for key, expected_val in expected_action.items():
                        actual_val = result.action.get(key)
                        if actual_val != expected_val:
                            case_passed = False
                            failure_reasons.append(
                                f'{key}: expected={expected_val}, actual={actual_val}'
                            )

                if case_passed:
                    passed_count += 1
                else:
                    failed_count += 1

                results.append({
                    'case_name': case_name,
                    'passed': case_passed,
                    'expected': {'matched': expected_matched, 'action': expected_action},
                    'actual': {'matched': result.matched, 'action': result.action},
                    'latency_ms': latency_ms,
                    'failure_reasons': failure_reasons if not case_passed else [],
                })

            except Exception as e:
                failed_count += 1
                latency_ms = (time.time() - start_time) * 1000
                total_latency += latency_ms

                results.append({
                    'case_name': case_name,
                    'passed': False,
                    'error': str(e),
                    'latency_ms': latency_ms,
                })

        total = len(test_cases)
        avg_latency = total_latency / total if total > 0 else 0

        return {
            'rule_id': rule_id,
            'total': total,
            'passed': passed_count,
            'failed': failed_count,
            'pass_rate': round(passed_count / total, 4) if total > 0 else 0,
            'avg_latency_ms': round(avg_latency, 3),
            'results': results,
        }

    def validate_expression_syntax(self, expression: str) -> Dict[str, Any]:
        is_valid, error_msg = self.validator.validate(expression)

        if not is_valid:
            return {
                'valid': False,
                'error': error_msg,
            }

        try:
            functions = ALLOWED_FUNCTIONS.copy()
            functions.update(self.function_registry.get_all())
            safe_simple_eval(expression, names={}, functions=functions)
        except NameNotDefined:
            pass
        except Exception as e:
            return {
                'valid': False,
                'error': f'Expression syntax error: {e}',
            }

        return {
            'valid': True,
            'message': 'Expression is valid',
        }


# ==================== Engine Health Monitor ====================

class RuleExecutionMonitor:
    @staticmethod
    def get_engine_health() -> Dict[str, Any]:
        test_start = time.time()
        try:
            engine = ConfigurableRuleEngine()
            test_result = engine.validate_expression_syntax('1 + 1 == 2')
            test_latency = (time.time() - test_start) * 1000

            return {
                'status': 'healthy' if test_result['valid'] else 'degraded',
                'test_latency_ms': round(test_latency, 3),
                'expression_validator': 'ok',
                'function_registry_count': len(RuleFunctionRegistry.get_all()),
                'checked_at': timezone.now().isoformat(),
            }
        except Exception as e:
            return {
                'status': 'unhealthy',
                'error': str(e),
                'checked_at': timezone.now().isoformat(),
            }