from __future__ import annotations

from pathlib import Path

from lmts.core.control import RunControl
from lmts.core.settings import MySQLSettings
from lmts.core.executor import TestExecutor
from lmts.core.registry import ProviderRegistry
from lmts.repositories.stats import StatsRepository
from lmts.repositories.system import SystemRepository
from lmts.repositories.user import UserRepository
from lmts.services.auth import AuthService
from lmts.services.evaluation import EvaluationService, RunCompletedCallback
from lmts.services.profile import DEFAULT_PROFILE_PATH, SystemProfileService
from lmts.services.results import ResultService
from lmts.services.run_lifecycle import RunLifecycleService
from lmts.services.stats import StatsService
from lmts.services.system import SystemService
from lmts.services.targets import TargetDiscoveryService
from lmts.services.user import UserService
from lmts.tests.base import TestModule
from lmts.tests.types import ConfiguredTest, TestLevel, TestMatrix, TestTypeRegistry

from .evaluation_state import EvaluationViewState
from .matrix_state import MatrixViewState
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
        mysql: MySQLSettings | None = None,
    ) -> None:
        self.providers = providers
        self.test_types = test_types
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
        self.user_repository = None if mysql is None else UserRepository(mysql)
        self.system_repository = None if mysql is None else SystemRepository(mysql)
        self.auth_service = AuthService()
        self.system_service = None if self.system_repository is None else SystemService(self.system_repository, self.profile_service)
        self.stats_service = None if mysql is None else StatsService(StatsRepository(mysql))
        self.user_service = UserService(self.user_repository, self.auth_service)
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
        self.matrix_view = MatrixViewState(self.state, test_types, matrix)
        self._sync_profile_state()
    @property
    def matrix(self) -> TestMatrix:
        return self.matrix_view.matrix
    def _sync_profile_state(self) -> None:
        status = self.profile_service.status()
        self.state.profile_required = status.required
        self.state.profiled_at = status.profiled_at
    def set_suite_level(self, level: TestLevel) -> bool:
        return self.matrix_view.set_suite_level(level)
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
        self.matrix_view.sync()
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
        return self.matrix_view.add_test(type_ref, instance_id, params)

    def remove_test(self, instance_id: str) -> bool:
        return self.matrix_view.remove_test(instance_id)

    def select_targets(self, indices: set[int]) -> None:
        self.matrix_view.select_targets(indices)

    def select_target_ids(self, target_ids: set[str]) -> None:
        self.matrix_view.select_target_ids(target_ids)

    def select_all_targets(self) -> None:
        self.matrix_view.select_all_targets()

    def select_tests(self, indices: set[int]) -> None:
        self.matrix_view.select_tests(indices)

    def select_test_refs(self, refs: set[str]) -> None:
        self.matrix_view.select_test_refs(refs)

    def select_all_tests(self) -> None:
        self.matrix_view.select_all_tests()

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
        if self.auth_service.local_mode:
            provenance: dict[str, object] = {}
        else:
            if self.system_service is None:
                self.state.message = 'local system persistence is not configured'
                return False
            try:
                identity = self.auth_service.require_identity()
                provenance = self.system_service.run_provenance(identity.user_id).to_dict()
            except (RuntimeError, ValueError) as exc:
                self.state.message = f'cannot start test: {exc}'
                return False

        self.last_errors = []
        self.last_publish_errors = []
        self.evaluation_view.prepare(targets, tests)
        started = self.lifecycle.start(
            lambda control: self._run_matrix(targets, tests, control, on_run_completed, provenance),
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
        provenance: dict[str, object],
    ) -> None:
        try:
            outcome = self.evaluation_service.execute(
                targets,
                tests,
                control,
                progress=self.evaluation_view.progress,
                on_run_completed=on_run_completed,
                provenance=provenance,
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
