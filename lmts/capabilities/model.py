from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class SweepConfig:
    low: float
    high: float
    tolerance: float
    repetitions: int = 1
    boundary_repetitions: int = 3
    required_success_rate: float = 1.0
    max_steps: int = 16

    def validate(self) -> None:
        if self.low < 0 or self.high <= self.low or self.tolerance <= 0:
            raise ValueError("invalid sweep bounds")
        if self.repetitions < 1 or self.boundary_repetitions < self.repetitions:
            raise ValueError("invalid repetitions")
        if not 0 < self.required_success_rate <= 1 or self.max_steps < 1:
            raise ValueError("invalid sweep policy")


@dataclass(slots=True)
class SweepPoint:
    complexity: float
    run_ids: list[str] = field(default_factory=list)
    passed: int = 0
    failed: int = 0

    @property
    def total(self) -> int:
        return self.passed + self.failed

    @property
    def success_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    def qualifies(self, required: float) -> bool:
        return self.total > 0 and self.success_rate >= required
