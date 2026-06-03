"""
Workflow Step Types

Specialized step implementations for different workflow patterns.
"""

import concurrent.futures
from typing import Any, Dict, List, Optional, Callable
from .workflow_engine import WorkflowStep, WorkflowContext, StepStatus


class SequentialStep(WorkflowStep):
    """
    A step that executes a single rule sequentially.
    
    This is the most common step type for linear workflows.
    """
    
    def execute(self, context: WorkflowContext, rule_engine: Any) -> Any:
        """Execute the rule and return result."""
        if self.rule_id is None:
            raise ValueError("SequentialStep requires a rule_id")
        
        # Get input from context or use default
        input_data = context.get(f'step_{self.name}_input', context.input_data)
        
        # Evaluate rule
        result = rule_engine.evaluate_rule(self.rule_id, input_data)
        
        # Store result in context for downstream steps
        context.set(f'step_{self.name}_result', result)
        
        return result


class ParallelStep(WorkflowStep):
    """
    A step that executes multiple rules in parallel.
    
    Useful for independent validations that can run concurrently.
    """
    
    def __init__(
        self,
        name: str,
        rule_ids: List[int],
        max_workers: int = 4,
        **kwargs
    ):
        super().__init__(name=name, **kwargs)
        self.rule_ids = rule_ids
        self.max_workers = max_workers
    
    def execute(self, context: WorkflowContext, rule_engine: Any) -> Dict[str, Any]:
        """Execute all rules in parallel."""
        results = {}
        errors = {}
        
        def execute_rule(rule_id: int) -> tuple:
            try:
                result = rule_engine.evaluate_rule(rule_id, context.input_data)
                return (rule_id, result, None)
            except Exception as e:
                return (rule_id, None, e)
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(execute_rule, rid): rid for rid in self.rule_ids}
            
            for future in concurrent.futures.as_completed(futures):
                rule_id, result, error = future.result()
                if error:
                    errors[rule_id] = error
                else:
                    results[rule_id] = result
        
        # Store in context
        context.set(f'step_{self.name}_results', results)
        context.set(f'step_{self.name}_errors', errors)
        
        if errors and len(errors) == len(self.rule_ids):
            raise Exception(f"All parallel rules failed: {list(errors.keys())}")
        
        return {
            'results': results,
            'errors': errors,
            'success_count': len(results),
            'failure_count': len(errors),
        }


class ConditionalStep(WorkflowStep):
    """
    A step that conditionally executes based on a predicate.
    
    The condition is evaluated before attempting to run the rule.
    """
    
    def __init__(
        self,
        name: str,
        rule_id: Optional[int] = None,
        condition: Optional[Callable[[WorkflowContext], bool]] = None,
        else_step: Optional[WorkflowStep] = None,
        **kwargs
    ):
        super().__init__(name=name, rule_id=rule_id, condition=condition, **kwargs)
        self.else_step = else_step
    
    def execute(self, context: WorkflowContext, rule_engine: Any) -> Any:
        """Execute rule if condition is met."""
        if self.rule_id is None:
            raise ValueError("ConditionalStep requires a rule_id")
        
        input_data = context.get(f'step_{self.name}_input', context.input_data)
        result = rule_engine.evaluate_rule(self.rule_id, input_data)
        
        context.set(f'step_{self.name}_result', result)
        context.set(f'step_{self.name}_condition_met', True)
        
        return result
    
    def run(self, context: WorkflowContext, rule_engine: Any) -> Any:
        """Run step with conditional logic."""
        if not self.should_execute(context):
            self.status = StepStatus.SKIPPED
            
            # Execute else step if provided
            if self.else_step:
                return self.else_step.run(context, rule_engine)
            
            return None
        
        return super().run(context, rule_engine)


class LoopStep(WorkflowStep):
    """
    A step that repeats execution based on a condition.
    
    Supports iterating over collections or repeating until a condition is met.
    """
    
    def __init__(
        self,
        name: str,
        rule_id: Optional[int] = None,
        iterate_over: Optional[str] = None,
        max_iterations: int = 100,
        until_condition: Optional[Callable[[WorkflowContext], bool]] = None,
        **kwargs
    ):
        super().__init__(name=name, rule_id=rule_id, **kwargs)
        self.iterate_over = iterate_over  # Context variable to iterate over
        self.max_iterations = max_iterations
        self.until_condition = until_condition
        self.step_results: List[Any] = []
    
    def execute(self, context: WorkflowContext, rule_engine: Any) -> List[Any]:
        """Execute rule in a loop."""
        if self.rule_id is None:
            raise ValueError("LoopStep requires a rule_id")
        
        self.step_results = []
        iteration = 0
        
        # Collection iteration mode
        if self.iterate_over:
            collection = context.get(self.iterate_over, [])
            
            for item in collection:
                if iteration >= self.max_iterations:
                    break
                
                # Set current item in context
                context.set(f'{self.name}_current_item', item)
                context.set(f'{self.name}_iteration', iteration)
                
                # Execute rule
                result = rule_engine.evaluate_rule(self.rule_id, context.input_data)
                self.step_results.append(result)
                
                iteration += 1
        
        # Condition-based repetition mode
        elif self.until_condition:
            while iteration < self.max_iterations:
                context.set(f'{self.name}_iteration', iteration)
                
                # Execute rule
                result = rule_engine.evaluate_rule(self.rule_id, context.input_data)
                self.step_results.append(result)
                
                # Check termination condition
                if self.until_condition(context):
                    break
                
                iteration += 1
        
        # Store results
        context.set(f'step_{self.name}_results', self.step_results)
        context.set(f'step_{self.name}_iterations', iteration)
        
        return self.step_results


class TransformStep(WorkflowStep):
    """
    A step that transforms data before passing to next step.
    
    Useful for data preparation between rule evaluations.
    """
    
    def __init__(
        self,
        name: str,
        transform_fn: Callable[[Dict[str, Any]], Dict[str, Any]],
        **kwargs
    ):
        super().__init__(name=name, **kwargs)
        self.transform_fn = transform_fn
    
    def execute(self, context: WorkflowContext, rule_engine: Any) -> Dict[str, Any]:
        """Apply transformation to context."""
        transformed = self.transform_fn(context.input_data)
        context.set(f'step_{self.name}_transformed', transformed)
        return transformed


class AggregatorStep(WorkflowStep):
    """
    A step that aggregates results from previous steps.
    
    Combines multiple results into a single output.
    """
    
    def __init__(
        self,
        name: str,
        aggregate_fn: Callable[[List[Any]], Any],
        source_steps: Optional[List[str]] = None,
        **kwargs
    ):
        super().__init__(name=name, **kwargs)
        self.aggregate_fn = aggregate_fn
        self.source_steps = source_steps or []
    
    def execute(self, context: WorkflowContext, rule_engine: Any) -> Any:
        """Aggregate results from source steps."""
        results_to_aggregate = []
        
        if self.source_steps:
            for step_name in self.source_steps:
                result = context.get(f'step_{step_name}_result')
                if result is not None:
                    results_to_aggregate.append(result)
        else:
            # Aggregate all step results
            results_to_aggregate = context.results
        
        aggregated = self.aggregate_fn(results_to_aggregate)
        context.set(f'step_{self.name}_aggregated', aggregated)
        
        return aggregated
