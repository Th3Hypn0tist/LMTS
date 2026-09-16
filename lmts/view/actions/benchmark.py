from __future__ import annotations

from lmts.tests.base import test_ref
from lmts.tests.catalog import test_matrix_for_level
from lmts.tests.types import TestParameter

from ..tui_common import next_instance_id
from .base import TUIActions


class BenchmarkActions(TUIActions):
    def __init__(self, state, host, stdscr, navigation) -> None:
        super().__init__(state, host, stdscr)
        self.navigation = navigation

    def select_suite(self, level: str, tab_id: str = 'benchmark') -> None:
        if not self.controller.set_suite_level(level):
            self.set_message(self.controller.state.message)
            return
        message = self.controller.state.message
        self.navigation.open_tab(tab_id)
        self.set_message(message)

    def select_targets(self, _stdscr) -> None:
        if self.controller.state.running:
            self.set_message('test matrix is running')
            return
        options = [f'{target.kind.upper():11} {target.id}' for target in self.controller.state.targets]
        selected = {
            i for i, target in enumerate(self.controller.state.targets)
            if target.id in self.controller.state.selected_target_ids
        }
        chosen = self.host.choose_many(
            self.stdscr,
            'Targets',
            options,
            selected,
            include_all=True,
            all_label='All targets',
        )
        if chosen is not None:
            self.controller.select_targets(chosen)
            self.set_message(f'selected {len(chosen)} target(s)')

    def select_tests(self, _stdscr) -> None:
        if self.controller.state.running:
            self.set_message('test matrix is running')
            return
        options = [
            f"[{str(getattr(test, 'minimum_level')).upper()}] {test_ref(test)}"
            for test in self.controller.state.tests
        ]
        selected = {
            i for i, test in enumerate(self.controller.state.tests)
            if test_ref(test) in self.controller.state.selected_test_refs
        }
        chosen = self.host.choose_many(
            self.stdscr,
            'Configured test matrix',
            options,
            selected,
            include_all=True,
            all_label='All configured tests',
        )
        if chosen is not None:
            self.controller.select_tests(chosen)
            self.set_message(f'selected {len(chosen)} configured test(s)')

    def collect_parameter(self, parameter: TestParameter) -> object | None:
        if parameter.kind == 'integer':
            default = parameter.default if isinstance(parameter.default, int) else 1
            return self.host.input_integer(
                self.stdscr,
                parameter.label,
                default=default,
                minimum=parameter.minimum if parameter.minimum is not None else -999999,
                maximum=parameter.maximum if parameter.maximum is not None else 999999,
            )
        if parameter.kind == 'boolean':
            chosen = self.host.choose(self.stdscr, parameter.label, ['false', 'true'], 0)
            return None if chosen is None else chosen == 1
        if parameter.kind == 'choice':
            chosen = self.host.choose(self.stdscr, parameter.label, list(parameter.choices), 0)
            return None if chosen is None else parameter.choices[chosen]
        initial = parameter.default if isinstance(parameter.default, str) else ''
        return self.host.input_multiline(self.stdscr, parameter.label, initial=initial)

    def add_test(self, _stdscr) -> None:
        if self.controller.state.running:
            self.set_message('test matrix is running')
            return
        definitions = self.controller.test_types.definitions()
        chosen = self.host.choose(
            self.stdscr,
            'Test type registry',
            [f'[{d.minimum_level.upper()}] {d.ref}  {d.title}' for d in definitions],
        )
        if chosen is None:
            return
        definition = definitions[chosen]
        params: dict[str, object] = {}
        for parameter in definition.parameters:
            value = self.collect_parameter(parameter)
            if value is None:
                self.set_message('test configuration cancelled')
                return
            params[parameter.name] = value
        configured = self.controller.add_test(
            definition.ref,
            next_instance_id(self.controller, definition),
            params,
        )
        self.set_message(f'added: {configured.ref}' if configured is not None else self.controller.state.message)

    def remove_test(self, _stdscr) -> None:
        tests = list(self.controller.state.tests)
        chosen = self.host.choose(self.stdscr, 'Remove configured test', [test_ref(test) for test in tests])
        if chosen is not None:
            self.controller.remove_test(getattr(tests[chosen], 'instance_id', ''))
            self.set_message(self.controller.state.message)

    def run_deep_suite(self, _stdscr) -> None:
        if not self.controller.set_suite_level('deep'):
            self.set_message(self.controller.state.message)
            return
        self.controller.run_all_tests()
        self.set_message(self.controller.state.message)

    def cancel(self, _stdscr) -> None:
        self.controller.cancel()
        self.set_message(self.controller.state.message)

    def refresh(self, _stdscr) -> None:
        self.controller.refresh()
        self.set_message(self.controller.state.message)

    def suite_preview(self, level: str) -> tuple[str, ...]:
        matrix = test_matrix_for_level(level, self.controller.test_types)
        refs = [test_ref(test) for test in matrix.tests()]
        current = 'CURRENT' if self.controller.state.suite_level == level else ''
        lines = [f'{level.upper()}  {len(refs)} automatic test(s)  {current}'.rstrip(), '']
        lines.extend(f'  {ref}' for ref in refs)
        return tuple(lines)

    def tests_dialog(self, _stdscr) -> None:
        if self.controller.state.running:
            self.set_message('test matrix is running')
            return
        options = ['Quick suite', 'Moderate suite', 'Deep suite', 'Select tests', 'Add test', 'Remove test', 'CW Bench']
        levels = ('quick', 'moderate', 'deep')

        def preview(index: int) -> tuple[str, ...]:
            if index < 3:
                return self.suite_preview(levels[index])
            if index == 3:
                selected = sorted(self.controller.state.selected_test_refs)
                return (
                    f'{len(selected)} selected / {len(self.controller.state.tests)} configured',
                    '',
                    *[f'  {ref}' for ref in selected],
                )
            if index == 4:
                return ('Add one configured test instance from the test type registry.',)
            if index == 5:
                return ('Remove one configured test instance from the current suite.',)
            return (
                'CW Bench',
                '',
                'Generate an implementation from canonical CW, import through CIC,',
                'and compare canonical CW against imported canonical CW.',
            )

        selected = levels.index(self.controller.state.suite_level) if self.controller.state.suite_level in levels else 1
        chosen = self.host.choose_with_preview(
            self.stdscr,
            'Tests',
            options,
            preview,
            selected=selected,
        )
        if chosen is None:
            return
        if chosen < 3:
            self.select_suite(levels[chosen])
        elif chosen == 3:
            self.select_tests(self.stdscr)
        elif chosen == 4:
            self.add_test(self.stdscr)
        elif chosen == 5:
            self.remove_test(self.stdscr)
        else:
            self.navigation.open_tab('cw_bench')

    def run_dialog(self, _stdscr) -> None:
        if self.controller.state.running:
            chosen = self.host.choose(self.stdscr, 'Run', ['Cancel run'])
            if chosen == 0:
                self.cancel(self.stdscr)
            return

        options = ['Run', 'Run all tests', 'Run all tests to all models']

        def preview(index: int) -> tuple[str, ...]:
            selected_tests = len(self.controller.state.selected_tests)
            all_tests = len(self.controller.state.tests)
            selected_targets = len(self.controller.state.selected_targets)
            model_targets = sum(1 for target in self.controller.state.targets if target.kind == 'model')
            if index == 0:
                return (
                    'Selected tests -> selected targets', '',
                    f'Tests   : {selected_tests}',
                    f'Targets : {selected_targets}',
                    f'Runs    : {selected_tests * selected_targets}',
                )
            if index == 1:
                return (
                    'All configured tests -> selected targets', '',
                    f'Tests   : {all_tests}',
                    f'Targets : {selected_targets}',
                    f'Runs    : {all_tests * selected_targets}',
                )
            return (
                'All configured tests -> all model targets', '',
                f'Tests   : {all_tests}',
                f'Models  : {model_targets}',
                f'Runs    : {all_tests * model_targets}',
                '',
                'Bots and compositions are not included.',
            )

        chosen = self.host.choose_with_preview(self.stdscr, 'Run', options, preview)
        if chosen is None:
            return
        if chosen == 0:
            self.controller.run_selected()
        elif chosen == 1:
            self.controller.run_all_tests()
        else:
            self.controller.run_all_tests_to_all_models()
        self.set_message(self.controller.state.message)
