from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from typing import Callable

from lmts.core.scoring import ScoreDimension, TestScore
from lmts.tests.base import TestContext, TestRequirements, TestResult


@dataclass(frozen=True, slots=True)
class NeuroSymbolicCase:
    family: str
    complexity: int
    variant: int
    case_id: str
    prompt: str
    expected: str

    def __post_init__(self) -> None:
        if not self.family or not self.family.strip():
            raise ValueError("neuro-symbolic family must be non-empty")
        if self.complexity < 2:
            raise ValueError("neuro-symbolic complexity must be >= 2")
        if self.variant < 0:
            raise ValueError("neuro-symbolic variant must be >= 0")
        if not self.case_id or not self.case_id.strip():
            raise ValueError("neuro-symbolic case id must be non-empty")
        if not self.prompt or not self.prompt.strip():
            raise ValueError("neuro-symbolic prompt must be non-empty")
        if not self.expected or not self.expected.strip():
            raise ValueError("neuro-symbolic expected answer must be non-empty")


CaseBuilder = Callable[[int, int], NeuroSymbolicCase]


def complexity_levels(max_complexity: int) -> tuple[int, ...]:
    if max_complexity < 2:
        raise ValueError("max_complexity must be >= 2")
    levels: list[int] = []
    value = 2
    while value < max_complexity:
        levels.append(value)
        value *= 2
    levels.append(max_complexity)
    return tuple(dict.fromkeys(levels))


def _shuffle(lines: list[str], seed: str) -> list[str]:
    values = list(lines)
    random.Random(seed).shuffle(values)
    return values


