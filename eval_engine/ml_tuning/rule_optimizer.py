"""
Rule Optimizer

Uses historical evaluation data to suggest rule optimizations.
"""

import statistics
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict


@dataclass
class RuleStats:
    """Statistics for a single rule."""
    rule_id: int
    evaluation_count: int = 0
    avg_duration_ms: float = 0.0
    p95_duration_ms: float = 0.0
    p99_duration_ms: float = 0.0
    success_rate: float = 1.0
    cache_hit_rate: float = 0.0
    input_fields: List[str] = field(default_factory=list)
    output_complexity: int = 0


@dataclass
class OptimizationResult:
    """Result of rule optimization analysis."""
    rule_id: int
    current_performance_score: float
    optimized_performance_score: float
    improvements: List[str] = field(default_factory=list)
    recommendations: List[Dict[str, Any]] = field(default_factory=list)
    estimated_improvement_pct: float = 0.0


class RuleOptimizer:
    """
    Analyzes rule performance and suggests optimizations.
    
    Uses statistical analysis of historical evaluation data
    to identify bottlenecks and recommend improvements.
    
    Usage:
        optimizer = RuleOptimizer()
        
        # Add evaluation history
        optimizer.add_evaluation(
            rule_id=123,
            duration_ms=45.2,
            success=True,
            cache_hit=False,
            input_data={"amount": 1000}
        )
        
        # Get optimization suggestions
        result = optimizer.analyze_rule(123)
        print(result.recommendations)
    """
    
    def __init__(self):
        self._evaluations: Dict[int, List[Dict]] = defaultdict(list)
        self._rule_stats: Dict[int, RuleStats] = {}
    
    def add_evaluation(
        self,
        rule_id: int,
        duration_ms: float,
        success: bool,
        cache_hit: bool,
        input_data: Optional[Dict] = None,
        output_data: Optional[Any] = None,
    ) -> None:
        """Record an evaluation for analysis."""
        evaluation = {
            'duration_ms': duration_ms,
            'success': success,
            'cache_hit': cache_hit,
            'input_fields': list(input_data.keys()) if input_data else [],
            'output_size': len(str(output_data)) if output_data else 0,
        }
        
        self._evaluations[rule_id].append(evaluation)
        
        # Update stats after every 100 evaluations
        if len(self._evaluations[rule_id]) % 100 == 0:
            self._update_stats(rule_id)
    
    def _update_stats(self, rule_id: int) -> RuleStats:
        """Update statistics for a rule."""
        evals = self._evaluations[rule_id]
        
        if not evals:
            return RuleStats(rule_id=rule_id)
        
        durations = [e['duration_ms'] for e in evals]
        sorted_durations = sorted(durations)
        
        # Calculate percentiles
        p95_idx = int(len(sorted_durations) * 0.95)
        p99_idx = int(len(sorted_durations) * 0.99)
        
        success_count = sum(1 for e in evals if e['success'])
        cache_hit_count = sum(1 for e in evals if e['cache_hit'])
        
        # Collect unique input fields
        all_fields = set()
        for e in evals:
            all_fields.update(e['input_fields'])
        
        avg_output_size = statistics.mean([e['output_size'] for e in evals])
        
        stats = RuleStats(
            rule_id=rule_id,
            evaluation_count=len(evals),
            avg_duration_ms=statistics.mean(durations),
            p95_duration_ms=sorted_durations[p95_idx] if p95_idx < len(sorted_durations) else durations[-1],
            p99_duration_ms=sorted_durations[p99_idx] if p99_idx < len(sorted_durations) else durations[-1],
            success_rate=success_count / len(evals),
            cache_hit_rate=cache_hit_count / len(evals),
            input_fields=list(all_fields),
            output_complexity=int(avg_output_size),
        )
        
        self._rule_stats[rule_id] = stats
        return stats
    
    def analyze_rule(self, rule_id: int) -> OptimizationResult:
        """Analyze a rule and generate optimization recommendations."""
        if rule_id not in self._rule_stats:
            self._update_stats(rule_id)
        
        stats = self._rule_stats.get(rule_id, RuleStats(rule_id=rule_id))
        
        if stats.evaluation_count == 0:
            return OptimizationResult(
                rule_id=rule_id,
                current_performance_score=0,
                optimized_performance_score=0,
                recommendations=[{
                    'type': 'data',
                    'priority': 'low',
                    'message': 'Insufficient data for analysis. Need more evaluations.',
                }]
            )
        
        recommendations = []
        improvements = []
        current_score = self._calculate_performance_score(stats)
        potential_score = current_score
        
        # Check cache hit rate
        if stats.cache_hit_rate < 0.5:
            recommendations.append({
                'type': 'caching',
                'priority': 'high',
                'message': f'Low cache hit rate ({stats.cache_hit_rate:.1%}). Consider enabling or optimizing cache.',
                'action': 'enable_cache',
                'estimated_improvement': (0.5 - stats.cache_hit_rate) * 100,
            })
            improvements.append('Enable caching')
            potential_score += (0.5 - stats.cache_hit_rate) * 20
        
        # Check P95 latency
        if stats.p95_duration_ms > 100:
            recommendations.append({
                'type': 'performance',
                'priority': 'high',
                'message': f'High P95 latency ({stats.p95_duration_ms:.1f}ms). Consider precompilation.',
                'action': 'use_compiled_engine',
                'estimated_improvement': min(50, (stats.p95_duration_ms - 100) / 10),
            })
            improvements.append('Use compiled engine')
            potential_score += min(10, (stats.p95_duration_ms - 100) / 20)
        
        # Check success rate
        if stats.success_rate < 0.99:
            recommendations.append({
                'type': 'reliability',
                'priority': 'critical',
                'message': f'Success rate below 99% ({stats.success_rate:.1%}). Review error logs.',
                'action': 'investigate_errors',
                'estimated_improvement': 0,  # Reliability doesn't improve score directly
            })
            improvements.append('Fix errors')
        
        # Check input complexity
        if len(stats.input_fields) > 20:
            recommendations.append({
                'type': 'complexity',
                'priority': 'medium',
                'message': f'Large number of input fields ({len(stats.input_fields)}). Consider splitting rule.',
                'action': 'split_rule',
                'estimated_improvement': 10,
            })
            improvements.append('Simplify inputs')
            potential_score += 5
        
        # Check P99 vs P95 gap (indicates outliers)
        if stats.p99_duration_ms > stats.p95_duration_ms * 2:
            recommendations.append({
                'type': 'stability',
                'priority': 'medium',
                'message': 'Large gap between P95 and P99. Investigate outlier causes.',
                'action': 'investigate_outliers',
                'estimated_improvement': 5,
            })
            improvements.append('Reduce variance')
            potential_score += 3
        
        estimated_improvement = max(0, ((potential_score - current_score) / current_score) * 100) if current_score > 0 else 0
        
        return OptimizationResult(
            rule_id=rule_id,
            current_performance_score=current_score,
            optimized_performance_score=min(100, potential_score),
            improvements=improvements,
            recommendations=recommendations,
            estimated_improvement_pct=estimated_improvement,
        )
    
    def _calculate_performance_score(self, stats: RuleStats) -> float:
        """Calculate overall performance score (0-100)."""
        if stats.evaluation_count == 0:
            return 0
        
        score = 100.0
        
        # Penalize high latency
        if stats.avg_duration_ms > 50:
            score -= min(30, (stats.avg_duration_ms - 50) / 5)
        
        # Penalize low cache hit rate
        score -= (1 - stats.cache_hit_rate) * 15
        
        # Penalize low success rate
        score -= (1 - stats.success_rate) * 20
        
        # Penalize high complexity
        if stats.output_complexity > 1000:
            score -= min(10, (stats.output_complexity - 1000) / 500)
        
        return max(0, min(100, score))
    
    def get_all_stats(self) -> Dict[int, RuleStats]:
        """Get statistics for all rules."""
        # Update all stats first
        for rule_id in self._evaluations:
            self._update_stats(rule_id)
        return dict(self._rule_stats)
    
    def get_slow_rules(self, threshold_ms: float = 100) -> List[Tuple[int, float]]:
        """Get rules with average duration above threshold."""
        stats = self.get_all_stats()
        slow_rules = [
            (rule_id, s.avg_duration_ms)
            for rule_id, s in stats.items()
            if s.avg_duration_ms > threshold_ms
        ]
        return sorted(slow_rules, key=lambda x: x[1], reverse=True)
    
    def get_unreliable_rules(self, threshold: float = 0.99) -> List[Tuple[int, float]]:
        """Get rules with success rate below threshold."""
        stats = self.get_all_stats()
        unreliable_rules = [
            (rule_id, s.success_rate)
            for rule_id, s in stats.items()
            if s.success_rate < threshold
        ]
        return sorted(unreliable_rules, key=lambda x: x[1])
