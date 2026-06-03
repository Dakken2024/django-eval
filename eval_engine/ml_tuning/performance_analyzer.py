"""
Performance Analyzer for Rule Evaluation

Analyzes rule performance and provides tuning recommendations.
"""

import statistics
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict
import time


@dataclass
class TuningRecommendation:
    """A performance tuning recommendation."""
    category: str
    priority: str  # 'low', 'medium', 'high', 'critical'
    title: str
    description: str
    action: str
    estimated_improvement_pct: float
    effort: str  # 'low', 'medium', 'high'


class PerformanceAnalyzer:
    """
    Analyzes rule evaluation performance and suggests optimizations.
    
    Provides actionable recommendations based on profiling data.
    
    Usage:
        analyzer = PerformanceAnalyzer()
        
        # Add profiling data
        analyzer.add_profiling_data(
            rule_id=123,
            duration_ms=45.2,
            cache_hit=False,
            engine_type='simple',
            expression_count=5
        )
        
        # Get recommendations
        recommendations = analyzer.analyze(rule_id=123)
    """
    
    def __init__(self):
        self._profiling_data: Dict[int, List[Dict]] = defaultdict(list)
    
    def add_profiling_data(
        self,
        rule_id: int,
        duration_ms: float,
        cache_hit: bool,
        engine_type: str,
        expression_count: int = 0,
        input_size_bytes: int = 0,
        output_size_bytes: int = 0,
    ) -> None:
        """Add profiling data point."""
        self._profiling_data[rule_id].append({
            'timestamp': time.time(),
            'duration_ms': duration_ms,
            'cache_hit': cache_hit,
            'engine_type': engine_type,
            'expression_count': expression_count,
            'input_size_bytes': input_size_bytes,
            'output_size_bytes': output_size_bytes,
        })
    
    def analyze(
        self, 
        rule_id: Optional[int] = None,
        threshold_ms: float = 50.0,
    ) -> Dict[int, List[TuningRecommendation]]:
        """
        Analyze performance and generate recommendations.
        
        Returns dict mapping rule_id to list of recommendations.
        """
        results = {}
        
        if rule_id is not None:
            results[rule_id] = self._analyze_rule(rule_id, threshold_ms)
        else:
            for rid in self._profiling_data.keys():
                results[rid] = self._analyze_rule(rid, threshold_ms)
        
        return results
    
    def _analyze_rule(self, rule_id: int, threshold_ms: float) -> List[TuningRecommendation]:
        """Analyze a single rule's performance."""
        data = self._profiling_data.get(rule_id, [])
        
        if len(data) < 10:
            return [TuningRecommendation(
                category='data',
                priority='low',
                title='Insufficient Data',
                description='Need more profiling data for accurate analysis',
                action='Continue collecting profiling data',
                estimated_improvement_pct=0,
                effort='low',
            )]
        
        recommendations = []
        
        durations = [d['duration_ms'] for d in data]
        avg_duration = statistics.mean(durations)
        p95_duration = sorted(durations)[int(len(durations) * 0.95)]
        
        cache_hits = sum(1 for d in data if d['cache_hit'])
        cache_hit_rate = cache_hits / len(data)
        
        engine_types = set(d['engine_type'] for d in data)
        
        # Check latency
        if avg_duration > threshold_ms:
            priority = 'high' if avg_duration > threshold_ms * 2 else 'medium'
            
            if 'compiled' not in engine_types:
                recommendations.append(TuningRecommendation(
                    category='performance',
                    priority=priority,
                    title='Enable Precompilation',
                    description=f'Average latency {avg_duration:.1f}ms exceeds threshold {threshold_ms}ms',
                    action='Switch to compiled rule engine for this rule',
                    estimated_improvement_pct=min(60, (avg_duration - threshold_ms) / avg_duration * 100),
                    effort='low',
                ))
            else:
                recommendations.append(TuningRecommendation(
                    category='performance',
                    priority=priority,
                    title='Optimize Expression',
                    description=f'Compiled engine still slow ({avg_duration:.1f}ms). Review expression complexity.',
                    action='Simplify rule expressions or split into multiple rules',
                    estimated_improvement_pct=30,
                    effort='medium',
                ))
        
        # Check cache effectiveness
        if cache_hit_rate < 0.5:
            recommendations.append(TuningRecommendation(
                category='caching',
                priority='high' if cache_hit_rate < 0.2 else 'medium',
                title='Improve Cache Hit Rate',
                description=f'Cache hit rate is only {cache_hit_rate:.1%}',
                action='Review cache key strategy and TTL settings',
                estimated_improvement_pct=(0.8 - cache_hit_rate) * 40,
                effort='medium',
            ))
        
        # Check expression complexity
        expr_counts = [d['expression_count'] for d in data if d['expression_count'] > 0]
        if expr_counts and statistics.mean(expr_counts) > 10:
            recommendations.append(TuningRecommendation(
                category='complexity',
                priority='medium',
                title='Reduce Expression Complexity',
                description=f'High expression count ({statistics.mean(expr_counts):.0f} avg)',
                action='Consider splitting rule or using decision table format',
                estimated_improvement_pct=20,
                effort='high',
            ))
        
        # Check P95 vs average gap (variance)
        if p95_duration > avg_duration * 2:
            recommendations.append(TuningRecommendation(
                category='stability',
                priority='medium',
                title='Reduce Latency Variance',
                description=f'P95 ({p95_duration:.1f}ms) is much higher than average ({avg_duration:.1f}ms)',
                action='Investigate outlier causes: GC, network, lock contention',
                estimated_improvement_pct=15,
                effort='high',
            ))
        
        # Check input size impact
        input_sizes = [d['input_size_bytes'] for d in data]
        if input_sizes and statistics.mean(input_sizes) > 10000:
            recommendations.append(TuningRecommendation(
                category='efficiency',
                priority='low',
                title='Large Input Data',
                description=f'Average input size is {statistics.mean(input_sizes):.0f} bytes',
                action='Consider passing only necessary fields to rule',
                estimated_improvement_pct=10,
                effort='medium',
            ))
        
        return recommendations
    
    def get_performance_summary(self, rule_id: int) -> Dict[str, Any]:
        """Get performance summary for a rule."""
        data = self._profiling_data.get(rule_id, [])
        
        if not data:
            return {'error': 'No data available'}
        
        durations = [d['duration_ms'] for d in data]
        sorted_durations = sorted(durations)
        
        cache_hits = sum(1 for d in data if d['cache_hit'])
        
        return {
            'rule_id': rule_id,
            'sample_count': len(data),
            'duration': {
                'min_ms': min(durations),
                'max_ms': max(durations),
                'avg_ms': statistics.mean(durations),
                'median_ms': statistics.median(durations),
                'p95_ms': sorted_durations[int(len(sorted_durations) * 0.95)],
                'p99_ms': sorted_durations[int(len(sorted_durations) * 0.99)] if len(sorted_durations) > 100 else sorted_durations[-1],
                'stdev_ms': statistics.stdev(durations) if len(durations) > 1 else 0,
            },
            'cache': {
                'hit_rate': cache_hits / len(data),
                'hits': cache_hits,
                'misses': len(data) - cache_hits,
            },
            'engine_distribution': self._get_engine_distribution(data),
        }
    
    def _get_engine_distribution(self, data: List[Dict]) -> Dict[str, int]:
        """Get distribution of engine types used."""
        distribution = defaultdict(int)
        for d in data:
            distribution[d['engine_type']] += 1
        return dict(distribution)
    
    def compare_rules(self, rule_ids: List[int]) -> Dict[str, Any]:
        """Compare performance across multiple rules."""
        summaries = {}
        
        for rid in rule_ids:
            summary = self.get_performance_summary(rid)
            if 'error' not in summary:
                summaries[rid] = summary
        
        if not summaries:
            return {'error': 'No valid data for comparison'}
        
        # Find best and worst performers
        avg_durations = [(rid, s['duration']['avg_ms']) for rid, s in summaries.items()]
        avg_durations.sort(key=lambda x: x[1])
        
        return {
            'comparison': summaries,
            'fastest_rule': avg_durations[0][0] if avg_durations else None,
            'slowest_rule': avg_durations[-1][0] if avg_durations else None,
            'ranking': [rid for rid, _ in avg_durations],
        }
    
    def export_report(self, rule_ids: Optional[List[int]] = None) -> str:
        """Export performance report as markdown."""
        if rule_ids is None:
            rule_ids = list(self._profiling_data.keys())
        
        lines = ['# Rule Performance Report\n']
        
        for rid in rule_ids:
            summary = self.get_performance_summary(rid)
            
            if 'error' in summary:
                continue
            
            lines.append(f'## Rule {rid}\n')
            lines.append(f"**Samples:** {summary['sample_count']}\n")
            lines.append(f"**Avg Latency:** {summary['duration']['avg_ms']:.2f}ms\n")
            lines.append(f"**P95 Latency:** {summary['duration']['p95_ms']:.2f}ms\n")
            lines.append(f"**Cache Hit Rate:** {summary['cache']['hit_rate']:.1%}\n")
            lines.append('')
        
        return '\n'.join(lines)
