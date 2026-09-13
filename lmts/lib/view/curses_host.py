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
                labels.append(f"[{'x' if all_selected() else ' '}] {all_label}")
            for option_index, option in enumerate(options):
                labels.append(f"[{'x' if option_index in selected_indices else ' '}] {option}")
            height, width = stdscr.getmaxyx()
            visible = max(1, min(row_count, height - 7, 20))
            offset = min(max(0, index - visible + 1), max(0, row_count - visible))
            win_h = visible + 3
            win_w = max(36, min(width - 4, max(len(title) + 4, *(len(x) + 4 for x in labels))))
            win = curses.newwin(win_h, win_w, max(0, (height - win_h) // 2), max(0, (width - win_w) // 2))
            win.keypad(True)
            win.erase()
            win.box()
            win.addnstr(0, 2, f" {title} ", max(0, win_w - 4))
            for row, option_row in enumerate(range(offset, min(row_count, offset + visible)), start=1):
                attr = curses.A_REVERSE if option_row == index else curses.A_NORMAL
                win.addnstr(row, 2, labels[option_row], max(0, win_w - 4), attr)
            win.addnstr(win_h - 2, 2, "Space toggle  Enter accept  Esc cancel", max(0, win_w - 4), curses.A_DIM)
            win.refresh()
            key = win.get_wch()
            if key == curses.KEY_UP:
                index = max(0, index - 1)
            elif key == curses.KEY_DOWN:
                index = min(row_count - 1, index + 1)
            elif key == " ":
                if include_all and index == 0:
                    selected_indices = set() if all_selected() else set(range(len(options)))
                else:
                    option_index = index - 1 if include_all else index
                    if option_index in selected_indices:
                        selected_indices.remove(option_index)
                    else:
                        selected_indices.add(option_index)
            elif key in ("\n", "\r") or key == curses.KEY_ENTER:
                return selected_indices
            elif key == "\x1b":
                return None

    def input_integer(
        self,
        stdscr: curses.window,
        title: str,
        *,
        default: int = 1,
        minimum: int = 1,
        maximum: int = 999,
    ) -> int | None:
        value = str(default)
        while True:
            height, width = stdscr.getmaxyx()
            win_h, win_w = 5, max(36, min(width - 4, len(title) + 12))
            win = curses.newwin(win_h, win_w, max(0, (height - win_h) // 2), max(0, (width - win_w) // 2))
            win.keypad(True)
            win.erase()
            win.box()
            win.addnstr(0, 2, f" {title} ", max(0, win_w - 4))
            win.addnstr(2, 2, value or "_", max(0, win_w - 4))
            win.addnstr(3, 2, "Enter accept  Esc cancel", max(0, win_w - 4), curses.A_DIM)
            win.refresh()
            key = win.get_wch()
            if key == "\x1b":
                return None
            if key in ("\n", "\r") or key == curses.KEY_ENTER:
                if value:
                    number = int(value)
                    if minimum <= number <= maximum:
                        return number
                continue
            if key in (curses.KEY_BACKSPACE, "\b", "\x7f"):
                value = value[:-1]
            elif isinstance(key, str) and key.isdigit():
                value += key

    def input_multiline(
        self,
        stdscr: curses.window,
        title: str,
        *,
        initial: str = "",
    ) -> str | None:
        """Scrollable multiline editor suitable for large pasted text.

        Enter inserts a newline. F2 accepts. Esc cancels.
        """
        lines = initial.split("\n") or [""]
        row = len(lines) - 1
        col = len(lines[row])
        scroll = 0
        while True:
            height, width = stdscr.getmaxyx()
            win_h = max(8, min(height - 2, 24))
            win_w = max(40, min(width - 2, 120))
            body_h = win_h - 4
            body_w = win_w - 4
            scroll = min(max(0, scroll), max(0, row))
            if row < scroll:
                scroll = row
            elif row >= scroll + body_h:
                scroll = row - body_h + 1
            win = curses.newwin(win_h, win_w, max(0, (height - win_h) // 2), max(0, (width - win_w) // 2))
            win.keypad(True)
            win.erase()
            win.box()
            win.addnstr(0, 2, f" {title} ", max(0, win_w - 4))
            for screen_row, source_row in enumerate(range(scroll, min(len(lines), scroll + body_h)), start=1):
                win.addnstr(screen_row, 2, lines[source_row], body_w)
            win.addnstr(win_h - 2, 2, "Enter newline  F2 accept  Esc cancel", body_w, curses.A_DIM)
            cursor_y = 1 + row - scroll
            cursor_x = 2 + min(col, max(0, body_w - 1))
            try:
                curses.curs_set(1)
                win.move(cursor_y, cursor_x)
            except curses.error:
                pass
            win.refresh()
            key = win.get_wch()
            if key == "\x1b":
                curses.curs_set(0)
                return None
            if key == curses.KEY_F2:
                curses.curs_set(0)
                return "\n".join(lines)
            if key == curses.KEY_UP:
                row = max(0, row - 1)
                col = min(col, len(lines[row]))
            elif key == curses.KEY_DOWN:
                row = min(len(lines) - 1, row + 1)
                col = min(col, len(lines[row]))
            elif key == curses.KEY_LEFT:
                if col > 0:
                    col -= 1
                elif row > 0:
                    row -= 1
                    col = len(lines[row])
            elif key == curses.KEY_RIGHT:
                if col < len(lines[row]):
                    col += 1
                elif row < len(lines) - 1:
                    row += 1
                    col = 0
            elif key in (curses.KEY_HOME,):
                col = 0
            elif key in (curses.KEY_END,):
                col = len(lines[row])
            elif key in (curses.KEY_BACKSPACE, "\b", "\x7f"):
                if col > 0:
                    lines[row] = lines[row][: col - 1] + lines[row][col:]
                    col -= 1
                elif row > 0:
                    previous = lines[row - 1]
                    col = len(previous)
                    lines[row - 1] = previous + lines[row]
                    del lines[row]
                    row -= 1
            elif key in ("\n", "\r") or key == curses.KEY_ENTER:
                tail = lines[row][col:]
                lines[row] = lines[row][:col]
                lines.insert(row + 1, tail)
                row += 1
                col = 0
            elif isinstance(key, str) and key.isprintable():
                lines[row] = lines[row][:col] + key + lines[row][col:]
                col += len(key)

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
        while True:
            lines = list(render_lines())
            height, width = stdscr.getmaxyx()
            visible = max(1, min(len(lines), height - 7, 20))
            win_h = visible + 4
            widest = max([len(title) + 4, 36, *(len(str(line)) + 4 for line in lines)])
            win_w = max(36, min(width - 4, widest))
            win = curses.newwin(win_h, win_w, max(0, (height - win_h) // 2), max(0, (width - win_w) // 2))
            win.keypad(True)
            win.timeout(poll_ms)
            win.erase()
            win.box()
            win.addnstr(0, 2, f" {title} ", max(0, win_w - 4))
            for screen_row, line in enumerate(lines[:visible], start=1):
                win.addnstr(screen_row, 2, str(line), max(0, win_w - 4))
            footer = "Enter close" if is_done() else ("c cancel  Esc hide" if cancel else "Esc hide; test continues")
            win.addnstr(win_h - 2, 2, footer, max(0, win_w - 4), curses.A_DIM)
            win.refresh()
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
        stdscr.timeout(250)
        while True:
            lines = list(self.render())
            height, width = stdscr.getmaxyx()
            content_h = max(1, height - 4)
            self.scroll = min(max(0, self.scroll), max(0, len(lines) - content_h))
            stdscr.erase()
            stdscr.addnstr(0, 0, self.title, max(0, width - 1), curses.A_BOLD)
            stdscr.addnstr(1, 0, self.status(), max(0, width - 1))
            for screen_row, line in enumerate(lines[self.scroll:self.scroll + content_h], start=2):
                if screen_row >= height - 2:
                    break
                stdscr.addnstr(screen_row, 0, str(line), max(0, width - 1))
            quit_hint = ""
            if self._quit:
                remaining = max(0, len(self.quit_sequence) - len(self._quit))
                quit_hint = f"quit: {self._quit}{'_' * remaining}"
            stdscr.addnstr(height - 2, 0, self.message or quit_hint, max(0, width - 1))
            stdscr.addnstr(height - 1, 0, self.footer, max(0, width - 1), curses.A_DIM)
            stdscr.refresh()
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
            expected = self.quit_sequence[len(self._quit):len(self._quit) + 1]
            if expected and key == expected:
                self._quit += key
                if self._quit == self.quit_sequence:
                    return
                continue
            self._quit = ""
            handler = self.handlers.get(key)
            if handler is not None:
                handler(stdscr)
