from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from lmts.core.paths import DVS_DATABASE_SOURCES_PATH
from lmts.core.settings import DEFAULT_SETTINGS_PATH, load_settings


DVS_DATABASE_SOURCES_SCHEMA_VERSION = 1
CORE_DATABASE_SOURCE_ID = 'lmts-core'
DEFAULT_DVS_DATABASE_SOURCES_PATH = DVS_DATABASE_SOURCES_PATH


@dataclass(frozen=True, slots=True)
class DVSDatabaseSource:
    id: str
    label: str
    host: str
    port: int
    database: str
    username: str
    password: str

    def __post_init__(self) -> None:
        for name, value in (
            ('id', self.id),
            ('label', self.label),
            ('host', self.host),
            ('database', self.database),
            ('username', self.username),
            ('password', self.password),
        ):
            if not str(value).strip():
                raise ValueError(f'DVS database source {name} must not be empty')
        if isinstance(self.port, bool) or not isinstance(self.port, int) or not 1 <= self.port <= 65535:
            raise ValueError('DVS database source port must be within 1..65535')

    def public_dict(self) -> dict[str, object]:
        return {
            'id': self.id,
            'label': self.label,
            'host': self.host,
            'port': self.port,
            'database': self.database,
            'username': self.username,
        }

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def load_dvs_database_sources(
    path: Path = DEFAULT_DVS_DATABASE_SOURCES_PATH,
) -> tuple[DVSDatabaseSource, ...]:
    path = path.expanduser()
    if not path.is_file():
        return ()
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict) or payload.get('schema_version') != DVS_DATABASE_SOURCES_SCHEMA_VERSION:
        raise ValueError('unsupported DVS database sources schema')
    raw_sources = payload.get('sources')
    if not isinstance(raw_sources, list):
        raise ValueError('DVS database sources must be a list')
    sources: list[DVSDatabaseSource] = []
    ids: set[str] = set()
    for raw in raw_sources:
        if not isinstance(raw, dict):
            raise ValueError('DVS database source must be an object')
        source = DVSDatabaseSource(
            id=str(raw.get('id') or '').strip(),
            label=str(raw.get('label') or '').strip(),
            host=str(raw.get('host') or '').strip(),
            port=int(raw.get('port') or 3306),
            database=str(raw.get('database') or '').strip(),
            username=str(raw.get('username') or '').strip(),
            password=str(raw.get('password') or ''),
        )
        if source.id in ids:
            raise ValueError(f'duplicate DVS database source id: {source.id}')
        ids.add(source.id)
        sources.append(source)
    return tuple(sorted(sources, key=lambda item: item.id.casefold()))


def load_all_dvs_database_sources(
    sources_path: Path = DEFAULT_DVS_DATABASE_SOURCES_PATH,
    settings_path: Path = DEFAULT_SETTINGS_PATH,
) -> tuple[DVSDatabaseSource, ...]:
    settings = load_settings(settings_path)
    core = DVSDatabaseSource(
        id=CORE_DATABASE_SOURCE_ID,
        label='LMTS core',
        host=settings.mysql.host,
        port=3306,
        database=settings.mysql.database,
        username=settings.mysql.username,
        password=settings.mysql.password,
    )
    extras = load_dvs_database_sources(sources_path)
    if any(source.id == CORE_DATABASE_SOURCE_ID for source in extras):
        raise ValueError(f'DVS database source id is reserved: {CORE_DATABASE_SOURCE_ID}')
    return (core, *extras)


def save_dvs_database_sources(
    sources: tuple[DVSDatabaseSource, ...],
    path: Path = DEFAULT_DVS_DATABASE_SOURCES_PATH,
) -> Path:
    ids = [source.id for source in sources]
    if CORE_DATABASE_SOURCE_ID in ids:
        raise ValueError(f'DVS database source id is reserved: {CORE_DATABASE_SOURCE_ID}')
    if len(ids) != len(set(ids)):
        raise ValueError('DVS database source ids must be unique')
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        'schema_version': DVS_DATABASE_SOURCES_SCHEMA_VERSION,
        'sources': [source.to_dict() for source in sorted(sources, key=lambda item: item.id.casefold())],
    }
    text = json.dumps(payload, indent=2, ensure_ascii=False) + '\n'
    temp = path.with_suffix(path.suffix + f'.tmp-{os.getpid()}')
    temp.write_text(text, encoding='utf-8')
    os.chmod(temp, 0o600)
    try:
        temp.replace(path)
        os.chmod(path, 0o600)
    finally:
        if temp.exists():
            temp.unlink()
    return path


def _mysql_client() -> str:
    client = shutil.which('mariadb') or shutil.which('mysql')
    if client is None:
        raise RuntimeError('mariadb/mysql client is required for DVS database sources')
    return client


def _query(source: DVSDatabaseSource, sql: str) -> list[str]:
    command = [
        _mysql_client(),
        f'--host={source.host}',
        f'--port={source.port}',
        f'--user={source.username}',
        '--protocol=tcp',
        '--default-character-set=utf8mb4',
        '--batch',
        '--skip-column-names',
        source.database,
        '--execute',
        sql,
    ]
    env = dict(os.environ)
    env['MYSQL_PWD'] = source.password
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or f'exit code {completed.returncode}'
        raise RuntimeError(f'DVS database source {source.id} query failed: {detail}')
    return [line for line in completed.stdout.splitlines() if line.strip()]


