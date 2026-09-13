from __future__ import annotations

import curses
from collections.abc import Callable, Sequence

from .curses_host import CursesViewHost


class SplitCursesViewHost(CursesViewHost):
    """Curses host with a passive read-only monitor occupying the lower pane."""

    def __init__(
        self,
        title: str,
        render: Callable[[], Sequence[str]],
        status: Callable[[], str],
        monitor_render: Callable[[], Sequence[str]],
        *,
        monitor_title: str = "Response monitor",
        monitor_fraction: float = 1 / 3,
        footer: str = "up/down scroll  q q q quit",
        quit_sequence: str = "qqq",
    ) -> None:
        super().__init__(title, render, status, footer=footer, quit_sequence=quit_sequence)
        self.monitor_render = monitor_render
        self.monitor_title = monitor_title
        self.monitor_fraction = max(0.2, min(0.5, monitor_fraction))

    @staticmethod
    def _safe_addnstr(win: curses.window, y: int, x: int, text: str, width: int, attr: int = 0) -> None:
        try:
            win.addnstr(y, x, text, max(0, width), attr)
        except curses.error:
            pass

    def text_viewer(
        self,
        stdscr: curses.window,
        title: str,
        lines: Sequence[str],
    ) -> None:
        """Scrollable read-only full-screen detail viewer."""
        scroll = 0
        while True:
            height, width = stdscr.getmaxyx()
            content_h = max(1, height - 3)
            scroll = min(max(0, scroll), max(0, len(lines) - content_h))
            stdscr.erase()
            self._safe_addnstr(stdscr, 0, 0, title, width - 1, curses.A_BOLD)
            for row, line in enumerate(lines[scroll : scroll + content_h], start=1):
                self._safe_addnstr(stdscr, row, 0, str(line), width - 1)
            self._safe_addnstr(
                stdscr,
                height - 1,
                0,
                "Up/Down/PgUp/PgDn scroll  Esc/Enter close",
                width - 1,
                curses.A_DIM,
            )
            stdscr.refresh()
            key = stdscr.get_wch()
            if key in ("\x1b", "\n", "\r") or key == curses.KEY_ENTER:
                return
            if key == curses.KEY_UP:
                scroll = max(0, scroll - 1)
            elif key == curses.KEY_DOWN:
                scroll += 1
            elif key == curses.KEY_PPAGE:
                scroll = max(0, scroll - content_h)
            elif key == curses.KEY_NPAGE:
                scroll += content_h
            elif key == curses.KEY_HOME:
                scroll = 0
            elif key == curses.KEY_END:
                scroll = max(0, len(lines) - content_h)

    def draw(self, stdscr: curses.window, *, commit: bool = True) -> None:
        """Render the split layout into curses' virtual screen.

        When commit=False the caller may compose additional windows before one
        atomic doupdate(), avoiding visible erase/redraw cycles between panes.
        """
        lines = list(self.render())
        monitor_lines = list(self.monitor_render())
        height, width = stdscr.getmaxyx()

        footer_rows = 2
        usable = max(4, height - footer_rows)
        monitor_h = max(4, int(usable * self.monitor_fraction))
        main_h = max(3, usable - monitor_h)
        if main_h + monitor_h > usable:
            monitor_h = max(3, usable - main_h)

        main_content_h = max(1, main_h - 2)
        self.scroll = min(max(0, self.scroll), max(0, len(lines) - main_content_h))

        stdscr.erase()
        self._safe_addnstr(stdscr, 0, 0, self.title, width - 1, curses.A_BOLD)
        self._safe_addnstr(stdscr, 1, 0, self.status(), width - 1)
        for row, line in enumerate(lines[self.scroll : self.scroll + main_content_h], start=2):
            if row >= main_h:
                break
            self._safe_addnstr(stdscr, row, 0, str(line), width - 1)

        separator_y = main_h
        self._safe_addnstr(stdscr, separator_y, 0, "─" * max(1, width - 1), width - 1, curses.A_DIM)
        title = f" {self.monitor_title} "
        self._safe_addnstr(stdscr, separator_y, 2, title, min(len(title), max(0, width - 4)), curses.A_BOLD)

        monitor_body_h = max(1, monitor_h - 1)
        tail = monitor_lines[-monitor_body_h:]
        for offset, line in enumerate(tail, start=separator_y + 1):
            if offset >= height - footer_rows:
                break
            self._safe_addnstr(stdscr, offset, 0, str(line), width - 1)

        quit_hint = ""
        if self._quit:
            remaining = max(0, len(self.quit_sequence) - len(self._quit))
            quit_hint = f"quit: {self._quit}{'_' * remaining}"
        self._safe_addnstr(stdscr, height - 2, 0, self.message or quit_hint, width - 1)
        self._safe_addnstr(stdscr, height - 1, 0, self.footer, width - 1, curses.A_DIM)

        stdscr.noutrefresh()
        if commit:
            curses.doupdate()

    def progress_dialog(
        self,
        stdscr: curses.window,
        title: str,
        render_lines: Callable[[], Sequence[str]],
        is_done: Callable[[], bool],
        *,
        poll_ms: int = 200,
        cancel: Callable[[], None] | None = None,
    ) -> None:
        """Keep split view and modal live in one atomic curses update."""
        while True:
            # Stage background first, but do not touch the physical terminal yet.
            self.draw(stdscr, commit=False)

            lines = list(render_lines())
            height, width = stdscr.getmaxyx()
            visible = max(1, min(len(lines), height - 7, 20))
            win_h = visible + 4
            widest = max([len(title) + 4, 36, *(len(str(line)) + 4 for line in lines)])
            win_w = max(36, min(width - 4, widest))
            win = curses.newwin(
                win_h,
                win_w,
                max(0, (height - win_h) // 2),
                max(0, (width - win_w) // 2),
            )
            win.keypad(True)
            win.timeout(poll_ms)
            win.erase()
            win.box()
            self._safe_addnstr(win, 0, 2, f" {title} ", win_w - 4)
            for screen_row, line in enumerate(lines[:visible], start=1):
                self._safe_addnstr(win, screen_row, 2, str(line), win_w - 4)
            footer = "Enter close" if is_done() else (
                "c cancel  Esc hide" if cancel else "Esc hide; test continues"
            )
            self._safe_addnstr(win, win_h - 2, 2, footer, win_w - 4, curses.A_DIM)

            # Stage modal over the background and commit the full frame once.
            win.noutrefresh()
            curses.doupdate()

            key = win.getch()
            if is_done() and key in (curses.KEY_ENTER, 10, 13, 27, -1):
                return
            if key == 27:
                return
            if cancel is not None and key in (ord("c"), ord("C")):
                cancel()

    def run(self, stdscr: curses.window) -> None:
        curses.curs_set(0)
        stdscr.keypad(True)
        stdscr.timeout(200)

        while True:
            self.draw(stdscr)
            try:
                key = stdscr.get_wch()
            except curses.error:
                continue
            if key == curses.KEY_UP:
                self.scroll = max(0, self.scroll - 1)
                self._quit = ""
                continue
            if key == curses.KEY_DOWN:
                self.scroll += 1
                self._quit = ""
                continue
            if not isinstance(key, str):
                self._quit = ""
                continue
            expected = self.quit_sequence[len(self._quit) : len(self._quit) + 1]
            if expected and key == expected:
                self._quit += key
                if self._quit == self.quit_sequence:
                    return
                continue
            self._quit = ""
            handler = self.handlers.get(key)
            if handler is not None:
                handler(stdscr)
