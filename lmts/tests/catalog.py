from __future__ import annotations

from lmts.tests.base import TestRequirements
from lmts.tests.modules.free_prompt import FreePromptConsistencyTest
from lmts.tests.modules.text_generation import TextGenerationTest
from lmts.tests.modules.workspace_multifile import WorkspaceMultiFileTest
from lmts.tests.types import TestMatrix, TestParameter, TestTypeDefinition, TestTypeRegistry


def default_test_type_registry() -> TestTypeRegistry:
    return TestTypeRegistry(
        [
            TestTypeDefinition(
                id="core.text_generation",
                version="1.0.0",
                title="Text generation",
                description="Basic text generation smoke test.",
                requirements=TestRequirements(text_generation=True),
                parameters=(),
                factory=lambda values: TextGenerationTest(),
            ),
            TestTypeDefinition(
                id="core.workspace_multifile",
                version="1.0.0",
                title="Workspace multifile",
                description="Read input and create exact multi-file output.",
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
        ]
    )


def default_test_matrix(registry: TestTypeRegistry | None = None) -> TestMatrix:
    types = registry or default_test_type_registry()
    matrix = TestMatrix()
    matrix.add(types.get("core.text_generation@1.0.0").configure("text-generation"))
    matrix.add(types.get("core.workspace_multifile@1.0.0").configure("workspace-multifile"))
    return matrix
