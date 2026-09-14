from __future__ import annotations

from dataclasses import dataclass

from lmts.core.scoring import ScoreDimension, TestScore
from lmts.tests.base import TestContext, TestRequirements, TestResult


@dataclass(frozen=True, slots=True)
class CarwashContextRetentionTest:
    id: str = "context.carwash_goal_persistence"
    version: str = "1.0.0"
    requirements: TestRequirements = TestRequirements(text_generation=True)

    @staticmethod
    def _decision(text: str) -> str:
        normalized = text.strip().upper().rstrip(".!?")
        if normalized == "DRIVE":
            return "DRIVE"
        if normalized == "WALK":
            return "WALK"
        return "OTHER"

    @staticmethod
    def _transcript(turns: list[tuple[str, str]], next_user: str) -> str:
        lines = [
            "Continue the conversation below. Preserve the original goal and all relevant entity state.",
            "For this test, answer the final user message with exactly DRIVE or WALK and nothing else.",
            "",
        ]
        for user, assistant in turns:
            lines.append(f"User: {user}")
            lines.append(f"Assistant: {assistant}")
        lines.append(f"User: {next_user}")
        lines.append("Assistant:")
        return "\n".join(lines)

    def run(self, context: TestContext) -> TestResult:
        first_user = "I'm taking car to carwash. It is on the other side of the road. Should I drive or walk?"
        first_prompt = (
            "Answer the user's practical question. Track what object must reach the destination. "
            "Reply with exactly DRIVE or WALK and nothing else.\n\n"
            f"User: {first_user}\nAssistant:"
        )
        first = context.generate(first_prompt)

        turns = [(first_user, first.text.strip())]
        second_user = "How do I wash the car if I walk?"
        second = context.generate(self._transcript(turns, second_user))

        turns.append((second_user, second.text.strip()))
        third_user = "I mean I need to wash the car. If I walk, the car stays at home and no wash."
        third = context.generate(self._transcript(turns, third_user))

        decisions = [self._decision(item.text) for item in (first, second, third)]
        passed_turns = [decision == "DRIVE" for decision in decisions]
        passed = all(passed_turns)
        score_value = 100.0 * sum(passed_turns) / len(passed_turns)

        return TestResult(
            passed=passed,
            score=TestScore(
                (
                    ScoreDimension(
                        id="goal_state_persistence",
                        score=score_value,
                        evidence={
                            "expected": ["DRIVE", "DRIVE", "DRIVE"],
                            "actual": decisions,
                            "turn_pass": passed_turns,
                        },
                    ),
                )
            ),
            metrics={
                "conversation_turns": 3,
                "goal_state_turns_passed": sum(passed_turns),
                "goal_state_retention_ratio": sum(passed_turns) / len(passed_turns),
                "total_input_tokens": sum(item.usage.input_tokens or 0 for item in (first, second, third)),
                "total_output_tokens": sum(item.usage.output_tokens or 0 for item in (first, second, third)),
                "total_ms": sum(item.timing.total_ms or 0.0 for item in (first, second, third)),
            },
            artifacts={
                "turns": [
                    {"user": first_user, "response": first.text, "decision": decisions[0]},
                    {"user": second_user, "response": second.text, "decision": decisions[1]},
                    {"user": third_user, "response": third.text, "decision": decisions[2]},
                ]
            },
        )
