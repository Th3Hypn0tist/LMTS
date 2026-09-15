from __future__ import annotations

import pytest

from lmts.tools.reference_benchmark import ReferenceBenchmarkProgress
from lmts.view.reference_progress import format_reference_progress


def event(phase: str, **kwargs) -> ReferenceBenchmarkProgress:
    return ReferenceBenchmarkProgress(domain='cpu', phase=phase, **kwargs)


def test_formats_suite_and_backend_boundaries() -> None:
    assert format_reference_progress(event('suite_started')) == 'CPU suite started'
    assert format_reference_progress(event('suite_completed')) == 'CPU suite completed'
    assert format_reference_progress(event('backend_started', label='CUDA')) == 'CPU backend started: CUDA'
    assert format_reference_progress(event('backend_completed', label='CUDA')) == 'CPU backend completed: CUDA'


def test_formats_test_and_sample_progress() -> None:
    assert format_reference_progress(event('test_started', label='Hash')) == 'CPU test started: Hash'
    assert format_reference_progress(event('sample_completed', label='Hash', sample_index=2, sample_total=5)) == 'CPU Hash: sample 2/5'
    assert format_reference_progress(event('test_completed', label='Hash')) == 'CPU test completed: Hash'


def test_uses_benchmark_id_when_label_is_missing() -> None:
    assert format_reference_progress(event('test_completed', benchmark_id='cpu.hash')) == 'CPU test completed: cpu.hash'


def test_rejects_incomplete_sample_event() -> None:
    with pytest.raises(ValueError, match='sample_index and sample_total'):
        format_reference_progress(event('sample_completed', label='Hash'))


def test_rejects_unknown_progress_phase() -> None:
    with pytest.raises(ValueError, match='unknown reference benchmark progress phase'):
        format_reference_progress(event('mystery'))
