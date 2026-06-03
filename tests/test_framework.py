"""Tests for test framework functionality."""
import pytest
from eval_engine.test_framework import RuleTestRunner, TestCase, TestSuite, TestResult, RuleTestBuilder


class TestTestCase:
    """Test cases for TestCase class."""
    
    def test_create_test_case(self):
        """Test creating a test case."""
        tc = TestCase(
            name='Test 1',
            context={'level': 'critical'},
            expected_output={'should_push': True},
            description='Test description'
        )
        
        assert tc.name == 'Test 1'
        assert tc.context == {'level': 'critical'}
        assert tc.expected_output == {'should_push': True}
    
    def test_test_case_to_dict(self):
        """Test converting test case to dictionary."""
        tc = TestCase(
            name='Test 1',
            context={'level': 'critical'},
            expected_output={'should_push': True},
        )
        data = tc.to_dict()
        
        assert data['name'] == 'Test 1'
        assert data['context'] == {'level': 'critical'}
    
    def test_test_case_from_dict(self):
        """Test creating test case from dictionary."""
        data = {
            'name': 'From Dict',
            'context': {'app': 'test'},
            'expected_output': {'action': 'send'},
            'description': 'Created from dict'
        }
        tc = TestCase.from_dict(data)
        
        assert tc.name == 'From Dict'
        assert tc.description == 'Created from dict'


class TestTestSuite:
    """Test cases for TestSuite class."""
    
    def test_create_test_suite(self):
        """Test creating a test suite."""
        suite = TestSuite(
            rule_id='rule_001',
            name='My Suite',
            description='Test suite'
        )
        
        assert suite.rule_id == 'rule_001'
        assert suite.name == 'My Suite'
        assert len(suite.test_cases) == 0
    
    def test_add_test_to_suite(self):
        """Test adding test cases to suite."""
        suite = TestSuite(rule_id='rule_001', name='Suite')
        tc = TestCase(name='Test 1', context={}, expected_output={})
        suite.add_test(tc)
        
        assert len(suite.test_cases) == 1
    
    def test_add_test_from_dict(self):
        """Test adding test case from dictionary."""
        suite = TestSuite(rule_id='rule_001', name='Suite')
        suite.add_test_from_dict({
            'name': 'Dict Test',
            'context': {'x': 1},
            'expected_output': {'y': 2}
        })
        
        assert len(suite.test_cases) == 1
        assert suite.test_cases[0].name == 'Dict Test'
    
    def test_suite_to_dict(self):
        """Test converting suite to dictionary."""
        suite = TestSuite(rule_id='rule_001', name='Suite')
        suite.add_test(TestCase(name='T1', context={}, expected_output={}))
        data = suite.to_dict()
        
        assert data['rule_id'] == 'rule_001'
        assert len(data['test_cases']) == 1


class TestRuleTestBuilder:
    """Test cases for RuleTestBuilder class."""
    
    def test_builder_fluent_interface(self):
        """Test builder fluent interface."""
        suite = (RuleTestBuilder()
            .for_rule('test_rule')
            .named('Built Suite')
            .add_test()
                .named_test('Test A')
                .with_context({'level': 'high'})
                .expects({'action': 'alert'})
            .end_test()
            .build()
        )
        
        assert suite.rule_id == 'test_rule'
        assert suite.name == 'Built Suite'
        assert len(suite.test_cases) == 1
        assert suite.test_cases[0].name == 'Test A'
    
    def test_builder_multiple_tests(self):
        """Test builder with multiple tests."""
        suite = (RuleTestBuilder()
            .for_rule('multi_rule')
            .named('Multi Test')
            .add_test()
                .named_test('Test 1')
                .with_context({'x': 1})
                .expects({'y': 2})
            .end_test()
            .add_test()
                .named_test('Test 2')
                .with_context({'a': 3})
                .expects({'b': 4})
            .end_test()
            .build()
        )
        
        assert len(suite.test_cases) == 2
    
    def test_builder_from_dict(self):
        """Test creating builder from existing suite dict."""
        suite_data = {
            'rule_id': 'existing',
            'name': 'Existing Suite',
            'test_cases': [
                {'name': 'TC1', 'context': {}, 'expected_output': {}}
            ]
        }
        builder = RuleTestBuilder.from_suite_dict(suite_data)
        suite = builder.build()
        
        assert suite.rule_id == 'existing'
        assert len(suite.test_cases) == 1


class TestRuleTestRunner:
    """Test cases for RuleTestRunner class."""
    
    def test_compare_outputs_match(self):
        """Test output comparison with matching values."""
        runner = RuleTestRunner(engine=None)
        
        actual = {'should_push': True, 'action': 'send'}
        expected = {'should_push': True, 'action': 'send'}
        
        assert runner._compare_outputs(actual, expected) is True
    
    def test_compare_outputs_mismatch(self):
        """Test output comparison with mismatched values."""
        runner = RuleTestRunner(engine=None)
        
        actual = {'should_push': True, 'action': 'send'}
        expected = {'should_push': False, 'action': 'send'}
        
        assert runner._compare_outputs(actual, expected) is False
    
    def test_compare_outputs_missing_key(self):
        """Test output comparison with missing key."""
        runner = RuleTestRunner(engine=None)
        
        actual = {'should_push': True}
        expected = {'should_push': True, 'action': 'send'}
        
        assert runner._compare_outputs(actual, expected) is False
    
    def test_compare_outputs_nested(self):
        """Test output comparison with nested dicts."""
        runner = RuleTestRunner(engine=None)
        
        actual = {'result': {'value': 10, 'status': 'ok'}}
        expected = {'result': {'value': 10, 'status': 'ok'}}
        
        assert runner._compare_outputs(actual, expected) is True
