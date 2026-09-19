from __future__ import annotations

from dataclasses import dataclass

from lmts.repositories.system import SystemRecord, SystemRepository

from .profile import SystemProfileService


@dataclass(frozen=True, slots=True)
class RunProvenance:
    tester_user_id: str
    system_id: str
    compute_profile_id: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            'tester_user_id': self.tester_user_id,
            'system_id': self.system_id,
            'compute_profile_id': self.compute_profile_id,
        }


class SystemService:
    """Resolve the current probed machine into a persistent user-owned System."""

    def __init__(self, repository: SystemRepository, profile_service: SystemProfileService) -> None:
        self.repository = repository
        self.profile_service = profile_service

    def ensure_current(self, user_id: str) -> SystemRecord:
        profile = self.profile_service.context()
        fingerprint = str(profile.get('fingerprint') or '').strip()
        schema_version = profile.get('schema_version')
        if not fingerprint:
            raise ValueError('system profile has no fingerprint')
        if isinstance(schema_version, bool) or not isinstance(schema_version, int):
            raise ValueError('system profile has invalid schema_version')
        return self.repository.ensure_system(
            user_id=user_id,
            fingerprint=fingerprint,
            profile_schema_version=schema_version,
        )

    def run_provenance(self, user_id: str) -> RunProvenance:
        system = self.ensure_current(user_id)
        return RunProvenance(
            tester_user_id=user_id,
            system_id=system.system_id,
            compute_profile_id=None,
        )
