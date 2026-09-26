from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .paths import SETTINGS_PATH


SETTINGS_SCHEMA_VERSION = 7
DEFAULT_SETTINGS_PATH = SETTINGS_PATH
DEFAULT_OUTPUT_FOLDER = 'exports'


@dataclass(frozen=True, slots=True)
class MySQLSettings:
    id: str = 'local'
    label: str = 'Local MySQL'
    host: str = 'localhost'
    port: int = 3306
    database: str = 'lmts'
    username: str = 'lmts'
    password: str = 'lmts'
    publish_key: str = 'lmts'

    def __post_init__(self) -> None:
        for name, value in (
            ('id', self.id),
            ('label', self.label),
            ('host', self.host),
            ('database', self.database),
            ('username', self.username),
            ('password', self.password),
            ('publish_key', self.publish_key),
        ):
            if not str(value).strip():
                raise ValueError(f'MySQL {name} must not be empty')
        if isinstance(self.port, bool) or not isinstance(self.port, int) or not 1 <= self.port <= 65535:
            raise ValueError('MySQL port must be an integer between 1 and 65535')


@dataclass(frozen=True, slots=True)
class PHPAPISettings:
    id: str = 'api'
    label: str = 'PHP API'
    base_url: str = ''
    publish_key: str = ''

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError('PHP API id must not be empty')
        if not self.label.strip():
            raise ValueError('PHP API label must not be empty')
        base_url = self.base_url.strip()
        if base_url and not base_url.startswith(('http://', 'https://')):
            raise ValueError('PHP API base_url must use http:// or https://')
        if base_url and not self.publish_key.strip():
            raise ValueError('PHP API publish_key must not be empty when base_url is configured')

    @property
    def configured(self) -> bool:
        return bool(self.base_url.strip() and self.publish_key.strip())

    @property
    def report_endpoint(self) -> str:
        if not self.configured:
            raise ValueError('PHP API is not configured')
        return f"{self.base_url.rstrip('/')}/storage/report.php"

    @property
    def reports_endpoint(self) -> str:
        if not self.configured:
            raise ValueError('PHP API is not configured')
        return f"{self.base_url.rstrip('/')}/api/reports.php"



def mysql_target_id(connection_id: str) -> str:
    return f'mysql:{connection_id}'


def php_api_target_id(connection_id: str) -> str:
    return f'php_api:{connection_id}'


@dataclass(frozen=True, slots=True)
class LMTSSettings:
    schema_version: int = SETTINGS_SCHEMA_VERSION
    output_folder: str = DEFAULT_OUTPUT_FOLDER
    mysql_connections: tuple[MySQLSettings, ...] = field(default_factory=lambda: (MySQLSettings(),))
    php_api_connections: tuple[PHPAPISettings, ...] = ()
    auto_publish_targets: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.mysql_connections:
            raise ValueError('LMTS requires at least one MySQL connection')
        mysql_ids = [item.id for item in self.mysql_connections]
        api_ids = [item.id for item in self.php_api_connections]
        if len(mysql_ids) != len(set(mysql_ids)):
            raise ValueError('MySQL connection ids must be unique')
        if len(api_ids) != len(set(api_ids)):
            raise ValueError('PHP API connection ids must be unique')
        if any(not item.configured for item in self.php_api_connections):
            raise ValueError('PHP API connections stored in LMTS settings must be fully configured')
        available = {
            *(mysql_target_id(item.id) for item in self.mysql_connections),
            *(php_api_target_id(item.id) for item in self.php_api_connections),
        }
        if len(self.auto_publish_targets) != len(set(self.auto_publish_targets)):
            raise ValueError('auto-publish targets must not contain duplicates')
        unknown = [target for target in self.auto_publish_targets if target not in available]
        if unknown:
            raise ValueError(f"unknown auto-publish target(s): {', '.join(unknown)}")

    @property
    def mysql(self) -> MySQLSettings:
        return self.mysql_connections[0]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _normalise_output_folder(value: object) -> str:
    text = str(value or '').strip()
    return text or DEFAULT_OUTPUT_FOLDER


def _mysql_from_payload(value: object, *, default_id: str = 'local', default_label: str = 'Local MySQL') -> MySQLSettings:
    if value is None:
        return MySQLSettings(id=default_id, label=default_label)
    if not isinstance(value, dict):
        raise ValueError('MySQL connection must be an object')
    raw_port = value.get('port', 3306)
    if isinstance(raw_port, bool):
        raise ValueError('MySQL port must be an integer')
    try:
        port = int(raw_port)
    except (TypeError, ValueError) as exc:
        raise ValueError('MySQL port must be an integer') from exc
    return MySQLSettings(
        id=str(value.get('id') or default_id).strip(),
        label=str(value.get('label') or default_label).strip(),
        host=str(value.get('host') or 'localhost').strip(),
        port=port,
        database=str(value.get('database') or 'lmts').strip(),
        username=str(value.get('username') or 'lmts').strip(),
        password=str(value.get('password') if value.get('password') is not None else 'lmts'),
        publish_key=str(value.get('publish_key') or 'lmts').strip(),
    )


