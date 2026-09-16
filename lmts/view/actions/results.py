from __future__ import annotations

from pathlib import Path

from lmts.core.analyzer import compare_targets, format_target_comparison
from lmts.core.result_export import build_matrix_bundle, export_matrix_bundle, export_run_json
from lmts.core.store import RunStore
from lmts.reporting import project_matrix_bundle
from lmts.tools.report_publish import publish_report

from ..output_dialog import choose_report_profile
from ..results import cell_verdict, format_run_result, matrix_label
from ..tui_common import short_test_label
from .base import TUIActions


class ResultActions(TUIActions):
    def choose_matrix_result(self, title: str, predicate=None):
        matrices = self.controller.recent_matrices()
        if predicate is not None:
            matrices = [item for item in matrices if predicate(item[1])]
        if not matrices:
            self.set_message('no canonical matrix results found')
            return None
        if len(matrices) == 1:
            return matrices[0]
        selected = self.host.choose(
            self.stdscr,
            title,
            [matrix_label(data, path) for path, data in matrices],
        )
        return None if selected is None else matrices[selected]

    def view_matrix_result(self, chosen) -> None:
        if chosen is None:
            return
        matrix_path, matrix_data = chosen
        targets = [str(v) for v in (matrix_data.get('target_ids') or [])]
        kinds = matrix_data.get('target_kinds') if isinstance(matrix_data.get('target_kinds'), dict) else {}
        tests = [str(v) for v in (matrix_data.get('test_refs') or [])]
        cells = [cell for cell in (matrix_data.get('cells') or []) if isinstance(cell, dict)]
        by_key = {(str(cell.get('target_id')), str(cell.get('test_ref'))): cell for cell in cells}
        values = [[cell_verdict(by_key.get((target, test))) for test in tests] for target in targets]
        rows = [f"{str(kinds.get(target) or '?').upper()} {target}" for target in targets]
        summary = (
            f"PASS {int(matrix_data.get('passed') or 0)}  "
            f"FAIL {int(matrix_data.get('failed') or 0)}  "
            f"ERROR {int(matrix_data.get('errors') or 0)}  "
            f"CANCEL {int(matrix_data.get('cancelled') or 0)}"
        )
        selected_cell = self.host.matrix_browser(
            self.stdscr,
            f"Results: {str(matrix_data.get('started_at') or '').replace('T', ' ')[:19]}",
            rows,
            [short_test_label(ref) for ref in tests],
            values,
            summary=summary,
        )
        if selected_cell is None:
            self.set_message(f'viewed matrix: {matrix_path}')
            return
        row_index, col_index = selected_cell
        cell = by_key.get((targets[row_index], tests[col_index]))
        if cell is None:
            self.set_message('no run for selected matrix cell')
            return
        output_folder = self.state.settings.output_folder
        run_action = self.host.choose(
            self.stdscr,
            f"Result actions: {cell.get('run_id', '?')}",
            [
                'View details',
                f'Export selected run -> {output_folder}',
                f'Export matrix -> {output_folder}',
            ],
        )
        if run_action is None:
            return
        if run_action == 2:
            try:
                path = export_matrix_bundle(
                    matrix_data,
                    Path(output_folder),
                    results_root=self.controller.results_root,
                )
                self.set_message(f'exported matrix: {path}')
            except (OSError, ValueError) as exc:
                self.set_message(f'matrix export failed: {exc}')
            return
        result_path = Path(str(cell.get('result_path') or ''))
        if not result_path.is_file():
            self.set_message(f'canonical run result missing: {result_path}')
            return
        run_data = RunStore(self.controller.results_root).load(result_path)
        if run_action == 1:
            try:
                path = export_run_json(run_data, Path(output_folder))
                self.set_message(f'exported run: {path}')
            except (OSError, ValueError) as exc:
                self.set_message(f'run export failed: {exc}')
            return
        self.host.text_viewer(
            self.stdscr,
            f"Run result: {cell.get('run_id', result_path.stem)}",
            format_run_result(run_data, result_path),
        )

    def browse_results(self, _stdscr) -> None:
        self.view_matrix_result(self.choose_matrix_result('Matrix results (newest first)'))

    def browse_cw_results(self, _stdscr) -> None:
        self.view_matrix_result(
            self.choose_matrix_result(
                'CW Bench results (newest first)',
                lambda data: 'deep.cw_bench@1.0.0' in [str(value) for value in (data.get('test_refs') or [])],
            )
        )

    def compare_targets_action(self, _stdscr) -> None:
        chosen = self.choose_matrix_result('Compare targets from matrix')
        if chosen is None:
            return
        _, matrix_data = chosen
        target_ids = [str(value) for value in (matrix_data.get('target_ids') or [])]
        if len(target_ids) < 2:
            self.set_message('target comparison requires at least two targets in the matrix')
            return
        baseline_index = self.host.choose(self.stdscr, 'Baseline target', target_ids)
        if baseline_index is None:
            return
        baseline = target_ids[baseline_index]
        candidates = [target for target in target_ids if target != baseline]
        candidate_index = self.host.choose(self.stdscr, 'Candidate target', candidates)
        if candidate_index is None:
            return
        candidate = candidates[candidate_index]
        try:
            bundle = build_matrix_bundle(matrix_data, results_root=self.controller.results_root)
            runs = bundle.get('runs') if isinstance(bundle.get('runs'), list) else []
            comparison = compare_targets(runs, baseline, candidate)
        except (OSError, ValueError) as exc:
            self.set_message(f'target comparison failed: {exc}')
            return
        self.host.text_viewer(
            self.stdscr,
            f'Compare: {baseline} -> {candidate}',
            format_target_comparison(comparison),
        )
        self.set_message(f'compared {baseline} -> {candidate}')

    def publish_report_action(self, _stdscr) -> None:
        chosen = self.choose_matrix_result('Publish matrix report')
        if chosen is None:
            return
        _, matrix_data = chosen
        try:
            profile = choose_report_profile(self.host, self.stdscr)
            if profile is None:
                return
            bundle = build_matrix_bundle(matrix_data, results_root=self.controller.results_root)
            report_id = publish_report(project_matrix_bundle(bundle), profile)
            self.set_message(f'published report: {report_id}')
        except (OSError, ValueError, RuntimeError) as exc:
            self.set_message(f'report publish failed: {exc}')

    def export_errors(self, _stdscr) -> None:
        path = self.controller.export_errors('task')
        self.set_message(self.controller.state.message if path is None else f'exported: {path}')

    def output_dialog(self, _stdscr) -> None:
        options = ['Historical results', 'Compare targets', 'Publish report', 'Export errors']
        chosen = self.host.choose(self.stdscr, 'Output', options)
        if chosen is None:
            return
        if chosen == 0:
            self.browse_results(self.stdscr)
        elif chosen == 1:
            self.compare_targets_action(self.stdscr)
        elif chosen == 2:
            self.publish_report_action(self.stdscr)
        else:
            self.export_errors(self.stdscr)
