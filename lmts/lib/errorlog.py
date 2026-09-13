from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def safe_task_name(task: str) -> str:
    value = _SAFE.sub("_", str(task).strip()).strip("._-")
    return value or "task"


def default_error_log_path(
    task: str,
    *,
    root: Path = Path("logs"),
    when: datetime | None = None,
) -> Path:
    timestamp = (when or datetime.now().astimezone()).strftime("%Y%m%d%H%M")
    return root / f"{timestamp}-{safe_task_name(task)}.log"


def export_error_log(
    task: str,
    errors: Sequence[Mapping[str, Any]],
    *,
    path: Path | None = None,
    root: Path = Path("logs"),
) -> Path:
    target = (path or default_error_log_path(task, root=root)).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "LMTS ERROR LOG",
        f"generated: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"task: {task}",
        f"error_count: {len(errors)}",
        "",
    ]

    for index, record in enumerate(errors, start=1):
        error = record.get("error")
        error_map = error if isinstance(error, Mapping) else {}
        lines.extend(
            [
                f"[{index}]",
                f"run_id: {record.get('run_id', '-')}",
                f"model_id: {record.get('model_id', '-')}",
                f"test_ref: {record.get('test_ref', '-')}",
                f"result_path: {record.get('result_path', '-')}",
                f"type: {error_map.get('type', '-')}",
                f"message: {error_map.get('message', '-')}",
                "traceback:",
                str(error_map.get("traceback") or "-").rstrip(),
                "",
            ]
        )

    target.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return target
