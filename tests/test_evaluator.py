from pathlib import Path

from lmts.core.evaluation_store import EvaluationStore
from lmts.core.evaluator import SubjectEvaluator
from lmts.core.executor import RuntimeExecutor
from lmts.core.models import ModelCapabilities, NormalizedResponse
from lmts.core.registry import ProviderRegistry
from lmts.core.runner import TestRunner
from lmts.core.store import RunStore
from lmts.core.subject import EvaluationSubject
from lmts.tests.modules.bot_core import BotCoreTextTest
from lmts.tools.profile import PROFILE_SCHEMA_VERSION
from lmts.tools.reference_benchmark import REFERENCE_BENCHMARK_SCHEMA_VERSION


class FakeTelemetry:
    def start(self):
        pass

    def stop(self):
        return {"samples": [], "summary": {"sample_count": 0}}


def _system_context():
    return {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "fingerprint": "system-fingerprint",
        "profile": {},
        "reference_benchmarks": {
            "schema_version": REFERENCE_BENCHMARK_SCHEMA_VERSION,
            "cpu": None,
            "memory": None,
            "gpu": None,
            "npu": None,
        },
    }


def test_subject_evaluator_persists_bot_scorecard(tmp_path: Path) -> None:
    subject = EvaluationSubject.for_bot("bot.demo", configuration={"version": 1})
    answers = {"first": "ONE", "second": "WRONG"}

    def generate(prompt, sink):
        return NormalizedResponse(text=answers[prompt])

    executor = RuntimeExecutor(
        executor_id="bot.demo",
        executor_kind="bot",
        evaluation_subject=subject,
        generate_handler=generate,
        executor_capabilities=ModelCapabilities(text=True),
    )
    tests = [
        BotCoreTextTest("bot.first", "first", "ONE", "first"),
        BotCoreTextTest("bot.second", "second", "TWO", "second"),
    ]
    runner = TestRunner(
        ProviderRegistry([]),
        RunStore(tmp_path / "results"),
        system_context_loader=_system_context,
        telemetry_factory=FakeTelemetry,
    )
    evaluator = SubjectEvaluator(runner, EvaluationStore(tmp_path / "results"))

    outcome = evaluator.evaluate(executor, tests, tmp_path / "workspaces")

    assert outcome.record.subject["kind"] == "bot"
    assert outcome.record.scorecard["overall_percent"] == 50.0
    assert outcome.record.scorecard["coverage"] == 1.0
    assert len(outcome.record.run_ids) == 2
    assert outcome.record_path.exists()
    assert "evaluations" in outcome.record_path.parts
