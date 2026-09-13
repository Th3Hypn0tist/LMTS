from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def result_label(data: dict[str, Any], path: Path) -> str:
    status = str(data.get("status") or "?")
    passed = data.get("passed")
    verdict = "PASS" if passed is True else "FAIL" if passed is False else status.upper()
    model = str(data.get("model_id") or "?")
    test_ref = str(data.get("test_ref") or "?")
    started = str(data.get("started_at") or "")
    stamp = started.replace("T", " ")[:19] if started else path.stem[:12]
    return f"{stamp}  {verdict:<9}  {model}  {test_ref}"


def _section(lines: list[str], title: str) -> None:
    if lines and lines[-1] != "":
        lines.append("")
    lines.append(title)
    lines.append("=" * len(title))


def _json_lines(value: object) -> list[str]:
    return json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True).splitlines()


def format_run_result(data: dict[str, Any], path: Path) -> tuple[str, ...]:
    lines: list[str] = []

    _section(lines, "Run")
    for key in (
        "run_id",
        "status",
        "passed",
        "test_ref",
        "model_id",
        "model_ref",
        "provider_ref",
        "started_at",
        "completed_at",
    ):
        lines.append(f"{key:16}: {data.get(key)}")
    lines.append(f"result_path      : {path}")

    _section(lines, "Metrics")
    metrics = data.get("metrics") or {}
    lines.extend(_json_lines(metrics))

    _section(lines, "Artifacts")
    artifacts = data.get("artifacts") or {}
    lines.extend(_json_lines(artifacts))

    responses = data.get("responses") or []
    _section(lines, f"Responses ({len(responses)})")
    if not responses:
        lines.append("<none>")
    for index, response in enumerate(responses, start=1):
        if not isinstance(response, dict):
            lines.append(f"[{index}] {response!r}")
            continue
        lines.append(f"[{index}] finish_reason: {response.get('finish_reason')}")
        usage = response.get("usage") or {}
        timing = response.get("timing") or {}
        lines.append(f"    input_tokens : {usage.get('input_tokens') if isinstance(usage, dict) else None}")
        lines.append(f"    output_tokens: {usage.get('output_tokens') if isinstance(usage, dict) else None}")
        lines.append(f"    ttft_ms      : {timing.get('ttft_ms') if isinstance(timing, dict) else None}")
        lines.append(f"    total_ms     : {timing.get('total_ms') if isinstance(timing, dict) else None}")
        lines.append("    text:")
        text = str(response.get("text") or "")
        if text:
            lines.extend(f"      {line}" for line in text.splitlines())
        else:
            lines.append("      <empty>")
        lines.append("    raw:")
        raw = response.get("raw") or {}
        lines.extend(f"      {line}" for line in _json_lines(raw))
        lines.append("")

    _section(lines, "Workspace trace")
    trace = data.get("workspace_trace") or []
    lines.extend(_json_lines(trace))

    _section(lines, "Model metadata")
    lines.extend(_json_lines(data.get("model_metadata") or {}))

    _section(lines, "System profile")
    lines.extend(_json_lines(data.get("system_profile") or {}))

    error = data.get("error")
    if error:
        _section(lines, "Error")
        if isinstance(error, dict):
            lines.append(f"type   : {error.get('type')}")
            lines.append(f"message: {error.get('message')}")
            lines.append("traceback:")
            lines.extend(str(error.get("traceback") or "").splitlines())
        else:
            lines.append(str(error))

    _section(lines, "Canonical JSON")
    lines.extend(_json_lines(data))
    return tuple(lines)
