from __future__ import annotations

from pathlib import Path

from lmts.tools.web_deploy import web_root_files


INSTALLER = Path('lmts/install/install_server.sh')


def test_web_deploy_starts_at_target_root() -> None:
    files = web_root_files()
    assert 'index.html' in files
    assert 'app.js' in files
    assert 'api/report.php' in files
    assert 'assets/lmts.css' in files
    assert 'config/db.php' in files
    assert all(not path.startswith('public/') for path in files)


def test_apache_serves_lmts_root_and_denies_config() -> None:
    text = INSTALLER.read_text(encoding='utf-8')
    assert 'LMTS_PUBLIC=' not in text
    assert 'Alias /benchmark/ ${LMTS_WEB}/' in text
    assert '<Directory ${LMTS_WEB}>' in text
    assert '<Directory ${LMTS_CONFIG}>' in text
    assert 'Require all denied' in text
    assert 'Web root : ${LMTS_WEB}' in text
