"""
Distributed Tracing for Rule Evaluation

Integrates with OpenTelemetry to provide distributed tracing.
"""

import time
from typing import Any, Dict, Optional, ContextManager
from contextlib import contextmanager
from dataclasses import dataclass


@dataclass
class SpanData:
    """Data associated with a tracing span."""
    trace_id: str
    span_id: str
    name: str
    start_time: float
    end_time: Optional[float] = None
    attributes: Dict[str, Any] = None
    status: str = "OK"
    error: Optional[str] = None
    
    def __post_init__(self):
        if self.attributes is None:
            self.attributes = {}
    
    @property
    def duration_ms(self) -> float:
        """Calculate span duration in milliseconds."""
        if self.end_time is None:
            return 0.0
        return (self.end_time - self.start_time) * 1000


class RuleTracer:
    """
    OpenTelemetry-based tracer for rule evaluation.
    
    Provides distributed tracing for rule evaluations, workflows,
    and cache operations.
    
    Usage:
        tracer = RuleTracer(service_name="rule-engine")
        
        with tracer.trace("evaluate_rule", attributes={"rule_id": 123}) as span:
            result = engine.evaluate(rule_id, data)
            span.set_attribute("result", result)
    
    If OpenTelemetry is not installed, falls back to no-op implementation.
    """
    
    def __init__(
        self,
        service_name: str = "django-eval",
        enabled: bool = True,
        sampling_rate: float = 1.0,
    ):
        self.service_name = service_name
        self.enabled = enabled
        self.sampling_rate = sampling_rate
        self._tracer = None
        self._spans: list = []
        
        # Try to initialize OpenTelemetry
        self._init_otel()
    
    def _init_otel(self) -> None:
        """Initialize OpenTelemetry if available."""
        try:
            from opentelemetry import trace
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import (
                BatchSpanProcessor,
                ConsoleSpanExporter,
            )
            
            provider = TracerProvider()
            processor = BatchSpanProcessor(ConsoleSpanExporter())
            provider.add_span_processor(processor)
            trace.set_tracer_provider(provider)
            
            self._tracer = trace.get_tracer(self.service_name)
            
        except ImportError:
            # OpenTelemetry not installed, use no-op
            self._tracer = None
    
    @contextmanager
    def trace(
        self,
        name: str,
        attributes: Optional[Dict[str, Any]] = None,
        parent: Optional[Any] = None,
    ):
        """
        Create a tracing span for an operation.
        
        Args:
            name: Span name (e.g., "evaluate_rule", "cache_lookup")
            attributes: Additional attributes to attach to span
            parent: Parent span context (for nested spans)
            
        Yields:
            SpanData object for recording additional information
        """
        if not self.enabled:
            yield SpanData("", "", name, time.time())
            return
        
        # Check sampling
        import random
        if random.random() > self.sampling_rate:
            yield SpanData("", "", name, time.time())
            return
        
        span_data = SpanData(
            trace_id="",
            span_id="",
            name=name,
            start_time=time.time(),
            attributes=attributes or {},
        )
        
        if self._tracer:
            try:
                # Use OpenTelemetry tracer
                with self._tracer.start_as_current_span(
                    name,
                    attributes=span_data.attributes,
                ) as span:
                    span_data.trace_id = span.get_span_context().trace_id
                    span_data.span_id = span.get_span_context().span_id
                    
                    yield span_data
                    
                    span_data.end_time = time.time()
                    
                    if span_data.error:
                        span.set_status(trace.Status(trace.StatusCode.ERROR, span_data.error))
                        
            except Exception as e:
                span_data.status = "ERROR"
                span_data.error = str(e)
                span_data.end_time = time.time()
                raise
        else:
            # Fallback: manual span tracking
            import uuid
            span_data.trace_id = str(uuid.uuid4())
            span_data.span_id = str(uuid.uuid4())
            
            try:
                yield span_data
                span_data.status = "OK"
            except Exception as e:
                span_data.status = "ERROR"
                span_data.error = str(e)
                raise
            finally:
                span_data.end_time = time.time()
                self._spans.append(span_data)
    
    def record_evaluation(
        self,
        rule_id: int,
        rule_name: str,
        duration_ms: float,
        success: bool,
        error: Optional[str] = None,
        input_size: int = 0,
        output_size: int = 0,
    ) -> None:
        """Record a rule evaluation metric."""
        attributes = {
            "rule.id": rule_id,
            "rule.name": rule_name,
            "evaluation.success": success,
            "evaluation.duration_ms": duration_ms,
            "input.size_bytes": input_size,
            "output.size_bytes": output_size,
        }
        
        if error:
            attributes["error.message"] = error
        
        # Record as span
        with self.trace("rule_evaluation", attributes=attributes) as span:
            span.end_time = span.start_time + (duration_ms / 1000.0)
            if error:
                span.status = "ERROR"
                span.error = error
    
    def record_cache_operation(
        self,
        operation: str,
        key: str,
        hit: bool,
        duration_ms: float,
    ) -> None:
        """Record a cache operation metric."""
        attributes = {
            "cache.operation": operation,
            "cache.key": key,
            "cache.hit": hit,
            "cache.duration_ms": duration_ms,
        }
        
        with self.trace("cache_operation", attributes=attributes) as span:
            span.end_time = span.start_time + (duration_ms / 1000.0)
    
    def get_spans(self) -> list:
        """Get all recorded spans (for testing/debugging)."""
        return self._spans.copy()
    
    def clear_spans(self) -> None:
        """Clear recorded spans."""
        self._spans.clear()


class TracingContextManager:
    """
    Manages tracing context across rule evaluations.
    
    Propagates trace IDs through the evaluation chain.
    """
    
    def __init__(self, tracer: RuleTracer):
        self.tracer = tracer
        self._current_trace_id: Optional[str] = None
    
    def start_trace(self, trace_id: Optional[str] = None) -> str:
        """Start a new trace context."""
        import uuid
        self._current_trace_id = trace_id or str(uuid.uuid4())
        return self._current_trace_id
    
    def get_trace_id(self) -> Optional[str]:
        """Get current trace ID."""
        return self._current_trace_id
    
    def inject_context(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Inject tracing context into evaluation context."""
        if self._current_trace_id:
            context['_trace_id'] = self._current_trace_id
        return context
    
    def extract_context(self, context: Dict[str, Any]) -> None:
        """Extract tracing context from evaluation context."""
        trace_id = context.get('_trace_id')
        if trace_id:
            self._current_trace_id = trace_id
