from lmts.tests.catalog import default_test_matrix, default_test_type_registry


def test_registry_and_matrix_are_separate() -> None:
    registry = default_test_type_registry()
    matrix = default_test_matrix(registry)

    type_refs = {definition.ref for definition in registry.definitions()}
    matrix_refs = {test.type_ref for test in matrix.tests()}

    assert "research.free_prompt_consistency@1.0.0" in type_refs
    assert "research.free_prompt_consistency@1.0.0" not in matrix_refs
    assert len(type_refs) == 3
    assert len(matrix.tests()) == 2


def test_parameterized_type_creates_configured_instance() -> None:
    registry = default_test_type_registry()
    definition = registry.get("research.free_prompt_consistency@1.0.0")

    configured = definition.configure(
        "repeatability-1",
        {"prompt": "same prompt", "repeats": 7},
    )

    assert configured.type_ref == "research.free_prompt_consistency@1.0.0"
    assert configured.ref == "research.free_prompt_consistency@1.0.0#repeatability-1"
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
