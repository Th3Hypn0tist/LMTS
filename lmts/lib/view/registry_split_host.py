from __future__ import annotations

import curses
from collections.abc import Callable, Iterable, Sequence

from .shortcut_registry import ShortcutRegistry
from .split_host import POLL_MS, SplitCursesViewHost


class RegistrySplitCursesViewHost(SplitCursesViewHost):
    """Split host whose application shortcuts come from a ShortcutRegistry."""

    def __init__(
        self,
        title: str,
        render: Callable[[], Sequence[str]],
        status: Callable[[], str],
        monitor_render: Callable[[], Sequence[str]],
        *,
        shortcuts: ShortcutRegistry,
        scopes: Callable[[], Iterable[str]],
        status_segments: Callable[[], Sequence[tuple[str, bool]]] | None = None,
        monitor_title: str = "Response monitor",
        monitor_fraction: float = 1 / 3,
    ) -> None:
        super().__init__(
            title,
            render,
            status,
            monitor_render,
            monitor_title=monitor_title,
            monitor_fraction=monitor_fraction,
            footer="",
            quit_sequence="qqq",
        )
        self.shortcuts = shortcuts
        self.shortcut_scopes = scopes
        self.status_segments = status_segments
        self.action_handlers: dict[str, Callable[[curses.window], None]] = {}
        self._sequence: tuple[str, ...] = ()
        self._stop_requested = False

    @staticmethod
    def key_token(key: object) -> str | None:
        if key == curses.KEY_UP:
            return "up"
        if key == curses.KEY_DOWN:
            return "down"
        if key == curses.KEY_LEFT:
            return "left"
        if key == curses.KEY_RIGHT:
            return "right"
        if key == curses.KEY_PPAGE:
            return "pgup"
        if key == curses.KEY_NPAGE:
            return "pgdn"
        if key == curses.KEY_ENTER or key in ("\n", "\r"):
            return "enter"
        if key == "\x1b":
            return "esc"
        if key == " ":
            return "space"
        if isinstance(key, str) and len(key) == 1:
            return key.casefold()
        return None

    def bind(self, action: str, handler: Callable[[curses.window], None]) -> None:
        self.action_handlers[action] = handler

    def _scopes(self) -> tuple[str, ...]:
        return tuple(self.shortcut_scopes())

    @staticmethod
    def _sequence_label(sequence: tuple[str, ...]) -> str:
        labels = {
            "esc": "Esc",
            "up": "Up",
            "down": "Down",
            "left": "Left",
            "right": "Right",
            "pgup": "PgUp",
            "pgdn": "PgDn",
            "enter": "Enter",
            "space": "Space",
        }
        return " ".join(labels.get(token, token) for token in sequence)

    def _footer(self) -> str:
        definitions = [
            item
            for item in self.shortcuts.definitions(self._scopes())
            if item.topic != "Tabs"
        ]
        if not definitions:
            return "Actions: -"
        return "Actions: " + " | ".join(
            f"{item.sequence_label}. {item.label}" for item in definitions
        )

    def _sequence_hint(self) -> str:
        if not self._sequence:
            return ""
        return f"keys: {self._sequence_label(self._sequence)} ..."

    def _dispatch(self, stdscr: curses.window, action: str) -> None:
        if action == "scroll.up":
            self.scroll = max(0, self.scroll - 1)
            return
        if action == "scroll.down":
            self.scroll += 1
            return
        if action == "app.quit":
            self._stop_requested = True
            return
        handler = self.action_handlers.get(action)
        if handler is not None:
            handler(stdscr)

    def _draw_status_segments(self, stdscr: curses.window) -> None:
        if self.status_segments is None:
            return
        height, width = stdscr.getmaxyx()
        if height < 2 or width < 2:
            return
        try:
            stdscr.move(1, 0)
            stdscr.clrtoeol()
        except curses.error:
            return
        x = 0
        for text, selected in self.status_segments():
            if x >= width - 1:
                break
            remaining = width - 1 - x
            piece = str(text)[:remaining]
            attr = curses.A_REVERSE if selected else curses.A_DIM
            self._safe_addnstr(stdscr, 1, x, piece, len(piece), attr)
            x += len(piece)

    def draw(self, stdscr: curses.window, *, commit: bool = True) -> None:
        self.footer = self._footer()
        original_message = self.message
        if not original_message and self._sequence:
            self.message = self._sequence_hint()
        try:
            if self.status_segments is None:
                super().draw(stdscr, commit=commit)
                return
            super().draw(stdscr, commit=False)
            self._draw_status_segments(stdscr)
            stdscr.noutrefresh()
            if commit:
                curses.doupdate()
        finally:
            self.message = original_message

    def run(self, stdscr: curses.window) -> None:
        curses.curs_set(0)
        stdscr.keypad(True)
        stdscr.timeout(POLL_MS)
        while not self._stop_requested:
            self.draw(stdscr)
            try:
                key = stdscr.get_wch()
            except curses.error:
                continue
            token = self.key_token(key)
            if token is None:
                self._sequence = ()
                continue
            match = self.shortcuts.match(self._sequence, token, self._scopes())
            if match.kind == "prefix":
                self._sequence = match.buffer
                continue
            self._sequence = ()
            if match.kind == "exact" and match.shortcut is not None:
                self._dispatch(stdscr, match.shortcut.action)
