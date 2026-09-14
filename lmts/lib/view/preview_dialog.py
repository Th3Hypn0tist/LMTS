from __future__ import annotations

import curses
from collections.abc import Callable, Sequence


PreviewProvider = Callable[[int], Sequence[str]]


def choose_with_preview(
    stdscr: curses.window,
    title: str,
    options: Sequence[str],
    preview: PreviewProvider,
    *,
    selected: int = 0,
) -> int | None:
    """Choose one option while rendering a scrollable preview for the selection."""
    if not options:
        return None

    index = min(max(0, selected), len(options) - 1)
    preview_scroll = 0

    def safe_addnstr(win: curses.window, y: int, x: int, text: str, width: int, attr: int = 0) -> None:
        try:
            win.addnstr(y, x, text, max(0, width), attr)
        except curses.error:
            pass

    while True:
        height, width = stdscr.getmaxyx()
        win_h = max(12, min(height - 2, 30))
        win_w = max(48, min(width - 2, 120))
        option_h = min(len(options), max(3, min(9, win_h // 3)))
        preview_h = max(1, win_h - option_h - 5)
        option_offset = min(max(0, index - option_h + 1), max(0, len(options) - option_h))

        preview_lines = [str(line) for line in preview(index)]
        max_preview_scroll = max(0, len(preview_lines) - preview_h)
        preview_scroll = min(max(0, preview_scroll), max_preview_scroll)

        win = curses.newwin(
            win_h,
            win_w,
            max(0, (height - win_h) // 2),
            max(0, (width - win_w) // 2),
        )
        win.keypad(True)
        win.erase()
        win.box()
        safe_addnstr(win, 0, 2, f" {title} ", win_w - 4, curses.A_BOLD)

        for row, option_index in enumerate(
            range(option_offset, min(len(options), option_offset + option_h)),
            start=1,
        ):
            attr = curses.A_REVERSE if option_index == index else curses.A_NORMAL
            safe_addnstr(win, row, 2, str(options[option_index]), win_w - 4, attr)

        separator_y = option_h + 1
        safe_addnstr(win, separator_y, 1, "─" * max(1, win_w - 2), win_w - 2, curses.A_DIM)

        for row, line in enumerate(
            preview_lines[preview_scroll : preview_scroll + preview_h],
            start=separator_y + 1,
        ):
            safe_addnstr(win, row, 2, line, win_w - 4)

        footer = "Up/Down select  PgUp/PgDn preview  Enter choose  Esc cancel"
        safe_addnstr(win, win_h - 2, 2, footer, win_w - 4, curses.A_DIM)
        win.refresh()

        key = win.get_wch()
        if key == curses.KEY_UP:
            new_index = max(0, index - 1)
            if new_index != index:
                index = new_index
                preview_scroll = 0
        elif key == curses.KEY_DOWN:
            new_index = min(len(options) - 1, index + 1)
            if new_index != index:
                index = new_index
                preview_scroll = 0
        elif key == curses.KEY_PPAGE:
            preview_scroll = max(0, preview_scroll - preview_h)
        elif key == curses.KEY_NPAGE:
            preview_scroll = min(max_preview_scroll, preview_scroll + preview_h)
        elif key in ("\n", "\r") or key == curses.KEY_ENTER:
            return index
        elif key == "\x1b":
            return None
