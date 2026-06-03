"""
Anomaly Detector for Rule Evaluation

Detects unusual patterns in rule evaluation behavior.
"""

import statistics
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict
import math


@dataclass
class AnomalyReport:
    """Report of detected anomalies."""
    rule_id: int
    anomaly_type: str
    severity: str  # 'low', 'medium', 'high', 'critical'
    description: str
    detected_at: float
    metrics: Dict[str, Any] = field(default_factory=dict)
    recommended_action: str = ""


class AnomalyDetector:
    """
    Detects anomalies in rule evaluation patterns.
    
    Uses statistical methods (Z-score, IQR, moving averages)
    to identify unusual behavior.
    
    Usage:
        detector = AnomalyDetector()
        
        # Feed evaluation data
        detector.record_evaluation(
            rule_id=123,
            duration_ms=45.2,
            success=True,
            result={"action": "approve"}
        )
        
        # Check for anomalies
        anomalies = detector.detect_anomalies(rule_id=123)
    """
    
    def __init__(
        self,
        z_threshold: float = 3.0,
        window_size: int = 100,
        min_samples: int = 30,
    ):
        self.z_threshold = z_threshold
        self.window_size = window_size
        self.min_samples = min_samples
        
        self._durations: Dict[int, List[float]] = defaultdict(list)
        self._success_rates: Dict[int, List[float]] = defaultdict(list)
        self._result_patterns: Dict[int, List[Dict]] = defaultdict(list)
        self._detected_anomalies: List[AnomalyReport] = []
    
    def record_evaluation(
        self,
        rule_id: int,
        duration_ms: float,
        success: bool,
        result: Optional[Dict] = None,
    ) -> List[AnomalyReport]:
        """
        Record an evaluation and check for anomalies.
        
        Returns any detected anomalies.
        """
        import time
        
        # Add to history
        self._durations[rule_id].append(duration_ms)
        self._success_rates[rule_id].append(1.0 if success else 0.0)
        
        if result:
            self._result_patterns[rule_id].append(result)
        
        # Trim to window size
        if len(self._durations[rule_id]) > self.window_size:
            self._durations[rule_id] = self._durations[rule_id][-self.window_size:]
            self._success_rates[rule_id] = self._success_rates[rule_id][-self.window_size:]
            self._result_patterns[rule_id] = self._result_patterns[rule_id][-self.window_size:]
        
        # Check for anomalies if we have enough samples
        anomalies = []
        if len(self._durations[rule_id]) >= self.min_samples:
            anomalies.extend(self._check_duration_anomaly(rule_id))
            anomalies.extend(self._check_success_rate_anomaly(rule_id))
            anomalies.extend(self._check_result_pattern_anomaly(rule_id))
        
        self._detected_anomalies.extend(anomalies)
        return anomalies
    
    def _check_duration_anomaly(self, rule_id: int) -> List[AnomalyReport]:
        """Check for latency anomalies using Z-score."""
        import time
        
        durations = self._durations[rule_id]
        if len(durations) < self.min_samples:
            return []
        
        mean = statistics.mean(durations)
        stdev = statistics.stdev(durations) if len(durations) > 1 else 0
        
        if stdev == 0:
            return []
        
        latest = durations[-1]
        z_score = (latest - mean) / stdev
        
        anomalies = []
        
        if abs(z_score) > self.z_threshold:
            severity = self._calculate_severity(abs(z_score), self.z_threshold)
            
            anomalies.append(AnomalyReport(
                rule_id=rule_id,
                anomaly_type='latency_spike' if z_score > 0 else 'latency_drop',
                severity=severity,
                description=f'Latency {latest:.1f}ms is {abs(z_score):.1f} std devs from mean ({mean:.1f}ms)',
                detected_at=time.time(),
                metrics={
                    'current_ms': latest,
                    'mean_ms': mean,
                    'stdev_ms': stdev,
                    'z_score': z_score,
                },
                recommended_action='Investigate recent changes or external dependencies' if z_score > 0 else 'Verify correctness of fast responses',
            ))
        
        # Check for sudden change (consecutive increases)
        if len(durations) >= 5:
            recent_trend = durations[-5:]
            if all(recent_trend[i] < recent_trend[i+1] for i in range(len(recent_trend)-1)):
                increase_pct = (recent_trend[-1] - recent_trend[0]) / recent_trend[0] * 100
                
                if increase_pct > 50:
                    anomalies.append(AnomalyReport(
                        rule_id=rule_id,
                        anomaly_type='latency_trend',
                        severity='medium' if increase_pct < 100 else 'high',
                        description=f'Latency increased {increase_pct:.0f}% over last 5 evaluations',
                        detected_at=time.time(),
                        metrics={
                            'increase_pct': increase_pct,
                            'start_ms': recent_trend[0],
                            'end_ms': recent_trend[-1],
                        },
                        recommended_action='Review recent deployments or configuration changes',
                    ))
        
        return anomalies
    
    def _check_success_rate_anomaly(self, rule_id: int) -> List[AnomalyReport]:
        """Check for success rate anomalies."""
        import time
        
        rates = self._success_rates[rule_id]
        if len(rates) < self.min_samples:
            return []
        
        # Calculate moving average
        window = min(20, len(rates))
        recent_avg = statistics.mean(rates[-window:])
        overall_avg = statistics.mean(rates)
        
        anomalies = []
        
        # Check for significant drop
        if recent_avg < overall_avg * 0.9:  # 10% drop
            drop_pct = (overall_avg - recent_avg) / overall_avg * 100
            
            severity = 'low'
            if drop_pct > 20:
                severity = 'medium'
            if drop_pct > 50:
                severity = 'high'
            if recent_avg < 0.5:
                severity = 'critical'
            
            anomalies.append(AnomalyReport(
                rule_id=rule_id,
                anomaly_type='success_rate_drop',
                severity=severity,
                description=f'Success rate dropped {drop_pct:.0f}% (from {overall_avg:.1%} to {recent_avg:.1%})',
                detected_at=time.time(),
                metrics={
                    'recent_avg': recent_avg,
                    'overall_avg': overall_avg,
                    'drop_pct': drop_pct,
                },
                recommended_action='Immediately investigate error logs and recent changes',
            ))
        
        return anomalies
    
    def _check_result_pattern_anomaly(self, rule_id: int) -> List[AnomalyReport]:
        """Check for unusual result distribution changes."""
        import time
        
        results = self._result_patterns[rule_id]
        if len(results) < self.min_samples:
            return []
        
        # Simple check: count unique result patterns
        window = min(50, len(results))
        recent_results = results[-window:]
        
        # Convert to hashable form
        def result_key(r):
            return str(sorted(r.items())) if r else 'null'
        
        recent_patterns = defaultdict(int)
        for r in recent_results:
            recent_patterns[result_key(r)] += 1
        
        # Check if a new pattern emerged suddenly
        old_window = min(50, len(results) // 2)
        old_results = results[:-window] if len(results) > window else []
        old_patterns = set(result_key(r) for r in old_results)
        
        new_patterns = [k for k in recent_patterns.keys() if k not in old_patterns]
        
        anomalies = []
        
        if len(new_patterns) > 0 and len(recent_results) > 20:
            new_pattern_count = sum(recent_patterns[k] for k in new_patterns)
            new_pattern_pct = new_pattern_count / len(recent_results) * 100
            
            if new_pattern_pct > 20:  # More than 20% new patterns
                anomalies.append(AnomalyReport(
                    rule_id=rule_id,
                    anomaly_type='result_pattern_change',
                    severity='medium',
                    description=f'{new_pattern_pct:.0f}% of recent results show new patterns',
                    detected_at=time.time(),
                    metrics={
                        'new_pattern_count': len(new_patterns),
                        'new_pattern_pct': new_pattern_pct,
                    },
                    recommended_action='Review rule logic and input data changes',
                ))
        
        return anomalies
    
    def _calculate_severity(self, value: float, threshold: float) -> str:
        """Calculate severity based on how much value exceeds threshold."""
        ratio = value / threshold
        
        if ratio > 3:
            return 'critical'
        elif ratio > 2:
            return 'high'
        elif ratio > 1.5:
            return 'medium'
        else:
            return 'low'
    
    def detect_anomalies(self, rule_id: Optional[int] = None) -> List[AnomalyReport]:
        """Get detected anomalies, optionally filtered by rule_id."""
        if rule_id is not None:
            return [a for a in self._detected_anomalies if a.rule_id == rule_id]
        return self._detected_anomalies.copy()
    
    def get_health_score(self, rule_id: int) -> float:
        """
        Calculate overall health score for a rule (0-100).
        
        Based on anomaly frequency and severity.
        """
        anomalies = self.detect_anomalies(rule_id=rule_id)
        
        if not anomalies:
            return 100.0
        
        # Weight by severity
        severity_weights = {
            'low': 1,
            'medium': 3,
            'high': 5,
            'critical': 10,
        }
        
        total_weight = sum(severity_weights.get(a.severity, 1) for a in anomalies)
        
        # More anomalies = lower score
        score = max(0, 100 - total_weight * 2)
        
        return score
    
    def clear_history(self, rule_id: Optional[int] = None) -> None:
        """Clear detection history."""
        if rule_id is not None:
            self._durations.pop(rule_id, None)
            self._success_rates.pop(rule_id, None)
            self._result_patterns.pop(rule_id, None)
            self._detected_anomalies = [a for a in self._detected_anomalies if a.rule_id != rule_id]
        else:
            self._durations.clear()
            self._success_rates.clear()
            self._result_patterns.clear()
            self._detected_anomalies.clear()
