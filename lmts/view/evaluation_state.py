from __future__ import annotations

from lmts.core.benchmark_runner import BenchmarkProgress
from lmts.core.executor import TestExecutor
from lmts.services.evaluation import EvaluationOutcome, EvaluationService
from lmts.tests.base import TestModule, test_ref

from .projector import LMTSViewState
from .response_monitor import ResponseMonitor


class EvaluationViewState:
    def __init__(
        self,
        state: LMTSViewState,
        response_monitor: ResponseMonitor,
        evaluation_service: EvaluationService,
    ) -> None:
        self.state = state
        self.response_monitor = response_monitor
        self.evaluation_service = evaluation_service

    def prepare(self, targets: list[TestExecutor], tests: list[TestModule]) -> None:
        self.response_monitor.reset()
        self.state.running = True
        self.state.cancel_requested = False
        self.state.progress_completed = 0
        self.state.progress_total = len(targets) * len(tests)
        self.state.progress_passed = 0
        self.state.progress_failed = 0
        self.state.progress_errors = 0
        self.state.progress_cancelled = 0
        self.state.progress_target_id = ''
        self.state.progress_test_ref = test_ref(tests[0])
        self.state.progress_phase = 'starting'
        self.state.live_target_ids = tuple(target.id for target in targets)
        self.state.live_target_kinds = {target.id: target.kind for target in targets}
        self.state.live_test_refs = tuple(test_ref(test) for test in tests)
        self.state.live_cells = {
            (target.id, test_ref(test)): '-'
            for target in targets
            for test in tests
        }
        self.state.last_result = None
        self.state.message = f'test matrix started: {len(targets)} target(s) x {len(tests)} configured test(s)'

    def progress(self, event: BenchmarkProgress) -> None:
        self.state.progress_target_id = event.target_id
        self.state.progress_test_ref = event.test_ref
        if event.phase == 'starting':
            self.response_monitor.reset(event.target_id)
            self.state.live_cells[(event.target_id, event.test_ref)] = 'RUN'
            if not self.state.cancel_requested:
                self.state.progress_phase = 'starting'
            return

        self.state.progress_completed += 1
        if not self.state.cancel_requested:
            self.state.progress_phase = event.phase
        verdict = self.evaluation_service.verdict(event)
        run = event.run
        if verdict is None or run is None:
            return
        self.state.live_cells[(run.executor_id, run.test_ref)] = verdict
        if run.status == 'cancelled':
            self.state.progress_cancelled += 1
        elif run.status != 'completed':
            self.state.progress_errors += 1
        elif run.passed is True:
            self.state.progress_passed += 1
        elif run.passed is False:
            self.state.progress_failed += 1

    def apply_outcome(
        self,
        outcome: EvaluationOutcome,
        targets: list[TestExecutor],
        tests: list[TestModule],
    ) -> None:
        self.state.progress_completed = outcome.completed
        self.state.progress_passed = outcome.passed
        self.state.progress_failed = outcome.failed
        self.state.progress_errors = outcome.errors
        self.state.progress_cancelled = outcome.cancelled
        self.state.last_result = {
            'suite_level': self.state.suite_level,
            'matrix': f'{len(targets)} target(s) x {len(tests)} configured test(s)',
            'matrix_id': outcome.matrix_id,
            'matrix_path': str(outcome.matrix_path),
            'runs': outcome.completed,
            'passed': outcome.passed,
            'failed': outcome.failed,
            'errors': outcome.errors,
            'cancelled': outcome.cancelled,
            'batch_ids': ', '.join(outcome.batch_ids),
            'batch_paths': ', '.join(outcome.batch_paths),
            'publish_errors': len(outcome.publish_errors),
        }
        if len(outcome.cells) == 1:
            self.state.last_result['single_run_id'] = outcome.cells[0].run_id
            self.state.last_result['single_run_path'] = outcome.cells[0].result_path
        if outcome.run_errors:
            self.state.last_result['error_log'] = 'Output -> Export errors'

        if outcome.status == 'cancelled':
            self.state.progress_phase = 'cancelled'
            self.state.message = (
                f'test matrix cancelled: {self.state.progress_completed}/{self.state.progress_total} run(s) reached'
            )
            return

        self.state.progress_phase = 'finished'
        self.state.message = (
            f'test matrix finished: {outcome.passed} passed, {outcome.failed} failed, {outcome.errors} error(s)'
        )
        if outcome.publish_errors:
            self.state.message += f'; {len(outcome.publish_errors)} report publish failure(s)'

    def abort(self, exc: Exception) -> None:
        self.state.progress_errors += 1
        self.state.progress_phase = 'error'
        self.state.message = f'test matrix aborted: {type(exc).__name__}: {exc}'

    def finish(self) -> None:
        self.state.running = False
