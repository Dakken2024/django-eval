"""
Test builder for rule engine testing.
Provides a fluent interface for building test cases and test suites.
"""
from typing import Dict, List, Any, Optional
from .test_runner import TestCase, TestSuite


class RuleTestBuilder:
    """
    Fluent builder for creating rule test cases and test suites.
    
    Example usage:
        builder = RuleTestBuilder()
        suite = (builder
            .for_rule("my_rule")
            .named("My Test Suite")
            .add_test()
                .named("Test critical alert")
                .with_context({"level": "critical", "app": "order-api"})
                .expects({"should_push": True, "action": "send"})
            .add_test()
                .named("Test remind alert")
                .with_context({"level": "remind", "app": "other"})
                .expects({"should_push": False, "action": "suppress"})
            .build()
        )
    """
    
    def __init__(self):
        self._rule_id = ""
        self._suite_name = "Test Suite"
        self._suite_description = ""
        self._test_cases: List[TestCase] = []
        self._current_test: Optional[Dict[str, Any]] = None
    
    def for_rule(self, rule_id: str) -> 'RuleTestBuilder':
        """Set the rule ID to test."""
        self._rule_id = rule_id
        return self
    
    def named(self, name: str) -> 'RuleTestBuilder':
        """Set the test suite name."""
        self._suite_name = name
        return self
    
    def described_as(self, description: str) -> 'RuleTestBuilder':
        """Set the test suite description."""
        self._suite_description = description
        return self
    
    def add_test(self) -> 'RuleTestBuilder':
        """Start adding a new test case."""
        self._current_test = {
            'name': 'Unnamed Test',
            'context': {},
            'expected_output': {},
            'description': '',
        }
        return self
    
    def named_test(self, name: str) -> 'RuleTestBuilder':
        """Set the current test case name."""
        if self._current_test:
            self._current_test['name'] = name
        return self
    
    def with_context(self, context: Dict[str, Any]) -> 'RuleTestBuilder':
        """Set the context for the current test case."""
        if self._current_test:
            self._current_test['context'] = context
        return self
    
    def expects(self, expected_output: Dict[str, Any]) -> 'RuleTestBuilder':
        """Set the expected output for the current test case."""
        if self._current_test:
            self._current_test['expected_output'] = expected_output
        return self
    
    def described_test(self, description: str) -> 'RuleTestBuilder':
        """Set the description for the current test case."""
        if self._current_test:
            self._current_test['description'] = description
        return self
    
    def end_test(self) -> 'RuleTestBuilder':
        """Finish the current test case and add it to the suite."""
        if self._current_test:
            self._test_cases.append(TestCase(
                name=self._current_test['name'],
                context=self._current_test['context'],
                expected_output=self._current_test['expected_output'],
                description=self._current_test['description'],
            ))
            self._current_test = None
        return self
    
    def add_test_from_dict(self, test_data: Dict[str, Any]) -> 'RuleTestBuilder':
        """Add a test case from a dictionary."""
        self._test_cases.append(TestCase.from_dict(test_data))
        return self
    
    def build(self) -> TestSuite:
        """Build and return the test suite."""
        # End any pending test case
        if self._current_test:
            self.end_test()
        
        suite = TestSuite(
            rule_id=self._rule_id,
            name=self._suite_name,
            test_cases=self._test_cases,
            description=self._suite_description,
        )
        
        return suite
    
    @classmethod
    def from_suite_dict(cls, suite_data: Dict[str, Any]) -> 'RuleTestBuilder':
        """Create a builder from an existing test suite dictionary."""
        builder = cls()
        builder._rule_id = suite_data.get('rule_id', '')
        builder._suite_name = suite_data.get('name', 'Test Suite')
        builder._suite_description = suite_data.get('description', '')
        
        for tc_data in suite_data.get('test_cases', []):
            builder.add_test_from_dict(tc_data)
        
        return builder
