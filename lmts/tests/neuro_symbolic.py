from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from lmts.core.scoring import ScoreDimension, TestScore
from lmts.tests.base import TestContext, TestRequirements, TestResult


@dataclass(frozen=True, slots=True)
class SealedChallenge:
    """Opaque challenge presented to the evaluated subject.

    LMTS receives only the public prompt and an opaque challenge id. Generator state,
    symbolic rules, oracle state and expected answers remain outside LMTS.
    """

    challenge_id: str
    prompt: str
    public_metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.challenge_id or self.challenge_id != self.challenge_id.strip():
            raise ValueError("sealed challenge id must be a non-empty canonical token")
        if not self.prompt or not self.prompt.strip():
            raise ValueError("sealed challenge prompt must be non-empty")


@dataclass(frozen=True, slots=True)
class SealedVerdict:
    passed: bool
    score: float
    public_evidence: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0.0 <= float(self.score) <= 100.0:
            raise ValueError("sealed verdict score must be between 0 and 100")


class SealedChallengeSource(Protocol):
    """External black-box challenge source. Implementation must not be exposed to the subject."""

    def issue(self) -> SealedChallenge: ...


class SealedChallengeScorer(Protocol):
    """External oracle boundary. LMTS supplies only challenge id and subject answer."""

    def score(self, challenge_id: str, answer: str) -> SealedVerdict: ...


@dataclass(frozen=True, slots=True)
class NeuroSymbolicSealedTest:
    """Black-box neuro-symbolic candidate test.

    Fairness invariant: this module never receives generator internals, symbolic ground
    truth, an expected answer, or oracle implementation details. Those remain behind
    the injected source/scorer boundaries.
    """

    source: SealedChallengeSource
    scorer: SealedChallengeScorer
    id: str = "neuro_symbolic.sealed_reasoning"
    version: str = "0.1.0-candidate"
    requirements: TestRequirements = TestRequirements(text_generation=True)

    def run(self, context: TestContext) -> TestResult:
        challenge = self.source.issue()
        response = context.generate(challenge.prompt)
        verdict = self.scorer.score(challenge.challenge_id, response.text)
        return TestResult(
            passed=verdict.passed,
            score=TestScore(
                (
                    ScoreDimension(
                        id="neuro_symbolic_reasoning",
                        score=float(verdict.score),
                        evidence=dict(verdict.public_evidence),
                    ),
                )
            ),
            metrics={
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "ttft_ms": response.timing.ttft_ms,
                "total_ms": response.timing.total_ms,
            },
            artifacts={
                "challenge_id": challenge.challenge_id,
                "challenge_public_metadata": dict(challenge.public_metadata),
                "response_text": response.text,
            },
        )
