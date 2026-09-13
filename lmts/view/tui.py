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

        def select_model(_stdscr: curses.window) -> None:
            options = [model.id for model in controller.state.models]
            index = host.choose(stdscr, "Model", options, controller.state.selected_model)
            if index is not None:
                controller.select_model(index)

        def select_test(_stdscr: curses.window) -> None:
            options = [f"{test.id}@{test.version}" for test in controller.state.tests]
            index = host.choose(stdscr, "Test", options, controller.state.selected_test)
            if index is not None:
                controller.select_test(index)

        def run_selected(_stdscr: curses.window) -> None:
            host.message = "running selected test..."
            stdscr.refresh()
            controller.run_selected()
            host.message = controller.state.message

        def benchmark(_stdscr: curses.window) -> None:
            host.message = "running benchmark on all local models..."
            stdscr.refresh()
            controller.benchmark_all_local()
            host.message = controller.state.message

        def profile(_stdscr: curses.window) -> None:
            controller.profile()
            host.message = controller.state.message

        def refresh(_stdscr: curses.window) -> None:
            controller.refresh()
            host.message = controller.state.message

        host.handlers.update({
            "m": select_model,
            "t": select_test,
            "r": run_selected,
            "b": benchmark,
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
