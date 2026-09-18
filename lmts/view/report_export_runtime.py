from __future__ import annotations

import curses
from pathlib import Path

from lmts.core.matrix_store import MatrixRunStore
from lmts.core.result_export import build_matrix_bundle
from lmts.core.settings import DEFAULT_SETTINGS_PATH, load_settings
from lmts.reporting import project_matrix_bundle
from lmts.reporting.single import project_run_result
from lmts.tools.report_export import export_report_json
from lmts.tools.report_targets import ReportTarget, configured_report_targets, resolve_report_target
from lmts.tools.report_publish import publish_report

from .actions.benchmark import BenchmarkActions
from .controller import LMTSViewController
from .lmts_host import LMTSInteractiveHost
from .tui_app import TUIApplication


_ACTIVE_CONTROLLER: 'ReportExportController | None' = None


def _select_report_target(host: LMTSInteractiveHost, stdscr: curses.window) -> ReportTarget | None:
    settings = load_settings(DEFAULT_SETTINGS_PATH)
    targets = configured_report_targets(settings)
    if len(targets) == 1:
        return targets[0]
    chosen = host.choose(stdscr, 'Report target', [target.label for target in targets])
    return None if chosen is None else targets[chosen]


def _auto_publish_target() -> ReportTarget | None:
    settings = load_settings(DEFAULT_SETTINGS_PATH)
    if settings.auto_publish_target is None:
        return None
    return resolve_report_target(settings, settings.auto_publish_target)


class ReportExportController(LMTSViewController):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._next_publish_target: ReportTarget | None = None
        global _ACTIVE_CONTROLLER
        _ACTIVE_CONTROLLER = self

    def configure_next_publish(self, target: ReportTarget | None) -> None:
        self._next_publish_target = target

    def _consume_publish_callback(self):
        target = self._next_publish_target
        self._next_publish_target = None
        if target is None:
            return None

        def publish(run: dict[str, object]) -> None:
            publish_report(project_run_result(run), target.profile)

        return publish

    def _launch(self, targets, tests) -> bool:
        callback = self._consume_publish_callback()
        return self._start_run(list(targets), list(tests), on_run_completed=callback)

    def run_selected(self, *, on_run_completed=None) -> bool:
        if on_run_completed is not None:
            return super().run_selected(on_run_completed=on_run_completed)
        return self._launch(self.state.selected_targets, self.state.selected_tests)

    def run_all_tests(self, *, on_run_completed=None) -> bool:
        if on_run_completed is not None:
            return super().run_all_tests(on_run_completed=on_run_completed)
        return self._launch(self.state.selected_targets, self.state.tests)

    def run_all_tests_to_all_models(self, *, on_run_completed=None) -> bool:
        if on_run_completed is not None:
            return super().run_all_tests_to_all_models(on_run_completed=on_run_completed)
        models = [target for target in self.state.targets if target.kind == 'model']
        return self._launch(models, self.state.tests)

    def test_all(self, *, on_run_completed=None) -> bool:
        if on_run_completed is not None:
            return super().test_all(on_run_completed=on_run_completed)
        return self._launch(self.state.targets, self.state.tests)


class ReportExportHost(LMTSInteractiveHost):
    def __init__(self, *args, **kwargs) -> None:
        self._handled_completion_ids: set[str] = set()
        super().__init__(*args, on_idle=self._global_completion_idle, **kwargs)

    def _completed_report(self, controller: ReportExportController, matrix_path: Path) -> dict[str, object]:
        if not matrix_path.is_file():
            raise FileNotFoundError(f'canonical matrix result missing: {matrix_path}')
        matrix_data = MatrixRunStore(controller.results_root).load(matrix_path)
        bundle = build_matrix_bundle(matrix_data, results_root=controller.results_root)
        return project_matrix_bundle(bundle)

    def _global_completion_idle(self, stdscr: curses.window) -> None:
        controller = _ACTIVE_CONTROLLER
        if controller is None or controller.state.running:
            return

        result = controller.state.last_result if isinstance(controller.state.last_result, dict) else {}
        matrix_id = str(result.get('matrix_id') or '').strip()
        matrix_path_text = str(result.get('matrix_path') or '').strip()
        if not matrix_id or not matrix_path_text or matrix_id in self._handled_completion_ids:
            return

        self._handled_completion_ids.add(matrix_id)
        matrix_path = Path(matrix_path_text)
        try:
            matrix_data = MatrixRunStore(controller.results_root).load(matrix_path)
        except (OSError, ValueError) as exc:
            self.message = f'completion report failed: {exc}'
            return

        target_ids = [str(value) for value in (matrix_data.get('target_ids') or [])]
        if len(target_ids) != 1 or str(matrix_data.get('status') or '') == 'cancelled':
            return
        if _auto_publish_target() is not None:
            return

        try:
            report = self._completed_report(controller, matrix_path)
        except (OSError, ValueError) as exc:
            self.message = f'report projection failed: {exc}'
            return

        action = self.choose(
            stdscr,
            'Test complete',
            ['Export to server', 'Export to file', 'Keep local'],
            0,
        )
        if action is None or action == 2:
            self.message = f'kept local: {matrix_path}'
            return

        if action == 0:
            try:
                target = _select_report_target(self, stdscr)
                if target is None:
                    self.message = 'server export cancelled; canonical result kept local'
                    return
                report_id = publish_report(report, target.profile)
                self.message = f'published report: {report_id}'
            except (OSError, ValueError, RuntimeError) as exc:
                self.message = f'report publish failed: {exc}; canonical result kept local'
            return

        try:
            settings = load_settings(DEFAULT_SETTINGS_PATH)
            path = export_report_json(report, Path(settings.output_folder))
            self.message = f'exported report: {path}'
        except (OSError, ValueError) as exc:
            self.message = f'report file export failed: {exc}; canonical result kept local'


class ReportExportBenchmarkActions(BenchmarkActions):
    def _run_target_count(self, choice: int) -> int:
        if choice in {0, 1}:
            return len(self.controller.state.selected_targets)
        return sum(1 for target in self.controller.state.targets if target.kind == 'model')

    def before_run_choice(self, choice: int) -> bool:
        controller = self.controller
        if not isinstance(controller, ReportExportController):
            raise TypeError('report-aware benchmark actions require ReportExportController')

        controller.configure_next_publish(None)

        auto_target = _auto_publish_target()
        if auto_target is not None:
            controller.configure_next_publish(auto_target)
            self.set_message(f'auto-publish enabled: {auto_target.label}')
            return True

        if self._run_target_count(choice) <= 1:
            return True

        publish_choice = self.host.choose(
            self.stdscr,
            'Export reports to server as they complete?',
            ['Yes', 'No'],
            0,
        )
        if publish_choice is None:
            return False
        if publish_choice == 1:
            return True

        target = _select_report_target(self.host, self.stdscr)
        if profile is None:
            self.set_message('run cancelled: no report server selected')
            return False
        controller.configure_next_publish(target)
        return True


class ReportExportTUIApplication(TUIApplication):
    controller_class = ReportExportController
    host_class = ReportExportHost
    benchmark_actions_class = ReportExportBenchmarkActions


def run_tui() -> None:
    ReportExportTUIApplication().run()


def main() -> int:
    run_tui()
    return 0
