"""SqliteStudentProgressRepository — ``allowed_classroom_ids`` сүзгісінің
юнит-тесттері (Multi-Teacher Accounts §6). Бар ``test_sqlite_student_
progress_repository.py``-ге ЕШБІР қатысы жоқ (§ ол файл ӨЗГЕРТІЛМЕГЕН,
дефолт ``allowed_classroom_ids=None`` мінез-құлқы бит-бітіне сол
қалпында), бұл файл ТЕК жаңа параметрдің өзін тексереді."""

from datetime import datetime, timezone

from domain.entities.classroom import Classroom
from domain.entities.experiment_feedback_result import ExperimentFeedbackResult
from domain.entities.experiment_session import ExperimentSession
from domain.entities.measurement import Measurement
from domain.entities.student import Student
from domain.entities.student_experiment_progress import ProgressStatus
from domain.entities.user_role import UserRole
from infrastructure.storage.sqlite_classroom_repository import SqliteClassroomRepository
from infrastructure.storage.sqlite_feedback_repository import SqliteFeedbackRepository
from infrastructure.storage.sqlite_session_repository import SqliteSessionRepository
from infrastructure.storage.sqlite_student_progress_repository import SqliteStudentProgressRepository
from infrastructure.storage.sqlite_student_repository import SqliteStudentRepository

_NOW = datetime.now(timezone.utc)


def _make_repository() -> tuple[
    SqliteStudentProgressRepository, SqliteSessionRepository, SqliteFeedbackRepository,
    SqliteClassroomRepository, SqliteStudentRepository,
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
    return progress_repository, session_repository, feedback_repository, classroom_repository, student_repository


def _seed_two_classrooms_with_measured_sessions(
    progress_repository: SqliteStudentProgressRepository,
    session_repository: SqliteSessionRepository,
    classroom_repository: SqliteClassroomRepository,
    student_repository: SqliteStudentRepository,
) -> None:
    for classroom_id, name in (("c1", "8А"), ("c2", "8Б")):
        classroom_repository.create(
            Classroom(id=classroom_id, name=name, created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
        )
    student_repository.create(
        Student(id="s1", classroom_id="c1", first_name="A", last_name="B", created_at=_NOW, updated_at=_NOW),
        UserRole.TEACHER,
    )
    student_repository.create(
        Student(id="s2", classroom_id="c2", first_name="C", last_name="D", created_at=_NOW, updated_at=_NOW),
        UserRole.TEACHER,
    )

    progress_repository.link_session("sess-c1", "s1", "c1", "ohms-law")
    session1 = ExperimentSession(id="sess-c1", experiment_id="ohms-law", started_at=_NOW)
    session1.add_measurement(Measurement(timestamp=_NOW, values={"voltage": 5.0}, experiment_id="ohms-law"))
    session_repository.save_session(session1)

    progress_repository.link_session("sess-c2", "s2", "c2", "ohms-law")
    session2 = ExperimentSession(id="sess-c2", experiment_id="ohms-law", started_at=_NOW)
    session2.add_measurement(Measurement(timestamp=_NOW, values={"voltage": 5.0}, experiment_id="ohms-law"))
    session_repository.save_session(session2)


# ---- compute_dashboard_counts -----------------------------------------------


def test_dashboard_counts_unrestricted_by_default() -> None:
    progress_repository, session_repository, _feedback, classroom_repository, student_repository = (
        _make_repository()
    )
    _seed_two_classrooms_with_measured_sessions(
        progress_repository, session_repository, classroom_repository, student_repository
    )

    counts = progress_repository.compute_dashboard_counts()

    assert counts["classrooms"] == 2
    assert counts["students"] == 2


def test_dashboard_counts_scoped_to_single_classroom() -> None:
    progress_repository, session_repository, _feedback, classroom_repository, student_repository = (
        _make_repository()
    )
    _seed_two_classrooms_with_measured_sessions(
        progress_repository, session_repository, classroom_repository, student_repository
    )

    counts = progress_repository.compute_dashboard_counts(frozenset({"c1"}))

    assert counts["classrooms"] == 1
    assert counts["students"] == 1
    assert counts["completed"] == 1  # only s1/c1's measured session counted


def test_dashboard_counts_empty_allowed_set_yields_zero() -> None:
    progress_repository, session_repository, _feedback, classroom_repository, student_repository = (
        _make_repository()
    )
    _seed_two_classrooms_with_measured_sessions(
        progress_repository, session_repository, classroom_repository, student_repository
    )

    counts = progress_repository.compute_dashboard_counts(frozenset())

    assert counts == {"classrooms": 0, "students": 0, "completed": 0, "awaiting_review": 0}


# ---- compute_classroom_activity ---------------------------------------------


def test_classroom_activity_scoped_excludes_other_teachers_classroom() -> None:
    progress_repository, session_repository, _feedback, classroom_repository, student_repository = (
        _make_repository()
    )
    _seed_two_classrooms_with_measured_sessions(
        progress_repository, session_repository, classroom_repository, student_repository
    )

    snapshots = progress_repository.compute_classroom_activity(frozenset({"c1"}))

    assert {s.classroom_id for s in snapshots} == {"c1"}


# ---- list_submitted_progress / list_all_progress -----------------------------


def test_list_all_progress_scoped_to_classroom() -> None:
    progress_repository, session_repository, _feedback, classroom_repository, student_repository = (
        _make_repository()
    )
    _seed_two_classrooms_with_measured_sessions(
        progress_repository, session_repository, classroom_repository, student_repository
    )

    scoped = progress_repository.list_all_progress(frozenset({"c2"}))

    assert len(scoped) == 1
    assert scoped[0].student_id == "s2"


def test_list_submitted_progress_scoped_excludes_other_classroom() -> None:
    progress_repository, session_repository, feedback_repository, classroom_repository, student_repository = (
        _make_repository()
    )
    _seed_two_classrooms_with_measured_sessions(
        progress_repository, session_repository, classroom_repository, student_repository
    )
    for session_id in ("sess-c1", "sess-c2"):
        feedback_repository.save_submission(
            ExperimentFeedbackResult(
                session_id=session_id, experiment_id="ohms-law", is_draft=False,
                level1_answers=(), level1_score=0, level1_total=0, level1_percentage=0.0,
                level2_answers=(), level3_answers=(),
            )
        )

    scoped = progress_repository.list_submitted_progress(frozenset({"c1"}))

    assert len(scoped) == 1
    assert scoped[0].student_id == "s1"
    assert scoped[0].status is ProgressStatus.FEEDBACK_SUBMITTED
