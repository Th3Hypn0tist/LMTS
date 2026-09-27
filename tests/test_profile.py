from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from lmts.tools.profile import (
    GPUProfile,
    PROFILE_SCHEMA_VERSION,
    SystemProfile,
    _nvidia_gpus,
    _system_memory_profile,
    load_system_profile,
    save_reference_benchmark,
    save_system_profile,
    scan_system_profile,
    system_fingerprint,
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
    assert payload["identity"] == {
        "cpu": {
            "architecture": "x86_64",
            "model_name": "Test CPU",
            "model_names": None,
            "vendor_id": None,
            "cpu_family": None,
            "model": None,
            "stepping": None,
            "logical_cores": 8,
            "physical_packages": None,
            "physical_cores": None,
        },
        "memory": {
            "total_bytes": 16 * 1024 ** 3,
            "memory_type": None,
            "ecc": None,
            "speed_mt_s": None,
            "form_factor": None,
            "modules": [],
        },
        "gpu": [],
        "npu": [],
    }
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


def test_system_fingerprint_ignores_software_and_driver_state() -> None:
    first = SystemProfile(
        cpu={"architecture": "x86_64", "model_name": "Test CPU", "logical_cores": 8},
        memory={"total_bytes": 16 * 1024 ** 3},
        gpu=[GPUProfile(vendor="NVIDIA", model="Test GPU", vram_bytes=8 * 1024 ** 3, driver_version="610.1")],
        npu=[{
            "class": "accel",
            "name": "accel0",
            "sysfs_path": "/sys/devices/a",
            "vendor_id": "0x1234",
            "device_id": "0xabcd",
            "subsystem_vendor_id": "0x1111",
            "subsystem_device_id": "0x2222",
            "driver": "driver-a",
            "pci_slot": "0000:01:00.0",
            "modalias": "pci:test",
        }],
        software={"os": "Linux", "os_release": "6.1", "python": "3.13"},
    )
    second = SystemProfile(
        cpu=dict(first.cpu),
        memory=dict(first.memory),
        gpu=[GPUProfile(vendor="NVIDIA", model="Test GPU", vram_bytes=8 * 1024 ** 3, driver_version="999.9")],
        npu=[{
            "class": "accel",
            "name": "accel9",
            "sysfs_path": "/sys/devices/b",
            "vendor_id": "0x1234",
            "device_id": "0xabcd",
            "subsystem_vendor_id": "0x1111",
            "subsystem_device_id": "0x2222",
            "driver": "driver-b",
            "pci_slot": "0000:09:00.0",
            "modalias": "pci:test",
        }],
        software={"os": "OtherOS", "os_release": "99", "python": "3.99"},
    )

    assert system_fingerprint(first) == system_fingerprint(second)



def test_system_memory_profile_parses_smbios_without_guessing() -> None:
    dmidecode = """# dmidecode 3.6
Handle 0x003A, DMI type 16, 23 bytes
Physical Memory Array
	Location: System Board Or Motherboard
	Use: System Memory
	Error Correction Type: Single-bit ECC
	Maximum Capacity: 128 GB
	Number Of Devices: 2

Handle 0x003B, DMI type 17, 92 bytes
Memory Device
	Array Handle: 0x003A
	Total Width: 72 bits
	Data Width: 64 bits
	Size: 32 GB
	Form Factor: DIMM
	Locator: DIMM_A1
	Bank Locator: BANK 0
	Type: DDR5
	Speed: 5600 MT/s
	Manufacturer: Example
	Part Number: EXAMPLE-32G
	Rank: 2
	Configured Memory Speed: 5200 MT/s

Handle 0x003C, DMI type 17, 92 bytes
Memory Device
	Array Handle: 0x003A
	Total Width: 72 bits
	Data Width: 64 bits
	Size: 32 GB
	Form Factor: DIMM
	Locator: DIMM_B1
	Bank Locator: BANK 1
	Type: DDR5
	Speed: 5600 MT/s
	Manufacturer: Example
	Part Number: EXAMPLE-32G
	Rank: 2
	Configured Memory Speed: 5200 MT/s
"""
    with (
        patch("lmts.tools.profile.platform.system", return_value="Linux"),
        patch("lmts.tools.profile.shutil.which", return_value="/usr/sbin/dmidecode"),
        patch("lmts.tools.profile._optional_command", return_value=dmidecode),
        patch("lmts.tools.profile._memory_total_bytes", return_value=64 * 1024 ** 3),
    ):
        memory = _system_memory_profile()

    assert memory["total_bytes"] == 64 * 1024 ** 3
    assert memory["memory_type"] == "DDR5"
    assert memory["ecc"] is True
    assert memory["speed_mt_s"] == 5600
    assert memory["configured_speed_mt_s"] == 5200
    assert memory["form_factor"] == "DIMM"
    assert memory["probe_sources"] == ["smbios"]
    assert len(memory["modules"]) == 2
    assert memory["modules"][0]["slot"] == "DIMM_A1"
    assert memory["modules"][0]["capacity_bytes"] == 32 * 1024 ** 3
    assert memory["modules"][0]["source"] == "smbios"


def test_system_memory_profile_keeps_unknowns_when_smbios_is_unavailable() -> None:
    with (
        patch("lmts.tools.profile.platform.system", return_value="Linux"),
        patch("lmts.tools.profile.shutil.which", return_value=None),
        patch("lmts.tools.profile._memory_total_bytes", return_value=16 * 1024 ** 3),
    ):
        memory = _system_memory_profile()

    assert memory == {
        "total_bytes": 16 * 1024 ** 3,
        "memory_type": None,
        "ecc": None,
        "speed_mt_s": None,
        "configured_speed_mt_s": None,
        "form_factor": "unknown",
        "modules": [],
        "probe_sources": [],
    }


def test_system_memory_profile_does_not_infer_form_factor_from_machine_type() -> None:
    dmidecode = """Memory Device
	Size: 16 GB
	Form Factor: Unknown
	Locator: ChannelA-DIMM0
	Type: DDR5
	Speed: 4800 MT/s
	Configured Memory Speed: 4800 MT/s
"""
    with (
        patch("lmts.tools.profile.platform.system", return_value="Linux"),
        patch("lmts.tools.profile.shutil.which", return_value="/usr/sbin/dmidecode"),
        patch("lmts.tools.profile._optional_command", return_value=dmidecode),
        patch("lmts.tools.profile._memory_total_bytes", return_value=16 * 1024 ** 3),
    ):
        memory = _system_memory_profile()

    assert memory["form_factor"] == "unknown"
    assert memory["modules"][0]["form_factor"] == "unknown"
    assert memory["ecc"] is None


def test_nvidia_profile_keeps_memory_type_unknown_and_reads_ecc_mode() -> None:
    def command_result(command, *, timeout=5):
        joined = " ".join(command)
        if "index,name,memory.total,driver_version" in joined:
            return "0, NVIDIA Test GPU, 8192, 610.43.02\n"
        if "index,ecc.mode.current" in joined:
            return "0, Enabled\n"
        return None

    with (
        patch("lmts.tools.profile.shutil.which", return_value="/usr/bin/nvidia-smi"),
        patch("lmts.tools.profile._optional_command", side_effect=command_result),
    ):
        gpus = _nvidia_gpus()

    assert len(gpus) == 1
    assert gpus[0].memory_type is None
    assert gpus[0].ecc is True
    assert gpus[0].vram_bytes == 8192 * 1024 * 1024


def test_system_fingerprint_distinguishes_reliably_known_memory_characteristics() -> None:
    base = SystemProfile(
        cpu={"architecture": "x86_64", "model_name": "Test CPU", "logical_cores": 8},
        memory={
            "total_bytes": 64 * 1024 ** 3,
            "memory_type": "DDR5",
            "ecc": False,
            "speed_mt_s": 5600,
            "configured_speed_mt_s": 5200,
            "form_factor": "DIMM",
            "modules": [],
        },
    )
    ecc = SystemProfile(
        cpu=dict(base.cpu),
        memory={**base.memory, "ecc": True},
    )
    ddr4 = SystemProfile(
        cpu=dict(base.cpu),
        memory={**base.memory, "memory_type": "DDR4"},
    )

    assert system_fingerprint(base) != system_fingerprint(ecc)
    assert system_fingerprint(base) != system_fingerprint(ddr4)


def test_system_fingerprint_ignores_module_slot_location() -> None:
    module = {
        "capacity_bytes": 32 * 1024 ** 3,
        "memory_type": "DDR5",
        "ecc": True,
        "speed_mt_s": 5600,
        "configured_speed_mt_s": 5200,
        "form_factor": "DIMM",
        "manufacturer": "Example",
        "part_number": "EXAMPLE-32G",
        "rank": 2,
    }
    first = SystemProfile(
        cpu={"architecture": "x86_64", "model_name": "Test CPU", "logical_cores": 8},
        memory={"total_bytes": 32 * 1024 ** 3, "modules": [{**module, "slot": "DIMM_A1"}]},
    )
    second = SystemProfile(
        cpu=dict(first.cpu),
        memory={"total_bytes": 32 * 1024 ** 3, "modules": [{**module, "slot": "DIMM_B2"}]},
    )

    assert system_fingerprint(first) == system_fingerprint(second)


def test_system_fingerprint_ignores_configured_memory_speed() -> None:
    base = SystemProfile(
        cpu={"architecture": "x86_64", "model_name": "Test CPU", "logical_cores": 8},
        memory={
            "total_bytes": 64 * 1024 ** 3,
            "memory_type": "DDR5",
            "ecc": False,
            "speed_mt_s": 5600,
            "configured_speed_mt_s": 5200,
            "form_factor": "DIMM",
            "modules": [{
                "capacity_bytes": 64 * 1024 ** 3,
                "memory_type": "DDR5",
                "ecc": False,
                "speed_mt_s": 5600,
                "configured_speed_mt_s": 5200,
                "form_factor": "DIMM",
                "manufacturer": "Example",
                "part_number": "EXAMPLE",
                "rank": 2,
            }],
        },
    )
    changed = SystemProfile(
        cpu=dict(base.cpu),
        memory={
            **base.memory,
            "configured_speed_mt_s": 4800,
            "modules": [{**base.memory["modules"][0], "configured_speed_mt_s": 4800}],
        },
    )

    assert system_fingerprint(base) == system_fingerprint(changed)


def test_system_fingerprint_ignores_current_gpu_ecc_mode() -> None:
    first = SystemProfile(
        cpu={"architecture": "x86_64", "model_name": "Test CPU", "logical_cores": 8},
        memory={"total_bytes": 16 * 1024 ** 3},
        gpu=[GPUProfile(
            vendor="NVIDIA",
            model="Test GPU",
            vram_bytes=24 * 1024 ** 3,
            memory_type="GDDR6X",
            ecc=False,
        )],
    )
    second = SystemProfile(
        cpu=dict(first.cpu),
        memory=dict(first.memory),
        gpu=[GPUProfile(
            vendor="NVIDIA",
            model="Test GPU",
            vram_bytes=24 * 1024 ** 3,
            memory_type="GDDR6X",
            ecc=True,
        )],
    )

    assert system_fingerprint(first) == system_fingerprint(second)
