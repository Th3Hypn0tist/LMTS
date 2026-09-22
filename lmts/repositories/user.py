from __future__ import annotations

import json
from dataclasses import dataclass

from lmts.core.settings import MySQLSettings
from lmts.tools.mysql_reports import _hex_text, _run


@dataclass(frozen=True, slots=True)
class UserActivityRecord:
    reports: int
    submissions: int
    result_records: int
    pass_records: int
    fail_records: int
    error_records: int
    cancelled_records: int
    unknown_records: int
    test_definitions: int
    test_versions: int
    telemetry_values: int
    models: int
    compositions: int
    systems: int
    compute_profiles: int
    hardware_nodes: int

    def to_dict(self) -> dict[str, int]:
        return {
            'reports': self.reports,
            'submissions': self.submissions,
            'result_records': self.result_records,
            'pass': self.pass_records,
            'fail': self.fail_records,
            'error': self.error_records,
            'cancelled': self.cancelled_records,
            'unknown': self.unknown_records,
            'test_definitions': self.test_definitions,
            'test_versions': self.test_versions,
            'telemetry_values': self.telemetry_values,
            'models': self.models,
            'compositions': self.compositions,
            'systems': self.systems,
            'compute_profiles': self.compute_profiles,
            'hardware_nodes': self.hardware_nodes,
        }


class UserRepository:
    """Read-only LMTS activity boundary keyed by an IAM user id."""

    def __init__(self, mysql: MySQLSettings) -> None:
        self.mysql = mysql

    def activity_for_user(self, user_id: str) -> UserActivityRecord:
        user_sql = _hex_text(user_id)
        query = f"""
SELECT JSON_OBJECT(
  'reports', (SELECT COUNT(DISTINCT report_id) FROM LMTS_report_record_index WHERE tester_user_id = {user_sql}),
  'submissions', (SELECT COUNT(*) FROM LMTS_report_submissions WHERE submitter_user_id = {user_sql}),
  'result_records', (SELECT COUNT(*) FROM LMTS_report_record_index WHERE tester_user_id = {user_sql}),
  'pass_records', (SELECT COUNT(*) FROM LMTS_report_record_index WHERE tester_user_id = {user_sql} AND outcome = 'pass'),
  'fail_records', (SELECT COUNT(*) FROM LMTS_report_record_index WHERE tester_user_id = {user_sql} AND outcome = 'fail'),
  'error_records', (SELECT COUNT(*) FROM LMTS_report_record_index WHERE tester_user_id = {user_sql} AND outcome = 'error'),
  'cancelled_records', (SELECT COUNT(*) FROM LMTS_report_record_index WHERE tester_user_id = {user_sql} AND outcome = 'cancelled'),
  'unknown_records', (
    SELECT COUNT(*) FROM LMTS_report_record_index
    WHERE tester_user_id = {user_sql}
      AND (outcome IS NULL OR outcome NOT IN ('pass','fail','error','cancelled'))
  ),
  'test_definitions', (
    SELECT COUNT(DISTINCT tv.test_definition_id)
    FROM LMTS_report_record_index rri
    JOIN LMTS_test_versions tv ON tv.test_version_id = rri.test_version_id
    WHERE rri.tester_user_id = {user_sql}
  ),
  'test_versions', (
    SELECT COUNT(DISTINCT test_version_id)
    FROM LMTS_report_record_index
    WHERE tester_user_id = {user_sql} AND test_version_id IS NOT NULL
  ),
  'telemetry_values', (SELECT COUNT(*) FROM LMTS_telemetry_values WHERE user_id = {user_sql}),
  'models', (
    SELECT COUNT(DISTINCT model_node_id)
    FROM LMTS_report_record_index
    WHERE tester_user_id = {user_sql} AND model_node_id IS NOT NULL
  ),
  'compositions', (
    SELECT COUNT(DISTINCT composition_id)
    FROM LMTS_report_record_index
    WHERE tester_user_id = {user_sql} AND composition_id IS NOT NULL
  ),
  'systems', (
    SELECT COUNT(DISTINCT system_id)
    FROM LMTS_report_record_index
    WHERE tester_user_id = {user_sql} AND system_id IS NOT NULL
  ),
  'compute_profiles', (
    SELECT COUNT(DISTINCT compute_profile_id)
    FROM LMTS_report_record_index
    WHERE tester_user_id = {user_sql} AND compute_profile_id IS NOT NULL
  ),
  'hardware_nodes', (
    SELECT COUNT(DISTINCT rrhi.hardware_id)
    FROM LMTS_report_record_hardware_index rrhi
    JOIN LMTS_report_record_index rri
      ON rri.report_id = rrhi.report_id
     AND rri.record_id = rrhi.record_id
    WHERE rri.tester_user_id = {user_sql}
  )
)
""".strip()
        raw = _run(self.mysql, query)
        lines = [line for line in raw.splitlines() if line.strip()]
        if not lines:
            raise RuntimeError('user activity query returned no data')
        payload = json.loads(lines[-1])
        if not isinstance(payload, dict):
            raise RuntimeError('user activity query did not return an object')
        names = (
            'reports', 'submissions', 'result_records',
            'pass_records', 'fail_records', 'error_records', 'cancelled_records', 'unknown_records',
            'test_definitions', 'test_versions', 'telemetry_values',
            'models', 'compositions', 'systems', 'compute_profiles', 'hardware_nodes',
        )
        values: dict[str, int] = {}
        for name in names:
            raw_value = payload.get(name)
            if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
                raise RuntimeError(f'invalid user activity count for {name}: {raw_value!r}')
            values[name] = int(raw_value)
        return UserActivityRecord(**values)
