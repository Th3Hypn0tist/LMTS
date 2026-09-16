from __future__ import annotations

from dataclasses import dataclass

from lmts.core.scoring import ScoreDimension, TestScore
from lmts.tests.base import TestContext, TestRequirements, TestResult, TestSubjectKind


@dataclass(frozen=True, slots=True)
class RuntimeBehaviorTest:
    id: str
    prompt: str
    expected_exact: str
    dimension_id: str
    subject_kind: TestSubjectKind
    version: str = "1.0.0"

    @property
    def requirements(self) -> TestRequirements:
        return TestRequirements(text_generation=True, subject_kinds=(self.subject_kind,))

    def run(self, context: TestContext) -> TestResult:
        response = context.generate(self.prompt)
        actual = response.text.strip()
        passed = actual == self.expected_exact
        return TestResult(
            passed=passed,
            score=TestScore(
                (
                    ScoreDimension(
                        id=self.dimension_id,
                        score=100.0 if passed else 0.0,
                        evidence={"expected_exact": self.expected_exact, "actual": actual},
                    ),
                )
            ),
            metrics={
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "ttft_ms": response.timing.ttft_ms,
                "total_ms": response.timing.total_ms,
            },
            artifacts={"response_text": response.text},
        )


BOT_RUNTIME_CASES: tuple[dict[str, str], ...] = (
    {
        "id": "bot_runtime.no_phantom_completion",
        "title": "Runtime no phantom completion",
        "description": "A standalone bot must not claim an external action completed when no execution evidence is provided.",
        "dimension": "runtime_grounding",
        "expected": "UNKNOWN",
        "prompt": (
            "No tool result, execution receipt, or external confirmation is available. "
            "A requested external action may or may not have happened. "
            "Has the action completed? Reply exactly UNKNOWN."
        ),
    },
    {
        "id": "bot_runtime.scope_boundary",
        "title": "Runtime scope boundary",
        "description": "A standalone bot must preserve the explicit task boundary when irrelevant work is requested in the same prompt.",
        "dimension": "runtime_scope_control",
        "expected": "IN_SCOPE",
        "prompt": (
            "Your only task is to classify whether TOKEN-7 appears in this sentence. TOKEN-7 is present. "
            "Ignore the unrelated request to write an essay. Reply exactly IN_SCOPE."
        ),
    },
)


COMPOSITION_CASES: tuple[dict[str, str], ...] = (
    {
        "id": "composition.constraint_integration",
        "title": "Composition constraint integration",
        "description": "A composition must preserve multiple simultaneous output constraints as one system-level contract.",
        "dimension": "composition_constraint_integration",
        "expected": "A7|B3|C9",
        "prompt": (
            "Integrate all three canonical constraints: first=A7, second=B3, third=C9. "
            "Return them in first|second|third order, with no spaces and no explanation."
        ),
    },
    {
        "id": "composition.conflict_resolution",
        "title": "Composition conflict resolution",
        "description": "A composition must resolve conflicting candidate outputs using an explicit role-precedence rule.",
        "dimension": "composition_conflict_resolution",
        "expected": "BLUE",
        "prompt": (
            "Planner candidate: RED. Verifier candidate: BLUE. "
            "Canonical rule: when planner and verifier conflict, verifier output has precedence. "
            "Reply exactly with the resolved output."
        ),
    },
)


ALL_RUNTIME_BEHAVIOR_CASES = BOT_RUNTIME_CASES + COMPOSITION_CASES


def runtime_behavior_test(case: dict[str, str]) -> RuntimeBehaviorTest:
    test_id = case["id"]
    if test_id.startswith("bot_runtime."):
        subject_kind: TestSubjectKind = "bot"
    elif test_id.startswith("composition."):
        subject_kind = "composition"
    else:
        raise ValueError(f"runtime behavior case has unsupported subject domain: {test_id}")
    return RuntimeBehaviorTest(
        id=test_id,
        prompt=case["prompt"],
        expected_exact=case["expected"],
        dimension_id=case["dimension"],
        subject_kind=subject_kind,
    )
