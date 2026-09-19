from __future__ import annotations

from types import SimpleNamespace

from lmts.services.user import UserDashboardSnapshot
from lmts.view.user_page import UserPage


def test_user_page_projects_activity_without_inventing_account_state() -> None:
    snapshot = UserDashboardSnapshot(
        username=None,
        tier=None,
        activity={
            'runs': 7,
            'matrices': 2,
            'targets': 3,
            'tests': 4,
            'models': 2,
            'bots': 1,
            'compositions': 0,
            'pass': 5,
            'fail': 1,
            'error': 1,
            'cancelled': 0,
            'unknown': 0,
        },
    )
    service = SimpleNamespace(dashboard_snapshot=lambda: snapshot)
    controller = SimpleNamespace(user_service=service)

    lines = UserPage(controller).lines()

    assert '  Username : not connected' in lines
    assert '  Tier     : -' in lines
    assert '  Test runs    : 7' in lines
    assert '  PASS      : 5' in lines
    assert '  ERROR     : 1' in lines
