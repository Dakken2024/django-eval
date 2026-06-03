"""
Test runner for rule engine testing.
Provides utilities for running test suites and collecting results.
"""
import time
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from datetime import datetime


@dataclass
class TestCase:
    """A single test case for a rule."""
    name: str
    context: Dict[str, Any]
    expected_output: Dict[str, Any]
    description: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'context': self.context,
            'expected_output': self.expected_output,
            'description': self.description,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TestCase':
        return cls(
            name=data.get('name', 'Unnamed'),
            context=data.get('context', {}),
            expected_output=data.get('expected_output', {}),
            description=data.get('description', ''),
        )


@dataclass
class TestResult:
    """Result of a single test case execution."""
    test_case: TestCase
    passed: bool
    actual_output: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    execution_time_ms: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'test_name': self.test_case.name,
            'passed': self.passed,
            'actual_output': self.actual_output,
            'error_message': self.error_message,
            'execution_time_ms': round(self.execution_time_ms, 3),
        }


@dataclass
class TestSuite:
    """A collection of test cases for a rule."""
    rule_id: str
    name: str
    test_cases: List[TestCase] = field(default_factory=list)
    description: str = ""
    
    def add_test(self, test_case: TestCase):
        """Add a test case to the suite."""
        self.test_cases.append(test_case)
        return self
    
    def add_test_from_dict(self, data: Dict[str, Any]):
        """Add a test case from dictionary."""
        self.test_cases.append(TestCase.from_dict(data))
        return self
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'rule_id': self.rule_id,
            'name': self.name,
            'description': self.description,
            'test_cases': [tc.to_dict() for tc in self.test_cases],
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TestSuite':
        suite = cls(
            rule_id=data.get('rule_id', ''),
            name=data.get('name', 'Unnamed Suite'),
            description=data.get('description', ''),
        )
        for tc_data in data.get('test_cases', []):
            suite.add_test_from_dict(tc_data)
        return suite


@dataclass
class TestSuiteResult:
    """Result of a test suite execution."""
    test_suite: TestSuite
    total_tests: int
    passed_count: int
    failed_count: int
    results: List[TestResult] = field(default_factory=list)
    total_execution_time_ms: float = 0.0
    executed_at: str = ""
    
    @property
    def pass_rate(self) -> float:
        if self.total_tests == 0:
            return 0.0
        return (self.passed_count / self.total_tests) * 100
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'rule_id': self.test_suite.rule_id,
            'suite_name': self.test_suite.name,
            'total_tests': self.total_tests,
            'passed_count': self.passed_count,
            'failed_count': self.failed_count,
            'pass_rate': round(self.pass_rate, 2),
            'total_execution_time_ms': round(self.total_execution_time_ms, 3),
            'executed_at': self.executed_at,
            'results': [r.to_dict() for r in self.results],
        }


class RuleTestRunner:
    """
    Runner for rule test suites.
    Executes test cases against a rule and collects results.
    """
    
    def __init__(self, engine):
        """
        Initialize the test runner.
        
        Args:
            engine: The rule engine instance to use for evaluation
        """
        self.engine = engine
    
    def run_test_case(self, test_case: TestCase, rule_id: str) -> TestResult:
        """
        Run a single test case.
        
        Args:
            test_case: The test case to run
            rule_id: The rule ID to test against
            
        Returns:
            TestResult with pass/fail status
        """
        start_time = time.time()
        try:
            result = self.engine.evaluate(rule_id, test_case.context)
            execution_time_ms = (time.time() - start_time) * 1000
            
            # Compare outputs
            actual_output = result.to_dict() if hasattr(result, 'to_dict') else result
            
            passed = self._compare_outputs(actual_output, test_case.expected_output)
            
            return TestResult(
                test_case=test_case,
                passed=passed,
                actual_output=actual_output,
                execution_time_ms=execution_time_ms,
            )
        except Exception as e:
            execution_time_ms = (time.time() - start_time) * 1000
            return TestResult(
                test_case=test_case,
                passed=False,
                error_message=str(e),
                execution_time_ms=execution_time_ms,
            )
    
    def _compare_outputs(self, actual: Dict[str, Any], expected: Dict[str, Any]) -> bool:
        """
        Compare actual output with expected output.
        
        Args:
            actual: Actual output from rule evaluation
            expected: Expected output
            
        Returns:
            True if outputs match, False otherwise
        """
        # Check all expected keys
        for key, expected_value in expected.items():
            if key not in actual:
                return False
            
            actual_value = actual.get(key)
            
            # Handle nested dicts
            if isinstance(expected_value, dict) and isinstance(actual_value, dict):
                if not self._compare_outputs(actual_value, expected_value):
                    return False
            elif actual_value != expected_value:
                return False
        
        return True
    
    def run_test_suite(self, test_suite: TestSuite) -> TestSuiteResult:
        """
        Run a complete test suite.
        
        Args:
            test_suite: The test suite to run
            
        Returns:
            TestSuiteResult with aggregated results
        """
        results = []
        passed_count = 0
        failed_count = 0
        total_start_time = time.time()
        
        for test_case in test_suite.test_cases:
            result = self.run_test_case(test_case, test_suite.rule_id)
            results.append(result)
            
            if result.passed:
                passed_count += 1
            else:
                failed_count += 1
        
        total_execution_time_ms = (time.time() - total_start_time) * 1000
        
        return TestSuiteResult(
            test_suite=test_suite,
            total_tests=len(test_suite.test_cases),
            passed_count=passed_count,
            failed_count=failed_count,
            results=results,
            total_execution_time_ms=total_execution_time_ms,
            executed_at=datetime.now().isoformat(),
        )
    
    def run_test_suite_from_dict(self, test_suite_data: Dict[str, Any]) -> TestSuiteResult:
        """
        Run a test suite from dictionary data.
        
        Args:
            test_suite_data: Dictionary containing test suite definition
            
        Returns:
            TestSuiteResult with aggregated results
        """
        test_suite = TestSuite.from_dict(test_suite_data)
        return self.run_test_suite(test_suite)
