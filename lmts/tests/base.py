from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from lmts.core.control import RunControl
from lmts.core.models import ModelDescriptor, NormalizedResponse, ResponseStreamChunk
from lmts.core.provider import ModelProvider
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
    provider: ModelProvider
    model: ModelDescriptor
    workspace: Workspace
    control: RunControl | None = None
    response_sink: Callable[[ResponseStreamChunk], None] | None = None
    responses: list[NormalizedResponse] = field(default_factory=list)

    def checkpoint(self) -> None:
        if self.control is not None:
            self.control.raise_if_cancelled()

    def generate(self, prompt: str) -> NormalizedResponse:
        self.checkpoint()
        generate_stream = getattr(self.provider, "generate_stream", None)
        if callable(generate_stream) and self.response_sink is not None:
            response = generate_stream(self.model, prompt, self.response_sink)
        else:
            response = self.provider.generate(self.model, prompt)
            if self.response_sink is not None:
                self.response_sink(
                    ResponseStreamChunk(
                        model_id=self.model.id,
                        channel="text",
                        text=response.text,
                    )
                )
                self.response_sink(
                    ResponseStreamChunk(
                        model_id=self.model.id,
                        channel="meta",
                        data={
                            "finish_reason": response.finish_reason,
                            "input_tokens": response.usage.input_tokens,
                            "output_tokens": response.usage.output_tokens,
                            "total_ms": response.timing.total_ms,
                        },
                    )
                )
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
