from __future__ import annotations

from pathlib import Path

import pytest

from lmts.services import deployment
from lmts.services.deployment import DeploymentPackageBuilder, ServerDeployConfig, deploy_server
from lmts.tools.output import DiskOutputTarget


def _config(**overrides: str) -> ServerDeployConfig:
    values = {
        'host': 'db.example.test',
        'database': 'lmts_server',
        'username': 'lmts_server_user',
        'password': 'server-secret',
        'publish_key': 'publish-secret',
    }
    values.update(overrides)
    return ServerDeployConfig(**values)


def test_server_deploy_config_rejects_empty_values() -> None:
    for field in ('host', 'database', 'username', 'password', 'publish_key'):
        with pytest.raises(ValueError, match=field):
            _config(**{field: ''})


def test_deployment_package_overrides_packaged_db_config(monkeypatch) -> None:
    monkeypatch.setattr(
        deployment,
        'php_package_files',
        lambda: {'visualizer/index.html': 'viewer', 'config.php': 'PACKAGED DEFAULT'},
    )

    files = DeploymentPackageBuilder().build(_config())
    db_php = str(files['config.php'])

    assert files['visualizer/index.html'] == 'viewer'
    assert 'PACKAGED DEFAULT' not in db_php
    assert 'db.example.test' in db_php
    assert 'lmts_server' in db_php
    assert 'lmts_server_user' in db_php
    assert 'server-secret' in db_php
    assert 'publish-secret' in db_php


def test_deploy_server_transfers_complete_package_once(monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple[object, dict[str, object]]] = []
    monkeypatch.setattr(
        deployment,
        'php_package_files',
        lambda: {'visualizer/index.html': 'viewer', 'config.php': 'PACKAGED DEFAULT'},
    )

    def record_write(target, files):
        calls.append((target, dict(files)))
        return sorted(files)

    monkeypatch.setattr(deployment, 'write_files', record_write)
    target = DiskOutputTarget(tmp_path)

    written = deploy_server(target, _config())

    assert len(calls) == 1
    assert calls[0][0] == target
    assert 'visualizer/index.html' in calls[0][1]
    assert 'db.example.test' in str(calls[0][1]['config.php'])
    assert written == ['config.php', 'visualizer/index.html']
