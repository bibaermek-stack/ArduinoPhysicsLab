"""experiment_feedback_result (Phase 39A) — жауап/нәтиже domain модель
тесттері: ``TeacherAssessment``/``ExperimentFeedbackResult`` валидация
шектері.
"""

from datetime import datetime, timezone

from domain.entities.experiment_feedback_result import (
    ExperimentFeedbackResult,
    MultipleChoiceAnswer,
    OpenResponseAnswer,
    ReflectionAnswer,
    TeacherAssessment,
)


def test_answer_dataclasses_hold_plain_values() -> None:
    mc = MultipleChoiceAnswer(question_id="q1", selected_option_index=2)
    assert mc.question_id == "q1"
    assert mc.selected_option_index == 2

    open_answer = OpenResponseAnswer(question_id="o1", response_text="my analysis")
    assert open_answer.response_text == "my analysis"

    reflection_answer = ReflectionAnswer(question_id="r1", response_text="my reflection")
    assert reflection_answer.response_text == "my reflection"


# ---- TeacherAssessment -------------------------------------------------------


def test_teacher_assessment_valid_score() -> None:
    assert TeacherAssessment(score=7).validate() == []


def test_teacher_assessment_boundary_scores_valid() -> None:
    assert TeacherAssessment(score=0).validate() == []
    assert TeacherAssessment(score=10).validate() == []


def test_teacher_assessment_negative_score_invalid() -> None:
    assert TeacherAssessment(score=-1).validate() != []


def test_teacher_assessment_above_max_score_invalid() -> None:
    assert TeacherAssessment(score=11).validate() != []


def test_teacher_assessment_defaults() -> None:
    assessment = TeacherAssessment(score=5)
    assert assessment.comment == ""
    assert assessment.reviewed is True


# ---- ExperimentFeedbackResult ------------------------------------------------


def test_valid_feedback_result() -> None:
    result = ExperimentFeedbackResult(experiment_id="ohms-law", session_id="s1")
    assert result.validate() == []


def test_feedback_result_requires_experiment_id() -> None:
    result = ExperimentFeedbackResult(experiment_id="", session_id="s1")
    assert any("experiment_id" in e for e in result.validate())


def test_feedback_result_requires_session_id() -> None:
    result = ExperimentFeedbackResult(experiment_id="ohms-law", session_id="")
    assert any("session_id" in e for e in result.validate())


def test_feedback_result_level1_score_out_of_range_invalid() -> None:
    result = ExperimentFeedbackResult(
        experiment_id="ohms-law", session_id="s1", level1_score=6, level1_total=5
    )
    assert any("level1_score" in e for e in result.validate())


def test_feedback_result_percentage_out_of_range_invalid() -> None:
    result = ExperimentFeedbackResult(
        experiment_id="ohms-law", session_id="s1", level1_percentage=150.0
    )
    assert any("level1_percentage" in e for e in result.validate())


def test_feedback_result_propagates_teacher_assessment_errors() -> None:
    result = ExperimentFeedbackResult(
        experiment_id="ohms-law", session_id="s1", teacher_assessment=TeacherAssessment(score=99)
    )
    assert result.validate() != []


def test_feedback_result_defaults_are_draft_with_no_teacher_assessment() -> None:
    result = ExperimentFeedbackResult(experiment_id="ohms-law", session_id="s1")
    assert result.is_draft is True
    assert result.teacher_assessment is None
    assert result.submitted_at is None
    assert result.self_assessment is None


def test_feedback_result_can_hold_full_answer_set() -> None:
    result = ExperimentFeedbackResult(
        experiment_id="ohms-law",
        session_id="s1",
        level1_answers=(MultipleChoiceAnswer("l1-1", 0),),
        level1_score=1,
        level1_total=1,
        level1_percentage=100.0,
        level2_answers=(OpenResponseAnswer("l2-1", "analysis"),),
        level3_answers=(ReflectionAnswer("l3-1", "reflection"),),
        self_assessment=4,
        is_draft=False,
        submitted_at=datetime.now(timezone.utc),
        teacher_assessment=TeacherAssessment(score=8, comment="Good"),
    )
    assert result.validate() == []
    assert result.is_draft is False
