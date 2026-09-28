from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from lmts.core.paths import SYSTEM_PROFILE_PATH

from lmts.core.hardware_order import build_hardware_order_profile

from .reference_benchmark import (
    REFERENCE_BENCHMARK_DOMAINS,
    ReferenceBenchmarkProgressCallback,
    empty_reference_benchmarks,
    run_reference_benchmark,
    validate_reference_benchmarks,
)

DEFAULT_PROFILE_PATH = SYSTEM_PROFILE_PATH
PROFILE_SCHEMA_VERSION = 7


@dataclass(slots=True)
class GPUProfile:
    vendor: str | None = None
    model: str | None = None
    vram_bytes: int | None = None
    memory_type: str | None = None
    ecc: bool | None = None
    driver_version: str | None = None


@dataclass(slots=True)
class SystemProfile:
    cpu: dict[str, object] = field(default_factory=dict)
    memory: dict[str, object] = field(default_factory=dict)
    gpu: list[GPUProfile] = field(default_factory=list)
    npu: list[dict[str, object]] = field(default_factory=list)
    software: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _read_text(path: Path) -> str | None:
    try:
        value = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    return value or None


def _memory_total_bytes() -> int | None:
    meminfo = Path("/proc/meminfo")
    if meminfo.exists():
        for line in meminfo.read_text(encoding="utf-8").splitlines():
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) * 1024
    return None


