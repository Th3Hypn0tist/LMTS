from pathlib import Path


CONTROLLER = Path('lmts/view/controller.py')


def test_controller_stays_a_thin_service_facade() -> None:
    text = CONTROLLER.read_text(encoding='utf-8')
    assert len(text.splitlines()) <= 280
    assert 'import threading' not in text
    assert 'import uuid' not in text
    for forbidden in (
        'lmts.core.runner',
        'lmts.core.benchmark_runner',
        'lmts.core.benchmark_store',
        'lmts.core.matrix_store',
        'lmts.core.runtime_targets',
        'lmts.core.store',
        'lmts.lib.errorlog',
        'lmts.tools.profile',
    ):
        assert forbidden not in text


def test_controller_uses_explicit_service_and_view_state_boundaries() -> None:
    text = CONTROLLER.read_text(encoding='utf-8')
    for required in (
        'EvaluationService',
        'SystemProfileService',
        'ResultService',
        'RunLifecycleService',
        'TargetDiscoveryService',
        'EvaluationViewState',
        'MatrixViewState',
    ):
        assert required in text
