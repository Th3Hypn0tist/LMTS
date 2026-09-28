from __future__ import annotations

from dataclasses import dataclass
from typing import Any


HARDWARE_ORDER_SCHEMA_VERSION = 1
_REQUIRED_CPU_AXES = (
    'single_thread_bytes_per_second',
    'all_threads_bytes_per_second',
)
_REQUIRED_MEMORY_AXES = (
    'copy_4mib_bytes_per_second',
    'copy_64mib_bytes_per_second',
)
_REQUIRED_GPU_BENCHMARKS = {
    'lmts.reference.gpu.d2d': 'throughput_bytes_per_second',
    'lmts.reference.gpu.h2d_pinned': 'throughput_bytes_per_second',
    'lmts.reference.gpu.d2h_pinned': 'throughput_bytes_per_second',
    'lmts.reference.gpu.fma_fp32': 'operations_per_second',
}


@dataclass(frozen=True, slots=True)
class HardwareOrderRelation:
    comparable: bool
    lower_or_equal: bool
    strict: bool
    reason: str


def _positive_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if number > 0 else None


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


def _suite(reference_benchmarks: dict[str, object], domain: str) -> dict[str, object] | None:
    raw = reference_benchmarks.get(domain)
    return raw if isinstance(raw, dict) and raw.get('status') == 'completed' else None


def _gpu_devices(
    profile: dict[str, object],
    reference_benchmarks: dict[str, object],
) -> tuple[list[dict[str, object]], list[str]]:
    gpus = profile.get('gpu') if isinstance(profile.get('gpu'), list) else []
    if not gpus:
        return [], []

    suite = _suite(reference_benchmarks, 'gpu')
    if suite is None:
        return [], ['gpu.reference']

    by_index: dict[int, dict[str, float]] = {}
    tests = suite.get('tests')
    if not isinstance(tests, list):
        return [], ['gpu.reference']

    for test in tests:
        if not isinstance(test, dict):
            continue
        benchmark_id = str(test.get('benchmark_id') or '')
        metric_name = _REQUIRED_GPU_BENCHMARKS.get(benchmark_id)
        if metric_name is None:
            continue
        target = test.get('target') if isinstance(test.get('target'), dict) else {}
        index = target.get('device_index')
        metrics = test.get('metrics') if isinstance(test.get('metrics'), dict) else {}
        value = _positive_number(metrics.get(metric_name))
        if isinstance(index, bool) or not isinstance(index, int) or index < 0 or value is None:
            continue
        by_index.setdefault(index, {})[benchmark_id] = value

    devices: list[dict[str, object]] = []
    missing: list[str] = []
    for index, gpu in enumerate(gpus):
        if not isinstance(gpu, dict):
            missing.append(f'gpu.{index}.profile')
            continue
        vram = _positive_int(gpu.get('vram_bytes'))
        metrics = by_index.get(index, {})
        if vram is None:
            missing.append(f'gpu.{index}.vram_bytes')
        for benchmark_id in _REQUIRED_GPU_BENCHMARKS:
            if benchmark_id not in metrics:
                missing.append(f'gpu.{index}.{benchmark_id}')
        devices.append({
            'index': index,
            'vram_bytes': vram,
            'metrics': {
                benchmark_id: metrics.get(benchmark_id)
                for benchmark_id in sorted(_REQUIRED_GPU_BENCHMARKS)
            },
        })
    return devices, missing


def build_hardware_order_profile(
    profile: dict[str, object],
    reference_benchmarks: dict[str, object] | None,
) -> dict[str, object]:
    references = reference_benchmarks if isinstance(reference_benchmarks, dict) else {}
    cpu = profile.get('cpu') if isinstance(profile.get('cpu'), dict) else {}
    memory = profile.get('memory') if isinstance(profile.get('memory'), dict) else {}
    npu = profile.get('npu') if isinstance(profile.get('npu'), list) else []

    architecture = str(cpu.get('architecture') or '').strip() or None
    system_memory_bytes = _positive_int(memory.get('total_bytes'))

    cpu_suite = _suite(references, 'cpu')
    cpu_summary = cpu_suite.get('summary') if isinstance(cpu_suite, dict) and isinstance(cpu_suite.get('summary'), dict) else {}
    memory_suite = _suite(references, 'memory')
    memory_summary = memory_suite.get('summary') if isinstance(memory_suite, dict) and isinstance(memory_suite.get('summary'), dict) else {}

    scalar_axes: dict[str, float | int | None] = {
        'system_memory_bytes': system_memory_bytes,
        **{f'cpu.{key}': _positive_number(cpu_summary.get(key)) for key in _REQUIRED_CPU_AXES},
        **{f'memory.{key}': _positive_number(memory_summary.get(key)) for key in _REQUIRED_MEMORY_AXES},
    }

    missing: list[str] = []
    if architecture is None:
        missing.append('architecture')
    for key, value in scalar_axes.items():
        if value is None:
            missing.append(key)

    gpu_devices, gpu_missing = _gpu_devices(profile, references)
    missing.extend(gpu_missing)

    if npu:
        missing.append('npu.ordering.v1.unsupported')

    return {
        'schema_version': HARDWARE_ORDER_SCHEMA_VERSION,
        'status': 'complete' if not missing else 'incomplete',
        'architecture': architecture,
        'scalar_axes': scalar_axes,
        'gpu_devices': gpu_devices,
        'missing': sorted(set(missing)),
    }


