from __future__ import annotations

import curses
from pathlib import Path

from lmts.cli import default_provider_registry
from lmts.core.result_export import build_matrix_bundle, export_matrix_bundle, export_run_json
from lmts.core.settings import DEFAULT_SETTINGS_PATH, LMTSSettings, load_settings, save_settings
from lmts.core.store import RunStore
from lmts.lib.view import SplitCursesViewHost, choose_directory
from lmts.reporting import project_matrix_bundle
from lmts.tests.base import test_ref
from lmts.tests.catalog import default_test_matrix, default_test_type_registry
from lmts.tests.types import TestParameter, TestTypeDefinition
from lmts.tools.report_publish import publish_report
from lmts.tools.web_deploy import deploy_web_root

from .controller import LMTSViewController
from .output_dialog import choose_ftp_profile, choose_output_target, manage_ftp_profiles
from .projector import LMTSViewProjector
from .results import cell_verdict, format_run_result, matrix_label


FOOTER = (
    "m models  t matrix  n add  d remove  r run  a all  v results  "
    "c cancel  e errors  o output  s settings  x refresh  q q q quit"
)


def _next_instance_id(controller: LMTSViewController, definition: TestTypeDefinition) -> str:
    base = definition.id.rsplit(".", 1)[-1].replace("_", "-")
    used = {getattr(test, "instance_id", "") for test in controller.state.tests}
    index = 1
    while f"{base}-{index}" in used:
        index += 1
    return f"{base}-{index}"


def _short_test_label(ref: str) -> str:
    return (ref.split("#", 1)[-1] if "#" in ref else ref.rsplit(".", 1)[-1])[:18]


