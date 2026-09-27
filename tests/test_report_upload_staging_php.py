from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest


PHP = shutil.which('php')


def _run_php(tmp_path: Path, code: str) -> subprocess.CompletedProcess[str]:
    if PHP is None:
        pytest.skip('PHP CLI is required for upload staging tests')
    runner = tmp_path / 'runner.php'
    runner.write_text("<?php\ndeclare(strict_types=1);\n" + code, encoding='utf-8')
    return subprocess.run(
        [PHP, str(runner)],
        text=True,
        capture_output=True,
        check=False,
    )


def test_chunked_upload_staging_round_trip(tmp_path: Path) -> None:
    library = Path('php/storage/lib/report_upload.php').resolve()
    staging = tmp_path / 'staging'
    body = (b'{"format":"lmts.report","payload":"' + b'x' * 700000 + b'"}')
    chunk_size = 262144
    chunks = [body[index:index + chunk_size] for index in range(0, len(body), chunk_size)]
    metadata = {
        'report_id': 'report-1',
        'size_bytes': len(body),
        'chunk_size': chunk_size,
        'chunk_count': len(chunks),
        'sha256': hashlib.sha256(body).hexdigest(),
    }

    chunk_literals = ','.join(
        "'" + chunk.hex() + "'" for chunk in chunks
    )
    code = f"""
require {json.dumps(str(library))};
$config = ['upload_staging_dir' => {json.dumps(str(staging))}];
$init = lmts_upload_init($config, json_decode({json.dumps(json.dumps(metadata))}, true, 32, JSON_THROW_ON_ERROR));
$uploadId = $init['upload_id'];
$chunks = [{chunk_literals}];
foreach ($chunks as $index => $hex) {{
    lmts_upload_put_chunk($config, $uploadId, $index, hex2bin($hex));
}}
[$dir, $meta, $assembled] = lmts_upload_assemble($config, $uploadId);
if ($assembled !== hex2bin({json.dumps(body.hex())})) {{
    fwrite(STDERR, 'assembled bytes differ');
    exit(2);
}}
lmts_upload_delete_tree($dir);
if (is_dir($dir)) {{
    fwrite(STDERR, 'staging directory remains');
    exit(3);
}}
fwrite(STDOUT, 'OK');
"""
    result = _run_php(tmp_path, code)
    assert result.returncode == 0, result.stderr
    assert result.stdout == 'OK'


def test_expired_upload_gc_removes_staging(tmp_path: Path) -> None:
    library = Path('php/storage/lib/report_upload.php').resolve()
    staging = tmp_path / 'staging'
    code = f"""
require {json.dumps(str(library))};
$config = ['upload_staging_dir' => {json.dumps(str(staging))}];
lmts_upload_require_dir({json.dumps(str(staging))});
$uploadId = str_repeat('a', 48);
$dir = lmts_upload_dir($config, $uploadId);
mkdir($dir, 0700);
lmts_upload_write_meta($dir, [
    'upload_id' => $uploadId,
    'expires_at_epoch' => time() - 1,
]);
lmts_upload_gc($config);
if (is_dir($dir)) {{
    fwrite(STDERR, 'expired staging directory remains');
    exit(2);
}}
fwrite(STDOUT, 'OK');
"""
    result = _run_php(tmp_path, code)
    assert result.returncode == 0, result.stderr
    assert result.stdout == 'OK'
