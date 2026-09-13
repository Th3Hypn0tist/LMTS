from __future__ import annotations

from unittest.mock import patch

from lmts.tools import reference_benchmark as reference
from lmts.tools.cuda_reference import CudaUnavailable
from lmts.tools.npu_reference import NPUUnavailable


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
    assert len(result["tests"]) == 2
    ids = {test["benchmark_id"] for test in result["tests"]}
    assert ids == {"lmts.reference.cpu.sha256_stream_1t", "lmts.reference.cpu.sha256_stream_all_threads"}
    assert all(test["target"] is None for test in result["tests"])
    assert result["summary"]["parallel_scaling_factor"] > 0


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
    assert len(result["tests"]) == 2
    assert all(test["target"] is None for test in result["tests"])
    assert all(test["metrics"]["verification_byte"] == 0xA5 for test in result["tests"])


def test_gpu_reference_preserves_device_target_identity() -> None:
    raw_tests = [{
        "benchmark_id": "lmts.reference.gpu.d2d",
        "label": "Device to device copy",
        "method": "cuda_memcpy_d2d",
        "method_version": 1,
        "status": "completed",
        "target": {"device_index": 0, "vendor": "NVIDIA", "model": "Test GPU", "uuid": "abc"},
        "metrics": {"throughput_gib_per_second": 123.0},
    }]
    with patch.object(reference, "run_cuda_reference", return_value=(raw_tests, {"backend": "cuda_driver_api"})):
        result = reference.run_gpu_reference_benchmark().to_dict()
    assert result["tests"][0]["target"]["uuid"] == "abc"
    assert result["summary"]["device_count"] == 1
    assert reference.validate_reference_benchmarks({
        "schema_version": reference.REFERENCE_BENCHMARK_SCHEMA_VERSION,
        "cpu": None,
        "memory": None,
        "gpu": result,
        "npu": None,
    })


def test_unavailable_accelerators_do_not_fabricate_results() -> None:
    with patch.object(reference, "run_cuda_reference", side_effect=CudaUnavailable("no CUDA")):
        try:
            reference.run_gpu_reference_benchmark()
        except NotImplementedError as exc:
            assert "no CUDA" in str(exc)
        else:
            raise AssertionError("GPU benchmark fabricated a result")

    with patch.object(reference.DEFAULT_NPU_REFERENCE_REGISTRY, "benchmark", side_effect=NPUUnavailable("no NPU")):
        try:
            reference.run_npu_reference_benchmark()
        except NotImplementedError as exc:
            assert "no NPU" in str(exc)
        else:
            raise AssertionError("NPU benchmark fabricated a result")
