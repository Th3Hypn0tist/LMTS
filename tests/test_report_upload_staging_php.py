from __future__ import annotations

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
    code = f"""
require {json.dumps(str(library))};
$config = ['upload_staging_dir' => {json.dumps(str(staging))}];
$body = '{{"format":"lmts.report","payload":"' . str_repeat('x', 700000) . '"}}';
$chunkSize = 262144;
$chunkCount = (int)ceil(strlen($body) / $chunkSize);
$init = lmts_upload_init($config, [
    'report_id' => 'report-1',
    'size_bytes' => strlen($body),
    'chunk_size' => $chunkSize,
    'chunk_count' => $chunkCount,
    'sha256' => hash('sha256', $body),
]);
$uploadId = $init['upload_id'];
for ($index = 0; $index < $chunkCount; $index++) {{
    $chunk = substr($body, $index * $chunkSize, $chunkSize);
    lmts_upload_put_chunk($config, $uploadId, $index, $chunk);
}}
[$dir, $meta, $assembled] = lmts_upload_assemble($config, $uploadId);
if ($assembled !== $body) {{
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
