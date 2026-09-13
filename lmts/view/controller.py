from __future__ import annotations

from pathlib import Path

from lmts.core.benchmark_runner import BenchmarkRunner
from lmts.core.benchmark_store import BenchmarkStore
from lmts.core.registry import ProviderRegistry
from lmts.core.runner import TestRunner
from lmts.core.store import RunStore
from lmts.tests.base import TestModule
from lmts.tests.registry import TestRegistry
from lmts.tools.profile import scan_system_profile

from .projector import LMTSViewState


def _test_ref(test: TestModule) -> str:
    return f"{test.id}@{test.version}"


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
        previous_models = set(self.state.selected_model_ids)
        previous_tests = set(self.state.selected_test_refs)

        self.state.models = self.providers.discover_models()
        self.state.tests = list(self.tests.tests())

        available_model_ids = {model.id for model in self.state.models}
        available_test_refs = {_test_ref(test) for test in self.state.tests}
        self.state.selected_model_ids = previous_models & available_model_ids
        self.state.selected_test_refs = previous_tests & available_test_refs

        if not self.state.selected_model_ids and self.state.models:
            self.state.selected_model_ids = {self.state.models[0].id}
        if not self.state.selected_test_refs and self.state.tests:
            self.state.selected_test_refs = set(available_test_refs)

        self.state.message = (
            f"discovered {len(self.state.models)} model(s), "
            f"{len(self.state.tests)} test(s)"
        )

    def select_models(self, indices: set[int]) -> None:
        self.state.selected_model_ids = {
            self.state.models[index].id
            for index in sorted(indices)
            if 0 <= index < len(self.state.models)
        }

    def select_model_ids(self, model_ids: set[str]) -> None:
        available = {model.id for model in self.state.models}
        self.state.selected_model_ids = set(model_ids) & available

    def select_all_models(self) -> None:
        self.state.selected_model_ids = {model.id for model in self.state.models}

    def select_tests(self, indices: set[int]) -> None:
        self.state.selected_test_refs = {
            _test_ref(self.state.tests[index])
            for index in sorted(indices)
            if 0 <= index < len(self.state.tests)
        }

    def select_test_refs(self, test_refs: set[str]) -> None:
        available = {_test_ref(test) for test in self.state.tests}
        self.state.selected_test_refs = set(test_refs) & available

    def select_all_tests(self) -> None:
        self.state.selected_test_refs = {_test_ref(test) for test in self.state.tests}

    def select_model(self, index: int) -> None:
        self.select_models({index})

    def select_test(self, index: int) -> None:
        self.select_tests({index})

    def run_selected(self) -> None:
        models = self.state.selected_models
        tests = self.state.selected_tests
        if not models or not tests:
            self.state.message = "select at least one model and one test"
            return

        runner = TestRunner(self.providers, RunStore(self.results_root))
        benchmark_runner = BenchmarkRunner(runner)
        benchmark_store = BenchmarkStore(self.results_root)

        batch_ids: list[str] = []
        batch_paths: list[str] = []
        passed = 0
        failed = 0
        errors = 0
        total_runs = 0

        for test in tests:
            batch = benchmark_runner.run(test, models, self.workspace_root)
            path = benchmark_store.append(batch)
            batch_ids.append(batch.batch_id)
            batch_paths.append(str(path))
            passed += batch.passed
            failed += batch.failed
            errors += batch.errors
            total_runs += len(batch.run_ids)

        self.state.last_result = {
            "matrix": f"{len(models)} model(s) x {len(tests)} test(s)",
            "runs": total_runs,
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "batch_ids": ", ".join(batch_ids),
            "batch_paths": ", ".join(batch_paths),
        }
        self.state.message = (
            f"test matrix finished: {passed} passed, {failed} failed, {errors} error(s)"
        )

    def test_all(self) -> None:
        self.select_all_models()
        self.select_all_tests()
        self.run_selected()

    def benchmark_all_local(self) -> None:
        local_ids = {model.id for model in self.state.models if model.location == "local"}
        self.select_model_ids(local_ids)
        self.run_selected()

    def profile(self) -> None:
        profile = scan_system_profile().to_dict()
        self.state.last_result = {
            "cpu": profile.get("cpu"),
            "memory": profile.get("memory"),
            "gpu": profile.get("gpu"),
            "npu": profile.get("npu"),
        }
        self.state.message = "system profile scanned"
