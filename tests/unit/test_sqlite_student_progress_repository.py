"""SqliteStudentProgressRepository юнит-тесттері: session-link,
прогресс есептеу (measurement/feedback композициясы арқылы), легаси
(байланыссыз) сессиялар, dashboard сандары."""

from datetime import datetime, timezone

from domain.entities.experiment_feedback_result import ExperimentFeedbackResult, TeacherAssessment
from domain.entities.experiment_session import ExperimentSession
from domain.entities.measurement import Measurement
from domain.entities.student_experiment_progress import ProgressStatus
from domain.entities.user_role import UserRole
from infrastructure.storage.sqlite_classroom_repository import SqliteClassroomRepository
from infrastructure.storage.sqlite_feedback_repository import SqliteFeedbackRepository
from infrastructure.storage.sqlite_session_repository import SqliteSessionRepository
from infrastructure.storage.sqlite_student_progress_repository import SqliteStudentProgressRepository
from infrastructure.storage.sqlite_student_repository import SqliteStudentRepository

_NOW = datetime.now(timezone.utc)


def _make_repository() -> tuple[
    SqliteStudentProgressRepository, SqliteSessionRepository, SqliteFeedbackRepository
]:
    session_repository = SqliteSessionRepository()
    feedback_repository = SqliteFeedbackRepository()
    classroom_repository = SqliteClassroomRepository()
    student_repository = SqliteStudentRepository()
    progress_repository = SqliteStudentProgressRepository(
        session_repository=session_repository,
        feedback_repository=feedback_repository,
        classroom_repository=classroom_repository,
        student_repository=student_repository,
    )
    return progress_repository, session_repository, feedback_repository


def _save_measured_session(session_repository: SqliteSessionRepository, session_id: str) -> None:
    session = ExperimentSession(id=session_id, experiment_id="ohms-law", started_at=_NOW)
    session.add_measurement(
        Measurement(timestamp=_NOW, values={"voltage": 5.0}, experiment_id="ohms-law")
    )
    session_repository.save_session(session)


def test_get_progress_without_link_is_not_started() -> None:
    progress_repository, _sessions, _feedback = _make_repository()

    progress = progress_repository.get_progress("s1", "ohms-law")

    assert progress.status is ProgressStatus.NOT_STARTED
    assert progress.latest_session_id is None


def test_link_session_then_zero_measurements_is_in_progress() -> None:
    progress_repository, _sessions, _feedback = _make_repository()

    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")

    progress = progress_repository.get_progress("s1", "ohms-law")
    assert progress.status is ProgressStatus.IN_PROGRESS
    assert progress.latest_session_id == "sess1"


def test_link_session_with_measurements_is_measurement_completed() -> None:
    progress_repository, session_repository, _feedback = _make_repository()
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")

    progress = progress_repository.get_progress("s1", "ohms-law")

    assert progress.status is ProgressStatus.MEASUREMENT_COMPLETED
    assert progress.measurement_count == 1


def test_progress_reflects_submitted_feedback_and_teacher_score() -> None:
    progress_repository, session_repository, feedback_repository = _make_repository()
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    feedback_repository.save_submission(
        ExperimentFeedbackResult(
            experiment_id="ohms-law", session_id="sess1",
            level1_score=4, level1_total=5, level1_percentage=80.0,
            self_assessment=4, is_draft=False, submitted_at=_NOW,
        )
    )

    progress = progress_repository.get_progress("s1", "ohms-law")

    assert progress.status is ProgressStatus.FEEDBACK_SUBMITTED
    assert progress.level1_score == 4
    assert progress.level1_total == 5
    assert progress.self_assessment == 4
    assert progress.teacher_reviewed is False
    assert progress.teacher_score is None


def test_progress_reflects_teacher_assessment_as_reviewed() -> None:
    progress_repository, session_repository, feedback_repository = _make_repository()
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    feedback_repository.save_submission(
        ExperimentFeedbackResult(
            experiment_id="ohms-law", session_id="sess1", is_draft=False, submitted_at=_NOW,
        )
    )
    feedback_repository.save_teacher_assessment(
        "sess1", "ohms-law", TeacherAssessment(score=9, comment="Жақсы"), UserRole.TEACHER
    )

    progress = progress_repository.get_progress("s1", "ohms-law")

    assert progress.status is ProgressStatus.REVIEWED
    assert progress.teacher_score == 9
    assert progress.teacher_reviewed is True


