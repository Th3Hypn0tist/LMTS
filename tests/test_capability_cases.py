from lmts.core.executor import RuntimeExecutor
from lmts.core.models import NormalizedResponse
from lmts.core.subject import EvaluationSubject
from lmts.lib.workspace import Workspace
from lmts.tests.base import TestContext
from lmts.tests.catalog import default_test_matrix, default_test_type_registry
from lmts.tests.modules.capability_cases import ALL_CAPABILITY_CASES, capability_test


def _context(tmp_path, text: str) -> TestContext:
    executor = RuntimeExecutor(
        executor_id="bot.test",
        executor_kind="bot",
        evaluation_subject=EvaluationSubject.for_bot("bot.test"),
        generate_handler=lambda prompt, sink: NormalizedResponse(text=text),
    )
    return TestContext(executor=executor, workspace=Workspace(tmp_path / "workspace"))


def test_capability_cases_are_registered_and_in_default_matrix() -> None:
    registry = default_test_type_registry()
    registered = {definition.id for definition in registry.definitions()}
    capability_ids = {case["id"] for case in ALL_CAPABILITY_CASES}
    assert capability_ids <= registered

    default_ids = {test.id for test in default_test_matrix(registry).tests()}
    assert capability_ids <= default_ids


def test_every_capability_case_has_deterministic_full_score(tmp_path) -> None:
    for case in ALL_CAPABILITY_CASES:
        result = capability_test(case).run(
            _context(tmp_path / case["id"].replace(".", "-"), case["expected"])
        )
        assert result.passed is True
        assert result.score is not None
        assert result.score.percent == 100.0
        assert result.score.dimensions[0].id == case["dimension"]
