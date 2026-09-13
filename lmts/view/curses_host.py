from __future__ import annotations

import curses
from collections.abc import Callable, Sequence


class CursesViewHost:
    """Terminal mechanics only; no LMTS semantics."""

    def __init__(self, title: str, render: Callable[[], Sequence[str]], status: Callable[[], str]) -> None:
        self.title = title
        self.render = render
        self.status = status
        self.handlers: dict[str, Callable[[curses.window], None]] = {}
        self.message = ""
        self.scroll = 0
        self._quit = ""

    def choose(self, stdscr: curses.window, title: str, options: Sequence[str], selected: int = 0) -> int | None:
        if not options:
            self.message = "no choices available"
            return None
        index = min(max(0, selected), len(options) - 1)
        while True:
            height, width = stdscr.getmaxyx()
            visible = max(1, min(len(options), height - 6, 20))
            offset = min(max(0, index - visible + 1), max(0, len(options) - visible))
            win_h = visible + 2
            win_w = max(32, min(width - 4, max(len(title) + 4, *(len(x) + 4 for x in options))))
            win = curses.newwin(win_h, win_w, max(0, (height - win_h) // 2), max(0, (width - win_w) // 2))
            win.keypad(True)
            win.erase()
            win.box()
            win.addnstr(0, 2, f" {title} ", max(0, win_w - 4))
            for row, option_index in enumerate(range(offset, min(len(options), offset + visible)), start=1):
                attr = curses.A_REVERSE if option_index == index else curses.A_NORMAL
                win.addnstr(row, 2, options[option_index], max(0, win_w - 4), attr)
            win.refresh()
            key = win.get_wch()
            if key == curses.KEY_UP:
                index = max(0, index - 1)
            elif key == curses.KEY_DOWN:
                index = min(len(options) - 1, index + 1)
            elif key in ("\n", "\r") or key == curses.KEY_ENTER:
                return index
            elif key == "\x1b":
                return None

    def run(self, stdscr: curses.window) -> None:
        curses.curs_set(0)
        stdscr.keypad(True)
        while True:
            lines = list(self.render())
            height, width = stdscr.getmaxyx()
            content_h = max(1, height - 4)
            self.scroll = min(max(0, self.scroll), max(0, len(lines) - content_h))
            stdscr.erase()
            stdscr.addnstr(0, 0, self.title, max(0, width - 1), curses.A_BOLD)
            stdscr.addnstr(1, 0, self.status(), max(0, width - 1))
            for row, line in enumerate(lines[self.scroll:self.scroll + content_h], start=2):
                if row >= height - 2:
                    break
                stdscr.addnstr(row, 0, str(line), max(0, width - 1))
            footer = "m model  t test  r run  b benchmark  p profile  x refresh  q q q quit"
            message = self.message or (f"quit: {self._quit}{'_' * (3-len(self._quit))}" if self._quit else "")
            stdscr.addnstr(height - 2, 0, message, max(0, width - 1))
            stdscr.addnstr(height - 1, 0, footer, max(0, width - 1), curses.A_DIM)
            stdscr.refresh()
            key = stdscr.get_wch()
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
            if key == "q":
                self._quit += "q"
                if self._quit == "qqq":
                    return
                continue
            self._quit = ""
            handler = self.handlers.get(key)
            if handler is not None:
                handler(stdscr)
