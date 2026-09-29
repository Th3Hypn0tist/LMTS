from __future__ import annotations

import json
from pathlib import Path

import pytest

from lmts.services.publish_auth import (
    MachinePublishCredential,
    MachinePublishCredentialStore,
    PublishAuthenticationError,
    _report_machine_identity,
    ensure_machine_credential,
)


def _report(user_id: str = 'usr_1', system_id: str = 'sys_1') -> dict[str, object]:
    context = {
        'fingerprint': 'abc123',
        'schema_version': 1,
        'profile': {'cpu': {'architecture': 'x86_64'}},
    }
    return {
        'records': [{
            'provenance': {
                'tester_user_id': user_id,
                'system_id': system_id,
            },
            'evidence': {'system_context': context},
        }],
    }


def test_machine_credential_store_is_private(tmp_path: Path) -> None:
    path = tmp_path / 'publish-auth.json'
    store = MachinePublishCredentialStore(path)
    credential = MachinePublishCredential(
        'https://aigm.fi/lmts-report/report.php',
        'sys_1',
        'pk_1',
        'a' * 64,
    )
    store.save(credential)

    assert store.load(endpoint=credential.endpoint, system_id='sys_1') == credential
    assert path.stat().st_mode & 0o777 == 0o600
    raw = json.loads(path.read_text(encoding='utf-8'))
    assert raw['publish_key_id'] == 'pk_1'
    assert raw['publish_secret'] == 'a' * 64


def test_same_user_can_have_independent_credentials_on_three_machines(tmp_path: Path) -> None:
    endpoint = 'https://aigm.fi/lmts-report/report.php'
    for index in range(3):
        store = MachinePublishCredentialStore(tmp_path / f'machine-{index}' / 'publish-auth.json')
        credential = MachinePublishCredential(
            endpoint,
            f'sys_{index}',
            f'pk_{index}',
            f'{index + 1:064x}',
        )
        store.save(credential)
        assert store.load(endpoint=endpoint, system_id=f'sys_{index}') == credential


def test_report_machine_identity_rejects_cross_machine_report() -> None:
    report = _report()
    report['records'].append({
        'provenance': {'tester_user_id': 'usr_1', 'system_id': 'sys_2'},
        'evidence': {'system_context': {
            'fingerprint': 'def456',
            'schema_version': 1,
            'profile': {'cpu': {'architecture': 'x86_64'}},
        }},
    })

    with pytest.raises(PublishAuthenticationError, match='mixes multiple'):
        _report_machine_identity(report)


def test_ensure_machine_credential_uses_existing_key_without_provisioning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    endpoint = 'https://aigm.fi/lmts-report/report.php'
    store = MachinePublishCredentialStore(tmp_path / 'publish-auth.json')
    credential = MachinePublishCredential(endpoint, 'sys_1', 'pk_existing', 'b' * 64)
    store.save(credential)

    def fail_provision(*args, **kwargs):
        raise AssertionError('provisioning should not run')

    monkeypatch.setattr('lmts.services.publish_auth.provision_machine_credential', fail_provision)

    result = ensure_machine_credential(
        _report(),
        endpoint,
        bearer_token='opaque-iam-token',
        store=store,
    )
    assert result == credential


def test_store_does_not_reuse_credential_for_another_system(tmp_path: Path) -> None:
    endpoint = 'https://aigm.fi/lmts-report/report.php'
    store = MachinePublishCredentialStore(tmp_path / 'publish-auth.json')
    store.save(MachinePublishCredential(endpoint, 'sys_a', 'pk_a', 'c' * 64))

    assert store.load(endpoint=endpoint, system_id='sys_b') is None
