from __future__ import annotations

import json
import os
from pathlib import Path

from .paths import UI_STATE_PATH


UI_STATE_SCHEMA_VERSION = 1
_FORBIDDEN_KEY_PARTS = ('token', 'password', 'secret', 'publish_key')


def _validate_public_state(value: object, *, path: str = '$') -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            name = str(key)
            normalized = name.casefold()
            if any(part in normalized for part in _FORBIDDEN_KEY_PARTS):
                raise ValueError(f'UI state must not contain secret field: {path}.{name}')
            _validate_public_state(item, path=f'{path}.{name}')
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _validate_public_state(item, path=f'{path}[{index}]')


def load_ui_state(path: Path = UI_STATE_PATH) -> dict[str, dict[str, object]]:
    target = path.expanduser()
    if not target.is_file():
        return {}
    try:
        payload = json.loads(target.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f'invalid UI state store: {target}: {exc}') from exc
    if not isinstance(payload, dict) or payload.get('schema_version') != UI_STATE_SCHEMA_VERSION:
        raise ValueError('unsupported UI state store schema')
    scopes = payload.get('scopes')
    if not isinstance(scopes, dict):
        raise ValueError('UI state scopes must be an object')
    normalized: dict[str, dict[str, object]] = {}
    for scope, state in scopes.items():
        if not isinstance(scope, str) or not scope.strip() or not isinstance(state, dict):
            raise ValueError('invalid UI state scope')
        _validate_public_state(state)
        normalized[scope] = dict(state)
    return normalized


def load_ui_scope(scope: str, path: Path = UI_STATE_PATH) -> dict[str, object]:
    value = str(scope).strip()
    if not value:
        raise ValueError('UI state scope must not be empty')
    return dict(load_ui_state(path).get(value, {}))


def save_ui_scope(
    scope: str,
    state: dict[str, object],
    path: Path = UI_STATE_PATH,
) -> Path:
    value = str(scope).strip()
    if not value:
        raise ValueError('UI state scope must not be empty')
    _validate_public_state(state)
    scopes = load_ui_state(path)
    scopes[value] = dict(state)
    payload = {
        'schema_version': UI_STATE_SCHEMA_VERSION,
        'scopes': scopes,
    }
    target = path.expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + f'.tmp-{os.getpid()}')
    temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    os.chmod(temp, 0o600)
    try:
        temp.replace(target)
        os.chmod(target, 0o600)
    finally:
        if temp.exists():
            temp.unlink()
    return target
