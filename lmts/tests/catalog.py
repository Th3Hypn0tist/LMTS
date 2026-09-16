from __future__ import annotations

from lmts.tests.base import TestRequirements
from lmts.tests.modules.bot_core import BOT_CORE_CASES, bot_core_test
from lmts.tests.modules.capability_cases import ALL_CAPABILITY_CASES, capability_test
from lmts.tests.modules.carwash_context import CarwashContextRetentionTest
from lmts.tests.modules.free_prompt import FreePromptConsistencyTest
from lmts.tests.modules.performance import ColdWarmPerformanceTest, RepeatVarianceTest
from lmts.tests.modules.runtime_behavior import ALL_RUNTIME_BEHAVIOR_CASES, runtime_behavior_test
from lmts.tests.modules.text_generation import TextGenerationTest
from lmts.tests.modules.workspace_multifile import WorkspaceMultiFileTest
from lmts.tests.neuro_symbolic import NEURO_SYMBOLIC_TEST_SPECS, neuro_symbolic_test
from lmts.tests.types import TestLevel, TestMatrix, TestParameter, TestTypeDefinition, TestTypeRegistry


QUICK_TEST_IDS = {
    "core.text_generation",
    "reasoning.carwash_transport",
    "bot.exact_instruction",
    "bot.negative_constraint",
    "bot.missing_information",
    "bot.contradiction_detection",
    "bot.no_phantom_action",
    "bot.evidence_before_claim",
    "bot.format_compliance",
    "bot.ambiguity_handling",
    "bot.stop_condition",
    "bot.closed_world_unknown",
    "reasoning.arithmetic_chain",
    "reasoning.symbolic_logic",
    "reasoning.ordering",
    "reasoning.impossible_constraints",
    "context.single_needle",
    "robustness.typo_tolerance",
    "robustness.unicode",
}

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

CANDIDATE_TEST_IDS = {
    "bot_runtime.no_phantom_completion",
    "bot_runtime.scope_boundary",
    "composition.constraint_integration",
    "composition.conflict_resolution",
    *(spec["id"] for spec in NEURO_SYMBOLIC_TEST_SPECS),
}

MANDATORY_TEST_IDS = {
    "reasoning.carwash_transport",
    "context.carwash_goal_persistence",
}

AUTOMATED_SUITE_EXCLUSIONS = {
    "research.free_prompt_consistency",
    *CANDIDATE_TEST_IDS,
}


def _minimum_level(test_id: str) -> TestLevel:
    if test_id in QUICK_TEST_IDS:
        return "quick"
    if test_id in MODERATE_TEST_IDS or test_id in CANDIDATE_TEST_IDS:
        return "moderate"
    raise ValueError(f"test has no explicit minimum level: {test_id}")


def _validate_level_contract(case_ids: set[str]) -> None:
    groups = (QUICK_TEST_IDS, MODERATE_TEST_IDS, CANDIDATE_TEST_IDS)
    for index, left in enumerate(groups):
        for right in groups[index + 1 :]:
            overlap = left & right
            if overlap:
                raise ValueError(f"test level/status overlap: {', '.join(sorted(overlap))}")
    classified = QUICK_TEST_IDS | MODERATE_TEST_IDS | CANDIDATE_TEST_IDS
    missing = case_ids - classified
    unknown = classified - case_ids
    if missing:
        raise ValueError(f"unclassified test id(s): {', '.join(sorted(missing))}")
    if unknown:
        raise ValueError(f"classification references unknown test id(s): {', '.join(sorted(unknown))}")


