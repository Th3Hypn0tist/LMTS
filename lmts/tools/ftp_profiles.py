from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping

from lmts.core.paths import FTP_PROFILES_PATH


FTP_PROFILES_SCHEMA_VERSION = 3
DEFAULT_FTP_PROFILES_PATH = FTP_PROFILES_PATH


@dataclass(frozen=True, slots=True)
class FTPProfile:
    name: str
    host: str
    username: str
    password_env: str
    root: str
    port: int = 21

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError('FTPS profile name must not be empty')
        if not self.host.strip():
            raise ValueError('FTPS host must not be empty')
        if not self.username.strip():
            raise ValueError('FTPS username must not be empty')
        if not self.password_env.strip() or self.password_env != self.password_env.strip():
            raise ValueError('FTPS password environment variable must be a non-empty canonical string')
        if not self.root.strip():
            raise ValueError('FTPS target root must not be empty')
        if not 1 <= int(self.port) <= 65535:
            raise ValueError('FTPS port must be between 1 and 65535')

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def resolve_password(self, environment: Mapping[str, str] | None = None) -> str:
        source = os.environ if environment is None else environment
        value = source.get(self.password_env)
        if not value:
            raise RuntimeError(
                f'FTPS password environment variable is not set or empty: {self.password_env}'
            )
        return value


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
        raise ValueError('FTPS profile store must be an object')
    schema_version = payload.get('schema_version')
    if schema_version == 2:
        raise ValueError(
            'legacy FTPS profile schema 2 contains plaintext passwords; recreate profiles using password_env'
        )
    if schema_version != FTP_PROFILES_SCHEMA_VERSION:
        raise ValueError('unsupported FTPS profile store schema')
    raw_profiles = payload.get('profiles')
    if not isinstance(raw_profiles, list):
        raise ValueError('FTPS profile store profiles must be a list')

    profiles: list[FTPProfile] = []
    names: set[str] = set()
    for raw in raw_profiles:
        if not isinstance(raw, dict):
            raise ValueError('FTPS profile must be an object')
        if 'password' in raw:
            raise ValueError('FTPS profile store must not contain plaintext password fields')
        profile = FTPProfile(
            name=str(raw.get('name') or '').strip(),
            host=str(raw.get('host') or '').strip(),
            username=str(raw.get('username') or '').strip(),
            password_env=str(raw.get('password_env') or ''),
            root=str(raw.get('root') or '').strip(),
            port=int(raw.get('port') or 21),
        )
        if profile.name in names:
            raise ValueError(f'duplicate FTPS profile name: {profile.name}')
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
    if '"password"' in text:
        raise ValueError('FTPS profile store serialization contains a plaintext password field')
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
