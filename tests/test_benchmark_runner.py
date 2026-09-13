from pathlib import Path

from lmts.core.benchmark_runner import BenchmarkRunner
from lmts.core.models import ModelDescriptor, NormalizedResponse
from lmts.core.registry import ProviderRegistry
from lmts.core.runner import TestRunner
from lmts.core.store import RunStore
from lmts.tests.modules.text_generation import TextGenerationTest


class FakeProvider:
    id = "fake"

    def discover_models(self):
        return []

    def generate(self, model, prompt):
        return NormalizedResponse(text="LMTS_OK")


def test_benchmark_runner_runs_same_test_for_multiple_models(tmp_path: Path) -> None:
    provider = FakeProvider()
    runner = TestRunner(
        ProviderRegistry([provider]),
        RunStore(tmp_path / "results"),
        system_context_loader=lambda: {"schema_version": 5, "fingerprint": "test-system"},
    )
    benchmark = BenchmarkRunner(runner)
    models = [
        ModelDescriptor(id="fake:a", provider_ref="fake", model_ref="a", location="local"),
        ModelDescriptor(id="fake:b", provider_ref="fake", model_ref="b", location="local"),
    ]
    batch = benchmark.run(TextGenerationTest(), models, tmp_path / "workspaces")
    assert batch.completed == 2
    assert batch.failed == 0
    assert len(batch.run_ids) == 2
