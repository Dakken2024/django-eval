"""
Utility functions for the alerts demo app.

This module demonstrates how to integrate django-eval's audit logging
and custom functions into your application.
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)


def demo_audit_logger(result_dict: dict[str, Any]) -> None:
    """
    Demo callback for django-eval audit logging.

    This function receives every rule evaluation result and can log it
    to a database, send to an external monitoring system, etc.

    Args:
        result_dict: Evaluation result containing trace_id, rule_id,
                     matched, action, latency_ms, etc.
    """
    logger.info(
        "[AUDIT] trace=%s rule=%s matched=%s latency=%.3fms fallback=%s",
        result_dict.get('trace_id'),
        result_dict.get('rule_id'),
        result_dict.get('matched'),
        result_dict.get('latency_ms', 0),
        result_dict.get('fallback', False),
    )


def evaluate_alert_push(alert) -> dict[str, Any]:
    """
    Evaluate whether an alert should be pushed using django-eval.

    This is the core integration point showing how to use the rule engine
    in your business logic.

    Args:
        alert: An Alert model instance

    Returns:
        Dict with 'should_push', 'channel', 'reason' keys
    """
    from eval_engine.configurable_rule_engine import ConfigurableRuleEngine

    engine = ConfigurableRuleEngine()
    context = alert.to_context()

    # Evaluate the default push decision rule
    result = engine.evaluate('default_push_decision', context)

    if result.fallback:
        # Rule evaluation failed - use safe default
        return {
            'should_push': True,
            'channel': 'im_normal',
            'reason': 'fallback_due_to_error',
            'trace_id': result.trace_id,
        }

    action = result.action
    return {
        'should_push': action.get('should_push', False),
        'channel': action.get('channel', 'im_normal'),
        'reason': action.get('reason', 'rule_evaluated'),
        'trace_id': result.trace_id,
        'latency_ms': result.latency_ms,
    }