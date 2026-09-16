from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from lmts.core.control import RunControl
from lmts.core.executor import TestExecutor
from lmts.core.models import NormalizedResponse, ResponseStreamChunk
from lmts.core.scoring import TestScore
from lmts.lib.workspace import Workspace
from lmts.tests.identity import TestIdentity, identity_for_test, parse_test_ref, test_ref, test_snapshot

TestSubjectKind = Literal["model", "bot", "composition"]
ALL_TEST_SUBJECT_KINDS: tuple[TestSubjectKind, ...] = ("model", "bot", "composition")


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
    subject_kinds: tuple[TestSubjectKind, ...] = ALL_TEST_SUBJECT_KINDS

    def __post_init__(self) -> None:
        if not self.subject_kinds:
            raise ValueError("test requirements must allow at least one subject kind")
        if len(self.subject_kinds) != len(set(self.subject_kinds)):
            raise ValueError("test requirement subject kinds must be unique")
        invalid = [kind for kind in self.subject_kinds if kind not in ALL_TEST_SUBJECT_KINDS]
        if invalid:
            raise ValueError("unsupported test subject kind: " + ", ".join(invalid))


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


__all__ = [
    'ALL_TEST_SUBJECT_KINDS',
    'TestContext',
    'TestIdentity',
    'TestModule',
    'TestRequirements',
    'TestResult',
    'TestSubjectKind',
    'identity_for_test',
    'parse_test_ref',
    'test_ref',
    'test_snapshot',
]
