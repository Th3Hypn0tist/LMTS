from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


DEFAULT_EXPLORER_REPEATS = 10
DEFAULT_VARIANCE_THRESHOLD = 0.0
DEFAULT_RUNTIME_OVERHEAD_RATIO = 0.15
DEFAULT_MEMORY_RESERVE_RATIO = 0.15
DEFAULT_DISK_RESERVE_BYTES = 5 * 1024 ** 3

FitStatus = Literal['fit', 'marginal', 'too_large']


@dataclass(frozen=True, slots=True)
class ModelCandidate:
    provider: str
    model_ref: str
    family: str
    size_bytes: int | None
    parameter_size: str | None = None
    quantization: str | None = None
    context_length: int | None = None
    digest: str | None = None
    source_url: str | None = None


@dataclass(frozen=True, slots=True)
class FitAssessment:
    status: FitStatus
    size_bytes: int | None
    estimated_runtime_bytes: int | None
    usable_memory_bytes: int | None
    free_disk_bytes: int | None
    reason: str

    @property
    def allowed_by_default(self) -> bool:
        return self.status != 'too_large'


@dataclass(frozen=True, slots=True)
class QualificationAggregate:
    sample_count: int
    pass_count: int
    fail_count: int
    pf_score: float
    variance: float
    status: Literal['pass', 'fail']

    def accepts(self, variance_threshold: float = DEFAULT_VARIANCE_THRESHOLD) -> bool:
        if variance_threshold < 0:
            raise ValueError('variance threshold must be non-negative')
        return self.status == 'pass' and self.variance <= variance_threshold


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


def usable_memory_bytes(profile: dict[str, object]) -> int | None:
    memory = profile.get('memory') if isinstance(profile.get('memory'), dict) else {}
    system_bytes = _positive_int(memory.get('total_bytes'))
    gpus = profile.get('gpu') if isinstance(profile.get('gpu'), list) else []

    dedicated_vram = 0
    for gpu in gpus:
        if not isinstance(gpu, dict):
            continue
        value = _positive_int(gpu.get('vram_bytes'))
        if value is not None:
            dedicated_vram += value

    if system_bytes is None and dedicated_vram <= 0:
        return None
    return (system_bytes or 0) + dedicated_vram


def assess_candidate_fit(
    candidate: ModelCandidate,
    profile: dict[str, object],
    *,
    free_disk_bytes: int | None,
    runtime_overhead_ratio: float = DEFAULT_RUNTIME_OVERHEAD_RATIO,
    memory_reserve_ratio: float = DEFAULT_MEMORY_RESERVE_RATIO,
    disk_reserve_bytes: int = DEFAULT_DISK_RESERVE_BYTES,
) -> FitAssessment:
    if runtime_overhead_ratio < 0:
        raise ValueError('runtime overhead ratio must be non-negative')
    if not 0 <= memory_reserve_ratio < 1:
        raise ValueError('memory reserve ratio must be in [0, 1)')
    if disk_reserve_bytes < 0:
        raise ValueError('disk reserve must be non-negative')

    size = _positive_int(candidate.size_bytes)
    capacity = usable_memory_bytes(profile)
    usable = None if capacity is None else int(capacity * (1.0 - memory_reserve_ratio))
    runtime_estimate = None if size is None else int(size * (1.0 + runtime_overhead_ratio))

    if size is not None and free_disk_bytes is not None:
        available_disk = max(0, free_disk_bytes - disk_reserve_bytes)
        if size > available_disk:
            return FitAssessment(
                status='too_large',
                size_bytes=size,
                estimated_runtime_bytes=runtime_estimate,
                usable_memory_bytes=usable,
                free_disk_bytes=free_disk_bytes,
                reason='artifact exceeds free disk after reserve',
            )

    if runtime_estimate is not None and usable is not None:
        if runtime_estimate > usable:
            return FitAssessment(
                status='too_large',
                size_bytes=size,
                estimated_runtime_bytes=runtime_estimate,
                usable_memory_bytes=usable,
                free_disk_bytes=free_disk_bytes,
                reason='estimated runtime memory exceeds profiled memory ceiling',
            )
        if runtime_estimate > int(usable * 0.8):
            return FitAssessment(
                status='marginal',
                size_bytes=size,
                estimated_runtime_bytes=runtime_estimate,
                usable_memory_bytes=usable,
                free_disk_bytes=free_disk_bytes,
                reason='estimated runtime memory leaves less than 20% headroom',
            )
        return FitAssessment(
            status='fit',
            size_bytes=size,
            estimated_runtime_bytes=runtime_estimate,
            usable_memory_bytes=usable,
            free_disk_bytes=free_disk_bytes,
            reason='artifact fits disk and profiled memory ceiling',
        )

    return FitAssessment(
        status='marginal',
        size_bytes=size,
        estimated_runtime_bytes=runtime_estimate,
        usable_memory_bytes=usable,
        free_disk_bytes=free_disk_bytes,
        reason='insufficient catalog or hardware metadata for a hard fit decision',
    )


def qualification_aggregate(samples: list[bool] | tuple[bool, ...]) -> QualificationAggregate:
    if not samples:
        raise ValueError('qualification requires at least one PASS/FAIL sample')
    if any(not isinstance(item, bool) for item in samples):
        raise ValueError('qualification samples must be PASS/FAIL booleans')
    count = len(samples)
    passes = sum(1 for item in samples if item)
    fails = count - passes
    probability = passes / count
    return QualificationAggregate(
        sample_count=count,
        pass_count=passes,
        fail_count=fails,
        pf_score=probability * 100.0,
        variance=probability * (1.0 - probability),
        status='pass' if passes >= 1 else 'fail',
    )
