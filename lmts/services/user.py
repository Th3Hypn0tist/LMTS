from __future__ import annotations

from dataclasses import dataclass

from .results import ResultService


@dataclass(frozen=True, slots=True)
class UserDashboardSnapshot:
    username: str | None
    tier: str | None
    activity: dict[str, int]


class UserService:
    """User-domain boundary for TUI and later database-backed account state."""

    def __init__(self, result_service: ResultService) -> None:
        self.result_service = result_service

    def dashboard_snapshot(self) -> UserDashboardSnapshot:
        return UserDashboardSnapshot(
            username=None,
            tier=None,
            activity=self.result_service.activity_summary(),
        )
