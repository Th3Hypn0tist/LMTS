from __future__ import annotations

import hashlib
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from lmts.core.settings import MySQLSettings, load_settings
from lmts.reporting import REPORT_FORMAT, REPORT_VERSION, validate_publishable_report

from .mysql_reports import write_report
from .report_profiles import ReportProfile


DEFAULT_CHUNK_SIZE = 262144


def _read_json_response(request: Request, *, timeout: float) -> tuple[int, dict[str, Any]]:
    try:
        with urlopen(request, timeout=timeout) as response:
            status = int(getattr(response, 'status', response.getcode()))
            raw = response.read().decode('utf-8')
    except HTTPError as exc:
        raw = exc.read().decode('utf-8', errors='replace')
        try:
            payload = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            payload = {}
        detail = payload.get('error') if isinstance(payload, dict) else None
        message = str(detail or raw.strip() or exc.reason or f'HTTP {exc.code}')
        raise RuntimeError(f'LMTS report server HTTP {exc.code}: {message}') from exc
    except URLError as exc:
        raise RuntimeError(f'LMTS report server connection failed: {exc.reason}') from exc

    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as exc:
        raise RuntimeError(f'LMTS report server returned invalid JSON (HTTP {status})') from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f'LMTS report server returned non-object JSON (HTTP {status})')
    return status, payload


def _report_lookup_url(endpoint: str, report_id: str) -> str:
    parts = urlsplit(endpoint)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query['id'] = report_id
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _upload_url(endpoint: str, *, action: str, upload_id: str | None = None, chunk: int | None = None) -> str:
    parts = urlsplit(endpoint)
    path = parts.path
    if '/' in path:
        base = path.rsplit('/', 1)[0]
        upload_path = f'{base}/upload.php'
    else:
        upload_path = 'upload.php'
    query: dict[str, str] = {'action': action}
    if upload_id is not None:
        query['id'] = upload_id
    if chunk is not None:
        query['chunk'] = str(chunk)
    return urlunsplit((parts.scheme, parts.netloc, upload_path, urlencode(query), ''))


def _validate_report_document(report: dict[str, Any]) -> str:
    return validate_publishable_report(report)


def _php_headers(profile: ReportProfile, content_type: str | None = None) -> dict[str, str]:
    headers = {
        'Accept': 'application/json',
        'X-LMTS-Key': profile.publish_key,
    }
    if content_type is not None:
        headers['Content-Type'] = content_type
    return headers


def _abort_upload(profile: ReportProfile, upload_id: str, *, timeout: float) -> None:
    request = Request(
        _upload_url(profile.endpoint, action='abort', upload_id=upload_id),
        data=b'',
        method='POST',
        headers=_php_headers(profile),
    )
    try:
        _read_json_response(request, timeout=timeout)
    except RuntimeError:
        pass


def _publish_php_chunked(
    report: dict[str, Any],
    profile: ReportProfile,
    *,
    timeout: float,
) -> str:
    report_id = _validate_report_document(report)
    body = json.dumps(report, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    size_bytes = len(body)
    if size_bytes <= 0:
        raise ValueError('LMTS report serialization produced an empty document')

    chunk_size = DEFAULT_CHUNK_SIZE
    chunk_count = (size_bytes + chunk_size - 1) // chunk_size
    digest = hashlib.sha256(body).hexdigest()

    init_payload = json.dumps({
        'report_id': report_id,
        'size_bytes': size_bytes,
        'chunk_size': chunk_size,
        'chunk_count': chunk_count,
        'sha256': digest,
    }, ensure_ascii=False, separators=(',', ':')).encode('utf-8')

    init_request = Request(
        _upload_url(profile.endpoint, action='init'),
        data=init_payload,
        method='POST',
        headers=_php_headers(profile, 'application/json; charset=utf-8'),
    )
    status, init_response = _read_json_response(init_request, timeout=timeout)
    if status not in {200, 201} or init_response.get('ok') is not True:
        raise RuntimeError(f'LMTS upload init failed: {init_response!r}')

    upload_id = str(init_response.get('upload_id') or '').strip()
    if not upload_id:
        raise RuntimeError('LMTS upload init returned no upload_id')

    server_chunk_size = init_response.get('chunk_size')
    server_chunk_count = init_response.get('chunk_count')
    if server_chunk_size != chunk_size or server_chunk_count != chunk_count:
        _abort_upload(profile, upload_id, timeout=timeout)
        raise RuntimeError('LMTS upload server returned unexpected chunk geometry')

    try:
        for index in range(chunk_count):
            start = index * chunk_size
            chunk_body = body[start:start + chunk_size]
            request = Request(
                _upload_url(profile.endpoint, action='chunk', upload_id=upload_id, chunk=index),
                data=chunk_body,
                method='PUT',
                headers=_php_headers(profile, 'application/octet-stream'),
            )
            chunk_status, payload = _read_json_response(request, timeout=timeout)
            if chunk_status != 200 or payload.get('ok') is not True:
                raise RuntimeError(f'LMTS upload chunk {index} failed: {payload!r}')
            if int(payload.get('chunk', -1)) != index:
                raise RuntimeError(f'LMTS upload chunk {index} returned wrong chunk index')
            if int(payload.get('received_bytes', -1)) != len(chunk_body):
                raise RuntimeError(f'LMTS upload chunk {index} returned wrong byte count')

        commit_request = Request(
            _upload_url(profile.endpoint, action='commit', upload_id=upload_id),
            data=b'',
            method='POST',
            headers=_php_headers(profile),
        )
        commit_status, payload = _read_json_response(commit_request, timeout=timeout)
        if commit_status not in {200, 201}:
            raise RuntimeError(f'LMTS upload commit returned unexpected HTTP status: {commit_status}')
        if payload.get('ok') is not True or payload.get('projected') is not True:
            raise RuntimeError(f'LMTS upload commit rejected report: {payload!r}')
        returned_id = str(payload.get('id') or '')
        if returned_id != report_id:
            raise RuntimeError(f'LMTS upload commit returned unexpected id: {returned_id!r}')
        return returned_id
    except Exception:
        _abort_upload(profile, upload_id, timeout=timeout)
        raise


def publish_report(
    report: dict[str, Any],
    profile: ReportProfile,
    *,
    timeout: float = 20.0,
    verify: bool = True,
    mysql: MySQLSettings | None = None,
) -> str:
    report_id = _validate_report_document(report)

    if profile.kind == 'mysql':
        returned_id = write_report(mysql or load_settings().mysql, report, verify=verify)
        if returned_id != report_id:
            raise RuntimeError(f'MySQL report target returned unexpected id: {returned_id!r}')
        return returned_id
    if profile.kind != 'php_api':
        raise ValueError(f'unsupported report target kind: {profile.kind}')

    returned_id = _publish_php_chunked(report, profile, timeout=timeout)

    if verify:
        verify_request = Request(
            _report_lookup_url(profile.endpoint, report_id),
            method='GET',
            headers={'Accept': 'application/json'},
        )
        _, stored = _read_json_response(verify_request, timeout=timeout)
        stored_id = _validate_report_document(stored)
        if stored_id != report_id:
            raise RuntimeError(
                f'LMTS report server verification returned unexpected id: {stored_id!r}'
            )

    return returned_id
