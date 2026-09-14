from __future__ import annotations

from dataclasses import dataclass

from lmts.core.scoring import ScoreDimension, TestScore
from lmts.tests.base import TestContext, TestRequirements, TestResult


@dataclass(frozen=True, slots=True)
class CapabilityTextTest:
    id: str
    prompt: str
    expected_exact: str
    dimension_id: str
    version: str = "1.0.0"
    requirements: TestRequirements = TestRequirements(text_generation=True)

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


REASONING_CASES: tuple[dict[str, str], ...] = (
    {
        "id": "reasoning.carwash_transport",
        "title": "Carwash transport",
        "description": "Preserve the actual task goal: the car itself must reach the car wash.",
        "dimension": "goal_context_reasoning",
        "expected": "DRIVE",
        "prompt": "I'm taking car to carwash. It is on the other side of the road. Should I drive or walk? Reply exactly DRIVE or WALK.",
    },
    {
        "id": "reasoning.arithmetic_chain",
        "title": "Arithmetic chain",
        "description": "Carry a short deterministic arithmetic chain without losing intermediate state.",
        "dimension": "arithmetic_reasoning",
        "expected": "42",
        "prompt": "Start with 8. Multiply by 5, add 6, then subtract 4. Reply with exactly the final integer and nothing else.",
    },
    {
        "id": "reasoning.symbolic_logic",
        "title": "Symbolic logic",
        "description": "Resolve a basic implication chain exactly.",
        "dimension": "symbolic_logic",
        "expected": "TRUE",
        "prompt": "Given: A is true. If A then B. If B then C. Is C necessarily true? Reply exactly TRUE or FALSE.",
    },
    {
        "id": "reasoning.ordering",
        "title": "Constraint ordering",
        "description": "Solve a deterministic ordering constraint.",
        "dimension": "ordering_reasoning",
        "expected": "B,A,C",
        "prompt": "Three tasks A, B, C must be ordered. B must occur before A. A must occur before C. Reply exactly with the only valid order using commas and no spaces.",
    },
    {
        "id": "reasoning.dependency_chain",
        "title": "Dependency chain",
        "description": "Identify the first executable item in a dependency graph.",
        "dimension": "dependency_reasoning",
        "expected": "D",
        "prompt": "Dependencies: A requires B and C. B requires D. C requires D. D has no dependencies. Which item must be executable first? Reply exactly with one letter.",
    },
    {
        "id": "reasoning.impossible_constraints",
        "title": "Impossible constraints",
        "description": "Recognize an unsatisfiable constraint set.",
        "dimension": "constraint_reasoning",
        "expected": "IMPOSSIBLE",
        "prompt": "Choose one integer x such that x > 10 and x < 5 simultaneously. If no such integer exists, reply exactly IMPOSSIBLE.",
    },
)


CONTEXT_CASES: tuple[dict[str, str], ...] = (
    {
        "id": "context.single_needle",
        "title": "Single needle retrieval",
        "description": "Retrieve one explicit fact from distracting context.",
        "dimension": "context_retrieval",
        "expected": "KAPPA-731",
        "prompt": "Context: red blue green chair cloud river. Important token: KAPPA-731. More distractors: lamp stone cable window. Reply exactly with the important token.",
    },
    {
        "id": "context.multi_needle",
        "title": "Multiple needle retrieval",
        "description": "Retrieve and preserve the order of multiple explicit facts.",
        "dimension": "multi_context_retrieval",
        "expected": "A17|B42|C09",
        "prompt": "Store these values: first=A17. Distractor text follows. second=B42. More unrelated text. third=C09. Reply exactly first|second|third using the stored values.",
    },
    {
        "id": "context.early_retention",
        "title": "Early context retention",
        "description": "Retain an instruction placed before a distractor block.",
        "dimension": "early_context_retention",
        "expected": "EARLY-OK",
        "prompt": "Remember this final answer: EARLY-OK. Now read unrelated material: alpha beta gamma delta epsilon zeta eta theta. What was the required final answer? Reply exactly with it.",
    },
    {
        "id": "context.conflict_priority",
        "title": "Context conflict priority",
        "description": "Keep the explicitly canonical value when later context is marked non-canonical.",
        "dimension": "context_conflict_resolution",
        "expected": "PORT-8000",
        "prompt": "Canonical value: PORT-8000. Later note, explicitly non-canonical: PORT-9000. Use only the canonical value and reply exactly with it.",
    },
    {
        "id": "context.irrelevant_resistance",
        "title": "Irrelevant context resistance",
        "description": "Ignore unrelated detail when answering a simple grounded question.",
        "dimension": "distractor_resistance",
        "expected": "HELSINKI",
        "prompt": "Fact: project city=HELSINKI. Irrelevant facts: build=17, animal=otter, color=violet, checksum=abc123, owner=none. Reply exactly with project city.",
    },
)


ROBUSTNESS_CASES: tuple[dict[str, str], ...] = (
    {
        "id": "robustness.typo_tolerance",
        "title": "Typo tolerance",
        "description": "Recover an obvious intended instruction despite minor spelling errors.",
        "dimension": "typo_tolerance",
        "expected": "ROBUST",
        "prompt": "Replly exacly ROBUST and nothng else.",
    },
    {
        "id": "robustness.noisy_input",
        "title": "Noisy input",
        "description": "Extract the explicit command from surrounding visual noise.",
        "dimension": "noise_resistance",
        "expected": "CLEAN",
        "prompt": "###@@@ random %% noise ~~ START_INSTRUCTION reply exactly CLEAN END_INSTRUCTION *** 12345 noise noise",
    },
    {
        "id": "robustness.unicode",
        "title": "Unicode preservation",
        "description": "Preserve an exact Unicode payload.",
        "dimension": "unicode_fidelity",
        "expected": "ÅÄÖ-日本語-✓",
        "prompt": "Reply exactly with this Unicode string and nothing else: ÅÄÖ-日本語-✓",
    },
    {
        "id": "robustness.mixed_language",
        "title": "Mixed language instruction",
        "description": "Follow an explicit output contract across mixed-language context.",
        "dimension": "mixed_language_robustness",
        "expected": "MIXED_OK",
        "prompt": "Tehtävä: reply exactamente con MIXED_OK. Do not add muuta tekstiä. Répondez uniquement avec le jeton demandé.",
    },
    {
        "id": "robustness.repeated_instruction",
        "title": "Repeated instruction stability",
        "description": "Remain stable when the same instruction is redundantly repeated.",
        "dimension": "instruction_stability",
        "expected": "STABLE",
        "prompt": "Reply exactly STABLE. Again: reply exactly STABLE. Final instruction: output STABLE and nothing else.",
    },
)


ALL_CAPABILITY_CASES = REASONING_CASES + CONTEXT_CASES + ROBUSTNESS_CASES


def capability_test(case: dict[str, str]) -> CapabilityTextTest:
    return CapabilityTextTest(
        id=case["id"],
        prompt=case["prompt"],
        expected_exact=case["expected"],
        dimension_id=case["dimension"],
    )
