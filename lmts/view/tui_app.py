from __future__ import annotations

import curses

from lmts.cli import default_provider_registry
from lmts.lib.view import UIEventBus
from lmts.services.settings import SettingsService
from lmts.tests.catalog import default_test_matrix, default_test_type_registry

from .actions.benchmark import BenchmarkActions
from .actions.navigation import NavigationActions
from .actions.profile import ProfileActions
from .actions.results import ResultActions
from .actions.settings import SettingsActions
from .actions.user import UserActions
from .controller import LMTSViewController
from .cw_bench_page import CWBenchPage
from .lmts_host import LMTSInteractiveHost
from .model_downloader_page import ModelDownloaderPage
from .projector import LMTSViewProjector
from .registries import TAB_REGISTRY, build_shortcut_registry
from .tui_render import TUIRenderer
from .tui_state import TUIState


class TUIApplication:
    controller_class = LMTSViewController
    host_class = LMTSInteractiveHost
    benchmark_actions_class = BenchmarkActions

    def __init__(self) -> None:
        settings_service = SettingsService()
        settings = settings_service.load_core()
        test_types = default_test_type_registry()
        matrix = default_test_matrix(test_types)
        controller = self.controller_class(default_provider_registry(), test_types, matrix, mysql=settings.mysql)
        controller.refresh()
        shortcut_overrides = settings_service.load_shortcuts()
        shortcuts = build_shortcut_registry(shortcut_overrides)
        events = UIEventBus()
        self.state = TUIState(
            controller=controller,
            projector=LMTSViewProjector(controller.state),
            cw_bench_page=CWBenchPage(controller),
            model_explorer_page=ModelDownloaderPage(),
            settings=settings,
            settings_service=settings_service,
            shortcut_overrides=shortcut_overrides,
            shortcuts=shortcuts,
            events=events,
        )
        self.renderer = TUIRenderer(self.state)

    def _restore_ui_state(self, scope: str) -> None:
        payload = self.state.settings_service.load_ui_scope(scope)
        if not payload:
            return

        raw_tests = payload.get('configured_tests')
        if not isinstance(raw_tests, list):
            raise ValueError('persisted UI state configured_tests must be an array')
        configured = []
        for item in raw_tests:
            if not isinstance(item, dict):
                raise ValueError('persisted configured test must be an object')
            params = item.get('params')
            if not isinstance(params, dict):
                raise ValueError('persisted configured test params must be an object')
            type_ref = str(item.get('type_ref') or '').strip()
            instance_id = str(item.get('instance_id') or '').strip()
            configured.append(
                self.state.controller.test_types.get(type_ref).configure(
                    instance_id,
                    params,
                )
            )

        repeats = payload.get('suite_repeats', 1)
        if isinstance(repeats, bool) or not isinstance(repeats, int):
            raise ValueError('persisted suite_repeats must be an integer')
        suite_level = str(payload.get('suite_level') or 'moderate').strip()
        raw_selected_tests = payload.get('selected_test_refs')
        if not isinstance(raw_selected_tests, list) or not all(isinstance(item, str) for item in raw_selected_tests):
            raise ValueError('persisted selected_test_refs must be an array of strings')
        self.state.controller.matrix_view.restore_configuration(
            configured,
            suite_level=suite_level,
            suite_repeats=repeats,
            selected_test_refs=set(raw_selected_tests),
        )

        raw_targets = payload.get('selected_target_ids')
        if not isinstance(raw_targets, list) or not all(isinstance(item, str) for item in raw_targets):
            raise ValueError('persisted selected_target_ids must be an array of strings')
        self.state.controller.select_target_ids(set(raw_targets))

        active_tab = str(payload.get('active_tab') or 'benchmark').strip()
        TAB_REGISTRY.get(active_tab)
        self.state.active_tab = active_tab

    def run(self) -> None:
        curses.wrapper(self._run_curses)

    def _run_curses(self, stdscr: curses.window) -> None:
        controller = self.state.controller
        host = self.host_class(
            f"AIGM LMTS - {'Profiling' if controller.state.profile_required else 'Benchmark'}",
            self.renderer.render_lines,
            self.renderer.tabs_line,
            controller.response_monitor.lines,
            shortcuts=self.state.shortcuts,
            scopes=lambda: (self.state.active_tab,),
            layout_panes=self.renderer.layout_panes,
            monitor_title='Console',
            monitor_fraction=1 / 3,
            events=self.state.events,
        )
        startup_user = UserActions(self.state, host, stdscr)
        while True:
            startup_user.set_message('')
            stdscr.erase()
            stdscr.refresh()
            startup = host.choose(stdscr, 'LMTS startup', ['Login', 'Local'], 0)
            if startup is None:
                return
            if startup == 0:
                try:
                    identity = controller.auth_service.current_identity()
                except Exception:
                    identity = None
                if identity is None:
                    startup_user.login(stdscr)
                    try:
                        identity = controller.auth_service.current_identity()
                    except Exception:
                        identity = None
                    if identity is None:
                        continue
                else:
                    self.state.events.publish(
                        'ui.message',
                        f'authenticated: {identity.username}',
                        source='tui_app',
                    )
                break
            startup_user.local(stdscr)
            break

        if controller.state.profile_required:
            self.state.active_tab = 'profile'
            ProfileActions(self.state, host, stdscr).profile_system(stdscr)

        if controller.auth_service.local_mode:
            scope = 'local'
        else:
            identity = controller.auth_service.require_identity()
            scope = f'user:{identity.user_id}'
        self.state.ui_state_scope = scope
        self._restore_ui_state(scope)
        active_tab = TAB_REGISTRY.get(self.state.active_tab)
        host.title = f'AIGM LMTS - {active_tab.label}'
        self.state.events.publish('ui.message', controller.state.message, source='tui_app')

        navigation = NavigationActions(self.state, host, stdscr)
        profile = ProfileActions(self.state, host, stdscr)
        benchmark = self.benchmark_actions_class(self.state, host, stdscr, navigation)
        results = ResultActions(self.state, host, stdscr)
        settings = SettingsActions(self.state, host, stdscr)
        user = UserActions(self.state, host, stdscr)

        def run_cw_bench(_stdscr) -> None:
            self.state.cw_bench_page.run(host)
            self.state.events.publish('ui.message', controller.state.message, source='cw_bench')

        def show_help(_stdscr) -> None:
            host.text_viewer(
                stdscr,
                'Help',
                (
                    'Global controls',
                    '  F1       Help',
                    '  Esc      Back',
                    '  Up/Down  Scroll',
                    '  Ctrl+L   Layout controls',
                    '  q q q    Quit',
                ),
            )

        bindings = {
            'app.help': show_help,
            'tab.benchmark': lambda _: navigation.open_tab('benchmark'),
            'tab.stats': lambda _: navigation.open_tab('stats'),
            'tab.downloader': lambda _: navigation.open_tab('downloader'),
            'downloader.module': lambda _: self.state.model_explorer_page.choose_module(host, stdscr),
            'downloader.catalog': lambda _: self.state.model_explorer_page.explore_catalog(host, stdscr),
            'downloader.download': lambda _: self.state.model_explorer_page.enqueue(host, stdscr),
            'downloader.delete': lambda _: self.state.model_explorer_page.delete(host, stdscr),
            'downloader.progress': lambda _: self.state.model_explorer_page.show_progress(host, stdscr),
            'downloader.refresh': lambda _: self.state.model_explorer_page.refresh(),
            'downloader.cancel': lambda _: self.state.model_explorer_page.cancel(host, stdscr),
            'tab.profile': lambda _: navigation.open_tab('profile'),
            'tab.settings': lambda _: navigation.open_tab('settings'),
            'nav.back': navigation.back,
            'profile.scan': profile.profile_system,
            'stats.refresh': lambda _: (
                controller.stats_service.snapshot(refresh=True)
                if controller.stats_service is not None
                else None
            ),
            'user.login': user.login,
            'user.logout': user.logout,
            'user.local': user.local,
            'user.refresh': user.refresh,
            'benchmark.tests': benchmark.tests_dialog,
            'benchmark.targets': benchmark.select_targets,
            'benchmark.run': benchmark.run_dialog,
            'benchmark.output': results.output_dialog,
            'benchmark.refresh': benchmark.refresh,
            'deep.cw_bench': lambda _: navigation.open_tab('cw_bench'),
            'deep.run': benchmark.run_deep_suite,
            'deep.results': results.browse_results,
            'cw.source': lambda _: self.state.cw_bench_page.choose_source(host, stdscr),
            'cw.language': lambda _: self.state.cw_bench_page.choose_language(host, stdscr),
            'cw.models': lambda _: self.state.cw_bench_page.choose_models(host, stdscr),
            'cw.run': run_cw_bench,
            'cw.results': results.browse_cw_results,
            'cw.cancel': benchmark.cancel,
            'settings.user': lambda _: navigation.open_tab('user'),
            'settings.output': settings.edit_output_folder,
            'settings.report_output': settings.report_output_settings,
            'settings.targets': settings.runtime_target_settings,
            'settings.shortcuts': settings.shortcut_editor,
        }
        for action, handler in bindings.items():
            host.bind(action, handler)
        host.run(stdscr)
