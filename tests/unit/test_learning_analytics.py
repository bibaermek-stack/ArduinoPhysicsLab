"""domain/services/learning_analytics.py тесттері (Phase 8: Advanced
Analytics & Learning Progress) — weak/strong classification, teacher
alerts (инъекцияланған ``now``), channel trend pooling, completion-rate
honesty, multi-student grouping.
"""

from datetime import datetime, timedelta, timezone

import pytest

from domain.entities.classroom import Classroom
from domain.entities.experiment_feedback_result import ExperimentFeedbackResult, TeacherAssessment
from domain.entities.learning_analytics import AlertKind, TopicPerformanceLevel
from domain.entities.measurement import Measurement
from domain.entities.student import Student
from domain.entities.student_experiment_progress import ProgressStatus
from domain.entities.user_role import UserRole
from domain.services.learning_analytics import (
    DEFAULT_AWAITING_REVIEW_DAYS,
    DEFAULT_OVERDUE_DAYS,
    DEFAULT_STRONG_THRESHOLD,
    DEFAULT_WEAK_THRESHOLD,
    compute_channel_trend,
    compute_students_learning_progress,
    compute_teacher_alerts,
    resolve_channel_value,
)
from infrastructure.storage.sqlite_classroom_repository import SqliteClassroomRepository
from infrastructure.storage.sqlite_feedback_repository import SqliteFeedbackRepository
from infrastructure.storage.sqlite_session_repository import SqliteSessionRepository
from infrastructure.storage.sqlite_student_progress_repository import SqliteStudentProgressRepository
from infrastructure.storage.sqlite_student_repository import SqliteStudentRepository
from modules.electricity.module import ElectricityModule
from modules.module_registry import ModuleRegistry

_NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


# ---- resolve_channel_value() / compute_channel_trend() — pure functions ----


def _measurement(values: dict[str, float]) -> Measurement:
    return Measurement(timestamp=_NOW, values=values, experiment_id="ohms-law")


def test_resolve_channel_value_returns_raw_value_when_present() -> None:
    measurement = _measurement({"voltage": 5.0})
    assert resolve_channel_value(measurement, "voltage") == 5.0


def test_resolve_channel_value_computes_power_fresh_when_missing() -> None:
    """§7a — "power" кейбір тәжірибелерде derived_values-те жоқ,
    CalculationEngine-мен БІРДЕЙ формула (P = U x I) осында ЖАҢАДАН
    есептеледі."""
    measurement = _measurement({"voltage": 4.0, "current": 0.5})
    assert resolve_channel_value(measurement, "power") == pytest.approx(2.0)


def test_resolve_channel_value_never_mutates_stored_measurement() -> None:
    measurement = _measurement({"voltage": 4.0, "current": 0.5})
    resolve_channel_value(measurement, "power")
    assert "power" not in measurement.derived_values


def test_resolve_channel_value_returns_none_when_insufficient_data() -> None:
    measurement = _measurement({"voltage": 4.0})  # § current жоқ
    assert resolve_channel_value(measurement, "power") is None


def test_compute_channel_trend_pools_values_across_sessions(tmp_path) -> None:
    session_repo = SqliteSessionRepository(str(tmp_path / "trend.db"))
    session_repo.append_measurements(
        "sess-1", "ohms-law", (_measurement({"voltage": 2.0}), _measurement({"voltage": 4.0})), started_at=_NOW
    )
    session_repo.append_measurements(
        "sess-2", "ohms-law", (_measurement({"voltage": 6.0}),), started_at=_NOW
    )

    stats = compute_channel_trend(session_repo, ("sess-1", "sess-2"), "voltage")

    assert stats.n == 3
    assert stats.minimum == 2.0
    assert stats.maximum == 6.0
    assert stats.average == pytest.approx(4.0)


def test_compute_channel_trend_empty_session_ids_never_fabricates_zero(tmp_path) -> None:
    session_repo = SqliteSessionRepository(str(tmp_path / "trend.db"))

    stats = compute_channel_trend(session_repo, (), "voltage")

    assert stats.n == 0
    assert stats.average is None


# ---- compute_students_learning_progress() -----------------------------------


