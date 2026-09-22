from __future__ import annotations

from types import SimpleNamespace

from lmts.services.user import UserDashboardSnapshot
from lmts.view.user_page import UserPage


def test_user_page_projects_canonical_identity_and_activity() -> None:
    snapshot = UserDashboardSnapshot(
        user_id='0',
        username='origin',
        tier=1337,
        tier_label='Test-content authority',
        status='active',
        verified=True,
        can_invite=True,
        activity={
            'reports': 7,
            'submissions': 2,
            'result_records': 7,
            'test_definitions': 4,
            'test_versions': 4,
            'telemetry_values': 11,
            'models': 2,
            'compositions': 0,
            'systems': 1,
            'compute_profiles': 0,
            'hardware_nodes': 3,
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

    assert '  Username   : origin' in lines
    assert '  User ID    : 0' in lines
    assert '  Tier       : 1337 Test-content authority' in lines
    assert '  Reports            : 7' in lines
    assert '  PASS               : 5' in lines
    assert '  ERROR              : 1' in lines
