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

DEFAULT_PROFILE_PATH = Path(".lmts/system-profile.json")
PROFILE_SCHEMA_VERSION = 3


@dataclass(slots=True)
class GPUProfile:
    vendor: str | None = None
    model: str | None = None
    vram_bytes: int | None = None
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


def _memory_total_bytes() -> int | None:
    meminfo = Path("/proc/meminfo")
    if meminfo.exists():
        for line in meminfo.read_text(encoding="utf-8").splitlines():
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) * 1024
    return None


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

    model_names = sorted(
        {
            block.get("model name", "").strip()
            for block in blocks
            if block.get("model name", "").strip()
        }
    )
    physical_ids = sorted(
        {
            block.get("physical id", "").strip()
            for block in blocks
            if block.get("physical id", "").strip()
        }
    )
    core_pairs = {
        (block.get("physical id", "0"), block.get("core id", ""))
        for block in blocks
        if block.get("core id", "").strip()
    }
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


def _nvidia_gpus() -> list[GPUProfile]:
    if shutil.which("nvidia-smi") is None:
        return []
    command = [
        "nvidia-smi",
        "--query-gpu=name,memory.total,driver_version",
        "--format=csv,noheader,nounits",
    ]
    try:
        output = subprocess.check_output(
            command,
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    gpus: list[GPUProfile] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 3:
            continue
        name, memory_mib, driver = parts
        try:
            vram = int(memory_mib) * 1024 * 1024
        except ValueError:
            vram = None
        gpus.append(GPUProfile(vendor="NVIDIA", model=name, vram_bytes=vram, driver_version=driver))
    return gpus


def scan_system_profile() -> SystemProfile:
    return SystemProfile(
        cpu=_cpu_profile(),
        memory={"total_bytes": _memory_total_bytes()},
        gpu=_nvidia_gpus(),
        software={
            "os": platform.system() or None,
            "os_release": platform.release() or None,
            "python": platform.python_version(),
        },
    )


def system_fingerprint(profile: SystemProfile) -> str:
    data = profile.to_dict()
    cpu = data.get("cpu") if isinstance(data.get("cpu"), dict) else {}
    software = data.get("software") if isinstance(data.get("software"), dict) else {}
    identity = {
        "cpu": {
            "architecture": cpu.get("architecture"),
            "model_name": cpu.get("model_name"),
            "model_names": cpu.get("model_names"),
            "vendor_id": cpu.get("vendor_id"),
            "cpu_family": cpu.get("cpu_family"),
            "model": cpu.get("model"),
            "stepping": cpu.get("stepping"),
            "logical_cores": cpu.get("logical_cores"),
            "physical_packages": cpu.get("physical_packages"),
            "physical_cores": cpu.get("physical_cores"),
        },
        "memory": data.get("memory"),
        "gpu": data.get("gpu"),
        "npu": data.get("npu"),
        "os": software.get("os"),
    }
    canonical = json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def save_system_profile(profile: SystemProfile, path: Path = DEFAULT_PROFILE_PATH) -> Path:
    target = path.expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "profiled_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "fingerprint": system_fingerprint(profile),
        "profile": profile.to_dict(),
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
    if not isinstance(payload, dict):
        return None
    if payload.get("schema_version") != PROFILE_SCHEMA_VERSION:
        return None
    if not isinstance(payload.get("profile"), dict):
        return None
    fingerprint = payload.get("fingerprint")
    if not isinstance(fingerprint, str) or not fingerprint:
        return None
    if fingerprint != system_fingerprint(scan_system_profile()):
        return None
    return payload


def ensure_system_profile(path: Path = DEFAULT_PROFILE_PATH) -> dict[str, object]:
    payload = load_system_profile(path)
    if payload is not None:
        return payload
    profile = scan_system_profile()
    save_system_profile(profile, path)
    return load_system_profile(path) or {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "fingerprint": system_fingerprint(profile),
        "profile": profile.to_dict(),
    }


def profile_json() -> str:
    return json.dumps(scan_system_profile().to_dict(), indent=2, ensure_ascii=False)