def _php_api_from_payload(value: object, *, default_id: str, default_label: str) -> PHPAPISettings:
    if value is None:
        return PHPAPISettings(id=default_id, label=default_label)
    if not isinstance(value, dict):
        raise ValueError('PHP API connection must be an object')
    return PHPAPISettings(
        id=str(value.get('id') or default_id).strip(),
        label=str(value.get('label') or default_label).strip(),
        base_url=str(value.get('base_url') or '').strip(),
        publish_key=str(value.get('publish_key') or '').strip(),
    )


def _mysql_connections_from_payload(value: object) -> tuple[MySQLSettings, ...]:
    if not isinstance(value, list):
        raise ValueError('settings.mysql_connections must be an array')
    return tuple(
        _mysql_from_payload(item, default_id=f'mysql-{index + 1}', default_label=f'MySQL {index + 1}')
        for index, item in enumerate(value)
    )


def _php_connections_from_payload(value: object) -> tuple[PHPAPISettings, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError('settings.php_api_connections must be an array')
    return tuple(
        _php_api_from_payload(item, default_id=f'api-{index + 1}', default_label=f'PHP API {index + 1}')
        for index, item in enumerate(value)
    )


def _migrate_v5(payload: dict[str, object]) -> LMTSSettings:
    mysql = _mysql_from_payload(payload.get('mysql'))
    api_connections: list[PHPAPISettings] = []
    legacy_dvstudio = _php_api_from_payload(payload.get('dvstudio_php_api'), default_id='legacy-dvstudio', default_label='Legacy PHP API 1')
    if legacy_dvstudio.configured:
        api_connections.append(legacy_dvstudio)
    legacy_dvisualizer = _php_api_from_payload(payload.get('dvisualizer_php_api'), default_id='legacy-dvisualizer', default_label='Legacy PHP API 2')
    if legacy_dvisualizer.configured:
        api_connections.append(legacy_dvisualizer)
    legacy_target = str(payload.get('auto_publish_target') or '').strip()
    mapping = {
        'dvstudio.mysql': mysql_target_id(mysql.id),
        'dvstudio.php_api': php_api_target_id(legacy_dvstudio.id),
        'dvisualizer.php_api': php_api_target_id(legacy_dvisualizer.id),
    }
    mapped = mapping.get(legacy_target)
    available = {mysql_target_id(mysql.id), *(php_api_target_id(item.id) for item in api_connections)}
    auto = (mapped,) if mapped in available else ()
    return LMTSSettings(
        output_folder=_normalise_output_folder(payload.get('output_folder')),
        mysql_connections=(mysql,),
        php_api_connections=tuple(api_connections),
        auto_publish_targets=auto,
    )


def load_settings(path: Path = DEFAULT_SETTINGS_PATH) -> LMTSSettings:
    path = path.expanduser()
    if not path.is_file():
        return LMTSSettings()
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except OSError as exc:
        raise RuntimeError(f'cannot read LMTS settings: {path}: {exc}') from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f'invalid LMTS settings JSON: {path}: {exc}') from exc
    if not isinstance(payload, dict):
        raise ValueError('LMTS settings root must be an object')

    schema_version = payload.get('schema_version')
    if schema_version == 1:
        return LMTSSettings(output_folder=_normalise_output_folder(payload.get('output_folder')))
    if schema_version in {2, 3, 4}:
        return LMTSSettings(output_folder=_normalise_output_folder(payload.get('output_folder')), mysql_connections=(_mysql_from_payload(payload.get('mysql')),))
    if schema_version == 5:
        return _migrate_v5(payload)
    if schema_version == 6:
        return LMTSSettings(
            output_folder=_normalise_output_folder(payload.get('output_folder')),
            mysql_connections=_mysql_connections_from_payload(payload.get('mysql_connections')),
            php_api_connections=_php_connections_from_payload(payload.get('php_api_connections')),
            auto_publish_targets=tuple(str(item).strip() for item in (payload.get('auto_publish_targets') or []) if str(item).strip()),
        )
    if schema_version != SETTINGS_SCHEMA_VERSION:
        raise ValueError(f'unsupported LMTS settings schema: {schema_version!r}')

    raw_auto = payload.get('auto_publish_targets')
    if raw_auto is None:
        auto_publish_targets: tuple[str, ...] = ()
    elif isinstance(raw_auto, list) and all(isinstance(item, str) for item in raw_auto):
        auto_publish_targets = tuple(str(item).strip() for item in raw_auto if str(item).strip())
    else:
        raise ValueError('settings.auto_publish_targets must be an array of strings')
    return LMTSSettings(
        output_folder=_normalise_output_folder(payload.get('output_folder')),
        mysql_connections=_mysql_connections_from_payload(payload.get('mysql_connections')),
        php_api_connections=_php_connections_from_payload(payload.get('php_api_connections')),
        auto_publish_targets=auto_publish_targets,
    )


def save_settings(settings: LMTSSettings, path: Path = DEFAULT_SETTINGS_PATH) -> Path:
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(settings.to_dict(), indent=2, ensure_ascii=False) + '\n'
    temp = path.with_suffix(path.suffix + f'.tmp-{os.getpid()}')
    temp.write_text(payload, encoding='utf-8')
    os.chmod(temp, 0o600)
    try:
        temp.replace(path)
        os.chmod(path, 0o600)
    finally:
        if temp.exists():
            temp.unlink()
    return path