def default_test_type_registry() -> TestTypeRegistry:
    static_case_ids = {
        "core.text_generation",
        "context.carwash_goal_persistence",
        "core.workspace_multifile",
        "research.free_prompt_consistency",
        "performance.cold_warm",
        "performance.repeat_variance",
        *(case["id"] for case in BOT_CORE_CASES),
        *(case["id"] for case in ALL_CAPABILITY_CASES),
        *(case["id"] for case in ALL_RUNTIME_BEHAVIOR_CASES),
        *(spec["id"] for spec in NEURO_SYMBOLIC_TEST_SPECS),
    }
    _validate_level_contract(static_case_ids)

    definitions = [
        TestTypeDefinition(
            id="core.text_generation",
            version="1.0.0",
            title="Text generation",
            description="Basic text generation smoke test.",
            minimum_level=_minimum_level("core.text_generation"),
            requirements=TestRequirements(text_generation=True),
            parameters=(),
            factory=lambda values: TextGenerationTest(),
        ),
        TestTypeDefinition(
            id="context.carwash_goal_persistence",
            version="1.0.0",
            title="Carwash goal persistence",
            description="Preserve the goal that the car itself must reach the car wash across a short conversation.",
            minimum_level=_minimum_level("context.carwash_goal_persistence"),
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
            minimum_level=_minimum_level("core.workspace_multifile"),
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
            minimum_level=_minimum_level("research.free_prompt_consistency"),
            requirements=TestRequirements(text_generation=True),
            parameters=(
                TestParameter(name="prompt", label="Prompt", kind="text", required=True, multiline=True),
                TestParameter(name="repeats", label="Repeats per model", kind="integer", required=True, default=3, minimum=1, maximum=100),
            ),
            factory=lambda values: FreePromptConsistencyTest(prompt=str(values["prompt"]), repeats=int(values["repeats"])),
        ),
        TestTypeDefinition(
            id="performance.cold_warm",
            version="1.0.0",
            title="Cold and warm inference",
            description="Measure first-call behavior separately from repeated warm inference.",
            minimum_level=_minimum_level("performance.cold_warm"),
            requirements=TestRequirements(text_generation=True),
            parameters=(
                TestParameter(name="prompt", label="Prompt", kind="text", required=True, default="Reply exactly PERF_OK", multiline=True),
                TestParameter(name="warm_repeats", label="Warm repeats", kind="integer", required=True, default=5, minimum=1, maximum=100),
            ),
            factory=lambda values: ColdWarmPerformanceTest(prompt=str(values["prompt"]), warm_repeats=int(values["warm_repeats"])),
        ),
        TestTypeDefinition(
            id="performance.repeat_variance",
            version="1.0.0",
            title="Repeat variance",
            description="Measure latency and generation-throughput variance across repeated identical calls.",
            minimum_level=_minimum_level("performance.repeat_variance"),
            requirements=TestRequirements(text_generation=True),
            parameters=(
                TestParameter(name="prompt", label="Prompt", kind="text", required=True, default="Reply exactly VAR_OK", multiline=True),
                TestParameter(name="repeats", label="Repeats", kind="integer", required=True, default=10, minimum=2, maximum=100),
            ),
            factory=lambda values: RepeatVarianceTest(prompt=str(values["prompt"]), repeats=int(values["repeats"])),
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

    for case in ALL_RUNTIME_BEHAVIOR_CASES:
        test_id = case["id"]
        module = runtime_behavior_test(case)
        definitions.append(
            TestTypeDefinition(
                id=test_id,
                version="1.0.0",
                title=case["title"],
                description=case["description"],
                minimum_level=_minimum_level(test_id),
                requirements=module.requirements,
                parameters=(),
                factory=lambda values, case=case: runtime_behavior_test(case),
            )
        )

    for spec in NEURO_SYMBOLIC_TEST_SPECS:
        test_id = str(spec["id"])
        family = str(spec["family"])
        definitions.append(
            TestTypeDefinition(
                id=test_id,
                version="0.1.0-candidate",
                title=str(spec["title"]),
                description=str(spec["description"]),
                minimum_level=_minimum_level(test_id),
                requirements=TestRequirements(text_generation=True),
                parameters=(
                    TestParameter(name="max_complexity", label="Maximum complexity", kind="integer", required=True, default=16, minimum=2, maximum=256),
                    TestParameter(name="cases_per_level", label="Cases per complexity level", kind="integer", required=True, default=2, minimum=1, maximum=10),
                ),
                factory=lambda values, test_id=test_id, family=family: neuro_symbolic_test(
                    test_id,
                    family,
                    max_complexity=int(values["max_complexity"]),
                    cases_per_level=int(values["cases_per_level"]),
                ),
            )
        )

    return TestTypeRegistry(definitions)


def test_matrix_for_level(level: TestLevel, registry: TestTypeRegistry | None = None) -> TestMatrix:
    types = registry if registry is not None else default_test_type_registry()
    matrix = TestMatrix()
    for definition in types.definitions_for_level(level):
        if definition.id in AUTOMATED_SUITE_EXCLUSIONS:
            continue
        matrix.add(definition.configure(definition.id.replace(".", "-")))
    return matrix


def default_test_matrix(registry: TestTypeRegistry | None = None) -> TestMatrix:
    return test_matrix_for_level("moderate", registry)
