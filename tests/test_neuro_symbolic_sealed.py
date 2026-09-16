from __future__ import annotations

from pathlib import Path

from lmts.core.control import RunControl
from lmts.core.executor import RuntimeExecutor
from lmts.core.models import ModelCapabilities, NormalizedResponse
from lmts.core.subject import EvaluationSubject
from lmts.lib.workspace import Workspace
from lmts.tests.base import TestContext
from lmts.tests.neuro_symbolic import (
    NeuroSymbolicSealedTest,
    SealedChallenge,
    SealedVerdict,
)
from lmts.tests.taxonomy import taxonomy_for


class _Source:
    def __init__(self) -> None:
        self.issued = 0

    def issue(self) -> SealedChallenge:
        self.issued += 1
        return SealedChallenge(
            challenge_id='opaque-001',
            prompt='Solve the hidden structured reasoning task and reply with the required answer.',
            public_metadata={'family': 'candidate'},
        )


class _Scorer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def score(self, challenge_id: str, answer: str) -> SealedVerdict:
        self.calls.append((challenge_id, answer))
        return SealedVerdict(True, 87.5, {'oracle': 'external'})


def test_neuro_symbolic_taxonomy_is_separate_domain() -> None:
    assert taxonomy_for('neuro_symbolic.sealed_reasoning').ref == 'neuro_symbolic/sealed_reasoning'


def test_sealed_test_exposes_no_expected_answer_or_oracle_state() -> None:
    fields = set(SealedChallenge.__dataclass_fields__)
    assert fields == {'challenge_id', 'prompt', 'public_metadata'}
    assert 'expected' not in fields
    assert 'answer' not in fields
    assert 'oracle' not in fields


def test_sealed_test_only_passes_opaque_id_and_subject_answer_to_scorer(tmp_path: Path) -> None:
    source = _Source()
    scorer = _Scorer()
    test = NeuroSymbolicSealedTest(source=source, scorer=scorer)

    def generate(prompt: str, sink) -> NormalizedResponse:
        assert 'ground truth' not in prompt.lower()
        return NormalizedResponse(text='SUBJECT-ANSWER')

    executor = RuntimeExecutor(
        executor_id='bot-under-test',
        executor_kind='bot',
        evaluation_subject=EvaluationSubject.for_bot('bot-under-test'),
        generate_handler=generate,
        executor_capabilities=ModelCapabilities(text=True),
    )
    context = TestContext(
        executor=executor,
        workspace=Workspace(tmp_path),
        control=RunControl(),
    )

    result = test.run(context)

    assert source.issued == 1
    assert scorer.calls == [('opaque-001', 'SUBJECT-ANSWER')]
    assert result.passed is True
    assert result.score is not None
    assert result.score.dimensions[0].score == 87.5
    assert result.artifacts['challenge_id'] == 'opaque-001'
    assert 'expected_answer' not in result.artifacts
    assert 'oracle_state' not in result.artifacts
