from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


SETTINGS_SCHEMA_VERSION = 1
DEFAULT_SETTINGS_PATH = Path('.lmts/settings.json')
DEFAULT_OUTPUT_FOLDER = 'exports'


@dataclass(frozen=True, slots=True)
class LMTSSettings:
    schema_version: int = SETTINGS_SCHEMA_VERSION
    output_folder: str = DEFAULT_OUTPUT_FOLDER

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _normalise_output_folder(value: object) -> str:
    text = str(value or '').strip()
    return text or DEFAULT_OUTPUT_FOLDER


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
    if payload.get('schema_version') != SETTINGS_SCHEMA_VERSION:
        return LMTSSettings()
    return LMTSSettings(output_folder=_normalise_output_folder(payload.get('output_folder')))


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
