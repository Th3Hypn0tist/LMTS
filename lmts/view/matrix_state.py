from __future__ import annotations

from lmts.core.custom_suites import configured_test_identity
from lmts.tests.base import test_ref
from lmts.tests.catalog import test_matrix_for_level
from lmts.tests.types import ConfiguredTest, TestLevel, TestMatrix, TestTypeRegistry

from .projector import LMTSViewState


class MatrixViewState:
    def __init__(self, state: LMTSViewState, test_types: TestTypeRegistry, matrix: TestMatrix) -> None:
        self.state = state
        self.test_types = test_types
        self.matrix = matrix

    def clear_live_matrix(self) -> None:
        self.state.live_target_ids = ()
        self.state.live_target_kinds = {}
        self.state.live_test_refs = ()
        self.state.live_cells = {}

    def sync(self) -> None:
        previous = set(self.state.selected_test_refs)
        self.state.tests = list(self.matrix.tests())
        available = {test_ref(test) for test in self.state.tests}
        self.state.selected_test_refs = previous & available
        if not self.state.selected_test_refs and self.state.tests:
            self.state.selected_test_refs = set(available)

    def set_suite_level(self, level: TestLevel) -> bool:
        if self.state.running:
            self.state.message = 'cannot change suite while test matrix is running'
            return False
        self.matrix = test_matrix_for_level(level, self.test_types)
        self.state.suite_level = level
        self.sync()
        self.state.selected_test_refs = {test_ref(test) for test in self.state.tests}
        self.clear_live_matrix()
        self.state.message = f'suite level: {level.upper()} ({len(self.state.tests)} configured test(s))'
        return True

    def add_test(
        self,
        type_ref: str,
        instance_id: str,
        params: dict[str, object] | None = None,
    ) -> ConfiguredTest | None:
        if self.state.running:
            self.state.message = 'cannot change matrix while test matrix is running'
            return None
        try:
            configured = self.test_types.get(type_ref).configure(instance_id, params)
            for existing in self.matrix.tests():
                if existing.type_ref == configured.type_ref and existing.params == configured.params:
                    raise ValueError(
                        f'identical configured test already exists: {existing.ref}'
                    )
            self.matrix.add(configured)
        except (KeyError, ValueError) as exc:
            self.state.message = f'cannot add test: {exc}'
            return None
        self.sync()
        self.state.selected_test_refs.add(configured.ref)
        self.clear_live_matrix()
        self.state.message = f'added configured test: {configured.ref}'
        return configured

    def restore_configuration(
        self,
        tests: list[ConfiguredTest],
        *,
        suite_level: str,
        suite_repeats: int,
        selected_test_refs: set[str],
    ) -> None:
        if self.state.running:
            raise RuntimeError('cannot restore matrix while test matrix is running')
        if isinstance(suite_repeats, bool) or not isinstance(suite_repeats, int) or not 1 <= suite_repeats <= 100:
            raise ValueError('suite repeats must be an integer between 1 and 100')
        matrix = TestMatrix()
        identities: set[str] = set()
        for test in tests:
            identity = configured_test_identity(test.type_ref, test.params)
            if identity in identities:
                raise ValueError(f'duplicate configured test in persisted UI state: {test.ref}')
            identities.add(identity)
            matrix.add(test)
        self.matrix = matrix
        self.state.suite_level = suite_level
        self.state.suite_repeats = suite_repeats
        self.sync()
        available = {test_ref(test) for test in self.state.tests}
        restored = selected_test_refs & available
        self.state.selected_test_refs = restored if restored else set(available)
        self.clear_live_matrix()

    def replace_with_custom(
        self,
        tests: list[ConfiguredTest],
        *,
        repeats: int = 1,
    ) -> bool:
        if self.state.running:
            self.state.message = 'cannot change matrix while test matrix is running'
            return False
        if not tests:
            self.state.message = 'custom suite must contain at least one configured test'
            return False
        if isinstance(repeats, bool) or not isinstance(repeats, int) or not 1 <= repeats <= 100:
            self.state.message = 'custom suite repeats must be an integer between 1 and 100'
            return False
        matrix = TestMatrix()
        identities: set[str] = set()
        for test in tests:
            identity = configured_test_identity(test.type_ref, test.params)
            if identity in identities:
                self.state.message = f'duplicate configured test in custom suite: {test.ref}'
                return False
            identities.add(identity)
            matrix.add(test)
        self.matrix = matrix
        self.state.suite_level = 'custom'
        self.state.suite_repeats = repeats
        self.sync()
        self.state.selected_test_refs = {test_ref(test) for test in self.state.tests}
        self.clear_live_matrix()
        self.state.message = f'custom suite loaded: {len(self.state.tests)} configured test(s)'
        return True

    def remove_test(self, instance_id: str) -> bool:
        if self.state.running:
            self.state.message = 'cannot change matrix while test matrix is running'
            return False
        try:
            removed = self.matrix.remove(instance_id)
        except KeyError as exc:
            self.state.message = str(exc)
            return False
        self.sync()
        self.clear_live_matrix()
        self.state.message = f'removed configured test: {removed.ref}'
        return True

    def select_targets(self, indices: set[int]) -> None:
        if self.state.running:
            return
        self.state.selected_target_ids = {
            self.state.targets[index].id
            for index in sorted(indices)
            if 0 <= index < len(self.state.targets)
        }
        self.clear_live_matrix()

    def select_target_ids(self, target_ids: set[str]) -> None:
        if self.state.running:
            return
        available = {target.id for target in self.state.targets}
        self.state.selected_target_ids = set(target_ids) & available
        self.clear_live_matrix()

    def select_all_targets(self) -> None:
        if self.state.running:
            return
        self.state.selected_target_ids = {target.id for target in self.state.targets}
        self.clear_live_matrix()

    def select_tests(self, indices: set[int]) -> None:
        if self.state.running:
            return
        self.state.selected_test_refs = {
            test_ref(self.state.tests[index])
            for index in sorted(indices)
            if 0 <= index < len(self.state.tests)
        }
        self.clear_live_matrix()

    def select_test_refs(self, refs: set[str]) -> None:
        if self.state.running:
            return
        available = {test_ref(test) for test in self.state.tests}
        self.state.selected_test_refs = set(refs) & available
        self.clear_live_matrix()

    def select_all_tests(self) -> None:
        if self.state.running:
            return
        self.state.selected_test_refs = {test_ref(test) for test in self.state.tests}
        self.clear_live_matrix()
