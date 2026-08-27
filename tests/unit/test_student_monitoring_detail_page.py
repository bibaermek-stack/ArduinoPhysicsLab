"""StudentMonitoringDetailPage юнит-тесттері (Phase 6: Teacher Live
Classroom Monitoring Dashboard §7/§8) — навигация, бос күйлер, графикті
инкременталды жаңарту, дубликат нүктелер жоқ."""

import sys
from datetime import datetime, timedelta, timezone

import pytest
from PySide6.QtWidgets import QApplication

from domain.entities.active_teacher_context import ActiveTeacherContext
from domain.entities.classroom import Classroom
from domain.entities.measurement import Measurement
from domain.entities.student import Student
from domain.entities.user_role import UserRole
from infrastructure.storage.sqlite_active_teacher_repository import SqliteActiveTeacherRepository
from infrastructure.storage.sqlite_classroom_repository import SqliteClassroomRepository
from infrastructure.storage.sqlite_session_repository import SqliteSessionRepository
from infrastructure.storage.sqlite_student_progress_repository import SqliteStudentProgressRepository
from infrastructure.storage.sqlite_student_repository import SqliteStudentRepository
from infrastructure.storage.sqlite_teacher_note_repository import SqliteTeacherNoteRepository
from modules.electricity.module import ElectricityModule
from modules.module_registry import ModuleRegistry
from ui.pages.student_monitoring_detail_page import StudentMonitoringDetailPage

def _now() -> datetime:
    # § "activity classification is wall-clock based" (Phase 6) — a module-
    # level constant captured at collection time would go stale relative to
    # the production code's own ``datetime.now()`` call by the time this
    # test actually runs in a large suite; each call here is fresh.
    return datetime.now(timezone.utc)


