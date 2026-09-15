from __future__ import annotations

import lmts.tools.reference_benchmark as reference


def _shrink_cpu(monkeypatch) -> None:
    monkeypatch.setattr(reference, '_CPU_CHUNK_BYTES', 64)
    monkeypatch.setattr(reference, '_CPU_SINGLE_REPEATS_PER_SAMPLE', 1)
    monkeypatch.setattr(reference, '_CPU_PARALLEL_REPEATS_PER_WORKER', 1)
    monkeypatch.setattr(reference, '_CPU_SAMPLE_COUNT', 2)
    monkeypatch.setattr(reference, '_CPU_WARMUP_REPEATS', 1)
    monkeypatch.setattr(reference.os, 'cpu_count', lambda: 2)


def _shrink_memory(monkeypatch) -> None:
    monkeypatch.setattr(reference, '_MEMORY_SMALL_WORKING_SET_BYTES', 32)
    monkeypatch.setattr(reference, '_MEMORY_SMALL_REPEATS_PER_SAMPLE', 1)
    monkeypatch.setattr(reference, '_MEMORY_LARGE_WORKING_SET_BYTES', 64)
    monkeypatch.setattr(reference, '_MEMORY_LARGE_REPEATS_PER_SAMPLE', 1)
    monkeypatch.setattr(reference, '_MEMORY_SAMPLE_COUNT', 2)
    monkeypatch.setattr(reference, '_MEMORY_WARMUP_REPEATS', 1)


def test_cpu_reference_emits_suite_test_and_sample_progress(monkeypatch) -> None:
    _shrink_cpu(monkeypatch)
    events = []

    result = reference.run_reference_benchmark('cpu', progress=events.append)

    assert result.domain == 'cpu'
    assert events[0].to_dict() == {
        'domain': 'cpu',
        'phase': 'suite_started',
        'benchmark_id': None,
        'label': None,
        'sample_index': None,
        'sample_total': None,
    }
    assert events[-1].phase == 'suite_completed'
    assert [event.phase for event in events].count('test_started') == 2
    assert [event.phase for event in events].count('test_completed') == 2
    samples = [event for event in events if event.phase == 'sample_completed']
    assert len(samples) == 4
    assert [event.sample_index for event in samples] == [1, 2, 1, 2]
    assert all(event.sample_total == 2 for event in samples)
    assert [event.benchmark_id for event in events if event.phase == 'test_started'] == [
        'lmts.reference.cpu.sha256_stream_1t',
        'lmts.reference.cpu.sha256_stream_all_threads',
    ]


def test_memory_reference_emits_progress_for_each_sample(monkeypatch) -> None:
    _shrink_memory(monkeypatch)
    events = []

    result = reference.run_reference_benchmark('memory', progress=events.append)

    assert result.domain == 'memory'
    assert events[0].phase == 'suite_started'
    assert events[-1].phase == 'suite_completed'
    samples = [event for event in events if event.phase == 'sample_completed']
    assert [(event.benchmark_id, event.sample_index, event.sample_total) for event in samples] == [
        ('lmts.reference.memory.copy_4mib', 1, 2),
        ('lmts.reference.memory.copy_4mib', 2, 2),
        ('lmts.reference.memory.copy_64mib', 1, 2),
        ('lmts.reference.memory.copy_64mib', 2, 2),
    ]


def test_gpu_reference_emits_backend_boundary_and_completed_tests(monkeypatch) -> None:
    raw_tests = [{
        'benchmark_id': 'gpu.test',
        'label': 'GPU Test',
        'method': 'fake',
        'method_version': 1,
        'status': 'completed',
        'target': {'device_index': 0},
        'metrics': {'value': 1},
    }]
    monkeypatch.setattr(reference, 'run_cuda_reference', lambda: (raw_tests, {'backend': 'fake'}))
    events = []

    result = reference.run_reference_benchmark('gpu', progress=events.append)

    assert result.domain == 'gpu'
    assert [event.phase for event in events] == [
        'suite_started',
        'backend_started',
        'backend_completed',
        'test_completed',
        'suite_completed',
    ]
    assert events[3].benchmark_id == 'gpu.test'


def test_npu_reference_emits_backend_boundary_and_completed_tests(monkeypatch) -> None:
    raw_tests = [{
        'benchmark_id': 'npu.test',
        'label': 'NPU Test',
        'method': 'fake',
        'method_version': 1,
        'status': 'completed',
        'target': {'device_index': 0},
        'metrics': {'value': 1},
    }]

    class FakeRegistry:
        @staticmethod
        def benchmark():
            return raw_tests, {'backend': 'fake'}

    monkeypatch.setattr(reference, 'DEFAULT_NPU_REFERENCE_REGISTRY', FakeRegistry())
    events = []

    result = reference.run_reference_benchmark('npu', progress=events.append)

    assert result.domain == 'npu'
    assert [event.phase for event in events] == [
        'suite_started',
        'backend_started',
        'backend_completed',
        'test_completed',
        'suite_completed',
    ]
    assert events[3].benchmark_id == 'npu.test'


def test_progress_callback_failure_aborts_benchmark(monkeypatch) -> None:
    _shrink_cpu(monkeypatch)

    def fail_on_sample(event) -> None:
        if event.phase == 'sample_completed':
            raise RuntimeError('progress sink failed')

    try:
        reference.run_reference_benchmark('cpu', progress=fail_on_sample)
    except RuntimeError as exc:
        assert str(exc) == 'progress sink failed'
    else:
        raise AssertionError('progress callback failure must not be swallowed')
