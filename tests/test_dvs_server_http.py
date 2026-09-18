from __future__ import annotations

import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

import lmts.dvs.server as server_module
from lmts.dvs.registry import DVSRegistry
from lmts.dvs.studio import DVSStudioStore


def _template(item_id: str, *, column: str = 'value') -> dict:
    return {
        'format': 's3d.dvs.input-template',
        'version': '1.0',
        'id': item_id,
        'source_format': 'example/1.0',
        'reader': 'json',
        'rows': 'records[*]',
        'columns': [{'name': column, 'selector': column, 'type': 'number', 'nullable': True}],
    }


def _preset(item_id: str, template_id: str, *, column: str = 'value') -> dict:
    return {
        'format': 's3d.dvs.visualization-preset',
        'version': '1.0',
        'id': item_id,
        'source_format': 'example/1.0',
        'input_template_ref': template_id,
        'generations': [{
            'id': 'root',
            'primitive': 'box',
            'bindings': {
                'scale.y': {
                    'column': column,
                    'interpretation': 'number-or-null',
                    'transform': {'null': 'not-rendered'},
                },
            },
        }],
    }


def _write_json(root: Path, name: str, payload: dict) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / name).write_text(json.dumps(payload), encoding='utf-8')


@pytest.fixture
def studio_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    system_templates = tmp_path / 'system-templates'
    system_presets = tmp_path / 'system-presets'
    studio_root = tmp_path / 'studio'
    _write_json(system_templates, 'system.template.json', _template('system.template'))

    registry = DVSRegistry(
        templates_root=system_templates,
        presets_root=system_presets,
        studio_root=studio_root,
    )
    store = DVSStudioStore(registry)
    monkeypatch.setattr(server_module, 'REGISTRY', registry)
    monkeypatch.setattr(server_module, 'STUDIO', store)
    monkeypatch.setattr(server_module, 'STUDIO_ROOT', studio_root.resolve())

    httpd = ThreadingHTTPServer(('127.0.0.1', 0), server_module.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address
    try:
        yield f'http://{host}:{port}', registry
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)
        assert not thread.is_alive()


def _request(base_url: str, method: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
    data = None if payload is None else json.dumps(payload).encode('utf-8')
    request = urllib.request.Request(
        base_url + path,
        method=method,
        data=data,
        headers={'Content-Type': 'application/json'} if data is not None else {},
    )
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            return response.status, json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode('utf-8'))


def _item_path(prefix: str, item_id: str) -> str:
    return prefix + urllib.parse.quote(item_id, safe='')


def test_studio_http_create_and_update_template(studio_server) -> None:
    base_url, registry = studio_server
    payload = _template('user/template')

    status, body = _request(base_url, 'POST', '/api/studio/input-templates', payload)
    assert status == 201
    assert body['ok'] is True
    assert body['input_template']['id'] == 'user/template'
    assert registry.templates.contains('user/template')

    updated = _template('user/template', column='score')
    status, body = _request(
        base_url,
        'PUT',
        _item_path('/api/studio/input-templates/', 'user/template'),
        updated,
    )
    assert status == 200
    assert body['input_template']['columns'] == [{
        'name': 'score',
        'selector': 'score',
        'type': 'number',
        'nullable': True,
    }]
    assert [column.name for column in registry.templates.get('user/template').columns] == ['score']


def test_studio_http_create_and_update_preset(studio_server) -> None:
    base_url, registry = studio_server
    status, _ = _request(base_url, 'POST', '/api/studio/input-templates', _template('table'))
    assert status == 201

    payload = _preset('view', 'table')
    status, body = _request(base_url, 'POST', '/api/studio/visualization-presets', payload)
    assert status == 201
    assert body['visualization_preset']['id'] == 'view'

    payload['generations'][0]['bindings'] = {
        'position.y': {
            'column': 'value',
            'interpretation': 'number-or-null',
            'transform': {'null': 'not-rendered'},
        },
    }
    status, body = _request(
        base_url,
        'PUT',
        _item_path('/api/studio/visualization-presets/', 'view'),
        payload,
    )
    assert status == 200
    assert 'position.y' in body['visualization_preset']['generations'][0]['bindings']
    assert list(registry.presets.get('view').generations[0].bindings) == ['position.y']


def test_studio_http_system_definition_is_read_only(studio_server) -> None:
    base_url, _ = studio_server
    status, body = _request(
        base_url,
        'PUT',
        _item_path('/api/studio/input-templates/', 'system.template'),
        _template('system.template', column='score'),
    )
    assert status == 403
    assert body['ok'] is False
    assert 'read-only' in body['error']


def test_studio_http_missing_update_is_404(studio_server) -> None:
    base_url, _ = studio_server
    status, body = _request(
        base_url,
        'PUT',
        _item_path('/api/studio/input-templates/', 'missing'),
        _template('missing'),
    )
    assert status == 404
    assert body['ok'] is False
    assert "has no item 'missing'" in body['error']


def test_studio_http_invalid_definition_is_400(studio_server) -> None:
    base_url, _ = studio_server
    status, body = _request(
        base_url,
        'POST',
        '/api/studio/input-templates',
        {'format': 'wrong', 'id': 'bad'},
    )
    assert status == 400
    assert body['ok'] is False
    assert body['error']


def test_studio_http_duplicate_create_is_400(studio_server) -> None:
    base_url, _ = studio_server
    payload = _template('table')
    status, _ = _request(base_url, 'POST', '/api/studio/input-templates', payload)
    assert status == 201
    status, body = _request(base_url, 'POST', '/api/studio/input-templates', payload)
    assert status == 400
    assert body['ok'] is False
    assert 'already exists' in body['error']


