from __future__ import annotations

import curses
from collections.abc import Callable, Sequence


class CursesViewHost:
    """Reusable terminal host with no domain semantics."""

    def __init__(
        self,
        title: str,
        render: Callable[[], Sequence[str]],
        status: Callable[[], str],
        *,
        footer: str = "up/down scroll  q q q quit",
        quit_sequence: str = "qqq",
    ) -> None:
        self.title = title
        self.render = render
        self.status = status
        self.footer = footer
        self.quit_sequence = quit_sequence
        self.handlers: dict[str, Callable[[curses.window], None]] = {}
        self.message = ""
        self.scroll = 0
        self._quit = ""

    def choose(
        self,
        stdscr: curses.window,
        title: str,
        options: Sequence[str],
        selected: int = 0,
    ) -> int | None:
        if not options:
            self.message = "no choices available"
            return None
        index = min(max(0, selected), len(options) - 1)
        while True:
            height, width = stdscr.getmaxyx()
            visible = max(1, min(len(options), height - 6, 20))
            offset = min(max(0, index - visible + 1), max(0, len(options) - visible))
            win_h = visible + 2
            win_w = max(
                32,
                min(width - 4, max(len(title) + 4, *(len(x) + 4 for x in options))),
            )
            win = curses.newwin(
                win_h,
                win_w,
                max(0, (height - win_h) // 2),
                max(0, (width - win_w) // 2),
            )
            win.keypad(True)
            win.erase()
            win.box()
            win.addnstr(0, 2, f" {title} ", max(0, win_w - 4))
            for row, option_index in enumerate(
                range(offset, min(len(options), offset + visible)), start=1
            ):
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

    def choose_many(
        self,
        stdscr: curses.window,
        title: str,
        options: Sequence[str],
        selected: set[int] | None = None,
        *,
        include_all: bool = True,
        all_label: str = "All",
    ) -> set[int] | None:
        if not options:
            self.message = "no choices available"
            return None

        selected_indices = set(selected or set())
        index = 0
        row_count = len(options) + (1 if include_all else 0)

        def all_selected() -> bool:
            return len(selected_indices) == len(options)

        while True:
            labels: list[str] = []
            if include_all:
                mark = "x" if all_selected() else " "
                labels.append(f"[{mark}] {all_label}")
            for option_index, option in enumerate(options):
                mark = "x" if option_index in selected_indices else " "
                labels.append(f"[{mark}] {option}")

            height, width = stdscr.getmaxyx()
            visible = max(1, min(row_count, height - 7, 20))
            offset = min(max(0, index - visible + 1), max(0, row_count - visible))
            win_h = visible + 3
            win_w = max(
                36,
                min(width - 4, max(len(title) + 4, *(len(x) + 4 for x in labels))),
            )
            win = curses.newwin(
                win_h,
                win_w,
                max(0, (height - win_h) // 2),
                max(0, (width - win_w) // 2),
            )
            win.keypad(True)
            win.erase()
            win.box()
            win.addnstr(0, 2, f" {title} ", max(0, win_w - 4))
            for row, option_row in enumerate(
                range(offset, min(row_count, offset + visible)), start=1
            ):
                attr = curses.A_REVERSE if option_row == index else curses.A_NORMAL
                win.addnstr(row, 2, labels[option_row], max(0, win_w - 4), attr)
            win.addnstr(
                win_h - 2,
                2,
                "Space toggle  Enter accept  Esc cancel",
                max(0, win_w - 4),
                curses.A_DIM,
            )
            win.refresh()

            key = win.get_wch()
            if key == curses.KEY_UP:
                index = max(0, index - 1)
                continue
            if key == curses.KEY_DOWN:
                index = min(row_count - 1, index + 1)
                continue
            if key == " ":
                if include_all and index == 0:
                    if all_selected():
                        selected_indices.clear()
                    else:
                        selected_indices = set(range(len(options)))
                else:
                    option_index = index - 1 if include_all else index
                    if option_index in selected_indices:
                        selected_indices.remove(option_index)
                    else:
                        selected_indices.add(option_index)
                continue
            if key in ("\n", "\r") or key == curses.KEY_ENTER:
                return selected_indices
            if key == "\x1b":
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
            for row, line in enumerate(
                lines[self.scroll : self.scroll + content_h], start=2
            ):
                if row >= height - 2:
                    break
                stdscr.addnstr(row, 0, str(line), max(0, width - 1))

            quit_hint = ""
            if self._quit:
                remaining = max(0, len(self.quit_sequence) - len(self._quit))
                quit_hint = f"quit: {self._quit}{'_' * remaining}"
            message = self.message or quit_hint
            stdscr.addnstr(height - 2, 0, message, max(0, width - 1))
            stdscr.addnstr(
                height - 1,
                0,
                self.footer,
                max(0, width - 1),
                curses.A_DIM,
            )
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
