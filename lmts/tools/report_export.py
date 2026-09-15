from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from lmts.reporting import REPORT_FORMAT, REPORT_VERSION


def _timestamp() -> str:
    return datetime.now().astimezone().strftime('%Y%m%d%H%M')


def export_report_json(report: dict[str, Any], output_folder: Path) -> Path:
    report_meta = report.get('report')
    if report.get('format') != REPORT_FORMAT or report.get('version') != REPORT_VERSION or not isinstance(report_meta, dict):
        raise ValueError(f'payload is not an LMTS Benchmark Report {REPORT_VERSION} document')
    report_id = str(report_meta.get('id') or '').strip()
    if not report_id:
        raise ValueError('LMTS report is missing report.id')

    safe_id = ''.join(ch if ch.isalnum() or ch in '-_.' else '-' for ch in report_id).strip('-_.') or 'report'
    path = output_folder.expanduser() / f'{_timestamp()}-report-{safe_id[:24]}.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, indent=2, ensure_ascii=False) + '\n'
    temp = path.with_suffix(path.suffix + f'.tmp-{os.getpid()}')
    temp.write_text(payload, encoding='utf-8')
    try:
        temp.replace(path)
    finally:
        if temp.exists():
            temp.unlink()
    return path
