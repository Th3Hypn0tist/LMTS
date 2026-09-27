from __future__ import annotations

from lmts.core.model_explorer import (
    ModelCandidate,
    assess_candidate_fit,
    qualification_aggregate,
)


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
