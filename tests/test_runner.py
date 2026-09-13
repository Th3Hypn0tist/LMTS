from lmts.core.executor import RuntimeExecutor
from lmts.core.models import ModelDescriptor, NormalizedResponse, NormalizedTiming, NormalizedUsage
from lmts.core.registry import ProviderRegistry
from lmts.core.runner import TestRunner
from lmts.core.store import RunStore
from lmts.core.subject import EvaluationSubject, SubjectMember
from lmts.tests.modules.text_generation import TextGenerationTest
from lmts.tools.profile import PROFILE_SCHEMA_VERSION
from lmts.tools.reference_benchmark import REFERENCE_BENCHMARK_SCHEMA_VERSION


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


class FakeTelemetry:
    def start(self):
        pass

    def stop(self):
        return {"samples": [{"fake": True}], "summary": {"sample_count": 1}}


def _system_context():
    return {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "fingerprint": "system-fingerprint",
        "profile": {"cpu": {"model_name": "Test CPU"}},
        "reference_benchmarks": {
            "schema_version": REFERENCE_BENCHMARK_SCHEMA_VERSION,
            "cpu": None,
            "memory": None,
            "gpu": None,
            "npu": None,
        },
    }


def _runtime_response(prompt, sink):
    return NormalizedResponse(
        text="LMTS_OK",
        finish_reason="stop",
        usage=NormalizedUsage(input_tokens=4, output_tokens=2),
        timing=NormalizedTiming(total_ms=10.0),
        raw={"runtime": True},
    )


def _runner(providers, root):
    return TestRunner(
        providers,
        RunStore(root),
        system_context_loader=_system_context,
        telemetry_factory=FakeTelemetry,
    )


def test_runner_executes_and_persists_canonical_run(tmp_path):
    providers = ProviderRegistry([FakeProvider()])
    model = providers.discover_models()[0]
    runner = _runner(providers, tmp_path / "results")
    run, path = runner.run(TextGenerationTest(), model, tmp_path / "workspaces")
    assert run.status == "completed"
    assert run.passed is True
    assert run.metrics["output_tokens"] == 2
    assert run.system_context["fingerprint"] == "system-fingerprint"
    assert run.executor_kind == "model"
    assert run.executor_id == "fake:model"
    assert run.execution_metadata["runtime_configuration_fingerprint"]
    assert run.telemetry["summary"]["sample_count"] == 1
    assert run.evaluation_subject["kind"] == "model"
    assert run.evaluation_subject["id"] == "fake:model"
    assert path.exists()
    assert len(run.responses) == 1


def test_runner_executes_standalone_bot_subject(tmp_path):
    runner = _runner(ProviderRegistry([]), tmp_path / "results")
    subject = EvaluationSubject.for_bot("bot.writer", configuration={"runtime": "fake"})
    executor = RuntimeExecutor(
        executor_id="bot.writer",
        executor_kind="bot",
        evaluation_subject=subject,
        generate_handler=_runtime_response,
        executor_metadata={"runtime": "fake"},
    )

    run, path = runner.run_executor(TextGenerationTest(), executor, tmp_path / "workspaces")

    assert run.status == "completed"
    assert run.passed is True
    assert run.executor_kind == "bot"
    assert run.model_id is None
    assert run.evaluation_subject["id"] == "bot.writer"
    assert "bot" in path.parts


def test_runner_executes_composition_subject(tmp_path):
    runner = _runner(ProviderRegistry([]), tmp_path / "results")
    subject = EvaluationSubject.for_composition(
        "composition.writer-reviewer",
        (
            SubjectMember("bot.writer", role="writer"),
            SubjectMember("bot.reviewer", role="reviewer"),
        ),
    )
    executor = RuntimeExecutor(
        executor_id="composition.writer-reviewer",
        executor_kind="composition",
        evaluation_subject=subject,
        generate_handler=_runtime_response,
    )

    run, path = runner.run_executor(TextGenerationTest(), executor, tmp_path / "workspaces")

    assert run.status == "completed"
    assert run.executor_kind == "composition"
    assert len(run.evaluation_subject["members"]) == 2
    assert "composition" in path.parts
