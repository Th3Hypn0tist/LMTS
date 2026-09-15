from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from lmts.core.settings import MySQLSettings


SCHEMA_PATH = Path(__file__).resolve().parent.parent / 'install' / 'schema_v1.sql'


def _client_error(stderr: bytes, returncode: int) -> str:
    text = stderr.decode('utf-8', errors='replace').strip()
    if not text:
        return f'MySQL schema install failed with exit code {returncode}'
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    non_warnings = [line for line in lines if not line.casefold().startswith('warning:')]
    return (non_warnings or lines)[-1]


def install_mysql_schema(mysql: MySQLSettings, *, schema_path: Path = SCHEMA_PATH) -> None:
    if not mysql.password:
        raise ValueError('MySQL password must not be empty for schema installation')

    client = shutil.which('mariadb') or shutil.which('mysql')
    if client is None:
        raise RuntimeError('mariadb/mysql client is required to install the LMTS schema')
    if not schema_path.is_file():
        raise RuntimeError(f'LMTS schema file not found: {schema_path}')

    command = [
        client,
        f'--host={mysql.host}',
        f'--user={mysql.username}',
        '--protocol=tcp',
        '--default-character-set=utf8mb4',
        mysql.database,
    ]
    env = dict(os.environ)
    env['MYSQL_PWD'] = mysql.password

    try:
        with schema_path.open('rb') as source:
            completed = subprocess.run(
                command,
                stdin=source,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                check=False,
            )
    except OSError as exc:
        raise RuntimeError(f'cannot run MySQL client: {exc}') from exc

    if completed.returncode != 0:
        raise RuntimeError(_client_error(completed.stderr, completed.returncode))
