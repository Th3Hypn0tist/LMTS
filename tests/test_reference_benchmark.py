from __future__ import annotations

from unittest.mock import patch

from lmts.tools import reference_benchmark as reference


def test_empty_reference_benchmarks_has_all_domains() -> None:
    payload = reference.empty_reference_benchmarks()
    assert payload["schema_version"] == reference.REFERENCE_BENCHMARK_SCHEMA_VERSION
    assert {key for key in payload if key != "schema_version"} == {"cpu", "memory", "gpu", "npu"}
    assert reference.validate_reference_benchmarks(payload)


def test_cpu_reference_benchmark_records_raw_metrics() -> None:
    with patch.object(reference, "_CPU_CHUNK_BYTES", 1024), patch.object(reference, "_CPU_REPEATS_PER_SAMPLE", 2), patch.object(reference, "_CPU_SAMPLE_COUNT", 2), patch.object(reference, "_CPU_WARMUP_REPEATS", 1):
        result = reference.run_cpu_reference_benchmark().to_dict()

    assert result["domain"] == "cpu"
    assert result["benchmark_id"] == "lmts.reference.cpu.sha256_stream"
    assert result["method_version"] == 1
    assert result["status"] == "completed"
    assert result["metrics"]["sample_count"] == 2
    assert len(result["metrics"]["sample_seconds"]) == 2
    assert result["metrics"]["throughput_bytes_per_second"] > 0
    assert result["metrics"]["digest_sha256"]


def test_memory_reference_benchmark_records_raw_metrics() -> None:
    with patch.object(reference, "_MEMORY_WORKING_SET_BYTES", 4096), patch.object(reference, "_MEMORY_REPEATS_PER_SAMPLE", 2), patch.object(reference, "_MEMORY_SAMPLE_COUNT", 2), patch.object(reference, "_MEMORY_WARMUP_REPEATS", 1):
        result = reference.run_memory_reference_benchmark().to_dict()

    assert result["domain"] == "memory"
    assert result["benchmark_id"] == "lmts.reference.memory.copy_slice"
    assert result["method_version"] == 1
    assert result["status"] == "completed"
    assert result["metrics"]["sample_count"] == 2
    assert len(result["metrics"]["sample_seconds"]) == 2
    assert result["metrics"]["throughput_bytes_per_second"] > 0
    assert result["metrics"]["verification_byte"] == 0xA5


def test_gpu_and_npu_do_not_fabricate_results() -> None:
    for domain in ("gpu", "npu"):
        try:
            reference.run_reference_benchmark(domain)
        except NotImplementedError:
            continue
        raise AssertionError(f"{domain} benchmark fabricated a result")
