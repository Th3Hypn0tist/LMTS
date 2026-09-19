from lmts.tests.catalog import (
    default_test_matrix,
    default_test_type_registry,
    test_matrix_for_level as matrix_for_level,
)


def test_registry_and_matrix_are_separate() -> None:
    registry = default_test_type_registry()
    matrix = default_test_matrix(registry)

    definitions = {definition.ref: definition for definition in registry.definitions()}
    matrix_refs = {test.type_ref for test in matrix.tests()}

    assert "research.free_prompt_consistency@1.0.0" in definitions
    assert "research.free_prompt_consistency@1.0.0" not in matrix_refs
    assert "context.carwash_goal_persistence@1.0.0" in definitions
    assert "context.carwash_goal_persistence@1.0.0" in matrix_refs
    assert "reasoning.carwash_transport@1.0.0" in definitions
    assert "reasoning.carwash_transport@1.0.0" in matrix_refs

    carwash_context = definitions["context.carwash_goal_persistence@1.0.0"]
    assert carwash_context.minimum_level == "moderate"
    assert carwash_context.mandatory is True

    carwash_reasoning = definitions["reasoning.carwash_transport@1.0.0"]
    assert carwash_reasoning.minimum_level == "quick"
    assert carwash_reasoning.mandatory is True

    configured_by_type = {test.type_ref: test for test in matrix.tests()}
    configured_carwash = configured_by_type["context.carwash_goal_persistence@1.0.0"]
    assert configured_carwash.minimum_level == "moderate"
    assert configured_carwash.mandatory is True


def test_suite_levels_are_cumulative() -> None:
    registry = default_test_type_registry()
    quick = {test.type_ref for test in matrix_for_level("quick", registry).tests()}
    moderate = {test.type_ref for test in matrix_for_level("moderate", registry).tests()}
    deep = {test.type_ref for test in matrix_for_level("deep", registry).tests()}

    assert quick < moderate
    assert moderate <= deep
    assert "reasoning.carwash_transport@1.0.0" in quick
    assert "context.carwash_goal_persistence@1.0.0" not in quick
    assert "context.carwash_goal_persistence@1.0.0" in moderate


def test_parameterized_type_creates_configured_instance() -> None:
    registry = default_test_type_registry()
    definition = registry.get("research.free_prompt_consistency@1.0.0")

    configured = definition.configure(
        "repeatability-1",
        {"prompt": "same prompt", "repeats": 7},
    )

    assert configured.type_ref == "research.free_prompt_consistency@1.0.0"
    assert configured.ref == "research.free_prompt_consistency@1.0.0#repeatability-1"
    assert configured.minimum_level == "moderate"
    assert configured.mandatory is False
    assert configured.params == {"prompt": "same prompt", "repeats": 7}
    assert configured.module.prompt == "same prompt"
    assert configured.module.repeats == 7


def test_matrix_rejects_duplicate_instance_ids() -> None:
    registry = default_test_type_registry()
    definition = registry.get("research.free_prompt_consistency@1.0.0")
    matrix = default_test_matrix(registry)
    first = definition.configure("same-id", {"prompt": "a", "repeats": 2})
    second = definition.configure("same-id", {"prompt": "b", "repeats": 3})

    matrix.add(first)
    try:
        matrix.add(second)
    except ValueError as exc:
        assert "same-id" in str(exc)
    else:
        raise AssertionError("duplicate configured test instance was accepted")

def test_test_definition_carries_canonical_telemetry_declarations() -> None:
    registry = default_test_type_registry()
    definition = registry.get("core.text_generation@1.0.0")
    configured = definition.configure("text-generation")

    assert "input_tokens" in definition.telemetry_types
    assert "gpu_power_w" in definition.telemetry_types
    assert configured.telemetry_types == definition.telemetry_types
    assert configured.description == definition.description
