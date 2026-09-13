from __future__ import annotations

import threading
from pathlib import Path

from lmts.core.benchmark_runner import BenchmarkProgress, BenchmarkRunner
from lmts.core.benchmark_store import BenchmarkStore
from lmts.core.control import RunControl
from lmts.core.registry import ProviderRegistry
from lmts.core.runner import TestRunner
from lmts.core.store import RunStore
from lmts.lib.errorlog import export_error_log
from lmts.tests.base import test_ref
from lmts.tests.types import ConfiguredTest, TestMatrix, TestTypeRegistry
from lmts.tools.profile import DEFAULT_PROFILE_PATH, load_system_profile, save_system_profile, scan_system_profile

from .projector import LMTSViewState
from .response_monitor import ResponseMonitor


class LMTSViewController:
    def __init__(self, providers: ProviderRegistry, test_types: TestTypeRegistry, matrix: TestMatrix, *, results_root: Path = Path("results"), workspace_root: Path = Path(".lmts/workspaces"), logs_root: Path = Path("logs"), profile_path: Path = DEFAULT_PROFILE_PATH) -> None:
        self.providers = providers
        self.test_types = test_types
        self.matrix = matrix
        self.results_root = results_root
        self.workspace_root = workspace_root
        self.logs_root = logs_root
        self.profile_path = profile_path
        self.state = LMTSViewState(tests=list(matrix.tests()))
        self.response_monitor = ResponseMonitor()
        self.last_errors: list[dict[str, object]] = []
        self._run_thread: threading.Thread | None = None
        self._run_control: RunControl | None = None
        self._sync_profile_state()

    def _sync_profile_state(self) -> None:
        payload = load_system_profile(self.profile_path)
        self.state.profile_required = payload is None
        self.state.profiled_at = str(payload.get("profiled_at") or "") if payload is not None else ""

    def _sync_matrix_state(self) -> None:
        previous = set(self.state.selected_test_refs)
        self.state.tests = list(self.matrix.tests())
        available = {test_ref(test) for test in self.state.tests}
        self.state.selected_test_refs = previous & available
        if not self.state.selected_test_refs and self.state.tests:
            self.state.selected_test_refs = set(available)

    def refresh(self) -> None:
        if self.state.running:
            self.state.message = "cannot refresh while test matrix is running"
            return
        previous_models = set(self.state.selected_model_ids)
        self.state.models = self.providers.discover_models()
        available_model_ids = {model.id for model in self.state.models}
        self.state.selected_model_ids = previous_models & available_model_ids
        if not self.state.selected_model_ids and self.state.models:
            self.state.selected_model_ids = {self.state.models[0].id}
        self._sync_matrix_state()
        self._sync_profile_state()
        self.state.message = f"discovered {len(self.state.models)} model(s), matrix has {len(self.state.tests)} configured test(s), registry has {len(self.test_types.definitions())} test type(s)"
        if self.state.profile_required:
            self.state.message += "; system profile required before testing"

    def recent_results(self, *, limit: int = 200) -> list[tuple[Path, dict]]:
        store = RunStore(self.results_root)
        paths = store.iter_run_paths()
        paths.sort(key=lambda path: path.stat().st_mtime if path.exists() else 0.0, reverse=True)
        output: list[tuple[Path, dict]] = []
        for path in paths[:limit]:
            try:
                output.append((path, store.load(path)))
            except (OSError, ValueError):
                continue
        return output

    def add_test(self, type_ref: str, instance_id: str, params: dict[str, object] | None = None) -> ConfiguredTest | None:
        if self.state.running:
            self.state.message = "cannot change matrix while test matrix is running"
            return None
        try:
            configured = self.test_types.get(type_ref).configure(instance_id, params)
            self.matrix.add(configured)
        except (KeyError, ValueError) as exc:
            self.state.message = f"cannot add test: {exc}"
            return None
        self._sync_matrix_state()
        self.state.selected_test_refs.add(configured.ref)
        self.state.message = f"added configured test: {configured.ref}"
        return configured

    def remove_test(self, instance_id: str) -> bool:
        if self.state.running:
            self.state.message = "cannot change matrix while test matrix is running"
            return False
        try:
            removed = self.matrix.remove(instance_id)
        except KeyError as exc:
            self.state.message = str(exc)
            return False
        self._sync_matrix_state()
        self.state.message = f"removed configured test: {removed.ref}"
        return True

    def select_models(self, indices: set[int]) -> None:
        if not self.state.running:
            self.state.selected_model_ids = {self.state.models[index].id for index in sorted(indices) if 0 <= index < len(self.state.models)}

    def select_model_ids(self, model_ids: set[str]) -> None:
        if not self.state.running:
            available = {model.id for model in self.state.models}
            self.state.selected_model_ids = set(model_ids) & available

    def select_all_models(self) -> None:
        if not self.state.running:
            self.state.selected_model_ids = {model.id for model in self.state.models}

    def select_tests(self, indices: set[int]) -> None:
        if not self.state.running:
            self.state.selected_test_refs = {test_ref(self.state.tests[index]) for index in sorted(indices) if 0 <= index < len(self.state.tests)}

    def select_test_refs(self, refs: set[str]) -> None:
        if not self.state.running:
            available = {test_ref(test) for test in self.state.tests}
            self.state.selected_test_refs = set(refs) & available

    def select_all_tests(self) -> None:
        if not self.state.running:
            self.state.selected_test_refs = {test_ref(test) for test in self.state.tests}

    def run_selected(self) -> bool:
        if self.state.running:
            self.state.message = "test matrix already running"
            return False
        if self.state.profile_required:
            self.state.message = "system profile required before testing"
            return False
        models = list(self.state.selected_models)
        tests = list(self.state.selected_tests)
        if not models or not tests:
            self.state.message = "select at least one model and one configured test"
            return False
        self._run_control = RunControl()
        self.response_monitor.reset()
        self.state.running = True
        self.state.cancel_requested = False
        self.state.progress_completed = 0
        self.state.progress_total = len(models) * len(tests)
        self.state.progress_passed = 0
        self.state.progress_failed = 0
        self.state.progress_errors = 0
        self.state.progress_cancelled = 0
        self.state.progress_model_id = ""
        self.state.progress_test_ref = ""
        self.state.progress_phase = "starting"
        self.state.last_result = None
        self.state.message = f"test matrix started: {len(models)} model(s) x {len(tests)} configured test(s)"
        self.last_errors = []
        self._run_thread = threading.Thread(target=self._run_matrix, args=(models, tests, self._run_control), name="lmts-test-matrix", daemon=True)
        self._run_thread.start()
        return True

    def cancel(self) -> bool:
        if not self.state.running or self._run_control is None:
            self.state.message = "no test matrix is running"
            return False
        if not self.state.cancel_requested:
            self.state.cancel_requested = True
            self.state.progress_phase = "cancel_requested"
            self.state.message = "cancel requested; waiting for current model call to return"
            self._run_control.request_cancel()
        return True

    def _run_matrix(self, models, tests, control: RunControl) -> None:
        runner = TestRunner(self.providers, RunStore(self.results_root), response_sink=self.response_monitor.accept)
        benchmark_runner = BenchmarkRunner(runner)
        benchmark_store = BenchmarkStore(self.results_root)
        batch_ids: list[str] = []
        batch_paths: list[str] = []
        completed_before = 0
        try:
            for test in tests:
                if control.cancelled:
                    break
                def on_progress(event: BenchmarkProgress, *, offset: int = completed_before) -> None:
                    self.state.progress_model_id = event.model_id
                    self.state.progress_test_ref = event.test_ref
                    if event.phase == "starting":
                        self.response_monitor.reset(event.model_id)
                    if not self.state.cancel_requested:
                        self.state.progress_phase = event.phase
                    if event.phase == "starting":
                        self.state.progress_completed = offset + event.index - 1
                        return
                    self.state.progress_completed = offset + event.index
                    run = event.run
                    if run is None:
                        return
                    if run.status == "cancelled":
                        self.state.progress_cancelled += 1
                    elif run.status != "completed":
                        self.state.progress_errors += 1
                        if event.result_path is not None:
                            self.last_errors.append({"run_id": run.run_id, "model_id": run.model_id, "test_ref": run.test_ref, "result_path": str(event.result_path), "error": run.error})
                    elif run.passed is True:
                        self.state.progress_passed += 1
                    elif run.passed is False:
                        self.state.progress_failed += 1
                batch = benchmark_runner.run(test, models, self.workspace_root, progress=on_progress, control=control)
                if batch.run_ids:
                    path = benchmark_store.append(batch)
                    batch_ids.append(batch.batch_id)
                    batch_paths.append(str(path))
                    completed_before += len(batch.run_ids)
            self.state.last_result = {"matrix": f"{len(models)} model(s) x {len(tests)} configured test(s)", "runs": self.state.progress_completed, "passed": self.state.progress_passed, "failed": self.state.progress_failed, "errors": self.state.progress_errors, "cancelled": self.state.progress_cancelled, "batch_ids": ", ".join(batch_ids), "batch_paths": ", ".join(batch_paths)}
            if self.last_errors:
                self.state.last_result["error_log"] = "press e to export"
            if control.cancelled:
                self.state.progress_phase = "cancelled"
                self.state.message = f"test matrix cancelled: {self.state.progress_completed}/{self.state.progress_total} run(s) reached"
            else:
                self.state.progress_phase = "finished"
                self.state.message = f"test matrix finished: {self.state.progress_passed} passed, {self.state.progress_failed} failed, {self.state.progress_errors} error(s)"
        except Exception as exc:
            self.state.progress_errors += 1
            self.state.progress_phase = "error"
            self.state.message = f"test matrix aborted: {type(exc).__name__}: {exc}"
        finally:
            self.state.running = False
            self._run_control = None

    def export_errors(self, task: str = "task") -> Path | None:
        if not self.last_errors:
            self.state.message = "no errors to export"
            return None
        path = export_error_log(task, self.last_errors, root=self.logs_root)
        self.state.message = f"error log exported: {path}"
        return path

    def test_all(self) -> bool:
        if self.state.running:
            self.state.message = "test matrix already running"
            return False
        self.select_all_models()
        self.select_all_tests()
        return self.run_selected()

    def profile(self) -> Path | None:
        if self.state.running:
            self.state.message = "cannot profile while test matrix is running"
            return None
        profile = scan_system_profile()
        path = save_system_profile(profile, self.profile_path)
        self._sync_profile_state()
        data = profile.to_dict()
        self.state.last_result = {"cpu": data.get("cpu"), "memory": data.get("memory"), "gpu": data.get("gpu"), "npu": data.get("npu"), "profile_path": str(path)}
        self.state.message = f"system profile saved: {path}"
        return path
