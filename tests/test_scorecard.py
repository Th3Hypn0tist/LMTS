from lmts.core.scoring import build_subject_scorecard
from lmts.core.subject import EvaluationSubject, SubjectMember


def _run(subject, test_ref, percent, dimension_id):
    return {
        "test_ref": test_ref,
        "status": "completed",
        "evaluation_subject": subject.to_dict(),
        "score": {
            "percent": percent,
            "dimensions": [
                {
                    "id": dimension_id,
                    "normalized": percent / 100.0,
                    "weight": 1.0,
                }
            ],
        },
    }


def test_subject_scorecard_aggregates_transparently() -> None:
    bot = EvaluationSubject.for_bot("bot.writer")
    scorecard = build_subject_scorecard(
        [
            _run(bot, "bot.goal_retention@1.0.0", 100.0, "goal_retention"),
            _run(bot, "bot.scope_control@1.0.0", 60.0, "scope_control"),
        ]
    )

    assert scorecard.subject["kind"] == "bot"
    assert scorecard.overall_percent == 80.0
    assert scorecard.coverage == 1.0
    assert scorecard.tests["bot.goal_retention@1.0.0"] == 100.0
    assert scorecard.dimensions["scope_control"] == 60.0


def test_scorecards_keep_composition_separate_from_standalone_bot() -> None:
    bot = EvaluationSubject.for_bot("bot.writer")
    composition = EvaluationSubject.for_composition(
        "composition.writer-reviewer",
        (
            SubjectMember("bot.writer", role="writer"),
            SubjectMember("bot.reviewer", role="reviewer"),
        ),
    )

    standalone = build_subject_scorecard([_run(bot, "bot.goal_retention@1.0.0", 80.0, "goal_retention")])
    combined = build_subject_scorecard([_run(composition, "bot.goal_retention@1.0.0", 95.0, "goal_retention")])

    assert standalone.subject["fingerprint"] != combined.subject["fingerprint"]
    assert standalone.overall_percent == 80.0
    assert combined.overall_percent == 95.0