def test_studio_http_health_exposes_write_root(studio_server) -> None:
    base_url, _ = studio_server
    status, body = _request(base_url, 'GET', '/api/health')
    assert status == 200
    assert body['studio']['write_api'] is True
    assert body['studio']['draft_api'] is True
    assert body['studio']['root']


def test_studio_http_validates_draft_template_without_persistence(studio_server) -> None:
    base_url, registry = studio_server
    status, body = _request(
        base_url,
        'POST',
        '/api/studio/validate/input-template',
        _template('draft'),
    )
    assert status == 200
    assert body['input_template']['id'] == 'draft'
    assert not registry.templates.contains('draft')


def test_studio_http_previews_typed_draft_template_against_source(studio_server) -> None:
    base_url, registry = studio_server
    status, body = _request(
        base_url,
        'POST',
        '/api/studio/preview/input-template',
        {
            'definition': _template('draft'),
            'source': {'records': [{'value': '5.5'}, {'value': None}]},
        },
    )
    assert status == 200
    assert body['columns'] == ['value']
    assert body['column_types'] == ['number']
    assert body['rows'] == [[5.5], [None]]
    assert body['parameters'] == {}
    assert not registry.templates.contains('draft')


def test_studio_http_finds_typed_range_before_scaling(studio_server) -> None:
    base_url, registry = studio_server
    definition = _template('draft')
    definition['columns'][0]['scale'] = {'low': 0, 'high': 100, 'power': 2}
    status, body = _request(
        base_url,
        'POST',
        '/api/studio/range/input-template',
        {
            'definition': definition,
            'source': {'records': [{'value': '1.5'}, {'value': None}, {'value': 8}]},
            'column': 'value',
        },
    )
    assert status == 200
    assert body['column'] == 'value'
    assert body['low'] == 1.5
    assert body['high'] == 8.0
    assert not registry.templates.contains('draft')


def test_studio_http_validates_and_previews_draft_preset_without_persistence(studio_server) -> None:
    base_url, registry = studio_server
    status, _ = _request(base_url, 'POST', '/api/studio/input-templates', _template('table'))
    assert status == 201

    preset = _preset('draft-view', 'table')
    status, body = _request(
        base_url,
        'POST',
        '/api/studio/validate/visualization-preset',
        preset,
    )
    assert status == 200
    assert body['visualization_preset']['id'] == 'draft-view'
    assert not registry.presets.contains('draft-view')

    status, body = _request(
        base_url,
        'POST',
        '/api/studio/preview/visualization-preset',
        {
            'definition': preset,
            'source': {'records': [{'value': 3}]},
        },
    )
    assert status == 200
    assert body['visual_plan']['format'] == 's3d.dvs.visual-plan'
    assert body['visual_plan']['row_count'] == 1
    assert not registry.presets.contains('draft-view')


def test_studio_http_draft_preview_rejects_closed_shape_violation(studio_server) -> None:
    base_url, _ = studio_server
    status, body = _request(
        base_url,
        'POST',
        '/api/studio/preview/input-template',
        {
            'definition': _template('draft'),
            'source': {'records': []},
            'extra': True,
        },
    )
    assert status == 400
    assert body['ok'] is False
    assert 'requires exactly definition and source' in body['error']


def test_studio_http_lists_database_sources_without_secrets(studio_server, monkeypatch) -> None:
    base_url, _ = studio_server

    class Source:
        def public_dict(self):
            return {
                'id': 'local',
                'label': 'Local',
                'host': '127.0.0.1',
                'port': 3306,
                'database': 'lmts',
                'username': 'lmts',
            }

    monkeypatch.setattr(server_module, 'load_all_dvs_database_sources', lambda: (Source(),))
    status, body = _request(base_url, 'GET', '/api/database-sources')
    assert status == 200
    assert body['database_sources'][0]['id'] == 'local'
    assert 'password' not in body['database_sources'][0]


def test_studio_http_lists_reports_from_multiple_selected_databases(studio_server, monkeypatch) -> None:
    base_url, _ = studio_server
    calls = []

    def fake_list(source_ids, *, limit_per_source):
        calls.append((source_ids, limit_per_source))
        return [
            {'database_source_id': 'a', 'report_id': 'r-a'},
            {'database_source_id': 'b', 'report_id': 'r-b'},
        ]

    monkeypatch.setattr(server_module, 'list_database_reports', fake_list)
    status, body = _request(
        base_url,
        'POST',
        '/api/database-reports',
        {'source_ids': ['a', 'b'], 'limit_per_source': 25},
    )
    assert status == 200
    assert calls == [(['a', 'b'], 25)]
    assert [item['report_id'] for item in body['reports']] == ['r-a', 'r-b']


def test_studio_http_loads_one_report_from_explicit_database(studio_server, monkeypatch) -> None:
    base_url, _ = studio_server
    calls = []

    def fake_load(source_id, report_id):
        calls.append((source_id, report_id))
        return {'format': 'lmts.report', 'version': '1.1', 'report': {'id': report_id}}

    monkeypatch.setattr(server_module, 'load_database_report', fake_load)
    status, body = _request(
        base_url,
        'POST',
        '/api/database-report',
        {'source_id': 'archive', 'report_id': 'r-42'},
    )
    assert status == 200
    assert calls == [('archive', 'r-42')]
    assert body['source']['report']['id'] == 'r-42'
