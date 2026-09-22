from __future__ import annotations

import json
from dataclasses import dataclass

from lmts.core.settings import MySQLSettings
from lmts.tools.mysql_reports import _run


TEST_STAT_EXPRESSIONS: tuple[tuple[str, str], ...] = (
    ('test_definitions', '(SELECT COUNT(*) FROM LMTS_test_definitions)'),
    ('test_versions', '(SELECT COUNT(*) FROM LMTS_test_versions)'),
    ('telemetry_types', '(SELECT COUNT(*) FROM LMTS_telemetry_types)'),
    ('telemetry_bindings', '(SELECT COUNT(*) FROM LMTS_test_version_telemetry_types)'),
    ('reports', '(SELECT COUNT(*) FROM LMTS_reports)'),
    ('report_submissions', '(SELECT COUNT(*) FROM LMTS_report_submissions)'),
    ('result_records', '(SELECT COUNT(*) FROM LMTS_report_record_index)'),
    ('passed_records', "(SELECT COUNT(*) FROM LMTS_report_record_index WHERE outcome = 'pass')"),
    ('failed_records', "(SELECT COUNT(*) FROM LMTS_report_record_index WHERE outcome = 'fail')"),
    ('unresolved_records', "(SELECT COUNT(*) FROM LMTS_report_record_index WHERE outcome IS NULL OR outcome NOT IN ('pass','fail'))"),
    ('telemetry_values', '(SELECT COUNT(*) FROM LMTS_telemetry_values)'),
    ('hardware_references', '(SELECT COUNT(*) FROM LMTS_report_record_hardware_index)'),
    ('executed_test_definitions', (
        '(SELECT COUNT(DISTINCT tv.test_definition_id) '
        'FROM LMTS_report_record_index rri '
        'JOIN LMTS_test_versions tv ON tv.test_version_id = rri.test_version_id)'
    )),
    ('executed_test_versions', (
        '(SELECT COUNT(DISTINCT test_version_id) '
        'FROM LMTS_report_record_index WHERE test_version_id IS NOT NULL)'
    )),
    ('testers', (
        '(SELECT COUNT(DISTINCT tester_user_id) '
        'FROM LMTS_report_record_index WHERE tester_user_id IS NOT NULL)'
    )),
    ('tested_models', (
        '(SELECT COUNT(DISTINCT model_node_id) '
        'FROM LMTS_report_record_index WHERE model_node_id IS NOT NULL)'
    )),
    ('tested_compositions', (
        '(SELECT COUNT(DISTINCT composition_id) '
        'FROM LMTS_report_record_index WHERE composition_id IS NOT NULL)'
    )),
    ('tested_systems', (
        '(SELECT COUNT(DISTINCT system_id) '
        'FROM LMTS_report_record_index WHERE system_id IS NOT NULL)'
    )),
    ('tested_compute_profiles', (
        '(SELECT COUNT(DISTINCT compute_profile_id) '
        'FROM LMTS_report_record_index WHERE compute_profile_id IS NOT NULL)'
    )),
    ('tested_hardware_nodes', (
        '(SELECT COUNT(DISTINCT hardware_id) FROM LMTS_report_record_hardware_index)'
    )),
)


@dataclass(frozen=True, slots=True)
class TestStatsSnapshot:
    counts: dict[str, int]


class StatsRepository:
    """Read-only canonical database statistics boundary."""

    def __init__(self, mysql: MySQLSettings) -> None:
        self.mysql = mysql

    def test_stats(self) -> TestStatsSnapshot:
        pairs = ',\n  '.join(
            f"'{name}', {expression}"
            for name, expression in TEST_STAT_EXPRESSIONS
        )
        raw = _run(self.mysql, f'SELECT JSON_OBJECT(\n  {pairs}\n)').strip()
        if not raw:
            raise RuntimeError('test stats query returned no data')
        payload = json.loads(raw.splitlines()[-1])
        if not isinstance(payload, dict):
            raise RuntimeError('test stats query did not return an object')
        counts: dict[str, int] = {}
        for name, _ in TEST_STAT_EXPRESSIONS:
            value = payload.get(name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise RuntimeError(f'invalid test stats count for {name}: {value!r}')
            counts[name] = int(value)
        return TestStatsSnapshot(counts=counts)
