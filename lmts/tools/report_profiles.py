from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

REPORT_PROFILES_SCHEMA_VERSION = 1
DEFAULT_REPORT_PROFILES_PATH = Path('.lmts/report-profiles.json')


@dataclass(frozen=True, slots=True)
class ReportProfile:
    name: str
    endpoint: str
    publish_key: str = 'lmts'

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError('report profile name must not be empty')
        endpoint = self.endpoint.strip()
        if not endpoint:
            raise ValueError('report endpoint must not be empty')
        if not endpoint.startswith(('http://', 'https://')):
            raise ValueError('report endpoint must use http:// or https://')

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ReportProfiles:
    schema_version: int = REPORT_PROFILES_SCHEMA_VERSION
    profiles: tuple[ReportProfile, ...] = ()

    def by_name(self, name: str) -> ReportProfile | None:
        for profile in self.profiles:
            if profile.name == name:
                return profile
        return None

    def upsert(self, profile: ReportProfile) -> 'ReportProfiles':
        items = [item for item in self.profiles if item.name != profile.name]
        items.append(profile)
        items.sort(key=lambda item: item.name.casefold())
        return ReportProfiles(profiles=tuple(items))

    def remove(self, name: str) -> 'ReportProfiles':
        return ReportProfiles(profiles=tuple(item for item in self.profiles if item.name != name))


def load_report_profiles(path: Path = DEFAULT_REPORT_PROFILES_PATH) -> ReportProfiles:
    path = path.expanduser()
    if not path.is_file():
        return ReportProfiles()
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict) or payload.get('schema_version') != REPORT_PROFILES_SCHEMA_VERSION:
        raise ValueError('unsupported report profile store schema')
    raw_profiles = payload.get('profiles')
    if not isinstance(raw_profiles, list):
        raise ValueError('report profile store profiles must be a list')

    profiles: list[ReportProfile] = []
    names: set[str] = set()
    for raw in raw_profiles:
        if not isinstance(raw, dict):
            raise ValueError('report profile must be an object')
        profile = ReportProfile(
            name=str(raw.get('name') or '').strip(),
            endpoint=str(raw.get('endpoint') or '').strip(),
            publish_key=str(raw.get('publish_key') or 'lmts'),
        )
        if profile.name in names:
            raise ValueError(f'duplicate report profile name: {profile.name}')
        names.add(profile.name)
        profiles.append(profile)
    profiles.sort(key=lambda item: item.name.casefold())
    return ReportProfiles(profiles=tuple(profiles))


def save_report_profiles(profiles: ReportProfiles, path: Path = DEFAULT_REPORT_PROFILES_PATH) -> Path:
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        'schema_version': REPORT_PROFILES_SCHEMA_VERSION,
        'profiles': [profile.to_dict() for profile in profiles.profiles],
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
