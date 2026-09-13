from __future__ import annotations

import hashlib
import json
import os
import platform
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime

from .cuda_reference import CudaUnavailable, run_cuda_reference
from .npu_reference import DEFAULT_NPU_REFERENCE_REGISTRY, NPUUnavailable

REFERENCE_BENCHMARK_SCHEMA_VERSION = 3
REFERENCE_BENCHMARK_DOMAINS = ("cpu", "memory", "gpu", "npu")

_CPU_CHUNK_BYTES = 1024 * 1024
_CPU_SINGLE_REPEATS_PER_SAMPLE = 256
_CPU_PARALLEL_REPEATS_PER_WORKER = 16
_CPU_SAMPLE_COUNT = 5
_CPU_WARMUP_REPEATS = 32

_MEMORY_SMALL_WORKING_SET_BYTES = 4 * 1024 * 1024
_MEMORY_SMALL_REPEATS_PER_SAMPLE = 128
_MEMORY_LARGE_WORKING_SET_BYTES = 64 * 1024 * 1024
_MEMORY_LARGE_REPEATS_PER_SAMPLE = 16
_MEMORY_SAMPLE_COUNT = 5
_MEMORY_WARMUP_REPEATS = 2


@dataclass(slots=True)
class ReferenceBenchmarkTestResult:
    benchmark_id: str
    label: str
    method: str
    method_version: int
    status: str = "completed"
    target: dict[str, object] | None = None
    metrics: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class ReferenceBenchmarkSuiteResult:
    domain: str
    suite_id: str
    suite_version: int
    measured_at: str
    status: str = "completed"
    tests: list[ReferenceBenchmarkTestResult] = field(default_factory=list)
    summary: dict[str, object] = field(default_factory=dict)
    environment: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def empty_reference_benchmarks() -> dict[str, object]:
    return {
        "schema_version": REFERENCE_BENCHMARK_SCHEMA_VERSION,
        **{domain: None for domain in REFERENCE_BENCHMARK_DOMAINS},
    }


