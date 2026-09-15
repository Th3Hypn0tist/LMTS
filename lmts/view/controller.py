from __future__ import annotations

import threading
import uuid
from pathlib import Path

from lmts.core.benchmark_runner import BenchmarkProgress, BenchmarkRunner
from lmts.core.benchmark_store import BenchmarkStore
from lmts.core.control import RunControl
from lmts.core.executor import ModelExecutor, TestExecutor
from lmts.core.matrix_store import MatrixCell, MatrixRunRecord, MatrixRunStore
from lmts.core.registry import ProviderRegistry
from lmts.core.run import utc_now
from lmts.core.runner import TestRunner
from lmts.core.runtime_targets import executor_from_definition, load_runtime_targets
from lmts.core.store import RunStore
from lmts.lib.errorlog import export_error_log
from lmts.tests.base import test_ref
from lmts.tests.catalog import test_matrix_for_level
from lmts.tests.types import ConfiguredTest, TestLevel, TestMatrix, TestTypeRegistry
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
        self.state = LMTSViewState(tests=list(matrix.tests()), suite_level="moderate")
        self.response_monitor = ResponseMonitor()
        self.last_errors: list[dict[str, object]] = []
        self._run_thread: threading.Thread | None = None
        self._run_control: RunControl | None = None
        self._sync_profile_state()

    def _system_context(self) -> dict[str, object]:
        payload = load_system_profile(self.profile_path)
        if payload is None:
            raise ValueError("valid canonical system profile required before testing")
        return payload

    def _sync_profile_state(self) -> None:
        payload = load_system_profile(self.profile_path)
        self.state.profile_required = payload is None
        self.state.profiled_at = str(payload.get("profiled_at") or "") if payload is not None else ""

    def _clear_live_matrix(self) -> None:
        self.state.live_target_ids = ()
        self.state.live_target_kinds = {}
        self.state.live_test_refs = ()
        self.state.live_cells = {}

    def _sync_matrix_state(self) -> None:
        previous = set(self.state.selected_test_refs)
        self.state.tests = list(self.matrix.tests())
        available = {test_ref(test) for test in self.state.tests}
        self.state.selected_test_refs = previous & available
        if not self.state.selected_test_refs and self.state.tests:
            self.state.selected_test_refs = set(available)

    def set_suite_level(self, level: TestLevel) -> bool:
        if self.state.running:
            self.state.message = "cannot change suite while test matrix is running"
            return False
        self.matrix = test_matrix_for_level(level, self.test_types)
        self.state.suite_level = level
        self._sync_matrix_state()
        self.state.selected_test_refs = {test_ref(test) for test in self.state.tests}
        self._clear_live_matrix()
        self.state.message = f"suite level: {level.upper()} ({len(self.state.tests)} configured test(s))"
        return True

    def _discover_targets(self) -> list[TestExecutor]:
        targets: list[TestExecutor] = []
        for model in self.providers.discover_models():
            targets.append(ModelExecutor(self.providers.provider(model.provider_ref), model))
        for definition in load_runtime_targets():
            targets.append(executor_from_definition(definition))
        ids = [target.id for target in targets]
        if len(ids) != len(set(ids)):
            raise ValueError("evaluation target ids must be unique across models, bots and compositions")
        return sorted(targets, key=lambda item: (item.kind, item.id.casefold()))

    def refresh(self) -> None:
        if self.state.running:
            self.state.message = "cannot refresh while test matrix is running"
            return
        previous_targets = set(self.state.selected_target_ids)
        try:
            self.state.targets = self._discover_targets()
        except (OSError, ValueError) as exc:
            self.state.targets = []
            self.state.selected_target_ids = set()
            self.state.message = f"target discovery failed: {exc}"
            return
        available_target_ids = {target.id for target in self.state.targets}
        self.state.selected_target_ids = previous_targets & available_target_ids
        if not self.state.selected_target_ids and self.state.targets:
            self.state.selected_target_ids = {self.state.targets[0].id}
        self._sync_matrix_state()
        self._sync_profile_state()
        counts = {kind: sum(1 for target in self.state.targets if target.kind == kind) for kind in ("model", "bot", "composition")}
        self.state.message = (
            f"discovered {len(self.state.targets)} target(s): {counts['model']} model, {counts['bot']} bot, "
            f"{counts['composition']} composition; {self.state.suite_level.upper()} suite has "
            f"{len(self.state.tests)} configured test(s), registry has {len(self.test_types.definitions())} test type(s)"
        )
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

    def recent_matrices(self, *, limit: int = 100) -> list[tuple[Path, dict]]:
        store = MatrixRunStore(self.results_root)
        paths = store.iter_paths()
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
        self._clear_live_matrix()
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
        self._clear_live_matrix()
        self.state.message = f"removed configured test: {removed.ref}"
        return True

    def select_targets(self, indices: set[int]) -> None:
        if not self.state.running:
            self.state.selected_target_ids = {self.state.targets[index].id for index in sorted(indices) if 0 <= index < len(self.state.targets)}
            self._clear_live_matrix()

    def select_target_ids(self, target_ids: set[str]) -> None:
        if not self.state.running:
            available = {target.id for target in self.state.targets}
            self.state.selected_target_ids = set(target_ids) & available
            self._clear_live_matrix()

    def select_all_targets(self) -> None:
        if not self.state.running:
            self.state.selected_target_ids = {target.id for target in self.state.targets}
            self._clear_live_matrix()

    def select_tests(self, indices: set[int]) -> None:
        if not self.state.running:
            self.state.selected_test_refs = {test_ref(self.state.tests[index]) for index in sorted(indices) if 0 <= index < len(self.state.tests)}
            self._clear_live_matrix()

    def select_test_refs(self, refs: set[str]) -> None:
        if not self.state.running:
            available = {test_ref(test) for test in self.state.tests}
            self.state.selected_test_refs = set(refs) & available
            self._clear_live_matrix()

    def select_all_tests(self) -> None:
        if not self.state.running:
            self.state.selected_test_refs = {test_ref(test) for test in self.state.tests}
            self._clear_live_matrix()

    def _start_run(self, targets: list[TestExecutor], tests: list[ConfiguredTest]) -> bool:
        if self.state.running:
            self.state.message = "test matrix already running"
            return False
        if self.state.profile_required:
            self.state.message = "system profile required before testing"
            return False
        if not targets or not tests:
            self.state.message = "select at least one target and one configured test"
            return False
        self._run_control = RunControl()
        self.response_monitor.reset()
        self.state.running = True
        self.state.cancel_requested = False
        self.state.progress_completed = 0
        self.state.progress_total = len(targets) * len(tests)
        self.state.progress_passed = 0
        self.state.progress_failed = 0
        self.state.progress_errors = 0
        self.state.progress_cancelled = 0
        self.state.progress_target_id = ""
        self.state.progress_test_ref = test_ref(tests[0])
        self.state.progress_phase = "starting"
        self.state.live_target_ids = tuple(target.id for target in targets)
        self.state.live_target_kinds = {target.id: target.kind for target in targets}
        self.state.live_test_refs = tuple(test_ref(test) for test in tests)
        self.state.live_cells = {
            (target.id, test_ref(test)): "-"
            for target in targets
            for test in tests
        }
        self.state.last_result = None
        self.state.message = f"test matrix started: {len(targets)} target(s) x {len(tests)} configured test(s)"
        self.last_errors = []
        self._run_thread = threading.Thread(target=self._run_matrix, args=(targets, tests, self._run_control), name="lmts-test-matrix", daemon=True)
        self._run_thread.start()
        return True

    def run_selected(self) -> bool:
        return self._start_run(list(self.state.selected_targets), list(self.state.selected_tests))

    def run_all_tests(self) -> bool:
        return self._start_run(list(self.state.selected_targets), list(self.state.tests))

    def run_all_tests_to_all_models(self) -> bool:
        models = [target for target in self.state.targets if target.kind == "model"]
        return self._start_run(models, list(self.state.tests))

    def cancel(self) -> bool:
        if not self.state.running or self._run_control is None:
            self.state.message = "no test matrix is running"
            return False
        if not self.state.cancel_requested:
            self.state.cancel_requested = True
            self.state.progress_phase = "cancel_requested"
            self.state.message = "cancel requested; waiting for current target call to return"
            self._run_control.request_cancel()
        return True

    def _run_matrix(self, targets, tests, control: RunControl) -> None:
        runner = TestRunner(
            self.providers,
            RunStore(self.results_root),
            response_sink=self.response_monitor.accept,
            system_context_loader=self._system_context,
        )
        benchmark_runner = BenchmarkRunner(runner)
        benchmark_store = BenchmarkStore(self.results_root)
        matrix_store = MatrixRunStore(self.results_root)
        matrix_id = uuid.uuid4().hex
        matrix_started_at = utc_now()
        matrix_cells: list[MatrixCell] = []
        batch_ids: list[str] = []
        batch_paths: list[str] = []
        completed_before = 0
        try:
            for test in tests:
                if control.cancelled:
                    break

                def on_progress(event: BenchmarkProgress, *, offset: int = completed_before) -> None:
                    self.state.progress_target_id = event.target_id
                    self.state.progress_test_ref = event.test_ref
                    if event.phase == "starting":
                        self.response_monitor.reset(event.target_id)
                        self.state.live_cells[(event.target_id, event.test_ref)] = "RUN"
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
                        verdict = "CANCEL"
                    elif run.status != "completed":
                        verdict = "ERROR"
                    elif run.passed is True:
                        verdict = "PASS"
                    elif run.passed is False:
                        verdict = "FAIL"
                    else:
                        verdict = "?"
                    self.state.live_cells[(run.executor_id, run.test_ref)] = verdict
                    if event.result_path is not None:
                        matrix_cells.append(
                            MatrixCell(
                                target_id=run.executor_id,
                                target_kind=run.executor_kind,
                                test_ref=run.test_ref,
                                run_id=run.run_id,
                                status=run.status,
                                passed=run.passed,
                                result_path=str(event.result_path),
                            )
                        )
                    if run.status == "cancelled":
                        self.state.progress_cancelled += 1
                    elif run.status != "completed":
                        self.state.progress_errors += 1
                        if event.result_path is not None:
                            self.last_errors.append({"run_id": run.run_id, "target_id": run.executor_id, "target_kind": run.executor_kind, "test_ref": run.test_ref, "result_path": str(event.result_path), "error": run.error})
                    elif run.passed is True:
                        self.state.progress_passed += 1
                    elif run.passed is False:
                        self.state.progress_failed += 1

                batch = benchmark_runner.run(test, targets, self.workspace_root, progress=on_progress, control=control)
                if batch.run_ids:
                    path = benchmark_store.append(batch)
                    batch_ids.append(batch.batch_id)
                    batch_paths.append(str(path))
                    completed_before += len(batch.run_ids)

            matrix_status = "cancelled" if control.cancelled else "completed"
            record = MatrixRunRecord(
                matrix_id=matrix_id,
                started_at=matrix_started_at,
                completed_at=utc_now(),
                status=matrix_status,
                target_ids=[target.id for target in targets],
                target_kinds={target.id: target.kind for target in targets},
                test_refs=[test_ref(test) for test in tests],
                cells=matrix_cells,
                passed=self.state.progress_passed,
                failed=self.state.progress_failed,
                errors=self.state.progress_errors,
                cancelled=self.state.progress_cancelled,
            )
            matrix_path = matrix_store.append(record)
            self.state.last_result = {
                "suite_level": self.state.suite_level,
                "matrix": f"{len(targets)} target(s) x {len(tests)} configured test(s)",
                "matrix_id": matrix_id,
                "matrix_path": str(matrix_path),
                "runs": self.state.progress_completed,
                "passed": self.state.progress_passed,
                "failed": self.state.progress_failed,
                "errors": self.state.progress_errors,
                "cancelled": self.state.progress_cancelled,
                "batch_ids": ", ".join(batch_ids),
                "batch_paths": ", ".join(batch_paths),
            }
            if self.last_errors:
                self.state.last_result["error_log"] = "Output -> Export errors"
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
        return self._start_run(list(self.state.targets), list(self.state.tests))

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
