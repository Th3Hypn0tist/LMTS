import pytest
from lmts.tests.base import TestRequirements, TestResult
from lmts.tests.registry import TestRegistry

class TestA:
    id = "demo.a"
    version = "1.0.0"
    requirements = TestRequirements()
    def run(self, context):
        return TestResult(passed=True)

class TestB:
    id = "demo.b"
    version = "1.0.0"
    requirements = TestRequirements()
    def run(self, context):
        return TestResult(passed=True)

def test_multiple_test_modules_can_coexist():
    registry = TestRegistry([TestA(), TestB()])
    assert [test.id for test in registry.tests()] == ["demo.a", "demo.b"]

def test_duplicate_test_ref_is_rejected():
    registry = TestRegistry([TestA()])
    with pytest.raises(ValueError):
        registry.register(TestA())