def test_get_student_for_session_returns_none_for_legacy_session() -> None:
    progress_repository, session_repository, _feedback = _make_repository()
    _save_measured_session(session_repository, "legacy-sess")

    assert progress_repository.get_student_for_session("legacy-sess") is None


def test_get_student_for_session_returns_linked_student() -> None:
    progress_repository, _sessions, _feedback = _make_repository()
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")

    assert progress_repository.get_student_for_session("sess1") == "s1"


def test_list_progress_for_student_covers_all_requested_experiments() -> None:
    progress_repository, session_repository, _feedback = _make_repository()
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")

    results = progress_repository.list_progress_for_student("s1", ("ohms-law", "current-voltage"))

    assert [p.experiment_id for p in results] == ["ohms-law", "current-voltage"]
    assert results[0].status is ProgressStatus.MEASUREMENT_COMPLETED
    assert results[1].status is ProgressStatus.NOT_STARTED


def test_latest_session_wins_when_multiple_links_exist() -> None:
    progress_repository, session_repository, _feedback = _make_repository()
    progress_repository.link_session("sess-old", "s1", "c1", "ohms-law")
    progress_repository.link_session("sess-new", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess-new")

    progress = progress_repository.get_progress("s1", "ohms-law")

    assert progress.latest_session_id == "sess-new"


def test_get_progress_same_linked_at_uses_rowid_desc() -> None:
    progress_repository, session_repository, _feedback = _make_repository()
    progress_repository.link_session("sess-old", "s1", "c1", "ohms-law")
    progress_repository.link_session("sess-new", "s1", "c1", "ohms-law")
    progress_repository._connection.execute(
        "UPDATE session_student_link SET linked_at = ?",
        ("2026-01-01T00:00:00+00:00",),
    )
    progress_repository._connection.commit()
    _save_measured_session(session_repository, "sess-new")

    progress = progress_repository.get_progress("s1", "ohms-law")

    assert progress.latest_session_id == "sess-new"


def test_compute_dashboard_counts_reflects_real_data() -> None:
    progress_repository, session_repository, feedback_repository = _make_repository()
    classroom_repository = progress_repository._classroom_repository
    student_repository = progress_repository._student_repository
    from domain.entities.classroom import Classroom
    from domain.entities.student import Student

    classroom_repository.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    student_repository.create(
        Student(id="s1", classroom_id="c1", first_name="Айдос", last_name="С",
                created_at=_NOW, updated_at=_NOW),
        UserRole.TEACHER,
    )
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    feedback_repository.save_submission(
        ExperimentFeedbackResult(
            experiment_id="ohms-law", session_id="sess1", is_draft=False, submitted_at=_NOW,
        )
    )

    counts = progress_repository.compute_dashboard_counts()

    assert counts["classrooms"] == 1
    assert counts["students"] == 1
    assert counts["completed"] == 1
    assert counts["awaiting_review"] == 1


def test_compute_dashboard_counts_empty_state() -> None:
    progress_repository, _sessions, _feedback = _make_repository()

    counts = progress_repository.compute_dashboard_counts()

    assert counts == {"classrooms": 0, "students": 0, "completed": 0, "awaiting_review": 0}


# =====================================================================
# Phase 13: compute_classroom_activity() — Teacher Dashboard "Бүгінгі
# белсенділік" панелі.
# =====================================================================


def test_compute_classroom_activity_empty_state_has_no_snapshots() -> None:
    """§ "DO NOT fabricate activity information" — классрумдар/оқушылар
    болса да, ешбір session_student_link болмаса, ЕШБІР snapshot
    қайтарылмайды."""
    from domain.entities.classroom import Classroom
    from domain.entities.student import Student

    progress_repository, _sessions, _feedback = _make_repository()
    classroom_repository = progress_repository._classroom_repository
    student_repository = progress_repository._student_repository
    classroom_repository.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    student_repository.create(
        Student(id="s1", classroom_id="c1", first_name="Айдос", last_name="С",
                created_at=_NOW, updated_at=_NOW),
        UserRole.TEACHER,
    )

    assert progress_repository.compute_classroom_activity() == ()


def test_compute_classroom_activity_buckets_students_by_status() -> None:
    from domain.entities.classroom import Classroom
    from domain.entities.student import Student

    progress_repository, session_repository, _feedback = _make_repository()
    classroom_repository = progress_repository._classroom_repository
    student_repository = progress_repository._student_repository
    classroom_repository.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    for sid, first in (("s1", "Один"), ("s2", "Екі"), ("s3", "Үш")):
        student_repository.create(
            Student(id=sid, classroom_id="c1", first_name=first, last_name="Т",
                    created_at=_NOW, updated_at=_NOW),
            UserRole.TEACHER,
        )

    # s1: measured (completed bucket); s2: linked, 0 measurements (in_progress); s3: never linked (not_started)
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    progress_repository.link_session("sess2", "s2", "c1", "ohms-law")

    snapshots = progress_repository.compute_classroom_activity()

    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert snapshot.classroom_name == "8А"
    assert snapshot.experiment_id == "ohms-law"
    assert snapshot.student_count == 3
    assert snapshot.completed_count == 1
    assert snapshot.in_progress_count == 1
    assert snapshot.not_started_count == 1
    assert snapshot.last_activity_at is not None
    assert snapshot.completion_percentage == round(1 / 3 * 100)


def test_compute_classroom_activity_picks_most_recently_linked_experiment() -> None:
    """Бір сыныпта екі ӘРТҮРЛІ тәжірибеге байланыс болса, ЕҢ СОҢҒЫ
    ``linked_at``-ы бар experiment_id таңдалады."""
    from domain.entities.classroom import Classroom
    from domain.entities.student import Student

    progress_repository, _sessions, _feedback = _make_repository()
    classroom_repository = progress_repository._classroom_repository
    student_repository = progress_repository._student_repository
    classroom_repository.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    student_repository.create(
        Student(id="s1", classroom_id="c1", first_name="Айдос", last_name="С",
                created_at=_NOW, updated_at=_NOW),
        UserRole.TEACHER,
    )

    progress_repository.link_session("sess_old", "s1", "c1", "old-experiment")
    progress_repository.link_session("sess_new", "s1", "c1", "new-experiment")

    snapshots = progress_repository.compute_classroom_activity()

    assert len(snapshots) == 1
    assert snapshots[0].experiment_id == "new-experiment"


# =====================================================================
# Phase 19 (Analytics Page): list_all_progress() — статус бойынша
# сүзгісіз, барлық байланысқан жұп.
# =====================================================================


def test_list_all_progress_empty_state_has_no_records() -> None:
    progress_repository, _sessions, _feedback = _make_repository()

    assert progress_repository.list_all_progress() == ()


def test_list_all_progress_returns_every_linked_pair_regardless_of_status() -> None:
    progress_repository, session_repository, feedback_repository = _make_repository()
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    feedback_repository.save_submission(
        ExperimentFeedbackResult(
            experiment_id="ohms-law", session_id="sess1", is_draft=False, submitted_at=_NOW,
        )
    )
    feedback_repository.save_teacher_assessment(
        "sess1", "ohms-law", TeacherAssessment(score=8, comment=""), UserRole.TEACHER
    )
    progress_repository.link_session("sess2", "s2", "c1", "current-voltage")

    results = progress_repository.list_all_progress()

    statuses = {(p.student_id, p.experiment_id): p.status for p in results}
    assert statuses[("s1", "ohms-law")] is ProgressStatus.REVIEWED
    assert statuses[("s2", "current-voltage")] is ProgressStatus.IN_PROGRESS
    assert len(results) == 2


def test_list_all_progress_never_includes_not_started() -> None:
    """§ ClassroomActivitySnapshot модуль docstring-і: "тағайындау"
    концепциясы доменде ЖОҚ, сондықтан байланысы жоқ жұп мұнда ешқашан
    болмайды."""
    progress_repository, _sessions, _feedback = _make_repository()
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")

    results = progress_repository.list_all_progress()

    assert all(p.status is not ProgressStatus.NOT_STARTED for p in results)


def test_compute_classroom_activity_skips_archived_classrooms() -> None:
    from domain.entities.classroom import Classroom
    from domain.entities.student import Student

    progress_repository, _sessions, _feedback = _make_repository()
    classroom_repository = progress_repository._classroom_repository
    student_repository = progress_repository._student_repository
    classroom_repository.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    student_repository.create(
        Student(id="s1", classroom_id="c1", first_name="Айдос", last_name="С",
                created_at=_NOW, updated_at=_NOW),
        UserRole.TEACHER,
    )
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    classroom_repository.archive("c1", UserRole.TEACHER, archived=True)

    assert progress_repository.compute_classroom_activity() == ()
