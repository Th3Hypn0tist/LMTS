from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from lmts.core.control import RunControl
from lmts.core.executor import TestExecutor
from lmts.core.models import NormalizedResponse, ResponseStreamChunk
from lmts.core.scoring import TestScore
from lmts.lib.workspace import Workspace


@dataclass(frozen=True, slots=True)
class TestRequirements:
    __test__ = False
    text_generation: bool = True
    vision: bool = False
    tools: bool = False
    structured_output: bool = False
    workspace_read: bool = False
    workspace_write: bool = False
    multi_file_output: bool = False


@dataclass(frozen=True, slots=True)
class TestResult:
    __test__ = False
    passed: bool | None
    score: TestScore | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TestContext:
    __test__ = False
    executor: TestExecutor
    workspace: Workspace
    control: RunControl | None = None
    response_sink: Callable[[ResponseStreamChunk], None] | None = None
    responses: list[NormalizedResponse] = field(default_factory=list)

    def checkpoint(self) -> None:
        if self.control is not None:
            self.control.raise_if_cancelled()

    def generate(self, prompt: str) -> NormalizedResponse:
        self.checkpoint()
        response = self.executor.generate(prompt, self.response_sink)
        self.responses.append(response)
        self.checkpoint()
        return response


class TestModule(Protocol):
    __test__ = False
    id: str
    version: str
    requirements: TestRequirements

    def run(self, context: TestContext) -> TestResult: ...


def test_ref(test: TestModule) -> str:
    """Return configured-instance ref when available, otherwise type ref."""
    configured = getattr(test, "ref", None)
    if isinstance(configured, str) and configured:
        return configured
    return f"{test.id}@{test.version}"
