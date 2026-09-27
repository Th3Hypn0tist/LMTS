<?php

declare(strict_types=1);

const LMTS_UPLOAD_DEFAULT_CHUNK_SIZE = 262144;
const LMTS_UPLOAD_MAX_CHUNK_SIZE = 524288;
const LMTS_UPLOAD_MAX_REPORT_SIZE = 67108864;
const LMTS_UPLOAD_MAX_CHUNKS = 256;
const LMTS_UPLOAD_TTL_SECONDS = 900;

function lmts_upload_base_dir(array $config): string {
    $configured = trim((string)($config['upload_staging_dir'] ?? ''));
    if ($configured !== '') return rtrim($configured, DIRECTORY_SEPARATOR);
    return __DIR__ . '/../../private_uploads';
}

function lmts_upload_require_dir(string $path): void {
    if (is_dir($path)) return;
    if (!mkdir($path, 0700, true) && !is_dir($path)) {
        throw new RuntimeException('cannot create upload staging directory');
    }
}

function lmts_upload_safe_id(): string {
    return bin2hex(random_bytes(24));
}

function lmts_upload_dir(array $config, string $uploadId): string {
    if (preg_match('/^[a-f0-9]{48}$/', $uploadId) !== 1) {
        throw new InvalidArgumentException('invalid upload id');
    }
    return lmts_upload_base_dir($config) . DIRECTORY_SEPARATOR . $uploadId;
}

function lmts_upload_meta_path(string $dir): string {
    return $dir . DIRECTORY_SEPARATOR . 'meta.json';
}

function lmts_upload_chunk_path(string $dir, int $index): string {
    return $dir . DIRECTORY_SEPARATOR . sprintf('%06d.chunk', $index);
}

function lmts_upload_atomic_write(string $path, string $bytes): void {
    $tmp = $path . '.tmp-' . bin2hex(random_bytes(8));
    if (file_put_contents($tmp, $bytes, LOCK_EX) !== strlen($bytes)) {
        @unlink($tmp);
        throw new RuntimeException('failed to write upload staging file');
    }
    @chmod($tmp, 0600);
    if (!rename($tmp, $path)) {
        @unlink($tmp);
        throw new RuntimeException('failed to finalize upload staging file');
    }
}

function lmts_upload_write_meta(string $dir, array $meta): void {
    lmts_upload_atomic_write(
        lmts_upload_meta_path($dir),
        json_encode($meta, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR),
    );
}

function lmts_upload_read_meta(string $dir): array {
    $path = lmts_upload_meta_path($dir);
    $raw = @file_get_contents($path);
    if ($raw === false) throw new RuntimeException('upload metadata not found');
    $meta = json_decode($raw, true, 32, JSON_THROW_ON_ERROR);
    if (!is_array($meta)) throw new RuntimeException('invalid upload metadata');
    return $meta;
}

function lmts_upload_delete_tree(string $dir): void {
    if (!is_dir($dir)) return;
    $items = scandir($dir);
    if ($items === false) return;
    foreach ($items as $item) {
        if ($item === '.' || $item === '..') continue;
        $path = $dir . DIRECTORY_SEPARATOR . $item;
        if (is_dir($path)) {
            lmts_upload_delete_tree($path);
        } else {
            @unlink($path);
        }
    }
    @rmdir($dir);
}

function lmts_upload_gc(array $config): void {
    $base = lmts_upload_base_dir($config);
    if (!is_dir($base)) return;
    $items = scandir($base);
    if ($items === false) return;
    $now = time();
    foreach ($items as $item) {
        if ($item === '.' || $item === '..' || preg_match('/^[a-f0-9]{48}$/', $item) !== 1) continue;
        $dir = $base . DIRECTORY_SEPARATOR . $item;
        if (!is_dir($dir)) continue;
        try {
            $meta = lmts_upload_read_meta($dir);
            $expiresAt = (int)($meta['expires_at_epoch'] ?? 0);
            if ($expiresAt > 0 && $expiresAt < $now) {
                lmts_upload_delete_tree($dir);
            }
        } catch (Throwable $error) {
            $mtime = @filemtime($dir);
            if ($mtime !== false && $mtime + LMTS_UPLOAD_TTL_SECONDS < $now) {
                lmts_upload_delete_tree($dir);
            }
        }
    }
}

