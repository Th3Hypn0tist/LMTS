from __future__ import annotations

import json
import mimetypes
import os
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .registry import DVSRegistry
from .runtime import project_visualization


PACKAGE_DIR = Path(__file__).resolve().parent
STATIC_DIR = (PACKAGE_DIR / 'static').resolve()
HOST = os.environ.get('LMTS_DVS_HOST', '127.0.0.1')
PORT = int(os.environ.get('LMTS_DVS_PORT', '8775'))
S3D_ROOT_VALUE = os.environ.get('LMTS_S3D_ROOT', '').strip()
S3D_ROOT = Path(S3D_ROOT_VALUE).expanduser().resolve() if S3D_ROOT_VALUE else None
REGISTRY = DVSRegistry()


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
                    's3d': s3d_status(),
                })
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
        except FileNotFoundError as exc:
            return self._json({'ok': False, 'error': str(exc)}, 404)
        except KeyError as exc:
            return self._json({'ok': False, 'error': str(exc)}, 404)
        except Exception as exc:
            return self._json({'ok': False, 'error': str(exc)}, 400)

    def do_POST(self) -> None:
        path = urllib.parse.urlparse(self.path).path
        try:
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
                    'rows': [list(row) for row in extracted.rows],
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
        except KeyError as exc:
            return self._json({'ok': False, 'error': str(exc)}, 404)
        except Exception as exc:
            return self._json({'ok': False, 'error': str(exc)}, 400)

    def log_message(self, fmt: str, *args) -> None:
        print(f'[lmts-dvs] {self.address_string()} {fmt % args}')


def main() -> None:
    REGISTRY.reload()
    status = s3d_status()
    if status['configured'] and not status['ready']:
        raise RuntimeError(f"LMTS_S3D_ROOT is invalid or missing s3d.js: {S3D_ROOT}")
    print(f'LMTS DVS -> http://{HOST}:{PORT}')
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == '__main__':
    main()
