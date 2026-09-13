from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path

from lmts.tests.base import TestModule

from .models import ModelDescriptor
from .run import utc_now
from .runner import TestRunner


@dataclass(slots=True)
class BenchmarkBatch:
    batch_id: str
    test_ref: str
    started_at: str
    completed_at: str
    model_ids: list[str] = field(default_factory=list)
    run_ids: list[str] = field(default_factory=list)
    completed: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "batch_id": self.batch_id,
            "test_ref": self.test_ref,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "model_ids": list(self.model_ids),
            "run_ids": list(self.run_ids),
            "completed": self.completed,
            "passed": self.passed,
            "failed": self.failed,
            "errors": self.errors,
        }


class BenchmarkRunner:
    def __init__(self, runner: TestRunner) -> None:
        self.runner = runner

    def run(self, test: TestModule, models: list[ModelDescriptor], workspace_root: Path) -> BenchmarkBatch:
        batch_id = uuid.uuid4().hex
        started_at = utc_now()
        run_ids: list[str] = []
        completed = 0
        passed = 0
        failed = 0
        errors = 0
        for model in models:
            run, _ = self.runner.run(test, model, workspace_root / batch_id)
            run_ids.append(run.run_id)
            if run.status == "completed":
                completed += 1
                if run.passed is True:
                    passed += 1
                else:
                    failed += 1
            else:
                errors += 1
        return BenchmarkBatch(
            batch_id=batch_id,
            test_ref=f"{test.id}@{test.version}",
            started_at=started_at,
            completed_at=utc_now(),
            model_ids=[model.id for model in models],
            run_ids=run_ids,
            completed=completed,
            passed=passed,
            failed=failed,
            errors=errors,
        )
