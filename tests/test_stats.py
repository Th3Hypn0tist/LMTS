from __future__ import annotations

import json

import lmts.repositories.stats as stats
from lmts.core.settings import MySQLSettings
from lmts.repositories.stats import StatsRepository
from lmts.services.stats import StatsService


def _mysql() -> MySQLSettings:
    return MySQLSettings(
        host='db.example',
        database='lmts',
        username='lmts',
        password='secret',
        publish_key='unused',
    )


def test_stats_repository_reads_all_declared_test_counts_in_one_query(monkeypatch) -> None:
    expected = {name: index for index, (name, _) in enumerate(stats.TEST_STAT_EXPRESSIONS, 1)}
    seen = {}

    def fake_run(mysql, query):
        seen['mysql'] = mysql
        seen['query'] = query
        return json.dumps(expected) + '\n'

    monkeypatch.setattr(stats, '_run', fake_run)
    snapshot = StatsRepository(_mysql()).test_stats()

    assert snapshot.counts == expected
    assert seen['query'].count('SELECT JSON_OBJECT') == 1
    assert 'FROM test_definitions' in seen['query']
    assert 'FROM test_versions' in seen['query']
    assert 'FROM telemetry_values' in seen['query']
    assert 'FROM report_record_index' in seen['query']
    assert 'FROM report_record_hardware_index' in seen['query']


def test_stats_service_caches_until_explicit_refresh() -> None:
    class FakeRepository:
        def __init__(self):
            self.calls = 0

        def test_stats(self):
            self.calls += 1
            return stats.TestStatsSnapshot({'reports': self.calls})

    repository = FakeRepository()
    service = StatsService(repository)  # type: ignore[arg-type]

    assert service.snapshot().counts['reports'] == 1
    assert service.snapshot().counts['reports'] == 1
    assert service.snapshot(refresh=True).counts['reports'] == 2
    assert repository.calls == 2
