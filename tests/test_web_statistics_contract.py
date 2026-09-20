from __future__ import annotations

import unittest

from lmts.tools.web_deploy import STATISTICS_APP_JS, STATS_PHP, WEBGUI_SOURCE_COMMIT, web_root_files


class WebStatisticsContractTests(unittest.TestCase):
    def test_package_contains_statistics_api_and_webgui_runtime(self) -> None:
        files = web_root_files()
        self.assertIn('api/stats.php', files)
        self.assertIn('WebGUI/webgui.js', files)
        self.assertIn('WebGUI/core/dom-structure.js', files)
        self.assertIn('WebGUI/core/theme.js', files)
        self.assertEqual(WEBGUI_SOURCE_COMMIT, '0dea8e711e0de84bf9da26826f0f40af4d4d8396')

    def test_statistics_api_reads_relational_projections(self) -> None:
        self.assertIn('FROM report_record_index rri', STATS_PHP)
        self.assertIn('FROM telemetry_values tv', STATS_PHP)
        self.assertIn('JOIN telemetry_types tt', STATS_PHP)
        self.assertNotIn("JSON_EXTRACT(report_json", STATS_PHP)
        self.assertNotIn("json_decode(report_json", STATS_PHP)

    def test_telemetry_is_not_implicitly_aggregated(self) -> None:
        self.assertNotIn('AVG(tv.value_number)', STATS_PHP)
        self.assertNotIn('SUM(tv.value_number)', STATS_PHP)
        self.assertIn("String(sample.canonical_key) + '\\u0000' + String(unit)", STATISTICS_APP_JS)
        self.assertIn('Every bar is one stored sample.', STATISTICS_APP_JS)

    def test_result_table_keeps_immutable_report_drilldown(self) -> None:
        self.assertIn("./api/report.php?id=", STATISTICS_APP_JS)
        self.assertIn('Open immutable report evidence', STATISTICS_APP_JS)


if __name__ == '__main__':
    unittest.main()
