from __future__ import annotations

import curses
from collections.abc import Callable, Iterable, Sequence

from .layout import LayoutPane
from .shortcut_registry import ShortcutDefinition, ShortcutRegistry
from .split_host import POLL_MS, SplitCursesViewHost


class RegistrySplitCursesViewHost(SplitCursesViewHost):
    """Registry-driven curses host with dynamic Actions and Layout footer modes."""

    def __init__(
        self,
        title: str,
        render: Callable[[], Sequence[str]],
        tabs: Callable[[], str],
        monitor_render: Callable[[], Sequence[str]],
        *,
        shortcuts: ShortcutRegistry,
        scopes: Callable[[], Iterable[str]],
        layout_panes: Callable[[], Sequence[LayoutPane]] | None = None,
        monitor_title: str = "Console",
        monitor_fraction: float = 1 / 3,
    ) -> None:
        self.shortcut_scopes = scopes
        self._monitor_source = monitor_render
        self._layout_source = layout_panes
        super().__init__(
            title,
            render,
            lambda: "",
            self._scoped_monitor_lines,
            monitor_title="Console",
            monitor_fraction=monitor_fraction,
            footer="",
            quit_sequence="qqq",
        )
        self.shortcuts = shortcuts
        self.tabs = tabs
        self.action_handlers: dict[str, Callable[[curses.window], None]] = {}
        self._sequence: tuple[str, ...] = ()
        self._stop_requested = False
        self._footer_mode = "actions"
        self._pane_visibility: dict[tuple[str, int], bool] = {}

    def _scope_key(self) -> str:
        scopes = self._scopes()
        return scopes[0] if scopes else "global"

    def _scoped_monitor_lines(self) -> Sequence[str]:
        return self._monitor_source()

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
        if key == "\x0c":
            return "ctrl+l"
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

    def _action_definitions(self) -> tuple[ShortcutDefinition, ...]:
        return tuple(
            item
            for item in self.shortcuts.definitions(self._scopes())
            if item.topic != "Tabs"
        )

    def _layout_definitions(self) -> tuple[LayoutPane, ...]:
        panes = tuple(self._layout_source() if self._layout_source is not None else ())
        slots = [pane.slot for pane in panes]
        if len(slots) != len(set(slots)):
            raise ValueError("layout pane slots must be unique within one page")
        scope = self._scope_key()
        for pane in panes:
            self._pane_visibility.setdefault((scope, pane.slot), pane.default_visible)
        return tuple(sorted(panes, key=lambda pane: pane.slot))

    def _pane_is_enabled(self, pane: LayoutPane) -> bool:
        scope = self._scope_key()
        return self._pane_visibility.get((scope, pane.slot), pane.default_visible)

    def _toggle_layout_slot(self, slot: int) -> None:
        panes = self._layout_definitions()
        scope = self._scope_key()
        if slot == 0:
            if not panes:
                return
            all_enabled = all(self._pane_is_enabled(pane) for pane in panes)
            next_state = not all_enabled
            for pane in panes:
                self._pane_visibility[(scope, pane.slot)] = next_state
            return
        for pane in panes:
            if pane.slot == slot:
                key = (scope, slot)
                self._pane_visibility[key] = not self._pane_visibility.get(key, pane.default_visible)
                return

    def _footer(self) -> str:
        if self._footer_mode == "layout":
            panes = self._layout_definitions()
            return "Layout:" + "".join([" 0 All", *[f" {pane.slot} {pane.label}" for pane in panes]])
        definitions = self._action_definitions()
        if not definitions:
            return "Actions: -"
        return "Actions:" + "".join(
            f" {item.sequence_label} {item.label}" for item in definitions
        )

    def _footer_segments(self) -> tuple[tuple[str, int], ...]:
        if self._footer_mode == "layout":
            panes = self._layout_definitions()
            segments: list[tuple[str, int]] = [("Layout:", curses.A_DIM)]
            all_enabled = bool(panes) and all(self._pane_is_enabled(pane) for pane in panes)
            segments.append((" 0 ", curses.A_REVERSE | curses.A_BOLD))
            segments.append((" ", 0))
            segments.append(("All", 0 if all_enabled else curses.A_DIM))
            for pane in panes:
                segments.append((f" {pane.slot} ", curses.A_REVERSE | curses.A_BOLD))
                segments.append((" ", 0))
                segments.append((pane.label, 0 if self._pane_is_enabled(pane) else curses.A_DIM))
            return tuple(segments)

        definitions = self._action_definitions()
        if not definitions:
            return (("Actions: -", curses.A_DIM),)
        segments = [("Actions:", curses.A_DIM)]
        for item in definitions:
            segments.append((f" {item.sequence_label} ", curses.A_REVERSE | curses.A_BOLD))
            segments.append((" ", 0))
            segments.append((item.label, 0))
        return tuple(segments)

    def _draw_footer(self, stdscr: curses.window) -> None:
        height, width = stdscr.getmaxyx()
        if height < 1 or width < 2:
            return
        y = height - 1
        try:
            stdscr.move(y, 0)
            stdscr.clrtoeol()
        except curses.error:
            return
        x = 0
        for text, attr in self._footer_segments():
            if x >= width - 1:
                break
            remaining = width - 1 - x
            piece = str(text)[:remaining]
            self._safe_addnstr(stdscr, y, x, piece, len(piece), attr)
            x += len(piece)

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

    def _selected_top_level_label(self) -> str:
        scopes = self._scopes()
        if not scopes:
            raise ValueError("tab scope is required")
        current = scopes[0]
        mapping = {
            "profile": "Profile",
            "benchmark": "Benchmark",
            "deep": "Benchmark",
            "cw_bench": "Benchmark",
            "downloader": "Model Downloader",
            "settings": "Settings",
        }
        try:
            return mapping[current]
        except KeyError as exc:
            raise ValueError(f"unknown tab scope: {current}") from exc

    def _tab_segments(self) -> tuple[tuple[str, bool], ...]:
        value = self.tabs()
        if not value.startswith("Tabs: "):
            raise ValueError("tab renderer must return canonical 'Tabs: ...' content")
        selected = self._selected_top_level_label()
        items = value[len("Tabs: "):].split(" | ")
        segments: list[tuple[str, bool]] = [("Tabs: ", False)]
        for index, item in enumerate(items):
            if ". " not in item:
                raise ValueError(f"invalid canonical tab item: {item!r}")
            label = item.split(". ", 1)[1]
            segments.append((item, label == selected))
            if index < len(items) - 1:
                segments.append((" | ", False))
        return tuple(segments)

    def _draw_tabs(self, stdscr: curses.window) -> None:
        height, width = stdscr.getmaxyx()
        if height < 2 or width < 2:
            return
        try:
            stdscr.move(0, 0)
            stdscr.clrtoeol()
        except curses.error:
            return
        x = 0
        for text, selected in self._tab_segments():
            if x >= width - 1:
                break
            remaining = width - 1 - x
            piece = str(text)[:remaining]
            attr = curses.A_REVERSE if selected else curses.A_DIM
            self._safe_addnstr(stdscr, 0, x, piece, len(piece), attr)
            x += len(piece)

    @staticmethod
    def _pane_heights(panes: Sequence[LayoutPane], available: int) -> list[int]:
        count = len(panes)
        if count == 0:
            return []
        if count == 1:
            return [available]
        if count == 2 and panes[0].primary and not panes[1].primary:
            first = max(1, available // 3)
            return [first, max(1, available - first)]
        base, remainder = divmod(available, count)
        return [max(1, base + (1 if index < remainder else 0)) for index in range(count)]

    def _draw_layout(self, stdscr: curses.window) -> None:
        height, width = stdscr.getmaxyx()
        screen_width = max(0, width - 1)
        body_top = 2
        body_bottom = max(body_top, height - 2)
        body_height = max(0, body_bottom - body_top)

        pane_payloads: list[tuple[LayoutPane, list[str]]] = []
        for pane in self._layout_definitions():
            if not self._pane_is_enabled(pane):
                continue
            lines = list(pane.render())
            if pane.auto_hide_empty and not lines:
                continue
            pane_payloads.append((pane, lines))

        stdscr.erase()
        self._draw_tabs(stdscr)
        self._safe_addnstr(stdscr, 1, 0, self.title, screen_width, curses.A_BOLD)

        if pane_payloads and body_height > 0:
            separator_count = max(0, len(pane_payloads) - 1)
            content_height = max(len(pane_payloads), body_height - separator_count)
            pane_heights = self._pane_heights([pane for pane, _ in pane_payloads], content_height)
            y = body_top
            for index, ((pane, lines), pane_height) in enumerate(zip(pane_payloads, pane_heights)):
                if index > 0 and y < body_bottom:
                    self._safe_addnstr(stdscr, y, 0, "─" * max(1, screen_width), screen_width, curses.A_DIM)
                    title = f" {pane.title or pane.label} "
                    self._safe_addnstr(stdscr, y, 2, title, min(len(title), max(0, screen_width - 2)), curses.A_BOLD)
                    y += 1
                elif index == 0 and not pane.primary and pane.title and y < body_bottom:
                    self._safe_addnstr(stdscr, y, 0, pane.title, screen_width, curses.A_BOLD)
                    y += 1
                    pane_height = max(0, pane_height - 1)

                visible_height = min(pane_height, max(0, body_bottom - y))
                if visible_height <= 0:
                    continue
                if pane.primary:
                    self.scroll = min(max(0, self.scroll), max(0, len(lines) - visible_height))
                    visible_lines = lines[self.scroll : self.scroll + visible_height]
                elif pane.follow_tail:
                    visible_lines = lines[-visible_height:]
                else:
                    visible_lines = lines[:visible_height]
                for offset, line in enumerate(visible_lines):
                    self._safe_addnstr(stdscr, y + offset, 0, str(line), screen_width)
                y += visible_height

        quit_hint = ""
        if self._quit:
            remaining = max(0, len(self.quit_sequence) - len(self._quit))
            quit_hint = f"quit: {self._quit}{'_' * remaining}"
        self._safe_addnstr(stdscr, height - 2, 0, self.message or quit_hint, screen_width)
        self._draw_footer(stdscr)

    def draw(self, stdscr: curses.window, *, commit: bool = True) -> None:
        self.footer = self._footer()
        original_message = self.message
        if not original_message and self._sequence:
            self.message = self._sequence_hint()
        try:
            if self._layout_source is not None:
                self._draw_layout(stdscr)
            else:
                super().draw(stdscr, commit=False)
                height, width = stdscr.getmaxyx()
                if height >= 2 and width >= 2:
                    try:
                        stdscr.move(1, 0)
                        stdscr.clrtoeol()
                    except curses.error:
                        pass
                    self._safe_addnstr(stdscr, 1, 0, self.title, width - 1, curses.A_BOLD)
                self._draw_tabs(stdscr)
                self._draw_footer(stdscr)
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
            if token == "ctrl+l":
                self._footer_mode = "layout" if self._footer_mode == "actions" else "actions"
                self._sequence = ()
                continue
            if self._footer_mode == "layout":
                if len(token) == 1 and token in "0123456789":
                    self._toggle_layout_slot(int(token))
                    self._footer_mode = "actions"
                self._sequence = ()
                continue
            match = self.shortcuts.match(self._sequence, token, self._scopes())
            if match.kind == "prefix":
                self._sequence = match.buffer
                continue
            self._sequence = ()
            if match.kind == "exact" and match.shortcut is not None:
                self._dispatch(stdscr, match.shortcut.action)
