from __future__ import annotations

import curses
from collections.abc import Callable, Sequence
from pathlib import Path

from lmts.lib.view.events import UIEvent, UIEventBus
from lmts.lib.view.modals import ModalManager
from lmts.lib.view.path_dialog import choose_directory as choose_directory_dialog
from lmts.lib.view.preview_dialog import PreviewProvider, choose_with_preview as choose_with_preview_dialog
from lmts.lib.view.registry_split_host import RegistrySplitCursesViewHost
from lmts.lib.view.split_host import POLL_MS


class LMTSInteractiveHost(RegistrySplitCursesViewHost):
    """LMTS host with centralized events, modal ownership and idle callbacks."""

    MODAL_OWNER = 'lmts.host'

    def __init__(
        self,
        *args,
        events: UIEventBus | None = None,
        modals: ModalManager | None = None,
        on_idle: Callable[[curses.window], None] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.events = events or UIEventBus()
        self.modals = modals or ModalManager(self.events)
        if self.modals.events is not None and self.modals.events is not self.events:
            raise ValueError('LMTS host and modal manager must share one UI event bus')
        self.on_idle = on_idle
        self.events.subscribe('ui.message', self._on_message)

    def _on_message(self, event: UIEvent) -> None:
        if not isinstance(event.payload, str):
            raise TypeError('ui.message payload must be a string')
        self.message = event.payload

    def _modal(self, kind: str, callback):
        return self.modals.run(self.MODAL_OWNER, kind, callback)

    def choose(self, stdscr, title, options, selected=0):
        parent = super()
        return self._modal('choose', lambda: parent.choose(stdscr, title, options, selected))

    def choose_many(self, stdscr, title, options, selected=None, *, include_all=True, all_label='All'):
        parent = super()
        return self._modal(
            'choose_many',
            lambda: parent.choose_many(
                stdscr,
                title,
                options,
                selected,
                include_all=include_all,
                all_label=all_label,
            ),
        )

    def input_integer(self, stdscr, title, *, default=1, minimum=1, maximum=999):
        parent = super()
        return self._modal(
            'input_integer',
            lambda: parent.input_integer(
                stdscr,
                title,
                default=default,
                minimum=minimum,
                maximum=maximum,
            ),
        )

    def input_multiline(self, stdscr, title, *, initial=''):
        parent = super()
        return self._modal(
            'input_multiline',
            lambda: parent.input_multiline(stdscr, title, initial=initial),
        )

    def text_viewer(self, stdscr, title: str, lines: Sequence[str]) -> None:
        parent = super()
        self._modal('text_viewer', lambda: parent.text_viewer(stdscr, title, lines))

    def matrix_browser(
        self,
        stdscr,
        title: str,
        row_labels: Sequence[str],
        column_labels: Sequence[str],
        values: Sequence[Sequence[str]],
        *,
        summary: str = '',
    ):
        parent = super()
        return self._modal(
            'matrix_browser',
            lambda: parent.matrix_browser(
                stdscr,
                title,
                row_labels,
                column_labels,
                values,
                summary=summary,
            ),
        )

    def progress_dialog(
        self,
        stdscr,
        title: str,
        render_lines,
        is_done,
        *,
        poll_ms: int = 200,
        cancel=None,
    ) -> None:
        parent = super()
        self._modal(
            'progress_dialog',
            lambda: parent.progress_dialog(
                stdscr,
                title,
                render_lines,
                is_done,
                poll_ms=poll_ms,
                cancel=cancel,
            ),
        )

    def choose_with_preview(
        self,
        stdscr,
        title: str,
        options: Sequence[str],
        preview: PreviewProvider,
        *,
        selected: int = 0,
    ) -> int | None:
        return self._modal(
            'choose_with_preview',
            lambda: choose_with_preview_dialog(
                stdscr,
                title,
                options,
                preview,
                selected=selected,
            ),
        )

    def choose_directory(
        self,
        stdscr,
        title: str,
        *,
        initial: Path | str = Path('.'),
    ) -> Path | None:
        return self._modal(
            'choose_directory',
            lambda: choose_directory_dialog(self, stdscr, title, initial=initial),
        )

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
