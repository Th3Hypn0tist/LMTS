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

    save_custom_suites([suite], path)

    assert load_custom_suites(path) == (suite,)
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
