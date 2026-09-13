from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


Location = Literal["local", "remote"]


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


@dataclass(frozen=True, slots=True)
class NormalizedResponse:
    text: str
    finish_reason: str | None = None
    usage: NormalizedUsage = field(default_factory=NormalizedUsage)
    timing: NormalizedTiming = field(default_factory=NormalizedTiming)
    raw: dict[str, Any] = field(default_factory=dict)
