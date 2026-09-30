from __future__ import annotations

import pytest

from lmts.tools.report_profiles import ReportProfile
from lmts.tools.report_publish import _php_headers


def _profile() -> ReportProfile:
    return ReportProfile(
        name='test',
        endpoint='https://aigm.fi/lmts-report/report.php',
    )


def test_machine_key_is_primary_publish_authorization() -> None:
    value = 'pk_1.' + ('a' * 64)
    headers = _php_headers(
        _profile(),
        bearer_token='iam-token',
        machine_key=value,
    )
    assert headers['Authorization'] == f'LMTS-Key {value}'
    assert headers['X-LMTS-Authorization'] == f'LMTS-Key {value}'
    assert 'X-LMTS-Key' not in headers


def test_bearer_is_available_for_provisioning_requests() -> None:
    headers = _php_headers(_profile(), bearer_token='iam-token')
    assert headers['Authorization'] == 'Bearer iam-token'
    assert headers['X-LMTS-Authorization'] == 'Bearer iam-token'
    assert 'X-LMTS-Key' not in headers


def test_http_request_without_auth_is_rejected() -> None:
    with pytest.raises(ValueError, match='authentication'):
        _php_headers(_profile())
