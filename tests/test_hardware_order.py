from __future__ import annotations

from lmts.core.hardware_order import (
    build_hardware_order_profile,
    hardware_order_relation,
)


def _references(*, cpu=100.0, memory=100.0, gpu=None):
    return {
        'schema_version': 3,
        'cpu': {
            'domain': 'cpu',
            'suite_id': 'lmts.reference.cpu',
            'suite_version': 1,
            'measured_at': '2026-09-28T00:00:00+00:00',
            'status': 'completed',
            'tests': [{'benchmark_id': 'cpu', 'label': 'cpu', 'method': 'cpu', 'method_version': 1, 'status': 'completed', 'target': None, 'metrics': {}}],
            'summary': {
                'single_thread_bytes_per_second': cpu,
                'all_threads_bytes_per_second': cpu,
            },
            'environment': {},
        },
        'memory': {
            'domain': 'memory',
            'suite_id': 'lmts.reference.memory',
            'suite_version': 1,
            'measured_at': '2026-09-28T00:00:00+00:00',
            'status': 'completed',
            'tests': [{'benchmark_id': 'memory', 'label': 'memory', 'method': 'memory', 'method_version': 1, 'status': 'completed', 'target': None, 'metrics': {}}],
            'summary': {
                'copy_4mib_bytes_per_second': memory,
                'copy_64mib_bytes_per_second': memory,
            },
            'environment': {},
        },
        'gpu': gpu,
        'npu': None,
    }


def _profile(*, ram=16, gpu_vram=None):
    gpus = [] if gpu_vram is None else [{
        'vendor': 'NVIDIA',
        'model': 'Test GPU',
        'vram_bytes': gpu_vram,
    }]
    return {
        'cpu': {'architecture': 'x86_64'},
        'memory': {'total_bytes': ram},
        'gpu': gpus,
        'npu': [],
    }


def _gpu_reference(scale: float = 1.0):
    tests = []
    for benchmark_id, metric_name in (
        ('lmts.reference.gpu.d2d', 'throughput_bytes_per_second'),
        ('lmts.reference.gpu.h2d_pinned', 'throughput_bytes_per_second'),
        ('lmts.reference.gpu.d2h_pinned', 'throughput_bytes_per_second'),
        ('lmts.reference.gpu.fma_fp32', 'operations_per_second'),
    ):
        tests.append({
            'benchmark_id': benchmark_id,
            'label': benchmark_id,
            'method': benchmark_id,
            'method_version': 1,
            'status': 'completed',
            'target': {'device_index': 0, 'vendor': 'NVIDIA', 'model': 'Test GPU'},
            'metrics': {metric_name: 100.0 * scale},
        })
    return {
        'domain': 'gpu',
        'suite_id': 'lmts.reference.gpu',
        'suite_version': 1,
        'measured_at': '2026-09-28T00:00:00+00:00',
        'status': 'completed',
        'tests': tests,
        'summary': {'device_count': 1},
        'environment': {},
    }


def test_order_profile_is_incomplete_without_required_reference_axes() -> None:
    order = build_hardware_order_profile(
        _profile(ram=16),
        {'schema_version': 3, 'cpu': None, 'memory': None, 'gpu': None, 'npu': None},
    )

    assert order['status'] == 'incomplete'
    assert 'cpu.single_thread_bytes_per_second' in order['missing']
    assert 'memory.copy_64mib_bytes_per_second' in order['missing']


def test_cpu_memory_only_profiles_form_partial_order() -> None:
    lower = build_hardware_order_profile(_profile(ram=16), _references(cpu=100, memory=100))
    higher = build_hardware_order_profile(_profile(ram=32), _references(cpu=120, memory=110))

    relation = hardware_order_relation(lower, higher)

    assert relation.comparable is True
    assert relation.lower_or_equal is True
    assert relation.strict is True


def test_crossed_capabilities_are_comparable_but_not_dominating() -> None:
    lower = build_hardware_order_profile(_profile(ram=16), _references(cpu=120, memory=100))
    candidate_higher = build_hardware_order_profile(_profile(ram=32), _references(cpu=100, memory=120))

    relation = hardware_order_relation(lower, candidate_higher)

    assert relation.comparable is True
    assert relation.lower_or_equal is False
    assert 'cpu.' in relation.reason


def test_gpu_order_requires_every_required_gpu_axis() -> None:
    incomplete_gpu = {
        **_gpu_reference(),
        'tests': _gpu_reference()['tests'][:-1],
    }
    order = build_hardware_order_profile(
        _profile(ram=16, gpu_vram=8),
        _references(gpu=incomplete_gpu),
    )

    assert order['status'] == 'incomplete'
    assert any('fma_fp32' in item for item in order['missing'])


def test_gpu_dominance_requires_vram_and_all_gpu_reference_axes() -> None:
    lower = build_hardware_order_profile(
        _profile(ram=16, gpu_vram=8),
        _references(cpu=100, memory=100, gpu=_gpu_reference(1.0)),
    )
    higher = build_hardware_order_profile(
        _profile(ram=32, gpu_vram=16),
        _references(cpu=110, memory=110, gpu=_gpu_reference(1.2)),
    )

    relation = hardware_order_relation(lower, higher)

    assert relation.lower_or_equal is True
    assert relation.strict is True


def test_architecture_mismatch_is_explicitly_incomparable() -> None:
    lower = build_hardware_order_profile(_profile(ram=16), _references())
    higher_profile = _profile(ram=32)
    higher_profile['cpu']['architecture'] = 'aarch64'
    higher = build_hardware_order_profile(higher_profile, _references(cpu=200, memory=200))

    relation = hardware_order_relation(lower, higher)

    assert relation.comparable is False
    assert relation.reason == 'architecture mismatch'
