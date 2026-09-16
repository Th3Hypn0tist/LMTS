from __future__ import annotations

from lmts.tests.base import test_snapshot as snapshot_for_test
from lmts.tests.catalog import default_test_type_registry
from lmts.tests.taxonomy import taxonomy_for


def test_every_builtin_test_has_explicit_taxonomy() -> None:
    registry = default_test_type_registry()
    definitions = registry.definitions()
    assert definitions
    for definition in definitions:
        taxonomy = taxonomy_for(definition.id)
        assert definition.category == taxonomy.category
        assert definition.subcategory == taxonomy.subcategory
        assert definition.taxonomy_ref == taxonomy.ref
        assert definition.category != 'uncategorized'


def test_taxonomy_does_not_change_canonical_test_identity() -> None:
    definition = default_test_type_registry().get('bot.no_phantom_action@1.0.0')
    configured = definition.configure('bot-no-phantom-action')
    assert configured.id == 'bot.no_phantom_action'
    assert configured.ref == 'bot.no_phantom_action@1.0.0#bot-no-phantom-action'
    assert configured.taxonomy_ref == 'bot/grounding'


def test_configured_test_snapshot_contains_taxonomy_metadata() -> None:
    definition = default_test_type_registry().get('bot.missing_information@1.0.0')
    configured = definition.configure('bot-missing-information')
    snapshot = snapshot_for_test(configured)
    assert snapshot['identity']['type_id'] == 'bot.missing_information'
    assert snapshot['taxonomy'] == {
        'category': 'bot',
        'subcategory': 'uncertainty',
        'ref': 'bot/uncertainty',
    }


def test_bot_behavior_categories_are_split_by_semantics() -> None:
    registry = default_test_type_registry()
    expected = {
        'bot.exact_instruction@1.0.0': 'bot/instruction_following',
        'bot.negative_constraint@1.0.0': 'bot/constraints',
        'bot.missing_information@1.0.0': 'bot/uncertainty',
        'bot.contradiction_detection@1.0.0': 'bot/conflict_detection',
        'bot.no_phantom_action@1.0.0': 'bot/grounding',
        'bot.evidence_before_claim@1.0.0': 'bot/grounding',
        'bot.scope_control@1.0.0': 'bot/scope_control',
        'bot.goal_retention@1.0.0': 'bot/goal_management',
        'bot.format_compliance@1.0.0': 'bot/output_contract',
        'bot.multi_constraint@1.0.0': 'bot/constraints',
        'bot.ambiguity_handling@1.0.0': 'bot/uncertainty',
        'bot.stop_condition@1.0.0': 'bot/completion_control',
        'bot.closed_world_unknown@1.0.0': 'bot/grounding',
        'bot.self_correction@1.0.0': 'bot/recovery',
    }
    assert {ref: registry.get(ref).taxonomy_ref for ref in expected} == expected
