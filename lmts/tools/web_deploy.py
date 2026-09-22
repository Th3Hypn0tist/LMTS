from __future__ import annotations

from pathlib import Path

from .output import FilePayload, OutputTarget, write_files


PHP_PACKAGE_ROOT = Path(__file__).resolve().parents[2] / 'php'


def php_package_files() -> dict[str, FilePayload]:
    """Return the standalone PHP package as deployable files."""
    if not PHP_PACKAGE_ROOT.is_dir():
        raise RuntimeError(f'LMTS PHP package is missing: {PHP_PACKAGE_ROOT}')
    files: dict[str, FilePayload] = {}
    for path in sorted(PHP_PACKAGE_ROOT.rglob('*')):
        if not path.is_file() or path.name == 'config.php':
            continue
        files[path.relative_to(PHP_PACKAGE_ROOT).as_posix()] = path.read_bytes()
    return files


def deploy_php_package(target: OutputTarget) -> list[str]:
    return write_files(target, php_package_files())
