from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .store import safe_component


@dataclass(frozen=True, slots=True)
class MatrixCell:
    model_id: str
    test_ref: str
    run_id: str
    status: str
    passed: bool | None
    result_path: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class MatrixRunRecord:
    matrix_id: str
    started_at: str
    completed_at: str
    status: str
    model_ids: list[str] = field(default_factory=list)
    test_refs: list[str] = field(default_factory=list)
    cells: list[MatrixCell] = field(default_factory=list)
    passed: int = 0
    failed: int = 0
    errors: int = 0
    cancelled: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "matrix_id": self.matrix_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "status": self.status,
            "model_ids": list(self.model_ids),
            "test_refs": list(self.test_refs),
            "cells": [cell.to_dict() for cell in self.cells],
            "passed": self.passed,
            "failed": self.failed,
            "errors": self.errors,
            "cancelled": self.cancelled,
        }


class MatrixRunStore:
    """Append-only store for one canonical record per executed test matrix."""

    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()

    def path_for_id(self, matrix_id: str) -> Path:
        return self.root / "matrices" / f"{safe_component(matrix_id)}.json"

    def append(self, record: MatrixRunRecord) -> Path:
        path = self.path_for_id(record.matrix_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise FileExistsError(f"matrix result already exists: {path}")
        payload = json.dumps(record.to_dict(), indent=2, ensure_ascii=False) + "\n"
        temp = path.with_suffix(path.suffix + f".tmp-{os.getpid()}")
        temp.write_text(payload, encoding="utf-8")
        try:
            temp.replace(path)
        finally:
            if temp.exists():
                temp.unlink()
        return path

    def load(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def iter_paths(self) -> list[Path]:
        directory = self.root / "matrices"
        if not directory.exists():
            return []
        return sorted(directory.glob("*.json"))
