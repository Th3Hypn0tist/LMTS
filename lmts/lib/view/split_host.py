from __future__ import annotations

import curses
from collections.abc import Callable, Sequence

from .curses_host import CursesViewHost


POLL_MS = 200


class SplitCursesViewHost(CursesViewHost):
    """Curses host with an optional passive read-only lower pane."""

    def __init__(
        self,
        title: str,
        render: Callable[[], Sequence[str]],
        status: Callable[[], str],
        monitor_render: Callable[[], Sequence[str]],
        *,
        monitor_title: str = "Console",
        monitor_fraction: float = 1 / 3,
        footer: str = "up/down scroll  q q q quit",
        quit_sequence: str = "qqq",
    ) -> None:
        super().__init__(title, render, status, footer=footer, quit_sequence=quit_sequence)
        self.monitor_render = monitor_render
        self.monitor_title = monitor_title
        self.monitor_fraction = max(0.2, min(0.5, monitor_fraction))
        self.monitor_visible = True

    def toggle_monitor(self) -> bool:
        self.monitor_visible = not self.monitor_visible
        return self.monitor_visible

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
            stdscr.timeout(-1)
            try:
                key = stdscr.get_wch()
            finally:
                stdscr.timeout(POLL_MS)
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

    def matrix_browser(
        self,
        stdscr: curses.window,
        title: str,
        row_labels: Sequence[str],
        column_labels: Sequence[str],
        values: Sequence[Sequence[str]],
        *,
        summary: str = "",
    ) -> tuple[int, int] | None:
        """Read-only matrix overview with selectable cells for drill-down."""
        if not row_labels or not column_labels:
            return None

        row_index = 0
        col_index = 0
        row_width = max(5, max(len(str(label)) for label in row_labels))
        col_width = max(
            8,
            max(
                [len(str(label)) for label in column_labels]
                + [len(str(value)) for row in values for value in row]
            ),
        )

        while True:
            height, width = stdscr.getmaxyx()
            screen_width = max(0, width - 1)
            stdscr.erase()
            self._safe_addnstr(stdscr, 0, 0, title, screen_width, curses.A_BOLD)

            cell_width = col_width + 2
            available_for_cells = max(1, screen_width - row_width)
            visible_column_count = max(1, available_for_cells // cell_width)
            start_col = min(
                max(0, col_index - visible_column_count + 1),
                max(0, len(column_labels) - visible_column_count),
            )
            end_col = min(len(column_labels), start_col + visible_column_count)

            header = f"{'MODEL':<{row_width}}"
            for label in column_labels[start_col:end_col]:
                header += f"  {str(label):^{col_width}}"
            self._safe_addnstr(stdscr, 2, 0, header, screen_width, curses.A_BOLD)

            separator = "-" * min(len(header), max(1, screen_width))
            self._safe_addnstr(stdscr, 3, 0, separator, screen_width, curses.A_DIM)

            max_rows = max(1, height - 7)
            start_row = min(max(0, row_index - max_rows + 1), max(0, len(row_labels) - max_rows))
            visible_rows = row_labels[start_row : start_row + max_rows]

            for screen_offset, row_label in enumerate(visible_rows, start=4):
                source_row = start_row + screen_offset - 4
                x = 0
                row_text = f"{str(row_label):<{row_width}}"
                row_piece = row_text[:screen_width]
                self._safe_addnstr(stdscr, screen_offset, x, row_piece, len(row_piece))
                x += row_width
                if x >= screen_width:
                    continue
                row_values = values[source_row]
                for source_col in range(start_col, min(end_col, len(row_values))):
                    value = row_values[source_col]
                    if x >= screen_width:
                        break
                    cell = f"  {str(value):^{col_width}}"
                    remaining = screen_width - x
                    piece = cell[:remaining]
                    attr = curses.A_REVERSE if source_row == row_index and source_col == col_index else 0
                    self._safe_addnstr(stdscr, screen_offset, x, piece, len(piece), attr)
                    x += len(cell)
                    if len(piece) < len(cell):
                        break

            range_hint = f"cols {start_col + 1}-{end_col}/{len(column_labels)}"
            summary_line = f"{summary}  {range_hint}".strip() if summary else range_hint
            self._safe_addnstr(stdscr, height - 2, 0, summary_line, screen_width)
            self._safe_addnstr(
                stdscr,
                height - 1,
                0,
                "Arrows select/scroll  Enter details  Esc back",
                screen_width,
                curses.A_DIM,
            )
            stdscr.refresh()

            stdscr.timeout(-1)
            try:
                key = stdscr.get_wch()
            finally:
                stdscr.timeout(POLL_MS)
            if key == "\x1b":
                return None
            if key in ("\n", "\r") or key == curses.KEY_ENTER:
                return row_index, col_index
            if key == curses.KEY_UP:
                row_index = max(0, row_index - 1)
            elif key == curses.KEY_DOWN:
                row_index = min(len(row_labels) - 1, row_index + 1)
            elif key == curses.KEY_LEFT:
                col_index = max(0, col_index - 1)
            elif key == curses.KEY_RIGHT:
                col_index = min(len(column_labels) - 1, col_index + 1)

    def draw(self, stdscr: curses.window, *, commit: bool = True) -> None:
        """Render the layout into curses' virtual screen."""
        lines = list(self.render())
        monitor_lines = list(self.monitor_render()) if self.monitor_visible else []
        height, width = stdscr.getmaxyx()

        footer_rows = 2
        usable = max(4, height - footer_rows)
        show_monitor = bool(monitor_lines)
        if show_monitor:
            monitor_h = max(4, int(usable * self.monitor_fraction))
            main_h = max(3, usable - monitor_h)
            if main_h + monitor_h > usable:
                monitor_h = max(3, usable - main_h)
        else:
            monitor_h = 0
            main_h = usable

        main_content_h = max(1, main_h - 2)
        self.scroll = min(max(0, self.scroll), max(0, len(lines) - main_content_h))

        stdscr.erase()
        self._safe_addnstr(stdscr, 0, 0, self.title, width - 1, curses.A_BOLD)
        self._safe_addnstr(stdscr, 1, 0, self.status(), width - 1)
        for row, line in enumerate(lines[self.scroll : self.scroll + main_content_h], start=2):
            if row >= main_h:
                break
            self._safe_addnstr(stdscr, row, 0, str(line), width - 1)

        if show_monitor:
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
        stdscr.timeout(POLL_MS)

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
