from __future__ import annotations

import hashlib
from dataclasses import dataclass

from lmts.tests.base import TestContext, TestRequirements, TestResult


@dataclass(frozen=True, slots=True)
class FreePromptTest:
    """One persisted trial of an arbitrary prompt.

    Repetition and cross-model comparison are orchestrated outside this module so
    every trial remains an ordinary canonical LMTS run.
    """

    prompt: str
    trial: int = 1
    id: str = "research.free_prompt"
    version: str = "1.0.0"
    requirements: TestRequirements = TestRequirements(text_generation=True)

    def run(self, context: TestContext) -> TestResult:
        if not self.prompt:
            raise ValueError("free prompt must not be empty")
        response = context.generate(self.prompt)
        digest = hashlib.sha256(self.prompt.encode("utf-8")).hexdigest()
        return TestResult(
            passed=True,
            metrics={
                "trial": self.trial,
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "ttft_ms": response.timing.ttft_ms,
                "total_ms": response.timing.total_ms,
            },
            artifacts={
                "prompt_sha256": digest,
                "trial": self.trial,
                "response_text": response.text,
            },
        )
