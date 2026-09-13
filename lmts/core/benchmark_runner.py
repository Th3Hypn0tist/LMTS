from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from lmts.tests.base import TestModule, test_ref

from .control import RunControl
from .executor import TestExecutor
from .run import RunResult, utc_now
from .runner import TestRunner


@dataclass(slots=True)
class BenchmarkBatch:
    batch_id: str
    test_ref: str
    started_at: str
    completed_at: str
    target_ids: list[str] = field(default_factory=list)
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
            "target_ids": list(self.target_ids),
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
    target_id: str
    target_kind: str
    run: RunResult | None = None
    result_path: Path | None = None


ProgressCallback = Callable[[BenchmarkProgress], None]


class BenchmarkRunner:
    def __init__(self, runner: TestRunner) -> None:
        self.runner = runner

    def run(
        self,
        test: TestModule,
        targets: list[TestExecutor],
        workspace_root: Path,
        *,
        progress: ProgressCallback | None = None,
        control: RunControl | None = None,
    ) -> BenchmarkBatch:
        batch_id = uuid.uuid4().hex
        started_at = utc_now()
        resolved_test_ref = test_ref(test)
        run_ids: list[str] = []
        completed = 0
        passed = 0
        failed = 0
        errors = 0
        cancelled = 0
        total = len(targets)

        for index, target in enumerate(targets, start=1):
            if control is not None and control.cancelled:
                break

            if progress is not None:
                progress(
                    BenchmarkProgress(
                        phase="starting",
                        index=index,
                        total=total,
                        test_ref=resolved_test_ref,
                        target_id=target.id,
                        target_kind=target.kind,
                    )
                )

            run, result_path = self.runner.run_executor(
                test,
                target,
                workspace_root / batch_id,
                control=control,
            )
            run_ids.append(run.run_id)
            if run.status == "completed":
                completed += 1
                if run.passed is True:
                    passed += 1
                elif run.passed is False:
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
                        test_ref=resolved_test_ref,
                        target_id=target.id,
                        target_kind=target.kind,
                        run=run,
                        result_path=result_path,
                    )
                )

            if run.status == "cancelled":
                break

        return BenchmarkBatch(
            batch_id=batch_id,
            test_ref=resolved_test_ref,
            started_at=started_at,
            completed_at=utc_now(),
            target_ids=[target.id for target in targets],
            run_ids=run_ids,
            completed=completed,
            passed=passed,
            failed=failed,
            errors=errors,
            cancelled=cancelled,
        )
