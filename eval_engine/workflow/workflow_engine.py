"""
Workflow Engine Core

Core classes for rule workflow execution.
"""

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable, Union
from enum import Enum


class StepStatus(Enum):
    """Status of a workflow step."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class WorkflowContext:
    """
    Context passed through workflow execution.
    
    Contains input data, intermediate results, and metadata.
    """
    workflow_id: str
    input_data: Dict[str, Any]
    variables: Dict[str, Any] = field(default_factory=dict)
    results: List[Any] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    start_time: float = field(default_factory=time.time)
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get variable from context."""
        return self.variables.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        """Set variable in context."""
        self.variables[key] = value
    
    def add_result(self, result: Any) -> None:
        """Add execution result."""
        self.results.append(result)


@dataclass
class WorkflowResult:
    """Result of workflow execution."""
    workflow_id: str
    success: bool
    output: Any
    context: WorkflowContext
    execution_time_ms: float
    steps_executed: int
    steps_failed: int
    error: Optional[str] = None


class WorkflowStep:
    """
    Base class for workflow steps.
    
    A step represents a single unit of work in a workflow.
    """
    
    def __init__(
        self,
        name: str,
        rule_id: Optional[int] = None,
        condition: Optional[Callable[[WorkflowContext], bool]] = None,
        on_success: Optional[Callable[[WorkflowContext, Any], None]] = None,
        on_failure: Optional[Callable[[WorkflowContext, Exception], None]] = None,
    ):
        self.name = name
        self.rule_id = rule_id
        self.condition = condition
        self.on_success = on_success
        self.on_failure = on_failure
        self.status = StepStatus.PENDING
        self.result: Any = None
        self.error: Optional[Exception] = None
    
    def should_execute(self, context: WorkflowContext) -> bool:
        """Check if step should execute based on condition."""
        if self.condition is None:
            return True
        try:
            return self.condition(context)
        except Exception:
            return False
    
    def execute(self, context: WorkflowContext, rule_engine: Any) -> Any:
        """
        Execute the step.
        
        Args:
            context: Workflow context
            rule_engine: Rule engine instance to evaluate rules
            
        Returns:
            Step execution result
        """
        raise NotImplementedError("Subclasses must implement execute()")
    
    def run(self, context: WorkflowContext, rule_engine: Any) -> Any:
        """Run step with status tracking."""
        if not self.should_execute(context):
            self.status = StepStatus.SKIPPED
            return None
        
        self.status = StepStatus.RUNNING
        
        try:
            result = self.execute(context, rule_engine)
            self.result = result
            self.status = StepStatus.COMPLETED
            
            if self.on_success:
                self.on_success(context, result)
            
            return result
            
        except Exception as e:
            self.error = e
            self.status = StepStatus.FAILED
            
            if self.on_failure:
                self.on_failure(context, e)
            
            raise


class RuleWorkflow:
    """
    Orchestrates execution of multiple rules in a workflow.
    
    Supports sequential, parallel, conditional, and loop patterns.
    
    Usage:
        workflow = RuleWorkflow(name="loan_approval")
        workflow.add_step(SequentialStep("check_credit", rule_id=1))
        workflow.add_step(SequentialStep("check_income", rule_id=2))
        workflow.add_step(ConditionalStep(
            "high_value_review",
            rule_id=3,
            condition=lambda ctx: ctx.get('loan_amount', 0) > 100000
        ))
        
        result = workflow.execute(context, rule_engine)
    """
    
    def __init__(
        self,
        name: str,
        description: str = "",
        timeout_ms: int = 30000,
        stop_on_failure: bool = False,
    ):
        self.name = name
        self.description = description
        self.timeout_ms = timeout_ms
        self.stop_on_failure = stop_on_failure
        self.steps: List[WorkflowStep] = []
        self.workflow_id: str = str(uuid.uuid4())
    
    def add_step(self, step: WorkflowStep) -> 'RuleWorkflow':
        """Add a step to the workflow."""
        self.steps.append(step)
        return self
    
    def add_steps(self, *steps: WorkflowStep) -> 'RuleWorkflow':
        """Add multiple steps to the workflow."""
        self.steps.extend(steps)
        return self
    
    def execute(
        self, 
        context: WorkflowContext, 
        rule_engine: Any
    ) -> WorkflowResult:
        """
        Execute the workflow.
        
        Args:
            context: Initial workflow context
            rule_engine: Rule engine instance
            
        Returns:
            WorkflowResult with execution outcomes
        """
        start_time = time.time()
        steps_executed = 0
        steps_failed = 0
        final_output = None
        
        try:
            for step in self.steps:
                # Check timeout
                elapsed_ms = (time.time() - start_time) * 1000
                if elapsed_ms > self.timeout_ms:
                    raise TimeoutError(f"Workflow timeout after {elapsed_ms:.0f}ms")
                
                try:
                    result = step.run(context, rule_engine)
                    steps_executed += 1
                    
                    if step.status == StepStatus.COMPLETED:
                        context.add_result(result)
                        final_output = result
                    elif step.status == StepStatus.FAILED:
                        steps_failed += 1
                        if self.stop_on_failure:
                            break
                            
                except Exception as e:
                    steps_failed += 1
                    if self.stop_on_failure:
                        raise
            
            execution_time_ms = (time.time() - start_time) * 1000
            
            return WorkflowResult(
                workflow_id=self.workflow_id,
                success=steps_failed == 0,
                output=final_output,
                context=context,
                execution_time_ms=execution_time_ms,
                steps_executed=steps_executed,
                steps_failed=steps_failed,
            )
            
        except Exception as e:
            execution_time_ms = (time.time() - start_time) * 1000
            
            return WorkflowResult(
                workflow_id=self.workflow_id,
                success=False,
                output=None,
                context=context,
                execution_time_ms=execution_time_ms,
                steps_executed=steps_executed,
                steps_failed=steps_failed,
                error=str(e),
            )
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize workflow definition to dictionary."""
        return {
            'workflow_id': self.workflow_id,
            'name': self.name,
            'description': self.description,
            'timeout_ms': self.timeout_ms,
            'stop_on_failure': self.stop_on_failure,
            'steps': [
                {
                    'name': step.name,
                    'type': step.__class__.__name__,
                    'rule_id': step.rule_id,
                }
                for step in self.steps
            ],
        }
