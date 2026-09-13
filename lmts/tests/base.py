from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from lmts.core.models import ModelDescriptor
from lmts.core.workspace import Workspace


@dataclass(frozen=True, slots=True)
class TestRequirements:
    text_generation: bool = True
    workspace_read: bool = False
    workspace_write: bool = False
    multi_file_output: bool = False


@dataclass(frozen=True, slots=True)
class TestResult:
    test_ref: str
    model_ref: str
    passed: bool | None
    metrics: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)


class TestModule(Protocol):
    id: str
    version: str
    requirements: TestRequirements

    def run(self, model: ModelDescriptor, workspace: Workspace) -> TestResult: ...
