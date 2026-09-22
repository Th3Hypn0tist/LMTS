from __future__ import annotations

from pathlib import Path

from lmts.tools.web_deploy import PHP_PACKAGE_ROOT, php_package_files


INSTALLER = Path('lmts/install/install_server.sh')


def test_php_package_has_two_application_subdirectories() -> None:
    directories = sorted(path.name for path in PHP_PACKAGE_ROOT.iterdir() if path.is_dir())
    assert directories == ['storage', 'visualizer']


def test_php_package_is_directly_copyable() -> None:
    files = php_package_files()
    assert 'README.md' in files
    assert 'config.example.php' in files
    assert 'visualizer/index.html' in files
    assert 'visualizer/app.js' in files
    assert 'visualizer/api/stats.php' in files
    assert 'visualizer/api/report.php' in files
    assert 'storage/report.php' in files
    assert 'storage/lib/report_contract.php' in files


def test_privileged_installer_does_not_own_web_location() -> None:
    text = INSTALLER.read_text(encoding='utf-8')
    assert 'LMTS_PUBLIC=' not in text
    assert 'LMTS_WEB=' not in text
    assert 'DocumentRoot' not in text
    assert 'Alias /benchmark/' not in text
    assert 'ServerName aigm.fi' not in text
    assert '/home/www' not in text
