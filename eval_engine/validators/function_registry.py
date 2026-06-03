"""
Function registry for rule evaluation.
Extracted from configurable_rule_engine.py for better modularity.
"""
import logging
from typing import Callable, Dict, Optional
from datetime import datetime

from django.utils import timezone

logger = logging.getLogger(__name__)


class RuleFunctionRegistry:
    """Registry for custom functions available in rule expressions."""
    
    _functions: Dict[str, Callable] = {}
    _initialized = False

    @classmethod
    def _initialize_builtins(cls):
        """Initialize built-in time and scoring functions."""
        if cls._initialized:
            return
        cls._initialized = True

        # Time-based functions
        cls.register('in_business_hours', cls._in_business_hours)
        cls.register('is_weekend', cls._is_weekend)
        cls.register('is_workday', cls._is_workday)
        cls.register('current_hour', cls._current_hour)
        cls.register('current_day_of_week', cls._current_day_of_week)

        # Scoring functions
        cls.register('severity_score', cls._severity_score)
        cls.register('priority_score', cls._priority_score)
        cls.register('alert_frequency_trend', cls._alert_frequency_trend)

        # Utility functions
        cls.register('clamp', cls._clamp)
        cls.register('between', cls._between)

    @classmethod
    def register(cls, name: str, func: Callable):
        """Register a custom function."""
        cls._functions[name] = func
        logger.debug(f'Registered rule function: {name}')

    @classmethod
    def get(cls, name: str) -> Optional[Callable]:
        """Get a registered function by name."""
        cls._initialize_builtins()
        return cls._functions.get(name)

    @classmethod
    def get_all(cls) -> Dict[str, Callable]:
        """Get all registered functions."""
        cls._initialize_builtins()
        return cls._functions.copy()

    @classmethod
    def unregister(cls, name: str):
        """Unregister a function by name."""
        if name in cls._functions:
            del cls._functions[name]
            logger.debug(f'Unregistered rule function: {name}')

    @classmethod
    def clear(cls):
        """Clear all registered functions (useful for testing)."""
        cls._functions = {}
        cls._initialized = False

    # ==================== Time-based Functions ====================
    
    @staticmethod
    def _in_business_hours(start_hour: int = 9, end_hour: int = 18) -> bool:
        """Check if current time is within business hours."""
        now = timezone.now()
        hour = now.hour
        weekday = now.weekday()
        if weekday >= 5:
            return False
        return start_hour <= hour < end_hour

    @staticmethod
    def _is_weekend() -> bool:
        """Check if today is weekend."""
        return timezone.now().weekday() >= 5

    @staticmethod
    def _is_workday() -> bool:
        """Check if today is a workday."""
        return timezone.now().weekday() < 5

    @staticmethod
    def _current_hour() -> int:
        """Get current hour (0-23)."""
        return timezone.now().hour

    @staticmethod
    def _current_day_of_week() -> int:
        """Get current day of week (0=Monday, 6=Sunday)."""
        return timezone.now().weekday()

    # ==================== Scoring Functions ====================
    
    @staticmethod
    def _severity_score(severity: str) -> int:
        """Convert severity string to numeric score."""
        mapping = {
            'critical': 3, 'warning': 2, 'info': 1,
            'high': 3, 'average': 2, 'low': 1,
        }
        return mapping.get(str(severity).lower(), 1)

    @staticmethod
    def _priority_score(priority: str) -> int:
        """Convert priority string to numeric score."""
        mapping = {'P0': 5, 'P1': 4, 'P2': 3, 'P3': 2, 'P4': 1}
        return mapping.get(str(priority).upper(), 1)

    @staticmethod
    def _alert_frequency_trend(count_1h: int, count_1d: int) -> float:
        """Calculate alert frequency trend ratio."""
        if count_1d <= 0:
            return 0.0
        hourly_avg = count_1d / 24.0
        if hourly_avg <= 0:
            return 0.0
        return min(10.0, count_1h / hourly_avg)

    # ==================== Utility Functions ====================
    
    @staticmethod
    def _clamp(value: float, min_val: float, max_val: float) -> float:
        """Clamp value between min and max."""
        return max(min_val, min(value, max_val))

    @staticmethod
    def _between(value: float, min_val: float, max_val: float) -> bool:
        """Check if value is between min and max (inclusive)."""
        return min_val <= value <= max_val
