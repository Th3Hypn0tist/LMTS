from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Literal, TYPE_CHECKING

if TYPE_CHECKING:
    from .models import ModelDescriptor

SubjectKind = Literal["model", "bot", "composition"]


@dataclass(frozen=True, slots=True)
class SubjectMember:
    ref: str
    role: str | None = None

    def __post_init__(self) -> None:
        if not self.ref or self.ref.isspace():
            raise ValueError("subject member ref must be non-empty")


@dataclass(frozen=True, slots=True)
class EvaluationSubject:
    """Canonical identity of the thing being evaluated, separate from its executor."""

    id: str
    kind: SubjectKind
    label: str = ""
    members: tuple[SubjectMember, ...] = ()
    configuration: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id or self.id.isspace():
            raise ValueError("evaluation subject id must be non-empty")
        if self.kind not in {"model", "bot", "composition"}:
            raise ValueError(f"unsupported evaluation subject kind: {self.kind}")
        if self.kind == "composition" and not self.members:
            raise ValueError("composition subject requires at least one member")
        refs = [member.ref for member in self.members]
        if len(refs) != len(set(refs)):
            raise ValueError("evaluation subject members must be unique")

    @property
    def fingerprint(self) -> str:
        canonical = {
            "id": self.id,
            "kind": self.kind,
            "members": [asdict(member) for member in self.members],
            "configuration": self.configuration,
        }
        encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "label": self.label,
            "members": [asdict(member) for member in self.members],
            "configuration": dict(self.configuration),
            "metadata": dict(self.metadata),
            "fingerprint": self.fingerprint,
        }

    @classmethod
    def for_model(cls, model: ModelDescriptor) -> EvaluationSubject:
        return cls(
            id=model.id,
            kind="model",
            label=model.model_ref,
            configuration={
                "provider_ref": model.provider_ref,
                "model_ref": model.model_ref,
                "location": model.location,
                "runtime_configuration": dict(model.runtime_configuration),
            },
            metadata={"model_metadata": dict(model.metadata)},
        )

    @classmethod
    def for_bot(cls, bot_id: str, *, label: str = "", configuration: dict[str, Any] | None = None, metadata: dict[str, Any] | None = None) -> EvaluationSubject:
        return cls(id=bot_id, kind="bot", label=label, configuration=dict(configuration or {}), metadata=dict(metadata or {}))

    @classmethod
    def for_composition(cls, composition_id: str, members: tuple[SubjectMember, ...], *, label: str = "", configuration: dict[str, Any] | None = None, metadata: dict[str, Any] | None = None) -> EvaluationSubject:
        return cls(id=composition_id, kind="composition", label=label, members=members, configuration=dict(configuration or {}), metadata=dict(metadata or {}))
