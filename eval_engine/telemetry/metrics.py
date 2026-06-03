"""
Metrics Collection for Rule Evaluation

Provides metrics collection and export capabilities.
"""

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable
from enum import Enum


class MetricType(Enum):
    """Types of metrics supported."""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"


@dataclass
class MetricPoint:
    """A single metric data point."""
    name: str
    value: float
    timestamp: float
    metric_type: MetricType
    labels: Dict[str, str] = field(default_factory=dict)
    
    def __post_init__(self):
        if self.timestamp == 0:
            self.timestamp = time.time()


@dataclass
class HistogramBucket:
    """Histogram bucket for distribution metrics."""
    le: float  # Less than or equal boundary
    count: int = 0


class MetricsCollector:
    """
    Collects and aggregates metrics for rule evaluation.
    
    Supports counters, gauges, histograms, and summaries.
    Can export to Prometheus, StatsD, or custom backends.
    
    Usage:
        collector = MetricsCollector()
        
        # Record counter
        collector.increment("rule.evaluations.total", labels={"rule_id": "123"})
        
        # Record histogram
        collector.record_histogram(
            "rule.evaluation.duration_ms",
            45.2,
            labels={"rule_id": "123"}
        )
        
        # Export metrics
        metrics = collector.get_metrics()
    """
    
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._counters: Dict[str, float] = defaultdict(float)
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, Dict] = defaultdict(lambda: {
            'buckets': [
                HistogramBucket(le=5),
                HistogramBucket(le=10),
                HistogramBucket(le=25),
                HistogramBucket(le=50),
                HistogramBucket(le=100),
                HistogramBucket(le=250),
                HistogramBucket(le=500),
                HistogramBucket(le=1000),
                HistogramBucket(le=float('inf')),
            ],
            'sum': 0.0,
            'count': 0,
            'labels': {},
        })
        self._summaries: Dict[str, Dict] = defaultdict(lambda: {
            'values': [],
            'count': 0,
            'sum': 0.0,
            'labels': {},
        })
        self._points: List[MetricPoint] = []
    
    def _make_key(self, name: str, labels: Dict[str, str]) -> str:
        """Create unique key from name and labels."""
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}" if label_str else name
    
    def increment(
        self,
        name: str,
        value: float = 1.0,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """Increment a counter metric."""
        if not self.enabled:
            return
        
        labels = labels or {}
        key = self._make_key(name, labels)
        self._counters[key] += value
        
        self._points.append(MetricPoint(
            name=name,
            value=self._counters[key],
            timestamp=time.time(),
            metric_type=MetricType.COUNTER,
            labels=labels,
        ))
    
    def set_gauge(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """Set a gauge metric."""
        if not self.enabled:
            return
        
        labels = labels or {}
        key = self._make_key(name, labels)
        self._gauges[key] = value
        
        self._points.append(MetricPoint(
            name=name,
            value=value,
            timestamp=time.time(),
            metric_type=MetricType.GAUGE,
            labels=labels,
        ))
    
    def record_histogram(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """Record a value in a histogram."""
        if not self.enabled:
            return
        
        labels = labels or {}
        key = self._make_key(name, labels)
        hist = self._histograms[key]
        
        hist['sum'] += value
        hist['count'] += 1
        hist['labels'] = labels
        
        # Update bucket counts
        for bucket in hist['buckets']:
            if value <= bucket.le:
                bucket.count += 1
        
        self._points.append(MetricPoint(
            name=name,
            value=value,
            timestamp=time.time(),
            metric_type=MetricType.HISTOGRAM,
            labels=labels,
        ))
    
    def record_summary(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """Record a value in a summary (for quantile calculation)."""
        if not self.enabled:
            return
        
        labels = labels or {}
        key = self._make_key(name, labels)
        summary = self._summaries[key]
        
        summary['values'].append(value)
        summary['count'] += 1
        summary['sum'] += value
        summary['labels'] = labels
        
        # Keep only last 1000 values to prevent memory growth
        if len(summary['values']) > 1000:
            summary['values'] = summary['values'][-1000:]
        
        self._points.append(MetricPoint(
            name=name,
            value=value,
            timestamp=time.time(),
            metric_type=MetricType.SUMMARY,
            labels=labels,
        ))
    
    def get_counter(self, name: str, labels: Optional[Dict[str, str]] = None) -> float:
        """Get current counter value."""
        labels = labels or {}
        key = self._make_key(name, labels)
        return self._counters.get(key, 0.0)
    
    def get_gauge(self, name: str, labels: Optional[Dict[str, str]] = None) -> Optional[float]:
        """Get current gauge value."""
        labels = labels or {}
        key = self._make_key(name, labels)
        return self._gauges.get(key)
    
    def get_histogram_stats(
        self, 
        name: str, 
        labels: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Get histogram statistics."""
        labels = labels or {}
        key = self._make_key(name, labels)
        hist = self._histograms.get(key)
        
        if not hist or hist['count'] == 0:
            return {'count': 0, 'sum': 0, 'avg': 0, 'buckets': []}
        
        avg = hist['sum'] / hist['count']
        
        return {
            'count': hist['count'],
            'sum': hist['sum'],
            'avg': avg,
            'buckets': [
                {'le': b.le, 'count': b.count} 
                for b in hist['buckets']
            ],
            'labels': hist['labels'],
        }
    
    def get_summary_stats(
        self,
        name: str,
        labels: Optional[Dict[str, str]] = None,
        quantiles: List[float] = None,
    ) -> Dict[str, Any]:
        """Get summary statistics including quantiles."""
        labels = labels or {}
        quantiles = quantiles or [0.5, 0.9, 0.95, 0.99]
        
        key = self._make_key(name, labels)
        summary = self._summaries.get(key)
        
        if not summary or summary['count'] == 0:
            return {'count': 0, 'sum': 0, 'avg': 0, 'quantiles': {}}
        
        avg = summary['sum'] / summary['count']
        values = sorted(summary['values'])
        
        # Calculate quantiles
        calculated_quantiles = {}
        for q in quantiles:
            idx = int(q * len(values))
            calculated_quantiles[q] = values[min(idx, len(values) - 1)]
        
        return {
            'count': summary['count'],
            'sum': summary['sum'],
            'avg': avg,
            'quantiles': calculated_quantiles,
            'labels': summary['labels'],
        }
    
    def get_metrics(self) -> List[MetricPoint]:
        """Get all recorded metric points."""
        return self._points.copy()
    
    def get_all_counters(self) -> Dict[str, float]:
        """Get all counter values."""
        return dict(self._counters)
    
    def get_all_gauges(self) -> Dict[str, float]:
        """Get all gauge values."""
        return dict(self._gauges)
    
    def clear(self) -> None:
        """Clear all collected metrics."""
        self._counters.clear()
        self._gauges.clear()
        self._histograms.clear()
        self._summaries.clear()
        self._points.clear()
    
    def export_prometheus(self) -> str:
        """Export metrics in Prometheus text format."""
        lines = []
        
        # Counters
        for key, value in self._counters.items():
            name = key.split('{')[0]
            lines.append(f"# TYPE {name} counter")
            lines.append(f"{key} {value}")

    def export_prometheus(self) -> str:
        """Export metrics in Prometheus text format."""
        lines = []

        # Counters
        for key, value in self._counters.items():
            name = key.split('{')[0]
            lines.append(f"# TYPE {name} counter")
            lines.append(f"{key} {value}")

        # Gauges
        for key, value in self._gauges.items():
            name = key.split('{')[0]
            lines.append(f"# TYPE {name} gauge")
            lines.append(f"{key} {value}")

        # Histograms
        for key, hist in self._histograms.items():
            name = key.split('{')[0]
            lines.append(f"# TYPE {name} histogram")

            cumulative = 0
            for bucket in hist['buckets']:
                cumulative += bucket.count
                label_parts = [f'{k}="{v}"' for k, v in hist['labels'].items()]
                label_str = ','.join(label_parts)
                
                if label_str:
                    lines.append(f'{name}_bucket{{{label_str},le="{bucket.le}"}} {cumulative}')
                else:
                    lines.append(f'{name}_bucket{{le="{bucket.le}"}} {cumulative}')
            
            sum_labels = ','.join(f'{k}="{v}"' for k, v in hist['labels'].items())
            if sum_labels:
                lines.append(f'{name}_sum{{{sum_labels}}} {hist["sum"]}')
                lines.append(f'{name}_count{{{sum_labels}}} {hist["count"]}')
            else:
                lines.append(f'{name}_sum {hist["sum"]}')
                lines.append(f'{name}_count {hist["count"]}')

        return '\n'.join(lines)
