from __future__ import annotations

from ..tui_state import TUIState


class TUIActions:
    def __init__(self, state: TUIState, host, stdscr) -> None:
        self.state = state
        self.host = host
        self.stdscr = stdscr

    @property
    def controller(self):
        return self.state.controller

    def set_message(self, value: str = '') -> None:
        self.host.message = value
