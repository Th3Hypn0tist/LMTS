from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path


SETTINGS_SCHEMA_VERSION = 3
DEFAULT_SETTINGS_PATH = Path('.lmts/settings.json')
DEFAULT_OUTPUT_FOLDER = 'exports'


@dataclass(frozen=True, slots=True)
class MySQLSettings:
    host: str = 'localhost'
    database: str = 'lmts'
    username: str = 'lmts'
    password: str = 'lmts'
    publish_key: str = 'lmts'

    def __post_init__(self) -> None:
        for label, value in (
            ('host', self.host),
            ('database', self.database),
            ('username', self.username),
            ('publish_key', self.publish_key),
        ):
            if not str(value).strip():
                raise ValueError(f'MySQL {label} must not be empty')


@dataclass(frozen=True, slots=True)
class DVSSettings:
    host: str = '127.0.0.1'
    port: int = 8775
    s3d_root: str = '../S3D'
    studio_root: str = '.lmts/dvs'

    def __post_init__(self) -> None:
        if not str(self.host).strip():
            raise ValueError('DVS host must not be empty')
        if isinstance(self.port, bool) or not isinstance(self.port, int) or not 1 <= self.port <= 65535:
            raise ValueError('DVS port must be an integer between 1 and 65535')
        if not str(self.studio_root).strip():
            raise ValueError('DVS Studio root must not be empty')


@dataclass(frozen=True, slots=True)
class LMTSSettings:
    schema_version: int = SETTINGS_SCHEMA_VERSION
    output_folder: str = DEFAULT_OUTPUT_FOLDER
    mysql: MySQLSettings = field(default_factory=MySQLSettings)
    dvs: DVSSettings = field(default_factory=DVSSettings)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _normalise_output_folder(value: object) -> str:
    text = str(value or '').strip()
    return text or DEFAULT_OUTPUT_FOLDER


def _mysql_from_payload(value: object) -> MySQLSettings:
    if not isinstance(value, dict):
        return MySQLSettings()
    return MySQLSettings(
        host=str(value.get('host') or 'localhost').strip(),
        database=str(value.get('database') or 'lmts').strip(),
        username=str(value.get('username') or 'lmts').strip(),
        password=str(value.get('password') if value.get('password') is not None else 'lmts'),
        publish_key=str(value.get('publish_key') or 'lmts').strip(),
    )


def _dvs_from_payload(value: object) -> DVSSettings:
    if not isinstance(value, dict):
        return DVSSettings()
    port = value.get('port', 8775)
    if isinstance(port, bool):
        raise ValueError('DVS port must be an integer')
    try:
        parsed_port = int(port)
    except (TypeError, ValueError) as exc:
        raise ValueError('DVS port must be an integer') from exc
    return DVSSettings(
        host=str(value.get('host') or '127.0.0.1').strip(),
        port=parsed_port,
        s3d_root=str(value.get('s3d_root') if value.get('s3d_root') is not None else '../S3D').strip(),
        studio_root=str(value.get('studio_root') or '.lmts/dvs').strip(),
    )


def load_settings(path: Path = DEFAULT_SETTINGS_PATH) -> LMTSSettings:
    path = path.expanduser()
    if not path.is_file():
        return LMTSSettings()
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError, TypeError):
        return LMTSSettings()
    if not isinstance(payload, dict):
        return LMTSSettings()

    schema_version = payload.get('schema_version')
    if schema_version == 1:
        return LMTSSettings(output_folder=_normalise_output_folder(payload.get('output_folder')))
    if schema_version not in {2, SETTINGS_SCHEMA_VERSION}:
        return LMTSSettings()

    try:
        mysql = _mysql_from_payload(payload.get('mysql'))
    except ValueError:
        mysql = MySQLSettings()
    try:
        dvs = _dvs_from_payload(payload.get('dvs'))
    except ValueError:
        dvs = DVSSettings()
    return LMTSSettings(
        output_folder=_normalise_output_folder(payload.get('output_folder')),
        mysql=mysql,
        dvs=dvs,
    )


def save_settings(settings: LMTSSettings, path: Path = DEFAULT_SETTINGS_PATH) -> Path:
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(settings.to_dict(), indent=2, ensure_ascii=False) + '\n'
    temp = path.with_suffix(path.suffix + f'.tmp-{os.getpid()}')
    temp.write_text(payload, encoding='utf-8')
    try:
        temp.replace(path)
    finally:
        if temp.exists():
            temp.unlink()
    return path
