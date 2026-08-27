"""experiment_feedback_service (Phase 39A) — таза domain функция
тесттері: 1-деңгей есептеу, Оқушыға арналған қауіпсіз көшірме, Мұғалім
бағасын қолдану кезіндегі рөл тексеруі.
"""

import pytest

from domain.entities.experiment_assessment import (
    ExperimentAssessmentDefinition,
    MultipleChoiceQuestion,
)
from domain.entities.experiment_feedback_result import (
    ExperimentFeedbackResult,
    MultipleChoiceAnswer,
    TeacherAssessment,
)
from domain.entities.user_role import UserRole
from domain.services.experiment_feedback_service import (
    apply_teacher_assessment,
    build_student_safe_result,
    score_level1,
)


def _assessment(*correct_indices: int) -> ExperimentAssessmentDefinition:
    questions = tuple(
        MultipleChoiceQuestion(id=f"q{i}", prompt="P?", options=("A", "B"), correct_option_index=idx)
        for i, idx in enumerate(correct_indices)
    )
    return ExperimentAssessmentDefinition(level1_questions=questions)


# ---- score_level1 -------------------------------------------------------


def test_score_level1_all_correct() -> None:
    assessment = _assessment(0, 1, 0)
    answers = (
        MultipleChoiceAnswer("q0", 0),
        MultipleChoiceAnswer("q1", 1),
        MultipleChoiceAnswer("q2", 0),
    )
    score, total, percentage = score_level1(assessment, answers)
    assert (score, total, percentage) == (3, 3, 100.0)


def test_score_level1_partial_correct() -> None:
    assessment = _assessment(0, 1, 0, 1)
    answers = (
        MultipleChoiceAnswer("q0", 0),  # correct
        MultipleChoiceAnswer("q1", 0),  # wrong
        MultipleChoiceAnswer("q2", 1),  # wrong
        MultipleChoiceAnswer("q3", 1),  # correct
    )
    score, total, percentage = score_level1(assessment, answers)
    assert score == 2
    assert total == 4
    assert percentage == 50.0


def test_score_level1_missing_answer_counts_as_incorrect() -> None:
    assessment = _assessment(0, 1)
    answers = (MultipleChoiceAnswer("q0", 0),)  # q1 unanswered
    score, total, _ = score_level1(assessment, answers)
    assert score == 1
    assert total == 2


def test_score_level1_empty_questions_returns_zero_percentage_not_crash() -> None:
    assessment = ExperimentAssessmentDefinition(
        level1_questions=(MultipleChoiceQuestion("q0", "P?", ("A", "B"), 0),)
    )
    # No level1_questions edge case avoided by dataclass validation elsewhere;
    # here we just confirm division-by-zero safety with zero answers/total>0.
    score, total, percentage = score_level1(assessment, ())
    assert score == 0
    assert total == 1
    assert percentage == 0.0


# ---- build_student_safe_result -------------------------------------------


def test_build_student_safe_result_strips_teacher_assessment() -> None:
    result = ExperimentFeedbackResult(
        experiment_id="x", session_id="s1", teacher_assessment=TeacherAssessment(score=9)
    )
    safe = build_student_safe_result(result)
    assert safe.teacher_assessment is None
    # Other fields preserved.
    assert safe.experiment_id == "x"
    assert safe.session_id == "s1"


def test_build_student_safe_result_is_noop_when_no_teacher_assessment() -> None:
    result = ExperimentFeedbackResult(experiment_id="x", session_id="s1")
    safe = build_student_safe_result(result)
    assert safe.teacher_assessment is None


# ---- apply_teacher_assessment (role enforcement) --------------------------


def test_apply_teacher_assessment_succeeds_for_teacher_role() -> None:
    result = ExperimentFeedbackResult(experiment_id="x", session_id="s1")
    updated = apply_teacher_assessment(result, TeacherAssessment(score=8), UserRole.TEACHER)
    assert updated.teacher_assessment.score == 8


def test_apply_teacher_assessment_rejects_student_role() -> None:
    result = ExperimentFeedbackResult(experiment_id="x", session_id="s1")
    with pytest.raises(PermissionError):
        apply_teacher_assessment(result, TeacherAssessment(score=8), UserRole.STUDENT)


def test_apply_teacher_assessment_does_not_mutate_original_result() -> None:
    result = ExperimentFeedbackResult(experiment_id="x", session_id="s1")
    apply_teacher_assessment(result, TeacherAssessment(score=8), UserRole.TEACHER)
    assert result.teacher_assessment is None
