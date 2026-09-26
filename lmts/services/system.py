from __future__ import annotations

from dataclasses import dataclass

from lmts.repositories.system import SystemRecord, SystemRepository, system_id_for

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

    def __init__(self, repository: SystemRepository | None, profile_service: SystemProfileService) -> None:
        self.repository = repository
        self.profile_service = profile_service

    def _profile_identity(self) -> tuple[str, int]:
        profile = self.profile_service.context()
        fingerprint = str(profile.get('fingerprint') or '').strip()
        schema_version = profile.get('schema_version')
        if not fingerprint:
            raise ValueError('system profile has no fingerprint')
        if isinstance(schema_version, bool) or not isinstance(schema_version, int):
            raise ValueError('system profile has invalid schema_version')
        return fingerprint, schema_version

    def build_run_provenance(self, user_id: str) -> RunProvenance:
        fingerprint, _schema_version = self._profile_identity()
        return RunProvenance(
            tester_user_id=user_id,
            system_id=system_id_for(user_id, fingerprint),
            compute_profile_id=None,
        )

    def ensure_current(self, user_id: str) -> SystemRecord:
        if self.repository is None:
            raise RuntimeError('local system persistence is not configured')
        fingerprint, schema_version = self._profile_identity()
        return self.repository.ensure_system(
            user_id=user_id,
            fingerprint=fingerprint,
            profile_schema_version=schema_version,
        )

    def run_provenance(self, user_id: str) -> RunProvenance:
        return self.build_run_provenance(user_id)
