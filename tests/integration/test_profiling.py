"""
Integration tests for performance profiling.
"""
import pytest
from django.test import TestCase

from eval_engine.profiling import RulePerformanceProfiler, PerformanceMetrics


class ProfilingIntegrationTestCase(TestCase):
    """Test case for performance profiling integration."""
    
    def setUp(self):
        self.profiler = RulePerformanceProfiler()
        self.profiler.reset()
    
    def test_record_metrics(self):
        """Test recording evaluation metrics."""
        self.profiler.record('test_rule', 50.0, is_success=True)
        self.profiler.record('test_rule', 60.0, is_success=True)
        self.profiler.record('test_rule', 100.0, is_success=False, error_type='TimeoutError')
        
        metrics = self.profiler.get_metrics('test_rule')
        
        assert metrics.call_count == 3
        assert metrics.success_count == 2
        assert metrics.error_count == 1
        assert metrics.success_rate == pytest.approx(66.67, rel=0.1)
        assert metrics.error_rate == pytest.approx(33.33, rel=0.1)
    
    def test_percentile_calculations(self):
        """Test P50/P90/P99 calculations."""
        # Record 100 samples with known values
        for i in range(100):
            self.profiler.record('percentile_test', float(i + 1), is_success=True)
        
        metrics = self.profiler.get_metrics('percentile_test')
        
        assert metrics.p50_latency_ms == pytest.approx(50.0, abs=1.0)
        assert metrics.p90_latency_ms == pytest.approx(90.0, abs=1.0)
        assert metrics.p99_latency_ms == pytest.approx(99.0, abs=1.0)
    
    def test_slow_rules_detection(self):
        """Test detection of slow rules."""
        # Reset to ensure clean state
        self.profiler.reset()
        
        # Fast rule
        for _ in range(10):
            self.profiler.record('fast_rule', 10.0, is_success=True)
        
        # Slow rule
        for _ in range(10):
            self.profiler.record('slow_rule', 200.0, is_success=True)
        
        slow_rules = self.profiler.get_slow_rules(threshold_ms=100.0)
        
        # Filter to only the slow_rule
        slow_rule_ids = [r['rule_id'] for r in slow_rules]
        assert 'slow_rule' in slow_rule_ids
        assert 'fast_rule' not in slow_rule_ids
    
    def test_global_metrics(self):
        """Test global aggregated metrics."""
        # Reset to ensure clean state
        self.profiler.reset()
        
        self.profiler.record('rule_a', 50.0, is_success=True)
        self.profiler.record('rule_b', 75.0, is_success=True)
        self.profiler.record('rule_c', 100.0, is_success=False)
        
        global_metrics = self.profiler.get_global_metrics()
        
        assert global_metrics.call_count == 3
        assert global_metrics.success_count == 2
        assert global_metrics.error_count == 1
    
    def test_export_stats(self):
        """Test exporting statistics."""
        self.profiler.record('export_test', 45.0, is_success=True)
        
        stats = self.profiler.export_stats()
        
        assert 'global' in stats
        assert 'rules' in stats
        assert 'slow_rules' in stats
        assert 'export_test' in stats['rules']
    
    def test_singleton_pattern(self):
        """Test that profiler follows singleton pattern."""
        profiler1 = RulePerformanceProfiler()
        profiler2 = RulePerformanceProfiler()
        
        assert profiler1 is profiler2
    
    def test_reset_specific_rule(self):
        """Test resetting metrics for a specific rule."""
        self.profiler.record('rule_x', 50.0, is_success=True)
        self.profiler.record('rule_y', 60.0, is_success=True)
        
        self.profiler.reset(rule_id='rule_x')
        
        metrics_x = self.profiler.get_metrics('rule_x')
        metrics_y = self.profiler.get_metrics('rule_y')
        
        assert metrics_x.call_count == 0
        assert metrics_y.call_count == 1