def run() -> None:
    test_types = default_test_type_registry()
    matrix = default_test_matrix(test_types)
    controller = LMTSViewController(default_provider_registry(), test_types, matrix)
    controller.refresh()
    projector = LMTSViewProjector(controller.state)
    settings = load_settings(DEFAULT_SETTINGS_PATH)

    def app(stdscr: curses.window) -> None:
        nonlocal settings
        host = SplitCursesViewHost(
            "LMTS",
            lambda: projector.project().lines,
            lambda: projector.project().status,
            controller.response_monitor.lines,
            monitor_title="Bot response",
            monitor_fraction=1 / 3,
            footer=FOOTER,
        )

        host.message = (
            "system profile required before testing"
            if controller.state.profile_required
            else controller.state.message
        )
        host.draw(stdscr)

        if controller.state.profile_required:
            controller.profile()
            host.message = controller.state.message
            host.draw(stdscr)

        def show_progress() -> None:
            host.progress_dialog(
                stdscr,
                "Test progress",
                controller.state.progress_lines,
                lambda: not controller.state.running,
                cancel=controller.cancel,
            )
            host.message = controller.state.message

        def select_models(_stdscr: curses.window) -> None:
            if controller.state.running:
                host.message = "test matrix is running"
                return
            options = [model.id for model in controller.state.models]
            selected = {
                index
                for index, model in enumerate(controller.state.models)
                if model.id in controller.state.selected_model_ids
            }
            chosen = host.choose_many(
                stdscr,
                "Models",
                options,
                selected,
                include_all=True,
                all_label="All models",
            )
            if chosen is not None:
                controller.select_models(chosen)
                host.message = f"selected {len(chosen)} model(s)"

        def select_tests(_stdscr: curses.window) -> None:
            if controller.state.running:
                host.message = "test matrix is running"
                return
            options = [test_ref(test) for test in controller.state.tests]
            selected = {
                index
                for index, test in enumerate(controller.state.tests)
                if test_ref(test) in controller.state.selected_test_refs
            }
            chosen = host.choose_many(
                stdscr,
                "Configured test matrix",
                options,
                selected,
                include_all=True,
                all_label="All configured tests",
            )
            if chosen is not None:
                controller.select_tests(chosen)
                host.message = f"selected {len(chosen)} configured test(s)"

        def collect_parameter(parameter: TestParameter) -> object | None:
            if parameter.kind == "integer":
                default = parameter.default if isinstance(parameter.default, int) else 1
                return host.input_integer(
                    stdscr,
                    parameter.label,
                    default=default,
                    minimum=parameter.minimum if parameter.minimum is not None else -999999,
                    maximum=parameter.maximum if parameter.maximum is not None else 999999,
                )
            if parameter.kind == "boolean":
                chosen = host.choose(stdscr, parameter.label, ["false", "true"], 0)
                return None if chosen is None else chosen == 1
            if parameter.kind == "choice":
                chosen = host.choose(stdscr, parameter.label, list(parameter.choices), 0)
                return None if chosen is None else parameter.choices[chosen]
            initial = parameter.default if isinstance(parameter.default, str) else ""
            return host.input_multiline(stdscr, parameter.label, initial=initial)

        def add_test(_stdscr: curses.window) -> None:
            if controller.state.running:
                host.message = "test matrix is running"
                return
            definitions = controller.test_types.definitions()
            options = [f"{definition.ref}  {definition.title}" for definition in definitions]
            chosen = host.choose(stdscr, "Test type registry", options)
            if chosen is None:
                return
            definition = definitions[chosen]
            params: dict[str, object] = {}
            for parameter in definition.parameters:
                value = collect_parameter(parameter)
                if value is None:
                    host.message = "test configuration cancelled"
                    return
                params[parameter.name] = value
            instance_id = _next_instance_id(controller, definition)
            configured = controller.add_test(definition.ref, instance_id, params)
            host.message = controller.state.message
            if configured is not None:
                host.message = f"added: {configured.ref}"

        def remove_test(_stdscr: curses.window) -> None:
            if controller.state.running:
                host.message = "test matrix is running"
                return
            tests = list(controller.state.tests)
            options = [test_ref(test) for test in tests]
            chosen = host.choose(stdscr, "Remove configured test", options)
            if chosen is None:
                return
            controller.remove_test(getattr(tests[chosen], "instance_id", ""))
            host.message = controller.state.message

        def run_selected(_stdscr: curses.window) -> None:
            started = controller.run_selected()
            host.message = controller.state.message
            if started:
                show_progress()

        def test_all(_stdscr: curses.window) -> None:
            started = controller.test_all()
            host.message = controller.state.message
            if started:
                show_progress()

        def export_matrix(matrix_data: dict) -> Path | None:
            try:
                path = export_matrix_bundle(
                    matrix_data,
                    Path(settings.output_folder),
                    results_root=controller.results_root,
                )
            except (OSError, ValueError) as exc:
                host.message = f"matrix export failed: {exc}"
                return None
            host.message = f"exported matrix: {path}"
            return path

        def export_run(run_data: dict) -> Path | None:
            try:
                path = export_run_json(run_data, Path(settings.output_folder))
            except (OSError, ValueError) as exc:
                host.message = f"run export failed: {exc}"
                return None
            host.message = f"exported run: {path}"
            return path

        def choose_matrix_result(title: str) -> tuple[Path, dict] | None:
            matrices = controller.recent_matrices()
            if not matrices:
                host.message = "no canonical matrix results found"
                return None
            chosen_matrix = 0
            if len(matrices) > 1:
                options = [matrix_label(data, path) for path, data in matrices]
                selected = host.choose(stdscr, title, options)
                if selected is None:
                    return None
                chosen_matrix = selected
            return matrices[chosen_matrix]

        def browse_results(_stdscr: curses.window) -> None:
            chosen = choose_matrix_result("Matrix results (newest first)")
            if chosen is None:
                return
            matrix_path, matrix_data = chosen
            models = [str(value) for value in (matrix_data.get("model_ids") or [])]
            tests = [str(value) for value in (matrix_data.get("test_refs") or [])]
            cells = [cell for cell in (matrix_data.get("cells") or []) if isinstance(cell, dict)]
            by_key = {
                (str(cell.get("model_id")), str(cell.get("test_ref"))): cell
                for cell in cells
            }
            values = [
                [cell_verdict(by_key.get((model, test))) for test in tests]
                for model in models
            ]
            summary = (
                f"PASS {int(matrix_data.get('passed') or 0)}  "
                f"FAIL {int(matrix_data.get('failed') or 0)}  "
                f"ERROR {int(matrix_data.get('errors') or 0)}  "
                f"CANCEL {int(matrix_data.get('cancelled') or 0)}"
            )
            selected_cell = host.matrix_browser(
                stdscr,
                f"Results: {str(matrix_data.get('started_at') or '').replace('T', ' ')[:19]}",
                models,
                [_short_test_label(ref) for ref in tests],
                values,
                summary=summary,
            )
            if selected_cell is None:
                host.message = f"viewed matrix: {matrix_path}"
                return

            row_index, col_index = selected_cell
            cell = by_key.get((models[row_index], tests[col_index]))
            run_id = str(cell.get("run_id") or "?") if cell is not None else "-"
            run_action = host.choose(
                stdscr,
                f"Result actions: {run_id}",
                [
                    "View details",
                    f"Export selected run -> {settings.output_folder}",
                    f"Export matrix -> {settings.output_folder}",
                ],
            )
            if run_action is None:
                return
            if run_action == 2:
                export_matrix(matrix_data)
                return
            if cell is None:
                host.message = "no run for selected matrix cell"
                return

            result_path = Path(str(cell.get("result_path") or ""))
            if not result_path.is_file():
                host.message = f"canonical run result missing: {result_path}"
                return
            try:
                run_data = RunStore(controller.results_root).load(result_path)
            except (OSError, ValueError) as exc:
                host.message = f"cannot load run result: {exc}"
                return
            if run_action == 1:
                export_run(run_data)
                return

            host.text_viewer(
                stdscr,
                f"Run result: {cell.get('run_id', result_path.stem)}",
                format_run_result(run_data, result_path),
            )
            host.message = f"viewed matrix cell: {cell.get('run_id', '?')}"

        def output_tools(_stdscr: curses.window) -> None:
            if controller.state.running:
                host.message = "output tools unavailable while test matrix is running"
                return
            action = host.choose(
                stdscr,
                "Output",
                [
                    "Publish report to MySQL server",
                    "Deploy web root",
                    "FTP profiles",
                ],
            )
            if action is None:
                return
            if action == 2:
                try:
                    manage_ftp_profiles(host, stdscr)
                except (OSError, ValueError) as exc:
                    host.message = f"FTP profile error: {exc}"
                return
            if action == 1:
                try:
                    target = choose_output_target(host, stdscr, disk_initial="/home/www/lmts")
                    if target is None:
                        return
                    written = deploy_web_root(target)
                    host.message = f"deployed {len(written)} web file(s)"
                except (OSError, ValueError, RuntimeError) as exc:
                    host.message = f"web deploy failed: {exc}"
                return

            chosen = choose_matrix_result("Publish matrix report")
            if chosen is None:
                return
            _matrix_path, matrix_data = chosen
            try:
                profile = choose_ftp_profile(host, stdscr)
                if profile is None:
                    return
                bundle = build_matrix_bundle(matrix_data, results_root=controller.results_root)
                report = project_matrix_bundle(bundle)
                report_id = publish_report(report, profile)
                host.message = f"published report: {report_id}"
            except (OSError, ValueError, RuntimeError) as exc:
                host.message = f"report publish failed: {exc}"

        def cancel(_stdscr: curses.window) -> None:
            controller.cancel()
            host.message = controller.state.message

        def export_errors(_stdscr: curses.window) -> None:
            path = controller.export_errors("task")
            host.message = controller.state.message if path is None else f"exported: {path}"

        def settings_dialog(_stdscr: curses.window) -> None:
            nonlocal settings
            if controller.state.running:
                host.message = "settings unavailable while test matrix is running"
                return
            while True:
                chosen = host.choose(
                    stdscr,
                    "Settings",
                    [
                        f"Output folder  {settings.output_folder}",
                        "Profile system",
                    ],
                )
                if chosen is None:
                    return
                if chosen == 0:
                    selected = choose_directory(
                        host,
                        stdscr,
                        "Output folder",
                        initial=settings.output_folder,
                    )
                    if selected is None:
                        continue
                    settings = LMTSSettings(output_folder=str(selected))
                    path = save_settings(settings, DEFAULT_SETTINGS_PATH)
                    host.message = f"output folder saved: {settings.output_folder} ({path})"
                    continue
                controller.profile()
                host.message = controller.state.message

        def refresh(_stdscr: curses.window) -> None:
            controller.refresh()
            host.message = controller.state.message

        host.handlers.update({
            "m": select_models,
            "t": select_tests,
            "n": add_test,
            "d": remove_test,
            "r": run_selected,
            "a": test_all,
            "v": browse_results,
            "c": cancel,
            "e": export_errors,
            "o": output_tools,
            "s": settings_dialog,
            "x": refresh,
        })
        host.run(stdscr)

    curses.wrapper(app)


def main() -> int:
    run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
