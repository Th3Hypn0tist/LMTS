from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass

from lmts.tests.base import TestContext, TestRequirements, TestResult


@dataclass(frozen=True, slots=True)
class FreePromptConsistencyTest:
    """Run the same arbitrary prompt repeatedly against one model."""

    prompt: str
    repeats: int = 3
    id: str = "research.free_prompt_consistency"
    version: str = "1.0.0"
    requirements: TestRequirements = TestRequirements(text_generation=True)

    def run(self, context: TestContext) -> TestResult:
        if not self.prompt:
            raise ValueError("free prompt must not be empty")
        if self.repeats < 1:
            raise ValueError("repeats must be positive")

        outputs: list[str] = []
        timings: list[dict[str, object]] = []
        for trial in range(1, self.repeats + 1):
            context.checkpoint()
            response = context.generate(self.prompt)
            outputs.append(response.text)
            timings.append(
                {
                    "trial": trial,
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                    "ttft_ms": response.timing.ttft_ms,
                    "total_ms": response.timing.total_ms,
                }
            )

        counts = Counter(outputs)
        unique_outputs = len(counts)
        largest_group = max(counts.values()) if counts else 0
        prompt_digest = hashlib.sha256(self.prompt.encode("utf-8")).hexdigest()
        output_digests = [
            hashlib.sha256(output.encode("utf-8")).hexdigest() for output in outputs
        ]

        return TestResult(
            passed=None,
            metrics={
                "repeats": self.repeats,
                "unique_exact_outputs": unique_outputs,
                "largest_exact_group": largest_group,
                "exact_consistency_ratio": largest_group / self.repeats,
                "all_identical": unique_outputs == 1,
                "trials": timings,
            },
            artifacts={
                "prompt_sha256": prompt_digest,
                "response_texts": outputs,
                "response_sha256": output_digests,
            },
        )


# Transitional alias for any early callers.
FreePromptTest = FreePromptConsistencyTest
