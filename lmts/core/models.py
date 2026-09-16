from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


Location = Literal["local", "remote"]
ResponseStreamChannel = Literal["input", "thinking", "text", "tool", "meta"]


def _canonical_ref(value: str, *, field_name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{field_name} must be a non-empty canonical string")
    return value


def canonical_model_id(provider_ref: str, model_ref: str) -> str:
    """Return the canonical provider-qualified identity for one model.

    Provider refs may not contain ':' so the first ':' is an unambiguous
    provider/model boundary. Model refs intentionally may contain ':' because
    provider-native names commonly use tags such as ``llama3.2:3b``.
    """
    provider = _canonical_ref(provider_ref, field_name="provider_ref")
    model = _canonical_ref(model_ref, field_name="model_ref")
    if ":" in provider:
        raise ValueError("provider_ref must not contain ':'")
    return f"{provider}:{model}"


@dataclass(frozen=True, slots=True)
class ModelCapabilities:
    text: bool = True
    vision: bool | None = None
    tools: bool | None = None
    structured_output: bool | None = None
    workspace_read: bool | None = None
    workspace_write: bool | None = None
    multi_file_output: bool | None = None


@dataclass(frozen=True, slots=True)
class ModelDescriptor:
    id: str
    provider_ref: str
    model_ref: str
    location: Location
    available: bool = True
    capabilities: ModelCapabilities = field(default_factory=ModelCapabilities)
    metadata: dict[str, Any] = field(default_factory=dict)
    runtime_configuration: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        canonical = canonical_model_id(self.provider_ref, self.model_ref)
        if self.id != canonical:
            raise ValueError(f"model id must be canonical provider-qualified identity: {canonical}")
        if self.location not in {"local", "remote"}:
            raise ValueError(f"unsupported model location: {self.location}")

    @property
    def canonical_id(self) -> str:
        return self.id


@dataclass(frozen=True, slots=True)
class NormalizedUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class NormalizedTiming:
    ttft_ms: float | None = None
    total_ms: float | None = None
    load_ms: float | None = None
    prompt_eval_ms: float | None = None
    generation_ms: float | None = None


@dataclass(frozen=True, slots=True)
class NormalizedPerformance:
    """Provider-neutral performance metrics derived from provider evidence."""

    prompt_tokens_per_second: float | None = None
    generation_tokens_per_second: float | None = None


@dataclass(frozen=True, slots=True)
class ResponseStreamChunk:
    """Executor-neutral read-only chunk of a response stream."""

    source_id: str
    channel: ResponseStreamChannel
    text: str = ""
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class NormalizedResponse:
    text: str
    finish_reason: str | None = None
    usage: NormalizedUsage = field(default_factory=NormalizedUsage)
    timing: NormalizedTiming = field(default_factory=NormalizedTiming)
    performance: NormalizedPerformance = field(default_factory=NormalizedPerformance)
    raw: dict[str, Any] = field(default_factory=dict)
