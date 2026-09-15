from __future__ import annotations

import curses
from collections.abc import Callable

from lmts.lib.view.registry_split_host import RegistrySplitCursesViewHost
from lmts.lib.view.split_host import POLL_MS


class LMTSInteractiveHost(RegistrySplitCursesViewHost):
    """LMTS host with a main-thread idle callback for background-run completion UI."""

    def __init__(self, *args, on_idle: Callable[[curses.window], None] | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.on_idle = on_idle

    def run(self, stdscr: curses.window) -> None:
        curses.curs_set(0)
        stdscr.keypad(True)
        stdscr.timeout(POLL_MS)
        while not self._stop_requested:
            if self.on_idle is not None:
                self.on_idle(stdscr)
            self.draw(stdscr)
            try:
                key = stdscr.get_wch()
            except curses.error:
                continue
            token = self.key_token(key)
            if token is None:
                self._sequence = ()
                continue
            if token == 'ctrl+l':
                self._footer_mode = 'layout' if self._footer_mode == 'actions' else 'actions'
                self._sequence = ()
                continue
            if self._footer_mode == 'layout':
                if len(token) == 1 and token in '0123456789':
                    self._toggle_layout_slot(int(token))
                    self._footer_mode = 'actions'
                self._sequence = ()
                continue
            match = self.shortcuts.match(self._sequence, token, self._scopes())
            if match.kind == 'prefix':
                self._sequence = match.buffer
                continue
            self._sequence = ()
            if match.kind == 'exact' and match.shortcut is not None:
                self._dispatch(stdscr, match.shortcut.action)
