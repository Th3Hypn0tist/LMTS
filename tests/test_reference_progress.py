from __future__ import annotations

import pytest

from lmts.tools.reference_benchmark import ReferenceBenchmarkProgress
from lmts.view.reference_progress import format_reference_progress


def test_reference_progress_formats_suite_backend_test_and_sample_events() -> None:
    assert format_reference_progress(ReferenceBenchmarkProgress('cpu', 'suite_started')) == 'CPU suite started'
    assert format_reference_progress(ReferenceBenchmarkProgress('gpu', 'backend_started', label='CUDA driver API')) == 'GPU backend started: CUDA driver API'
    assert format_reference_progress(ReferenceBenchmarkProgress('memory', 'test_started', benchmark_id='copy', label='Copy 4 MiB')) == 'MEMORY test started: Copy 4 MiB'
    assert format_reference_progress(ReferenceBenchmarkProgress('memory', 'sample_completed', benchmark_id='copy', label='Copy 4 MiB', sample_index=3, sample_total=5)) == 'MEMORY Copy 4 MiB: sample 3/5'
    assert format_reference_progress(ReferenceBenchmarkProgress('npu', 'test_completed', benchmark_id='matmul', label='Matmul')) == 'NPU test completed: Matmul'
    assert format_reference_progress(ReferenceBenchmarkProgress('cpu', 'suite_completed')) == 'CPU suite completed'


def test_reference_progress_rejects_incomplete_sample_event() -> None:
    with pytest.raises(ValueError, match='sample_index and sample_total'):
        format_reference_progress(ReferenceBenchmarkProgress('cpu', 'sample_completed', label='SHA-256'))


def test_reference_progress_rejects_unknown_phase() -> None:
    with pytest.raises(ValueError, match='unknown reference benchmark progress phase'):
        format_reference_progress(ReferenceBenchmarkProgress('cpu', 'future_phase'))
