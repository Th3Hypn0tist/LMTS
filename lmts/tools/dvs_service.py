from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

from lmts.core.settings import DVSSettings


DEFAULT_STATE_PATH = Path('.lmts/dvs-service.json')
DEFAULT_LOG_PATH = Path('.lmts/dvs-service.log')


@dataclass(frozen=True, slots=True)
class DVSServiceStatus:
    state: str
    host: str
    port: int
    pid: int | None = None
    instance_id: str | None = None
    health_ok: bool = False
    s3d_configured: bool = False
    s3d_ready: bool = False
    studio_root: str = ''
    log_path: str = ''
    error: str = ''

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _health_host(host: str) -> str:
    value = host.strip()
    if value in {'0.0.0.0', '::'}:
        return '127.0.0.1'
    return value


def _health_url(settings: DVSSettings) -> str:
    return f'http://{_health_host(settings.host)}:{settings.port}/api/health'


def _read_state(path: Path) -> dict[str, object] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError, TypeError):
        return None
    return payload if isinstance(payload, dict) else None


def _write_state(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + f'.tmp-{os.getpid()}')
    temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    try:
        temp.replace(path)
    finally:
        if temp.exists():
            temp.unlink()


def _remove_state(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _health(settings: DVSSettings, *, timeout: float = 0.5) -> dict[str, object] | None:
    try:
        with urllib.request.urlopen(_health_url(settings), timeout=timeout) as response:
            payload = json.loads(response.read().decode('utf-8'))
    except (OSError, ValueError, urllib.error.URLError):
        return None
    return payload if isinstance(payload, dict) else None


def _tail(path: Path, *, lines: int = 12) -> str:
    try:
        content = path.read_text(encoding='utf-8', errors='replace').splitlines()
    except OSError:
        return ''
    return '\n'.join(content[-lines:])


def dvs_status(
    settings: DVSSettings,
    *,
    state_path: Path = DEFAULT_STATE_PATH,
    log_path: Path = DEFAULT_LOG_PATH,
) -> DVSServiceStatus:
    state = _read_state(state_path)
    health = _health(settings)
    health_instance = str(health.get('instance_id') or '') if health is not None else ''
    s3d = health.get('s3d') if isinstance(health, dict) and isinstance(health.get('s3d'), dict) else {}
    studio = health.get('studio') if isinstance(health, dict) and isinstance(health.get('studio'), dict) else {}

    if state is None:
        if health is None:
            return DVSServiceStatus('stopped', settings.host, settings.port, log_path=str(log_path))
        return DVSServiceStatus(
            'unmanaged',
            settings.host,
            settings.port,
            instance_id=health_instance or None,
            health_ok=True,
            s3d_configured=bool(s3d.get('configured')),
            s3d_ready=bool(s3d.get('ready')),
            studio_root=str(studio.get('root') or ''),
            log_path=str(log_path),
            error='DVS-compatible service is running but is not owned by this LMTS instance',
        )

    try:
        pid = int(state['pid'])
        instance_id = str(state['instance_id'])
    except (KeyError, TypeError, ValueError):
        return DVSServiceStatus(
            'error', settings.host, settings.port, log_path=str(log_path), error='invalid DVS service state file'
        )

    if not _pid_alive(pid):
        _remove_state(state_path)
        return DVSServiceStatus(
            'error',
            settings.host,
            settings.port,
            pid=pid,
            instance_id=instance_id,
            log_path=str(log_path),
            error='managed DVS process exited',
        )

    if health is None:
        return DVSServiceStatus(
            'starting',
            settings.host,
            settings.port,
            pid=pid,
            instance_id=instance_id,
            log_path=str(log_path),
            error='process is alive but health endpoint is not ready',
        )

    if health_instance != instance_id:
        return DVSServiceStatus(
            'error',
            settings.host,
            settings.port,
            pid=pid,
            instance_id=instance_id,
            health_ok=True,
            s3d_configured=bool(s3d.get('configured')),
            s3d_ready=bool(s3d.get('ready')),
            studio_root=str(studio.get('root') or ''),
            log_path=str(log_path),
            error='health endpoint belongs to a different DVS instance',
        )

    return DVSServiceStatus(
        'running',
        settings.host,
        settings.port,
        pid=pid,
        instance_id=instance_id,
        health_ok=True,
        s3d_configured=bool(s3d.get('configured')),
        s3d_ready=bool(s3d.get('ready')),
        studio_root=str(studio.get('root') or ''),
        log_path=str(log_path),
    )


def start_dvs(
    settings: DVSSettings,
    *,
    state_path: Path = DEFAULT_STATE_PATH,
    log_path: Path = DEFAULT_LOG_PATH,
    timeout: float = 5.0,
) -> DVSServiceStatus:
    current = dvs_status(settings, state_path=state_path, log_path=log_path)
    if current.state in {'running', 'starting'}:
        return current
    if current.state == 'unmanaged':
        raise RuntimeError(current.error)
    if current.state == 'error' and current.pid is not None and _pid_alive(current.pid):
        raise RuntimeError(current.error)

    s3d_root = settings.s3d_root.strip()
    if s3d_root:
        resolved_s3d = Path(s3d_root).expanduser().resolve()
        if not (resolved_s3d / 's3d.js').is_file():
            raise RuntimeError(f'DVS S3D root is invalid or missing s3d.js: {resolved_s3d}')
    else:
        resolved_s3d = None
    studio_root = Path(settings.studio_root).expanduser().resolve()
    studio_root.mkdir(parents=True, exist_ok=True)
    log_path = log_path.expanduser().resolve()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    state_path = state_path.expanduser().resolve()
    state_path.parent.mkdir(parents=True, exist_ok=True)

    instance_id = uuid.uuid4().hex
    env = dict(os.environ)
    env['LMTS_DVS_HOST'] = settings.host
    env['LMTS_DVS_PORT'] = str(settings.port)
    env['LMTS_DVS_STUDIO_ROOT'] = str(studio_root)
    env['LMTS_DVS_INSTANCE_ID'] = instance_id
    if resolved_s3d is None:
        env.pop('LMTS_S3D_ROOT', None)
    else:
        env['LMTS_S3D_ROOT'] = str(resolved_s3d)

    with log_path.open('ab', buffering=0) as log:
        process = subprocess.Popen(
            [sys.executable, '-m', 'lmts.dvs.server'],
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            env=env,
            start_new_session=True,
            close_fds=True,
        )

    _write_state(
        state_path,
        {
            'pid': process.pid,
            'instance_id': instance_id,
            'host': settings.host,
            'port': settings.port,
            'started_at': time.time(),
            'log_path': str(log_path),
        },
    )

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            _remove_state(state_path)
            detail = _tail(log_path)
            raise RuntimeError(f'DVS failed to start{": " + detail if detail else ""}')
        status = dvs_status(settings, state_path=state_path, log_path=log_path)
        if status.state == 'running':
            return status
        time.sleep(0.1)

    status = dvs_status(settings, state_path=state_path, log_path=log_path)
    if status.state == 'running':
        return status
    raise RuntimeError(f'DVS did not become healthy within {timeout:.1f}s: {status.error or status.state}')


def stop_dvs(
    settings: DVSSettings,
    *,
    state_path: Path = DEFAULT_STATE_PATH,
    log_path: Path = DEFAULT_LOG_PATH,
    timeout: float = 5.0,
) -> DVSServiceStatus:
    state = _read_state(state_path)
    if state is None:
        current = dvs_status(settings, state_path=state_path, log_path=log_path)
        if current.state == 'unmanaged':
            raise RuntimeError(current.error)
        return current

    try:
        pid = int(state['pid'])
        instance_id = str(state['instance_id'])
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError('invalid DVS service state file') from exc

    if not _pid_alive(pid):
        _remove_state(state_path)
        return DVSServiceStatus('stopped', settings.host, settings.port, log_path=str(log_path))

    health = _health(settings)
    if health is None or str(health.get('instance_id') or '') != instance_id:
        raise RuntimeError('refusing to stop DVS because managed instance ownership cannot be verified')

    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _pid_alive(pid):
            _remove_state(state_path)
            return DVSServiceStatus('stopped', settings.host, settings.port, log_path=str(log_path))
        time.sleep(0.1)
    raise RuntimeError('DVS did not stop after SIGTERM')


def restart_dvs(
    settings: DVSSettings,
    *,
    state_path: Path = DEFAULT_STATE_PATH,
    log_path: Path = DEFAULT_LOG_PATH,
) -> DVSServiceStatus:
    stop_dvs(settings, state_path=state_path, log_path=log_path)
    return start_dvs(settings, state_path=state_path, log_path=log_path)
