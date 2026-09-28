from __future__ import annotations

from lmts.core.model_explorer import (
    ModelCandidate,
    assess_candidate_fit,
    qualification_aggregate,
)
from lmts.services.model_explorer import ModelExplorerService


def _candidate(size_gb: int) -> ModelCandidate:
    return ModelCandidate(
        provider='ollama',
        model_ref=f'test:{size_gb}gb',
        family='test',
        size_bytes=size_gb * 1000 ** 3,
    )


def _profile() -> dict[str, object]:
    return {
        'memory': {'total_bytes': 64 * 1024 ** 3},
        'gpu': [{'vram_bytes': 8 * 1024 ** 3}],
    }


def test_model_explorer_blocks_candidate_above_memory_ceiling() -> None:
    fit = assess_candidate_fit(
        _candidate(80),
        _profile(),
        free_disk_bytes=500 * 1024 ** 3,
    )

    assert fit.status == 'too_large'
    assert fit.allowed_by_default is False
    assert 'memory ceiling' in fit.reason


def test_model_explorer_blocks_candidate_above_disk_ceiling() -> None:
    fit = assess_candidate_fit(
        _candidate(20),
        _profile(),
        free_disk_bytes=21 * 1000 ** 3,
    )

    assert fit.status == 'too_large'
    assert 'free disk' in fit.reason


def test_zero_variance_threshold_requires_consistent_passes() -> None:
    stable = qualification_aggregate([True] * 10)
    unstable = qualification_aggregate([True] * 9 + [False])
    stable_fail = qualification_aggregate([False] * 10)

    assert stable.sample_count == 10
    assert stable.pf_score == 100.0
    assert stable.variance == 0.0
    assert stable.accepts(0.0) is True

    assert unstable.status == 'pass'
    assert unstable.variance > 0.0
    assert unstable.accepts(0.0) is False

    assert stable_fail.status == 'fail'
    assert stable_fail.variance == 0.0
    assert stable_fail.accepts(0.0) is False


def test_memory_fit_does_not_sum_ram_and_vram() -> None:
    profile = {
        'memory': {'total_bytes': 16 * 1024 ** 3},
        'gpu': [{'vram_bytes': 12 * 1024 ** 3}],
    }
    fit = assess_candidate_fit(
        _candidate(20),
        profile,
        free_disk_bytes=500 * 1024 ** 3,
    )

    assert fit.status == 'too_large'
    assert fit.usable_memory_bytes == int(16 * 1024 ** 3 * 0.85)
    assert 'conservative profiled memory ceiling' in fit.reason


class _LifecycleExecutor:
    def __init__(self, *, stays_loaded: bool = False) -> None:
        self.loaded = True
        self.stays_loaded = stays_loaded

    def unload(self) -> None:
        if not self.stays_loaded:
            self.loaded = False

    def is_loaded(self) -> bool:
        return self.loaded


def test_explorer_requires_verified_candidate_unload() -> None:
    executor = _LifecycleExecutor()

    ModelExplorerService._unload_verified(executor)

    assert executor.loaded is False


def test_explorer_rejects_candidate_that_remains_loaded() -> None:
    executor = _LifecycleExecutor(stays_loaded=True)

    try:
        ModelExplorerService._unload_verified(executor)
    except RuntimeError as exc:
        assert 'remained loaded after unload' in str(exc)
    else:
        raise AssertionError('candidate cleanup accepted a still-loaded model')