@pytest.fixture()
def repos(tmp_path):
    db_path = str(tmp_path / "analytics.db")
    classroom_repo = SqliteClassroomRepository(db_path)
    student_repo = SqliteStudentRepository(db_path)
    session_repo = SqliteSessionRepository(db_path)
    feedback_repo = SqliteFeedbackRepository(db_path)
    progress_repo = SqliteStudentProgressRepository(
        db_path, session_repository=session_repo, feedback_repository=feedback_repo,
        classroom_repository=classroom_repo, student_repository=student_repo,
    )
    classroom_repo.create(Classroom(id="ca", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER)
    module_registry = ModuleRegistry()
    module_registry.register(ElectricityModule())
    return {
        "classroom": classroom_repo, "student": student_repo, "session": session_repo,
        "feedback": feedback_repo, "progress": progress_repo, "modules": module_registry,
    }


def _add_student(repos, student_id: str, classroom_id: str = "ca") -> None:
    repos["student"].create(
        Student(id=student_id, classroom_id=classroom_id, first_name="Оқушы", last_name=student_id, created_at=_NOW, updated_at=_NOW),
        UserRole.TEACHER,
    )


def _review_with_score(repos, session_id: str, student_id: str, experiment_id: str, score: int) -> None:
    repos["progress"].link_session(session_id, student_id, "ca", experiment_id)
    repos["session"].append_measurements(session_id, experiment_id, (_measurement({"voltage": 1.0}),), started_at=_NOW)
    repos["feedback"].save_submission(
        ExperimentFeedbackResult(experiment_id=experiment_id, session_id=session_id, is_draft=False, submitted_at=_NOW)
    )
    repos["feedback"].save_teacher_assessment(
        session_id, experiment_id, TeacherAssessment(score=score, comment=""), UserRole.TEACHER
    )


def test_empty_progress_list_returns_empty_tuple(repos) -> None:
    result = compute_students_learning_progress(
        (), student_repository=repos["student"], classroom_repository=repos["classroom"],
        module_registry=repos["modules"],
    )
    assert result == ()


def test_reviewed_high_score_is_classified_strong(repos) -> None:
    _add_student(repos, "s1")
    _review_with_score(repos, "sess-1", "s1", "ohms-law", 9)
    progress_list = repos["progress"].list_all_progress()

    result = compute_students_learning_progress(
        progress_list, student_repository=repos["student"], classroom_repository=repos["classroom"],
        module_registry=repos["modules"],
    )

    assert len(result) == 1
    topic = result[0].topics[0]
    assert topic.average_score == 9.0
    assert topic.level is TopicPerformanceLevel.STRONG


def test_reviewed_low_score_is_classified_weak(repos) -> None:
    _add_student(repos, "s1")
    _review_with_score(repos, "sess-1", "s1", "ohms-law", 3)
    progress_list = repos["progress"].list_all_progress()

    result = compute_students_learning_progress(
        progress_list, student_repository=repos["student"], classroom_repository=repos["classroom"],
        module_registry=repos["modules"],
    )

    assert result[0].topics[0].level is TopicPerformanceLevel.WEAK


def test_reviewed_mid_score_is_neutral_never_weak_or_strong(repos) -> None:
    _add_student(repos, "s1")
    _review_with_score(repos, "sess-1", "s1", "ohms-law", 6)
    progress_list = repos["progress"].list_all_progress()

    result = compute_students_learning_progress(
        progress_list, student_repository=repos["student"], classroom_repository=repos["classroom"],
        module_registry=repos["modules"],
    )

    assert result[0].topics[0].level is TopicPerformanceLevel.NEUTRAL


def test_weak_strong_thresholds_are_exact_named_constants() -> None:
    assert DEFAULT_WEAK_THRESHOLD == 5.0
    assert DEFAULT_STRONG_THRESHOLD == 8.0


def test_unscored_measurement_completed_topic_is_neutral_not_fabricated(repos) -> None:
    """§ "never fabricate weak/strong without a real score signal"."""
    _add_student(repos, "s1")
    repos["progress"].link_session("sess-1", "s1", "ca", "ohms-law")
    repos["session"].append_measurements("sess-1", "ohms-law", (_measurement({"voltage": 1.0}),), started_at=_NOW)
    progress_list = repos["progress"].list_all_progress()

    result = compute_students_learning_progress(
        progress_list, student_repository=repos["student"], classroom_repository=repos["classroom"],
        module_registry=repos["modules"],
    )

    topic = result[0].topics[0]
    assert topic.average_score is None
    assert topic.level is TopicPerformanceLevel.NEUTRAL
    assert topic.completed_count == 1  # § MEASUREMENT_COMPLETED - "completed" болса да, балл жоқ


def test_completion_rate_is_completed_over_attempted_never_enrolled(repos) -> None:
    """§ Architecture Decision #4 — "laboratory completion statistics =
    completed/attempted, ЕШҚАШАН /enrolled"."""
    _add_student(repos, "s1")
    _review_with_score(repos, "sess-1", "s1", "ohms-law", 7)
    repos["progress"].link_session("sess-2", "s1", "ca", "current-voltage")  # § 0 measurement -> IN_PROGRESS
    progress_list = repos["progress"].list_all_progress()

    result = compute_students_learning_progress(
        progress_list, student_repository=repos["student"], classroom_repository=repos["classroom"],
        module_registry=repos["modules"],
    )

    assert len(result[0].topics) == 2
    assert result[0].overall_completion_rate == pytest.approx(0.5)  # § 1-і аяқталды, 1-і жоқ


def test_weakest_and_strongest_topic_identified_across_two_topics(repos) -> None:
    _add_student(repos, "s1")
    _review_with_score(repos, "sess-1", "s1", "ohms-law", 3)
    _review_with_score(repos, "sess-2", "s1", "current-voltage", 9)
    progress_list = repos["progress"].list_all_progress()

    result = compute_students_learning_progress(
        progress_list, student_repository=repos["student"], classroom_repository=repos["classroom"],
        module_registry=repos["modules"],
    )

    assert result[0].weakest_topic.experiment_id == "ohms-law"
    assert result[0].strongest_topic.experiment_id == "current-voltage"
    assert result[0].overall_average_score == pytest.approx(6.0)


def test_deleted_student_is_skipped_gracefully(repos) -> None:
    _add_student(repos, "s1")
    _review_with_score(repos, "sess-1", "s1", "ohms-law", 7)
    progress_list = repos["progress"].list_all_progress()

    # § "student not found at all" сценарийін нақты сынау үшін тікелей
    # шикі progress жазбасын, шынайы жоқ student_id-мен қолданамыз.
    from dataclasses import replace

    fake_progress = tuple(replace(p, student_id="does-not-exist") for p in progress_list)

    result = compute_students_learning_progress(
        fake_progress, student_repository=repos["student"], classroom_repository=repos["classroom"],
        module_registry=repos["modules"],
    )

    assert result == ()  # § ешбір жалған жол ешқашан фабрикацияланбайды


def test_multiple_students_produce_separate_rows(repos) -> None:
    _add_student(repos, "s1")
    _add_student(repos, "s2")
    _review_with_score(repos, "sess-1", "s1", "ohms-law", 7)
    _review_with_score(repos, "sess-2", "s2", "ohms-law", 4)
    progress_list = repos["progress"].list_all_progress()

    result = compute_students_learning_progress(
        progress_list, student_repository=repos["student"], classroom_repository=repos["classroom"],
        module_registry=repos["modules"],
    )

    assert {row.student_id for row in result} == {"s1", "s2"}


# ---- compute_teacher_alerts() ------------------------------------------------


def test_overdue_alert_triggers_past_threshold(repos) -> None:
    _add_student(repos, "s1")
    repos["progress"].link_session("sess-1", "s1", "ca", "ohms-law")
    progress = repos["progress"].get_progress("s1", "ohms-law")
    from dataclasses import replace

    stale_progress = replace(progress, last_activity_at=_NOW - timedelta(days=DEFAULT_OVERDUE_DAYS, seconds=1))

    alerts = compute_teacher_alerts(
        (stale_progress,), student_repository=repos["student"], classroom_repository=repos["classroom"],
        module_registry=repos["modules"], now=_NOW,
    )

    assert len(alerts) == 1
    assert alerts[0].kind is AlertKind.OVERDUE
    assert alerts[0].student_id == "s1"


def test_overdue_alert_does_not_trigger_within_window(repos) -> None:
    _add_student(repos, "s1")
    repos["progress"].link_session("sess-1", "s1", "ca", "ohms-law")
    progress = repos["progress"].get_progress("s1", "ohms-law")
    from dataclasses import replace

    fresh_progress = replace(progress, last_activity_at=_NOW - timedelta(days=DEFAULT_OVERDUE_DAYS) + timedelta(seconds=1))

    alerts = compute_teacher_alerts(
        (fresh_progress,), student_repository=repos["student"], classroom_repository=repos["classroom"],
        module_registry=repos["modules"], now=_NOW,
    )

    assert alerts == ()


def test_overdue_alert_never_fires_for_not_started() -> None:
    """§ "тағайындау ұғымы жоқ" — NOT_STARTED ЕШҚАШАН overdue болмайды."""
    from domain.entities.student_experiment_progress import StudentExperimentProgress

    never_started = StudentExperimentProgress(
        student_id="s1", experiment_id="ohms-law", status=ProgressStatus.NOT_STARTED,
        last_activity_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
    )

    class _FakeStudentRepo:
        def get(self, student_id):
            from domain.entities.student import Student
            return Student(id="s1", classroom_id="ca", first_name="A", last_name="B", created_at=_NOW, updated_at=_NOW)

    class _FakeClassroomRepo:
        def get(self, classroom_id):
            return Classroom(id="ca", name="8А", created_at=_NOW, updated_at=_NOW)

    module_registry = ModuleRegistry()
    module_registry.register(ElectricityModule())

    alerts = compute_teacher_alerts(
        (never_started,), student_repository=_FakeStudentRepo(), classroom_repository=_FakeClassroomRepo(),
        module_registry=module_registry, now=_NOW,
    )

    assert alerts == ()


def test_low_score_alert_triggers_below_threshold(repos) -> None:
    _add_student(repos, "s1")
    _review_with_score(repos, "sess-1", "s1", "ohms-law", 3)
    progress_list = repos["progress"].list_all_progress()

    alerts = compute_teacher_alerts(
        progress_list, student_repository=repos["student"], classroom_repository=repos["classroom"],
        module_registry=repos["modules"], now=_NOW,
    )

    assert any(a.kind is AlertKind.LOW_SCORE for a in alerts)


def test_low_score_alert_does_not_trigger_at_or_above_threshold(repos) -> None:
    _add_student(repos, "s1")
    _review_with_score(repos, "sess-1", "s1", "ohms-law", int(DEFAULT_WEAK_THRESHOLD))
    progress_list = repos["progress"].list_all_progress()

    alerts = compute_teacher_alerts(
        progress_list, student_repository=repos["student"], classroom_repository=repos["classroom"],
        module_registry=repos["modules"], now=_NOW,
    )

    assert not any(a.kind is AlertKind.LOW_SCORE for a in alerts)


def test_awaiting_review_too_long_alert_triggers_past_threshold(repos) -> None:
    _add_student(repos, "s1")
    repos["progress"].link_session("sess-1", "s1", "ca", "ohms-law")
    repos["session"].append_measurements("sess-1", "ohms-law", (_measurement({"voltage": 1.0}),), started_at=_NOW)
    repos["feedback"].save_submission(
        ExperimentFeedbackResult(
            experiment_id="ohms-law", session_id="sess-1", is_draft=False,
            submitted_at=_NOW - timedelta(days=DEFAULT_AWAITING_REVIEW_DAYS, seconds=1),
        )
    )
    progress_list = repos["progress"].list_all_progress()

    alerts = compute_teacher_alerts(
        progress_list, student_repository=repos["student"], classroom_repository=repos["classroom"],
        module_registry=repos["modules"], now=_NOW,
    )

    assert any(a.kind is AlertKind.AWAITING_REVIEW_TOO_LONG for a in alerts)


def test_awaiting_review_alert_does_not_trigger_recently_submitted(repos) -> None:
    _add_student(repos, "s1")
    repos["progress"].link_session("sess-1", "s1", "ca", "ohms-law")
    repos["session"].append_measurements("sess-1", "ohms-law", (_measurement({"voltage": 1.0}),), started_at=_NOW)
    repos["feedback"].save_submission(
        ExperimentFeedbackResult(
            experiment_id="ohms-law", session_id="sess-1", is_draft=False, submitted_at=_NOW,
        )
    )
    progress_list = repos["progress"].list_all_progress()

    alerts = compute_teacher_alerts(
        progress_list, student_repository=repos["student"], classroom_repository=repos["classroom"],
        module_registry=repos["modules"], now=_NOW,
    )

    assert not any(a.kind is AlertKind.AWAITING_REVIEW_TOO_LONG for a in alerts)


def test_custom_thresholds_are_respected(repos) -> None:
    _add_student(repos, "s1")
    _review_with_score(repos, "sess-1", "s1", "ohms-law", 6)
    progress_list = repos["progress"].list_all_progress()

    alerts = compute_teacher_alerts(
        progress_list, student_repository=repos["student"], classroom_repository=repos["classroom"],
        module_registry=repos["modules"], now=_NOW, low_score_threshold=7.0,
    )

    assert any(a.kind is AlertKind.LOW_SCORE for a in alerts)


def test_multiple_alert_kinds_can_coexist_for_different_students(repos) -> None:
    _add_student(repos, "s1")
    _add_student(repos, "s2")
    _review_with_score(repos, "sess-1", "s1", "ohms-law", 2)
    repos["progress"].link_session("sess-2", "s2", "ca", "current-voltage")
    progress = repos["progress"].get_progress("s2", "current-voltage")
    from dataclasses import replace

    stale_progress = replace(progress, last_activity_at=_NOW - timedelta(days=DEFAULT_OVERDUE_DAYS, seconds=1))

    reviewed_list = tuple(
        p for p in repos["progress"].list_all_progress() if p.student_id == "s1"
    )
    alerts = compute_teacher_alerts(
        reviewed_list + (stale_progress,), student_repository=repos["student"], classroom_repository=repos["classroom"],
        module_registry=repos["modules"], now=_NOW,
    )

    kinds = {a.kind for a in alerts}
    assert AlertKind.LOW_SCORE in kinds
    assert AlertKind.OVERDUE in kinds
