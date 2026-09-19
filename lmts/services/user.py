from __future__ import annotations

from dataclasses import dataclass

from .auth import AuthService, AuthenticationError
from .results import ResultService


@dataclass(frozen=True, slots=True)
class UserDashboardSnapshot:
    username: str | None
    tier: str | None
    activity: dict[str, int]
    identity_error: str | None = None


class UserService:
    """User-domain boundary for TUI and later account-backed surfaces."""

    def __init__(self, result_service: ResultService, auth_service: AuthService | None = None) -> None:
        self.result_service = result_service
        self.auth_service = auth_service

    def dashboard_snapshot(self) -> UserDashboardSnapshot:
        identity = None
        identity_error = None
        if self.auth_service is not None:
            try:
                identity = self.auth_service.current_identity()
            except (AuthenticationError, RuntimeError, ValueError) as exc:
                identity_error = str(exc)
        return UserDashboardSnapshot(
            username=None if identity is None else identity.username,
            tier=None if identity is None else str(identity.tier),
            activity=self.result_service.activity_summary(),
            identity_error=identity_error,
        )