def _by_id(source_id: str, sources: tuple[DVSDatabaseSource, ...]) -> DVSDatabaseSource:
    for source in sources:
        if source.id == source_id:
            return source
    raise KeyError(f'unknown DVS database source: {source_id}')


def list_database_reports(
    source_ids: list[str],
    *,
    limit_per_source: int = 100,
    sources_path: Path = DEFAULT_DVS_DATABASE_SOURCES_PATH,
) -> list[dict[str, Any]]:
    if not source_ids:
        raise ValueError('select at least one DVS database source')
    if not 1 <= limit_per_source <= 1000:
        raise ValueError('limit_per_source must be within 1..1000')
    configured = load_all_dvs_database_sources(sources_path)
    if len(source_ids) != len(set(source_ids)):
        raise ValueError('DVS database source selection must not contain duplicates')
    reports: list[dict[str, Any]] = []
    for source_id in source_ids:
        source = _by_id(source_id, configured)
        sql = (
            "SELECT JSON_OBJECT("
            "'report_id', report_id,"
            "'report_type', report_type,"
            "'created_at', DATE_FORMAT(created_at, '%Y-%m-%dT%H:%i:%s.%f'),"
            "'source_type', source_type,"
            "'source_id', source_id"
            ") FROM reports ORDER BY created_at DESC LIMIT "
            f"{limit_per_source}"
        )
        for line in _query(source, sql):
            item = json.loads(line)
            if not isinstance(item, dict):
                raise ValueError(f'DVS database source {source.id} returned invalid report summary')
            item['database_source_id'] = source.id
            item['database_source_label'] = source.label
            reports.append(item)
    reports.sort(key=lambda item: str(item.get('created_at') or ''), reverse=True)
    return reports


def load_database_report(
    source_id: str,
    report_id: str,
    *,
    sources_path: Path = DEFAULT_DVS_DATABASE_SOURCES_PATH,
) -> dict[str, Any]:
    if not report_id.strip():
        raise ValueError('report_id must not be empty')
    configured = load_all_dvs_database_sources(sources_path)
    source = _by_id(source_id, configured)
    report_id_hex = report_id.encode('utf-8').hex()
    rows = _query(
        source,
        "SELECT REPLACE(TO_BASE64(report_json), CHAR(10), '') FROM reports "
        f"WHERE report_id = CONVERT(0x{report_id_hex} USING utf8mb4) LIMIT 1",
    )
    if not rows:
        raise KeyError(f'report not found in DVS database source {source_id}: {report_id}')
    raw = base64.b64decode(''.join(rows), validate=True).decode('utf-8')
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError('stored LMTS report root must be an object')
    return payload


def database_source_statuses(
    *,
    sources_path: Path = DEFAULT_DVS_DATABASE_SOURCES_PATH,
    settings_path: Path = DEFAULT_SETTINGS_PATH,
) -> list[dict[str, Any]]:
    statuses: list[dict[str, Any]] = []
    for source in load_all_dvs_database_sources(sources_path, settings_path):
        item: dict[str, Any] = {
            **source.public_dict(),
            'ok': False,
            'reports_table': False,
            'report_count': 0,
            'latest_report_id': None,
            'latest_created_at': None,
            'schema_version': None,
            'error': None,
        }
        try:
            table_rows = _query(
                source,
                "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'reports'",
            )
            has_reports = bool(table_rows and int(table_rows[0]) == 1)
            item['reports_table'] = has_reports
            if not has_reports:
                item['error'] = 'reports table not found'
                statuses.append(item)
                continue

            rows = _query(
                source,
                "SELECT JSON_OBJECT("
                "'report_count', COUNT(*),"
                "'latest_report_id', COALESCE(("
                "SELECT report_id FROM reports ORDER BY created_at DESC, imported_at DESC LIMIT 1"
                "), ''),"
                "'latest_created_at', COALESCE(("
                "SELECT DATE_FORMAT(created_at, '%Y-%m-%dT%H:%i:%s.%f') "
                "FROM reports ORDER BY created_at DESC, imported_at DESC LIMIT 1"
                "), '')"
                ") FROM reports",
            )
            if not rows:
                raise RuntimeError('report count query returned no rows')
            summary = json.loads(rows[0])
            if not isinstance(summary, dict):
                raise RuntimeError('report count query returned invalid JSON')
            item['report_count'] = int(summary.get('report_count') or 0)
            latest_id = str(summary.get('latest_report_id') or '').strip()
            latest_at = str(summary.get('latest_created_at') or '').strip()
            item['latest_report_id'] = latest_id or None
            item['latest_created_at'] = latest_at or None

            version_table = _query(
                source,
                "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'lmts_schema_version'",
            )
            if version_table and int(version_table[0]) == 1:
                version_rows = _query(
                    source,
                    "SELECT COALESCE(MAX(schema_version),0) FROM lmts_schema_version "
                    "WHERE component='result_server'",
                )
                if version_rows:
                    item['schema_version'] = int(version_rows[0])

            item['ok'] = True
        except (RuntimeError, ValueError, json.JSONDecodeError) as exc:
            item['error'] = str(exc)
        statuses.append(item)
    return statuses
