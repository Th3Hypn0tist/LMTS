from __future__ import annotations

from dataclasses import dataclass
from ftplib import FTP, FTP_TLS
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Mapping

from .ftp_profiles import FTPProfile


FilePayload = str | bytes


@dataclass(frozen=True, slots=True)
class DiskOutputTarget:
    root: Path


@dataclass(frozen=True, slots=True)
class FTPOutputTarget:
    profile: FTPProfile


OutputTarget = DiskOutputTarget | FTPOutputTarget


def _safe_relative_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in ('', '.', '..') for part in path.parts):
        raise ValueError(f'invalid output path: {value!r}')
    return path


def _payload_bytes(payload: FilePayload) -> bytes:
    return payload.encode('utf-8') if isinstance(payload, str) else payload


def write_files(target: OutputTarget, files: Mapping[str, FilePayload]) -> list[str]:
    normalized = [(_safe_relative_path(name), _payload_bytes(payload)) for name, payload in files.items()]
    if isinstance(target, DiskOutputTarget):
        return _write_disk(target, normalized)
    if isinstance(target, FTPOutputTarget):
        return _write_ftp(target, normalized)
    raise TypeError(f'unsupported output target: {type(target)!r}')


def _write_disk(target: DiskOutputTarget, files: list[tuple[PurePosixPath, bytes]]) -> list[str]:
    root = target.root.expanduser().resolve()
    written: list[str] = []
    for relative, payload in files:
        path = root.joinpath(*relative.parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        written.append(str(path))
    return written


def _ftp_mkdirs(ftp: FTP, path: PurePosixPath) -> None:
    for part in path.parts:
        if part in ('', '/'):
            continue
        try:
            ftp.cwd(part)
        except Exception:
            ftp.mkd(part)
            ftp.cwd(part)


def _write_ftp(target: FTPOutputTarget, files: list[tuple[PurePosixPath, bytes]]) -> list[str]:
    profile = target.profile
    password = profile.resolve_password()
    written: list[str] = []
    with FTP_TLS() as ftp:
        ftp.connect(profile.host, profile.port, timeout=20)
        ftp.login(profile.username, password)
        ftp.prot_p()
        ftp.set_pasv(True)
        if profile.root:
            ftp.cwd(profile.root)
        base = ftp.pwd()

        for relative, payload in files:
            ftp.cwd(base)
            if len(relative.parts) > 1:
                _ftp_mkdirs(ftp, PurePosixPath(*relative.parts[:-1]))
            filename = relative.parts[-1]
            ftp.storbinary(f'STOR {filename}', BytesIO(payload))
            written.append(str(PurePosixPath(profile.root or '/') / relative))
    return written
