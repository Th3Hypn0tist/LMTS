from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from .models import ModelCapabilities, ModelDescriptor, NormalizedResponse, ResponseStreamChunk
from .provider import ModelProvider
from .subject import EvaluationSubject

ExecutorKind = Literal["model", "bot", "composition"]
ResponseSink = Callable[[ResponseStreamChunk], None]
GenerateHandler = Callable[[str, ResponseSink | None], NormalizedResponse]


class TestExecutor(Protocol):
    """Execution boundary consumed by LMTS tests."""

    @property
    def id(self) -> str: ...

    @property
    def kind(self) -> ExecutorKind: ...

    @property
    def subject(self) -> EvaluationSubject: ...

    @property
    def capabilities(self) -> ModelCapabilities: ...

    @property
    def metadata(self) -> dict[str, Any]: ...

    def generate(self, prompt: str, sink: ResponseSink | None = None) -> NormalizedResponse: ...


@dataclass(frozen=True, slots=True)
class ModelExecutor:
    provider: ModelProvider
    model: ModelDescriptor

    @property
    def id(self) -> str:
        return self.model.id

    @property
    def kind(self) -> ExecutorKind:
        return "model"

    @property
    def subject(self) -> EvaluationSubject:
        return EvaluationSubject.for_model(self.model)

    @property
    def capabilities(self) -> ModelCapabilities:
        base = self.model.capabilities
        return ModelCapabilities(
            text=base.text,
            vision=base.vision,
            tools=base.tools,
            structured_output=base.structured_output,
            workspace_read=True if base.text else False,
            workspace_write=True if base.text else False,
            multi_file_output=True if base.text else False,
        )

    @property
    def metadata(self) -> dict[str, Any]:
        return {
            "provider_ref": self.model.provider_ref,
            "model_ref": self.model.model_ref,
            "location": self.model.location,
            "model_metadata": dict(self.model.metadata),
            "runtime_configuration": dict(self.model.runtime_configuration),
        }

    def generate(self, prompt: str, sink: ResponseSink | None = None) -> NormalizedResponse:
        generate_stream = getattr(self.provider, "generate_stream", None)
        if sink is not None and callable(generate_stream):
            return generate_stream(self.model, prompt, sink)

        response = self.provider.generate(self.model, prompt)
        if sink is not None:
            sink(ResponseStreamChunk(source_id=self.id, channel="text", text=response.text))
            sink(
                ResponseStreamChunk(
                    source_id=self.id,
                    channel="meta",
                    data={
                        "finish_reason": response.finish_reason,
                        "input_tokens": response.usage.input_tokens,
                        "output_tokens": response.usage.output_tokens,
                        "ttft_ms": response.timing.ttft_ms,
                        "total_ms": response.timing.total_ms,
                        "load_ms": response.timing.load_ms,
                        "prompt_eval_ms": response.timing.prompt_eval_ms,
                        "generation_ms": response.timing.generation_ms,
                        "prompt_tokens_per_second": response.performance.prompt_tokens_per_second,
                        "generation_tokens_per_second": response.performance.generation_tokens_per_second,
                    },
                )
            )
        return response


@dataclass(frozen=True, slots=True)
class RuntimeExecutor:
    """Adapter boundary for a real standalone bot or composition runtime."""

    executor_id: str
    executor_kind: Literal["bot", "composition"]
    evaluation_subject: EvaluationSubject
    generate_handler: GenerateHandler
    executor_capabilities: ModelCapabilities = field(default_factory=ModelCapabilities)
    executor_metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.executor_id or self.executor_id.isspace():
            raise ValueError("executor_id must be non-empty")
        if self.evaluation_subject.kind != self.executor_kind:
            raise ValueError("executor kind must match evaluation subject kind")

    @property
    def id(self) -> str:
        return self.executor_id

    @property
    def kind(self) -> ExecutorKind:
        return self.executor_kind

    @property
    def subject(self) -> EvaluationSubject:
        return self.evaluation_subject

    @property
    def capabilities(self) -> ModelCapabilities:
        return self.executor_capabilities

    @property
    def metadata(self) -> dict[str, Any]:
        return dict(self.executor_metadata)

    def generate(self, prompt: str, sink: ResponseSink | None = None) -> NormalizedResponse:
        return self.generate_handler(prompt, sink)
