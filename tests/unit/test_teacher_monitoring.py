"""domain/services/teacher_monitoring.py тесттері (Phase 6: Teacher
Live Classroom Monitoring Dashboard) — activity classification (таза
функция), classroom/student snapshot aggregation (нақты sqlite
репозиторийлер, инъекцияланған ``now`` — ешбір flaky wall-clock sleep).
"""

from datetime import datetime, timedelta, timezone

import pytest

from domain.entities.classroom import Classroom
from domain.entities.measurement import Measurement
from domain.entities.monitoring_activity_state import MonitoringActivityState
from domain.entities.student import Student
from domain.entities.student_experiment_progress import ProgressStatus
from domain.entities.user_role import UserRole
from domain.services.teacher_monitoring import (
    DEFAULT_ACTIVE_WINDOW,
    DEFAULT_STALE_WINDOW,
    classify_activity,
    compute_classroom_monitoring,
    compute_student_monitoring_detail,
)
from infrastructure.storage.sqlite_classroom_repository import SqliteClassroomRepository
from infrastructure.storage.sqlite_session_repository import SqliteSessionRepository
from infrastructure.storage.sqlite_student_progress_repository import SqliteStudentProgressRepository
from infrastructure.storage.sqlite_student_repository import SqliteStudentRepository

_NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


# ---- classify_activity() — pure function -----------------------------------
#
# § "session_is_running" — ХАЛАЛ "тәжірибе әлі жүріп жатыр ма" сигналы
# (§ ``SessionSummary.ended_at is None``), ЕШҚАШАН ``ProgressStatus``
# ЕМЕС (§ ``classify_activity()`` докстрингіндегі түбір себеп: Phase 4/5
# инкременталды ``append_measurements()`` арқасында measurement_count>0
# БОЛСА да сессия ӘЛІ шынымен жүріп жатуы мүмкін).


def test_not_started_status_is_never_active() -> None:
    assert (
        classify_activity(ProgressStatus.NOT_STARTED, None, None, _NOW)
        is MonitoringActivityState.NOT_STARTED
    )


def test_finished_session_is_completed_regardless_of_progress_status() -> None:
    """§ ЕЩ ProgressStatus мәні (MEASUREMENT_COMPLETED/REPORT_COMPLETED/
    FEEDBACK_SUBMITTED/REVIEWED) сессия ``ended_at``-ы БАР болса,
    әрқашан COMPLETED деп есептеледі — тек ``session_is_running=False``
    ШЕШУШІ сигнал."""
    result = classify_activity(
        ProgressStatus.MEASUREMENT_COMPLETED, False, _NOW - timedelta(hours=1), _NOW
    )
    assert result is MonitoringActivityState.COMPLETED


def test_in_progress_with_recent_measurement_is_active() -> None:
    result = classify_activity(ProgressStatus.IN_PROGRESS, True, _NOW - timedelta(seconds=5), _NOW)
    assert result is MonitoringActivityState.ACTIVE


def test_measurement_completed_status_but_session_still_running_is_active() -> None:
    """§ НАҚТЫ табылған/түзетілген дизайн қатесі: Phase 4/5-те
    measurement_count>0 БОЛҒАН СОҢ да ``derive_status()`` бірден
    ``MEASUREMENT_COMPLETED`` қайтарады, БІРАҚ сессия (``ended_at IS
    NULL``) ӘЛІ ШЫНЫМЕН жүріп жатуы мүмкін — ``session_is_running=True``
    осы жағдайда ЖЕҢЕДІ, ACTIVE/STALE/OFFLINE НАҚТЫ measurement
    жаңалығынан есептеледі."""
    result = classify_activity(
        ProgressStatus.MEASUREMENT_COMPLETED, True, _NOW - timedelta(seconds=5), _NOW
    )
    assert result is MonitoringActivityState.ACTIVE


def test_in_progress_at_exact_active_window_boundary_is_active() -> None:
    result = classify_activity(ProgressStatus.IN_PROGRESS, True, _NOW - DEFAULT_ACTIVE_WINDOW, _NOW)
    assert result is MonitoringActivityState.ACTIVE


def test_in_progress_just_past_active_window_is_stale() -> None:
    result = classify_activity(
        ProgressStatus.IN_PROGRESS, True, _NOW - DEFAULT_ACTIVE_WINDOW - timedelta(seconds=1), _NOW
    )
    assert result is MonitoringActivityState.STALE


def test_in_progress_at_exact_stale_window_boundary_is_stale() -> None:
    result = classify_activity(ProgressStatus.IN_PROGRESS, True, _NOW - DEFAULT_STALE_WINDOW, _NOW)
    assert result is MonitoringActivityState.STALE


def test_in_progress_past_stale_window_is_offline() -> None:
    result = classify_activity(
        ProgressStatus.IN_PROGRESS, True, _NOW - DEFAULT_STALE_WINDOW - timedelta(seconds=1), _NOW
    )
    assert result is MonitoringActivityState.OFFLINE


