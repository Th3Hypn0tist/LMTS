from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass

from lmts.core.settings import MySQLSettings


@dataclass(frozen=True, slots=True)
class StoredReport:
    report_id: str
    report_type: str
    created_at: str
    source_type: str
    source_id: str
    report_version: str
    imported_at: str

    def to_dict(self) -> dict[str, str]:
        return {
            'report_id': self.report_id,
            'report_type': self.report_type,
            'created_at': self.created_at,
            'source_type': self.source_type,
            'source_id': self.source_id,
            'report_version': self.report_version,
            'imported_at': self.imported_at,
        }


def _client(mysql: MySQLSettings) -> str:
    client = shutil.which('mariadb') or shutil.which('mysql')
    if client is None:
        raise RuntimeError('mariadb/mysql client is required to read LMTS reports')
    return client


def _run(mysql: MySQLSettings, query: str) -> str:
    command = [
        _client(mysql),
        f'--host={mysql.host}',
        f'--user={mysql.username}',
        '--protocol=tcp',
        '--batch',
        '--raw',
        '--skip-column-names',
        '--default-character-set=utf8mb4',
        mysql.database,
        '--execute',
        query,
    ]
    env = dict(os.environ)
    env['MYSQL_PWD'] = mysql.password
    completed = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        check=False,
    )
    if completed.returncode != 0:
        text = completed.stderr.decode('utf-8', errors='replace').strip()
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        non_warnings = [line for line in lines if not line.casefold().startswith('warning:')]
        detail = (non_warnings or lines or [f'exit code {completed.returncode}'])[-1]
        raise RuntimeError(f'MySQL report query failed: {detail}')
    return completed.stdout.decode('utf-8', errors='strict')


def list_reports(mysql: MySQLSettings, *, limit: int = 100) -> tuple[StoredReport, ...]:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
        raise ValueError('report list limit must be an integer between 1 and 1000')
    query = f"""
SELECT JSON_OBJECT(
  'report_id', report_id,
  'report_type', report_type,
  'created_at', DATE_FORMAT(created_at, '%Y-%m-%dT%H:%i:%s.%fZ'),
  'source_type', source_type,
  'source_id', source_id,
  'report_version', JSON_UNQUOTE(JSON_EXTRACT(report_json, '$.version')),
  'imported_at', DATE_FORMAT(imported_at, '%Y-%m-%dT%H:%i:%s.%fZ')
)
FROM reports
ORDER BY created_at DESC, imported_at DESC
LIMIT {limit}
""".strip()
    output = _run(mysql, query)
    items: list[StoredReport] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        items.append(StoredReport(**{key: str(value or '') for key, value in payload.items()}))
    return tuple(items)


def read_report(mysql: MySQLSettings, report_id: str) -> dict[str, object]:
    value = str(report_id).strip()
    if not value:
        raise ValueError('report id must not be empty')
    encoded = value.encode('utf-8').hex()
    query = (
        "SELECT report_json FROM reports "
        f"WHERE report_id = CONVERT(0x{encoded} USING utf8mb4) LIMIT 1"
    )
    raw = _run(mysql, query).strip()
    if not raw:
        raise KeyError(value)
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise RuntimeError(f'stored report root is not an object: {value}')
    return payload
