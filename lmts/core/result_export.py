from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from .run import utc_now
from .store import RunStore, safe_component


EXPORT_SCHEMA_VERSION = 1


def _timestamp() -> str:
    return datetime.now().astimezone().strftime('%Y%m%d%H%M')


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, ensure_ascii=False) + '\n'
    temp = path.with_suffix(path.suffix + f'.tmp-{os.getpid()}')
    temp.write_text(text, encoding='utf-8')
    try:
        temp.replace(path)
    finally:
        if temp.exists():
            temp.unlink()
    return path


def export_run_json(run_data: dict, output_folder: Path) -> Path:
    run_id = str(run_data.get('run_id') or '').strip()
    if not run_id:
        raise ValueError('canonical run is missing run_id')
    short_id = safe_component(run_id)[:12]
    path = output_folder.expanduser() / f'{_timestamp()}-run-{short_id}.json'
    return _write_json(path, run_data)


def _resolve_run_path(results_root: Path, locator: str) -> Path:
    root = results_root.expanduser().resolve()
    candidate = Path(locator).expanduser()
    resolved = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError(f'canonical run result escapes results root: {locator!r}')
    return resolved


def _validate_cell_run(cell: dict, run_data: dict, run_id: str) -> None:
    expected = {
        'run_id': run_id,
        'executor_id': str(cell.get('target_id') or ''),
        'executor_kind': str(cell.get('target_kind') or ''),
        'test_ref': str(cell.get('test_ref') or ''),
        'status': str(cell.get('status') or ''),
        'passed': cell.get('passed'),
    }
    actual = {
        'run_id': str(run_data.get('run_id') or ''),
        'executor_id': str(run_data.get('executor_id') or ''),
        'executor_kind': str(run_data.get('executor_kind') or ''),
        'test_ref': str(run_data.get('test_ref') or ''),
        'status': str(run_data.get('status') or ''),
        'passed': run_data.get('passed'),
    }
    for field, expected_value in expected.items():
        if actual[field] != expected_value:
            raise ValueError(
                f'canonical matrix/run mismatch for {run_id}: {field} '
                f'{expected_value!r} != {actual[field]!r}'
            )


def build_matrix_bundle(matrix_data: dict, *, results_root: Path) -> dict:
    matrix_id = str(matrix_data.get('matrix_id') or '').strip()
    if not matrix_id:
        raise ValueError('canonical matrix is missing matrix_id')
    cells = matrix_data.get('cells')
    if not isinstance(cells, list):
        raise ValueError('canonical matrix cells must be a list')

    store = RunStore(results_root)
    runs: list[dict] = []
    for cell in cells:
        if not isinstance(cell, dict):
            raise ValueError('canonical matrix contains a non-object cell')
        run_id = str(cell.get('run_id') or '').strip()
        result_path_text = str(cell.get('result_path') or '').strip()
        if not run_id or not result_path_text:
            raise ValueError('canonical matrix cell is missing run_id or result_path')
        result_path = _resolve_run_path(results_root, result_path_text)
        if not result_path.is_file():
            raise FileNotFoundError(f'canonical run result missing: {result_path}')
        run_data = store.load(result_path)
        _validate_cell_run(cell, run_data, run_id)
        runs.append(run_data)

    return {
        'schema_version': EXPORT_SCHEMA_VERSION,
        'export_type': 'lmts.matrix_bundle',
        'exported_at': utc_now(),
        'matrix': matrix_data,
        'runs': runs,
    }


def export_matrix_bundle(matrix_data: dict, output_folder: Path, *, results_root: Path) -> Path:
    payload = build_matrix_bundle(matrix_data, results_root=results_root)
    matrix_id = str(matrix_data.get('matrix_id') or '').strip()
    short_id = safe_component(matrix_id)[:12]
    path = output_folder.expanduser() / f'{_timestamp()}-matrix-{short_id}.json'
    return _write_json(path, payload)
