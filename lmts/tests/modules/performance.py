from __future__ import annotations

import statistics
from dataclasses import dataclass

from lmts.tests.base import TestContext, TestRequirements, TestResult


def _series(values: list[float]) -> dict[str, float | int | list[float]]:
    if not values:
        return {"count": 0, "samples": []}
    median = statistics.median(values)
    return {
        "count": len(values),
        "samples": values,
        "minimum": min(values),
        "maximum": max(values),
        "median": median,
        "mean": statistics.fmean(values),
        "stdev": statistics.pstdev(values) if len(values) > 1 else 0.0,
    }


@dataclass(frozen=True, slots=True)
class ColdWarmPerformanceTest:
    prompt: str = "Reply exactly PERF_OK"
    warm_repeats: int = 5
    id: str = "performance.cold_warm"
    version: str = "1.0.0"
    requirements: TestRequirements = TestRequirements(text_generation=True)

    def run(self, context: TestContext) -> TestResult:
        if self.warm_repeats < 1:
            raise ValueError("warm_repeats must be positive")

        responses = [context.generate(self.prompt)]
        for _ in range(self.warm_repeats):
            responses.append(context.generate(self.prompt))

        cold = responses[0]
        warm = responses[1:]
        warm_total = [float(item.timing.total_ms) for item in warm if item.timing.total_ms is not None]
        warm_ttft = [float(item.timing.ttft_ms) for item in warm if item.timing.ttft_ms is not None]
        warm_generation_rate = [
            float(item.performance.generation_tokens_per_second)
            for item in warm
            if item.performance.generation_tokens_per_second is not None
        ]
        warm_prompt_rate = [
            float(item.performance.prompt_tokens_per_second)
            for item in warm
            if item.performance.prompt_tokens_per_second is not None
        ]

        return TestResult(
            passed=None,
            metrics={
                "cold": {
                    "total_ms": cold.timing.total_ms,
                    "ttft_ms": cold.timing.ttft_ms,
                    "load_ms": cold.timing.load_ms,
                    "prompt_eval_ms": cold.timing.prompt_eval_ms,
                    "generation_ms": cold.timing.generation_ms,
                    "prompt_tokens_per_second": cold.performance.prompt_tokens_per_second,
                    "generation_tokens_per_second": cold.performance.generation_tokens_per_second,
                },
                "warm_total_ms": _series(warm_total),
                "warm_ttft_ms": _series(warm_ttft),
                "warm_generation_tokens_per_second": _series(warm_generation_rate),
                "warm_prompt_tokens_per_second": _series(warm_prompt_rate),
            },
            artifacts={
                "response_texts": [item.text for item in responses],
            },
        )


@dataclass(frozen=True, slots=True)
class RepeatVarianceTest:
    prompt: str = "Reply exactly VAR_OK"
    repeats: int = 10
    id: str = "performance.repeat_variance"
    version: str = "1.0.0"
    requirements: TestRequirements = TestRequirements(text_generation=True)

    def run(self, context: TestContext) -> TestResult:
        if self.repeats < 2:
            raise ValueError("repeats must be at least 2")

        responses = [context.generate(self.prompt) for _ in range(self.repeats)]
        totals = [float(item.timing.total_ms) for item in responses if item.timing.total_ms is not None]
        ttfts = [float(item.timing.ttft_ms) for item in responses if item.timing.ttft_ms is not None]
        generation_rates = [
            float(item.performance.generation_tokens_per_second)
            for item in responses
            if item.performance.generation_tokens_per_second is not None
        ]
        return TestResult(
            passed=None,
            metrics={
                "total_ms": _series(totals),
                "ttft_ms": _series(ttfts),
                "generation_tokens_per_second": _series(generation_rates),
                "exact_output_variants": len({item.text for item in responses}),
            },
            artifacts={"response_texts": [item.text for item in responses]},
        )
