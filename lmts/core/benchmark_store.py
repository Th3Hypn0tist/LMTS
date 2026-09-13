from __future__ import annotations

import json
import os
from pathlib import Path

from .benchmark_runner import BenchmarkBatch
from .store import safe_component


class BenchmarkStore:
    """Append-only store for benchmark batch manifests."""

    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()

    def path_for(self, batch: BenchmarkBatch) -> Path:
        return (
            self.root
            / "benchmarks"
            / safe_component(batch.test_ref)
            / "batches"
            / f"{safe_component(batch.batch_id)}.json"
        )

    def append(self, batch: BenchmarkBatch) -> Path:
        path = self.path_for(batch)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise FileExistsError(f"benchmark batch already exists: {path}")
        payload = json.dumps(batch.to_dict(), indent=2, ensure_ascii=False) + "\n"
        temp = path.with_suffix(path.suffix + f".tmp-{os.getpid()}")
        temp.write_text(payload, encoding="utf-8")
        try:
            temp.replace(path)
        finally:
            if temp.exists():
                temp.unlink()
        return path
