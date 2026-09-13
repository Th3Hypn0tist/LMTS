from __future__ import annotations

from unittest.mock import patch

from lmts.tools import reference_benchmark as reference


def test_empty_reference_benchmarks_has_all_domains() -> None:
    payload = reference.empty_reference_benchmarks()
    assert payload["schema_version"] == reference.REFERENCE_BENCHMARK_SCHEMA_VERSION
    assert {key for key in payload if key != "schema_version"} == {"cpu", "memory", "gpu", "npu"}
    assert reference.validate_reference_benchmarks(payload)


def test_cpu_reference_suite_records_multiple_tests() -> None:
    with (
        patch.object(reference, "_CPU_CHUNK_BYTES", 1024),
        patch.object(reference, "_CPU_SINGLE_REPEATS_PER_SAMPLE", 2),
        patch.object(reference, "_CPU_PARALLEL_REPEATS_PER_WORKER", 1),
        patch.object(reference, "_CPU_SAMPLE_COUNT", 2),
        patch.object(reference, "_CPU_WARMUP_REPEATS", 1),
        patch.object(reference.os, "cpu_count", return_value=2),
    ):
        result = reference.run_cpu_reference_benchmark().to_dict()

    assert result["domain"] == "cpu"
    assert result["suite_id"] == "lmts.reference.cpu"
    assert result["suite_version"] == 1
    assert result["status"] == "completed"
    assert len(result["tests"]) == 2
    ids = {test["benchmark_id"] for test in result["tests"]}
    assert ids == {
        "lmts.reference.cpu.sha256_stream_1t",
        "lmts.reference.cpu.sha256_stream_all_threads",
    }
    for test in result["tests"]:
        assert test["metrics"]["sample_count"] == 2
        assert len(test["metrics"]["sample_seconds"]) == 2
        assert test["metrics"]["throughput_bytes_per_second"] > 0
    assert result["summary"]["single_thread_bytes_per_second"] > 0
    assert result["summary"]["all_threads_bytes_per_second"] > 0
    assert result["summary"]["parallel_scaling_factor"] > 0
    assert reference.validate_reference_benchmarks({
        "schema_version": reference.REFERENCE_BENCHMARK_SCHEMA_VERSION,
        "cpu": result,
        "memory": None,
        "gpu": None,
        "npu": None,
    })


def test_memory_reference_suite_records_multiple_working_sets() -> None:
    with (
        patch.object(reference, "_MEMORY_SMALL_WORKING_SET_BYTES", 4096),
        patch.object(reference, "_MEMORY_SMALL_REPEATS_PER_SAMPLE", 2),
        patch.object(reference, "_MEMORY_LARGE_WORKING_SET_BYTES", 8192),
        patch.object(reference, "_MEMORY_LARGE_REPEATS_PER_SAMPLE", 2),
        patch.object(reference, "_MEMORY_SAMPLE_COUNT", 2),
        patch.object(reference, "_MEMORY_WARMUP_REPEATS", 1),
    ):
        result = reference.run_memory_reference_benchmark().to_dict()

    assert result["domain"] == "memory"
    assert result["suite_id"] == "lmts.reference.memory"
    assert result["suite_version"] == 1
    assert result["status"] == "completed"
    assert len(result["tests"]) == 2
    ids = {test["benchmark_id"] for test in result["tests"]}
    assert ids == {
        "lmts.reference.memory.copy_4mib",
        "lmts.reference.memory.copy_64mib",
    }
    for test in result["tests"]:
        assert test["metrics"]["sample_count"] == 2
        assert len(test["metrics"]["sample_seconds"]) == 2
        assert test["metrics"]["throughput_bytes_per_second"] > 0
        assert test["metrics"]["verification_byte"] == 0xA5


def test_gpu_and_npu_do_not_fabricate_results() -> None:
    for domain in ("gpu", "npu"):
        try:
            reference.run_reference_benchmark(domain)
        except NotImplementedError:
            continue
        raise AssertionError(f"{domain} benchmark fabricated a result")
