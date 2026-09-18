from __future__ import annotations

import json
from pathlib import Path

import pytest

from lmts.core.settings import DVSSettings
from lmts.tools import dvs_service


def test_status_reports_stopped_without_state_or_health(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(dvs_service, '_health', lambda settings: None)
    status = dvs_service.dvs_status(
        DVSSettings(),
        state_path=tmp_path / 'state.json',
        log_path=tmp_path / 'dvs.log',
    )
    assert status.state == 'stopped'
    assert status.health_ok is False


def test_status_reports_unmanaged_health_without_state(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        dvs_service,
        '_health',
        lambda settings: {
            'instance_id': 'foreign',
            's3d': {'configured': True, 'ready': True},
            'studio': {'root': '/tmp/studio'},
        },
    )
    status = dvs_service.dvs_status(
        DVSSettings(),
        state_path=tmp_path / 'state.json',
        log_path=tmp_path / 'dvs.log',
    )
    assert status.state == 'unmanaged'
    assert status.instance_id == 'foreign'
    assert status.s3d_ready is True


def test_status_requires_matching_instance_identity(monkeypatch, tmp_path: Path) -> None:
    state_path = tmp_path / 'state.json'
    state_path.write_text(json.dumps({'pid': 123, 'instance_id': 'owned'}), encoding='utf-8')
    monkeypatch.setattr(dvs_service, '_pid_alive', lambda pid: True)
    monkeypatch.setattr(
        dvs_service,
        '_health',
        lambda settings: {
            'instance_id': 'different',
            's3d': {'configured': True, 'ready': True},
            'studio': {'root': '/tmp/studio'},
        },
    )
    status = dvs_service.dvs_status(
        DVSSettings(),
        state_path=state_path,
        log_path=tmp_path / 'dvs.log',
    )
    assert status.state == 'error'
    assert 'different DVS instance' in status.error


def test_stop_refuses_when_health_ownership_cannot_be_verified(monkeypatch, tmp_path: Path) -> None:
    state_path = tmp_path / 'state.json'
    state_path.write_text(json.dumps({'pid': 123, 'instance_id': 'owned'}), encoding='utf-8')
    monkeypatch.setattr(dvs_service, '_pid_alive', lambda pid: True)
    monkeypatch.setattr(dvs_service, '_health', lambda settings: None)
    with pytest.raises(RuntimeError, match='ownership cannot be verified'):
        dvs_service.stop_dvs(
            DVSSettings(),
            state_path=state_path,
            log_path=tmp_path / 'dvs.log',
        )


def test_start_rejects_invalid_s3d_root(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(dvs_service, '_health', lambda settings: None)
    settings = DVSSettings(s3d_root=str(tmp_path / 'missing'))
    with pytest.raises(RuntimeError, match='missing s3d.js'):
        dvs_service.start_dvs(
            settings,
            state_path=tmp_path / 'state.json',
            log_path=tmp_path / 'dvs.log',
        )


def test_status_marks_old_starting_process_as_error(monkeypatch, tmp_path: Path) -> None:
    state_path = tmp_path / 'state.json'
    state_path.write_text(
        json.dumps({
            'pid': 123,
            'instance_id': 'owned',
            'started_at': 0.0,
        }),
        encoding='utf-8',
    )
    log_path = tmp_path / 'dvs.log'
    log_path.write_text('boot failed detail\n', encoding='utf-8')
    monkeypatch.setattr(dvs_service, '_pid_alive', lambda pid: True)
    monkeypatch.setattr(dvs_service, '_process_instance_id', lambda pid: 'owned')
    monkeypatch.setattr(dvs_service, '_health', lambda settings: None)

    status = dvs_service.dvs_status(
        DVSSettings(),
        state_path=state_path,
        log_path=log_path,
    )
    assert status.state == 'error'
    assert 'health endpoint did not become ready' in status.error
    assert 'boot failed detail' in status.error


def test_pid_alive_rejects_linux_zombie(monkeypatch) -> None:
    class FakeStatPath:
        def read_text(self, **kwargs):
            return '123 (python) Z 1 2 3'

    monkeypatch.setattr(dvs_service, 'Path', lambda value: FakeStatPath())
    assert dvs_service._pid_alive(123) is False


def test_dvs_defaults_bind_all_interfaces_but_health_checks_loopback() -> None:
    settings = DVSSettings()
    assert settings.host == '0.0.0.0'
    assert dvs_service._health_url(settings) == 'http://127.0.0.1:8775/api/health'


def test_status_detects_running_bind_drift(monkeypatch, tmp_path: Path) -> None:
    state_path = tmp_path / 'state.json'
    state_path.write_text(
        json.dumps({'pid': 123, 'instance_id': 'owned', 'started_at': 0.0}),
        encoding='utf-8',
    )
    monkeypatch.setattr(dvs_service, '_pid_alive', lambda pid: True)
    monkeypatch.setattr(dvs_service, '_process_instance_id', lambda pid: 'owned')
    monkeypatch.setattr(dvs_service, '_process_bind', lambda pid: ('127.0.0.1', 8775))
    monkeypatch.setattr(
        dvs_service,
        '_health',
        lambda settings: {
            'instance_id': 'owned',
            's3d': {'configured': True, 'ready': True},
            'studio': {'root': '/tmp/studio'},
        },
    )

    status = dvs_service.dvs_status(
        DVSSettings(host='0.0.0.0', port=8775),
        state_path=state_path,
        log_path=tmp_path / 'dvs.log',
    )
    assert status.state == 'error'
    assert 'configured 0.0.0.0:8775' in status.error
    assert 'running 127.0.0.1:8775' in status.error
    assert 'restart DVS' in status.error


def test_health_contract_rejects_backend_without_report_source_api(monkeypatch) -> None:
    monkeypatch.setattr(dvs_service, 'DVS_SOURCE_ROOT', Path('/srv/lmts'))
    health = {
        'runtime': {'source_root': '/srv/lmts'},
        'api_features': ['database_source_statuses'],
    }
    message = dvs_service._health_runtime_mismatch(health)
    assert 'report_source_statuses' in message
    assert 'report_source_reports' in message
