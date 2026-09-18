from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from lmts.core.paths import REPORT_PROFILES_PATH


REPORT_PROFILES_SCHEMA_VERSION = 3
DEFAULT_REPORT_PROFILES_PATH = REPORT_PROFILES_PATH
ReportTargetKind = Literal['php_api', 'mysql']


@dataclass(frozen=True, slots=True)
class ReportProfile:
    name: str
    endpoint: str = ''
    publish_key: str = 'lmts'
    kind: ReportTargetKind = 'php_api'

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError('report profile name must not be empty')
        if self.kind not in {'php_api', 'mysql'}:
            raise ValueError(f'unsupported report target kind: {self.kind}')
        endpoint = self.endpoint.strip()
        publish_key = self.publish_key.strip()
        if self.kind == 'php_api':
            if not endpoint:
                raise ValueError('PHP API report endpoint must not be empty')
            if not endpoint.startswith(('http://', 'https://')):
                raise ValueError('PHP API report endpoint must use http:// or https://')
            if not publish_key:
                raise ValueError('PHP API report publish key must not be empty')
            return
        if endpoint:
            raise ValueError('MySQL report target uses LMTS MySQL settings and must not define an HTTP endpoint')
        if publish_key:
            raise ValueError('MySQL report target uses LMTS MySQL settings and must not define a publish key')

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ReportProfiles:
    schema_version: int = REPORT_PROFILES_SCHEMA_VERSION
    profiles: tuple[ReportProfile, ...] = ()
    auto_publish_profile: str | None = None

    def __post_init__(self) -> None:
        if self.auto_publish_profile is not None and self.by_name(self.auto_publish_profile) is None:
            raise ValueError(f'auto-publish report profile does not exist: {self.auto_publish_profile}')

    def by_name(self, name: str) -> ReportProfile | None:
        for profile in self.profiles:
            if profile.name == name:
                return profile
        return None

    def upsert(self, profile: ReportProfile) -> 'ReportProfiles':
        items = [item for item in self.profiles if item.name != profile.name]
        items.append(profile)
        items.sort(key=lambda item: item.name.casefold())
        return ReportProfiles(profiles=tuple(items), auto_publish_profile=self.auto_publish_profile)

    def remove(self, name: str) -> 'ReportProfiles':
        remaining = tuple(item for item in self.profiles if item.name != name)
        auto = None if self.auto_publish_profile == name else self.auto_publish_profile
        return ReportProfiles(profiles=remaining, auto_publish_profile=auto)

    def with_auto_publish(self, name: str | None) -> 'ReportProfiles':
        if name is not None and self.by_name(name) is None:
            raise KeyError(f'unknown report profile: {name}')
        return ReportProfiles(profiles=self.profiles, auto_publish_profile=name)

    def auto_publish(self) -> ReportProfile | None:
        return None if self.auto_publish_profile is None else self.by_name(self.auto_publish_profile)


def load_report_profiles(path: Path = DEFAULT_REPORT_PROFILES_PATH) -> ReportProfiles:
    path = path.expanduser()
    if not path.is_file():
        return ReportProfiles()
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError('report profile store root must be an object')
    schema_version = payload.get('schema_version')
    if schema_version not in {1, 2, REPORT_PROFILES_SCHEMA_VERSION}:
        raise ValueError('unsupported report profile store schema')
    raw_profiles = payload.get('profiles')
    if not isinstance(raw_profiles, list):
        raise ValueError('report profile store profiles must be a list')

    profiles: list[ReportProfile] = []
    names: set[str] = set()
    for raw in raw_profiles:
        if not isinstance(raw, dict):
            raise ValueError('report profile must be an object')
        kind = 'php_api' if schema_version in {1, 2} else str(raw.get('kind') or 'php_api').strip()
        raw_publish_key = raw.get('publish_key')
        profile = ReportProfile(
            name=str(raw.get('name') or '').strip(),
            endpoint=str(raw.get('endpoint') or '').strip(),
            publish_key=str(raw_publish_key if raw_publish_key is not None else ('lmts' if kind == 'php_api' else '')),
            kind=kind,
        )
        if profile.name in names:
            raise ValueError(f'duplicate report profile name: {profile.name}')
        names.add(profile.name)
        profiles.append(profile)
    profiles.sort(key=lambda item: item.name.casefold())
    auto_publish_profile = None
    if schema_version in {2, REPORT_PROFILES_SCHEMA_VERSION}:
        raw_auto = payload.get('auto_publish_profile')
        if raw_auto is not None:
            auto_publish_profile = str(raw_auto).strip() or None
    return ReportProfiles(
        profiles=tuple(profiles),
        auto_publish_profile=auto_publish_profile,
    )


def save_report_profiles(profiles: ReportProfiles, path: Path = DEFAULT_REPORT_PROFILES_PATH) -> Path:
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        'schema_version': REPORT_PROFILES_SCHEMA_VERSION,
        'profiles': [profile.to_dict() for profile in profiles.profiles],
        'auto_publish_profile': profiles.auto_publish_profile,
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
