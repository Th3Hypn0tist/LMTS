from __future__ import annotations

from lmts.core.settings import MySQLSettings
from lmts.reporting import REPORT_FORMAT, REPORT_VERSION
from lmts.tools import mysql_reports, report_publish
from lmts.tools.report_profiles import ReportProfile


def _report() -> dict:
    return {
        'format': REPORT_FORMAT,
        'version': REPORT_VERSION,
        'report': {
            'id': 'report-1',
            'type': 'benchmark',
            'title': 'LMTS Benchmark Report',
            'created_at': '2026-09-18T10:00:00+00:00',
        },
        'source': {
            'type': 'lmts.run',
            'id': 'run-1',
        },
    }


def _mysql() -> MySQLSettings:
    return MySQLSettings(
        host='db.example',
        database='lmts',
        username='lmts',
        password='secret',
        publish_key='unused-directly',
    )


def test_mysql_report_target_dispatches_directly_without_php(monkeypatch) -> None:
    captured = {}

    def fake_write(mysql, report, *, verify=True):
        captured['mysql'] = mysql
        captured['report'] = report
        captured['verify'] = verify
        return 'report-1'

    monkeypatch.setattr(report_publish, 'write_report', fake_write)
    profile = ReportProfile(name='direct-db', kind='mysql', endpoint='', publish_key='')
    report = _report()

    report_id = report_publish.publish_report(report, profile, mysql=_mysql())

    assert report_id == 'report-1'
    assert captured['mysql'] == _mysql()
    assert captured['report'] == report
    assert captured['verify'] is True


def test_mysql_report_writer_uses_insert_only(monkeypatch) -> None:
    captured = {'queries': []}

    def fake_run(mysql, query):
        captured['mysql'] = mysql
        captured['queries'].append(query)
        return ''

    monkeypatch.setattr(mysql_reports, '_run', fake_run)
    report_id = mysql_reports.write_report(_mysql(), _report(), verify=False)

    assert report_id == 'report-1'
    assert captured['mysql'] == _mysql()
    report_insert = captured['queries'][0]
    assert 'INSERT INTO reports' in report_insert
    assert 'UPDATE' not in report_insert.upper()
    assert 'DELETE' not in report_insert.upper()
