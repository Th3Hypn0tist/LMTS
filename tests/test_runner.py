from lmts.core.models import ModelDescriptor, NormalizedResponse, NormalizedTiming, NormalizedUsage
from lmts.core.registry import ProviderRegistry
from lmts.core.runner import TestRunner
from lmts.core.store import RunStore
from lmts.core.subject import EvaluationSubject, SubjectMember
from lmts.tests.modules.text_generation import TextGenerationTest


class FakeProvider:
    id = "fake"

    def discover_models(self):
        return [ModelDescriptor(id="fake:model", provider_ref="fake", model_ref="model", location="local")]

    def generate(self, model, prompt):
        return NormalizedResponse(
            text="LMTS_OK",
            finish_reason="stop",
            usage=NormalizedUsage(input_tokens=4, output_tokens=2),
            timing=NormalizedTiming(total_ms=12.5),
            raw={"fake": True},
        )


def _system_context():
    return {
        "schema_version": 5,
        "fingerprint": "system-fingerprint",
        "profile": {"cpu": {"model_name": "Test CPU"}},
        "reference_benchmarks": {"schema_version": 2, "cpu": None, "memory": None, "gpu": None, "npu": None},
    }


def test_runner_executes_and_persists_canonical_run(tmp_path):
    providers = ProviderRegistry([FakeProvider()])
    model = providers.discover_models()[0]
    runner = TestRunner(
        providers,
        RunStore(tmp_path / "results"),
        system_context_loader=_system_context,
    )
    run, path = runner.run(TextGenerationTest(), model, tmp_path / "workspaces")
    assert run.status == "completed"
    assert run.passed is True
    assert run.metrics["output_tokens"] == 2
    assert run.system_context["fingerprint"] == "system-fingerprint"
    assert run.evaluation_subject["kind"] == "model"
    assert run.evaluation_subject["id"] == "fake:model"
    assert path.exists()
    assert len(run.responses) == 1


def test_runner_can_score_bot_and_composition_subjects(tmp_path):
    providers = ProviderRegistry([FakeProvider()])
    model = providers.discover_models()[0]
    runner = TestRunner(providers, RunStore(tmp_path / "results"), system_context_loader=_system_context)

    bot = EvaluationSubject.for_bot("bot.writer", configuration={"model": model.id})
    bot_run, _ = runner.run(TextGenerationTest(), model, tmp_path / "workspaces", subject=bot)
    assert bot_run.evaluation_subject["kind"] == "bot"
    assert bot_run.evaluation_subject["id"] == "bot.writer"

    composition = EvaluationSubject.for_composition(
        "composition.writer-reviewer",
        (
            SubjectMember("bot.writer", role="writer"),
            SubjectMember("bot.reviewer", role="reviewer"),
        ),
    )
    composition_run, _ = runner.run(TextGenerationTest(), model, tmp_path / "workspaces", subject=composition)
    assert composition_run.evaluation_subject["kind"] == "composition"
    assert len(composition_run.evaluation_subject["members"]) == 2
    assert composition_run.evaluation_subject["fingerprint"] != bot_run.evaluation_subject["fingerprint"]
