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

from lmts.core.paths import DVS_SERVICE_LOG_PATH, DVS_SERVICE_STATE_PATH
from lmts.core.settings import DVSSettings


DEFAULT_STATE_PATH = DVS_SERVICE_STATE_PATH
DEFAULT_LOG_PATH = DVS_SERVICE_LOG_PATH
STARTUP_GRACE_SECONDS = 5.0
DVS_SOURCE_ROOT = Path(__file__).resolve().parents[2]
REQUIRED_DVS_API_FEATURES = {
    'report_sources',
    'report_source_statuses',
    'report_source_reports',
    'report_source_report',
    'report_source_dataset',
}


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

    stat_path = Path(f'/proc/{pid}/stat')
    try:
        stat = stat_path.read_text(encoding='utf-8', errors='replace')
    except (FileNotFoundError, PermissionError, OSError):
        stat = ''
    if stat:
        # /proc/<pid>/stat field 3 is the process state. Zombies still answer
        # kill(pid, 0), but they cannot serve DVS and must not count as alive.
        close = stat.rfind(')')
        if close >= 0:
            fields = stat[close + 1:].strip().split()
            if fields and fields[0] == 'Z':
                return False

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _process_bind(pid: int) -> tuple[str, int] | None:
    environ = Path(f'/proc/{pid}/environ')
    try:
        raw = environ.read_bytes()
    except (FileNotFoundError, PermissionError, OSError):
        return None
    values: dict[str, str] = {}
    for entry in raw.split(b'\0'):
        if b'=' not in entry:
            continue
        key, value = entry.split(b'=', 1)
        if key in {b'LMTS_DVS_HOST', b'LMTS_DVS_PORT'}:
            values[key.decode('ascii')] = value.decode('utf-8', errors='replace')
    host = values.get('LMTS_DVS_HOST')
    port_text = values.get('LMTS_DVS_PORT')
    if not host or not port_text:
        return None
    try:
        port = int(port_text)
    except ValueError:
        return None
    return host, port


def _process_instance_id(pid: int) -> str | None:
    """Return the managed DVS instance id carried by a live Linux process.

    None means ownership could not be established. An empty string means the
    process environment was readable but it is not an LMTS-managed DVS process.
    """
    environ = Path(f'/proc/{pid}/environ')
    try:
        raw = environ.read_bytes()
    except (FileNotFoundError, PermissionError, OSError):
        return None
    prefix = b'LMTS_DVS_INSTANCE_ID='
    for entry in raw.split(b'\0'):
        if entry.startswith(prefix):
            return entry[len(prefix):].decode('utf-8', errors='replace')
    return ''


def _health(settings: DVSSettings, *, timeout: float = 0.5) -> dict[str, object] | None:
    try:
        with urllib.request.urlopen(_health_url(settings), timeout=timeout) as response:
            payload = json.loads(response.read().decode('utf-8'))
    except (OSError, ValueError, urllib.error.URLError):
        return None
    return payload if isinstance(payload, dict) else None


