from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from .models import NormalizedResponse

RunStatus = Literal["completed", "failed", "cancelled"]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def primitive(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return primitive(asdict(value))
    if isinstance(value, dict):
        return {str(key): primitive(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [primitive(item) for item in value]
    return value


@dataclass(slots=True)
class RunResult:
    run_id: str
    test_ref: str
    executor_id: str
    executor_kind: str
    started_at: str
    completed_at: str
    status: RunStatus
    passed: bool | None
    evaluation_subject: dict[str, Any] = field(default_factory=dict)
    execution_metadata: dict[str, Any] = field(default_factory=dict)
    score: dict[str, Any] | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)
    responses: list[NormalizedResponse] = field(default_factory=list)
    workspace_trace: list[dict[str, object]] = field(default_factory=list)
    system_context: dict[str, Any] = field(default_factory=dict)
    model_id: str | None = None
    model_ref: str | None = None
    provider_ref: str | None = None
    model_metadata: dict[str, Any] = field(default_factory=dict)
    error: dict[str, str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return primitive(self)
