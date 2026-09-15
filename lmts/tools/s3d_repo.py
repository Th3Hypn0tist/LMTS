from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


S3D_REPOSITORY_URL = 'https://github.com/Th3Hypn0tist/S3D.git'
S3D_BRANCH = 'main'


def _run_git(args: list[str], *, cwd: Path | None = None) -> str:
    git = shutil.which('git')
    if git is None:
        raise RuntimeError('git is required to fetch S3D')
    completed = subprocess.run(
        [git, *args],
        cwd=None if cwd is None else str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or f'exit code {completed.returncode}'
        raise RuntimeError(detail.splitlines()[-1])
    return completed.stdout.strip()


def _normalise_remote(value: str) -> str:
    remote = value.strip().removesuffix('/')
    if remote.endswith('.git'):
        remote = remote[:-4]
    if remote.startswith('git@github.com:'):
        remote = 'https://github.com/' + remote.removeprefix('git@github.com:')
    return remote


def sync_s3d_repository(target: Path) -> str:
    target = target.expanduser().resolve()
    entrypoint = target / 's3d.js'

    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        _run_git(['clone', '--branch', S3D_BRANCH, '--single-branch', S3D_REPOSITORY_URL, str(target)])
        if not entrypoint.is_file():
            raise RuntimeError(f'cloned S3D repository is missing s3d.js: {target}')
        return 'cloned'

    if not target.is_dir():
        raise RuntimeError(f'S3D root exists but is not a directory: {target}')
    if not (target / '.git').is_dir():
        raise RuntimeError(f'S3D root exists but is not a git repository: {target}')

    remote = _run_git(['remote', 'get-url', 'origin'], cwd=target)
    if _normalise_remote(remote) != _normalise_remote(S3D_REPOSITORY_URL):
        raise RuntimeError(f'S3D root origin is not canonical S3D repository: {remote}')

    dirty = _run_git(['status', '--porcelain'], cwd=target)
    if dirty:
        raise RuntimeError(f'S3D repository has local changes: {target}')

    _run_git(['fetch', 'origin', S3D_BRANCH], cwd=target)
    _run_git(['merge', '--ff-only', f'origin/{S3D_BRANCH}'], cwd=target)

    if not entrypoint.is_file():
        raise RuntimeError(f'S3D repository is missing s3d.js after update: {target}')
    return 'updated'