def _device_dominates(higher: dict[str, object], lower: dict[str, object]) -> tuple[bool, bool]:
    high_vram = _positive_int(higher.get('vram_bytes'))
    low_vram = _positive_int(lower.get('vram_bytes'))
    if high_vram is None or low_vram is None or high_vram < low_vram:
        return False, False
    strict = high_vram > low_vram

    high_metrics = higher.get('metrics') if isinstance(higher.get('metrics'), dict) else {}
    low_metrics = lower.get('metrics') if isinstance(lower.get('metrics'), dict) else {}
    for benchmark_id in _REQUIRED_GPU_BENCHMARKS:
        high = _positive_number(high_metrics.get(benchmark_id))
        low = _positive_number(low_metrics.get(benchmark_id))
        if high is None or low is None or high < low:
            return False, False
        strict = strict or high > low
    return True, strict


def _match_gpu_devices(
    higher: list[dict[str, object]],
    lower: list[dict[str, object]],
) -> tuple[bool, bool]:
    if len(higher) < len(lower):
        return False, False
    used: set[int] = set()

    def search(position: int, strict_so_far: bool) -> tuple[bool, bool]:
        if position >= len(lower):
            return True, strict_so_far or len(higher) > len(lower)
        low = lower[position]
        for index, high in enumerate(higher):
            if index in used:
                continue
            dominates, strict = _device_dominates(high, low)
            if not dominates:
                continue
            used.add(index)
            ok, final_strict = search(position + 1, strict_so_far or strict)
            used.remove(index)
            if ok:
                return True, final_strict
        return False, False

    return search(0, False)


def hardware_order_relation(
    lower: dict[str, object],
    higher: dict[str, object],
) -> HardwareOrderRelation:
    if lower.get('schema_version') != HARDWARE_ORDER_SCHEMA_VERSION or higher.get('schema_version') != HARDWARE_ORDER_SCHEMA_VERSION:
        return HardwareOrderRelation(False, False, False, 'ordering schema mismatch')
    if lower.get('status') != 'complete' or higher.get('status') != 'complete':
        return HardwareOrderRelation(False, False, False, 'ordering evidence incomplete')
    if lower.get('architecture') != higher.get('architecture'):
        return HardwareOrderRelation(False, False, False, 'architecture mismatch')

    low_axes = lower.get('scalar_axes') if isinstance(lower.get('scalar_axes'), dict) else {}
    high_axes = higher.get('scalar_axes') if isinstance(higher.get('scalar_axes'), dict) else {}
    strict = False
    for key in sorted(set(low_axes) | set(high_axes)):
        low = _positive_number(low_axes.get(key))
        high = _positive_number(high_axes.get(key))
        if low is None or high is None:
            return HardwareOrderRelation(False, False, False, f'missing scalar axis: {key}')
        if high < low:
            return HardwareOrderRelation(True, False, False, f'higher configuration is weaker on {key}')
        strict = strict or high > low

    low_gpu = lower.get('gpu_devices') if isinstance(lower.get('gpu_devices'), list) else []
    high_gpu = higher.get('gpu_devices') if isinstance(higher.get('gpu_devices'), list) else []
    if not all(isinstance(item, dict) for item in low_gpu + high_gpu):
        return HardwareOrderRelation(False, False, False, 'invalid gpu ordering evidence')
    gpu_ok, gpu_strict = _match_gpu_devices(high_gpu, low_gpu)
    if not gpu_ok:
        return HardwareOrderRelation(True, False, False, 'higher configuration does not dominate lower GPU resources')
    strict = strict or gpu_strict
    return HardwareOrderRelation(True, True, strict, 'dominates' if strict else 'capability-equivalent')
