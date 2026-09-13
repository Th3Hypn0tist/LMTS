from lmts.core.models import ModelDescriptor, NormalizedResponse, NormalizedTiming, NormalizedUsage
from lmts.core.registry import ProviderRegistry
from lmts.core.runner import TestRunner
from lmts.core.store import RunStore
from lmts.tests.modules.text_generation import TextGenerationTest
from lmts.tools.profile import SystemProfile


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


def test_runner_executes_and_persists_canonical_run(tmp_path):
    providers = ProviderRegistry([FakeProvider()])
    model = providers.discover_models()[0]
    runner = TestRunner(
        providers,
        RunStore(tmp_path / "results"),
        profile_scan=lambda: SystemProfile(cpu={"model": "test"}),
    )
    run, path = runner.run(TextGenerationTest(), model, tmp_path / "workspaces")
    assert run.status == "completed"
    assert run.passed is True
    assert run.metrics["output_tokens"] == 2
    assert run.system_profile["cpu"]["model"] == "test"
    assert path.exists()
    assert len(run.responses) == 1
