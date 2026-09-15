from __future__ import annotations

from pathlib import Path


INSTALLER = Path('lmts/install/install_server.sh')


def _text() -> str:
    return INSTALLER.read_text(encoding='utf-8')


def test_installer_uses_canonical_schema_file() -> None:
    text = _text()
    assert 'SCHEMA_FILE="${SCRIPT_DIR}/schema_v1.sql"' in text
    assert 'mariadb --protocol=socket "${DB_NAME}" < "${SCHEMA_FILE}"' in text
    assert 'CREATE TABLE IF NOT EXISTS reports' not in text


def test_installer_generates_secrets_instead_of_default_lmts_password() -> None:
    text = _text()
    assert 'openssl rand -hex 24' in text
    assert 'openssl rand -hex 32' in text
    assert "'password' => 'lmts'" not in text
    assert 'DB credentials: lmts:lmts' not in text


def test_installer_runtime_account_is_least_privilege() -> None:
    text = _text()
    assert 'GRANT SELECT, INSERT ON' in text
    assert 'GRANT SELECT, INSERT, UPDATE, DELETE' not in text


def test_installer_writes_generated_settings_for_sudo_user() -> None:
    text = _text()
    assert 'CALLER_USER="${SUDO_USER:-}"' in text
    assert "payload['mysql']" in text
    assert 'chmod 600 "${SETTINGS_FILE}"' in text


def test_installer_does_not_print_generated_secrets() -> None:
    text = _text()
    assert 'Secrets are not printed to stdout.' in text
    assert 'password :' not in text
