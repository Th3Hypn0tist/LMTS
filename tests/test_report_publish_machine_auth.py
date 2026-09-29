from __future__ import annotations

import pytest

from lmts.tools.report_profiles import ReportProfile
from lmts.tools.report_publish import _php_headers


def _profile(publish_key: str = 'legacy') -> ReportProfile:
    return ReportProfile(
        name='test',
        endpoint='https://aigm.fi/lmts-report/report.php',
        publish_key=publish_key,
    )


def test_machine_key_is_primary_publish_authorization() -> None:
    headers = _php_headers(
        _profile(),
        bearer_token='iam-token',
        machine_key='pk_1.' + ('a' * 64),
    )
    assert headers['Authorization'] == 'LMTS-Key pk_1.' + ('a' * 64)
    assert 'X-LMTS-Key' not in headers


def test_bearer_remains_migration_fallback() -> None:
    headers = _php_headers(_profile(), bearer_token='iam-token')
    assert headers['Authorization'] == 'Bearer iam-token'
    assert 'X-LMTS-Key' not in headers


def test_shared_key_remains_last_migration_fallback() -> None:
    headers = _php_headers(_profile('legacy'))
    assert headers['X-LMTS-Key'] == 'legacy'
    assert 'Authorization' not in headers


def test_public_profile_without_any_auth_is_rejected() -> None:
    with pytest.raises(ValueError, match='authentication'):
        _php_headers(_profile(''))
