from __future__ import annotations

from .base import TUIActions
from ..registries import TAB_REGISTRY


class NavigationActions(TUIActions):
    def open_tab(self, tab_id: str) -> None:
        tab = TAB_REGISTRY.get(tab_id)
        self.state.active_tab = tab_id
        self.host.title = f'AIGM LMTS - {tab.label}'
        self.host.scroll = 0
        self.set_message('')

    def back(self, _stdscr) -> None:
        parent = TAB_REGISTRY.parent(self.state.active_tab)
        if parent is None or parent.id == 'root':
            self.set_message('already at top level')
            return
        if self.state.active_tab == 'cw_bench':
            self.open_tab('benchmark')
            return
        self.open_tab(parent.id)
