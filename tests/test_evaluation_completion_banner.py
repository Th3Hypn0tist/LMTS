from __future__ import annotations

from types import SimpleNamespace

from lmts.services.evaluation import EvaluationOutcome
from lmts.view.evaluation_state import EvaluationViewState
from lmts.view.projector import LMTSViewState
from lmts.view.response_monitor import ResponseMonitor


def test_completed_matrix_appends_tests_done_banner(tmp_path) -> None:
    state = LMTSViewState()
    monitor = ResponseMonitor()
    view = EvaluationViewState(state, monitor, SimpleNamespace(verdict=lambda event: None))

    outcome = EvaluationOutcome(
        matrix_id='matrix-1',
        matrix_path=tmp_path / 'matrix.json',
        status='completed',
        completed=1,
        passed=1,
        failed=0,
        errors=0,
        cancelled=0,
        cells=(),
        batch_ids=(),
        batch_paths=(),
        run_errors=(),
        publish_errors=(),
    )

    view.apply_outcome(outcome, [SimpleNamespace()], [SimpleNamespace()])

    lines = monitor.lines()
    assert '            TESTS DONE!' in lines
    assert state.progress_phase == 'finished'


def test_cancelled_matrix_does_not_append_tests_done_banner(tmp_path) -> None:
    state = LMTSViewState()
    monitor = ResponseMonitor()
    view = EvaluationViewState(state, monitor, SimpleNamespace(verdict=lambda event: None))

    outcome = EvaluationOutcome(
        matrix_id='matrix-1',
        matrix_path=tmp_path / 'matrix.json',
        status='cancelled',
        completed=0,
        passed=0,
        failed=0,
        errors=0,
        cancelled=1,
        cells=(),
        batch_ids=(),
        batch_paths=(),
        run_errors=(),
        publish_errors=(),
    )

    view.apply_outcome(outcome, [SimpleNamespace()], [SimpleNamespace()])

    assert not any('TESTS DONE!' in line for line in monitor.lines())
    assert state.progress_phase == 'cancelled'


def test_publish_failure_details_are_appended_to_console(tmp_path) -> None:
    state = LMTSViewState()
    monitor = ResponseMonitor()
    view = EvaluationViewState(state, monitor, SimpleNamespace(verdict=lambda event: None))

    outcome = EvaluationOutcome(
        matrix_id='matrix-1',
        matrix_path=tmp_path / 'matrix.json',
        status='completed',
        completed=1,
        passed=1,
        failed=0,
        errors=0,
        cancelled=0,
        cells=(),
        batch_ids=(),
        batch_paths=(),
        run_errors=(),
        publish_errors=({
            'run_id': 'run-1',
            'target_id': 'model-a',
            'test_ref': 'core.test@1.0.0#test',
            'error': 'RuntimeError: auto-publish failed: AIGM.fi: LMTS report server HTTP 403: invalid publish key',
        },),
    )

    view.apply_outcome(outcome, [SimpleNamespace()], [SimpleNamespace()])

    lines = monitor.lines()
    assert '          PUBLISH FAILED' in lines
    assert any('HTTP 403: invalid publish key' in line for line in lines)
