from __future__ import annotations

from lmts.core.runtime_targets import load_runtime_targets
from lmts.lib.view import LayoutPane
from lmts.tools.ftp_profiles import load_ftp_profiles
from lmts.tools.profile import load_system_profile

from .tui_state import TUIState
from .user_page import UserPage


def _format_reference_metric(test: object) -> str:
    if not isinstance(test, dict):
        return '-'
    metrics = test.get('metrics') if isinstance(test.get('metrics'), dict) else {}
    throughput = metrics.get('throughput_gib_per_second')
    if isinstance(throughput, (int, float)):
        return f'{float(throughput):.2f} GiB/s'
    gigaops = metrics.get('gigaoperations_per_second')
    if isinstance(gigaops, (int, float)):
        return f'{float(gigaops):.2f} GOP/s'
    median_seconds = metrics.get('median_seconds')
    if isinstance(median_seconds, (int, float)):
        return f'{float(median_seconds):.4f} s median'
    return 'measured'


def _reference_target_suffix(test: dict) -> str:
    target = test.get('target')
    if not isinstance(target, dict):
        return ''
    label = str(target.get('model') or target.get('uuid') or target.get('device_index') or '').strip()
    return f' @ {label}' if label else ''


def _reference_suite_lines(label: str, suite: object) -> list[str]:
    if not isinstance(suite, dict):
        return [f'{label}: not measured']
    tests = suite.get('tests') if isinstance(suite.get('tests'), list) else []
    suite_version = suite.get('suite_version')
    suffix = f' v{suite_version}' if isinstance(suite_version, int) else ''
    lines = [f'{label}:{suffix}']
    for test in tests:
        if not isinstance(test, dict):
            continue
        test_label = str(test.get('label') or test.get('benchmark_id') or 'test') + _reference_target_suffix(test)
        method_version = test.get('method_version')
        method = str(test.get('method') or '')
        method_suffix = f' [{method} v{method_version}]' if method and isinstance(method_version, int) else ''
        lines.append(f'  {test_label}: {_format_reference_metric(test)}{method_suffix}')
    summary = suite.get('summary') if isinstance(suite.get('summary'), dict) else {}
    scaling = summary.get('parallel_scaling_factor')
    if isinstance(scaling, (int, float)):
        lines.append(f'  Parallel scaling: {float(scaling):.2f}x')
    if len(lines) == 1:
        lines.append('  no test results')
    return lines


