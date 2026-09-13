from __future__ import annotations

from collections.abc import Iterable

from .executor import TestExecutor


class ExecutorRegistry:
    """Registry of concrete evaluation executors keyed by canonical executor id."""

    def __init__(self, executors: Iterable[TestExecutor] = ()) -> None:
        self._executors: dict[str, TestExecutor] = {}
        for executor in executors:
            self.register(executor)

    def register(self, executor: TestExecutor) -> None:
        if executor.id in self._executors:
            raise ValueError(f"executor already registered: {executor.id}")
        self._executors[executor.id] = executor

    def replace(self, executor: TestExecutor) -> None:
        self._executors[executor.id] = executor

    def remove(self, executor_id: str) -> TestExecutor:
        try:
            return self._executors.pop(executor_id)
        except KeyError as exc:
            raise KeyError(f"unknown executor: {executor_id}") from exc

    def get(self, executor_id: str) -> TestExecutor:
        try:
            return self._executors[executor_id]
        except KeyError as exc:
            raise KeyError(f"unknown executor: {executor_id}") from exc

    def executors(self) -> tuple[TestExecutor, ...]:
        return tuple(self._executors[key] for key in sorted(self._executors))

    def by_kind(self, kind: str) -> tuple[TestExecutor, ...]:
        return tuple(
            executor
            for executor in self.executors()
            if executor.kind == kind
        )
