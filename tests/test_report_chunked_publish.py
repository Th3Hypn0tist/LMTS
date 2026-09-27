from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

from lmts.reporting import REPORT_FORMAT, REPORT_VERSION
from lmts.tools import report_publish
from lmts.tools.report_profiles import ReportProfile


def _report(payload_size: int = 600000) -> dict:
    return {
        'format': REPORT_FORMAT,
        'version': REPORT_VERSION,
        'report': {
            'id': 'report-chunked-1',
            'type': 'benchmark',
            'title': 'Chunked report',
            'created_at': '2026-09-27T06:00:00+00:00',
        },
        'source': {'type': 'lmts.test', 'id': 'source-1'},
        'padding': 'x' * payload_size,
    }


def test_php_publish_uses_binary_chunks_and_commit(monkeypatch) -> None:
    seen = []

    def fake_read(request, *, timeout):
        seen.append(request)
        parts = urlsplit(request.full_url)
        query = parse_qs(parts.query)
        action = query.get('action', [''])[0]

        if action == 'init':
            return 201, {
                'ok': True,
                'upload_id': 'a' * 48,
                'chunk_size': report_publish.DEFAULT_CHUNK_SIZE,
                'chunk_count': 3,
            }
        if action == 'chunk':
            index = int(query['chunk'][0])
            return 200, {
                'ok': True,
                'upload_id': 'a' * 48,
                'chunk': index,
                'received_bytes': len(request.data or b''),
            }
        if action == 'commit':
            return 201, {
                'ok': True,
                'id': 'report-chunked-1',
                'version': REPORT_VERSION,
                'created': True,
                'projected': True,
            }
        raise AssertionError(request.full_url)

    monkeypatch.setattr(report_publish, '_read_json_response', fake_read)

    profile = ReportProfile(
        name='public',
        kind='php_api',
        endpoint='https://aigm.fi/lmts-report/report.php',
        publish_key='secret',
    )
    returned = report_publish.publish_report(_report(), profile, verify=False)

    assert returned == 'report-chunked-1'
    assert len(seen) == 5

    init = seen[0]
    assert init.method == 'POST'
    assert urlsplit(init.full_url).path == '/lmts-report/upload.php'
    assert parse_qs(urlsplit(init.full_url).query)['action'] == ['init']
    assert init.headers['Content-type'] == 'application/json; charset=utf-8'

    chunks = seen[1:4]
    assert [request.method for request in chunks] == ['PUT', 'PUT', 'PUT']
    assert all(urlsplit(request.full_url).path == '/lmts-report/upload.php' for request in chunks)
    assert all(request.headers['Content-type'] == 'application/octet-stream' for request in chunks)
    assert [int(parse_qs(urlsplit(request.full_url).query)['chunk'][0]) for request in chunks] == [0, 1, 2]
    assert all(len(request.data or b'') <= report_publish.DEFAULT_CHUNK_SIZE for request in chunks)

    commit = seen[4]
    assert commit.method == 'POST'
    assert parse_qs(urlsplit(commit.full_url).query)['action'] == ['commit']
    assert parse_qs(urlsplit(commit.full_url).query)['id'] == ['a' * 48]


def test_php_publish_aborts_after_chunk_failure(monkeypatch) -> None:
    actions = []

    def fake_read(request, *, timeout):
        query = parse_qs(urlsplit(request.full_url).query)
        action = query.get('action', [''])[0]
        actions.append(action)

        if action == 'init':
            return 201, {
                'ok': True,
                'upload_id': 'b' * 48,
                'chunk_size': report_publish.DEFAULT_CHUNK_SIZE,
                'chunk_count': 1,
            }
        if action == 'chunk':
            raise RuntimeError('chunk failed')
        if action == 'abort':
            return 200, {'ok': True, 'upload_id': 'b' * 48}
        raise AssertionError(request.full_url)

    monkeypatch.setattr(report_publish, '_read_json_response', fake_read)

    profile = ReportProfile(
        name='public',
        kind='php_api',
        endpoint='https://aigm.fi/lmts-report/report.php',
        publish_key='secret',
    )

    try:
        report_publish.publish_report(_report(payload_size=1000), profile, verify=False)
    except RuntimeError as exc:
        assert 'chunk failed' in str(exc)
    else:
        raise AssertionError('expected chunk failure')

    assert actions == ['init', 'chunk', 'abort']
