from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from lmts.core.benchmark_runner import BenchmarkProgress, BenchmarkRunner
from lmts.core.benchmark_store import BenchmarkStore
from lmts.core.control import RunControl
from lmts.core.executor import TestExecutor
from lmts.core.matrix_store import MatrixCell, MatrixRunRecord, MatrixRunStore
from lmts.core.registry import ProviderRegistry
from lmts.core.run import utc_now
from lmts.core.runner import TestRunner
from lmts.core.store import RunStore
from lmts.tests.base import TestModule, test_ref


RunCompletedCallback = Callable[[dict[str, object]], None]
ProgressCallback = Callable[[BenchmarkProgress], None]


@dataclass(frozen=True, slots=True)
class EvaluationOutcome:
    matrix_id: str
    matrix_path: Path
    status: str
    completed: int
    passed: int
    failed: int
    errors: int
    cancelled: int
    cells: tuple[MatrixCell, ...]
    batch_ids: tuple[str, ...]
    batch_paths: tuple[str, ...]
    run_errors: tuple[dict[str, object], ...]
    publish_errors: tuple[dict[str, str], ...]


class EvaluationService:
    def __init__(
        self,
        providers: ProviderRegistry,
        *,
        results_root: Path,
        workspace_root: Path,
        response_sink,
        system_context_loader,
    ) -> None:
        self.providers = providers
        self.results_root = results_root
        self.workspace_root = workspace_root
        self.response_sink = response_sink
        self.system_context_loader = system_context_loader

    @staticmethod
    def verdict(event: BenchmarkProgress) -> str | None:
        run = event.run
        if run is None:
            return None
        if run.status == 'cancelled':
            return 'CANCEL'
        if run.status != 'completed':
            return 'ERROR'
        if run.passed is True:
            return 'PASS'
        if run.passed is False:
            return 'FAIL'
        return '?'

    def execute(
        self,
        targets: list[TestExecutor],
        tests: list[TestModule],
        control: RunControl,
        *,
        progress: ProgressCallback | None = None,
        on_run_completed: RunCompletedCallback | None = None,
        provenance: dict[str, object] | None = None,
    ) -> EvaluationOutcome:
        runner = TestRunner(
            self.providers,
            RunStore(self.results_root),
            response_sink=self.response_sink,
            system_context_loader=self.system_context_loader,
            provenance=provenance,
        )
        benchmark_runner = BenchmarkRunner(runner)
        benchmark_store = BenchmarkStore(self.results_root)
        matrix_store = MatrixRunStore(self.results_root)
        matrix_id = uuid.uuid4().hex
        matrix_started_at = utc_now()
        matrix_cells: list[MatrixCell] = []
        batch_ids: list[str] = []
        batch_paths: list[str] = []
        run_errors: list[dict[str, object]] = []
        publish_errors: list[dict[str, str]] = []
        passed = failed = errors = cancelled = completed = 0

        for test in tests:
            if control.cancelled:
                break

            def on_progress(event: BenchmarkProgress) -> None:
                nonlocal passed, failed, errors, cancelled, completed
                if progress is not None:
                    progress(event)
                run = event.run
                if event.phase != 'completed' or run is None:
                    return
                completed += 1
                if event.result_path is not None:
                    matrix_cells.append(
                        MatrixCell(
                            target_id=run.executor_id,
                            target_kind=run.executor_kind,
                            test_ref=run.test_ref,
                            run_id=run.run_id,
                            status=run.status,
                            passed=run.passed,
                            result_path=str(event.result_path),
                        )
                    )
                if run.status == 'cancelled':
                    cancelled += 1
                elif run.status != 'completed':
                    errors += 1
                    if event.result_path is not None:
                        run_errors.append({
                            'run_id': run.run_id,
                            'target_id': run.executor_id,
                            'target_kind': run.executor_kind,
                            'test_ref': run.test_ref,
                            'result_path': str(event.result_path),
                            'error': run.error,
                        })
                elif run.passed is True:
                    passed += 1
                elif run.passed is False:
                    failed += 1

                if on_run_completed is not None and run.status != 'cancelled':
                    try:
                        on_run_completed(run.to_dict())
                    except Exception as exc:
                        publish_errors.append({
                            'run_id': run.run_id,
                            'target_id': run.executor_id,
                            'test_ref': run.test_ref,
                            'error': f'{type(exc).__name__}: {exc}',
                        })

            batch = benchmark_runner.run(
                test,
                targets,
                self.workspace_root,
                progress=on_progress,
                control=control,
            )
            if batch.run_ids:
                path = benchmark_store.append(batch)
                batch_ids.append(batch.batch_id)
                batch_paths.append(str(path))

        status = 'cancelled' if control.cancelled else 'completed'
        record = MatrixRunRecord(
            matrix_id=matrix_id,
            started_at=matrix_started_at,
            completed_at=utc_now(),
            status=status,
            target_ids=[target.id for target in targets],
            target_kinds={target.id: target.kind for target in targets},
            test_refs=[test_ref(test) for test in tests],
            cells=matrix_cells,
            passed=passed,
            failed=failed,
            errors=errors,
            cancelled=cancelled,
        )
        matrix_path = matrix_store.append(record)
        return EvaluationOutcome(
            matrix_id=matrix_id,
            matrix_path=matrix_path,
            status=status,
            completed=completed,
            passed=passed,
            failed=failed,
            errors=errors,
            cancelled=cancelled,
            cells=tuple(matrix_cells),
            batch_ids=tuple(batch_ids),
            batch_paths=tuple(batch_paths),
            run_errors=tuple(run_errors),
            publish_errors=tuple(publish_errors),
        )
