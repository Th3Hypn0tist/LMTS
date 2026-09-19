from __future__ import annotations

import curses

from lmts.cli import default_provider_registry
from lmts.lib.view import UIEventBus
from lmts.services.settings import SettingsService
from lmts.tests.catalog import default_test_matrix, default_test_type_registry
from lmts.tools.dvs_service import dvs_status

from .actions.benchmark import BenchmarkActions
from .actions.navigation import NavigationActions
from .actions.profile import ProfileActions
from .actions.results import ResultActions
from .actions.settings import SettingsActions
from .controller import LMTSViewController
from .cw_bench_page import CWBenchPage
from .lmts_host import LMTSInteractiveHost
from .projector import LMTSViewProjector
from .registries import build_shortcut_registry
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
            settings=settings,
            settings_service=settings_service,
            dvs_service_state=dvs_status(settings.dvs),
            shortcut_overrides=shortcut_overrides,
            shortcuts=shortcuts,
            events=events,
        )
        self.renderer = TUIRenderer(self.state)

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
        if controller.state.profile_required:
            self.state.active_tab = 'profile'
            ProfileActions(self.state, host, stdscr).profile_system(stdscr)
        self.state.active_tab = 'benchmark'
        self.state.events.publish('ui.message', controller.state.message, source='tui_app')

        navigation = NavigationActions(self.state, host, stdscr)
        profile = ProfileActions(self.state, host, stdscr)
        benchmark = self.benchmark_actions_class(self.state, host, stdscr, navigation)
        results = ResultActions(self.state, host, stdscr)
        settings = SettingsActions(self.state, host, stdscr)

        def run_cw_bench(_stdscr) -> None:
            self.state.cw_bench_page.run(host)
            self.state.events.publish('ui.message', controller.state.message, source='cw_bench')

        bindings = {
            'tab.user': lambda _: navigation.open_tab('user'),
            'tab.benchmark': lambda _: navigation.open_tab('benchmark'),
            'tab.profile': lambda _: navigation.open_tab('profile'),
            'tab.downloader': lambda _: navigation.open_tab('downloader'),
            'tab.settings': lambda _: navigation.open_tab('settings'),
            'nav.back': navigation.back,
            'profile.scan': profile.profile_system,
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
            'settings.output': settings.edit_output_folder,
            'settings.report_output': settings.report_output_settings,
            'settings.dvs': settings.edit_dvs,
            'settings.targets': settings.runtime_target_settings,
            'settings.shortcuts': settings.shortcut_editor,
        }
        for action, handler in bindings.items():
            host.bind(action, handler)
        host.run(stdscr)
