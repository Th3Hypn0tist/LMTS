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


def test_privileged_installer_does_not_own_web_location() -> None:
    text = INSTALLER.read_text(encoding='utf-8')
    assert 'LMTS_PUBLIC=' not in text
    assert 'LMTS_WEB=' not in text
    assert 'DocumentRoot' not in text
    assert 'Alias /benchmark/' not in text
    assert 'ServerName aigm.fi' not in text
    assert '/home/www' not in text
    assert 'Deploy the LMTS web package from the TUI to any web-visible directory you choose.' in text
