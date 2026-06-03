"""
Performance profiler for rule evaluation.
Provides P50/P99 latency statistics and performance monitoring.
"""
import time
import threading
import statistics
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """Performance metrics for a rule."""
    rule_id: str
    call_count: int = 0
    total_latency_ms: float = 0.0
    latencies_ms: List[float] = field(default_factory=list)
    error_count: int = 0
    success_count: int = 0
    
    @property
    def avg_latency_ms(self) -> float:
        """Average latency in milliseconds."""
        if not self.latencies_ms:
            return 0.0
        return statistics.mean(self.latencies_ms)
    
    @property
    def p50_latency_ms(self) -> float:
        """50th percentile latency (median)."""
        if not self.latencies_ms:
            return 0.0
        return statistics.median(self.latencies_ms)
    
    @property
    def p90_latency_ms(self) -> float:
        """90th percentile latency."""
        if not self.latencies_ms:
            return 0.0
        sorted_latencies = sorted(self.latencies_ms)
        idx = int(len(sorted_latencies) * 0.9)
        return sorted_latencies[min(idx, len(sorted_latencies) - 1)]
    
    @property
    def p99_latency_ms(self) -> float:
        """99th percentile latency."""
        if not self.latencies_ms:
            return 0.0
        sorted_latencies = sorted(self.latencies_ms)
        idx = int(len(sorted_latencies) * 0.99)
        return sorted_latencies[min(idx, len(sorted_latencies) - 1)]
    
    @property
    def min_latency_ms(self) -> float:
        """Minimum latency."""
        if not self.latencies_ms:
            return 0.0
        return min(self.latencies_ms)
    
    @property
    def max_latency_ms(self) -> float:
        """Maximum latency."""
        if not self.latencies_ms:
            return 0.0
        return max(self.latencies_ms)
    
    @property
    def success_rate(self) -> float:
        """Success rate as a percentage."""
        if self.call_count == 0:
            return 0.0
        return (self.success_count / self.call_count) * 100
    
    @property
    def error_rate(self) -> float:
        """Error rate as a percentage."""
        if self.call_count == 0:
            return 0.0
        return (self.error_count / self.call_count) * 100
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            'rule_id': self.rule_id,
            'call_count': self.call_count,
            'avg_latency_ms': round(self.avg_latency_ms, 3),
            'p50_latency_ms': round(self.p50_latency_ms, 3),
            'p90_latency_ms': round(self.p90_latency_ms, 3),
            'p99_latency_ms': round(self.p99_latency_ms, 3),
            'min_latency_ms': round(self.min_latency_ms, 3),
            'max_latency_ms': round(self.max_latency_ms, 3),
            'success_count': self.success_count,
            'error_count': self.error_count,
            'success_rate': round(self.success_rate, 2),
            'error_rate': round(self.error_rate, 2),
        }
    
    def reset(self):
        """Reset all metrics."""
        self.call_count = 0
        self.total_latency_ms = 0.0
        self.latencies_ms = []
        self.error_count = 0
        self.success_count = 0


class RulePerformanceProfiler:
    """
    Performance profiler for rule evaluation.
    Tracks latency percentiles (P50, P90, P99) and success/error rates.
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._metrics: Dict[str, PerformanceMetrics] = defaultdict(lambda: PerformanceMetrics(rule_id=''))
        self._global_metrics = PerformanceMetrics(rule_id='__global__')
        self._lock = threading.Lock()
        self._max_samples_per_rule = 10000  # Max samples to keep per rule
    
    def record(
        self,
        rule_id: str,
        latency_ms: float,
        is_success: bool = True,
        error_type: Optional[str] = None
    ):
        """
        Record a rule evaluation result.
        
        Args:
            rule_id: The rule ID
            latency_ms: Execution latency in milliseconds
            is_success: Whether the evaluation succeeded
            error_type: Type of error if failed
        """
        with self._lock:
            metrics = self._metrics[rule_id]
            metrics.rule_id = rule_id
            metrics.call_count += 1
            metrics.total_latency_ms += latency_ms
            
            # Keep a rolling window of samples
            if len(metrics.latencies_ms) >= self._max_samples_per_rule:
                metrics.latencies_ms.pop(0)
            metrics.latencies_ms.append(latency_ms)
            
            if is_success:
                metrics.success_count += 1
            else:
                metrics.error_count += 1
                logger.debug(f'Rule {rule_id} failed with error type: {error_type}')
            
            # Update global metrics
            self._global_metrics.call_count += 1
            self._global_metrics.total_latency_ms += latency_ms
            if len(self._global_metrics.latencies_ms) >= self._max_samples_per_rule * 10:
                self._global_metrics.latencies_ms.pop(0)
            self._global_metrics.latencies_ms.append(latency_ms)
            
            if is_success:
                self._global_metrics.success_count += 1
            else:
                self._global_metrics.error_count += 1
    
    def get_metrics(self, rule_id: str) -> Optional[PerformanceMetrics]:
        """Get metrics for a specific rule."""
        with self._lock:
            return self._metrics.get(rule_id)
    
    def get_all_metrics(self) -> Dict[str, PerformanceMetrics]:
        """Get metrics for all rules."""
        with self._lock:
            return dict(self._metrics)
    
    def get_global_metrics(self) -> PerformanceMetrics:
        """Get global aggregated metrics."""
        with self._lock:
            return self._global_metrics
    
    def get_slow_rules(self, threshold_ms: float = 100.0, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get the slowest rules by P99 latency.
        
        Args:
            threshold_ms: Minimum P99 latency to consider
            limit: Maximum number of rules to return
            
        Returns:
            List of rule metrics sorted by P99 latency
        """
        with self._lock:
            slow_rules = [
                m.to_dict() for m in self._metrics.values()
                if m.call_count > 0 and m.p99_latency_ms >= threshold_ms
            ]
            slow_rules.sort(key=lambda x: x['p99_latency_ms'], reverse=True)
            return slow_rules[:limit]
    
    def reset(self, rule_id: Optional[str] = None):
        """
        Reset metrics.
        
        Args:
            rule_id: If provided, reset only this rule. Otherwise reset all.
        """
        with self._lock:
            if rule_id:
                if rule_id in self._metrics:
                    self._metrics[rule_id].reset()
            else:
                self._metrics.clear()
                self._global_metrics.reset()
    
    def export_stats(self) -> Dict[str, Any]:
        """Export all statistics for monitoring systems."""
        with self._lock:
            global_stats = self._global_metrics.to_dict()
            rules_stats = {k: v.to_dict() for k, v in self._metrics.items()}
        
        # Get slow rules separately to avoid nested lock acquisition
        slow_rules = self.get_slow_rules()
        
        return {
            'global': global_stats,
            'rules': rules_stats,
            'slow_rules': slow_rules,
        }


# Context manager for easy profiling
class RuleEvaluationContext:
    """Context manager for timing rule evaluations."""
    
    def __init__(self, rule_id: str, profiler: Optional[RulePerformanceProfiler] = None):
        self.rule_id = rule_id
        self.profiler = profiler or RulePerformanceProfiler()
        self.start_time = None
        self.is_success = True
        self.error_type = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        latency_ms = (time.time() - self.start_time) * 1000
        if exc_type is not None:
            self.is_success = False
            self.error_type = exc_type.__name__
        self.profiler.record(
            rule_id=self.rule_id,
            latency_ms=latency_ms,
            is_success=self.is_success,
            error_type=self.error_type
        )
        return False  # Don't suppress exceptions
