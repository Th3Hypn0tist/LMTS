from __future__ import annotations

import curses
from pathlib import Path

from lmts.core.matrix_store import MatrixRunStore
from lmts.core.result_export import build_matrix_bundle
from lmts.core.settings import DEFAULT_SETTINGS_PATH, load_settings
from lmts.core.store import RunStore
from lmts.reporting import project_matrix_bundle
from lmts.reporting.single import project_run_result
from lmts.tools.report_export import export_report_json
from lmts.tools.report_profiles import ReportProfile, load_report_profiles
from lmts.tools.report_publish import publish_report

from .controller import LMTSViewController
from .lmts_host import LMTSInteractiveHost
from .output_dialog import choose_report_profile


_ACTIVE_CONTROLLER: 'ReportExportController | None' = None


def _select_report_profile(host: LMTSInteractiveHost, stdscr: curses.window) -> ReportProfile | None:
    profiles = load_report_profiles().profiles
    if len(profiles) == 1:
        return profiles[0]
    return choose_report_profile(host, stdscr)


class ReportExportController(LMTSViewController):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._next_publish_profile: ReportProfile | None = None
        self.completion_export_pending = False
        global _ACTIVE_CONTROLLER
        _ACTIVE_CONTROLLER = self

    def configure_next_publish(self, profile: ReportProfile | None) -> None:
        self._next_publish_profile = profile

    def _consume_publish_callback(self):
        profile = self._next_publish_profile
        self._next_publish_profile = None
        if profile is None:
            return None

        def publish(run: dict[str, object]) -> None:
            publish_report(project_run_result(run), profile)

        return publish

    def _launch(self, targets, tests) -> bool:
        targets = list(targets)
        tests = list(tests)
        callback = self._consume_publish_callback()
        started = self._start_run(targets, tests, on_run_completed=callback)
        self.completion_export_pending = bool(started and len(targets) == 1 and callback is None)
        return started

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
        super().__init__(*args, on_idle=self._report_export_idle, **kwargs)

    def _run_shape(self, choice: int) -> tuple[int, int]:
        controller = _ACTIVE_CONTROLLER
        if controller is None:
            return 0, 0
        if choice == 0:
            return len(controller.state.selected_targets), len(controller.state.selected_tests)
        if choice == 1:
            return len(controller.state.selected_targets), len(controller.state.tests)
        model_count = sum(1 for target in controller.state.targets if target.kind == 'model')
        return model_count, len(controller.state.tests)

    def choose(self, stdscr: curses.window, title: str, options, selected: int = 0):
        choice = super().choose(stdscr, title, options, selected)
        if choice is None or title != 'Run' or tuple(options) != ('Run', 'Run all tests', 'Run all tests to all models'):
            return choice

        controller = _ACTIVE_CONTROLLER
        if controller is None:
            return choice
        controller.configure_next_publish(None)
        target_count, _ = self._run_shape(choice)
        if target_count <= 1:
            return choice

        publish_choice = super().choose(
            stdscr,
            'Export reports to server as they complete?',
            ['Yes', 'No'],
            0,
        )
        if publish_choice is None:
            return None
        if publish_choice == 1:
            return choice

        profile = _select_report_profile(self, stdscr)
        if profile is None:
            self.message = 'run cancelled: no report server selected'
            return None
        controller.configure_next_publish(profile)
        return choice

    def _completed_report(self, controller: ReportExportController) -> tuple[dict[str, object], Path]:
        result = controller.state.last_result if isinstance(controller.state.last_result, dict) else {}

        single_path = str(result.get('single_run_path') or '').strip()
        if single_path:
            evidence_path = Path(single_path)
            if not evidence_path.is_file():
                raise FileNotFoundError(f'canonical run result missing: {evidence_path}')
            run_data = RunStore(controller.results_root).load(evidence_path)
            return project_run_result(run_data), evidence_path

        matrix_path_text = str(result.get('matrix_path') or '').strip()
        if not matrix_path_text:
            raise ValueError('completed test set is missing canonical matrix path')
        evidence_path = Path(matrix_path_text)
        if not evidence_path.is_file():
            raise FileNotFoundError(f'canonical matrix result missing: {evidence_path}')
        matrix_data = MatrixRunStore(controller.results_root).load(evidence_path)
        bundle = build_matrix_bundle(matrix_data, results_root=controller.results_root)
        return project_matrix_bundle(bundle), evidence_path

    def _report_export_idle(self, stdscr: curses.window) -> None:
        controller = _ACTIVE_CONTROLLER
        if controller is None or controller.state.running or not controller.completion_export_pending:
            return

        controller.completion_export_pending = False
        try:
            report, evidence_path = self._completed_report(controller)
        except (OSError, ValueError) as exc:
            self.message = f'report projection failed: {exc}'
            return

        action = super().choose(
            stdscr,
            'Test complete',
            ['Export to server', 'Export to file', 'Keep local'],
            0,
        )
        if action is None or action == 2:
            self.message = f'kept local: {evidence_path}'
            return

        if action == 0:
            try:
                profile = _select_report_profile(self, stdscr)
                if profile is None:
                    self.message = 'server export cancelled; canonical result kept local'
                    return
                report_id = publish_report(report, profile)
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


def run_tui() -> None:
    from . import tui

    tui.LMTSViewController = ReportExportController
    tui.RegistrySplitCursesViewHost = ReportExportHost
    tui.run()


def main() -> int:
    run_tui()
    return 0
