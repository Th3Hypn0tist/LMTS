from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lmts.tools.profile import DEFAULT_PROFILE_PATH, load_system_profile, save_system_profile, scan_system_profile


@dataclass(frozen=True, slots=True)
class ProfileStatus:
    required: bool
    profiled_at: str


@dataclass(frozen=True, slots=True)
class ProfileResult:
    path: Path
    data: dict[str, object]
    status: ProfileStatus


class SystemProfileService:
    def __init__(self, profile_path: Path) -> None:
        self.profile_path = profile_path

    def load(self) -> dict[str, object] | None:
        return load_system_profile(self.profile_path)

    def context(self) -> dict[str, object]:
        payload = self.load()
        if payload is None:
            raise ValueError('valid canonical system profile required before testing')
        return payload

    def status(self) -> ProfileStatus:
        payload = self.load()
        return ProfileStatus(
            required=payload is None,
            profiled_at=str(payload.get('profiled_at') or '') if payload is not None else '',
        )

    def scan(self) -> ProfileResult:
        profile = scan_system_profile()
        path = save_system_profile(profile, self.profile_path)
        data = profile.to_dict()
        status = self.status()
        return ProfileResult(path=path, data=data, status=status)
