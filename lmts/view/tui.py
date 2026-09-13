from __future__ import annotations

import curses
from dataclasses import replace
from pathlib import Path

from lmts.cli import default_provider_registry
from lmts.core.result_export import build_matrix_bundle, export_matrix_bundle, export_run_json
from lmts.core.settings import (
    DEFAULT_SETTINGS_PATH,
    LMTSSettings,
    MySQLSettings,
    load_settings,
    save_settings,
)
from lmts.core.store import RunStore
from lmts.lib.view import RegistrySplitCursesViewHost, choose_directory
from lmts.reporting import project_matrix_bundle
from lmts.tests.base import test_ref
from lmts.tests.catalog import default_test_matrix, default_test_type_registry
from lmts.tests.types import TestParameter, TestTypeDefinition
from lmts.tools.ftp_profiles import load_ftp_profiles
from lmts.tools.mysql_config import deploy_mysql_config
from lmts.tools.profile import load_system_profile
from lmts.tools.report_publish import publish_report
from lmts.tools.web_deploy import deploy_web_root

from .controller import LMTSViewController
from .output_dialog import choose_ftp_profile, choose_output_target, manage_ftp_profiles
from .projector import LMTSViewProjector
from .registries import TAB_REGISTRY, build_shortcut_registry
from .results import cell_verdict, format_run_result, matrix_label
from .shortcut_settings import (
    DEFAULT_SHORTCUT_SETTINGS_PATH,
    load_shortcut_overrides,
    normalise_sequence_text,
    save_shortcut_overrides,
)


def _next_instance_id(controller: LMTSViewController, definition: TestTypeDefinition) -> str:
    base = definition.id.rsplit('.', 1)[-1].replace('_', '-')
    used = {getattr(test, 'instance_id', '') for test in controller.state.tests}
    index = 1
    while f'{base}-{index}' in used:
        index += 1
    return f'{base}-{index}'


def _short_test_label(ref: str) -> str:
    return (ref.split('#', 1)[-1] if '#' in ref else ref.rsplit('.', 1)[-1])[:18]


def _single_line(host, stdscr, title: str, *, initial: str = '', allow_empty: bool = False) -> str | None:
    while True:
        value = host.input_multiline(stdscr, title, initial=initial)
        if value is None:
            return None
        value = value.strip()
        if '\n' not in value and '\r' not in value and (value or allow_empty):
            return value
        host.message = f"{title}: enter one {'line' if allow_empty else 'non-empty line'}"


def _profile_lines(controller: LMTSViewController) -> tuple[str, ...]:
    payload = load_system_profile(controller.profile_path)
    lines = [
        'System identity and reference performance for benchmark comparison.',
        '',
        f"Profile: {'REQUIRED' if controller.state.profile_required else 'ready'}",
    ]
    if payload is None:
        lines.extend(['', 'No valid system profile is currently stored.'])
        return tuple(lines)
    profile = payload.get('profile')
    if not isinstance(profile, dict):
        lines.extend(['', 'Stored system profile is invalid.'])
        return tuple(lines)
    cpu = profile.get('cpu') if isinstance(profile.get('cpu'), dict) else {}
    memory = profile.get('memory') if isinstance(profile.get('memory'), dict) else {}
    gpu = profile.get('gpu') if isinstance(profile.get('gpu'), list) else []
    npu = profile.get('npu') if isinstance(profile.get('npu'), list) else []
    cpu_label = str(cpu.get('model_name') or '-')
    total_bytes = memory.get('total_bytes')
    memory_label = f'{int(total_bytes) / (1024 ** 3):.2f} GiB' if isinstance(total_bytes, int) and total_bytes > 0 else '-'
    gpu_labels = [str(item.get('model') or item.get('vendor') or '-') for item in gpu if isinstance(item, dict)]
    npu_labels = [str(item.get('model') or item.get('name') or item.get('vendor') or '-') for item in npu if isinstance(item, dict)]
    lines.extend([
        f'CPU : {cpu_label}',
        f'MEM : {memory_label}',
        f"GPU : {', '.join(gpu_labels) if gpu_labels else '-'}",
        f"NPU : {', '.join(npu_labels) if npu_labels else '-'}",
    ])
    profiled_at = str(payload.get('profiled_at') or '')
    if profiled_at:
        lines.append(f'Profiled: {profiled_at}')
    return tuple(lines)


