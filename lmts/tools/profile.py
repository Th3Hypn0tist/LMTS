from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path


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
    command = ["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader,nounits"]
    try:
        output = subprocess.check_output(command, text=True, stderr=subprocess.DEVNULL, timeout=5)
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
    return SystemProfile(cpu={"architecture": platform.machine() or None, "model": platform.processor() or None, "logical_cores": os.cpu_count()}, memory={"total_bytes": _memory_total_bytes()}, gpu=_nvidia_gpus(), software={"os": platform.system() or None, "os_release": platform.release() or None, "python": platform.python_version()})


def profile_json() -> str:
    return json.dumps(scan_system_profile().to_dict(), indent=2, ensure_ascii=False)
