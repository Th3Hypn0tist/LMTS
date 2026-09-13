from __future__ import annotations

import curses

from lmts.cli import default_provider_registry, default_test_registry
from lmts.lib.view import CursesViewHost

from .controller import LMTSViewController
from .projector import LMTSViewProjector


FOOTER = (
    "m models  t tests  r run matrix  a test all  e export errors  "
    "p profile  x refresh  q q q quit"
)


def run() -> None:
    controller = LMTSViewController(default_provider_registry(), default_test_registry())
    controller.refresh()
    projector = LMTSViewProjector(controller.state)

    def app(stdscr: curses.window) -> None:
        host = CursesViewHost(
            "LMTS",
            lambda: projector.project().lines,
            lambda: projector.project().status,
            footer=FOOTER,
        )

        def select_models(_stdscr: curses.window) -> None:
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
            options = [f"{test.id}@{test.version}" for test in controller.state.tests]
            selected = {
                index
                for index, test in enumerate(controller.state.tests)
                if f"{test.id}@{test.version}" in controller.state.selected_test_refs
            }
            chosen = host.choose_many(
                stdscr,
                "Tests",
                options,
                selected,
                include_all=True,
                all_label="Test all",
            )
            if chosen is not None:
                controller.select_tests(chosen)
                host.message = f"selected {len(chosen)} test(s)"

        def run_selected(_stdscr: curses.window) -> None:
            host.message = "running selected test matrix..."
            stdscr.refresh()
            controller.run_selected()
            host.message = controller.state.message

        def test_all(_stdscr: curses.window) -> None:
            host.message = "running all tests on all models..."
            stdscr.refresh()
            controller.test_all()
            host.message = controller.state.message

        def export_errors(_stdscr: curses.window) -> None:
            path = controller.export_errors("task")
            host.message = controller.state.message
            if path is not None:
                host.message = f"exported: {path}"

        def profile(_stdscr: curses.window) -> None:
            controller.profile()
            host.message = controller.state.message

        def refresh(_stdscr: curses.window) -> None:
            controller.refresh()
            host.message = controller.state.message

        host.handlers.update({
            "m": select_models,
            "t": select_tests,
            "r": run_selected,
            "a": test_all,
            "e": export_errors,
            "p": profile,
            "x": refresh,
        })
        host.run(stdscr)

    curses.wrapper(app)


def main() -> int:
    run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
