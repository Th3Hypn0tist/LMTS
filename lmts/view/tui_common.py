from __future__ import annotations

import curses

from lmts.tests.types import TestTypeDefinition

from .controller import LMTSViewController


def next_instance_id(controller: LMTSViewController, definition: TestTypeDefinition) -> str:
    base = definition.id.rsplit('.', 1)[-1].replace('_', '-')
    used = {getattr(test, 'instance_id', '') for test in controller.state.tests}
    index = 1
    while f'{base}-{index}' in used:
        index += 1
    return f'{base}-{index}'


def short_test_label(ref: str) -> str:
    return (ref.split('#', 1)[-1] if '#' in ref else ref.rsplit('.', 1)[-1])[:18]


def single_line(host, stdscr, title: str, *, initial: str = '', allow_empty: bool = False) -> str | None:
    while True:
        value = host.input_multiline(stdscr, title, initial=initial)
        if value is None:
            return None
        value = value.strip()
        if '\n' not in value and '\r' not in value and (value or allow_empty):
            return value
        host.message = f"{title}: enter one {'line' if allow_empty else 'non-empty line'}"


def secret_line(stdscr: curses.window, title: str, *, maximum: int = 1024) -> str | None:
    value: list[str] = []
    try:
        while True:
            height, width = stdscr.getmaxyx()
            win_h = max(5, min(height - 2, 7))
            win_w = max(30, min(width - 2, 80))
            body_w = max(1, win_w - 4)
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
            masked = '*' * min(len(value), body_w)
            win.addnstr(2, 2, masked, body_w)
            win.addnstr(win_h - 2, 2, 'Enter accept  Esc cancel', body_w, curses.A_DIM)
            try:
                curses.curs_set(1)
                win.move(2, 2 + min(len(masked), max(0, body_w - 1)))
            except curses.error:
                pass
            win.refresh()
            key = win.get_wch()
            if key == '\x1b':
                return None
            if key in ('\n', '\r') or key == curses.KEY_ENTER:
                if value:
                    return ''.join(value)
                continue
            if key in (curses.KEY_BACKSPACE, '\b', '\x7f'):
                if value:
                    value.pop()
                continue
            if isinstance(key, str) and key.isprintable() and len(value) < maximum:
                value.append(key)
    finally:
        try:
            curses.curs_set(0)
        except curses.error:
            pass
