from __future__ import annotations

from collections.abc import Iterable

from .base import TestModule


class TestRegistry:
    __test__ = False

    def __init__(self, tests: Iterable[TestModule] = ()) -> None:
        self._tests: dict[str, TestModule] = {}
        for test in tests:
            self.register(test)

    def register(self, test: TestModule) -> None:
        ref = self.ref(test)
        if ref in self._tests:
            raise ValueError(f"test already registered: {ref}")
        self._tests[ref] = test

    @staticmethod
    def ref(test: TestModule) -> str:
        return f"{test.id}@{test.version}"

    def get(self, ref: str) -> TestModule:
        try:
            return self._tests[ref]
        except KeyError as exc:
            raise KeyError(f"unknown test: {ref}") from exc

    def tests(self) -> tuple[TestModule, ...]:
        return tuple(self._tests[key] for key in sorted(self._tests))