def _optional_command(command: list[str], *, timeout: int = 5) -> str | None:
    try:
        return subprocess.check_output(
            command,
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _parse_dmidecode_sections(text: str, title: str) -> list[dict[str, str]]:
    sections: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    active = False
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if line == title:
            current = {}
            sections.append(current)
            active = True
            continue
        if not active or current is None:
            continue
        if line and not line[0].isspace():
            active = False
            current = None
            continue
        stripped = line.strip()
        if not stripped or ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        current[key.strip()] = value.strip()
    return sections


def _parse_capacity_bytes(value: str | None) -> int | None:
    if not value:
        return None
    normalized = value.strip()
    if normalized.casefold() in {"unknown", "no module installed", "not installed", "none"}:
        return None
    parts = normalized.split()
    if len(parts) < 2:
        return None
    try:
        amount = float(parts[0])
    except ValueError:
        return None
    unit = parts[1].upper()
    factors = {
        "KB": 1024,
        "MB": 1024 ** 2,
        "GB": 1024 ** 3,
        "TB": 1024 ** 4,
    }
    factor = factors.get(unit)
    if factor is None:
        return None
    return int(amount * factor)


def _parse_mt_s(value: str | None) -> int | None:
    if not value:
        return None
    normalized = value.strip().upper()
    if normalized in {"UNKNOWN", "NONE", "NOT SPECIFIED"}:
        return None
    parts = normalized.split()
    if len(parts) < 2 or parts[1] not in {"MT/S", "MT/S."}:
        return None
    try:
        return int(float(parts[0]))
    except ValueError:
        return None


def _parse_width_bits(value: str | None) -> int | None:
    if not value:
        return None
    parts = value.strip().split()
    if len(parts) < 2 or parts[1].casefold() not in {"bit", "bits"}:
        return None
    try:
        return int(parts[0])
    except ValueError:
        return None


def _normalize_memory_type(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().upper().replace(" ", "")
    if normalized in {"", "UNKNOWN", "OTHER", "NOTSPECIFIED"}:
        return None
    aliases = {
        "LPDDR": "LPDDR",
        "LPDDR2": "LPDDR2",
        "LPDDR3": "LPDDR3",
        "LPDDR4": "LPDDR4",
        "LPDDR4X": "LPDDR4X",
        "LPDDR5": "LPDDR5",
        "LPDDR5X": "LPDDR5X",
        "DDR": "DDR",
        "DDR2": "DDR2",
        "DDR3": "DDR3",
        "DDR4": "DDR4",
        "DDR5": "DDR5",
        "HBM": "HBM",
        "HBM2": "HBM2",
        "HBM2E": "HBM2E",
        "HBM3": "HBM3",
        "GDDR5": "GDDR5",
        "GDDR5X": "GDDR5X",
        "GDDR6": "GDDR6",
        "GDDR6X": "GDDR6X",
        "GDDR7": "GDDR7",
    }
    return aliases.get(normalized)


def _normalize_form_factor(value: str | None) -> str:
    if not value:
        return "unknown"
    normalized = value.strip().casefold().replace("-", "").replace("_", "").replace(" ", "")
    if normalized in {"", "unknown", "notspecified"}:
        return "unknown"
    if normalized in {"dimm", "fbdimm", "minidimm"}:
        return "DIMM"
    if normalized in {"sodimm", "smalloutlinedimm"}:
        return "SODIMM"
    if normalized in {"rowofchips", "chip"}:
        return "soldered"
    return "other"


def _ecc_from_widths(total_width: str | None, data_width: str | None) -> bool | None:
    total = _parse_width_bits(total_width)
    data = _parse_width_bits(data_width)
    if total is None or data is None or total < data:
        return None
    return total > data


def _ecc_from_array(value: str | None) -> bool | None:
    if not value:
        return None
    normalized = value.strip().casefold()
    if normalized in {"unknown", "other", "not provided", "not specified"}:
        return None
    if normalized == "none":
        return False
    if "ecc" in normalized:
        return True
    return None


def _parse_rank(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(value.strip().split()[0])
    except (ValueError, IndexError):
        return None


def _uniform_module_value(modules: list[dict[str, object]], key: str) -> object | None:
    if not modules:
        return None
    values = [module.get(key) for module in modules]
    if any(value is None or value == "unknown" for value in values):
        return None
    first = values[0]
    return first if all(value == first for value in values[1:]) else None


def _system_memory_profile() -> dict[str, object]:
    profile: dict[str, object] = {
        "total_bytes": _memory_total_bytes(),
        "memory_type": None,
        "ecc": None,
        "speed_mt_s": None,
        "configured_speed_mt_s": None,
        "form_factor": "unknown",
        "modules": [],
        "probe_sources": [],
    }
    if platform.system().casefold() != "linux" or shutil.which("dmidecode") is None:
        return profile

    output = _optional_command(["dmidecode", "--type", "memory"], timeout=8)
    if not output:
        return profile

    modules: list[dict[str, object]] = []
    for device in _parse_dmidecode_sections(output, "Memory Device"):
        capacity = _parse_capacity_bytes(device.get("Size"))
        if capacity is None:
            continue
        module = {
            "slot": device.get("Locator") or None,
            "bank": device.get("Bank Locator") or None,
            "capacity_bytes": capacity,
            "memory_type": _normalize_memory_type(device.get("Type")),
            "memory_type_raw": device.get("Type") or None,
            "ecc": _ecc_from_widths(device.get("Total Width"), device.get("Data Width")),
            "speed_mt_s": _parse_mt_s(device.get("Speed")),
            "configured_speed_mt_s": _parse_mt_s(device.get("Configured Memory Speed")),
            "manufacturer": None if (device.get("Manufacturer") or "").strip().casefold() in {"", "unknown", "not specified"} else device.get("Manufacturer"),
            "part_number": None if (device.get("Part Number") or "").strip().casefold() in {"", "unknown", "not specified"} else device.get("Part Number"),
            "rank": _parse_rank(device.get("Rank")),
            "form_factor": _normalize_form_factor(device.get("Form Factor")),
            "form_factor_raw": device.get("Form Factor") or None,
            "source": "smbios",
        }
        modules.append(module)

    arrays = _parse_dmidecode_sections(output, "Physical Memory Array")
    array_ecc_values = [
        _ecc_from_array(array.get("Error Correction Type"))
        for array in arrays
        if array.get("Error Correction Type")
    ]
    known_array_ecc = [value for value in array_ecc_values if value is not None]
    array_ecc = known_array_ecc[0] if known_array_ecc and all(value == known_array_ecc[0] for value in known_array_ecc) else None

    profile["modules"] = modules
    profile["probe_sources"] = ["smbios"]
    profile["memory_type"] = _uniform_module_value(modules, "memory_type")
    profile["speed_mt_s"] = _uniform_module_value(modules, "speed_mt_s")
    profile["configured_speed_mt_s"] = _uniform_module_value(modules, "configured_speed_mt_s")
    form_factor = _uniform_module_value(modules, "form_factor")
    profile["form_factor"] = form_factor if isinstance(form_factor, str) else "unknown"
    module_ecc = _uniform_module_value(modules, "ecc")
    profile["ecc"] = array_ecc if array_ecc is not None else module_ecc
    return profile


def _cpuinfo_blocks() -> list[dict[str, str]]:
    path = Path("/proc/cpuinfo")
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    blocks: list[dict[str, str]] = []
    for raw_block in text.strip().split("\n\n"):
        block: dict[str, str] = {}
        for line in raw_block.splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            block[key.strip()] = value.strip()
        if block:
            blocks.append(block)
    return blocks


def _as_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _as_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _cpu_profile() -> dict[str, object]:
    blocks = _cpuinfo_blocks()
    first = blocks[0] if blocks else {}
    model_names = sorted({block.get("model name", "").strip() for block in blocks if block.get("model name", "").strip()})
    physical_ids = sorted({block.get("physical id", "").strip() for block in blocks if block.get("physical id", "").strip()})
    core_pairs = {(block.get("physical id", "0"), block.get("core id", "")) for block in blocks if block.get("core id", "").strip()}
    flags_text = first.get("flags") or first.get("Features") or ""
    return {
        "architecture": platform.machine() or None,
        "model_name": first.get("model name") or platform.processor() or None,
        "model_names": model_names,
        "vendor_id": first.get("vendor_id") or None,
        "cpu_family": _as_int(first.get("cpu family")),
        "model": _as_int(first.get("model")),
        "model_id": first.get("model") or None,
        "stepping": _as_int(first.get("stepping")),
        "microcode": first.get("microcode") or None,
        "cache_size": first.get("cache size") or None,
        "cpu_mhz": _as_float(first.get("cpu MHz")),
        "bogomips": _as_float(first.get("bogomips")),
        "logical_cores": os.cpu_count(),
        "reported_processors": len(blocks) or None,
        "physical_packages": len(physical_ids) if physical_ids else None,
        "physical_ids": physical_ids,
        "physical_cores": len(core_pairs) if core_pairs else None,
        "cores_per_socket": _as_int(first.get("cpu cores")),
        "siblings_per_socket": _as_int(first.get("siblings")),
        "flags": flags_text.split() if flags_text else [],
    }


def _nvidia_ecc_modes() -> dict[int, bool | None]:
    output = _optional_command(
        ["nvidia-smi", "--query-gpu=index,ecc.mode.current", "--format=csv,noheader,nounits"],
        timeout=5,
    )
    if not output:
        return {}
    modes: dict[int, bool | None] = {}
    for line in output.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 2:
            continue
        try:
            index = int(parts[0])
        except ValueError:
            continue
        value = parts[1].casefold()
        if value == "enabled":
            modes[index] = True
        elif value == "disabled":
            modes[index] = False
        else:
            modes[index] = None
    return modes


def _nvidia_gpus() -> list[GPUProfile]:
    if shutil.which("nvidia-smi") is None:
        return []
    output = _optional_command(
        ["nvidia-smi", "--query-gpu=index,name,memory.total,driver_version", "--format=csv,noheader,nounits"],
        timeout=5,
    )
    if not output:
        return []
    ecc_modes = _nvidia_ecc_modes()
    gpus: list[GPUProfile] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 4:
            continue
        index_raw, name, memory_mib, driver = parts
        try:
            index = int(index_raw)
        except ValueError:
            continue
        try:
            vram = int(memory_mib) * 1024 * 1024
        except ValueError:
            vram = None
        gpus.append(
            GPUProfile(
                vendor="NVIDIA",
                model=name,
                vram_bytes=vram,
                memory_type=None,
                ecc=ecc_modes.get(index),
                driver_version=driver,
            )
        )
    return gpus


def _linux_accelerators(root: Path = Path("/sys/class/accel")) -> list[dict[str, object]]:
    if not root.is_dir():
        return []
    devices: list[dict[str, object]] = []
    for entry in sorted(root.iterdir(), key=lambda path: path.name):
        if not entry.name.startswith("accel"):
            continue
        device = entry / "device"
        resolved = device.resolve() if device.exists() else entry.resolve()
        driver_link = device / "driver"
        driver = None
        try:
            if driver_link.exists():
                driver = driver_link.resolve().name
        except OSError:
            driver = None
        identity: dict[str, object] = {
            "class": "accel",
            "name": entry.name,
            "sysfs_path": str(resolved),
            "vendor_id": _read_text(device / "vendor"),
            "device_id": _read_text(device / "device"),
            "subsystem_vendor_id": _read_text(device / "subsystem_vendor"),
            "subsystem_device_id": _read_text(device / "subsystem_device"),
            "driver": driver,
        }
        uevent = _read_text(device / "uevent")
        if uevent:
            fields: dict[str, str] = {}
            for line in uevent.splitlines():
                key, sep, value = line.partition("=")
                if sep:
                    fields[key] = value
            identity["driver"] = identity.get("driver") or fields.get("DRIVER")
            identity["pci_slot"] = fields.get("PCI_SLOT_NAME")
            identity["modalias"] = fields.get("MODALIAS")
        devices.append(identity)
    return devices


def scan_system_profile() -> SystemProfile:
    return SystemProfile(
        cpu=_cpu_profile(),
        memory=_system_memory_profile(),
        gpu=_nvidia_gpus(),
        npu=_linux_accelerators(),
        software={"os": platform.system() or None, "os_release": platform.release() or None, "python": platform.python_version()},
    )


def system_identity(profile: SystemProfile) -> dict[str, object]:
    data = profile.to_dict()
    cpu = data.get("cpu") if isinstance(data.get("cpu"), dict) else {}
    memory = data.get("memory") if isinstance(data.get("memory"), dict) else {}
    gpu = data.get("gpu") if isinstance(data.get("gpu"), list) else []
    npu = data.get("npu") if isinstance(data.get("npu"), list) else []
    gpu_identity = sorted(
        (
            str(item.get("vendor") or ""),
            str(item.get("model") or ""),
            item.get("vram_bytes"),
            item.get("memory_type"),
        )
        for item in gpu if isinstance(item, dict)
    )
    npu_identity = sorted(
        (
            str(item.get("class") or ""), str(item.get("vendor_id") or ""), str(item.get("device_id") or ""),
            str(item.get("subsystem_vendor_id") or ""), str(item.get("subsystem_device_id") or ""),
            str(item.get("modalias") or ""),
        )
        for item in npu if isinstance(item, dict)
    )
    return {
        "cpu": {
            "architecture": cpu.get("architecture"), "model_name": cpu.get("model_name"), "model_names": cpu.get("model_names"),
            "vendor_id": cpu.get("vendor_id"), "cpu_family": cpu.get("cpu_family"), "model": cpu.get("model"),
            "stepping": cpu.get("stepping"), "logical_cores": cpu.get("logical_cores"),
            "physical_packages": cpu.get("physical_packages"), "physical_cores": cpu.get("physical_cores"),
        },
        "memory": {
            "total_bytes": memory.get("total_bytes"),
            "memory_type": memory.get("memory_type"),
            "ecc": memory.get("ecc"),
            "speed_mt_s": memory.get("speed_mt_s"),
            "form_factor": memory.get("form_factor"),
            "modules": sorted(
                (
                    module.get("capacity_bytes"),
                    module.get("memory_type"),
                    module.get("ecc"),
                    module.get("speed_mt_s"),
                    module.get("form_factor"),
                    str(module.get("manufacturer") or ""),
                    str(module.get("part_number") or ""),
                    module.get("rank"),
                )
                for module in memory.get("modules", [])
                if isinstance(module, dict)
            ),
        },
        "gpu": gpu_identity,
        "npu": npu_identity,
    }


def system_fingerprint(profile: SystemProfile) -> str:
    canonical = json.dumps(system_identity(profile), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _existing_reference_benchmarks(target: Path, fingerprint: str) -> dict[str, object] | None:
    if not target.is_file():
        return None
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("schema_version") != PROFILE_SCHEMA_VERSION or payload.get("fingerprint") != fingerprint:
        return None
    references = payload.get("reference_benchmarks")
    return references if validate_reference_benchmarks(references) else None


def save_system_profile(profile: SystemProfile, path: Path = DEFAULT_PROFILE_PATH, *, reference_benchmarks: dict[str, object] | None = None) -> Path:
    target = path.expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    fingerprint = system_fingerprint(profile)
    references = reference_benchmarks
    if references is None:
        references = _existing_reference_benchmarks(target, fingerprint) or empty_reference_benchmarks()
    if not validate_reference_benchmarks(references):
        raise ValueError("invalid reference benchmark payload")
    profile_data = profile.to_dict()
    payload = {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "profiled_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "fingerprint": fingerprint,
        "identity": system_identity(profile),
        "profile": profile_data,
        "reference_benchmarks": references,
        "hardware_order": build_hardware_order_profile(profile_data, references),
    }
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return target


def load_system_profile(path: Path = DEFAULT_PROFILE_PATH) -> dict[str, object] | None:
    target = path.expanduser()
    if not target.is_file():
        return None
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("schema_version") != PROFILE_SCHEMA_VERSION or not isinstance(payload.get("profile"), dict):
        return None
    references = payload.get("reference_benchmarks")
    if not validate_reference_benchmarks(references):
        return None
    hardware_order = payload.get("hardware_order")
    if hardware_order != build_hardware_order_profile(payload["profile"], references):
        return None
    fingerprint = payload.get("fingerprint")
    identity = payload.get("identity")
    if not isinstance(fingerprint, str) or not fingerprint or not isinstance(identity, dict):
        return None
    scanned = scan_system_profile()
    if fingerprint != system_fingerprint(scanned):
        return None
    if identity != system_identity(scanned):
        return None
    return payload


def save_reference_benchmark(domain: str, result: dict[str, object], path: Path = DEFAULT_PROFILE_PATH) -> Path:
    normalized = domain.strip().casefold()
    if normalized not in REFERENCE_BENCHMARK_DOMAINS:
        raise ValueError(f"unknown reference benchmark domain: {domain}")
    if result.get("domain") != normalized:
        raise ValueError("reference benchmark domain mismatch")
    payload = load_system_profile(path)
    if payload is None:
        raise ValueError("valid system profile required before reference benchmarking")
    references = dict(payload["reference_benchmarks"])
    references[normalized] = result
    if not validate_reference_benchmarks(references):
        raise ValueError("invalid reference benchmark result")
    payload["reference_benchmarks"] = references
    payload["hardware_order"] = build_hardware_order_profile(payload["profile"], references)
    target = path.expanduser()
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return target


def benchmark_system_reference(
    domain: str,
    path: Path = DEFAULT_PROFILE_PATH,
    *,
    progress: ReferenceBenchmarkProgressCallback | None = None,
) -> dict[str, object]:
    result = run_reference_benchmark(domain, progress=progress).to_dict()
    save_reference_benchmark(domain, result, path)
    return result


def ensure_system_profile(path: Path = DEFAULT_PROFILE_PATH) -> dict[str, object]:
    payload = load_system_profile(path)
    if payload is not None:
        return payload
    profile = scan_system_profile()
    save_system_profile(profile, path)
    return load_system_profile(path) or {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "fingerprint": system_fingerprint(profile),
        "identity": system_identity(profile),
        "profile": profile.to_dict(),
        "reference_benchmarks": empty_reference_benchmarks(),
        "hardware_order": build_hardware_order_profile(
            profile.to_dict(),
            empty_reference_benchmarks(),
        ),
    }


def profile_json() -> str:
    return json.dumps(scan_system_profile().to_dict(), indent=2, ensure_ascii=False)
