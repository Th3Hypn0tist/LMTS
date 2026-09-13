from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from lmts.core.control import RunControl
from lmts.core.models import ModelDescriptor, NormalizedResponse
from lmts.core.provider import ModelProvider
from lmts.lib.workspace import Workspace


@dataclass(frozen=True, slots=True)
class TestRequirements:
    __test__ = False
    text_generation: bool = True
    workspace_read: bool = False
    workspace_write: bool = False
    multi_file_output: bool = False


@dataclass(frozen=True, slots=True)
class TestResult:
    __test__ = False
    passed: bool | None
    metrics: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TestContext:
    __test__ = False
    provider: ModelProvider
    model: ModelDescriptor
    workspace: Workspace
    control: RunControl | None = None
    responses: list[NormalizedResponse] = field(default_factory=list)

    def checkpoint(self) -> None:
        if self.control is not None:
            self.control.raise_if_cancelled()

    def generate(self, prompt: str) -> NormalizedResponse:
        self.checkpoint()
        response = self.provider.generate(self.model, prompt)
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
