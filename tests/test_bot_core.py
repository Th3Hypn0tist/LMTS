from lmts.core.models import ModelDescriptor, NormalizedResponse
from lmts.tests.catalog import default_test_matrix, default_test_type_registry
from lmts.tests.modules.bot_core import BOT_CORE_CASES, bot_core_test
from lmts.tests.base import TestContext
from lmts.lib.workspace import Workspace


class EchoExpectedProvider:
    id = "fake"

    def __init__(self, text: str) -> None:
        self.text = text

    def generate(self, model, prompt):
        return NormalizedResponse(text=self.text)


def _context(tmp_path, text: str) -> TestContext:
    model = ModelDescriptor(id="fake:model", provider_ref="fake", model_ref="model", location="local")
    return TestContext(
        provider=EchoExpectedProvider(text),
        model=model,
        workspace=Workspace(tmp_path / "workspace"),
    )


def test_bot_core_cases_are_registered_but_not_default_matrix() -> None:
    registry = default_test_type_registry()
    registered = {definition.id for definition in registry.definitions()}
    bot_ids = {case["id"] for case in BOT_CORE_CASES}
    assert bot_ids <= registered

    default_ids = {test.id for test in default_test_matrix(registry).tests()}
    assert not (bot_ids & default_ids)


def test_every_bot_core_case_scores_exact_success(tmp_path) -> None:
    for case in BOT_CORE_CASES:
        test = bot_core_test(case)
        result = test.run(_context(tmp_path / case["id"].replace(".", "-"), case["expected"]))
        assert result.passed is True
        assert result.score is not None
        assert result.score.percent == 100.0
        assert result.score.dimensions[0].id == case["dimension"]


def test_bot_core_failure_scores_zero_with_evidence(tmp_path) -> None:
    case = BOT_CORE_CASES[0]
    result = bot_core_test(case).run(_context(tmp_path, "WRONG"))
    assert result.passed is False
    assert result.score is not None
    assert result.score.percent == 0.0
    evidence = result.score.dimensions[0].evidence
    assert evidence["expected_exact"] == case["expected"]
    assert evidence["actual"] == "WRONG"
