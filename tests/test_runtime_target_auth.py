from __future__ import annotations

import json
from pathlib import Path

from lmts.core.models import ModelCapabilities
from lmts.core.runtime_targets import (
    RuntimeTargetDefinition,
    load_runtime_secrets,
    load_runtime_targets,
    save_runtime_secrets,
    save_runtime_targets,
)


def test_runtime_key_is_stored_separately_from_target_definition(tmp_path: Path) -> None:
    targets_path = tmp_path / 'runtime-targets.json'
    secrets_path = tmp_path / 'runtime-secrets.json'
    definition = RuntimeTargetDefinition(
        id='bot-a',
        kind='bot',
        transport='http',
        endpoint='https://example.invalid/lmts',
        auth_header='Authorization',
        auth_prefix='Bearer ',
        capabilities=ModelCapabilities(text=True),
    )

    save_runtime_targets((definition,), targets_path)
    save_runtime_secrets({'bot-a': 'super-secret-key'}, secrets_path)

    raw_targets = targets_path.read_text(encoding='utf-8')
    assert 'super-secret-key' not in raw_targets
    assert json.loads(raw_targets)['targets'][0]['auth_header'] == 'Authorization'
    assert load_runtime_targets(targets_path)[0].auth_prefix == 'Bearer '
    assert load_runtime_secrets(secrets_path) == {'bot-a': 'super-secret-key'}


def test_runtime_secret_store_is_private(tmp_path: Path) -> None:
    secrets_path = tmp_path / 'runtime-secrets.json'
    save_runtime_secrets({'bot-a': 'secret'}, secrets_path)
    assert secrets_path.stat().st_mode & 0o777 == 0o600
