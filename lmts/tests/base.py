from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from lmts.core.models import ModelDescriptor, NormalizedResponse
from lmts.core.provider import ModelProvider
from lmts.core.workspace import Workspace


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
    responses: list[NormalizedResponse] = field(default_factory=list)

    def generate(self, prompt: str) -> NormalizedResponse:
        response = self.provider.generate(self.model, prompt)
        self.responses.append(response)
        return response


class TestModule(Protocol):
    __test__ = False
    id: str
    version: str
    requirements: TestRequirements

    def run(self, context: TestContext) -> TestResult: ...
