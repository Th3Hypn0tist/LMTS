from __future__ import annotations

import json
import mimetypes
import os
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from lmts.core.settings import DEFAULT_SETTINGS_PATH

from .database_sources import database_source_statuses, load_all_dvs_database_sources, load_database_report, list_database_reports
from .report_dataset import project_percent_telemetry_dataset
from .report_sources import load_all_dvs_report_sources, load_report_source_report, list_report_source_reports, report_source_statuses
from .registry import DVSRegistry
from .runtime import project_visualization
from .studio import DVSStudioStore
from .studio_preview import (
    find_input_template_range,
    preview_input_template,
    preview_visualization_preset,
    validate_input_template,
    validate_visualization_preset,
)


PACKAGE_DIR = Path(__file__).resolve().parent
SOURCE_ROOT = Path(os.environ.get('LMTS_DVS_SOURCE_ROOT') or Path(__file__).resolve().parents[2]).resolve()
API_FEATURES = [
    'database_sources',
    'database_source_statuses',
    'database_reports',
    'database_report',
    'report_sources',
    'report_source_statuses',
    'report_source_reports',
    'report_source_report',
    'report_source_dataset',
]
STATIC_DIR = (PACKAGE_DIR / 'static').resolve()
HOST = os.environ.get('LMTS_DVS_HOST', '0.0.0.0')
PORT = int(os.environ.get('LMTS_DVS_PORT', '8775'))
INSTANCE_ID = os.environ.get('LMTS_DVS_INSTANCE_ID', '').strip()
S3D_ROOT_VALUE = os.environ.get('LMTS_S3D_ROOT', '').strip()
S3D_ROOT = Path(S3D_ROOT_VALUE).expanduser().resolve() if S3D_ROOT_VALUE else None
STUDIO_ROOT_VALUE = os.environ.get('LMTS_DVS_STUDIO_ROOT', '.lmts/dvs').strip()
if not STUDIO_ROOT_VALUE:
    raise ValueError('LMTS_DVS_STUDIO_ROOT must not be empty')
STUDIO_ROOT = Path(STUDIO_ROOT_VALUE).expanduser().resolve()
REGISTRY = DVSRegistry(studio_root=STUDIO_ROOT)
STUDIO = DVSStudioStore(REGISTRY)


def safe_asset_path(root: Path, relative_path: str) -> Path:
    decoded = urllib.parse.unquote(relative_path).replace('\\', '/')
    candidate = (root / decoded.lstrip('/')).resolve()
    if root not in candidate.parents and candidate != root:
        raise ValueError('asset path escapes configured root')
    if not candidate.is_file():
        raise FileNotFoundError(relative_path)
    return candidate