def _health_runtime_mismatch(health: dict[str, object]) -> str:
    runtime = health.get('runtime')
    if not isinstance(runtime, dict):
        return 'DVS health has no runtime identity; restart from the current LMTS source'

    actual_root = str(runtime.get('source_root') or '').strip()
    expected_root = str(DVS_SOURCE_ROOT)
    if actual_root != expected_root:
        return f'DVS source mismatch: expected {expected_root}, running {actual_root or "<unknown>"}'

    features = health.get('api_features')
    if not isinstance(features, list):
        return 'DVS health has no API capability list; backend is stale'
    available = {str(value) for value in features}
    missing = sorted(REQUIRED_DVS_API_FEATURES - available)
    if missing:
        return f'DVS backend is missing required API capabilities: {", ".join(missing)}'
    return ''


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
            'error',
            settings.host,
            settings.port,
            log_path=str(log_path),
            error='invalid DVS service state file',
        )

    if not _pid_alive(pid):
        _remove_state(state_path)
        return DVSServiceStatus('stopped', settings.host, settings.port, log_path=str(log_path))

    process_instance = _process_instance_id(pid)
    if process_instance is not None and process_instance != instance_id:
        _remove_state(state_path)
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
            error='stale DVS state removed; endpoint belongs to another process',
        )

    process_bind = _process_bind(pid)
    if process_bind is not None and process_bind != (settings.host, settings.port):
        running_host, running_port = process_bind
        return DVSServiceStatus(
            'error',
            settings.host,
            settings.port,
            pid=pid,
            instance_id=instance_id,
            health_ok=health is not None,
            s3d_configured=bool(s3d.get('configured')),
            s3d_ready=bool(s3d.get('ready')),
            studio_root=str(studio.get('root') or ''),
            log_path=str(log_path),
            error=(
                'configured bind differs from running process: '
                f'configured {settings.host}:{settings.port}, '
                f'running {running_host}:{running_port}; restart DVS'
            ),
        )

    if health is None:
        started_at = state.get('started_at')
        age = None
        if isinstance(started_at, (int, float)) and not isinstance(started_at, bool):
            age = max(0.0, time.time() - float(started_at))
        if age is not None and age > STARTUP_GRACE_SECONDS:
            detail = _tail(log_path)
            message = (
                'process is alive but health endpoint did not become ready '
                f'within {STARTUP_GRACE_SECONDS:.1f}s'
            )
            if detail:
                message += f'\nLast DVS log lines:\n{detail}'
            return DVSServiceStatus(
                'error',
                settings.host,
                settings.port,
                pid=pid,
                instance_id=instance_id,
                log_path=str(log_path),
                error=message,
            )
        return DVSServiceStatus(
            'starting',
            settings.host,
            settings.port,
            pid=pid,
            instance_id=instance_id,
            log_path=str(log_path),
            error='process is alive but health endpoint is not ready',
        )

    runtime_mismatch = _health_runtime_mismatch(health)
    if runtime_mismatch:
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
            error=runtime_mismatch,
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
    if current.state == 'running':
        return current
    if current.state == 'starting':
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            time.sleep(0.1)
            current = dvs_status(settings, state_path=state_path, log_path=log_path)
            if current.state == 'running':
                return current
            if current.state != 'starting':
                break
        detail = current.error or _tail(log_path) or current.state
        raise RuntimeError(f'DVS did not become healthy: {detail}')
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
    env['LMTS_DVS_SOURCE_ROOT'] = str(DVS_SOURCE_ROOT)
    existing_pythonpath = env.get('PYTHONPATH', '').strip()
    env['PYTHONPATH'] = (
        str(DVS_SOURCE_ROOT)
        if not existing_pythonpath
        else str(DVS_SOURCE_ROOT) + os.pathsep + existing_pythonpath
    )
    if resolved_s3d is None:
        env.pop('LMTS_S3D_ROOT', None)
    else:
        env['LMTS_S3D_ROOT'] = str(resolved_s3d)

    with log_path.open('ab', buffering=0) as log:
        process = subprocess.Popen(
            [sys.executable, '-m', 'lmts.dvs.server'],
            cwd=str(DVS_SOURCE_ROOT),
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

    # This process was created by this start call and never became healthy.
    # Do not leave a broken "starting" process and state file behind.
    if process.poll() is None:
        try:
            process.terminate()
            process.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=1.0)
    _remove_state(state_path)
    detail = status.error or _tail(log_path) or status.state
    raise RuntimeError(f'DVS did not become healthy within {timeout:.1f}s: {detail}')


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
    if health is not None:
        if str(health.get('instance_id') or '') != instance_id:
            raise RuntimeError('refusing to stop DVS because health endpoint belongs to a different instance')
    else:
        process_instance = _process_instance_id(pid)
        if process_instance is not None and process_instance != instance_id:
            _remove_state(state_path)
            return DVSServiceStatus('stopped', settings.host, settings.port, log_path=str(log_path))
        if process_instance is None:
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
