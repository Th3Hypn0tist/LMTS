from __future__ import annotations

import hashlib
import platform
import statistics
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime

REFERENCE_BENCHMARK_SCHEMA_VERSION = 1
REFERENCE_BENCHMARK_DOMAINS = ("cpu", "memory", "gpu", "npu")

_CPU_CHUNK_BYTES = 1024 * 1024
_CPU_REPEATS_PER_SAMPLE = 256
_CPU_SAMPLE_COUNT = 5
_CPU_WARMUP_REPEATS = 32

_MEMORY_WORKING_SET_BYTES = 64 * 1024 * 1024
_MEMORY_REPEATS_PER_SAMPLE = 16
_MEMORY_SAMPLE_COUNT = 5
_MEMORY_WARMUP_REPEATS = 2


@dataclass(slots=True)
class ReferenceBenchmarkResult:
    domain: str
    benchmark_id: str
    method: str
    method_version: int
    measured_at: str
    status: str = "completed"
    metrics: dict[str, object] = field(default_factory=dict)
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
        result = value.get(domain)
        if result is not None and not _valid_result(result, domain):
            return False
    return True


def _valid_result(value: object, domain: str) -> bool:
    if not isinstance(value, dict):
        return False
    if value.get("domain") != domain or value.get("status") != "completed":
        return False
    if not isinstance(value.get("benchmark_id"), str) or not value.get("benchmark_id"):
        return False
    if not isinstance(value.get("method"), str) or not value.get("method"):
        return False
    if not isinstance(value.get("method_version"), int) or int(value.get("method_version")) < 1:
        return False
    if not isinstance(value.get("measured_at"), str) or not value.get("measured_at"):
        return False
    return isinstance(value.get("metrics"), dict) and isinstance(value.get("environment"), dict)


def _measured_at() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


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


def run_cpu_reference_benchmark() -> ReferenceBenchmarkResult:
    chunk = bytes((index % 251 for index in range(_CPU_CHUNK_BYTES)))

    warmup = hashlib.sha256()
    for _ in range(_CPU_WARMUP_REPEATS):
        warmup.update(chunk)
    warmup.digest()

    durations: list[float] = []
    digest_hex = ""
    for _ in range(_CPU_SAMPLE_COUNT):
        digest = hashlib.sha256()
        started = time.perf_counter()
        for _ in range(_CPU_REPEATS_PER_SAMPLE):
            digest.update(chunk)
        digest_hex = digest.hexdigest()
        durations.append(time.perf_counter() - started)

    bytes_per_sample = _CPU_CHUNK_BYTES * _CPU_REPEATS_PER_SAMPLE
    metrics = _throughput_metrics(durations, bytes_per_sample)
    metrics.update({
        "chunk_bytes": _CPU_CHUNK_BYTES,
        "repeats_per_sample": _CPU_REPEATS_PER_SAMPLE,
        "digest_sha256": digest_hex,
    })
    return ReferenceBenchmarkResult(
        domain="cpu",
        benchmark_id="lmts.reference.cpu.sha256_stream",
        method="sha256_stream",
        method_version=1,
        measured_at=_measured_at(),
        metrics=metrics,
        environment={
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "architecture": platform.machine() or None,
        },
    )


def run_memory_reference_benchmark() -> ReferenceBenchmarkResult:
    source = b"\xa5" * _MEMORY_WORKING_SET_BYTES
    target = bytearray(_MEMORY_WORKING_SET_BYTES)

    for _ in range(_MEMORY_WARMUP_REPEATS):
        target[:] = source

    durations: list[float] = []
    for _ in range(_MEMORY_SAMPLE_COUNT):
        started = time.perf_counter()
        for _ in range(_MEMORY_REPEATS_PER_SAMPLE):
            target[:] = source
        durations.append(time.perf_counter() - started)

    bytes_per_sample = _MEMORY_WORKING_SET_BYTES * _MEMORY_REPEATS_PER_SAMPLE
    metrics = _throughput_metrics(durations, bytes_per_sample)
    metrics.update({
        "working_set_bytes": _MEMORY_WORKING_SET_BYTES,
        "repeats_per_sample": _MEMORY_REPEATS_PER_SAMPLE,
        "verification_byte": target[0] if target else None,
    })
    return ReferenceBenchmarkResult(
        domain="memory",
        benchmark_id="lmts.reference.memory.copy_slice",
        method="copy_slice",
        method_version=1,
        measured_at=_measured_at(),
        metrics=metrics,
        environment={
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "architecture": platform.machine() or None,
        },
    )


def run_reference_benchmark(domain: str) -> ReferenceBenchmarkResult:
    normalized = domain.strip().casefold()
    if normalized == "cpu":
        return run_cpu_reference_benchmark()
    if normalized == "memory":
        return run_memory_reference_benchmark()
    if normalized in {"gpu", "npu"}:
        raise NotImplementedError(f"{normalized.upper()} reference benchmark is not implemented yet")
    raise ValueError(f"unknown reference benchmark domain: {domain}")
