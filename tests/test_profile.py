from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from lmts.tools.profile import (
    PROFILE_SCHEMA_VERSION,
    SystemProfile,
    load_system_profile,
    save_reference_benchmark,
    save_system_profile,
    scan_system_profile,
)
from lmts.tools.reference_benchmark import (
    REFERENCE_BENCHMARK_SCHEMA_VERSION,
    ReferenceBenchmarkSuiteResult,
    ReferenceBenchmarkTestResult,
)


def test_profile_has_core_sections() -> None:
    profile = scan_system_profile().to_dict()
    assert set(profile) == {"cpu", "memory", "gpu", "npu", "software"}
    assert "logical_cores" in profile["cpu"]
    assert "total_bytes" in profile["memory"]


def _test_profile() -> SystemProfile:
    return SystemProfile(
        cpu={"architecture": "x86_64", "model_name": "Test CPU", "logical_cores": 8},
        memory={"total_bytes": 16 * 1024 ** 3},
        software={"os": "TestOS", "python": "3.13"},
    )


def _cpu_reference() -> dict[str, object]:
    test = ReferenceBenchmarkTestResult(
        benchmark_id="lmts.reference.cpu.sha256_stream_1t",
        label="SHA-256 stream 1T",
        method="sha256_stream",
        method_version=1,
        metrics={"throughput_bytes_per_second": 123.0, "sample_seconds": [1.0]},
    )
    return ReferenceBenchmarkSuiteResult(
        domain="cpu",
        suite_id="lmts.reference.cpu",
        suite_version=1,
        measured_at="2026-09-13T20:00:00+03:00",
        tests=[test],
        summary={"single_thread_bytes_per_second": 123.0},
        environment={"python": "3.13"},
    ).to_dict()


def test_saved_profile_contains_empty_reference_contract(tmp_path: Path) -> None:
    profile = _test_profile()
    path = tmp_path / "profile.json"
    with patch("lmts.tools.profile.scan_system_profile", return_value=profile):
        save_system_profile(profile, path)
        payload = load_system_profile(path)

    assert payload is not None
    assert payload["schema_version"] == PROFILE_SCHEMA_VERSION
    references = payload["reference_benchmarks"]
    assert references["schema_version"] == REFERENCE_BENCHMARK_SCHEMA_VERSION
    assert references["cpu"] is None
    assert references["memory"] is None
    assert references["gpu"] is None
    assert references["npu"] is None


def test_reference_suite_survives_same_hardware_rescan(tmp_path: Path) -> None:
    profile = _test_profile()
    path = tmp_path / "profile.json"
    with patch("lmts.tools.profile.scan_system_profile", return_value=profile):
        save_system_profile(profile, path)
        save_reference_benchmark("cpu", _cpu_reference(), path)
        save_system_profile(profile, path)
        payload = load_system_profile(path)

    assert payload is not None
    cpu_suite = payload["reference_benchmarks"]["cpu"]
    assert cpu_suite["suite_id"] == "lmts.reference.cpu"
    assert cpu_suite["tests"][0]["benchmark_id"] == "lmts.reference.cpu.sha256_stream_1t"
