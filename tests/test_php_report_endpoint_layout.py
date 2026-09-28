from pathlib import Path

from lmts.tools.web_deploy import php_package_files


def test_php_package_has_canonical_read_and_chunked_upload_endpoints() -> None:
    files = php_package_files()
    assert 'report.php' in files
    assert 'upload.php' in files
    assert 'storage/report.php' not in files
    assert 'storage/lib/report_contract.php' in files
    assert 'storage/lib/report_projection.php' in files
    assert 'storage/lib/report_store.php' in files
    assert 'storage/lib/report_upload.php' in files
    assert 'storage/contracts/LMTS_Benchmark_Report_Template_v1.1.schema.json' in files


def test_root_report_endpoint_is_read_only() -> None:
    text = Path('php/report.php').read_text(encoding='utf-8')
    assert "REQUEST_METHOD'] !== 'GET'" in text
    assert 'report publishing uses upload.php' in text
    assert "INSERT INTO LMTS_reports" not in text


def test_upload_endpoint_reuses_contract_store_and_projection() -> None:
    text = Path('php/upload.php').read_text(encoding='utf-8')
    assert "require_once __DIR__ . '/storage/lib/report_contract.php'" in text
    assert "require_once __DIR__ . '/storage/lib/report_projection.php'" in text
    assert "require_once __DIR__ . '/storage/lib/report_store.php'" in text
    assert "require_once __DIR__ . '/storage/lib/report_upload.php'" in text
    assert "__DIR__ . '/storage/contracts/' . LMTS_REPORT_CONTRACT_FILE" in text
    assert 'lmts_store_report($pdo, $report)' in text
    assert 'lmts_project_report($pdo, $report)' in text


def test_projection_projects_system_profile_hardware_and_memory() -> None:
    text = Path('php/storage/lib/report_projection.php').read_text(encoding='utf-8')
    assert 'LMTS_hardware_nodes' in text
    assert 'LMTS_system_resources' in text
    assert 'LMTS_system_memory_pools' in text
    assert 'LMTS_hardware_configurations' in text
    assert "system_context fingerprint does not match canonical hardware identity" in text
    assert "lmts_projection_project_system_profile($pdo, $systemId, $profile)" in text
    assert "capacity_bytes, properties_json" in text
    assert "lmts_projection_json($memory)" in text
    ensure_system = text[
        text.index('function lmts_projection_ensure_system(PDO $pdo, array $record): void'):
        text.index('function lmts_projection_assert_compute_profile')
    ]
    assert ensure_system.index('lmts_projection_ensure_system_identity') < ensure_system.index('lmts_projection_project_system_profile')



def test_projection_guards_numeric_record_index_metrics() -> None:
    text = Path('php/storage/lib/report_projection.php').read_text(encoding='utf-8')
    assert 'function lmts_projection_numeric_metric_value' in text
    assert "lmts_projection_numeric_metric_value($record, 'ttft')" in text
    assert "lmts_projection_numeric_metric_value($record, 'score_percent')" in text
