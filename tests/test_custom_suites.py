from __future__ import annotations

from lmts.core.custom_suites import (
    CustomSuite,
    CustomSuiteTest,
    load_custom_suites,
    save_custom_suites,
)


def test_custom_suites_round_trip_named_configured_tests(tmp_path) -> None:
    path = tmp_path / 'custom-suites.json'
    suite = CustomSuite(
        name='Qualification',
        repeats=10,
        tests=(
            CustomSuiteTest(
                type_ref='core.text_generation@1.0.0',
                instance_id='text-generation',
                params={},
            ),
            CustomSuiteTest(
                type_ref='research.free_prompt_consistency@1.0.0',
                instance_id='free-prompt',
                params={'prompt': 'test', 'repeats': 3},
            ),
        ),
    )

    save_custom_suites('local', [suite], path)

    assert load_custom_suites('local', path) == (suite,)
    assert path.stat().st_mode & 0o777 == 0o600


def test_custom_suite_rejects_identical_configured_tests() -> None:
    test_a = CustomSuiteTest(
        type_ref='core.text_generation@1.0.0',
        instance_id='one',
        params={},
    )
    test_b = CustomSuiteTest(
        type_ref='core.text_generation@1.0.0',
        instance_id='two',
        params={},
    )

    try:
        CustomSuite(name='Duplicate', repeats=1, tests=(test_a, test_b))
    except ValueError as exc:
        assert 'duplicate configured tests' in str(exc)
    else:
        raise AssertionError('identical configured tests were accepted')


def test_custom_suites_are_scoped_per_identity(tmp_path) -> None:
    path = tmp_path / 'custom-suites.json'
    local = CustomSuite(
        name='Local',
        repeats=1,
        tests=(CustomSuiteTest(
            type_ref='core.text_generation@1.0.0',
            instance_id='local',
            params={'prompt': 'local'},
        ),),
    )
    user = CustomSuite(
        name='User',
        repeats=2,
        tests=(CustomSuiteTest(
            type_ref='core.text_generation@1.0.0',
            instance_id='user',
            params={'prompt': 'user'},
        ),),
    )

    save_custom_suites('local', [local], path)
    save_custom_suites('user:42', [user], path)

    assert load_custom_suites('local', path) == (local,)
    assert load_custom_suites('user:42', path) == (user,)


def test_custom_suite_identity_is_stable_for_nested_parameter_order() -> None:
    first = CustomSuiteTest(
        type_ref='core.text_generation@1.0.0',
        instance_id='one',
        params={'outer': {'b': 2, 'a': 1}},
    )
    second = CustomSuiteTest(
        type_ref='core.text_generation@1.0.0',
        instance_id='two',
        params={'outer': {'a': 1, 'b': 2}},
    )

    try:
        CustomSuite(name='Duplicate nested', repeats=1, tests=(first, second))
    except ValueError as exc:
        assert 'duplicate configured tests' in str(exc)
    else:
        raise AssertionError('nested configured-test duplicate was accepted')
