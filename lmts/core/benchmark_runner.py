from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from lmts.tests.base import TestModule

from .control import RunControl
from .models import ModelDescriptor
from .run import RunResult, utc_now
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
    cancelled: int = 0

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
            "cancelled": self.cancelled,
        }


@dataclass(frozen=True, slots=True)
class BenchmarkProgress:
    phase: Literal["starting", "completed"]
    index: int
    total: int
    test_ref: str
    model_id: str
    run: RunResult | None = None
    result_path: Path | None = None


ProgressCallback = Callable[[BenchmarkProgress], None]


class BenchmarkRunner:
    def __init__(self, runner: TestRunner) -> None:
        self.runner = runner

    def run(
        self,
        test: TestModule,
        models: list[ModelDescriptor],
        workspace_root: Path,
        *,
        progress: ProgressCallback | None = None,
        control: RunControl | None = None,
    ) -> BenchmarkBatch:
        batch_id = uuid.uuid4().hex
        started_at = utc_now()
        test_ref = f"{test.id}@{test.version}"
        run_ids: list[str] = []
        completed = 0
        passed = 0
        failed = 0
        errors = 0
        cancelled = 0
        total = len(models)

        for index, model in enumerate(models, start=1):
            if control is not None and control.cancelled:
                break

            if progress is not None:
                progress(
                    BenchmarkProgress(
                        phase="starting",
                        index=index,
                        total=total,
                        test_ref=test_ref,
                        model_id=model.id,
                    )
                )

            run, result_path = self.runner.run(
                test,
                model,
                workspace_root / batch_id,
                control=control,
            )
            run_ids.append(run.run_id)
            if run.status == "completed":
                completed += 1
                if run.passed is True:
                    passed += 1
                else:
                    failed += 1
            elif run.status == "cancelled":
                cancelled += 1
            else:
                errors += 1

            if progress is not None:
                progress(
                    BenchmarkProgress(
                        phase="completed",
                        index=index,
                        total=total,
                        test_ref=test_ref,
                        model_id=model.id,
                        run=run,
                        result_path=result_path,
                    )
                )

            if run.status == "cancelled":
                break

        return BenchmarkBatch(
            batch_id=batch_id,
            test_ref=test_ref,
            started_at=started_at,
            completed_at=utc_now(),
            model_ids=[model.id for model in models],
            run_ids=run_ids,
            completed=completed,
            passed=passed,
            failed=failed,
            errors=errors,
            cancelled=cancelled,
        )
