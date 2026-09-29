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
TargetCompletedCallback = Callable[[dict[str, object]], None]
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

    @staticmethod
    def _target_bundle(
        target: TestExecutor,
        *,
        started_at: str,
        completed_at: str,
        status: str,
        cells: list[MatrixCell],
        runs: list[dict[str, object]],
        passed: int,
        failed: int,
        errors: int,
        cancelled: int,
    ) -> dict[str, object]:
        report_matrix_id = uuid.uuid4().hex
        test_refs = list(dict.fromkeys(str(run.get('test_ref') or '') for run in runs if run.get('test_ref')))
        return {
            'schema_version': 1,
            'export_type': 'lmts.matrix_bundle',
            'exported_at': completed_at,
            'matrix': {
                'matrix_id': report_matrix_id,
                'started_at': started_at,
                'completed_at': completed_at,
                'status': status,
                'target_ids': [target.id],
                'target_kinds': {target.id: target.kind},
                'test_refs': test_refs,
                'cells': [cell.to_dict() for cell in cells],
                'passed': passed,
                'failed': failed,
                'errors': errors,
                'cancelled': cancelled,
            },
            'runs': list(runs),
        }

    def execute(
        self,
        targets: list[TestExecutor],
        tests: list[TestModule],
        control: RunControl,
        *,
        progress: ProgressCallback | None = None,
        on_run_completed: RunCompletedCallback | None = None,
        on_target_completed: TargetCompletedCallback | None = None,
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

        # Target-major execution is intentional:
        # one target/model runs its complete selected test suite before the next
        # target starts. This keeps model lifecycle, warm state and report
        # boundaries aligned.
        for target in targets:
            if control.cancelled:
                break

            target_started_at = utc_now()
            target_cells: list[MatrixCell] = []
            target_runs: list[dict[str, object]] = []
            target_passed = target_failed = target_errors = target_cancelled = 0

            for test in tests:
                if control.cancelled:
                    break

                def on_progress(event: BenchmarkProgress) -> None:
                    nonlocal passed, failed, errors, cancelled, completed
                    nonlocal target_passed, target_failed, target_errors, target_cancelled

                    if progress is not None:
                        progress(event)

                    run = event.run
                    if event.phase != 'completed' or run is None:
                        return

                    completed += 1
                    run_dict = run.to_dict()
                    target_runs.append(run_dict)

                    cell = None
                    if event.result_path is not None:
                        cell = MatrixCell(
                            target_id=run.executor_id,
                            target_kind=run.executor_kind,
                            test_ref=run.test_ref,
                            run_id=run.run_id,
                            status=run.status,
                            passed=run.passed,
                            result_path=str(event.result_path),
                        )
                        matrix_cells.append(cell)
                        target_cells.append(cell)

                    if run.status == 'cancelled':
                        cancelled += 1
                        target_cancelled += 1
                    elif run.status != 'completed':
                        errors += 1
                        target_errors += 1
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
                        target_passed += 1
                    elif run.passed is False:
                        failed += 1
                        target_failed += 1

                    if on_run_completed is not None and run.status != 'cancelled':
                        try:
                            on_run_completed(run_dict)
                        except Exception as exc:
                            publish_errors.append({
                                'run_id': run.run_id,
                                'target_id': run.executor_id,
                                'test_ref': run.test_ref,
                                'error': f'{type(exc).__name__}: {exc}',
                            })

                batch = benchmark_runner.run(
                    test,
                    [target],
                    self.workspace_root,
                    progress=on_progress,
                    control=control,
                )
                if batch.run_ids:
                    path = benchmark_store.append(batch)
                    batch_ids.append(batch.batch_id)
                    batch_paths.append(str(path))

                if control.cancelled:
                    break

            target_completed_at = utc_now()
            target_status = 'cancelled' if control.cancelled else 'completed'

            # Publish/consume one complete target report synchronously before
            # advancing to the next model. ERROR/CANCELLED-only material is not
            # eligible benchmark evidence for publication.
            publishable_runs = [
                run for run in target_runs
                if run.get('status') == 'completed' and isinstance(run.get('passed'), bool)
            ]
            publishable_run_ids = {str(run.get('run_id') or '') for run in publishable_runs}
            publishable_cells = [
                cell for cell in target_cells
                if cell.run_id in publishable_run_ids
            ]

            if on_target_completed is not None and publishable_runs:
                bundle = self._target_bundle(
                    target,
                    started_at=target_started_at,
                    completed_at=target_completed_at,
                    status=target_status,
                    cells=publishable_cells,
                    runs=publishable_runs,
                    passed=target_passed,
                    failed=target_failed,
                    errors=0,
                    cancelled=0,
                )
                try:
                    on_target_completed(bundle)
                except Exception as exc:
                    publish_errors.append({
                        'run_id': '',
                        'target_id': target.id,
                        'test_ref': '',
                        'error': f'{type(exc).__name__}: {exc}',
                    })

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
