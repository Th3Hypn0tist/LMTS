from __future__ import annotations

from pathlib import Path

from lmts.core.control import RunControl
from lmts.core.executor import TestExecutor
from lmts.core.registry import ProviderRegistry
from lmts.services.evaluation import EvaluationService, RunCompletedCallback
from lmts.services.profile import SystemProfileService
from lmts.services.results import ResultService
from lmts.services.run_lifecycle import RunLifecycleService
from lmts.services.targets import TargetDiscoveryService
from lmts.tests.base import TestModule, test_ref
from lmts.tests.catalog import test_matrix_for_level
from lmts.tests.types import ConfiguredTest, TestLevel, TestMatrix, TestTypeRegistry
from lmts.tools.profile import DEFAULT_PROFILE_PATH

from .evaluation_state import EvaluationViewState
from .projector import LMTSViewState
from .response_monitor import ResponseMonitor


class LMTSViewController:
    def __init__(
        self,
        providers: ProviderRegistry,
        test_types: TestTypeRegistry,
        matrix: TestMatrix,
        *,
        results_root: Path = Path('results'),
        workspace_root: Path = Path('.lmts/workspaces'),
        logs_root: Path = Path('logs'),
        profile_path: Path = DEFAULT_PROFILE_PATH,
    ) -> None:
        self.providers = providers
        self.test_types = test_types
        self.matrix = matrix
        self.results_root = results_root
        self.workspace_root = workspace_root
        self.logs_root = logs_root
        self.profile_path = profile_path
        self.state = LMTSViewState(tests=list(matrix.tests()), suite_level='moderate')
        self.response_monitor = ResponseMonitor()
        self.last_errors: list[dict[str, object]] = []
        self.last_publish_errors: list[dict[str, str]] = []

        self.profile_service = SystemProfileService(profile_path)
        self.target_service = TargetDiscoveryService(providers)
        self.result_service = ResultService(results_root=results_root, logs_root=logs_root)
        self.lifecycle = RunLifecycleService()
        self.evaluation_service = EvaluationService(
            providers,
            results_root=results_root,
            workspace_root=workspace_root,
            response_sink=self.response_monitor.accept,
            system_context_loader=self.profile_service.context,
        )
        self.evaluation_view = EvaluationViewState(
            self.state,
            self.response_monitor,
            self.evaluation_service,
        )
        self._sync_profile_state()

    def _sync_profile_state(self) -> None:
        status = self.profile_service.status()
        self.state.profile_required = status.required
        self.state.profiled_at = status.profiled_at

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
            self.state.message = 'cannot change suite while test matrix is running'
            return False
        self.matrix = test_matrix_for_level(level, self.test_types)
        self.state.suite_level = level
        self._sync_matrix_state()
        self.state.selected_test_refs = {test_ref(test) for test in self.state.tests}
        self._clear_live_matrix()
        self.state.message = f'suite level: {level.upper()} ({len(self.state.tests)} configured test(s))'
        return True

    def refresh(self) -> None:
        if self.state.running:
            self.state.message = 'cannot refresh while test matrix is running'
            return
        previous_targets = set(self.state.selected_target_ids)
        try:
            self.state.targets = self.target_service.discover()
        except (OSError, ValueError) as exc:
            self.state.targets = []
            self.state.selected_target_ids = set()
            self.state.message = f'target discovery failed: {exc}'
            return
        available_target_ids = {target.id for target in self.state.targets}
        self.state.selected_target_ids = previous_targets & available_target_ids
        if not self.state.selected_target_ids and self.state.targets:
            self.state.selected_target_ids = {self.state.targets[0].id}
        self._sync_matrix_state()
        self._sync_profile_state()
        counts = {
            kind: sum(1 for target in self.state.targets if target.kind == kind)
            for kind in ('model', 'bot', 'composition')
        }
        self.state.message = (
            f"discovered {len(self.state.targets)} target(s): {counts['model']} model, {counts['bot']} bot, "
            f"{counts['composition']} composition; {self.state.suite_level.upper()} suite has "
            f"{len(self.state.tests)} configured test(s), registry has {len(self.test_types.definitions())} test type(s)"
        )
        if self.state.profile_required:
            self.state.message += '; system profile required before testing'

    def recent_results(self, *, limit: int = 200) -> list[tuple[Path, dict]]:
        return self.result_service.recent_results(limit=limit)

    def recent_matrices(self, *, limit: int = 100) -> list[tuple[Path, dict]]:
        return self.result_service.recent_matrices(limit=limit)

    def add_test(
        self,
        type_ref: str,
        instance_id: str,
        params: dict[str, object] | None = None,
    ) -> ConfiguredTest | None:
        if self.state.running:
            self.state.message = 'cannot change matrix while test matrix is running'
            return None
        try:
            configured = self.test_types.get(type_ref).configure(instance_id, params)
            self.matrix.add(configured)
        except (KeyError, ValueError) as exc:
            self.state.message = f'cannot add test: {exc}'
            return None
        self._sync_matrix_state()
        self.state.selected_test_refs.add(configured.ref)
        self._clear_live_matrix()
        self.state.message = f'added configured test: {configured.ref}'
        return configured

    def remove_test(self, instance_id: str) -> bool:
        if self.state.running:
            self.state.message = 'cannot change matrix while test matrix is running'
            return False
        try:
            removed = self.matrix.remove(instance_id)
        except KeyError as exc:
            self.state.message = str(exc)
            return False
        self._sync_matrix_state()
        self._clear_live_matrix()
        self.state.message = f'removed configured test: {removed.ref}'
        return True

    def select_targets(self, indices: set[int]) -> None:
        if not self.state.running:
            self.state.selected_target_ids = {
                self.state.targets[index].id
                for index in sorted(indices)
                if 0 <= index < len(self.state.targets)
            }
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
            self.state.selected_test_refs = {
                test_ref(self.state.tests[index])
                for index in sorted(indices)
                if 0 <= index < len(self.state.tests)
            }
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

    def _start_run(
        self,
        targets: list[TestExecutor],
        tests: list[TestModule],
        *,
        on_run_completed: RunCompletedCallback | None = None,
    ) -> bool:
        if self.state.running:
            self.state.message = 'test matrix already running'
            return False
        if self.state.profile_required:
            self.state.message = 'system profile required before testing'
            return False
        if not targets or not tests:
            self.state.message = 'select at least one target and one configured test'
            return False

        self.last_errors = []
        self.last_publish_errors = []
        self.evaluation_view.prepare(targets, tests)
        started = self.lifecycle.start(
            lambda control: self._run_matrix(targets, tests, control, on_run_completed),
        )
        if started:
            return True
        self.evaluation_view.finish()
        self.state.message = 'test matrix already running'
        return False

    def _run_matrix(
        self,
        targets: list[TestExecutor],
        tests: list[TestModule],
        control: RunControl,
        on_run_completed: RunCompletedCallback | None,
    ) -> None:
        try:
            outcome = self.evaluation_service.execute(
                targets,
                tests,
                control,
                progress=self.evaluation_view.progress,
                on_run_completed=on_run_completed,
            )
            self.last_errors = list(outcome.run_errors)
            self.last_publish_errors = list(outcome.publish_errors)
            self.evaluation_view.apply_outcome(outcome, targets, tests)
        except Exception as exc:
            self.evaluation_view.abort(exc)
        finally:
            self.evaluation_view.finish()

    def run_selected(self, *, on_run_completed: RunCompletedCallback | None = None) -> bool:
        return self._start_run(
            list(self.state.selected_targets),
            list(self.state.selected_tests),
            on_run_completed=on_run_completed,
        )

    def run_all_tests(self, *, on_run_completed: RunCompletedCallback | None = None) -> bool:
        return self._start_run(
            list(self.state.selected_targets),
            list(self.state.tests),
            on_run_completed=on_run_completed,
        )

    def run_all_tests_to_all_models(self, *, on_run_completed: RunCompletedCallback | None = None) -> bool:
        models = [target for target in self.state.targets if target.kind == 'model']
        return self._start_run(models, list(self.state.tests), on_run_completed=on_run_completed)

    def test_all(self, *, on_run_completed: RunCompletedCallback | None = None) -> bool:
        return self._start_run(
            list(self.state.targets),
            list(self.state.tests),
            on_run_completed=on_run_completed,
        )

    def cancel(self) -> bool:
        if not self.state.running:
            self.state.message = 'no test matrix is running'
            return False
        if self.state.cancel_requested:
            return True
        self.state.cancel_requested = True
        self.state.progress_phase = 'cancel_requested'
        self.state.message = 'cancel requested; waiting for current target call to return'
        if self.lifecycle.request_cancel():
            return True
        self.state.message = 'no test matrix is running'
        self.state.running = False
        return False

    def export_errors(self, task: str = 'task') -> Path | None:
        if not self.last_errors:
            self.state.message = 'no errors to export'
            return None
        path = self.result_service.export_errors(task, self.last_errors)
        self.state.message = f'error log exported: {path}'
        return path

    def profile(self) -> Path | None:
        if self.state.running:
            self.state.message = 'cannot profile while test matrix is running'
            return None
        result = self.profile_service.scan()
        self.state.profile_required = result.status.required
        self.state.profiled_at = result.status.profiled_at
        self.state.last_result = {
            'cpu': result.data.get('cpu'),
            'memory': result.data.get('memory'),
            'gpu': result.data.get('gpu'),
            'npu': result.data.get('npu'),
            'profile_path': str(result.path),
        }
        self.state.message = f'system profile saved: {result.path}'
        return result.path