def test_linked_session_not_yet_created_with_no_measurement_is_stale() -> None:
    """§ "linked but zero measurements yet" — ``session_student_link``
    бар, БІРАҚ бірінші ``append_measurements()``-тен БҰРЫН (``session_
    is_running=None``, § ``experiment_sessions`` жолы ӘЛІ ЖОҚ) — ЕШҚАШАН
    OFFLINE/COMPLETED фабрикацияланбайды, тек "әлі дәлел жоқ" (STALE)."""
    assert (
        classify_activity(ProgressStatus.IN_PROGRESS, None, None, _NOW)
        is MonitoringActivityState.STALE
    )


def test_clock_skew_never_produces_negative_age_crash() -> None:
    """§ қорғаныс: measurement уақыты ``now``-дан КЕЙІН болса (сағат
    ауытқуы), ешбір exception, ACTIVE деп есептеледі."""
    result = classify_activity(ProgressStatus.IN_PROGRESS, True, _NOW + timedelta(seconds=30), _NOW)
    assert result is MonitoringActivityState.ACTIVE


def test_custom_thresholds_are_respected() -> None:
    result = classify_activity(
        ProgressStatus.IN_PROGRESS, True, _NOW - timedelta(seconds=3), _NOW,
        active_window=timedelta(seconds=2), stale_window=timedelta(seconds=10),
    )
    assert result is MonitoringActivityState.STALE


# ---- compute_classroom_monitoring() / compute_student_monitoring_detail() --


def _make_measurement(offset_seconds: float, voltage: float) -> Measurement:
    return Measurement(
        timestamp=_NOW - timedelta(seconds=offset_seconds), values={"voltage": voltage}, experiment_id="ohms-law"
    )


