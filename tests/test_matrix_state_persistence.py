from __future__ import annotations

from lmts.tests.catalog import default_test_matrix, default_test_type_registry
from lmts.view.matrix_state import MatrixViewState
from lmts.view.projector import LMTSViewState


def test_restore_configuration_preserves_empty_test_selection() -> None:
    registry = default_test_type_registry()
    matrix = default_test_matrix(registry)
    state = LMTSViewState()
    view = MatrixViewState(state, registry, matrix)

    configured = list(matrix.tests())
    view.restore_configuration(
        configured,
        suite_level='moderate',
        suite_repeats=1,
        selected_test_refs=set(),
    )

    assert state.tests
    assert state.selected_test_refs == set()
