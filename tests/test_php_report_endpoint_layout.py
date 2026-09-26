from pathlib import Path

from lmts.tools.web_deploy import php_package_files


def test_php_package_has_single_canonical_report_endpoint() -> None:
    files = php_package_files()
    assert 'report.php' in files
    assert 'storage/report.php' not in files
    assert 'storage/lib/report_contract.php' in files
    assert 'storage/contracts/LMTS_Benchmark_Report_Template_v1.1.schema.json' in files


def test_root_report_endpoint_uses_root_config_and_storage_contract() -> None:
    text = Path('php/report.php').read_text(encoding='utf-8')
    assert "require __DIR__ . '/config.php'" in text
    assert "require_once __DIR__ . '/storage/lib/report_contract.php'" in text
    assert "__DIR__ . '/storage/contracts/' . LMTS_REPORT_CONTRACT_FILE" in text