@pytest.fixture()
def repos(tmp_path):
    db_path = str(tmp_path / "monitoring.db")
    classroom_repo = SqliteClassroomRepository(db_path)
    student_repo = SqliteStudentRepository(db_path)
    session_repo = SqliteSessionRepository(db_path)
    progress_repo = SqliteStudentProgressRepository(
        db_path, session_repository=session_repo, classroom_repository=classroom_repo, student_repository=student_repo,
    )
    classroom_repo.create(Classroom(id="ca", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER)
    return {
        "classroom": classroom_repo, "student": student_repo, "session": session_repo, "progress": progress_repo,
    }


def _add_student(repos, student_id: str, classroom_id: str = "ca") -> None:
    repos["student"].create(
        Student(id=student_id, classroom_id=classroom_id, first_name="Оқушы", last_name=student_id, created_at=_NOW, updated_at=_NOW),
        UserRole.TEACHER,
    )


def test_unknown_classroom_returns_none(repos) -> None:
    result = compute_classroom_monitoring(
        "does-not-exist", classroom_repository=repos["classroom"], student_repository=repos["student"],
        student_progress_repository=repos["progress"], session_repository=repos["session"], now=_NOW,
    )
    assert result is None


def test_empty_classroom_has_zero_students(repos) -> None:
    snapshot = compute_classroom_monitoring(
        "ca", classroom_repository=repos["classroom"], student_repository=repos["student"],
        student_progress_repository=repos["progress"], session_repository=repos["session"], now=_NOW,
    )
    assert snapshot is not None
    assert snapshot.total_students == 0
    assert snapshot.classroom_name == "8А"


def test_student_with_no_session_is_not_started(repos) -> None:
    _add_student(repos, "s1")

    snapshot = compute_classroom_monitoring(
        "ca", classroom_repository=repos["classroom"], student_repository=repos["student"],
        student_progress_repository=repos["progress"], session_repository=repos["session"], now=_NOW,
    )

    assert snapshot.total_students == 1
    assert snapshot.students[0].activity_state is MonitoringActivityState.NOT_STARTED
    assert snapshot.not_started_count == 1


def test_active_session_with_recent_measurement(repos) -> None:
    _add_student(repos, "s1")
    repos["progress"].link_session("sess-1", "s1", "ca", "ohms-law")
    repos["session"].append_measurements(
        "sess-1", "ohms-law", (_make_measurement(20, 3.0), _make_measurement(3, 6.5)), started_at=_NOW - timedelta(seconds=20)
    )

    snapshot = compute_classroom_monitoring(
        "ca", classroom_repository=repos["classroom"], student_repository=repos["student"],
        student_progress_repository=repos["progress"], session_repository=repos["session"], now=_NOW,
    )

    student_snapshot = snapshot.students[0]
    assert student_snapshot.activity_state is MonitoringActivityState.ACTIVE
    assert student_snapshot.measurement_count == 2
    assert student_snapshot.latest_measurement_values == {"voltage": 6.5}
    assert snapshot.active_count == 1


def test_stale_session_needs_attention(repos) -> None:
    _add_student(repos, "s1")
    repos["progress"].link_session("sess-1", "s1", "ca", "ohms-law")
    repos["session"].append_measurements(
        "sess-1", "ohms-law", (_make_measurement(90, 3.0),), started_at=_NOW - timedelta(seconds=90)
    )

    snapshot = compute_classroom_monitoring(
        "ca", classroom_repository=repos["classroom"], student_repository=repos["student"],
        student_progress_repository=repos["progress"], session_repository=repos["session"], now=_NOW,
    )

    assert snapshot.students[0].activity_state is MonitoringActivityState.OFFLINE
    assert snapshot.needs_attention_count == 1


def test_completed_session_is_not_active(repos) -> None:
    _add_student(repos, "s1")
    repos["progress"].link_session("sess-1", "s1", "ca", "ohms-law")
    repos["session"].append_measurements("sess-1", "ohms-law", (_make_measurement(3600, 3.0),), started_at=_NOW - timedelta(hours=1))
    from domain.entities.experiment_session import ExperimentSession

    full_session = ExperimentSession(
        id="sess-1", experiment_id="ohms-law", started_at=_NOW - timedelta(hours=1), ended_at=_NOW - timedelta(minutes=50),
        measurements=[_make_measurement(3600, 3.0)],
    )
    repos["session"].save_session(full_session)

    snapshot = compute_classroom_monitoring(
        "ca", classroom_repository=repos["classroom"], student_repository=repos["student"],
        student_progress_repository=repos["progress"], session_repository=repos["session"], now=_NOW,
    )

    assert snapshot.students[0].activity_state is MonitoringActivityState.COMPLETED
    assert snapshot.completed_count == 1


def test_multiple_experiments_picks_most_recently_started(repos) -> None:
    _add_student(repos, "s1")
    repos["progress"].link_session("sess-old", "s1", "ca", "ohms-law")
    repos["session"].append_measurements("sess-old", "ohms-law", (_make_measurement(7200, 1.0),), started_at=_NOW - timedelta(hours=2))
    repos["progress"].link_session("sess-new", "s1", "ca", "rc-circuit")
    repos["session"].append_measurements("sess-new", "rc-circuit", (_make_measurement(5, 9.0),), started_at=_NOW - timedelta(seconds=5))

    snapshot = compute_classroom_monitoring(
        "ca", classroom_repository=repos["classroom"], student_repository=repos["student"],
        student_progress_repository=repos["progress"], session_repository=repos["session"], now=_NOW,
    )

    assert snapshot.students[0].experiment_id == "rc-circuit"
    assert snapshot.students[0].latest_session_id == "sess-new"


def test_classroom_isolation_never_shows_other_classroom_students(repos) -> None:
    repos["classroom"].create(Classroom(id="cb", name="8Б", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER)
    _add_student(repos, "s1", classroom_id="ca")
    _add_student(repos, "s2", classroom_id="cb")

    snapshot = compute_classroom_monitoring(
        "ca", classroom_repository=repos["classroom"], student_repository=repos["student"],
        student_progress_repository=repos["progress"], session_repository=repos["session"], now=_NOW,
    )

    assert snapshot.total_students == 1
    assert snapshot.students[0].student_id == "s1"


def test_thirty_student_classroom_scale(repos) -> None:
    for i in range(30):
        _add_student(repos, f"s{i}")
    for i in range(0, 10):
        repos["progress"].link_session(f"sess-{i}", f"s{i}", "ca", "ohms-law")
        repos["session"].append_measurements(f"sess-{i}", "ohms-law", (_make_measurement(2, 5.0),), started_at=_NOW)

    snapshot = compute_classroom_monitoring(
        "ca", classroom_repository=repos["classroom"], student_repository=repos["student"],
        student_progress_repository=repos["progress"], session_repository=repos["session"], now=_NOW,
    )

    assert snapshot.total_students == 30
    assert snapshot.active_count == 10
    assert snapshot.not_started_count == 20


# ---- compute_student_monitoring_detail() ------------------------------------


def test_student_detail_unknown_student_returns_none(repos) -> None:
    result = compute_student_monitoring_detail(
        "does-not-exist", "ohms-law", student_repository=repos["student"], classroom_repository=repos["classroom"],
        student_progress_repository=repos["progress"], session_repository=repos["session"], now=_NOW,
    )
    assert result is None


def test_student_detail_preserves_measurement_order(repos) -> None:
    _add_student(repos, "s1")
    repos["progress"].link_session("sess-1", "s1", "ca", "ohms-law")
    repos["session"].append_measurements(
        "sess-1", "ohms-law",
        (_make_measurement(10, 1.0), _make_measurement(5, 2.0), _make_measurement(1, 3.0)),
        started_at=_NOW - timedelta(seconds=10),
    )

    detail = compute_student_monitoring_detail(
        "s1", "ohms-law", student_repository=repos["student"], classroom_repository=repos["classroom"],
        student_progress_repository=repos["progress"], session_repository=repos["session"], now=_NOW,
    )

    assert detail is not None
    assert [m.values["voltage"] for m in detail.measurements] == [1.0, 2.0, 3.0]
    assert detail.classroom_name == "8А"
    assert detail.measurement_count == 3
    assert detail.activity_state is MonitoringActivityState.ACTIVE
