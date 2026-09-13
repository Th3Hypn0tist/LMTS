from pathlib import Path

from lmts.core.benchmark_runner import BenchmarkRunner
from lmts.core.executor import ModelExecutor
from lmts.core.models import ModelDescriptor, NormalizedResponse
from lmts.core.registry import ProviderRegistry
from lmts.core.runner import TestRunner
from lmts.core.store import RunStore
from lmts.tests.modules.text_generation import TextGenerationTest
from lmts.tools.profile import PROFILE_SCHEMA_VERSION


class FakeProvider:
    id = "fake"

    def discover_models(self):
        return []

    def generate(self, model, prompt):
        return NormalizedResponse(text="LMTS_OK")


class FakeTelemetry:
    def start(self):
        pass

    def stop(self):
        return {"samples": [], "summary": {"sample_count": 0}}


def test_benchmark_runner_runs_same_test_for_multiple_targets(tmp_path: Path) -> None:
    provider = FakeProvider()
    providers = ProviderRegistry([provider])
    runner = TestRunner(
        providers,
        RunStore(tmp_path / "results"),
        system_context_loader=lambda: {"schema_version": PROFILE_SCHEMA_VERSION, "fingerprint": "test-system"},
        telemetry_factory=FakeTelemetry,
    )
    benchmark = BenchmarkRunner(runner)
    models = [
        ModelDescriptor(id="fake:a", provider_ref="fake", model_ref="a", location="local"),
        ModelDescriptor(id="fake:b", provider_ref="fake", model_ref="b", location="local"),
    ]
    targets = [ModelExecutor(provider, model) for model in models]
    batch = benchmark.run(TextGenerationTest(), targets, tmp_path / "workspaces")
    assert batch.completed == 2
    assert batch.failed == 0
    assert batch.target_ids == ["fake:a", "fake:b"]
    assert len(batch.run_ids) == 2