def content_type(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(path.name)
    if path.suffix == '.js':
        return 'application/javascript; charset=utf-8'
    if path.suffix == '.css':
        return 'text/css; charset=utf-8'
    if path.suffix == '.html':
        return 'text/html; charset=utf-8'
    if guessed and guessed.startswith('text/'):
        return f'{guessed}; charset=utf-8'
    return guessed or 'application/octet-stream'


def s3d_status() -> dict[str, Any]:
    if S3D_ROOT is None:
        return {'configured': False, 'ready': False}
    entrypoint = S3D_ROOT / 's3d.js'
    return {
        'configured': True,
        'ready': S3D_ROOT.is_dir() and entrypoint.is_file(),
        'root': str(S3D_ROOT),
        'entrypoint': '/s3d/s3d.js',
    }


class Handler(BaseHTTPRequestHandler):
    server_version = 'LMTS-DVS/1.0'

    def _json(self, payload: Any, status: int = 200) -> None:
        raw = json.dumps(payload, ensure_ascii=False, indent=2).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(raw)

    def _file(self, path: Path) -> None:
        raw = path.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', content_type(path))
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(raw)

    def _body(self) -> dict[str, Any]:
        size = int(self.headers.get('Content-Length', '0') or 0)
        if size <= 0:
            raise ValueError('request body is required')
        payload = json.loads(self.rfile.read(size).decode('utf-8'))
        if not isinstance(payload, dict):
            raise ValueError('JSON request body must be an object')
        return payload

    def _error(self, exc: Exception) -> None:
        if isinstance(exc, PermissionError):
            return self._json({'ok': False, 'error': str(exc)}, 403)
        if isinstance(exc, (FileNotFoundError, KeyError)):
            return self._json({'ok': False, 'error': str(exc)}, 404)
        return self._json({'ok': False, 'error': str(exc)}, 400)

    def do_GET(self) -> None:
        path = urllib.parse.urlparse(self.path).path
        try:
            if path == '/':
                return self._file(safe_asset_path(STATIC_DIR, 'index.html'))
            if path.startswith('/static/'):
                return self._file(safe_asset_path(STATIC_DIR, path.removeprefix('/static/')))
            if path.startswith('/s3d/'):
                if S3D_ROOT is None:
                    return self._json({'ok': False, 'error': 's3d_not_configured'}, 503)
                return self._file(safe_asset_path(S3D_ROOT, path.removeprefix('/s3d/')))
            if path == '/api/health':
                return self._json({
                    'ok': True,
                    'service': 'LMTS DVS',
                    'host_role': 'studio+viewer',
                    'version': '1.0',
                    'instance_id': INSTANCE_ID,
                    'runtime': {
                        'source_root': str(SOURCE_ROOT),
                        'server_file': str(Path(__file__).resolve()),
                        'settings_path': str(DEFAULT_SETTINGS_PATH),
                    },
                    'api_features': API_FEATURES,
                    's3d': s3d_status(),
                    'studio': {
                        'root': str(STUDIO_ROOT),
                        'write_api': True,
                        'draft_api': True,
                    },
                })
            if path == '/api/database-sources':
                return self._json({'database_sources': [item.public_dict() for item in load_all_dvs_database_sources()]})
            if path == '/api/database-source-statuses':
                return self._json({'database_sources': database_source_statuses()})
            if path == '/api/report-sources':
                return self._json({'report_sources': [item.public_dict() for item in load_all_dvs_report_sources()]})
            if path == '/api/report-source-statuses':
                return self._json({'report_sources': report_source_statuses()})
            if path == '/api/input-templates':
                return self._json({'input_templates': [item.to_dict() for item in REGISTRY.templates.list()]})
            if path.startswith('/api/input-templates/'):
                item_id = urllib.parse.unquote(path.removeprefix('/api/input-templates/'))
                return self._json({'input_template': REGISTRY.templates.get(item_id).to_dict()})
            if path == '/api/visualization-presets':
                return self._json({'visualization_presets': [item.to_dict() for item in REGISTRY.presets.list()]})
            if path.startswith('/api/visualization-presets/'):
                item_id = urllib.parse.unquote(path.removeprefix('/api/visualization-presets/'))
                return self._json({'visualization_preset': REGISTRY.presets.get(item_id).to_dict()})
            return self._json({'ok': False, 'error': 'not_found'}, 404)
        except Exception as exc:
            return self._error(exc)

    def do_POST(self) -> None:
        path = urllib.parse.urlparse(self.path).path
        try:
            if path == '/api/database-reports':
                payload = self._body()
                if set(payload) != {'source_ids', 'limit_per_source'}:
                    raise ValueError('/api/database-reports requires exactly source_ids and limit_per_source')
                source_ids = payload['source_ids']
                if not isinstance(source_ids, list) or not all(isinstance(item, str) for item in source_ids):
                    raise ValueError('source_ids must be a list of strings')
                limit = payload['limit_per_source']
                if isinstance(limit, bool) or not isinstance(limit, int):
                    raise ValueError('limit_per_source must be an integer')
                return self._json({'ok': True, 'reports': list_database_reports(source_ids, limit_per_source=limit)})
            if path == '/api/database-report':
                payload = self._body()
                if set(payload) != {'source_id', 'report_id'}:
                    raise ValueError('/api/database-report requires exactly source_id and report_id')
                return self._json({
                    'ok': True,
                    'source_id': str(payload['source_id']),
                    'report_id': str(payload['report_id']),
                    'source': load_database_report(str(payload['source_id']), str(payload['report_id'])),
                })
            if path == '/api/report-source-reports':
                payload = self._body()
                if set(payload) != {'source_ids', 'limit_per_source'}:
                    raise ValueError('/api/report-source-reports requires exactly source_ids and limit_per_source')
                source_ids = payload['source_ids']
                if not isinstance(source_ids, list) or not all(isinstance(item, str) for item in source_ids):
                    raise ValueError('source_ids must be a list of strings')
                limit = payload['limit_per_source']
                if isinstance(limit, bool) or not isinstance(limit, int):
                    raise ValueError('limit_per_source must be an integer')
                return self._json({
                    'ok': True,
                    'reports': list_report_source_reports(source_ids, limit_per_source=limit),
                })
            if path == '/api/report-source-report':
                payload = self._body()
                if set(payload) != {'source_id', 'report_id'}:
                    raise ValueError('/api/report-source-report requires exactly source_id and report_id')
                return self._json({
                    'ok': True,
                    'source_id': str(payload['source_id']),
                    'report_id': str(payload['report_id']),
                    'source': load_report_source_report(str(payload['source_id']), str(payload['report_id'])),
                })
            if path == '/api/report-source-dataset':
                payload = self._body()
                if set(payload) != {'reports'}:
                    raise ValueError('/api/report-source-dataset requires exactly reports')
                selections = payload['reports']
                if not isinstance(selections, list) or not selections:
                    raise ValueError('reports must be a non-empty array')
                if len(selections) > 100:
                    raise ValueError('reports selection must contain at most 100 items')
                loaded: list[tuple[str, str, dict[str, Any]]] = []
                seen: set[tuple[str, str]] = set()
                for index, selection in enumerate(selections):
                    if not isinstance(selection, dict) or set(selection) != {'source_id', 'report_id'}:
                        raise ValueError(f'reports[{index}] requires exactly source_id and report_id')
                    source_id = str(selection['source_id']).strip()
                    report_id = str(selection['report_id']).strip()
                    if not source_id or not report_id:
                        raise ValueError(f'reports[{index}] source_id and report_id must not be empty')
                    key = (source_id, report_id)
                    if key in seen:
                        continue
                    seen.add(key)
                    loaded.append((source_id, report_id, load_report_source_report(source_id, report_id)))
                dataset = project_percent_telemetry_dataset(loaded)
                return self._json({'ok': True, 'selected_report_count': len(seen), 'source': dataset})
            if path == '/api/studio/validate/input-template':
                return self._json({'ok': True, 'input_template': validate_input_template(self._body())})
            if path == '/api/studio/preview/input-template':
                return self._json({'ok': True, **preview_input_template(self._body())})
            if path == '/api/studio/range/input-template':
                return self._json({'ok': True, **find_input_template_range(self._body())})
            if path == '/api/studio/validate/visualization-preset':
                return self._json({
                    'ok': True,
                    'visualization_preset': validate_visualization_preset(self._body(), REGISTRY),
                })
            if path == '/api/studio/preview/visualization-preset':
                return self._json({'ok': True, **preview_visualization_preset(self._body(), REGISTRY)})
            if path == '/api/studio/input-templates':
                item = STUDIO.create_input_template(self._body())
                return self._json({'ok': True, 'input_template': item.to_dict()}, 201)
            if path == '/api/studio/visualization-presets':
                item = STUDIO.create_visualization_preset(self._body())
                return self._json({'ok': True, 'visualization_preset': item.to_dict()}, 201)
            if path == '/api/extract':
                payload = self._body()
                if set(payload) != {'input_template_id', 'source'}:
                    raise ValueError('/api/extract requires exactly input_template_id and source')
                template = REGISTRY.templates.get(str(payload['input_template_id']))
                extracted = template.extract(payload['source'])
                return self._json({
                    'ok': True,
                    'input_template_id': template.id,
                    'columns': list(extracted.columns),
                    'column_types': list(extracted.column_types),
                    'rows': [list(row) for row in extracted.rows],
                    'parameters': dict(extracted.parameters),
                })
            if path == '/api/visualize':
                payload = self._body()
                required = {'input_template_id', 'visualization_preset_id', 'source'}
                if set(payload) != required:
                    raise ValueError(
                        '/api/visualize requires exactly input_template_id, visualization_preset_id and source'
                    )
                template = REGISTRY.templates.get(str(payload['input_template_id']))
                preset = REGISTRY.presets.get(str(payload['visualization_preset_id']))
                plan = project_visualization(payload['source'], template, preset)
                return self._json({'ok': True, 'visual_plan': plan})
            return self._json({'ok': False, 'error': 'not_found'}, 404)
        except Exception as exc:
            return self._error(exc)

    def do_PUT(self) -> None:
        path = urllib.parse.urlparse(self.path).path
        try:
            template_prefix = '/api/studio/input-templates/'
            if path.startswith(template_prefix):
                item_id = urllib.parse.unquote(path.removeprefix(template_prefix))
                if not item_id:
                    raise ValueError('Input Template id is required')
                item = STUDIO.update_input_template(item_id, self._body())
                return self._json({'ok': True, 'input_template': item.to_dict()})

            preset_prefix = '/api/studio/visualization-presets/'
            if path.startswith(preset_prefix):
                item_id = urllib.parse.unquote(path.removeprefix(preset_prefix))
                if not item_id:
                    raise ValueError('Visualization Preset id is required')
                item = STUDIO.update_visualization_preset(item_id, self._body())
                return self._json({'ok': True, 'visualization_preset': item.to_dict()})

            return self._json({'ok': False, 'error': 'not_found'}, 404)
        except Exception as exc:
            return self._error(exc)

    def log_message(self, fmt: str, *args) -> None:
        print(f'[lmts-dvs] {self.address_string()} {fmt % args}')


def main() -> None:
    REGISTRY.reload()
    status = s3d_status()
    if status['configured'] and not status['ready']:
        raise RuntimeError(f"LMTS_S3D_ROOT is invalid or missing s3d.js: {S3D_ROOT}")
    print(f'LMTS DVS -> http://{HOST}:{PORT}')
    print(f'DVS Studio -> {STUDIO_ROOT}')
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == '__main__':
    main()
