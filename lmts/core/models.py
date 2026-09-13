from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


Location = Literal["local", "remote"]
ResponseStreamChannel = Literal["thinking", "text", "tool", "meta"]


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
