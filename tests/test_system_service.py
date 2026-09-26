from __future__ import annotations

from types import SimpleNamespace

import pytest

from lmts.repositories.system import system_id_for
from lmts.services.system import SystemService


class ProfileService:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def context(self) -> dict[str, object]:
        return dict(self.payload)


def test_run_provenance_does_not_require_local_database() -> None:
    profile = ProfileService({
        'fingerprint': 'machine-fingerprint',
        'schema_version': 6,
    })
    service = SystemService(None, profile)

    provenance = service.build_run_provenance('0')

    assert provenance.tester_user_id == '0'
    assert provenance.system_id == system_id_for('0', 'machine-fingerprint')
    assert provenance.compute_profile_id is None


def test_local_persistence_still_requires_repository() -> None:
    profile = ProfileService({
        'fingerprint': 'machine-fingerprint',
        'schema_version': 6,
    })
    service = SystemService(None, profile)

    with pytest.raises(RuntimeError, match='local system persistence is not configured'):
        service.ensure_current('0')
