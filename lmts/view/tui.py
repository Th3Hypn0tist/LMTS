from __future__ import annotations

import curses

from lmts.cli import default_provider_registry, default_test_registry

from .controller import LMTSViewController
from .curses_host import CursesViewHost
from .projector import LMTSViewProjector


def run() -> None:
    controller = LMTSViewController(default_provider_registry(), default_test_registry())
    controller.refresh()
    projector = LMTSViewProjector(controller.state)

    def app(stdscr: curses.window) -> None:
        host = CursesViewHost(
            "LMTS",
            lambda: projector.project().lines,
            lambda: projector.project().status,
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
