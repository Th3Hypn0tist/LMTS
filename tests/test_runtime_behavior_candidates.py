from __future__ import annotations

import pytest

from lmts.core.models import ModelCapabilities
from lmts.tests.base import TestRequirements, test_snapshot as canonical_test_snapshot
from lmts.tests.catalog import (
    AUTOMATED_SUITE_EXCLUSIONS,
    CANDIDATE_TEST_IDS,
    default_test_type_registry,
    test_matrix_for_level as matrix_for_level,
)
from lmts.tests.requirements import validate_requirements


def test_subject_kind_requirement_rejects_wrong_target_kind() -> None:
    requirements = TestRequirements(text_generation=True, subject_kinds=('bot',))
    capabilities = ModelCapabilities(text=True)

    validate_requirements(requirements, capabilities, subject_kind='bot')
    with pytest.raises(ValueError, match="does not apply to subject kind 'model'"):
        validate_requirements(requirements, capabilities, subject_kind='model')
    with pytest.raises(ValueError, match="does not apply to subject kind 'composition'"):
        validate_requirements(requirements, capabilities, subject_kind='composition')


def test_runtime_candidate_tests_have_explicit_subject_domains() -> None:
    registry = default_test_type_registry()
    expected = {
        'bot_runtime.no_phantom_completion@1.0.0': ('bot_runtime/grounding', ('bot',)),
        'bot_runtime.scope_boundary@1.0.0': ('bot_runtime/scope_control', ('bot',)),
        'composition.constraint_integration@1.0.0': ('composition/constraint_integration', ('composition',)),
        'composition.conflict_resolution@1.0.0': ('composition/conflict_resolution', ('composition',)),
    }

    for ref, (taxonomy_ref, subject_kinds) in expected.items():
        definition = registry.get(ref)
        assert definition.taxonomy_ref == taxonomy_ref
        assert definition.requirements.subject_kinds == subject_kinds


def test_candidate_tests_are_not_automatic_reference_suite_members() -> None:
    assert CANDIDATE_TEST_IDS <= AUTOMATED_SUITE_EXCLUSIONS
    moderate_ids = {test.id for test in matrix_for_level('moderate').tests()}
    deep_ids = {test.id for test in matrix_for_level('deep').tests()}
    assert not (CANDIDATE_TEST_IDS & moderate_ids)
    assert not (CANDIDATE_TEST_IDS & deep_ids)


def test_canonical_snapshot_records_subject_applicability() -> None:
    definition = default_test_type_registry().get('composition.conflict_resolution@1.0.0')
    configured = definition.configure('composition-conflict-resolution')
    snapshot = canonical_test_snapshot(configured)

    assert snapshot['subject_kinds'] == ['composition']
    assert snapshot['taxonomy'] == {
        'category': 'composition',
        'subcategory': 'conflict_resolution',
        'ref': 'composition/conflict_resolution',
    }
