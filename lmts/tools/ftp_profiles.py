from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


FTP_PROFILES_SCHEMA_VERSION = 2
DEFAULT_FTP_PROFILES_PATH = Path('.lmts/ftp-profiles.json')


@dataclass(frozen=True, slots=True)
class FTPProfile:
    name: str
    host: str
    username: str
    password: str
    root: str
    port: int = 21

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError('FTP profile name must not be empty')
        if not self.host.strip():
            raise ValueError('FTP host must not be empty')
        if not self.username.strip():
            raise ValueError('FTP username must not be empty')
        if not 1 <= int(self.port) <= 65535:
            raise ValueError('FTP port must be between 1 and 65535')

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class FTPProfiles:
    schema_version: int = FTP_PROFILES_SCHEMA_VERSION
    profiles: tuple[FTPProfile, ...] = ()

    def by_name(self, name: str) -> FTPProfile | None:
        for profile in self.profiles:
            if profile.name == name:
                return profile
        return None

    def upsert(self, profile: FTPProfile) -> 'FTPProfiles':
        items = [item for item in self.profiles if item.name != profile.name]
        items.append(profile)
        items.sort(key=lambda item: item.name.casefold())
        return FTPProfiles(profiles=tuple(items))

    def remove(self, name: str) -> 'FTPProfiles':
        return FTPProfiles(profiles=tuple(item for item in self.profiles if item.name != name))


def load_ftp_profiles(path: Path = DEFAULT_FTP_PROFILES_PATH) -> FTPProfiles:
    path = path.expanduser()
    if not path.is_file():
        return FTPProfiles()
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError('FTP profile store must be an object')
    if payload.get('schema_version') != FTP_PROFILES_SCHEMA_VERSION:
        raise ValueError('unsupported FTP profile store schema')
    raw_profiles = payload.get('profiles')
    if not isinstance(raw_profiles, list):
        raise ValueError('FTP profile store profiles must be a list')

    profiles: list[FTPProfile] = []
    names: set[str] = set()
    for raw in raw_profiles:
        if not isinstance(raw, dict):
            raise ValueError('FTP profile must be an object')
        profile = FTPProfile(
            name=str(raw.get('name') or '').strip(),
            host=str(raw.get('host') or '').strip(),
            username=str(raw.get('username') or '').strip(),
            password=str(raw.get('password') or ''),
            root=str(raw.get('root') or '').strip(),
            port=int(raw.get('port') or 21),
        )
        if profile.name in names:
            raise ValueError(f'duplicate FTP profile name: {profile.name}')
        names.add(profile.name)
        profiles.append(profile)
    profiles.sort(key=lambda item: item.name.casefold())
    return FTPProfiles(profiles=tuple(profiles))


def save_ftp_profiles(profiles: FTPProfiles, path: Path = DEFAULT_FTP_PROFILES_PATH) -> Path:
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        'schema_version': FTP_PROFILES_SCHEMA_VERSION,
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
