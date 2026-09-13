from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _section(lines: list[str], title: str) -> None:
    if lines and lines[-1] != "":
        lines.append("")
    lines.append(title)
    lines.append("=" * len(title))


def _json_lines(value: object) -> list[str]:
    return json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True).splitlines()


def matrix_label(data: dict[str, Any], path: Path) -> str:
    started = str(data.get("started_at") or "")
    stamp = started.replace("T", " ")[:19] if started else path.stem[:12]
    targets = data.get("target_ids") or []
    tests = data.get("test_refs") or []
    status = str(data.get("status") or "?").upper()
    passed = int(data.get("passed") or 0)
    failed = int(data.get("failed") or 0)
    errors = int(data.get("errors") or 0)
    cancelled = int(data.get("cancelled") or 0)
    return (
        f"{stamp}  {status:<9}  {len(targets)}x{len(tests)}  "
        f"P:{passed} F:{failed} E:{errors} C:{cancelled}"
    )


def cell_verdict(cell: dict[str, Any] | None) -> str:
    if cell is None:
        return "-"
    status = str(cell.get("status") or "")
    passed = cell.get("passed")
    if status == "cancelled":
        return "CANCEL"
    if status != "completed":
        return "ERROR"
    if passed is True:
        return "PASS"
    if passed is False:
        return "FAIL"
    return status.upper() or "?"


def format_matrix(data: dict[str, Any]) -> tuple[str, ...]:
    targets = [str(value) for value in (data.get("target_ids") or [])]
    kinds = data.get("target_kinds") if isinstance(data.get("target_kinds"), dict) else {}
    tests = [str(value) for value in (data.get("test_refs") or [])]
    cells = [cell for cell in (data.get("cells") or []) if isinstance(cell, dict)]
    by_key = {(str(cell.get("target_id")), str(cell.get("test_ref"))): cell for cell in cells}

    short_tests: list[str] = []
    for ref in tests:
        instance = ref.split("#", 1)[-1] if "#" in ref else ref.rsplit(".", 1)[-1]
        short_tests.append(instance[:18])

    target_labels = [f"{str(kinds.get(target) or '?')}:{target}" for target in targets]
    target_width = max([6, *(len(label) for label in target_labels)]) if target_labels else 6
    col_width = max(8, *(len(label) for label in short_tests)) if short_tests else 8

    started = str(data.get("started_at") or "")
    stamp = started.replace("T", " ")[:19] if started else "?"
    lines = [f"Run: {stamp}", f"Status: {str(data.get('status') or '?').upper()}", ""]

    header = f"{'TARGET':<{target_width}}"
    for label in short_tests:
        header += f"  {label:^{col_width}}"
    lines.append(header)
    lines.append("-" * len(header))

    for target, label in zip(targets, target_labels):
        row = f"{label:<{target_width}}"
        for test_ref in tests:
            row += f"  {cell_verdict(by_key.get((target, test_ref))):^{col_width}}"
        lines.append(row)

    lines.extend([
        "",
        f"PASS {int(data.get('passed') or 0)}  FAIL {int(data.get('failed') or 0)}  ERROR {int(data.get('errors') or 0)}  CANCEL {int(data.get('cancelled') or 0)}",
    ])
    return tuple(lines)


def matrix_cells(data: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    return tuple(cell for cell in (data.get("cells") or []) if isinstance(cell, dict))


def format_run_result(data: dict[str, Any], path: Path) -> tuple[str, ...]:
    lines: list[str] = []

    _section(lines, "Run")
    for key in (
        "run_id",
        "status",
        "passed",
        "test_ref",
        "executor_id",
        "executor_kind",
        "model_id",
        "model_ref",
        "provider_ref",
        "started_at",
        "completed_at",
    ):
        lines.append(f"{key:16}: {data.get(key)}")
    lines.append(f"result_path      : {path}")

    _section(lines, "Evaluation subject")
    lines.extend(_json_lines(data.get("evaluation_subject") or {}))

    _section(lines, "Execution metadata")
    lines.extend(_json_lines(data.get("execution_metadata") or {}))

    _section(lines, "Score")
    lines.extend(_json_lines(data.get("score") or {}))

    _section(lines, "Metrics")
    lines.extend(_json_lines(data.get("metrics") or {}))

    _section(lines, "Telemetry")
    lines.extend(_json_lines(data.get("telemetry") or {}))

    _section(lines, "Artifacts")
    lines.extend(_json_lines(data.get("artifacts") or {}))

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
        performance = response.get("performance") or {}
        lines.append(f"    input_tokens : {usage.get('input_tokens') if isinstance(usage, dict) else None}")
        lines.append(f"    output_tokens: {usage.get('output_tokens') if isinstance(usage, dict) else None}")
        lines.append(f"    ttft_ms      : {timing.get('ttft_ms') if isinstance(timing, dict) else None}")
        lines.append(f"    total_ms     : {timing.get('total_ms') if isinstance(timing, dict) else None}")
        lines.append(f"    prompt tok/s : {performance.get('prompt_tokens_per_second') if isinstance(performance, dict) else None}")
        lines.append(f"    output tok/s : {performance.get('generation_tokens_per_second') if isinstance(performance, dict) else None}")
        lines.append("    text:")
        text = str(response.get("text") or "")
        lines.extend(f"      {line}" for line in text.splitlines()) if text else lines.append("      <empty>")
        lines.append("")

    _section(lines, "Workspace trace")
    lines.extend(_json_lines(data.get("workspace_trace") or []))

    _section(lines, "System context")
    lines.extend(_json_lines(data.get("system_context") or {}))

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
