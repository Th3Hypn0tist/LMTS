from __future__ import annotations

from lmts.core.custom_suites import CustomSuite, CustomSuiteTest
from lmts.tests.base import test_ref
from lmts.tests.catalog import test_matrix_for_level
from lmts.tests.types import TestParameter

from ..tui_common import next_instance_id, single_line
from .base import TUIActions


class BenchmarkActions(TUIActions):
    def __init__(self, state, host, stdscr, navigation) -> None:
        super().__init__(state, host, stdscr)
        self.navigation = navigation

    def before_run_choice(self, choice: int) -> bool:
        return True

    def _custom_suite_scope(self) -> str:
        scope = self.state.ui_state_scope
        if not isinstance(scope, str) or not scope.strip():
            raise RuntimeError('custom suite persistence requires an active UI state scope')
        return scope

    def select_suite(self, level: str, tab_id: str = 'benchmark') -> None:
        if not self.controller.set_suite_level(level):
            self.set_message(self.controller.state.message)
            return
        message = self.controller.state.message
        self.navigation.open_tab(tab_id)
        self.persist_ui_state()
        self.set_message(message)

    def set_suite_repeats(self, _stdscr) -> None:
        if self.controller.state.running:
            self.set_message('test matrix is running')
            return
        value = self.host.input_integer(
            self.stdscr,
            'Whole-suite repeats',
            default=self.controller.state.suite_repeats,
            minimum=1,
            maximum=100,
        )
        if value is None:
            return
        self.controller.state.suite_repeats = value
        self.persist_ui_state()
        self.set_message(f'suite repeats: {value}')

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
            self.persist_ui_state()
            self.set_message(f'selected {len(chosen)} target(s)')

    @staticmethod
    def _taxonomy_label(test) -> str:
        return f'{getattr(test, "category", "uncategorized")}/{getattr(test, "subcategory", "general")}'

    def select_tests(self, _stdscr) -> None:
        if self.controller.state.running:
            self.set_message('test matrix is running')
            return
        options = [
            f"[{self._taxonomy_label(test)}] [{str(getattr(test, 'minimum_level')).upper()}] {test_ref(test)}"
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
            self.persist_ui_state()
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
            [f'[{d.taxonomy_ref}] [{d.minimum_level.upper()}] {d.ref}  {d.title}' for d in definitions],
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
        if configured is not None:
            self.persist_ui_state()
        self.set_message(f'added: {configured.ref}' if configured is not None else self.controller.state.message)

    def remove_test(self, _stdscr) -> None:
        tests = list(self.controller.state.tests)
        chosen = self.host.choose(
            self.stdscr,
            'Remove configured test',
            [f'[{self._taxonomy_label(test)}] {test_ref(test)}' for test in tests],
        )
        if chosen is not None:
            if self.controller.remove_test(getattr(tests[chosen], 'instance_id', '')):
                self.persist_ui_state()
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
        tests = list(matrix.tests())
        current = 'CURRENT' if self.controller.state.suite_level == level else ''
        lines = [f'{level.upper()}  {len(tests)} automatic test(s)  {current}'.rstrip(), '']
        last_taxonomy = None
        for test in tests:
            taxonomy = self._taxonomy_label(test)
            if taxonomy != last_taxonomy:
                if last_taxonomy is not None:
                    lines.append('')
                lines.append(f'{taxonomy.upper()}')
                last_taxonomy = taxonomy
            lines.append(f'  {test_ref(test)}')
        return tuple(lines)

    def custom_suites_dialog(self, _stdscr) -> None:
        if self.controller.state.running:
            self.set_message('test matrix is running')
            return
        options = ['Save current selection', 'Load custom suite', 'Delete custom suite']
        chosen = self.host.choose(self.stdscr, 'Custom suites', options, 0)
        if chosen is None:
            return
        if chosen == 0:
            self.save_custom_suite(self.stdscr)
        elif chosen == 1:
            self.load_custom_suite(self.stdscr)
        else:
            self.delete_custom_suite(self.stdscr)

    def save_custom_suite(self, _stdscr) -> None:
        selected = [
            test for test in self.controller.state.tests
            if test_ref(test) in self.controller.state.selected_test_refs
        ]
        if not selected:
            self.set_message('select at least one configured test before saving a custom suite')
            return
        name = single_line(self.host, self.stdscr, 'Custom suite name')
        if name is None:
            return
        name = name.strip()
        if not name:
            self.set_message('custom suite name must not be empty')
            return
        suite = CustomSuite(
            name=name,
            repeats=self.controller.state.suite_repeats,
            tests=tuple(
                CustomSuiteTest(
                    type_ref=test.type_ref,
                    instance_id=test.instance_id,
                    params=dict(test.params),
                )
                for test in selected
            ),
        )
        suites = list(self.state.settings_service.load_custom_suites(self._custom_suite_scope()))
        existing = next(
            (index for index, item in enumerate(suites) if item.name.casefold() == name.casefold()),
            None,
        )
        if existing is not None:
            confirm = self.host.choose(
                self.stdscr,
                f'Overwrite custom suite {suites[existing].name}?',
                ['No', 'Overwrite'],
                0,
            )
            if confirm != 1:
                return
            suites[existing] = suite
        else:
            suites.append(suite)
        self.state.settings_service.save_custom_suites(self._custom_suite_scope(), suites)
        self.controller.state.suite_level = 'custom'
        self.persist_ui_state()
        self.set_message(f'custom suite saved: {name}')

    def load_custom_suite(self, _stdscr) -> None:
        suites = list(self.state.settings_service.load_custom_suites(self._custom_suite_scope()))
        if not suites:
            self.set_message('no custom suites saved')
            return
        chosen = self.host.choose(
            self.stdscr,
            'Load custom suite',
            [f'{suite.name}  ({len(suite.tests)} tests x {suite.repeats})' for suite in suites],
            0,
        )
        if chosen is None:
            return
        suite = suites[chosen]
        configured = []
        try:
            for item in suite.tests:
                configured.append(
                    self.controller.test_types.get(item.type_ref).configure(
                        item.instance_id,
                        item.params,
                    )
                )
        except (KeyError, ValueError) as exc:
            self.set_message(f'cannot load custom suite: {exc}')
            return
        if self.controller.replace_with_custom_suite(configured, repeats=suite.repeats):
            self.persist_ui_state()
            self.set_message(f'custom suite loaded: {suite.name}')
        else:
            self.set_message(self.controller.state.message)

    def delete_custom_suite(self, _stdscr) -> None:
        suites = list(self.state.settings_service.load_custom_suites(self._custom_suite_scope()))
        if not suites:
            self.set_message('no custom suites saved')
            return
        chosen = self.host.choose(
            self.stdscr,
            'Delete custom suite',
            [suite.name for suite in suites],
            0,
        )
        if chosen is None:
            return
        suite = suites[chosen]
        confirm = self.host.choose(
            self.stdscr,
            f'Delete custom suite {suite.name}?',
            ['No', 'Delete'],
            0,
        )
        if confirm != 1:
            return
        del suites[chosen]
        self.state.settings_service.save_custom_suites(self._custom_suite_scope(), suites)
        self.set_message(f'custom suite deleted: {suite.name}')

    def tests_dialog(self, _stdscr) -> None:
        if self.controller.state.running:
            self.set_message('test matrix is running')
            return
        options = ['Quick suite', 'Moderate suite', 'Deep suite', 'Suite repeats', 'Custom suites', 'Select tests', 'Add test', 'Remove test', 'CW Bench']
        levels = ('quick', 'moderate', 'deep')

        def preview(index: int) -> tuple[str, ...]:
            if index < 3:
                return self.suite_preview(levels[index])
            if index == 3:
                full_runs = len(self.controller.state.tests) * len(self.controller.state.selected_targets)
                return (
                    f'Whole-suite repeats: {self.controller.state.suite_repeats}',
                    '',
                    'First suite pass stores full benchmark evidence.',
                    'Additional suite passes store PASS/FAIL variance observations only.',
                    f'Current full cells: {full_runs}',
                    f'Total executions: {full_runs * self.controller.state.suite_repeats}',
                )
            if index == 4:
                suites = self.state.settings_service.load_custom_suites(self._custom_suite_scope())
                if not suites:
                    return ('No custom suites saved.',)
                lines = [f'{len(suites)} saved custom suite(s)', '']
                for suite in suites:
                    lines.append(f'  {suite.name}: {len(suite.tests)} tests x {suite.repeats}')
                return tuple(lines)
            if index == 5:
                selected = [
                    test for test in self.controller.state.tests
                    if test_ref(test) in self.controller.state.selected_test_refs
                ]
                lines = [f'{len(selected)} selected / {len(self.controller.state.tests)} configured', '']
                for test in selected:
                    lines.append(f'  [{self._taxonomy_label(test)}] {test_ref(test)}')
                return tuple(lines)
            if index == 6:
                return ('Add one configured test instance from the test type registry.',)
            if index == 7:
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
            self.set_suite_repeats(self.stdscr)
        elif chosen == 4:
            self.custom_suites_dialog(self.stdscr)
        elif chosen == 5:
            self.select_tests(self.stdscr)
        elif chosen == 6:
            self.add_test(self.stdscr)
        elif chosen == 7:
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
                    f'Full runs  : {selected_tests * selected_targets}',
                    f'Executions : {selected_tests * selected_targets * self.controller.state.suite_repeats}',
                )
            if index == 1:
                return (
                    'All configured tests -> selected targets', '',
                    f'Tests   : {all_tests}',
                    f'Targets : {selected_targets}',
                    f'Full runs  : {all_tests * selected_targets}',
                    f'Executions : {all_tests * selected_targets * self.controller.state.suite_repeats}',
                )
            return (
                'All configured tests -> all model targets', '',
                f'Tests   : {all_tests}',
                f'Models  : {model_targets}',
                f'Full runs  : {all_tests * model_targets}',
                f'Executions : {all_tests * model_targets * self.controller.state.suite_repeats}',
                '',
                'Bots and compositions are not included.',
            )

        chosen = self.host.choose_with_preview(self.stdscr, 'Run', options, preview)
        if chosen is None:
            return
        if not self.before_run_choice(chosen):
            return
        if chosen == 0:
            self.controller.run_selected()
        elif chosen == 1:
            self.controller.run_all_tests()
        else:
            self.controller.run_all_tests_to_all_models()
        self.set_message(self.controller.state.message)