def validate_reference_benchmarks(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    if value.get("schema_version") != REFERENCE_BENCHMARK_SCHEMA_VERSION:
        return False
    for domain in REFERENCE_BENCHMARK_DOMAINS:
        if domain not in value:
            return False
        suite = value.get(domain)
        if suite is not None and not _valid_suite(suite, domain):
            return False
    return True


def _target_key(value: object) -> str:
    if value is None:
        return ""
    if not isinstance(value, dict):
        return "!invalid"
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _valid_suite(value: object, domain: str) -> bool:
    if not isinstance(value, dict):
        return False
    if value.get("domain") != domain or value.get("status") != "completed":
        return False
    if not isinstance(value.get("suite_id"), str) or not value.get("suite_id"):
        return False
    if not isinstance(value.get("suite_version"), int) or int(value.get("suite_version")) < 1:
        return False
    if not isinstance(value.get("measured_at"), str) or not value.get("measured_at"):
        return False
    tests = value.get("tests")
    if not isinstance(tests, list) or not tests:
        return False
    if not all(_valid_test_result(test) for test in tests):
        return False
    keys = [
        (test.get("benchmark_id"), _target_key(test.get("target")))
        for test in tests
        if isinstance(test, dict)
    ]
    if len(set(keys)) != len(keys):
        return False
    return isinstance(value.get("summary"), dict) and isinstance(value.get("environment"), dict)


def _valid_test_result(value: object) -> bool:
    if not isinstance(value, dict) or value.get("status") != "completed":
        return False
    if not isinstance(value.get("benchmark_id"), str) or not value.get("benchmark_id"):
        return False
    if not isinstance(value.get("label"), str) or not value.get("label"):
        return False
    if not isinstance(value.get("method"), str) or not value.get("method"):
        return False
    if not isinstance(value.get("method_version"), int) or int(value.get("method_version")) < 1:
        return False
    target = value.get("target")
    if target is not None and not isinstance(target, dict):
        return False
    return isinstance(value.get("metrics"), dict)


def _measured_at() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _environment() -> dict[str, object]:
    return {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "architecture": platform.machine() or None,
        "logical_cores": os.cpu_count(),
    }


def _throughput_metrics(durations: list[float], bytes_per_sample: int) -> dict[str, object]:
    median_seconds = statistics.median(durations)
    throughput = bytes_per_sample / median_seconds
    return {
        "sample_count": len(durations),
        "sample_seconds": durations,
        "median_seconds": median_seconds,
        "bytes_per_sample": bytes_per_sample,
        "throughput_bytes_per_second": throughput,
        "throughput_gib_per_second": throughput / (1024 ** 3),
    }


def _sha256_digest(chunk: bytes, repeats: int) -> str:
    digest = hashlib.sha256()
    for _ in range(repeats):
        digest.update(chunk)
    return digest.hexdigest()


def _cpu_single_thread_test(chunk: bytes) -> ReferenceBenchmarkTestResult:
    _sha256_digest(chunk, _CPU_WARMUP_REPEATS)
    durations: list[float] = []
    digest_hex = ""
    for _ in range(_CPU_SAMPLE_COUNT):
        started = time.perf_counter()
        digest_hex = _sha256_digest(chunk, _CPU_SINGLE_REPEATS_PER_SAMPLE)
        durations.append(time.perf_counter() - started)
    metrics = _throughput_metrics(durations, _CPU_CHUNK_BYTES * _CPU_SINGLE_REPEATS_PER_SAMPLE)
    metrics.update({"threads": 1, "chunk_bytes": _CPU_CHUNK_BYTES, "repeats_per_sample": _CPU_SINGLE_REPEATS_PER_SAMPLE, "digest_sha256": digest_hex})
    return ReferenceBenchmarkTestResult("lmts.reference.cpu.sha256_stream_1t", "SHA-256 stream 1T", "sha256_stream", 1, metrics=metrics)


def _cpu_parallel_test(chunk: bytes) -> ReferenceBenchmarkTestResult:
    workers = max(1, os.cpu_count() or 1)
    _sha256_digest(chunk, _CPU_WARMUP_REPEATS)
    durations: list[float] = []
    digests: list[str] = []
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="lmts-ref-cpu") as executor:
        for _ in range(_CPU_SAMPLE_COUNT):
            started = time.perf_counter()
            futures = [executor.submit(_sha256_digest, chunk, _CPU_PARALLEL_REPEATS_PER_WORKER) for _ in range(workers)]
            digests = [future.result() for future in futures]
            durations.append(time.perf_counter() - started)
    bytes_per_sample = _CPU_CHUNK_BYTES * _CPU_PARALLEL_REPEATS_PER_WORKER * workers
    metrics = _throughput_metrics(durations, bytes_per_sample)
    metrics.update({"threads": workers, "chunk_bytes": _CPU_CHUNK_BYTES, "repeats_per_worker": _CPU_PARALLEL_REPEATS_PER_WORKER, "digest_sha256": digests[0] if digests else ""})
    return ReferenceBenchmarkTestResult("lmts.reference.cpu.sha256_stream_all_threads", "SHA-256 stream all threads", "sha256_stream_parallel", 1, metrics=metrics)


def run_cpu_reference_benchmark() -> ReferenceBenchmarkSuiteResult:
    chunk = bytes((index % 251 for index in range(_CPU_CHUNK_BYTES)))
    single = _cpu_single_thread_test(chunk)
    parallel = _cpu_parallel_test(chunk)
    single_rate = float(single.metrics["throughput_bytes_per_second"])
    parallel_rate = float(parallel.metrics["throughput_bytes_per_second"])
    return ReferenceBenchmarkSuiteResult(
        domain="cpu", suite_id="lmts.reference.cpu", suite_version=1, measured_at=_measured_at(), tests=[single, parallel],
        summary={"single_thread_bytes_per_second": single_rate, "all_threads_bytes_per_second": parallel_rate, "parallel_scaling_factor": parallel_rate / single_rate if single_rate > 0 else None},
        environment=_environment(),
    )


