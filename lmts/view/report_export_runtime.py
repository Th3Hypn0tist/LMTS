from __future__ import annotations

import curses
from pathlib import Path

from lmts.core.matrix_store import MatrixRunStore
from lmts.core.result_export import build_matrix_bundle
from lmts.core.settings import DEFAULT_SETTINGS_PATH, load_settings
from lmts.reporting import project_matrix_bundle
from lmts.reporting.single import project_run_result
from lmts.services.auth import AuthenticationError
from lmts.tools.report_export import export_report_json
from lmts.tools.report_publish import publish_report
from lmts.tools.report_targets import ReportTarget, configured_report_targets, resolve_report_target

from .actions.benchmark import BenchmarkActions
from .controller import LMTSViewController
from .lmts_host import LMTSInteractiveHost
from .tui_app import TUIApplication
from .tui_common import single_line

_ACTIVE_CONTROLLER: 'ReportExportController | None' = None

def _secret_line(stdscr: curses.window, title: str, *, maximum: int = 1024) -> str | None:
    """Read one non-empty secret without rendering the plaintext value."""
    value: list[str] = []
    try:
        while True:
            height, width = stdscr.getmaxyx()
            win_h = max(5, min(height - 2, 7))
            win_w = max(30, min(width - 2, 80))
            body_w = max(1, win_w - 4)
            win = curses.newwin(
                win_h,
                win_w,
                max(0, (height - win_h) // 2),
                max(0, (width - win_w) // 2),
            )
            win.keypad(True)
            win.erase()
            win.box()
            win.addnstr(0, 2, f" {title} ", max(0, win_w - 4))
            masked = '*' * min(len(value), body_w)
            win.addnstr(2, 2, masked, body_w)
            win.addnstr(win_h - 2, 2, 'Enter accept  Esc cancel', body_w, curses.A_DIM)
            try:
                curses.curs_set(1)
                win.move(2, 2 + min(len(masked), max(0, body_w - 1)))
            except curses.error:
                pass
            win.refresh()
            key = win.get_wch()
            if key == '\x1b':
                return None
            if key in ('\n', '\r') or key == curses.KEY_ENTER:
                if value:
                    return ''.join(value)
                continue
            if key in (curses.KEY_BACKSPACE, '\b', '\x7f'):
                if value:
                    value.pop()
                continue
            if isinstance(key, str) and key.isprintable() and len(value) < maximum:
                value.append(key)
    finally:
        try:
            curses.curs_set(0)
        except curses.error:
            pass

def _ensure_authenticated(
    host: LMTSInteractiveHost,
    stdscr: curses.window,
    controller: 'ReportExportController',
) -> bool:
    auth = controller.auth_service
    if auth is None:
        controller.state.message = 'registered user authentication is required before testing'
        return False
    try:
        if auth.current_identity() is not None:
            return True
    except AuthenticationError as exc:
        controller.state.message = f'cannot restore authentication: {exc}'
        return False

    username = single_line(host, stdscr, 'LMTS username')
    if username is None:
        controller.state.message = 'run cancelled: authentication required'
        return False
    password = _secret_line(stdscr, 'LMTS password')
    if password is None:
        controller.state.message = 'run cancelled: authentication required'
        return False
    try:
        identity = auth.login(username, password)
    except (AuthenticationError, RuntimeError, ValueError) as exc:
        controller.state.message = f'IAM login failed: {exc}'
        return False
    controller.user_service.clear()
    controller.state.message = f'authenticated: {identity.username}'
    return True

def _select_report_target(host: LMTSInteractiveHost, stdscr: curses.window) -> ReportTarget | None:
    settings = load_settings(DEFAULT_SETTINGS_PATH)
    targets = configured_report_targets(settings)
    if len(targets) == 1:
        return targets[0]
    chosen = host.choose(stdscr, 'Report target', [target.label for target in targets])
    return None if chosen is None else targets[chosen]

def _auto_publish_targets() -> tuple[ReportTarget, ...]:
    settings = load_settings(DEFAULT_SETTINGS_PATH)
    return tuple(resolve_report_target(settings, target_id) for target_id in settings.auto_publish_targets)

def _publish_one(report: dict[str, object], target: ReportTarget) -> str:
    return publish_report(report, target.profile, mysql=target.mysql)

def _publish_many(report: dict[str, object], targets: tuple[ReportTarget, ...]) -> None:
    failures: list[str] = []
    for target in targets:
        try:
            _publish_one(report, target)
        except (OSError, ValueError, RuntimeError) as exc:
            failures.append(f'{target.label}: {exc}')
    if failures:
        raise RuntimeError('auto-publish failed: ' + ' | '.join(failures))

class ReportExportController(LMTSViewController):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._next_publish_targets: tuple[ReportTarget, ...] = ()
        global _ACTIVE_CONTROLLER
        _ACTIVE_CONTROLLER = self

    def configure_next_publish(self, targets: tuple[ReportTarget, ...]) -> None:
        self._next_publish_targets = tuple(targets)

    def _consume_publish_callback(self):
        targets = self._next_publish_targets
        self._next_publish_targets = ()
        if not targets:
            return None
        def publish(run: dict[str, object]) -> None:
            _publish_many(project_run_result(run), targets)
        return publish

    def _launch(self, targets, tests) -> bool:
        return self._start_run(list(targets), list(tests), on_run_completed=self._consume_publish_callback())

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
        matrix_data = MatrixRunStore(controller.results_root).load(matrix_path)
        target_ids = [str(value) for value in (matrix_data.get('target_ids') or [])]
        if len(target_ids) != 1 or str(matrix_data.get('status') or '') == 'cancelled' or _auto_publish_targets():
            return
        report = self._completed_report(controller, matrix_path)
        action = self.choose(stdscr, 'Test complete', ['Export to server', 'Export to file', 'Keep local'], 0)
        if action is None or action == 2:
            return
        if action == 0:
            try:
                target = _select_report_target(self, stdscr)
                if target is None:
                    return
                self.message = f'published report: {_publish_one(report, target)}'
            except (OSError, ValueError, RuntimeError) as exc:
                self.message = f'report publish failed: {exc}; canonical result kept local'
            return
        settings = load_settings(DEFAULT_SETTINGS_PATH)
        self.message = f'exported report: {export_report_json(report, Path(settings.output_folder))}'

class ReportExportBenchmarkActions(BenchmarkActions):
    def _run_target_count(self, choice: int) -> int:
        if choice in {0, 1}:
            return len(self.controller.state.selected_targets)
        return sum(1 for target in self.controller.state.targets if target.kind == 'model')

    def before_run_choice(self, choice: int) -> bool:
        controller = self.controller
        if not isinstance(controller, ReportExportController):
            raise TypeError('report-aware benchmark actions require ReportExportController')
        if not _ensure_authenticated(self.host, self.stdscr, controller):
            self.set_message(controller.state.message)
            return False
        controller.configure_next_publish(())
        auto_targets = _auto_publish_targets()
        if auto_targets:
            controller.configure_next_publish(auto_targets)
            self.set_message(f'auto-publish enabled: {len(auto_targets)} output(s)')
            return True
        if self._run_target_count(choice) <= 1:
            return True
        publish_choice = self.host.choose(self.stdscr, 'Export reports to server as they complete?', ['Yes', 'No'], 0)
        if publish_choice is None:
            return False
        if publish_choice == 1:
            return True
        target = _select_report_target(self.host, self.stdscr)
        if target is None:
            self.set_message('run cancelled: no report target selected')
            return False
        controller.configure_next_publish((target,))
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
