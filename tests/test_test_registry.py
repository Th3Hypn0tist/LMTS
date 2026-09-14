import unittest

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


class TestRegistryTests(unittest.TestCase):
    def test_multiple_test_modules_can_coexist(self):
        registry = TestRegistry([TestA(), TestB()])
        self.assertEqual([test.id for test in registry.tests()], ["demo.a", "demo.b"])

    def test_duplicate_test_ref_is_rejected(self):
        registry = TestRegistry([TestA()])
        with self.assertRaises(ValueError):
            registry.register(TestA())


if __name__ == "__main__":
    unittest.main()
