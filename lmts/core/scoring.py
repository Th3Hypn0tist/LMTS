from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable


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


@dataclass(frozen=True, slots=True)
class SubjectScorecard:
    subject: dict[str, Any]
    run_count: int
    scored_run_count: int
    overall_percent: float | None
    coverage: float
    tests: dict[str, float]
    dimensions: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject": dict(self.subject),
            "run_count": self.run_count,
            "scored_run_count": self.scored_run_count,
            "overall_percent": self.overall_percent,
            "coverage": self.coverage,
            "tests": dict(self.tests),
            "dimensions": dict(self.dimensions),
        }


def build_subject_scorecard(runs: Iterable[dict[str, Any]]) -> SubjectScorecard:
    records = [dict(run) for run in runs]
    if not records:
        raise ValueError("subject scorecard requires at least one run")

    subjects = [run.get("evaluation_subject") for run in records]
    if not all(isinstance(subject, dict) for subject in subjects):
        raise ValueError("all runs must contain an evaluation subject")
    fingerprints = {str(subject.get("fingerprint") or "") for subject in subjects if isinstance(subject, dict)}
    if "" in fingerprints or len(fingerprints) != 1:
        raise ValueError("all runs in one scorecard must share one subject fingerprint")

    completed = [run for run in records if run.get("status") == "completed"]
    test_values: dict[str, list[float]] = defaultdict(list)
    dimension_values: dict[str, list[tuple[float, float]]] = defaultdict(list)
    scored_run_percents: list[float] = []

    for run in completed:
        score = run.get("score")
        if not isinstance(score, dict):
            continue
        percent = score.get("percent")
        if not isinstance(percent, (int, float)):
            continue
        percent_value = float(percent)
        if percent_value < 0 or percent_value > 100:
            raise ValueError("run score percent must be within 0..100")
        scored_run_percents.append(percent_value)
        test_values[str(run.get("test_ref") or "unknown")].append(percent_value)

        dimensions = score.get("dimensions")
        if not isinstance(dimensions, list):
            continue
        for dimension in dimensions:
            if not isinstance(dimension, dict):
                continue
            dimension_id = dimension.get("id")
            normalized = dimension.get("normalized")
            weight = dimension.get("weight", 1.0)
            if not isinstance(dimension_id, str) or not dimension_id:
                continue
            if not isinstance(normalized, (int, float)) or not isinstance(weight, (int, float)):
                continue
            if float(weight) <= 0:
                continue
            dimension_values[dimension_id].append((float(normalized), float(weight)))

    tests = {
        test_ref: sum(values) / len(values)
        for test_ref, values in sorted(test_values.items())
    }
    dimensions: dict[str, float] = {}
    for dimension_id, values in sorted(dimension_values.items()):
        total_weight = sum(weight for _, weight in values)
        dimensions[dimension_id] = (
            sum(normalized * weight for normalized, weight in values) / total_weight * 100.0
        )

    scored_count = len(scored_run_percents)
    completed_count = len(completed)
    return SubjectScorecard(
        subject=dict(subjects[0]),
        run_count=len(records),
        scored_run_count=scored_count,
        overall_percent=(
            sum(scored_run_percents) / scored_count if scored_count else None
        ),
        coverage=(scored_count / completed_count if completed_count else 0.0),
        tests=tests,
        dimensions=dimensions,
    )