@pytest.fixture(scope="module", autouse=True)
def qt_application() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def _make_measurement(offset_seconds: float, voltage: float) -> Measurement:
    return Measurement(
        timestamp=_now() - timedelta(seconds=offset_seconds), values={"voltage": voltage, "current": 0.05},
        experiment_id="ohms-law",
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
    classroom_repo.create(Classroom(id="ca", name="8А", created_at=_now(), updated_at=_now()), UserRole.TEACHER)
    student_repo.create(
        Student(id="s1", classroom_id="ca", first_name="Асан", last_name="Асанов", created_at=_now(), updated_at=_now()),
        UserRole.TEACHER,
    )
    module_registry = ModuleRegistry()
    module_registry.register(ElectricityModule())
    teacher_note_repo = SqliteTeacherNoteRepository(db_path)
    active_teacher_repo = SqliteActiveTeacherRepository(db_path)
    active_teacher_repo.set(ActiveTeacherContext(teacher_id="t1"))
    return {
        "classroom": classroom_repo, "student": student_repo, "session": session_repo,
        "progress": progress_repo, "modules": module_registry,
        "teacher_note": teacher_note_repo, "active_teacher": active_teacher_repo,
    }


def _make_page(repos) -> StudentMonitoringDetailPage:
    return StudentMonitoringDetailPage(
        student_repository=repos["student"], classroom_repository=repos["classroom"],
        student_progress_repository=repos["progress"], session_repository=repos["session"],
        module_registry=repos["modules"],
        teacher_note_repository=repos["teacher_note"],
        active_teacher_repository=repos["active_teacher"],
    )


def test_unknown_student_shows_empty_state(repos) -> None:
    page = _make_page(repos)

    page.on_enter("does-not-exist", "ohms-law")

    assert page._empty_label.isVisibleTo(page)
    assert not page._live_graph.isVisibleTo(page)


def test_student_with_no_measurements_shows_empty_state(repos) -> None:
    repos["progress"].link_session("sess-1", "s1", "ca", "ohms-law")
    page = _make_page(repos)

    page.on_enter("s1", "ohms-law")

    assert page._empty_label.isVisibleTo(page)
    assert "Дерек күтілуде" in page._status_label.text() or "Бастамады" in page._status_label.text()


def test_active_experiment_shows_graph_and_status(repos) -> None:
    repos["progress"].link_session("sess-1", "s1", "ca", "ohms-law")
    repos["session"].append_measurements(
        "sess-1", "ohms-law", (_make_measurement(3, 4.0), _make_measurement(1, 5.0)), started_at=_now() - timedelta(seconds=3)
    )
    page = _make_page(repos)

    page.on_enter("s1", "ohms-law")

    assert page._live_graph.isVisibleTo(page)
    assert not page._empty_label.isVisibleTo(page)
    assert "Тәжірибе жүріп жатыр" in page._status_label.text()
    assert "8А" in page._info_label.text()
    assert page._appended_measurement_count == 2


def test_refresh_appends_only_new_measurements_incrementally(repos) -> None:
    """§8 "avoid unnecessarily rebuilding a huge graph every 10 seconds" —
    екінші ``on_enter()`` тек ЖАҢА measurement-дерді қосады, ТОЛЫҚ
    graph rebuild ЕМЕС (§ ``_appended_measurement_count`` өспелі)."""
    repos["progress"].link_session("sess-1", "s1", "ca", "ohms-law")
    repos["session"].append_measurements("sess-1", "ohms-law", (_make_measurement(5, 4.0),), started_at=_now() - timedelta(seconds=5))
    page = _make_page(repos)
    page.on_enter("s1", "ohms-law")
    assert page._appended_measurement_count == 1

    repos["session"].append_measurements("sess-1", "ohms-law", (_make_measurement(1, 5.0),), started_at=_now() - timedelta(seconds=5))
    page.on_enter()  # § sticky auto-refresh — параметрсіз

    assert page._appended_measurement_count == 2


def test_no_duplicate_points_after_repeated_refresh_with_no_new_data(repos) -> None:
    repos["progress"].link_session("sess-1", "s1", "ca", "ohms-law")
    repos["session"].append_measurements("sess-1", "ohms-law", (_make_measurement(2, 4.0),), started_at=_now())
    page = _make_page(repos)
    page.on_enter("s1", "ohms-law")
    assert page._appended_measurement_count == 1

    page.on_enter()
    page.on_enter()

    assert page._appended_measurement_count == 1  # § "жаңа дерек жоқ" -> қайта қосу ЖОҚ


def test_completed_experiment_shows_completed_status(repos) -> None:
    from domain.entities.experiment_session import ExperimentSession

    repos["progress"].link_session("sess-1", "s1", "ca", "ohms-law")
    repos["session"].save_session(
        ExperimentSession(
            id="sess-1", experiment_id="ohms-law", started_at=_now() - timedelta(minutes=5), ended_at=_now() - timedelta(minutes=4),
            measurements=[_make_measurement(300, 4.0)],
        )
    )
    page = _make_page(repos)

    page.on_enter("s1", "ohms-law")

    assert "Аяқталды" in page._status_label.text()


def test_back_button_emits_back_requested(repos) -> None:
    page = _make_page(repos)
    received = []
    page.back_requested.connect(lambda: received.append(True))

    page.back_requested.emit()

    assert received == [True]


# ---- Phase 7 (Teacher Actions, Feedback Delivery, and Session History) ----


def test_history_button_emits_session_history_requested(repos) -> None:
    page = _make_page(repos)
    page.on_enter("s1", "ohms-law")
    received = []
    page.session_history_requested.connect(lambda student_id: received.append(student_id))

    page._on_history_clicked()

    assert received == ["s1"]


def test_history_button_disabled_without_student() -> None:
    repos_dict = _repos_without_student()
    page = _make_page(repos_dict)
    page.on_enter()

    assert not page._history_button.isEnabled()


def _repos_without_student():
    """§ ``_history_button`` "no student selected yet" тест жағдайы —
    жеке, кіші фикстура (fixture емес, тікелей функция) себебі негізгі
    ``repos`` фикстурасы алдын ала оқушыны құрастырады."""
    import tempfile
    from pathlib import Path

    tmp_dir = Path(tempfile.mkdtemp())
    db_path = str(tmp_dir / "monitoring_empty.db")
    classroom_repo = SqliteClassroomRepository(db_path)
    student_repo = SqliteStudentRepository(db_path)
    session_repo = SqliteSessionRepository(db_path)
    progress_repo = SqliteStudentProgressRepository(
        db_path, session_repository=session_repo, classroom_repository=classroom_repo, student_repository=student_repo,
    )
    module_registry = ModuleRegistry()
    module_registry.register(ElectricityModule())
    return {
        "classroom": classroom_repo, "student": student_repo, "session": session_repo,
        "progress": progress_repo, "modules": module_registry,
        "teacher_note": SqliteTeacherNoteRepository(db_path),
        "active_teacher": SqliteActiveTeacherRepository(db_path),
    }


def test_empty_notes_list_shows_placeholder(repos) -> None:
    page = _make_page(repos)

    page.on_enter("s1", "ohms-law")

    assert page._notes_list.count() == 1
    assert "пікір" in page._notes_list.item(0).text()


def test_send_note_creates_note_and_refreshes_list(repos) -> None:
    page = _make_page(repos)
    page.on_enter("s1", "ohms-law")

    page._message_edit.setText("Кернеу мәніне назар аудар")
    page._on_send_clicked()

    notes = repos["teacher_note"].list_for_student("s1")
    assert len(notes) == 1
    assert notes[0].message == "Кернеу мәніне назар аудар"
    assert notes[0].teacher_id == "t1"
    assert notes[0].experiment_id == "ohms-law"
    assert page._message_edit.text() == ""
    assert page._notes_list.count() == 1
    assert "Кернеу мәніне назар аудар" in page._notes_list.item(0).text()
    assert "Жіберілуде" in page._notes_list.item(0).text()


def test_send_note_ignores_blank_message(repos) -> None:
    page = _make_page(repos)
    page.on_enter("s1", "ohms-law")

    page._message_edit.setText("   ")
    page._on_send_clicked()

    assert repos["teacher_note"].list_for_student("s1") == ()


def test_send_note_without_active_teacher_does_not_crash(repos) -> None:
    repos["active_teacher"].clear()
    page = _make_page(repos)
    page.on_enter("s1", "ohms-law")

    page._message_edit.setText("Хабарлама")
    page._on_send_clicked()

    assert repos["teacher_note"].list_for_student("s1") == ()


def test_notes_list_shows_delivered_state_after_sync(repos) -> None:
    page = _make_page(repos)
    page.on_enter("s1", "ohms-law")
    page._message_edit.setText("Тексерілді")
    page._on_send_clicked()
    note_id = repos["teacher_note"].list_for_student("s1")[0].id

    repos["teacher_note"].mark_note_synced(note_id, 1)
    page._refresh_notes()

    assert "Жеткізілді" in page._notes_list.item(0).text()


def test_notes_list_shows_newest_first(repos) -> None:
    page = _make_page(repos)
    page.on_enter("s1", "ohms-law")

    page._message_edit.setText("Бірінші")
    page._on_send_clicked()
    page._message_edit.setText("Екінші")
    page._on_send_clicked()

    assert "Екінші" in page._notes_list.item(0).text()
    assert "Бірінші" in page._notes_list.item(1).text()
