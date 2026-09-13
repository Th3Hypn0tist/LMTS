from __future__ import annotations

from pathlib import Path

from lmts.core.benchmark_runner import BenchmarkRunner
from lmts.core.benchmark_store import BenchmarkStore
from lmts.core.registry import ProviderRegistry
from lmts.core.runner import TestRunner
from lmts.core.store import RunStore
from lmts.tests.registry import TestRegistry
from lmts.tools.profile import scan_system_profile

from .projector import LMTSViewState


class LMTSViewController:
    def __init__(
        self,
        providers: ProviderRegistry,
        tests: TestRegistry,
        *,
        results_root: Path = Path("results"),
        workspace_root: Path = Path(".lmts/workspaces"),
    ) -> None:
        self.providers = providers
        self.tests = tests
        self.results_root = results_root
        self.workspace_root = workspace_root
        self.state = LMTSViewState(tests=list(tests.tests()))

    def refresh(self) -> None:
        self.state.models = self.providers.discover_models()
        self.state.tests = list(self.tests.tests())
        self.state.selected_model = min(self.state.selected_model, max(0, len(self.state.models) - 1))
        self.state.selected_test = min(self.state.selected_test, max(0, len(self.state.tests) - 1))
        self.state.message = f"discovered {len(self.state.models)} model(s)"

    def select_model(self, index: int) -> None:
        if not self.state.models:
            return
        self.state.selected_model = min(max(0, index), len(self.state.models) - 1)

    def select_test(self, index: int) -> None:
        if not self.state.tests:
            return
        self.state.selected_test = min(max(0, index), len(self.state.tests) - 1)

    def run_selected(self) -> None:
        model = self.state.model
        test = self.state.test
        if model is None or test is None:
            self.state.message = "select a model and test first"
            return
        runner = TestRunner(self.providers, RunStore(self.results_root))
        run, path = runner.run(test, model, self.workspace_root)
        self.state.last_result = {
            "run_id": run.run_id,
            "status": run.status,
            "passed": run.passed,
            "path": str(path),
        }
        self.state.message = f"run finished: {run.status}"

    def benchmark_all_local(self) -> None:
        test = self.state.test
        models = [model for model in self.state.models if model.location == "local"]
        if test is None or not models:
            self.state.message = "no selected test or local models"
            return
        batch = BenchmarkRunner(TestRunner(self.providers, RunStore(self.results_root))).run(
            test, models, self.workspace_root
        )
        path = BenchmarkStore(self.results_root).append(batch)
        self.state.last_result = {
            "batch_id": batch.batch_id,
            "passed": batch.passed,
            "failed": batch.failed,
            "errors": batch.errors,
            "path": str(path),
        }
        self.state.message = "benchmark finished"

    def profile(self) -> None:
        profile = scan_system_profile().to_dict()
        self.state.last_result = {
            "cpu": profile.get("cpu"),
            "memory": profile.get("memory"),
            "gpu": profile.get("gpu"),
            "npu": profile.get("npu"),
        }
        self.state.message = "system profile scanned"
