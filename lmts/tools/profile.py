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
PROFILE_SCHEMA_VERSION = 2


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
        cpu={
            "architecture": platform.machine() or None,
            "model": platform.processor() or None,
            "logical_cores": os.cpu_count(),
        },
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
    software = data.get("software") if isinstance(data.get("software"), dict) else {}
    identity = {
        "cpu": data.get("cpu"),
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
    return load_system_profile(path) or {"profile": profile.to_dict()}


def profile_json() -> str:
    return json.dumps(scan_system_profile().to_dict(), indent=2, ensure_ascii=False)
