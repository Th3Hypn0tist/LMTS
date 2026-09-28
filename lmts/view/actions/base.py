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
        self.state.events.publish('ui.message', value, source=type(self).__name__)


    def persist_ui_state(self) -> None:
        scope = self.state.ui_state_scope
        if not scope:
            return
        controller_state = self.controller.state
        payload: dict[str, object] = {
            'active_tab': self.state.active_tab,
            'suite_level': controller_state.suite_level,
            'suite_repeats': controller_state.suite_repeats,
            'selected_target_ids': sorted(controller_state.selected_target_ids),
            'selected_test_refs': sorted(controller_state.selected_test_refs),
            'model_explorer_variance_threshold': (
                self.state.model_explorer_page.variance_threshold
                if self.state.model_explorer_page is not None
                else None
            ),
            'configured_tests': [
                {
                    'type_ref': getattr(test, 'type_ref', ''),
                    'instance_id': getattr(test, 'instance_id', ''),
                    'params': dict(getattr(test, 'params', {})),
                }
                for test in controller_state.tests
                if getattr(test, 'type_ref', '') and getattr(test, 'instance_id', '')
            ],
        }
        self.state.settings_service.save_ui_scope(scope, payload)
