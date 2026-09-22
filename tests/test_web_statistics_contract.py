from __future__ import annotations

import unittest
from pathlib import Path


PHP_ROOT = Path('php')
STATS_PHP = (PHP_ROOT / 'visualizer/api/stats.php').read_text(encoding='utf-8')
APP_JS = (PHP_ROOT / 'visualizer/app.js').read_text(encoding='utf-8')
STORAGE_PHP = (PHP_ROOT / 'storage/report.php').read_text(encoding='utf-8')


class WebStatisticsContractTests(unittest.TestCase):
    def test_statistics_api_reads_relational_projections(self) -> None:
        self.assertIn('FROM report_record_index rri', STATS_PHP)
        self.assertIn('FROM telemetry_values tv', STATS_PHP)
        self.assertIn('JOIN telemetry_types tt', STATS_PHP)
        self.assertNotIn("JSON_EXTRACT(report_json", STATS_PHP)
        self.assertNotIn("json_decode(report_json", STATS_PHP)

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
