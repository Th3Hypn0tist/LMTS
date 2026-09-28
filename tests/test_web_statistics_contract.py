from __future__ import annotations

import unittest
from pathlib import Path


PHP_ROOT = Path('php')
STATS_PHP = (PHP_ROOT / 'visualizer/api/stats.php').read_text(encoding='utf-8')
APP_JS = (PHP_ROOT / 'visualizer/app.js').read_text(encoding='utf-8')
REPORT_PHP = (PHP_ROOT / 'report.php').read_text(encoding='utf-8')
UPLOAD_PHP = (PHP_ROOT / 'upload.php').read_text(encoding='utf-8')
VISUALIZER_REPORT_PHP = (PHP_ROOT / 'visualizer/api/report.php').read_text(encoding='utf-8')


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
        self.assertIn("$_SERVER['REQUEST_METHOD'] !== 'GET'", REPORT_PHP)
        self.assertIn('report publishing uses upload.php', REPORT_PHP)
        self.assertIn("$_SERVER['HTTP_X_LMTS_KEY']", UPLOAD_PHP)
        self.assertIn("$_SERVER['REQUEST_METHOD'] === 'POST' && $action === 'init'", UPLOAD_PHP)
        self.assertIn("$_SERVER['REQUEST_METHOD'] !== 'GET'", VISUALIZER_REPORT_PHP)
        self.assertNotIn('HTTP_X_LMTS_KEY', VISUALIZER_REPORT_PHP)


if __name__ == '__main__':
    unittest.main()


def test_level1_configuration_overview_contract_ranks_exact_pf_then_coverage() -> None:
    assert "'configuration_overview' => $configurationOverview" in STATS_PHP
    assert "FROM LMTS_variance_samples vs" in STATS_PHP
    assert "JOIN LMTS_hardware_configurations hc ON hc.configuration_id = vs.configuration_id" in STATS_PHP
    assert "s.configuration_id = vs.configuration_id" in STATS_PHP
    assert "100.0 * SUM(CASE WHEN vs.outcome = 'pass' THEN 1 ELSE 0 END) / COUNT(*)" in STATS_PHP
    assert "array_sum($perTestScores) / count($perTestScores)" in STATS_PHP
    assert "100.0 * $testedCount / $testUniverseCount" in STATS_PHP
    assert "$right['pf_score'] <=> $left['pf_score']" in STATS_PHP
    assert "$right['coverage'] <=> $left['coverage']" in STATS_PHP
    assert "$sameRank ? $previousRank : $index + 1" in STATS_PHP
    assert "'ranking_status' => 'ranked_exact_pf_coverage'" in STATS_PHP
    assert "'ranking_contract' => 'exact_hardware:pf_desc:coverage_desc:shared_equal'" in STATS_PHP
    assert "Exact hardware evidence · P/F ↓ · coverage ↓ · equal values share rank" in APP_JS
    assert "Shared #1" in APP_JS




def test_level1_exposes_use_case_telemetry_sort_controls() -> None:
    assert "'level1_metric_options' => $level1MetricOptions" in STATS_PHP
    assert "FROM LMTS_telemetry_values tv" in STATS_PHP
    assert "JSON_ARRAYAGG(tv.value_number) AS samples_json" in STATS_PHP
    assert "'telemetry' => $configurationTelemetry" in STATS_PHP
    assert "function level1ViewState(metricOptions)" in APP_JS
    assert "l1_metric" in APP_JS
    assert "l1_agg" in APP_JS
    assert "l1_dir" in APP_JS
    assert "Default ranking is P/F then coverage." in APP_JS
    assert "item.value === 'pf_score' || item.value === 'coverage'" in APP_JS
    assert "High first" in APP_JS
    assert "Low first" in APP_JS
    assert "view.metric !== 'pf_score' || Number(model.coverage) === firstCoverage" in APP_JS


def test_level2_configuration_matrix_applies_canonical_hardware_ceiling() -> None:
    assert "'configuration_matrix' => [" in STATS_PHP
    assert "'evidence_scope' => $selectedConfigurationId === null ? null : 'exact_plus_compatibility'" in STATS_PHP
    assert "'hardware_ceiling_status' => $hardwareCeilingStatus" in STATS_PHP
    assert "'lighter_configuration_ids' => $lighterConfigurationIds" in STATS_PHP
    assert "stats_hardware_order_relation($candidateOrder, $selectedOrder)" in STATS_PHP
    assert "$relation['comparable'] && $relation['lower_or_equal'] && $relation['strict']" in STATS_PHP
    assert "JSON_ARRAYAGG(rri.duration_ms) AS total_time_samples_json" in STATS_PHP


def test_level2_compatibility_uses_variance_evidence_and_never_propagates_performance() -> None:
    assert "FROM LMTS_variance_samples vs" in STATS_PHP
    assert "'inferred_lighter_pass'" in STATS_PHP
    assert "'lower_fail_only'" in STATS_PHP
    assert "'performance_scope' => 'none'" in STATS_PHP
    assert "'pf_score' => null" in STATS_PHP
    assert "'total_time_samples_ms' => []" in STATS_PHP
    assert "lighter FAIL does not propagate" in APP_JS
    assert "performance unavailable" in APP_JS


def test_level2_supports_metric_aggregation_and_axis_controls() -> None:
    assert "JSON_ARRAYAGG(rri.ttft_ms) AS ttft_samples_json" in STATS_PHP
    assert "function level2ViewState()" in APP_JS
    assert "l2_metric" in APP_JS
    assert "l2_agg" in APP_JS
    assert "l2_axes" in APP_JS
    assert "option('total_time', 'Total time'" in APP_JS
    assert "option('ttft', 'TTFT'" in APP_JS
    assert "option('pf_score', 'P/F score'" in APP_JS
    assert "option('med', 'Med'" in APP_JS
    assert "option('avg', 'Avg'" in APP_JS
    assert "option('model_test', 'Models × tests'" in APP_JS
    assert "option('test_model', 'Tests × models'" in APP_JS


def test_level2_inferred_pass_never_gets_measured_performance() -> None:
    assert "if (text(cell.evidence_scope, 'unknown') === 'inferred_lighter_pass') return null;" in APP_JS
    assert "cell.performance_scope !== 'exact'" in APP_JS
    assert "performance unavailable" in APP_JS


def test_level3_model_drilldown_is_tests_by_exact_hardware() -> None:
    assert "'model_drilldown' => $modelDrilldown" in STATS_PHP
    assert "$selectedTargetKind === 'model'" in STATS_PHP
    assert "GROUP BY s.configuration_id, hc.label, hc.order_status, rri.target_ref" in STATS_PHP
    assert "FROM LMTS_variance_samples vs" in STATS_PHP
    assert "FROM LMTS_telemetry_values tv" in STATS_PHP
    assert "function modelDrilldownTable(drilldown, view, payload)" in APP_JS
    assert "Test / hardware" in APP_JS
    assert "Axes are fixed." in APP_JS


def test_level3_metric_options_include_timing_pf_variance_and_numeric_telemetry() -> None:
    assert "['value' => 'total_time', 'label' => 'Total time (ms)']" in STATS_PHP
    assert "['value' => 'ttft', 'label' => 'TTFT (ms)']" in STATS_PHP
    assert "['value' => 'pf_score', 'label' => 'P/F score']" in STATS_PHP
    assert "['value' => 'variance', 'label' => 'Variance']" in STATS_PHP
    assert "'value' => 'telemetry:' . $typeId" in STATS_PHP
    assert "view.metric.startsWith('telemetry:')" in APP_JS
    assert "l3_metric" in APP_JS
    assert "l3_agg" in APP_JS
