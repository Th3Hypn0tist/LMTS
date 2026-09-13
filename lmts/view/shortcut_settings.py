from __future__ import annotations

import json
import os
from pathlib import Path


SHORTCUT_SETTINGS_SCHEMA_VERSION = 1
DEFAULT_SHORTCUT_SETTINGS_PATH = Path('.lmts/shortcuts.json')


def normalise_sequence_text(value: str) -> tuple[str, ...]:
    aliases = {
        'escape': 'esc',
        'return': 'enter',
        'pageup': 'pgup',
        'pagedown': 'pgdn',
    }
    tokens = tuple(aliases.get(token.casefold(), token.casefold()) for token in value.split() if token.strip())
    if not tokens:
        raise ValueError('shortcut sequence must not be empty')
    return tokens


def load_shortcut_overrides(
    path: Path = DEFAULT_SHORTCUT_SETTINGS_PATH,
) -> dict[str, tuple[str, ...]]:
    path = path.expanduser()
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict) or payload.get('schema_version') != SHORTCUT_SETTINGS_SCHEMA_VERSION:
        raise ValueError('unsupported shortcut settings schema')
    raw = payload.get('bindings')
    if not isinstance(raw, dict):
        raise ValueError('shortcut settings bindings must be an object')

    output: dict[str, tuple[str, ...]] = {}
    for action, sequence in raw.items():
        if not isinstance(action, str) or not action.strip():
            raise ValueError('shortcut action must be a non-empty string')
        if not isinstance(sequence, list) or not sequence or any(not isinstance(item, str) or not item for item in sequence):
            raise ValueError(f'invalid shortcut sequence for {action}')
        output[action] = tuple(item.casefold() for item in sequence)
    return output


def save_shortcut_overrides(
    bindings: dict[str, tuple[str, ...]],
    path: Path = DEFAULT_SHORTCUT_SETTINGS_PATH,
) -> Path:
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        'schema_version': SHORTCUT_SETTINGS_SCHEMA_VERSION,
        'bindings': {action: list(sequence) for action, sequence in sorted(bindings.items())},
    }
    text = json.dumps(payload, indent=2, ensure_ascii=False) + '\n'
    temp = path.with_suffix(path.suffix + f'.tmp-{os.getpid()}')
    temp.write_text(text, encoding='utf-8')
    try:
        temp.replace(path)
        os.chmod(path, 0o600)
    finally:
        if temp.exists():
            temp.unlink()
    return path
