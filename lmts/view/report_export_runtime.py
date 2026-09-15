from __future__ import annotations

import curses
from pathlib import Path

from lmts.core.matrix_store import MatrixRunStore
from lmts.core.result_export import build_matrix_bundle
from lmts.core.settings import DEFAULT_SETTINGS_PATH, load_settings
from lmts.reporting import project_matrix_bundle
from lmts.reporting.single import project_run_result
from lmts.tools.report_export import export_report_json
from lmts.tools.report_profiles import ReportProfile, load_report_profiles
from lmts.tools.report_publish import publish_report

from .controller import LMTSViewController
from .lmts_host import LMTSInteractiveHost
from .output_dialog import choose_report_profile


_ACTIVE_CONTROLLER: 'ReportExportController | None' = None
_ACTIVE_HOST: 'ReportExportHost | None' = None
_RUN_OPTIONS = ('Run', 'Run all tests', 'Run all tests to all models')


def _select_report_profile(host: LMTSInteractiveHost, stdscr: curses.window) -> ReportProfile | None:
    profiles = load_report_profiles().profiles
    if len(profiles) == 1:
        return profiles[0]
    return choose_report_profile(host, stdscr)


class ReportExportController(LMTSViewController):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._next_publish_profile: ReportProfile | None = None
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
        global _ACTIVE_HOST
        _ACTIVE_HOST = self

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

        # Claim the event before opening any modal so one completed matrix can
        # never produce duplicate dialogs on subsequent idle ticks.
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

        try:
            report = self._completed_report(controller, matrix_path)
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
            self.message = f'kept local: {matrix_path}'
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


def _run_target_count(controller: ReportExportController, choice: int) -> int:
    if choice == 0:
        return len(controller.state.selected_targets)
    if choice == 1:
        return len(controller.state.selected_targets)
    return sum(1 for target in controller.state.targets if target.kind == 'model')


def _install_run_publish_prompt(tui_module) -> None:
    current = tui_module.choose_with_preview
    original = getattr(current, '_lmts_report_original', current)

    def choose_with_report_prompt(stdscr, title, options, preview, *args, **kwargs):
        choice = original(stdscr, title, options, preview, *args, **kwargs)
        if choice is None or title != 'Run' or tuple(options) != _RUN_OPTIONS:
            return choice

        controller = _ACTIVE_CONTROLLER
        host = _ACTIVE_HOST
        if controller is None or host is None:
            return choice

        controller.configure_next_publish(None)
        if _run_target_count(controller, choice) <= 1:
            return choice

        publish_choice = host.choose(
            stdscr,
            'Export reports to server as they complete?',
            ['Yes', 'No'],
            0,
        )
        if publish_choice is None:
            return None
        if publish_choice == 1:
            return choice

        profile = _select_report_profile(host, stdscr)
        if profile is None:
            host.message = 'run cancelled: no report server selected'
            return None
        controller.configure_next_publish(profile)
        return choice

    choose_with_report_prompt._lmts_report_original = original
    tui_module.choose_with_preview = choose_with_report_prompt


def run_tui() -> None:
    from . import tui

    tui.LMTSViewController = ReportExportController
    tui.RegistrySplitCursesViewHost = ReportExportHost
    _install_run_publish_prompt(tui)
    tui.run()


def main() -> int:
    run_tui()
    return 0
