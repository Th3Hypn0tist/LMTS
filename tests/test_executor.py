from lmts.core.executor import ModelExecutor, RuntimeExecutor
from lmts.core.models import ModelDescriptor, NormalizedResponse
from lmts.core.subject import EvaluationSubject
from lmts.tests.base import TestRequirements
from lmts.tests.requirements import missing_requirements


class FakeProvider:
    id = "fake"

    def discover_models(self):
        return []

    def generate(self, model, prompt):
        return NormalizedResponse(text="OK")


def test_model_executor_exposes_lmts_workspace_surface() -> None:
    model = ModelDescriptor(
        id="fake:model",
        provider_ref="fake",
        model_ref="model",
        location="local",
    )
    executor = ModelExecutor(FakeProvider(), model)

    assert executor.capabilities.text is True
    assert executor.capabilities.workspace_read is True
    assert executor.capabilities.workspace_write is True
    assert executor.capabilities.multi_file_output is True


def test_runtime_executor_missing_requirements_are_explicit() -> None:
    subject = EvaluationSubject.for_bot("bot.demo")
    executor = RuntimeExecutor(
        executor_id="bot.demo",
        executor_kind="bot",
        evaluation_subject=subject,
        generate_handler=lambda prompt, sink: NormalizedResponse(text="OK"),
    )
    missing = missing_requirements(
        TestRequirements(text_generation=True, tools=True),
        executor.capabilities,
    )

    assert missing == ("tools",)
