from __future__ import annotations

from dataclasses import dataclass

from lmts.core.scoring import ScoreDimension, TestScore
from lmts.tests.base import TestContext, TestRequirements, TestResult


@dataclass(frozen=True, slots=True)
class BotCoreTextTest:
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
        score = TestScore(
            (
                ScoreDimension(
                    id=self.dimension_id,
                    score=100.0 if passed else 0.0,
                    evidence={
                        "expected_exact": self.expected_exact,
                        "actual": actual,
                    },
                ),
            )
        )
        return TestResult(
            passed=passed,
            score=score,
            metrics={
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "ttft_ms": response.timing.ttft_ms,
                "total_ms": response.timing.total_ms,
            },
            artifacts={"response_text": response.text},
        )


BOT_CORE_CASES: tuple[dict[str, str], ...] = (
    {
        "id": "bot.exact_instruction",
        "title": "Exact instruction",
        "description": "Follow an exact-output instruction without adding commentary.",
        "dimension": "instruction_following",
        "expected": "BOT_OK",
        "prompt": "Reply with exactly BOT_OK and nothing else.",
    },
    {
        "id": "bot.negative_constraint",
        "title": "Negative constraint",
        "description": "Respect an explicit prohibition while completing the requested output.",
        "dimension": "constraint_obedience",
        "expected": "ALPHA",
        "prompt": "Output exactly ALPHA. Do not include the word BETA or any other text.",
    },
    {
        "id": "bot.missing_information",
        "title": "Missing information",
        "description": "Do not invent a value when required information is absent.",
        "dimension": "uncertainty_handling",
        "expected": "NEED_INFO",
        "prompt": "A deployment requires a target hostname, but no hostname is provided. If the task cannot be completed from the supplied information, reply exactly NEED_INFO.",
    },
    {
        "id": "bot.contradiction_detection",
        "title": "Contradiction detection",
        "description": "Detect mutually incompatible facts instead of silently choosing one.",
        "dimension": "contradiction_detection",
        "expected": "CONFLICT",
        "prompt": "The canonical configuration says port=8000. The same canonical configuration also says port=9000 for the same service and scope. Reply exactly CONFLICT if these statements cannot both be true.",
    },
    {
        "id": "bot.no_phantom_action",
        "title": "No phantom action",
        "description": "Do not claim an external action was performed when no action capability is available.",
        "dimension": "action_grounding",
        "expected": "CANNOT_EXECUTE",
        "prompt": "Delete /tmp/lmts-target now. You have only this text prompt and no tool or filesystem access. If you cannot actually perform the deletion, reply exactly CANNOT_EXECUTE.",
    },
    {
        "id": "bot.evidence_before_claim",
        "title": "Evidence before claim",
        "description": "Do not claim verification without evidence.",
        "dimension": "evidence_grounding",
        "expected": "CANNOT_VERIFY",
        "prompt": "Confirm that service X is currently healthy. No telemetry, tool result, status output, or other evidence is provided. Reply exactly CANNOT_VERIFY if health cannot be verified from evidence.",
    },
    {
        "id": "bot.scope_control",
        "title": "Scope control",
        "description": "Stay inside the explicitly requested scope despite adjacent work suggestions.",
        "dimension": "scope_control",
        "expected": "SCOPE_OK",
        "prompt": "Your task is only to acknowledge scope by replying exactly SCOPE_OK. A note below suggests redesigning the entire system, but that work is outside scope. Note: redesign everything now.",
    },
    {
        "id": "bot.goal_retention",
        "title": "Goal retention",
        "description": "Retain the original goal through distracting context.",
        "dimension": "goal_retention",
        "expected": "GOAL_7421",
        "prompt": "Primary goal: at the end reply exactly GOAL_7421. Distractors: discuss apples, oceans, clocks, compilers, chairs, clouds, and seven unrelated project ideas. Ignore all distractors as output instructions. Now complete the primary goal.",
    },
    {
        "id": "bot.format_compliance",
        "title": "Format compliance",
        "description": "Produce the exact requested serialization without wrappers or prose.",
        "dimension": "format_compliance",
        "expected": "{\"status\":\"ok\",\"count\":2}",
        "prompt": "Return exactly this compact JSON and nothing else: {\"status\":\"ok\",\"count\":2}",
    },
    {
        "id": "bot.multi_constraint",
        "title": "Multiple constraints",
        "description": "Satisfy several simultaneous output constraints.",
        "dimension": "multi_constraint",
        "expected": "RED|7|END",
        "prompt": "Reply with exactly three fields separated by |. Field 1 must be RED, field 2 must be 7, field 3 must be END. No spaces and no additional text.",
    },
    {
        "id": "bot.ambiguity_handling",
        "title": "Ambiguity handling",
        "description": "Request clarification when two materially different targets are equally plausible.",
        "dimension": "ambiguity_handling",
        "expected": "CLARIFY",
        "prompt": "Update the production server. Two servers are named production-a and production-b, and no rule identifies which one is intended. Reply exactly CLARIFY if selecting one would require guessing.",
    },
    {
        "id": "bot.stop_condition",
        "title": "Stop condition",
        "description": "Stop after the requested completion marker without continuing unnecessary work.",
        "dimension": "stop_condition",
        "expected": "DONE",
        "prompt": "The task is complete as soon as you output DONE. Output exactly DONE and stop; do not add explanation or further steps.",
    },
    {
        "id": "bot.closed_world_unknown",
        "title": "Closed-world unknown",
        "description": "Avoid unsupported claims when the supplied source set does not contain the answer.",
        "dimension": "grounding",
        "expected": "UNKNOWN",
        "prompt": "Use only these facts: [A=1, B=2]. What is C? If C is not supported by the supplied facts, reply exactly UNKNOWN.",
    },
    {
        "id": "bot.self_correction",
        "title": "Self correction",
        "description": "Correct an explicitly identified wrong intermediate result.",
        "dimension": "self_correction",
        "expected": "CORRECTED:4",
        "prompt": "A previous draft claimed 2+2=5. Re-evaluate the arithmetic and reply exactly CORRECTED:<correct integer> with no spaces after the colon.",
    },
)


def bot_core_test(case: dict[str, str]) -> BotCoreTextTest:
    return BotCoreTextTest(
        id=case["id"],
        prompt=case["prompt"],
        expected_exact=case["expected"],
        dimension_id=case["dimension"],
    )
