from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from lmts.tests.base import TestModule, test_ref

from .control import RunControl
from .evaluation_store import EvaluationRecord, EvaluationStore
from .executor import TestExecutor
from .run import utc_now
from .runner import TestRunner
from .scoring import build_subject_scorecard


@dataclass(frozen=True, slots=True)
class EvaluationOutcome:
    record: EvaluationRecord
    record_path: Path
    run_paths: tuple[Path, ...]


class SubjectEvaluator:
    """Evaluate one model, bot or composition against one explicit test set."""

    def __init__(
        self,
        runner: TestRunner,
        store: EvaluationStore,
    ) -> None:
        self.runner = runner
        self.store = store

    def evaluate(
        self,
        executor: TestExecutor,
        tests: list[TestModule],
        workspace_root: Path,
        *,
        control: RunControl | None = None,
    ) -> EvaluationOutcome:
        if not tests:
            raise ValueError("subject evaluation requires at least one test")

        evaluation_id = uuid.uuid4().hex
        started_at = utc_now()
        run_payloads: list[dict] = []
        run_ids: list[str] = []
        run_paths: list[Path] = []

        for test in tests:
            if control is not None and control.cancelled:
                break
            run, path = self.runner.run_executor(
                test,
                executor,
                workspace_root / evaluation_id,
                control=control,
            )
            run_payloads.append(run.to_dict())
            run_ids.append(run.run_id)
            run_paths.append(path)
            if run.status == "cancelled":
                break

        if not run_payloads:
            raise ValueError("subject evaluation produced no runs")

        scorecard = build_subject_scorecard(run_payloads)
        status = "cancelled" if control is not None and control.cancelled else "completed"
        record = EvaluationRecord(
            evaluation_id=evaluation_id,
            started_at=started_at,
            completed_at=utc_now(),
            subject=executor.subject.to_dict(),
            test_refs=tuple(test_ref(test) for test in tests),
            run_ids=tuple(run_ids),
            scorecard=scorecard.to_dict(),
            status=status,
            metadata={
                "executor_id": executor.id,
                "executor_kind": executor.kind,
            },
        )
        record_path = self.store.append(record)
        return EvaluationOutcome(
            record=record,
            record_path=record_path,
            run_paths=tuple(run_paths),
        )
