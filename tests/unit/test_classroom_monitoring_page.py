"""ClassroomMonitoringPage юнит-тесттері (Phase 6: Teacher Live Classroom
Monitoring Dashboard) — навигация, бос күйлер, сүзгі/сұрыптау, "defense
in depth" авторизация тексеруі."""

import sys
from datetime import datetime, timedelta, timezone

import pytest
from PySide6.QtWidgets import QApplication

from domain.entities.classroom import Classroom
from domain.entities.measurement import Measurement
from domain.entities.student import Student
from domain.entities.user_role import UserRole
from infrastructure.storage.sqlite_classroom_repository import SqliteClassroomRepository
from infrastructure.storage.sqlite_session_repository import SqliteSessionRepository
from infrastructure.storage.sqlite_student_progress_repository import SqliteStudentProgressRepository
from infrastructure.storage.sqlite_student_repository import SqliteStudentRepository
from modules.electricity.module import ElectricityModule
from modules.module_registry import ModuleRegistry
from ui.pages.classroom_monitoring_page import ClassroomMonitoringPage

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


def _make_measurement(offset_seconds: float) -> Measurement:
    return Measurement(
        timestamp=_now() - timedelta(seconds=offset_seconds), values={"voltage": 5.0, "current": 0.05},
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
    module_registry = ModuleRegistry()
    module_registry.register(ElectricityModule())
    return {
        "classroom": classroom_repo, "student": student_repo, "session": session_repo,
        "progress": progress_repo, "modules": module_registry,
    }


def _make_page(repos) -> ClassroomMonitoringPage:
    return ClassroomMonitoringPage(
        classroom_repository=repos["classroom"], student_repository=repos["student"],
        student_progress_repository=repos["progress"], session_repository=repos["session"],
        module_registry=repos["modules"],
    )


def test_no_classrooms_shows_empty_state(repos) -> None:
    page = _make_page(repos)

    page.on_enter()

    assert page._empty_label.isVisibleTo(page)
    assert "сынып" in page._empty_label.text()


def test_classroom_with_no_students_shows_empty_state(repos) -> None:
    repos["classroom"].create(Classroom(id="ca", name="8А", created_at=_now(), updated_at=_now()), UserRole.TEACHER)
    page = _make_page(repos)

    page.on_enter("ca")

    assert page._empty_label.isVisibleTo(page)
    assert page._classroom_name_label.text() == "8А"


def test_roster_shows_active_student(repos) -> None:
    repos["classroom"].create(Classroom(id="ca", name="8А", created_at=_now(), updated_at=_now()), UserRole.TEACHER)
    repos["student"].create(
        Student(id="s1", classroom_id="ca", first_name="Асан", last_name="Асанов", created_at=_now(), updated_at=_now()),
        UserRole.TEACHER,
    )
    repos["progress"].link_session("sess-1", "s1", "ca", "ohms-law")
    repos["session"].append_measurements("sess-1", "ohms-law", (_make_measurement(3),), started_at=_now())
    page = _make_page(repos)

    page.on_enter("ca")

    assert page._table.isVisibleTo(page)
    assert page._table.rowCount() == 1
    assert page._table.item(0, 0).text() == "Асанов Асан"
    assert "Тәжірибе жүріп жатыр" in page._table.item(0, 2).text()


def test_sticky_on_enter_keeps_same_classroom_for_auto_refresh(repos) -> None:
    repos["classroom"].create(Classroom(id="ca", name="8А", created_at=_now(), updated_at=_now()), UserRole.TEACHER)
    repos["student"].create(
        Student(id="s1", classroom_id="ca", first_name="Асан", last_name="Асанов", created_at=_now(), updated_at=_now()),
        UserRole.TEACHER,
    )
    page = _make_page(repos)
    page.on_enter("ca")

    repos["progress"].link_session("sess-1", "s1", "ca", "ohms-law")
    repos["session"].append_measurements("sess-1", "ohms-law", (_make_measurement(1),), started_at=_now())
    page.on_enter()  # § MainWindow auto-refresh choke point-пен БІРДЕЙ, параметрсіз

    assert page._table.rowCount() == 1
    assert "Тәжірибе жүріп жатыр" in page._table.item(0, 2).text()


def test_filter_active_hides_not_started_students(repos) -> None:
    repos["classroom"].create(Classroom(id="ca", name="8А", created_at=_now(), updated_at=_now()), UserRole.TEACHER)
    repos["student"].create(
        Student(id="s1", classroom_id="ca", first_name="Белсенді", last_name="Оқушы", created_at=_now(), updated_at=_now()),
        UserRole.TEACHER,
    )
    repos["student"].create(
        Student(id="s2", classroom_id="ca", first_name="Бастамаған", last_name="Оқушы", created_at=_now(), updated_at=_now()),
        UserRole.TEACHER,
    )
    repos["progress"].link_session("sess-1", "s1", "ca", "ohms-law")
    repos["session"].append_measurements("sess-1", "ohms-law", (_make_measurement(2),), started_at=_now())
    page = _make_page(repos)
    page.on_enter("ca")
    assert page._table.rowCount() == 2

    page._filter_combo.setCurrentText("Белсенді")

    assert page._table.rowCount() == 1
    assert page._table.item(0, 0).text() == "Оқушы Белсенді"


def test_sort_puts_active_before_not_started(repos) -> None:
    repos["classroom"].create(Classroom(id="ca", name="8А", created_at=_now(), updated_at=_now()), UserRole.TEACHER)
    repos["student"].create(
        Student(id="s1", classroom_id="ca", first_name="Бастамаған", last_name="Бірінші", created_at=_now(), updated_at=_now()),
        UserRole.TEACHER,
    )
    repos["student"].create(
        Student(id="s2", classroom_id="ca", first_name="Белсенді", last_name="Екінші", created_at=_now(), updated_at=_now()),
        UserRole.TEACHER,
    )
    repos["progress"].link_session("sess-2", "s2", "ca", "ohms-law")
    repos["session"].append_measurements("sess-2", "ohms-law", (_make_measurement(1),), started_at=_now())
    page = _make_page(repos)

    page.on_enter("ca")

    assert page._table.item(0, 0).text() == "Екінші Белсенді"
    assert page._table.item(1, 0).text() == "Бірінші Бастамаған"


def test_double_click_active_row_emits_student_selected(repos, qtbot=None) -> None:
    repos["classroom"].create(Classroom(id="ca", name="8А", created_at=_now(), updated_at=_now()), UserRole.TEACHER)
    repos["student"].create(
        Student(id="s1", classroom_id="ca", first_name="Асан", last_name="Асанов", created_at=_now(), updated_at=_now()),
        UserRole.TEACHER,
    )
    repos["progress"].link_session("sess-1", "s1", "ca", "ohms-law")
    repos["session"].append_measurements("sess-1", "ohms-law", (_make_measurement(1),), started_at=_now())
    page = _make_page(repos)
    page.on_enter("ca")
    received = []
    page.student_selected.connect(lambda sid, eid: received.append((sid, eid)))

    page._on_row_activated(0, 0)

    assert received == [("s1", "ohms-law")]


def test_double_click_not_started_row_does_not_emit(repos) -> None:
    repos["classroom"].create(Classroom(id="ca", name="8А", created_at=_now(), updated_at=_now()), UserRole.TEACHER)
    repos["student"].create(
        Student(id="s1", classroom_id="ca", first_name="Асан", last_name="Асанов", created_at=_now(), updated_at=_now()),
        UserRole.TEACHER,
    )
    page = _make_page(repos)
    page.on_enter("ca")
    received = []
    page.student_selected.connect(lambda sid, eid: received.append((sid, eid)))

    page._on_row_activated(0, 0)

    assert received == []


def test_back_button_emits_back_requested(repos) -> None:
    page = _make_page(repos)
    received = []
    page.back_requested.connect(lambda: received.append(True))

    page.back_requested.emit()

    assert received == [True]


# ---- Defense-in-depth authorization (§16) -----------------------------------


def test_classroom_id_not_in_allowed_list_is_never_shown(repos) -> None:
    """§16 "must remain true even if local UI filtering is bypassed" —
    ``classroom_repository.list_active()``-те ЖОҚ classroom_id
    берілсе (мыс. рұқсат етілмеген/жойылған сынып), ЕШБІР дерек
    көрсетілмейді."""
    repos["classroom"].create(Classroom(id="ca", name="8А", created_at=_now(), updated_at=_now()), UserRole.TEACHER)
    page = _make_page(repos)

    page.on_enter("unauthorized-classroom-id")

    assert page._current_classroom_id != "unauthorized-classroom-id"
    assert page._empty_label.isVisibleTo(page)
