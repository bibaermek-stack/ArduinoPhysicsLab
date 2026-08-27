"""StudentExperimentProgress/ProgressStatus/derive_status — Phase 39B
статус-есептеу логикасы (домен деңгейінде, УИ-ден тыс, § "Do not allow
UI code to invent status independently").
"""

from datetime import datetime, timezone

from domain.entities.experiment_feedback_result import ExperimentFeedbackResult, TeacherAssessment
from domain.entities.student_experiment_progress import ProgressStatus, derive_status

_NOW = datetime.now(timezone.utc)


def _make_result(**overrides: object) -> ExperimentFeedbackResult:
    defaults: dict[str, object] = dict(experiment_id="e1", session_id="s1")
    defaults.update(overrides)
    return ExperimentFeedbackResult(**defaults)


def test_no_link_is_not_started() -> None:
    assert derive_status(has_link=False, measurement_count=0, feedback_result=None) is (
        ProgressStatus.NOT_STARTED
    )


def test_link_with_zero_measurements_is_in_progress() -> None:
    assert derive_status(has_link=True, measurement_count=0, feedback_result=None) is (
        ProgressStatus.IN_PROGRESS
    )


def test_measurements_with_no_feedback_record_is_measurement_completed() -> None:
    assert derive_status(has_link=True, measurement_count=5, feedback_result=None) is (
        ProgressStatus.MEASUREMENT_COMPLETED
    )


def test_draft_feedback_is_report_completed() -> None:
    result = _make_result(is_draft=True)
    assert derive_status(has_link=True, measurement_count=5, feedback_result=result) is (
        ProgressStatus.REPORT_COMPLETED
    )


def test_submitted_feedback_without_teacher_assessment_is_feedback_submitted() -> None:
    result = _make_result(is_draft=False, submitted_at=_NOW)
    assert derive_status(has_link=True, measurement_count=5, feedback_result=result) is (
        ProgressStatus.FEEDBACK_SUBMITTED
    )


def test_teacher_assessment_present_is_reviewed() -> None:
    result = _make_result(
        is_draft=False,
        submitted_at=_NOW,
        teacher_assessment=TeacherAssessment(score=8, comment="Жақсы"),
    )
    assert derive_status(has_link=True, measurement_count=5, feedback_result=result) is (
        ProgressStatus.REVIEWED
    )


def test_draft_with_zero_measurements_still_reports_in_progress_precedence() -> None:
    # measurement_count=0 басым тексеріледі — жоба кездейсоқ бос сессияда
    # "аяқталды" деп жалған көрсетілмейді.
    result = _make_result(is_draft=True)
    assert derive_status(has_link=True, measurement_count=0, feedback_result=result) is (
        ProgressStatus.IN_PROGRESS
    )
