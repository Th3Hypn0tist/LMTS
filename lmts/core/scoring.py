from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ScoreDimension:
    id: str
    score: float
    maximum: float = 100.0
    weight: float = 1.0
    evidence: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id or self.id.isspace():
            raise ValueError("score dimension id must be non-empty")
        if self.maximum <= 0:
            raise ValueError("score dimension maximum must be positive")
        if self.weight < 0:
            raise ValueError("score dimension weight must not be negative")
        if self.score < 0 or self.score > self.maximum:
            raise ValueError("score must be within 0..maximum")

    @property
    def normalized(self) -> float:
        return self.score / self.maximum

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["normalized"] = self.normalized
        return value


@dataclass(frozen=True, slots=True)
class TestScore:
    dimensions: tuple[ScoreDimension, ...]

    def __post_init__(self) -> None:
        ids = [dimension.id for dimension in self.dimensions]
        if len(ids) != len(set(ids)):
            raise ValueError("score dimension ids must be unique")

    @property
    def normalized(self) -> float | None:
        weighted = [(dimension.normalized, dimension.weight) for dimension in self.dimensions if dimension.weight > 0]
        total_weight = sum(weight for _, weight in weighted)
        if total_weight <= 0:
            return None
        return sum(value * weight for value, weight in weighted) / total_weight

    @property
    def percent(self) -> float | None:
        value = self.normalized
        return None if value is None else value * 100.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimensions": [dimension.to_dict() for dimension in self.dimensions],
            "normalized": self.normalized,
            "percent": self.percent,
        }
