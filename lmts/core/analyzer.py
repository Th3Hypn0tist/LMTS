from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .scoring import SubjectScorecard, build_subject_scorecard


@dataclass(frozen=True, slots=True)
class TargetComparison:
    baseline_id: str
    candidate_id: str
    baseline_score: float | None
    candidate_score: float | None
    score_delta_points: float | None
    test_deltas: dict[str, float]
    dimension_deltas: dict[str, float]
    coverage: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "baseline_id": self.baseline_id,
            "candidate_id": self.candidate_id,
            "baseline_score": self.baseline_score,
            "candidate_score": self.candidate_score,
            "score_delta_points": self.score_delta_points,
            "test_deltas": dict(self.test_deltas),
            "dimension_deltas": dict(self.dimension_deltas),
            "coverage": dict(self.coverage),
        }


def _scorecard(runs: list[dict[str, Any]], target_id: str) -> SubjectScorecard:
    selected = [run for run in runs if str(run.get("executor_id") or "") == target_id]
    if not selected:
        raise ValueError(f"no runs found for target: {target_id}")
    return build_subject_scorecard(selected)


def _delta_map(baseline: dict[str, float], candidate: dict[str, float]) -> dict[str, float]:
    keys = sorted(set(baseline) & set(candidate))
    return {key: candidate[key] - baseline[key] for key in keys}


def compare_targets(
    runs: list[dict[str, Any]],
    baseline_id: str,
    candidate_id: str,
) -> TargetComparison:
    if baseline_id == candidate_id:
        raise ValueError("baseline and candidate targets must differ")
    baseline = _scorecard(runs, baseline_id)
    candidate = _scorecard(runs, candidate_id)

    overall_delta = None
    if baseline.overall_percent is not None and candidate.overall_percent is not None:
        overall_delta = candidate.overall_percent - baseline.overall_percent

    return TargetComparison(
        baseline_id=baseline_id,
        candidate_id=candidate_id,
        baseline_score=baseline.overall_percent,
        candidate_score=candidate.overall_percent,
        score_delta_points=overall_delta,
        test_deltas=_delta_map(baseline.tests, candidate.tests),
        dimension_deltas=_delta_map(baseline.dimensions, candidate.dimensions),
        coverage={
            baseline_id: baseline.coverage,
            candidate_id: candidate.coverage,
        },
    )


def performance_summary(runs: list[dict[str, Any]], target_id: str) -> dict[str, Any]:
    selected = [run for run in runs if str(run.get("executor_id") or "") == target_id]
    generation_rates: list[float] = []
    prompt_rates: list[float] = []
    ttfts: list[float] = []
    totals: list[float] = []
    for run in selected:
        for response in run.get("responses") or []:
            if not isinstance(response, dict):
                continue
            performance = response.get("performance") if isinstance(response.get("performance"), dict) else {}
            timing = response.get("timing") if isinstance(response.get("timing"), dict) else {}
            for bucket, value in (
                (generation_rates, performance.get("generation_tokens_per_second")),
                (prompt_rates, performance.get("prompt_tokens_per_second")),
                (ttfts, timing.get("ttft_ms")),
                (totals, timing.get("total_ms")),
            ):
                if isinstance(value, (int, float)):
                    bucket.append(float(value))

    def average(values: list[float]) -> float | None:
        return None if not values else sum(values) / len(values)

    return {
        "target_id": target_id,
        "run_count": len(selected),
        "generation_tokens_per_second_mean": average(generation_rates),
        "prompt_tokens_per_second_mean": average(prompt_rates),
        "ttft_ms_mean": average(ttfts),
        "total_ms_mean": average(totals),
    }


def format_target_comparison(comparison: TargetComparison) -> tuple[str, ...]:
    lines = [
        f"Baseline : {comparison.baseline_id}",
        f"Candidate: {comparison.candidate_id}",
        f"Baseline score : {comparison.baseline_score if comparison.baseline_score is not None else '-'}",
        f"Candidate score: {comparison.candidate_score if comparison.candidate_score is not None else '-'}",
        f"Delta points   : {comparison.score_delta_points:+.2f}" if comparison.score_delta_points is not None else "Delta points   : -",
        "",
        "Capability / dimension delta",
    ]
    if comparison.dimension_deltas:
        for key, value in sorted(comparison.dimension_deltas.items(), key=lambda item: (-abs(item[1]), item[0])):
            lines.append(f"  {key:<32} {value:+.2f}")
    else:
        lines.append("  <no shared scored dimensions>")
    lines.extend(["", "Test delta"])
    if comparison.test_deltas:
        for key, value in sorted(comparison.test_deltas.items(), key=lambda item: (-abs(item[1]), item[0])):
            lines.append(f"  {key:<48} {value:+.2f}")
    else:
        lines.append("  <no shared scored tests>")
    return tuple(lines)
