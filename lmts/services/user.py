from __future__ import annotations

from dataclasses import dataclass

from lmts.repositories.user import UserRepository

from .auth import AuthService, AuthenticationError, is_origin


TIER_LABELS = {
    4: 'Reader',
    3: 'Registered',
    2: 'Invite-capable',
    1: 'Canonical authority',
    1337: 'Test-content authority',
}

EMPTY_ACTIVITY = {
    'reports': 0,
    'submissions': 0,
    'result_records': 0,
    'pass': 0,
    'fail': 0,
    'error': 0,
    'cancelled': 0,
    'unknown': 0,
    'test_definitions': 0,
    'test_versions': 0,
    'telemetry_values': 0,
    'models': 0,
    'compositions': 0,
    'systems': 0,
    'compute_profiles': 0,
    'hardware_nodes': 0,
}


@dataclass(frozen=True, slots=True)
class UserDashboardSnapshot:
    user_id: str | None
    username: str | None
    tier: int
    tier_label: str
    status: str
    verified: bool | None
    can_invite: bool
    activity: dict[str, int]
    identity_error: str | None = None


class UserService:
    """Authenticated user dashboard boundary backed by canonical database state."""

    def __init__(self, repository: UserRepository | None, auth_service: AuthService | None) -> None:
        self.repository = repository
        self.auth_service = auth_service
        self._snapshot: UserDashboardSnapshot | None = None

    @staticmethod
    def _anonymous(identity_error: str | None = None) -> UserDashboardSnapshot:
        return UserDashboardSnapshot(
            user_id=None,
            username=None,
            tier=4,
            tier_label=TIER_LABELS[4],
            status='anonymous',
            verified=None,
            can_invite=False,
            activity=dict(EMPTY_ACTIVITY),
            identity_error=identity_error,
        )

    def dashboard_snapshot(self, *, refresh: bool = False) -> UserDashboardSnapshot:
        if self._snapshot is not None and not refresh:
            return self._snapshot
        if self.auth_service is None:
            self._snapshot = self._anonymous('IAM authentication is not configured')
            return self._snapshot
        if self.auth_service.local_mode:
            local = self._anonymous()
            self._snapshot = UserDashboardSnapshot(
                user_id=None,
                username='local',
                tier=4,
                tier_label='Local',
                status='local',
                verified=None,
                can_invite=False,
                activity=dict(EMPTY_ACTIVITY),
                identity_error=None,
            )
            return self._snapshot
        try:
            identity = self.auth_service.current_identity()
        except (AuthenticationError, RuntimeError, ValueError) as exc:
            self._snapshot = self._anonymous(str(exc))
            return self._snapshot
        if identity is None:
            self._snapshot = self._anonymous()
            return self._snapshot
        if self.repository is None:
            activity = dict(EMPTY_ACTIVITY)
            warning = 'local user activity database is not configured'
        else:
            try:
                activity = self.repository.activity_for_user(identity.user_id).to_dict()
            except (RuntimeError, ValueError) as exc:
                activity = dict(EMPTY_ACTIVITY)
                warning = str(exc)
            else:
                warning = None
        self._snapshot = UserDashboardSnapshot(
            user_id=identity.user_id,
            username=identity.username,
            tier=identity.tier,
            tier_label=TIER_LABELS.get(identity.tier, f'Tier {identity.tier}'),
            status=identity.status,
            verified=identity.verified,
            can_invite=is_origin(identity.user_id) or identity.tier in {1, 2, 1337},
            activity=activity,
            identity_error=warning,
        )
        return self._snapshot

    def clear(self) -> None:
        self._snapshot = None
