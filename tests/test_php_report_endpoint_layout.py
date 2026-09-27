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
