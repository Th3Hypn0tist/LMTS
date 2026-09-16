from __future__ import annotations

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
            self.matrix.add(configured)
        except (KeyError, ValueError) as exc:
            self.state.message = f'cannot add test: {exc}'
            return None
        self.sync()
        self.state.selected_test_refs.add(configured.ref)
        self.clear_live_matrix()
        self.state.message = f'added configured test: {configured.ref}'
        return configured

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
