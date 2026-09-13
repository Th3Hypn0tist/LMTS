from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .store import safe_component


@dataclass(frozen=True, slots=True)
class EvaluationRecord:
    evaluation_id: str
    started_at: str
    completed_at: str
    subject: dict[str, Any]
    test_refs: tuple[str, ...]
    run_ids: tuple[str, ...]
    scorecard: dict[str, Any]
    status: str = "completed"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EvaluationStore:
    """Append-only canonical store for one evaluated subject and test set."""

    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()

    def path_for(self, record: EvaluationRecord) -> Path:
        subject = record.subject
        kind = safe_component(str(subject.get("kind") or "unknown"))
        subject_id = safe_component(str(subject.get("id") or "unknown"))
        fingerprint = safe_component(str(subject.get("fingerprint") or "unfingerprinted"))
        return (
            self.root
            / "subjects"
            / kind
            / subject_id
            / fingerprint
            / "evaluations"
            / f"{safe_component(record.evaluation_id)}.json"
        )

    def append(self, record: EvaluationRecord) -> Path:
        path = self.path_for(record)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise FileExistsError(f"evaluation already exists: {path}")
        payload = json.dumps(record.to_dict(), indent=2, ensure_ascii=False) + "\n"
        temp = path.with_suffix(path.suffix + f".tmp-{os.getpid()}")
        temp.write_text(payload, encoding="utf-8")
        try:
            temp.replace(path)
        finally:
            if temp.exists():
                temp.unlink()
        return path

    def load(self, path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))
