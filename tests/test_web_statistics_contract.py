from __future__ import annotations

import unittest
from pathlib import Path


PHP_ROOT = Path('php')
STATS_PHP = (PHP_ROOT / 'visualizer/api/stats.php').read_text(encoding='utf-8')
APP_JS = (PHP_ROOT / 'visualizer/app.js').read_text(encoding='utf-8')
STORAGE_PHP = (PHP_ROOT / 'storage/report.php').read_text(encoding='utf-8')


class WebStatisticsContractTests(unittest.TestCase):
    def test_statistics_api_reads_relational_projections(self) -> None:
        self.assertIn('FROM LMTS_report_record_index rri', STATS_PHP)
        self.assertIn('FROM LMTS_telemetry_values tv', STATS_PHP)
        self.assertIn('JOIN LMTS_telemetry_types tt', STATS_PHP)
        self.assertNotIn("JSON_EXTRACT(report_json", STATS_PHP)
        self.assertNotIn("json_decode(report_json", STATS_PHP)

    def test_variance_is_aggregated_from_pass_fail_samples(self) -> None:
        self.assertIn('FROM LMTS_variance_samples vs', STATS_PHP)
        self.assertIn('AS sample_count', STATS_PHP)
        self.assertIn('AS pf_score', STATS_PHP)
        self.assertIn('AS variance', STATS_PHP)
        self.assertIn("CASE WHEN grouped.pass_count > 0 THEN 'pass' ELSE 'fail' END AS status", STATS_PHP)

    def test_statistics_surface_exposes_only_canonical_pass_fail_outcomes(self) -> None:
        self.assertIn("outcome must be pass or fail", STATS_PHP)
        self.assertNotIn("AS error", STATS_PHP)
        self.assertNotIn("AS cancelled", STATS_PHP)
        self.assertNotIn("AS unknown", STATS_PHP)
        self.assertIn("WHERE outcome IN ('pass','fail')", STATS_PHP)

    def test_telemetry_is_not_implicitly_aggregated(self) -> None:
        self.assertNotIn('AVG(tv.value_number)', STATS_PHP)
        self.assertNotIn('SUM(tv.value_number)', STATS_PHP)
        self.assertIn("String(sample.canonical_key) + '\\u0000' + String(unit)", APP_JS)
        self.assertIn('Every bar is one stored sample.', APP_JS)

    def test_visualizer_keeps_immutable_report_drilldown(self) -> None:
        self.assertIn("./api/report.php?id=", APP_JS)
        self.assertIn('Open immutable report evidence', APP_JS)

    def test_storage_is_separate_from_visualizer(self) -> None:
        self.assertIn("$_SERVER['REQUEST_METHOD'] !== 'POST'", STORAGE_PHP)
        self.assertIn('X-LMTS-Key', STORAGE_PHP)
        self.assertNotIn("$_SERVER['REQUEST_METHOD'] !== 'POST'", (PHP_ROOT / 'visualizer/api/report.php').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()


def test_level1_configuration_overview_contract_is_canonical_and_unranked() -> None:
    assert "'configuration_overview' => $configurationOverview" in STATS_PHP
    assert "hc.configuration_id" in STATS_PHP
    assert "hc.label AS configuration_name" in STATS_PHP
    assert "COUNT(DISTINCT rri.target_ref) AS models_tested_count" in STATS_PHP
    assert "rri.target_kind = 'model'" in STATS_PHP
    assert "NULL AS leading_model" in STATS_PHP
    assert "NULL AS leading_model_pf_score" in STATS_PHP
    assert "NULL AS leading_model_time_ms" in STATS_PHP
    assert "'ranking_contract_unresolved' AS ranking_status" in STATS_PHP


def test_level2_configuration_matrix_is_exact_until_hardware_ordering_exists() -> None:
    assert "'configuration_matrix' => [" in STATS_PHP
    assert "'evidence_scope' => $selectedConfigurationId === null ? null : 'exact'" in STATS_PHP
    assert "'hardware_ceiling_status' => $selectedConfigurationId === null" in STATS_PHP
    assert "'ordering_contract_unresolved'" in STATS_PHP
    assert "'lighter_configuration_ids' => []" in STATS_PHP
    assert "JSON_ARRAYAGG(rri.duration_ms) AS total_time_samples_json" in STATS_PHP
    assert "WHERE s.configuration_id = ?" in STATS_PHP
    assert "AND rri.target_kind = 'model'" in STATS_PHP
