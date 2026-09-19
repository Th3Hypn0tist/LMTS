from __future__ import annotations

from lmts.repositories.stats import StatsRepository, TestStatsSnapshot


class StatsService:
    """Cached database-backed statistics for human-facing views."""

    def __init__(self, repository: StatsRepository) -> None:
        self.repository = repository
        self._snapshot: TestStatsSnapshot | None = None

    def snapshot(self, *, refresh: bool = False) -> TestStatsSnapshot:
        if refresh or self._snapshot is None:
            self._snapshot = self.repository.test_stats()
        return self._snapshot

    def clear(self) -> None:
        self._snapshot = None
