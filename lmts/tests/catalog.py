from __future__ import annotations

from lmts.tests.base import TestRequirements
from lmts.tests.modules.bot_core import BOT_CORE_CASES, bot_core_test
from lmts.tests.modules.capability_cases import ALL_CAPABILITY_CASES, capability_test
from lmts.tests.modules.carwash_context import CarwashContextRetentionTest
from lmts.tests.modules.free_prompt import FreePromptConsistencyTest
from lmts.tests.modules.performance import ColdWarmPerformanceTest, RepeatVarianceTest
from lmts.tests.modules.text_generation import TextGenerationTest
from lmts.tests.modules.workspace_multifile import WorkspaceMultiFileTest
from lmts.tests.types import TestLevel, TestMatrix, TestParameter, TestTypeDefinition, TestTypeRegistry


MODERATE_TEST_IDS = {
    "context.carwash_goal_persistence",
    "core.workspace_multifile",
    "research.free_prompt_consistency",
    "performance.cold_warm",
    "performance.repeat_variance",
    "bot.scope_control",
    "bot.goal_retention",
    "bot.multi_constraint",
    "bot.self_correction",
    "reasoning.dependency_chain",
    "context.multi_needle",
    "context.early_retention",
    "context.conflict_priority",
    "context.irrelevant_resistance",
    "robustness.noisy_input",
    "robustness.mixed_language",
    "robustness.repeated_instruction",
}

MANDATORY_TEST_IDS = {
    "reasoning.carwash_transport",
    "context.carwash_goal_persistence",
}

# Free-prompt is intentionally user-configured. No fabricated default prompt.
AUTOMATED_SUITE_EXCLUSIONS = {"research.free_prompt_consistency"}


def _minimum_level(test_id: str) -> TestLevel:
    return "moderate" if test_id in MODERATE_TEST_IDS else "quick"


def default_test_type_registry() -> TestTypeRegistry:
    definitions = [
        TestTypeDefinition(
            id="core.text_generation",
            version="1.0.0",
            title="Text generation",
            description="Basic text generation smoke test.",
            minimum_level="quick",
            requirements=TestRequirements(text_generation=True),
            parameters=(),
            factory=lambda values: TextGenerationTest(),
        ),
        TestTypeDefinition(
            id="context.carwash_goal_persistence",
            version="1.0.0",
            title="Carwash goal persistence",
            description="Preserve the goal that the car itself must reach the car wash across a short conversation.",
            minimum_level="moderate",
            mandatory=True,
            requirements=TestRequirements(text_generation=True),
            parameters=(),
            factory=lambda values: CarwashContextRetentionTest(),
        ),
        TestTypeDefinition(
            id="core.workspace_multifile",
            version="1.0.0",
            title="Workspace multifile",
            description="Read input and create exact multi-file output.",
            minimum_level="moderate",
            requirements=TestRequirements(
                text_generation=True,
                workspace_read=True,
                workspace_write=True,
                multi_file_output=True,
            ),
            parameters=(),
            factory=lambda values: WorkspaceMultiFileTest(),
        ),
        TestTypeDefinition(
            id="research.free_prompt_consistency",
            version="1.0.0",
            title="Free prompt consistency",
            description="Run one arbitrary prompt repeatedly to measure exact-output consistency.",
            minimum_level="moderate",
            requirements=TestRequirements(text_generation=True),
            parameters=(
                TestParameter(
                    name="prompt",
                    label="Prompt",
                    kind="text",
                    required=True,
                    multiline=True,
                ),
                TestParameter(
                    name="repeats",
                    label="Repeats per model",
                    kind="integer",
                    required=True,
                    default=3,
                    minimum=1,
                    maximum=100,
                ),
            ),
            factory=lambda values: FreePromptConsistencyTest(
                prompt=str(values["prompt"]),
                repeats=int(values["repeats"]),
            ),
        ),
        TestTypeDefinition(
            id="performance.cold_warm",
            version="1.0.0",
            title="Cold and warm inference",
            description="Measure first-call behavior separately from repeated warm inference.",
            minimum_level="moderate",
            requirements=TestRequirements(text_generation=True),
            parameters=(
                TestParameter(name="prompt", label="Prompt", kind="text", required=True, default="Reply exactly PERF_OK", multiline=True),
                TestParameter(name="warm_repeats", label="Warm repeats", kind="integer", required=True, default=5, minimum=1, maximum=100),
            ),
            factory=lambda values: ColdWarmPerformanceTest(
                prompt=str(values["prompt"]),
                warm_repeats=int(values["warm_repeats"]),
            ),
        ),
        TestTypeDefinition(
            id="performance.repeat_variance",
            version="1.0.0",
            title="Repeat variance",
            description="Measure latency and generation-throughput variance across repeated identical calls.",
            minimum_level="moderate",
            requirements=TestRequirements(text_generation=True),
            parameters=(
                TestParameter(name="prompt", label="Prompt", kind="text", required=True, default="Reply exactly VAR_OK", multiline=True),
                TestParameter(name="repeats", label="Repeats", kind="integer", required=True, default=10, minimum=2, maximum=100),
            ),
            factory=lambda values: RepeatVarianceTest(
                prompt=str(values["prompt"]),
                repeats=int(values["repeats"]),
            ),
        ),
    ]
    for case in BOT_CORE_CASES:
        test_id = case["id"]
        definitions.append(
            TestTypeDefinition(
                id=test_id,
                version="1.0.0",
                title=case["title"],
                description=case["description"],
                minimum_level=_minimum_level(test_id),
                mandatory=test_id in MANDATORY_TEST_IDS,
                requirements=TestRequirements(text_generation=True),
                parameters=(),
                factory=lambda values, case=case: bot_core_test(case),
            )
        )
    for case in ALL_CAPABILITY_CASES:
        test_id = case["id"]
        definitions.append(
            TestTypeDefinition(
                id=test_id,
                version="1.0.0",
                title=case["title"],
                description=case["description"],
                minimum_level=_minimum_level(test_id),
                mandatory=test_id in MANDATORY_TEST_IDS,
                requirements=TestRequirements(text_generation=True),
                parameters=(),
                factory=lambda values, case=case: capability_test(case),
            )
        )
    return TestTypeRegistry(definitions)


def test_matrix_for_level(
    level: TestLevel,
    registry: TestTypeRegistry | None = None,
) -> TestMatrix:
    types = registry or default_test_type_registry()
    matrix = TestMatrix()
    for definition in types.definitions_for_level(level):
        if definition.id in AUTOMATED_SUITE_EXCLUSIONS:
            continue
        matrix.add(definition.configure(definition.id.replace(".", "-")))
    return matrix


def default_test_matrix(registry: TestTypeRegistry | None = None) -> TestMatrix:
    return test_matrix_for_level("moderate", registry)
