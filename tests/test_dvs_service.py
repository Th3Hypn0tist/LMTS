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
