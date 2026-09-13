from __future__ import annotations

import csv
import os
import platform
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_linux_meminfo() -> dict[str, int]:
    path = "/proc/meminfo"
    if not os.path.isfile(path):
        return {}
    values: dict[str, int] = {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                key, _, rest = line.partition(":")
                token = rest.strip().split()[0] if rest.strip() else ""
                if token.isdigit():
                    values[key] = int(token) * 1024
    except OSError:
        return {}
    return values


def _system_memory_snapshot() -> dict[str, int | None]:
    info = _read_linux_meminfo()
    if info:
        total = info.get("MemTotal")
        available = info.get("MemAvailable")
        used = None if total is None or available is None else total - available
        return {"total_bytes": total, "available_bytes": available, "used_bytes": used}
    return {"total_bytes": None, "available_bytes": None, "used_bytes": None}


def _load_average() -> dict[str, float | None]:
    try:
        one, five, fifteen = os.getloadavg()
        return {"1m": one, "5m": five, "15m": fifteen}
    except (AttributeError, OSError):
        return {"1m": None, "5m": None, "15m": None}


def _parse_optional_float(value: str) -> float | None:
    value = value.strip()
    if not value or value.upper() in {"N/A", "[NOT SUPPORTED]"}:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _parse_optional_int(value: str) -> int | None:
    parsed = _parse_optional_float(value)
    return None if parsed is None else int(parsed)


def nvidia_gpu_snapshot() -> list[dict[str, Any]]:
    fields = [
        "index",
        "uuid",
        "name",
        "utilization.gpu",
        "utilization.memory",
        "memory.used",
        "memory.total",
        "temperature.gpu",
        "power.draw",
    ]
    command = [
        "nvidia-smi",
        f"--query-gpu={','.join(fields)}",
        "--format=csv,noheader,nounits",
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=3.0,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if completed.returncode != 0:
        return []

    output: list[dict[str, Any]] = []
    for row in csv.reader(completed.stdout.splitlines()):
        if len(row) != len(fields):
            continue
        output.append(
            {
                "index": _parse_optional_int(row[0]),
                "uuid": row[1].strip() or None,
                "name": row[2].strip() or None,
                "gpu_util_percent": _parse_optional_float(row[3]),
                "memory_util_percent": _parse_optional_float(row[4]),
                "memory_used_mib": _parse_optional_float(row[5]),
                "memory_total_mib": _parse_optional_float(row[6]),
                "temperature_c": _parse_optional_float(row[7]),
                "power_w": _parse_optional_float(row[8]),
            }
        )
    return output


def telemetry_snapshot() -> dict[str, Any]:
    return {
        "measured_at": _utc_now(),
        "platform": platform.system(),
        "load_average": _load_average(),
        "memory": _system_memory_snapshot(),
        "gpus": nvidia_gpu_snapshot(),
    }


def _numeric_summary(values: list[float]) -> dict[str, float] | None:
    if not values:
        return None
    return {
        "minimum": min(values),
        "maximum": max(values),
        "mean": sum(values) / len(values),
    }


def summarize_telemetry(samples: list[dict[str, Any]]) -> dict[str, Any]:
    gpu_by_key: dict[str, dict[str, list[float]]] = {}
    for sample in samples:
        for gpu in sample.get("gpus", []):
            key = str(gpu.get("uuid") or gpu.get("index"))
            bucket = gpu_by_key.setdefault(
                key,
                {
                    "gpu_util_percent": [],
                    "memory_util_percent": [],
                    "memory_used_mib": [],
                    "temperature_c": [],
                    "power_w": [],
                },
            )
            for metric in bucket:
                value = gpu.get(metric)
                if isinstance(value, (int, float)):
                    bucket[metric].append(float(value))

    gpus = {
        key: {metric: _numeric_summary(values) for metric, values in metrics.items()}
        for key, metrics in gpu_by_key.items()
    }
    return {
        "sample_count": len(samples),
        "gpus": gpus,
    }


@dataclass(slots=True)
class TelemetrySampler:
    interval_seconds: float = 1.0
    samples: list[dict[str, Any]] = field(default_factory=list)
    _thread: threading.Thread | None = field(default=None, init=False, repr=False)
    _stop: threading.Event = field(default_factory=threading.Event, init=False, repr=False)

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("telemetry sampler already started")
        self.samples.append(telemetry_snapshot())
        self._thread = threading.Thread(target=self._run, name="lmts-telemetry", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            self.samples.append(telemetry_snapshot())

    def stop(self) -> dict[str, Any]:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(1.0, self.interval_seconds * 2.0))
        self.samples.append(telemetry_snapshot())
        return {
            "samples": list(self.samples),
            "summary": summarize_telemetry(self.samples),
        }