def _benchmark_lines(projector: LMTSViewProjector) -> tuple[str, ...]:
    lines = list(projector.project().lines)
    if lines and lines[0] == 'LMTS model laboratory':
        del lines[0]
        if lines and lines[0] == '':
            del lines[0]
    return tuple(lines)


def run() -> None:
    test_types = default_test_type_registry()
    matrix = default_test_matrix(test_types)
    controller = LMTSViewController(default_provider_registry(), test_types, matrix)
    controller.refresh()
    projector = LMTSViewProjector(controller.state)
    settings = load_settings(DEFAULT_SETTINGS_PATH)
    try:
        shortcut_overrides = load_shortcut_overrides(DEFAULT_SHORTCUT_SETTINGS_PATH)
        shortcuts = build_shortcut_registry(shortcut_overrides)
    except (OSError, ValueError):
        shortcut_overrides = {}
        shortcuts = build_shortcut_registry()
    active_shortcuts = [shortcuts]
    active_tab = ['profile']

    def current_tab() -> str:
        return active_tab[0]

    def shortcut_label(action: str) -> str:
        for definition in active_shortcuts[0].definitions((current_tab(),)):
            if definition.action == action:
                return definition.sequence_label
        return '-'

    def tabs_line() -> str:
        return 'Tabs: ' + ' | '.join(
            f"{shortcut_label(f'tab.{tab.id}')}. {tab.label}"
            for tab in TAB_REGISTRY.children('root')
        )

    def settings_lines() -> tuple[str, ...]:
        ftp_count = len(load_ftp_profiles().profiles)
        mysql = settings.mysql
        return (
            'Application, server and connection settings.',
            '',
            f'Output folder : {settings.output_folder}',
            f'MySQL host    : {mysql.host}',
            f'MySQL database: {mysql.database}',
            f'MySQL user    : {mysql.username}',
            f'FTP profiles  : {ftp_count}',
            f'Shortcuts     : {len(shortcut_overrides)} custom binding(s)',
            '',
            'Server installer:',
            '  lmts/install/install_server.sh',
        )

    def render_lines() -> tuple[str, ...]:
        if current_tab() == 'profile':
            return _profile_lines(controller)
        if current_tab() == 'benchmark':
            return _benchmark_lines(projector)
        if current_tab() == 'settings':
            return settings_lines()
        return ()

    def app(stdscr: curses.window) -> None:
        nonlocal settings
        host = RegistrySplitCursesViewHost(
            'AIGM LMTS - Profile', render_lines, tabs_line, controller.response_monitor.lines,
            shortcuts=active_shortcuts[0], scopes=lambda: (current_tab(),),
            monitor_title='Bot response', monitor_fraction=1 / 3,
        )
        if controller.state.profile_required:
            controller.profile()
        host.message = controller.state.message

        def set_message(value: str = '') -> None:
            host.message = value

        def open_tab(tab_id: str) -> None:
            tab = TAB_REGISTRY.get(tab_id)
            active_tab[0] = tab_id
            host.title = f'AIGM LMTS - {tab.label}'
            host.scroll = 0
            set_message('')

        def back(_stdscr: curses.window) -> None:
            parent = TAB_REGISTRY.parent(current_tab())
            if parent is None or parent.id == 'root':
                set_message('already at top level')
                return
            open_tab(parent.id)

        def show_progress() -> None:
            host.progress_dialog(stdscr, 'Test progress', controller.state.progress_lines, lambda: not controller.state.running, cancel=controller.cancel)
            set_message(controller.state.message)

        def select_models(_stdscr: curses.window) -> None:
            if controller.state.running:
                set_message('test matrix is running')
                return
            options = [model.id for model in controller.state.models]
            selected = {i for i, model in enumerate(controller.state.models) if model.id in controller.state.selected_model_ids}
            chosen = host.choose_many(stdscr, 'Models', options, selected, include_all=True, all_label='All models')
            if chosen is not None:
                controller.select_models(chosen)
                set_message(f'selected {len(chosen)} model(s)')

        def select_tests(_stdscr: curses.window) -> None:
            if controller.state.running:
                set_message('test matrix is running')
                return
            options = [test_ref(test) for test in controller.state.tests]
            selected = {i for i, test in enumerate(controller.state.tests) if test_ref(test) in controller.state.selected_test_refs}
            chosen = host.choose_many(stdscr, 'Configured test matrix', options, selected, include_all=True, all_label='All configured tests')
            if chosen is not None:
                controller.select_tests(chosen)
                set_message(f'selected {len(chosen)} configured test(s)')

        def collect_parameter(parameter: TestParameter) -> object | None:
            if parameter.kind == 'integer':
                default = parameter.default if isinstance(parameter.default, int) else 1
                return host.input_integer(stdscr, parameter.label, default=default, minimum=parameter.minimum if parameter.minimum is not None else -999999, maximum=parameter.maximum if parameter.maximum is not None else 999999)
            if parameter.kind == 'boolean':
                chosen = host.choose(stdscr, parameter.label, ['false', 'true'], 0)
                return None if chosen is None else chosen == 1
            if parameter.kind == 'choice':
                chosen = host.choose(stdscr, parameter.label, list(parameter.choices), 0)
                return None if chosen is None else parameter.choices[chosen]
            initial = parameter.default if isinstance(parameter.default, str) else ''
            return host.input_multiline(stdscr, parameter.label, initial=initial)

        def add_test(_stdscr: curses.window) -> None:
            if controller.state.running:
                set_message('test matrix is running')
                return
            definitions = controller.test_types.definitions()
            chosen = host.choose(stdscr, 'Test type registry', [f'{d.ref}  {d.title}' for d in definitions])
            if chosen is None:
                return
            definition = definitions[chosen]
            params: dict[str, object] = {}
            for parameter in definition.parameters:
                value = collect_parameter(parameter)
                if value is None:
                    set_message('test configuration cancelled')
                    return
                params[parameter.name] = value
            configured = controller.add_test(definition.ref, _next_instance_id(controller, definition), params)
            set_message(f'added: {configured.ref}' if configured is not None else controller.state.message)

        def remove_test(_stdscr: curses.window) -> None:
            tests = list(controller.state.tests)
            chosen = host.choose(stdscr, 'Remove configured test', [test_ref(test) for test in tests])
            if chosen is not None:
                controller.remove_test(getattr(tests[chosen], 'instance_id', ''))
                set_message(controller.state.message)

        def run_selected(_stdscr: curses.window) -> None:
            if controller.run_selected():
                show_progress()
            set_message(controller.state.message)

        def test_all(_stdscr: curses.window) -> None:
            if controller.test_all():
                show_progress()
            set_message(controller.state.message)

        def choose_matrix_result(title: str):
            matrices = controller.recent_matrices()
            if not matrices:
                set_message('no canonical matrix results found')
                return None
            if len(matrices) == 1:
                return matrices[0]
            selected = host.choose(stdscr, title, [matrix_label(data, path) for path, data in matrices])
            return None if selected is None else matrices[selected]

        def browse_results(_stdscr: curses.window) -> None:
            chosen = choose_matrix_result('Matrix results (newest first)')
            if chosen is None:
                return
            matrix_path, matrix_data = chosen
            models = [str(v) for v in (matrix_data.get('model_ids') or [])]
            tests = [str(v) for v in (matrix_data.get('test_refs') or [])]
            cells = [cell for cell in (matrix_data.get('cells') or []) if isinstance(cell, dict)]
            by_key = {(str(cell.get('model_id')), str(cell.get('test_ref'))): cell for cell in cells}
            values = [[cell_verdict(by_key.get((model, test))) for test in tests] for model in models]
            summary = f"PASS {int(matrix_data.get('passed') or 0)}  FAIL {int(matrix_data.get('failed') or 0)}  ERROR {int(matrix_data.get('errors') or 0)}  CANCEL {int(matrix_data.get('cancelled') or 0)}"
            selected_cell = host.matrix_browser(stdscr, f"Results: {str(matrix_data.get('started_at') or '').replace('T', ' ')[:19]}", models, [_short_test_label(ref) for ref in tests], values, summary=summary)
            if selected_cell is None:
                set_message(f'viewed matrix: {matrix_path}')
                return
            row_index, col_index = selected_cell
            cell = by_key.get((models[row_index], tests[col_index]))
            if cell is None:
                set_message('no run for selected matrix cell')
                return
            run_action = host.choose(stdscr, f"Result actions: {cell.get('run_id', '?')}", ['View details', f'Export selected run -> {settings.output_folder}', f'Export matrix -> {settings.output_folder}'])
            if run_action is None:
                return
            if run_action == 2:
                try:
                    path = export_matrix_bundle(matrix_data, Path(settings.output_folder), results_root=controller.results_root)
                    set_message(f'exported matrix: {path}')
                except (OSError, ValueError) as exc:
                    set_message(f'matrix export failed: {exc}')
                return
            result_path = Path(str(cell.get('result_path') or ''))
            if not result_path.is_file():
                set_message(f'canonical run result missing: {result_path}')
                return
            run_data = RunStore(controller.results_root).load(result_path)
            if run_action == 1:
                try:
                    path = export_run_json(run_data, Path(settings.output_folder))
                    set_message(f'exported run: {path}')
                except (OSError, ValueError) as exc:
                    set_message(f'run export failed: {exc}')
                return
            host.text_viewer(stdscr, f"Run result: {cell.get('run_id', result_path.stem)}", format_run_result(run_data, result_path))

        def publish_report_action(_stdscr: curses.window) -> None:
            chosen = choose_matrix_result('Publish matrix report')
            if chosen is None:
                return
            _, matrix_data = chosen
            try:
                profile = choose_ftp_profile(host, stdscr)
                if profile is None:
                    return
                bundle = build_matrix_bundle(matrix_data, results_root=controller.results_root)
                report_id = publish_report(project_matrix_bundle(bundle), profile)
                set_message(f'published report: {report_id}')
            except (OSError, ValueError, RuntimeError) as exc:
                set_message(f'report publish failed: {exc}')

        def profile_system(_stdscr: curses.window) -> None:
            controller.profile()
            set_message(controller.state.message)

        def profile_reference(domain: str) -> None:
            set_message(f'{domain.upper()} reference benchmark is not implemented yet')

        def edit_output_folder(_stdscr: curses.window) -> None:
            nonlocal settings
            selected = choose_directory(host, stdscr, 'Output folder', initial=settings.output_folder)
            if selected is not None:
                settings = replace(settings, output_folder=str(selected))
                save_settings(settings, DEFAULT_SETTINGS_PATH)
                set_message(f'output folder saved: {settings.output_folder}')

        def edit_mysql(_stdscr: curses.window) -> None:
            nonlocal settings
            mysql = settings.mysql
            values = []
            for title, initial, allow_empty in [
                ('MySQL host', mysql.host, False), ('MySQL database', mysql.database, False),
                ('MySQL username', mysql.username, False), ('MySQL password', mysql.password, True),
                ('Publish key', mysql.publish_key, False),
            ]:
                value = _single_line(host, stdscr, title, initial=initial, allow_empty=allow_empty)
                if value is None:
                    return
                values.append(value)
            settings = replace(settings, mysql=MySQLSettings(host=values[0], database=values[1], username=values[2], password=values[3], publish_key=values[4]))
            save_settings(settings, DEFAULT_SETTINGS_PATH)
            set_message('MySQL settings saved')

        def ftp_settings(_stdscr: curses.window) -> None:
            manage_ftp_profiles(host, stdscr)
            set_message('FTP profiles updated')

        def server_setup(_stdscr: curses.window) -> None:
            action = host.choose(stdscr, 'Server setup', ['Deploy www-root', 'Show installer path'])
            if action is None:
                return
            if action == 1:
                set_message('installer: lmts/install/install_server.sh')
                return
            target = choose_output_target(host, stdscr, disk_initial='/home/www/lmts')
            if target is None:
                return
            try:
                written = deploy_web_root(target)
                written.extend(deploy_mysql_config(target, settings.mysql))
                set_message(f'deployed {len(written)} server file(s)')
            except (OSError, ValueError, RuntimeError) as exc:
                set_message(f'server deploy failed: {exc}')

        def shortcut_editor(_stdscr: curses.window) -> None:
            definitions = list(active_shortcuts[0].definitions(('profile', 'benchmark', 'settings')))
            options = ['Reset all to defaults', *[f'[{item.topic}] {item.sequence_label}  {item.label}' for item in definitions]]
            chosen = host.choose(stdscr, 'Shortcut editor', options)
            if chosen is None:
                return
            if chosen == 0:
                shortcut_overrides.clear()
                save_shortcut_overrides(shortcut_overrides)
                active_shortcuts[0] = build_shortcut_registry()
                host.shortcuts = active_shortcuts[0]
                set_message('shortcuts reset to defaults')
                return
            definition = definitions[chosen - 1]
            value = _single_line(host, stdscr, f"{definition.label} shortcut (space-separated; 'default' resets)", initial=definition.sequence_label)
            if value is None:
                return
            candidate = dict(shortcut_overrides)
            if value.casefold() == 'default':
                candidate.pop(definition.action, None)
            else:
                candidate[definition.action] = normalise_sequence_text(value)
            try:
                registry = build_shortcut_registry(candidate)
            except ValueError as exc:
                set_message(f'shortcut conflict: {exc}')
                return
            shortcut_overrides.clear()
            shortcut_overrides.update(candidate)
            save_shortcut_overrides(shortcut_overrides)
            active_shortcuts[0] = registry
            host.shortcuts = registry
            set_message(f'shortcut saved: {definition.label}')

        def cancel(_stdscr: curses.window) -> None:
            controller.cancel()
            set_message(controller.state.message)

        def export_errors(_stdscr: curses.window) -> None:
            path = controller.export_errors('task')
            set_message(controller.state.message if path is None else f'exported: {path}')

        def refresh(_stdscr: curses.window) -> None:
            controller.refresh()
            set_message(controller.state.message)

        bindings = {
            'tab.profile': lambda _: open_tab('profile'), 'tab.benchmark': lambda _: open_tab('benchmark'), 'tab.settings': lambda _: open_tab('settings'),
            'nav.back': back, 'profile.scan': profile_system,
            'profile.cpu': lambda _: profile_reference('cpu'), 'profile.memory': lambda _: profile_reference('memory'),
            'profile.gpu': lambda _: profile_reference('gpu'), 'profile.npu': lambda _: profile_reference('npu'),
            'models': select_models, 'tests': select_tests, 'test.add': add_test, 'test.remove': remove_test,
            'run.selected': run_selected, 'run.all': test_all, 'results': browse_results,
            'benchmark.publish': publish_report_action, 'cancel': cancel, 'errors': export_errors, 'refresh': refresh,
            'settings.output': edit_output_folder, 'settings.server': server_setup, 'settings.mysql': edit_mysql,
            'settings.ftp': ftp_settings, 'settings.shortcuts': shortcut_editor,
        }
        for action, handler in bindings.items():
            host.bind(action, handler)
        host.run(stdscr)

    curses.wrapper(app)


def main() -> int:
    run()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
