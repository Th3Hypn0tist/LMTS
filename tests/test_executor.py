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



class LifecycleProvider(FakeProvider):
    def __init__(self):
        self.loaded = False
        self.prompts = []

    def generate(self, model, prompt):
        self.loaded = True
        self.prompts.append(prompt)
        return NormalizedResponse(text="OK")

    def unload(self, model):
        self.loaded = False

    def is_loaded(self, model):
        return self.loaded


def test_model_executor_warmup_is_unmeasured_provider_call() -> None:
    provider = LifecycleProvider()
    model = ModelDescriptor(
        id="fake:model",
        provider_ref="fake",
        model_ref="model",
        location="local",
    )
    executor = ModelExecutor(provider, model)

    response = executor.warm_up()

    assert response.text == "OK"
    assert provider.loaded is True
    assert provider.prompts == ["Reply exactly OK"]


def test_model_executor_exposes_verified_lifecycle_hooks() -> None:
    provider = LifecycleProvider()
    model = ModelDescriptor(
        id="fake:model",
        provider_ref="fake",
        model_ref="model",
        location="local",
    )
    executor = ModelExecutor(provider, model)

    executor.warm_up()
    assert executor.is_loaded() is True

    executor.unload()
    assert executor.is_loaded() is False
