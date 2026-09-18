from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from lmts.core.settings import DVSSettings
from lmts.lib.view import choose_with_preview
from lmts.tools.dvs_service import DVSServiceStatus, dvs_status, restart_dvs, start_dvs, stop_dvs
from lmts.tools.s3d_repo import sync_s3d_repository


def _single_line(host, stdscr, title: str, *, initial: str = '', allow_empty: bool = False) -> str | None:
    while True:
        value = host.input_multiline(stdscr, title, initial=initial)
        if value is None:
            return None
        value = value.strip()
        if '\n' not in value and '\r' not in value and (value or allow_empty):
            return value
        host.message = f"{title}: enter one {'line' if allow_empty else 'non-empty line'}"


def status_lines(settings: DVSSettings, status: DVSServiceStatus) -> tuple[str, ...]:
    s3d = 'ready' if status.s3d_ready else ('configured/not ready' if status.s3d_configured else 'not configured')
    lines = [
        f'Status      : {status.state.upper()}',
        f'Endpoint    : http://{settings.host}:{settings.port}',
        f'PID         : {status.pid if status.pid is not None else "-"}',
        f'Instance    : {status.instance_id or "-"}',
        f'S3D         : {s3d}',
        f'S3D root    : {settings.s3d_root or "-"}',
        f'Studio root : {status.studio_root or settings.studio_root}',
        f'Log         : {status.log_path or ".lmts/dvs-service.log"}',
        '',
        'Report sources: inherited from LMTS Settings',
    ]
    if status.error:
        lines.extend(['', f'Error: {status.error}'])
    return tuple(lines)


def manage_dvs(host, stdscr, current: DVSSettings) -> tuple[DVSSettings, DVSServiceStatus, str]:
    settings = current
    status = dvs_status(settings)
    options = ['Refresh status', 'Start', 'Stop', 'Restart', 'Fetch / Update S3D', 'Edit configuration']

    def preview(_index: int) -> tuple[str, ...]:
        return status_lines(settings, status)

    chosen = choose_with_preview(stdscr, f'DVS [{status.state.upper()}]', options, preview)
    if chosen is None:
        return settings, status, ''

    if chosen == 0:
        status = dvs_status(settings)
        return settings, status, f'DVS status: {status.state}'
    if chosen == 1:
        try:
            status = start_dvs(settings)
            return settings, status, f'DVS started: http://{settings.host}:{settings.port}'
        except RuntimeError as exc:
            return settings, dvs_status(settings), f'DVS start failed: {exc}'
    if chosen == 2:
        try:
            status = stop_dvs(settings)
            return settings, status, 'DVS stopped'
        except RuntimeError as exc:
            return settings, dvs_status(settings), f'DVS stop failed: {exc}'
    if chosen == 3:
        try:
            status = restart_dvs(settings)
            return settings, status, f'DVS restarted: http://{settings.host}:{settings.port}'
        except RuntimeError as exc:
            return settings, dvs_status(settings), f'DVS restart failed: {exc}'
    if chosen == 4:
        if not settings.s3d_root.strip():
            return settings, status, 'S3D root is not configured'
        if status.state in {'running', 'starting'}:
            return settings, status, 'stop DVS before updating S3D'
        target = Path(settings.s3d_root).expanduser().resolve()
        try:
            result = sync_s3d_repository(target)
        except RuntimeError as exc:
            return settings, status, f'S3D fetch failed: {exc}'
        return settings, dvs_status(settings), f'S3D {result}: {target}'

    if status.state in {'running', 'starting'}:
        return settings, status, 'stop DVS before changing its configuration'
    host_value = _single_line(host, stdscr, 'DVS host', initial=settings.host)
    if host_value is None:
        return settings, status, 'DVS configuration unchanged'
    port_value = host.input_integer(stdscr, 'DVS port', default=settings.port, minimum=1, maximum=65535)
    if port_value is None:
        return settings, status, 'DVS configuration unchanged'
    s3d_root = _single_line(host, stdscr, 'S3D root (empty disables S3D)', initial=settings.s3d_root, allow_empty=True)
    if s3d_root is None:
        return settings, status, 'DVS configuration unchanged'
    studio_root = _single_line(host, stdscr, 'DVS Studio root', initial=settings.studio_root)
    if studio_root is None:
        return settings, status, 'DVS configuration unchanged'
    settings = replace(settings, host=host_value, port=port_value, s3d_root=s3d_root, studio_root=studio_root)
    return settings, dvs_status(settings), 'DVS configuration updated'