class TUIRenderer:
    def __init__(self, state: TUIState) -> None:
        self.state = state
        self.user_page = UserPage(state.controller)

    def shortcut_label(self, action: str) -> str:
        definitions = [
            definition
            for definition in self.state.shortcuts.definitions((self.state.active_tab,))
            if definition.action == action
        ]
        if len(definitions) != 1:
            raise ValueError(f'exactly one active shortcut required for {action}: found {len(definitions)}')
        return definitions[0].sequence_label

    def tabs_line(self) -> str:
        from .registries import TAB_REGISTRY

        return 'Tabs: ' + ' | '.join(
            f"{self.shortcut_label(f'tab.{tab.id}')}. {tab.label}"
            for tab in TAB_REGISTRY.children('root')
        )

    def profile_lines(self) -> tuple[str, ...]:
        controller = self.state.controller
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
        references = payload.get('reference_benchmarks') if isinstance(payload.get('reference_benchmarks'), dict) else {}
        lines.extend(['', 'Reference performance:'])
        for label, domain in [('CPU', 'cpu'), ('MEM', 'memory'), ('GPU', 'gpu'), ('NPU', 'npu')]:
            lines.extend(_reference_suite_lines(label, references.get(domain)))
        profiled_at = str(payload.get('profiled_at') or '')
        if profiled_at:
            lines.append(f'Profiled: {profiled_at}')
        return tuple(lines)

    def benchmark_lines(self) -> tuple[str, ...]:
        lines = list(self.state.projector.project().lines)
        if lines and lines[0] == 'LMTS evaluation laboratory':
            del lines[0]
            if lines and lines[0] == '':
                del lines[0]
        return tuple(lines)

    def deep_lines(self) -> tuple[str, ...]:
        controller = self.state.controller
        return (
            'Deep',
            '',
            'Cumulative suite: Quick + Moderate + Deep.',
            f'Automatic suite tests: {len(controller.state.tests)}',
            '',
            'Options',
            f"  {self.shortcut_label('deep.cw_bench')}. CW Bench",
            f"  {self.shortcut_label('deep.run')}. Run Deep suite",
            f"  {self.shortcut_label('deep.results')}. Results",
            '',
            'CW Bench generates an implementation from one selected CW source, imports the output',
            'back through CIC, and compares canonical CW against imported canonical CW.',
        )

    def settings_lines(self) -> tuple[str, ...]:
        settings = self.state.settings
        ftp_count = len(load_ftp_profiles().profiles)
        runtime_count = len(load_runtime_targets())
        dvs = self.state.dvs_service_state
        dvs_s3d = 'ready' if dvs.s3d_ready else ('not ready' if dvs.s3d_configured else 'not configured')
        return (
            'Application, server and connection settings.', '',
            f'Output folder    : {settings.output_folder}',
            f'MySQL outputs    : {len(settings.mysql_connections)}',
            f'PHP API outputs  : {len(settings.php_api_connections)}',
            f'Auto-publish     : {len(settings.auto_publish_targets)} selected',
            f'DVS status       : {dvs.state.upper()}',
            f'DVS endpoint     : {settings.dvs.host}:{settings.dvs.port}',
            f'DVS S3D          : {dvs_s3d}',
            f'FTP profiles     : {ftp_count}',
            f'Runtime targets  : {runtime_count}',
            f'Shortcuts        : {len(self.state.shortcut_overrides)} custom binding(s)',
            '',
            'Server installer:',
            '  lmts/install/install_server.sh',
        )

    def render_lines(self) -> tuple[str, ...]:
        tab = self.state.active_tab
        if tab == 'user':
            return self.user_page.lines()
        if tab == 'profile':
            return self.profile_lines()
        if tab == 'benchmark':
            return self.benchmark_lines()
        if tab == 'deep':
            return self.deep_lines()
        if tab == 'cw_bench':
            return self.state.cw_bench_page.lines()
        if tab == 'downloader':
            return ('Model Downloader', '', 'Use the Actions row to select a downloader module and model operation.')
        if tab == 'settings':
            return self.settings_lines()
        raise ValueError(f'unknown TUI tab: {tab}')

    def benchmark_results_lines(self) -> tuple[str, ...]:
        lines = list(self.state.controller.state.live_matrix_lines())
        if lines and lines[0] == 'Results matrix':
            del lines[0]
        return tuple(lines)

    def live_run_panes(self, main_lines) -> tuple[LayoutPane, ...]:
        controller = self.state.controller
        return (
            LayoutPane(1, 'Main', main_lines, primary=True),
            LayoutPane(2, 'Results', self.benchmark_results_lines, title='Results', auto_hide_empty=True),
            LayoutPane(3, 'Console', controller.response_monitor.lines, title='Console', auto_hide_empty=True, follow_tail=True),
        )

    def layout_panes(self) -> tuple[LayoutPane, ...]:
        tab = self.state.active_tab
        if tab == 'profile':
            return (
                LayoutPane(1, 'Main', self.profile_lines, primary=True),
                LayoutPane(2, 'Console', lambda: tuple(self.state.profile_console), title='Console', auto_hide_empty=True, follow_tail=True),
            )
        if tab == 'benchmark':
            return self.live_run_panes(self.benchmark_lines)
        if tab == 'deep':
            return self.live_run_panes(self.deep_lines)
        if tab == 'cw_bench':
            return self.live_run_panes(self.state.cw_bench_page.lines)
        return (LayoutPane(1, 'Main', self.render_lines, primary=True),)