function lmts_upload_init(array $config, array $request): array {
    lmts_upload_gc($config);

    $reportId = trim((string)($request['report_id'] ?? ''));
    $sizeBytes = $request['size_bytes'] ?? null;
    $chunkSize = $request['chunk_size'] ?? LMTS_UPLOAD_DEFAULT_CHUNK_SIZE;
    $chunkCount = $request['chunk_count'] ?? null;
    $sha256 = strtolower(trim((string)($request['sha256'] ?? '')));

    if ($reportId === '') throw new InvalidArgumentException('report_id is required');
    if (!is_int($sizeBytes) || $sizeBytes <= 0 || $sizeBytes > LMTS_UPLOAD_MAX_REPORT_SIZE) {
        throw new InvalidArgumentException('invalid report size');
    }
    if (!is_int($chunkSize) || $chunkSize <= 0 || $chunkSize > LMTS_UPLOAD_MAX_CHUNK_SIZE) {
        throw new InvalidArgumentException('invalid chunk size');
    }
    if (!is_int($chunkCount) || $chunkCount <= 0 || $chunkCount > LMTS_UPLOAD_MAX_CHUNKS) {
        throw new InvalidArgumentException('invalid chunk count');
    }
    $expectedChunks = (int)ceil($sizeBytes / $chunkSize);
    if ($chunkCount !== $expectedChunks) {
        throw new InvalidArgumentException('chunk count does not match report size');
    }
    if (preg_match('/^[a-f0-9]{64}$/', $sha256) !== 1) {
        throw new InvalidArgumentException('invalid sha256');
    }

    $base = lmts_upload_base_dir($config);
    lmts_upload_require_dir($base);

    do {
        $uploadId = lmts_upload_safe_id();
        $dir = lmts_upload_dir($config, $uploadId);
    } while (file_exists($dir));

    if (!mkdir($dir, 0700, false)) {
        throw new RuntimeException('cannot create upload session');
    }

    $now = time();
    $meta = [
        'upload_id' => $uploadId,
        'report_id' => $reportId,
        'size_bytes' => $sizeBytes,
        'chunk_size' => $chunkSize,
        'chunk_count' => $chunkCount,
        'sha256' => $sha256,
        'created_at_epoch' => $now,
        'expires_at_epoch' => $now + LMTS_UPLOAD_TTL_SECONDS,
    ];
    lmts_upload_write_meta($dir, $meta);

    return [
        'ok' => true,
        'upload_id' => $uploadId,
        'expires_at' => gmdate('c', $meta['expires_at_epoch']),
        'chunk_size' => $chunkSize,
        'chunk_count' => $chunkCount,
    ];
}

function lmts_upload_get_active(array $config, string $uploadId): array {
    $dir = lmts_upload_dir($config, $uploadId);
    if (!is_dir($dir)) throw new InvalidArgumentException('unknown upload id');
    $meta = lmts_upload_read_meta($dir);
    if ((int)($meta['expires_at_epoch'] ?? 0) < time()) {
        lmts_upload_delete_tree($dir);
        throw new InvalidArgumentException('upload expired');
    }
    return [$dir, $meta];
}

function lmts_upload_put_chunk(array $config, string $uploadId, int $index, string $bytes): array {
    [$dir, $meta] = lmts_upload_get_active($config, $uploadId);
    $chunkCount = (int)$meta['chunk_count'];
    if ($index < 0 || $index >= $chunkCount) {
        throw new InvalidArgumentException('chunk index out of range');
    }

    $chunkSize = (int)$meta['chunk_size'];
    $expected = $index === $chunkCount - 1
        ? (int)$meta['size_bytes'] - ($chunkSize * ($chunkCount - 1))
        : $chunkSize;

    $length = strlen($bytes);
    if ($length !== $expected) {
        throw new InvalidArgumentException('chunk size mismatch');
    }
    if ($length > LMTS_UPLOAD_MAX_CHUNK_SIZE) {
        throw new InvalidArgumentException('chunk too large');
    }

    $path = lmts_upload_chunk_path($dir, $index);
    if (is_file($path)) {
        $existing = file_get_contents($path);
        if ($existing === false) throw new RuntimeException('cannot read existing chunk');
        if (!hash_equals(hash('sha256', $existing), hash('sha256', $bytes))) {
            throw new RuntimeException('duplicate chunk differs from existing content');
        }
    } else {
        lmts_upload_atomic_write($path, $bytes);
    }

    return [
        'ok' => true,
        'upload_id' => $uploadId,
        'chunk' => $index,
        'received_bytes' => $length,
    ];
}

function lmts_upload_assemble(array $config, string $uploadId): array {
    [$dir, $meta] = lmts_upload_get_active($config, $uploadId);
    $chunkCount = (int)$meta['chunk_count'];
    $buffer = '';
    $hash = hash_init('sha256');
    $total = 0;

    for ($index = 0; $index < $chunkCount; $index++) {
        $path = lmts_upload_chunk_path($dir, $index);
        if (!is_file($path)) throw new InvalidArgumentException("missing chunk $index");
        $bytes = file_get_contents($path);
        if ($bytes === false) throw new RuntimeException("cannot read chunk $index");
        $total += strlen($bytes);
        if ($total > LMTS_UPLOAD_MAX_REPORT_SIZE) {
            throw new InvalidArgumentException('assembled report exceeds maximum size');
        }
        hash_update($hash, $bytes);
        $buffer .= $bytes;
    }

    if ($total !== (int)$meta['size_bytes']) {
        throw new InvalidArgumentException('assembled report size mismatch');
    }
    $digest = hash_final($hash);
    if (!hash_equals((string)$meta['sha256'], $digest)) {
        throw new InvalidArgumentException('assembled report sha256 mismatch');
    }

    return [$dir, $meta, $buffer];
}
