from lmts.core.executor import RuntimeExecutor
from lmts.core.executor_registry import ExecutorRegistry
from lmts.core.models import NormalizedResponse
from lmts.core.subject import EvaluationSubject, SubjectMember


def _response(prompt, sink):
    return NormalizedResponse(text="OK")


def test_executor_registry_keeps_bot_and_composition_distinct() -> None:
    bot = RuntimeExecutor(
        executor_id="bot.writer",
        executor_kind="bot",
        evaluation_subject=EvaluationSubject.for_bot("bot.writer"),
        generate_handler=_response,
    )
    composition = RuntimeExecutor(
        executor_id="composition.writer-reviewer",
        executor_kind="composition",
        evaluation_subject=EvaluationSubject.for_composition(
            "composition.writer-reviewer",
            (
                SubjectMember("bot.writer", role="writer"),
                SubjectMember("bot.reviewer", role="reviewer"),
            ),
        ),
        generate_handler=_response,
    )
    registry = ExecutorRegistry([bot, composition])

    assert registry.get("bot.writer").kind == "bot"
    assert registry.get("composition.writer-reviewer").kind == "composition"
    assert [executor.id for executor in registry.by_kind("bot")] == ["bot.writer"]