def _memory_copy_test(*, benchmark_id: str, label: str, working_set_bytes: int, repeats_per_sample: int) -> ReferenceBenchmarkTestResult:
    source = b"\xa5" * working_set_bytes
    target = bytearray(working_set_bytes)
    for _ in range(_MEMORY_WARMUP_REPEATS):
        target[:] = source
    durations: list[float] = []
    for _ in range(_MEMORY_SAMPLE_COUNT):
        started = time.perf_counter()
        for _ in range(repeats_per_sample):
            target[:] = source
        durations.append(time.perf_counter() - started)
    metrics = _throughput_metrics(durations, working_set_bytes * repeats_per_sample)
    metrics.update({"working_set_bytes": working_set_bytes, "repeats_per_sample": repeats_per_sample, "verification_byte": target[0] if target else None})
    return ReferenceBenchmarkTestResult(benchmark_id, label, "copy_slice", 1, metrics=metrics)


def run_memory_reference_benchmark() -> ReferenceBenchmarkSuiteResult:
    small = _memory_copy_test(benchmark_id="lmts.reference.memory.copy_4mib", label="Copy 4 MiB working set", working_set_bytes=_MEMORY_SMALL_WORKING_SET_BYTES, repeats_per_sample=_MEMORY_SMALL_REPEATS_PER_SAMPLE)
    large = _memory_copy_test(benchmark_id="lmts.reference.memory.copy_64mib", label="Copy 64 MiB working set", working_set_bytes=_MEMORY_LARGE_WORKING_SET_BYTES, repeats_per_sample=_MEMORY_LARGE_REPEATS_PER_SAMPLE)
    return ReferenceBenchmarkSuiteResult(
        domain="memory", suite_id="lmts.reference.memory", suite_version=1, measured_at=_measured_at(), tests=[small, large],
        summary={"copy_4mib_bytes_per_second": small.metrics["throughput_bytes_per_second"], "copy_64mib_bytes_per_second": large.metrics["throughput_bytes_per_second"]},
        environment=_environment(),
    )


def _external_tests(raw_tests: list[dict[str, object]]) -> list[ReferenceBenchmarkTestResult]:
    return [
        ReferenceBenchmarkTestResult(
            benchmark_id=str(item["benchmark_id"]),
            label=str(item["label"]),
            method=str(item["method"]),
            method_version=int(item["method_version"]),
            status=str(item.get("status") or "completed"),
            target=dict(item["target"]) if isinstance(item.get("target"), dict) else None,
            metrics=dict(item.get("metrics") or {}),
        )
        for item in raw_tests
    ]


def run_gpu_reference_benchmark() -> ReferenceBenchmarkSuiteResult:
    try:
        raw_tests, backend_environment = run_cuda_reference()
    except CudaUnavailable as exc:
        raise NotImplementedError(str(exc)) from exc
    tests = _external_tests(raw_tests)
    return ReferenceBenchmarkSuiteResult(
        domain="gpu", suite_id="lmts.reference.gpu", suite_version=1, measured_at=_measured_at(), tests=tests,
        summary={"device_count": len({ _target_key(test.target) for test in tests })},
        environment={**_environment(), **backend_environment},
    )


def run_npu_reference_benchmark() -> ReferenceBenchmarkSuiteResult:
    try:
        raw_tests, backend_environment = DEFAULT_NPU_REFERENCE_REGISTRY.benchmark()
    except NPUUnavailable as exc:
        raise NotImplementedError(str(exc)) from exc
    tests = _external_tests(raw_tests)
    return ReferenceBenchmarkSuiteResult(
        domain="npu", suite_id="lmts.reference.npu", suite_version=1, measured_at=_measured_at(), tests=tests,
        summary={"device_count": len({ _target_key(test.target) for test in tests })},
        environment={**_environment(), **backend_environment},
    )


def run_reference_benchmark(domain: str) -> ReferenceBenchmarkSuiteResult:
    normalized = domain.strip().casefold()
    if normalized == "cpu":
        return run_cpu_reference_benchmark()
    if normalized == "memory":
        return run_memory_reference_benchmark()
    if normalized == "gpu":
        return run_gpu_reference_benchmark()
    if normalized == "npu":
        return run_npu_reference_benchmark()
    raise ValueError(f"unknown reference benchmark domain: {domain}")
