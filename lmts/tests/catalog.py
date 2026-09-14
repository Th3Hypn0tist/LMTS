from __future__ import annotations

from lmts.tests.base import TestRequirements
from lmts.tests.modules.bot_core import BOT_CORE_CASES, bot_core_test
from lmts.tests.modules.capability_cases import ALL_CAPABILITY_CASES, capability_test
from lmts.tests.modules.free_prompt import FreePromptConsistencyTest
from lmts.tests.modules.performance import ColdWarmPerformanceTest, RepeatVarianceTest
from lmts.tests.modules.text_generation import TextGenerationTest
from lmts.tests.modules.workspace_multifile import WorkspaceMultiFileTest
from lmts.tests.types import TestMatrix, TestParameter, TestTypeDefinition, TestTypeRegistry


def default_test_type_registry() -> TestTypeRegistry:
    definitions = [
        TestTypeDefinition(
            id="core.text_generation",
            version="1.0.0",
            title="Text generation",
            description="Basic text generation smoke test.",
            level="quick",
            requirements=TestRequirements(text_generation=True),
            parameters=(),
            factory=lambda values: TextGenerationTest(),
        ),
        TestTypeDefinition(
            id="core.workspace_multifile",
            version="1.0.0",
            title="Workspace multifile",
            description="Read input and create exact multi-file output.",
            level="standard",
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
            level="standard",
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
            level="standard",
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
            level="standard",
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
        definitions.append(
            TestTypeDefinition(
                id=case["id"],
                version="1.0.0",
                title=case["title"],
                description=case["description"],
                level=case.get("level", "quick"),
                mandatory=case.get("mandatory") == "true",
                requirements=TestRequirements(text_generation=True),
                parameters=(),
                factory=lambda values, case=case: bot_core_test(case),
            )
        )
    for case in ALL_CAPABILITY_CASES:
        definitions.append(
            TestTypeDefinition(
                id=case["id"],
                version="1.0.0",
                title=case["title"],
                description=case["description"],
                level=case.get("level", "quick"),
                mandatory=case.get("mandatory") == "true",
                requirements=TestRequirements(text_generation=True),
                parameters=(),
                factory=lambda values, case=case: capability_test(case),
            )
        )
    return TestTypeRegistry(definitions)


def default_test_matrix(registry: TestTypeRegistry | None = None) -> TestMatrix:
    types = registry or default_test_type_registry()
    matrix = TestMatrix()
    matrix.add(types.get("core.text_generation@1.0.0").configure("text-generation"))
    matrix.add(types.get("core.workspace_multifile@1.0.0").configure("workspace-multifile"))
    return matrix
