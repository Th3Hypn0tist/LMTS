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
from lmts.core.variance_store import VarianceStore
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
        suite_repeats: int = 1,
    ) -> EvaluationOutcome:
        if isinstance(suite_repeats, bool) or not isinstance(suite_repeats, int) or not 1 <= suite_repeats <= 100:
            raise ValueError('suite_repeats must be an integer between 1 and 100')
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
        variance_store = VarianceStore(self.results_root)
        matrix_id = uuid.uuid4().hex
        matrix_started_at = utc_now()
        matrix_cells: list[MatrixCell] = []
        batch_ids: list[str] = []
        batch_paths: list[str] = []
        run_errors: list[dict[str, object]] = []
        publish_errors: list[dict[str, str]] = []
        passed = failed = errors = cancelled = completed = 0
        anchor_runs: dict[tuple[str, str], object] = {}

        ready_targets: list[TestExecutor] = []
        for target in targets:
            if control.cancelled:
                break
            if target.kind != 'model':
                ready_targets.append(target)
                continue
            warm_up = getattr(target, 'warm_up', None)
            if not callable(warm_up):
                ready_targets.append(target)
                continue
            try:
                warm_up()
                ready_targets.append(target)
            except Exception as exc:
                errors += 1
                run_errors.append({
                    'phase': 'warmup',
                    'target_id': target.id,
                    'target_kind': target.kind,
                    'test_ref': None,
                    'run_id': None,
                    'result_path': None,
                    'error': {
                        'type': type(exc).__name__,
                        'message': str(exc),
                    },
                })

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
                anchor_runs[(run.executor_id, run.test_ref)] = run

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

                if (
                    suite_repeats == 1
                    and on_run_completed is not None
                    and run.status == 'completed'
                    and isinstance(run.passed, bool)
                ):
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
                ready_targets,
                self.workspace_root,
                progress=on_progress,
                control=control,
            )
            if batch.run_ids:
                path = benchmark_store.append(batch)
                batch_ids.append(batch.batch_id)
                batch_paths.append(str(path))

        if suite_repeats > 1 and not control.cancelled:
            for repeat_index in range(1, suite_repeats):
                if control.cancelled:
                    break
                for test in tests:
                    if control.cancelled:
                        break
                    resolved_test_ref = test_ref(test)
                    for target in ready_targets:
                        if control.cancelled:
                            break
                        anchor = anchor_runs.get((target.id, resolved_test_ref))
                        if anchor is None or getattr(anchor, 'status', None) != 'completed':
                            continue
                        if not isinstance(getattr(anchor, 'passed', None), bool):
                            continue
                        observation = runner.run_variance_executor(
                            test,
                            target,
                            self.workspace_root / f'variance-{matrix_id}-{repeat_index}',
                            control=control,
                        )
                        if observation.cancelled:
                            cancelled += 1
                            break
                        if observation.error is not None:
                            errors += 1
                            run_errors.append({
                                'phase': 'variance',
                                'target_id': target.id,
                                'target_kind': target.kind,
                                'test_ref': resolved_test_ref,
                                'run_id': getattr(anchor, 'run_id', None),
                                'result_path': None,
                                'error': observation.error,
                            })
                            continue
                        if isinstance(observation.passed, bool):
                            variance_store.append(
                                str(getattr(anchor, 'run_id')),
                                observation.passed,
                                observed_at=observation.observed_at,
                            )

        if suite_repeats > 1 and on_run_completed is not None and not control.cancelled:
            for anchor in anchor_runs.values():
                if getattr(anchor, 'status', None) != 'completed' or not isinstance(getattr(anchor, 'passed', None), bool):
                    continue
                payload = anchor.to_dict()
                samples = variance_store.samples_for_run(str(getattr(anchor, 'run_id')))
                if samples:
                    payload['variance_samples'] = samples
                try:
                    on_run_completed(payload)
                except Exception as exc:
                    publish_errors.append({
                        'run_id': str(getattr(anchor, 'run_id')),
                        'target_id': str(getattr(anchor, 'executor_id')),
                        'test_ref': str(getattr(anchor, 'test_ref')),
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
