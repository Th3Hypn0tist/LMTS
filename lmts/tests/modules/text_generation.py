from __future__ import annotations

from dataclasses import dataclass

from lmts.tests.base import TestContext, TestRequirements, TestResult


@dataclass(frozen=True, slots=True)
class TextGenerationTest:
    prompt: str = "Reply with exactly: LMTS_OK"
    expected_contains: str | None = "LMTS_OK"

    id: str = "core.text_generation"
    version: str = "1.0.0"
    requirements: TestRequirements = TestRequirements(text_generation=True)

    def run(self, context: TestContext) -> TestResult:
        response = context.generate(self.prompt)
        passed = None if self.expected_contains is None else self.expected_contains in response.text
        metrics = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "ttft_ms": response.timing.ttft_ms,
            "total_ms": response.timing.total_ms,
        }
        return TestResult(
            passed=passed,
            metrics=metrics,
            artifacts={"response_text": response.text},
        )
