from __future__ import annotations

from pathlib import Path

from lmts.core.control import RunControl
from lmts.core.executor import RuntimeExecutor
from lmts.core.models import ModelCapabilities, NormalizedResponse, NormalizedTiming
from lmts.core.subject import EvaluationSubject
from lmts.lib.workspace import Workspace
from lmts.tests.base import TestContext
from lmts.tests.catalog import AUTOMATED_SUITE_EXCLUSIONS, CANDIDATE_TEST_IDS, default_test_type_registry
from lmts.tests.neuro_symbolic import (
    NEURO_SYMBOLIC_BUILDERS,
    NEURO_SYMBOLIC_TEST_SPECS,
    complexity_levels,
    neuro_symbolic_test,
)
from lmts.tests.taxonomy import taxonomy_for


def test_neuro_symbolic_candidates_are_separate_black_box_domain() -> None:
    expected = {
        'neuro_symbolic.rule_chaining': 'neuro_symbolic/deduction',
        'neuro_symbolic.graph_reachability': 'neuro_symbolic/graph_reasoning',
        'neuro_symbolic.state_transitions': 'neuro_symbolic/state_tracking',
        'neuro_symbolic.constraint_ordering': 'neuro_symbolic/constraint_solving',
    }
    assert {spec['id'] for spec in NEURO_SYMBOLIC_TEST_SPECS} == set(expected)
    for test_id, taxonomy_ref in expected.items():
        assert taxonomy_for(test_id).ref == taxonomy_ref
        assert test_id in CANDIDATE_TEST_IDS
        assert test_id in AUTOMATED_SUITE_EXCLUSIONS


def test_complexity_levels_scale_geometrically_and_end_exactly_at_requested_limit() -> None:
    assert complexity_levels(2) == (2,)
    assert complexity_levels(16) == (2, 4, 8, 16)
    assert complexity_levels(20) == (2, 4, 8, 16, 20)


def test_case_builders_are_deterministic_and_have_machine_checkable_answers() -> None:
    for family, builder in NEURO_SYMBOLIC_BUILDERS.items():
        first = builder(8, 1)
        second = builder(8, 1)
        assert first == second
        assert first.family == family
        assert first.complexity == 8
        assert first.expected.strip()
        assert first.prompt.strip()


def test_registry_exposes_scaling_parameters_but_keeps_candidates_out_of_reference_suites() -> None:
    registry = default_test_type_registry()
    definition = registry.get('neuro_symbolic.rule_chaining@0.1.0-candidate')
    assert definition.taxonomy_ref == 'neuro_symbolic/deduction'
    configured = definition.configure(
        'ns-rule-chain',
        {'max_complexity': 32, 'cases_per_level': 3},
    )
    assert configured.params == {'max_complexity': 32, 'cases_per_level': 3}
    assert configured.module.max_complexity == 32
    assert configured.module.cases_per_level == 3


def test_scaling_test_reports_accuracy_complexity_ceiling_and_latency_growth(tmp_path: Path) -> None:
    expected_by_prompt = {}
    builder = NEURO_SYMBOLIC_BUILDERS['rule_chaining']
    for complexity in complexity_levels(8):
        for variant in range(2):
            case = builder(complexity, variant)
            expected_by_prompt[case.prompt] = case.expected

    calls = 0

    def generate(prompt: str, sink) -> NormalizedResponse:
        nonlocal calls
        calls += 1
        answer = expected_by_prompt[prompt]
        if 'P008' in prompt and calls % 2 == 0:
            answer = 'NO' if answer == 'YES' else 'YES'
        return NormalizedResponse(
            text=answer,
            timing=NormalizedTiming(total_ms=float(calls * 10), ttft_ms=float(calls)),
        )

    executor = RuntimeExecutor(
        executor_id='black-box-neuro-symbolic-system',
        executor_kind='bot',
        evaluation_subject=EvaluationSubject.for_bot('black-box-neuro-symbolic-system'),
        generate_handler=generate,
        executor_capabilities=ModelCapabilities(text=True),
    )
    context = TestContext(
        executor=executor,
        workspace=Workspace(tmp_path),
        control=RunControl(),
    )
    test = neuro_symbolic_test(
        'neuro_symbolic.rule_chaining',
        'rule_chaining',
        max_complexity=8,
        cases_per_level=2,
    )

    result = test.run(context)

    assert result.passed is False
    assert result.score is not None
    dimensions = {dimension.id: dimension for dimension in result.score.dimensions}
    assert dimensions['neuro_symbolic_accuracy'].score < 100.0
    assert dimensions['neuro_symbolic_complexity_ceiling'].score < 100.0
    assert result.metrics['max_contiguous_fully_solved_complexity'] == 4
    assert result.metrics['first_failure_complexity'] == 8
    assert isinstance(result.metrics['latency_growth_ratio'], float)
    assert len(result.artifacts['cases']) == 6
    assert all('expected' in case and 'actual' in case for case in result.artifacts['cases'])