def build_rule_chain_case(complexity: int, variant: int) -> NeuroSymbolicCase:
    nodes = [f"P{i:03d}" for i in range(complexity + 1)]
    rules = [f"{nodes[i]} -> {nodes[i + 1]}" for i in range(complexity)]
    expected = "YES"
    if variant % 2:
        del rules[complexity // 2]
        expected = "NO"
    distractors = [f"D{i:03d} -> E{i:03d}" for i in range(complexity)]
    rule_lines = _shuffle(rules + distractors, f"rule-chain:{complexity}:{variant}")
    prompt = (
        "Use only the facts and implication rules below. A rule A -> B may fire only when A is established. "
        "Do not invent missing rules. Determine whether the query is derivable. Reply exactly YES or NO.\n\n"
        f"FACTS:\n{nodes[0]}\n\nRULES:\n" + "\n".join(rule_lines) + f"\n\nQUERY:\n{nodes[-1]}"
    )
    return NeuroSymbolicCase(
        family="rule_chaining",
        complexity=complexity,
        variant=variant,
        case_id=f"rule-chain-c{complexity}-v{variant}",
        prompt=prompt,
        expected=expected,
    )


def build_graph_reachability_case(complexity: int, variant: int) -> NeuroSymbolicCase:
    nodes = [f"N{i:03d}" for i in range(complexity + 1)]
    edges = [f"{nodes[i]} -> {nodes[i + 1]}" for i in range(complexity)]
    expected = "YES"
    if variant % 2:
        del edges[complexity // 2]
        expected = "NO"
    distractors = [f"X{i:03d} -> X{i + 1:03d}" for i in range(complexity)]
    edge_lines = _shuffle(edges + distractors, f"graph:{complexity}:{variant}")
    prompt = (
        "The graph below is directed. Using only the listed edges, determine whether a directed path exists from START to TARGET. "
        "Reply exactly YES or NO.\n\nEDGES:\n"
        + "\n".join(edge_lines)
        + f"\n\nSTART: {nodes[0]}\nTARGET: {nodes[-1]}"
    )
    return NeuroSymbolicCase(
        family="graph_reachability",
        complexity=complexity,
        variant=variant,
        case_id=f"graph-c{complexity}-v{variant}",
        prompt=prompt,
        expected=expected,
    )


def build_state_transition_case(complexity: int, variant: int) -> NeuroSymbolicCase:
    width = max(4, min(24, complexity // 2 + 2))
    state = [0] * width
    operations: list[str] = []
    for step in range(complexity):
        kind = (step + variant) % 3
        left = (step * 3 + variant) % width
        right = (step * 5 + variant + 1) % width
        if right == left:
            right = (right + 1) % width
        if kind == 0:
            state[left] = 1 - state[left]
            operations.append(f"FLIP B{left}")
        elif kind == 1:
            state[right] = state[left]
            operations.append(f"COPY B{left} B{right}")
        else:
            state[left], state[right] = state[right], state[left]
            operations.append(f"SWAP B{left} B{right}")
    expected = "".join(str(bit) for bit in state)
    prompt = (
        f"There are {width} binary registers B0 through B{width - 1}, all initially 0. Apply the operations in order.\n"
        "FLIP Bx toggles Bx. COPY Bx By replaces By with the current value of Bx. SWAP Bx By exchanges their current values.\n"
        f"After all operations, reply with exactly {width} bits in B0..B{width - 1} order and no other text.\n\n"
        + "\n".join(f"{index + 1}. {operation}" for index, operation in enumerate(operations))
    )
    return NeuroSymbolicCase(
        family="state_transitions",
        complexity=complexity,
        variant=variant,
        case_id=f"state-c{complexity}-v{variant}",
        prompt=prompt,
        expected=expected,
    )


def build_constraint_ordering_case(complexity: int, variant: int) -> NeuroSymbolicCase:
    count = complexity + 2
    labels = [f"K{i:03d}" for i in range(count)]
    hidden = list(labels)
    random.Random(f"ordering:hidden:{complexity}:{variant}").shuffle(hidden)
    constraints = [f"{hidden[i]} < {hidden[i + 1]}" for i in range(count - 1)]
    for index in range(0, count - 2, 2):
        constraints.append(f"{hidden[index]} < {hidden[index + 2]}")
    constraints = _shuffle(constraints, f"ordering:constraints:{complexity}:{variant}")
    expected = ",".join(hidden)
    prompt = (
        "Each constraint A < B means A must appear before B. The constraints define one complete ordering. "
        "Resolve the ordering and reply with all symbols from first to last as a comma-separated list with no spaces or other text.\n\n"
        + "\n".join(constraints)
    )
    return NeuroSymbolicCase(
        family="constraint_ordering",
        complexity=complexity,
        variant=variant,
        case_id=f"ordering-c{complexity}-v{variant}",
        prompt=prompt,
        expected=expected,
    )


NEURO_SYMBOLIC_BUILDERS: dict[str, CaseBuilder] = {
    "rule_chaining": build_rule_chain_case,
    "graph_reachability": build_graph_reachability_case,
    "state_transitions": build_state_transition_case,
    "constraint_ordering": build_constraint_ordering_case,
}

NEURO_SYMBOLIC_TEST_SPECS = (
    {
        "id": "neuro_symbolic.rule_chaining",
        "family": "rule_chaining",
        "title": "Neuro-symbolic rule chaining",
        "description": "Measure exact deductive rule chaining as chain length and distractor count increase.",
    },
    {
        "id": "neuro_symbolic.graph_reachability",
        "family": "graph_reachability",
        "title": "Neuro-symbolic graph reachability",
        "description": "Measure directed reachability reasoning as graph path length and distractors increase.",
    },
    {
        "id": "neuro_symbolic.state_transitions",
        "family": "state_transitions",
        "title": "Neuro-symbolic state transitions",
        "description": "Measure exact symbolic state tracking across increasingly long transition sequences.",
    },
    {
        "id": "neuro_symbolic.constraint_ordering",
        "family": "constraint_ordering",
        "title": "Neuro-symbolic constraint ordering",
        "description": "Measure constraint integration and exact total-order recovery as problem size increases.",
    },
)


@dataclass(frozen=True, slots=True)
class NeuroSymbolicScalingTest:
    id: str
    family: str
    max_complexity: int = 16
    cases_per_level: int = 2
    version: str = "0.1.0-candidate"
    requirements: TestRequirements = TestRequirements(text_generation=True)

    def __post_init__(self) -> None:
        if self.family not in NEURO_SYMBOLIC_BUILDERS:
            raise ValueError(f"unsupported neuro-symbolic family: {self.family}")
        if self.max_complexity < 2 or self.max_complexity > 256:
            raise ValueError("max_complexity must be within 2..256")
        if self.cases_per_level < 1 or self.cases_per_level > 10:
            raise ValueError("cases_per_level must be within 1..10")

    def run(self, context: TestContext) -> TestResult:
        builder = NEURO_SYMBOLIC_BUILDERS[self.family]
        levels = complexity_levels(self.max_complexity)
        records: list[dict[str, object]] = []
        level_metrics: list[dict[str, object]] = []
        total_correct = 0
        total_cases = 0
        contiguous_ceiling = 0
        ceiling_open = True
        first_failure: int | None = None

        for complexity in levels:
            level_correct = 0
            level_timings: list[float] = []
            level_ttft: list[float] = []
            for variant in range(self.cases_per_level):
                case = builder(complexity, variant)
                response = context.generate(case.prompt)
                actual = response.text.strip()
                correct = actual == case.expected
                total_cases += 1
                if correct:
                    total_correct += 1
                    level_correct += 1
                if isinstance(response.timing.total_ms, (int, float)):
                    level_timings.append(float(response.timing.total_ms))
                if isinstance(response.timing.ttft_ms, (int, float)):
                    level_ttft.append(float(response.timing.ttft_ms))
                records.append(
                    {
                        "case_id": case.case_id,
                        "family": case.family,
                        "complexity": case.complexity,
                        "variant": case.variant,
                        "prompt_sha256": hashlib.sha256(case.prompt.encode("utf-8")).hexdigest(),
                        "expected": case.expected,
                        "actual": actual,
                        "correct": correct,
                        "total_ms": response.timing.total_ms,
                        "ttft_ms": response.timing.ttft_ms,
                        "input_tokens": response.usage.input_tokens,
                        "output_tokens": response.usage.output_tokens,
                    }
                )

            fully_solved = level_correct == self.cases_per_level
            if ceiling_open and fully_solved:
                contiguous_ceiling = complexity
            elif not fully_solved:
                ceiling_open = False
                if first_failure is None:
                    first_failure = complexity
            level_metrics.append(
                {
                    "complexity": complexity,
                    "correct": level_correct,
                    "cases": self.cases_per_level,
                    "accuracy_percent": level_correct / self.cases_per_level * 100.0,
                    "mean_total_ms": None if not level_timings else sum(level_timings) / len(level_timings),
                    "mean_ttft_ms": None if not level_ttft else sum(level_ttft) / len(level_ttft),
                    "fully_solved": fully_solved,
                }
            )

        accuracy = total_correct / total_cases * 100.0
        ceiling_score = contiguous_ceiling / self.max_complexity * 100.0
        timed_levels = [
            item for item in level_metrics if isinstance(item.get("mean_total_ms"), (int, float)) and float(item["mean_total_ms"]) > 0
        ]
        latency_growth_ratio = None
        if len(timed_levels) >= 2:
            latency_growth_ratio = float(timed_levels[-1]["mean_total_ms"]) / float(timed_levels[0]["mean_total_ms"])

        return TestResult(
            passed=total_correct == total_cases,
            score=TestScore(
                (
                    ScoreDimension(
                        id="neuro_symbolic_accuracy",
                        score=accuracy,
                        evidence={"correct": total_correct, "cases": total_cases},
                    ),
                    ScoreDimension(
                        id="neuro_symbolic_complexity_ceiling",
                        score=ceiling_score,
                        evidence={
                            "max_complexity": self.max_complexity,
                            "max_contiguous_fully_solved_complexity": contiguous_ceiling,
                            "first_failure_complexity": first_failure,
                        },
                    ),
                )
            ),
            metrics={
                "family": self.family,
                "max_complexity": self.max_complexity,
                "cases_per_level": self.cases_per_level,
                "levels": list(levels),
                "accuracy_percent": accuracy,
                "max_contiguous_fully_solved_complexity": contiguous_ceiling,
                "first_failure_complexity": first_failure,
                "latency_growth_ratio": latency_growth_ratio,
                "by_complexity": level_metrics,
            },
            artifacts={"cases": records},
        )


def neuro_symbolic_test(
    test_id: str,
    family: str,
    *,
    max_complexity: int = 16,
    cases_per_level: int = 2,
) -> NeuroSymbolicScalingTest:
    return NeuroSymbolicScalingTest(
        id=test_id,
        family=family,
        max_complexity=max_complexity,
        cases_per_level=cases_per_level,
    )
