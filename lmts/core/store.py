from __future__ import annotations

import json
import os
import re
from pathlib import Path

from .run import RunResult

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def safe_component(value: str) -> str:
    cleaned = _SAFE.sub("_", value).strip("._")
    return cleaned or "unnamed"


class RunStore:
    """Append-only filesystem store for canonical LMTS run records."""

    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()

    def path_for(self, run: RunResult) -> Path:
        subject = run.evaluation_subject
        subject_id = str(subject.get("id") or "unknown-subject")
        subject_kind = str(subject.get("kind") or "unknown")
        fingerprint = str(subject.get("fingerprint") or "unfingerprinted")
        return (
            self.root
            / "subjects"
            / safe_component(subject_kind)
            / safe_component(subject_id)
            / safe_component(fingerprint)
            / "tests"
            / safe_component(run.test_ref)
            / "runs"
            / f"{safe_component(run.run_id)}.json"
        )

    def append(self, run: RunResult) -> Path:
        path = self.path_for(run)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise FileExistsError(f"run already exists: {path}")

        payload = json.dumps(run.to_dict(), indent=2, ensure_ascii=False) + "\n"
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

    def iter_run_paths(self) -> list[Path]:
        if not self.root.exists():
            return []
        return sorted(self.root.glob("subjects/*/*/*/tests/*/runs/*.json"))
