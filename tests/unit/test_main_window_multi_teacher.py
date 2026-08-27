"""MainWindow — Multi-Teacher Accounts фазасының сессия/шектеу
интеграция тесттері: Sidebar-дағы аты-жөні, Teacher A/B арасындағы
сессия оқшаулануы, "Режімді ауыстыру" контекстті тазалауы, Сыныптар
мен оқушылар/Бақылау тақтасы/Аналитика беттерінің ағымдағы мұғалімге
сай сүзілуі."""

import sys
from datetime import datetime, timezone

import pytest
from PySide6.QtWidgets import QApplication

from domain.entities.active_teacher_context import ActiveTeacherContext
from domain.entities.classroom import Classroom
from domain.entities.student import Student
from domain.entities.teacher import Teacher
from domain.entities.user_role import UserRole
from domain.services.teacher_pin import hash_pin
from modules.module_registry import ModuleRegistry
from ui.main_window import MainWindow

_NOW = datetime.now(timezone.utc)


@pytest.fixture(scope="module", autouse=True)
def qt_application() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def _make_window() -> MainWindow:
    return MainWindow(module_registry=ModuleRegistry(), initial_role=UserRole.TEACHER)


def _seed_two_teachers_two_classes(window: MainWindow) -> tuple[Teacher, Teacher]:
    window.classroom_repository.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    window.classroom_repository.create(
        Classroom(id="c2", name="8Б", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    window.classroom_repository.create(
        Classroom(id="c3", name="8В", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    window.student_repository.create(
        Student(id="s1", classroom_id="c1", first_name="Aidos", last_name="A", created_at=_NOW, updated_at=_NOW),
        UserRole.TEACHER,
    )
    window.student_repository.create(
        Student(id="s2", classroom_id="c3", first_name="Bota", last_name="B", created_at=_NOW, updated_at=_NOW),
        UserRole.TEACHER,
    )
    teacher_a = Teacher(
        id="ta", full_name="Aidos Nurlanuly", pin_hash=hash_pin("482915"), created_at=_NOW, updated_at=_NOW
    )
    window.teacher_repository.create(teacher_a, assigned_classroom_ids=("c1", "c2"))
    teacher_b = Teacher(
        id="tb", full_name="Gulmira Serikkyzy", pin_hash=hash_pin("731426"), created_at=_NOW, updated_at=_NOW
    )
    window.teacher_repository.create(teacher_b, assigned_classroom_ids=("c3",))
    return teacher_a, teacher_b


def _login_via_page(window: MainWindow, pin: str) -> None:
    window._role_selection_page.show_teacher_login()
    window._role_selection_page._pin_edit.setText(pin)
    window._role_selection_page._on_teacher_login_clicked()


# ---- MainWindow constructs teacher infrastructure automatically -------------


def test_main_window_migrates_default_teacher_on_first_boot() -> None:
    window = _make_window()

    teachers = window.teacher_repository.list_all()
    assert len(teachers) == 1
    assert teachers[0].full_name == "Бастапқы мұғалім"


def test_settings_page_shows_initial_teacher_count() -> None:
    window = _make_window()

    assert "1" in window._settings_page._teacher_count_label.text()


# ---- Sidebar teacher name display --------------------------------------------


def test_sidebar_shows_authenticated_teacher_name_after_login() -> None:
    window = _make_window()
    _seed_two_teachers_two_classes(window)

    _login_via_page(window, "482915")

    assert window._sidebar._active_teacher_label.text() == "Aidos Nurlanuly"


def test_sidebar_teacher_label_cleared_when_switching_role() -> None:
    window = _make_window()
    _seed_two_teachers_two_classes(window)
    _login_via_page(window, "482915")
    assert window._sidebar._active_teacher_label.text() == "Aidos Nurlanuly"

    window._sidebar._switch_role_button.click()

    assert window._sidebar._active_teacher_label.text() == ""


# ---- Session isolation between Teacher A and Teacher B -----------------------


def test_teacher_a_login_sets_active_teacher_context() -> None:
    window = _make_window()
    _seed_two_teachers_two_classes(window)

    _login_via_page(window, "482915")

    assert window.active_teacher_repository.get() == ActiveTeacherContext(teacher_id="ta")


def test_switch_role_clears_active_teacher_before_next_login() -> None:
    window = _make_window()
    _seed_two_teachers_two_classes(window)
    _login_via_page(window, "482915")

    window._sidebar._switch_role_button.click()

    assert window.active_teacher_repository.get() is None


def test_teacher_b_login_after_teacher_a_does_not_inherit_session() -> None:
    """§14/§15: "Teacher B must not inherit Teacher A session state"."""
    window = _make_window()
    _seed_two_teachers_two_classes(window)
    _login_via_page(window, "482915")
    assert window._sidebar._active_teacher_label.text() == "Aidos Nurlanuly"

    window._sidebar._switch_role_button.click()
    _login_via_page(window, "731426")

    assert window.active_teacher_repository.get() == ActiveTeacherContext(teacher_id="tb")
    assert window._sidebar._active_teacher_label.text() == "Gulmira Serikkyzy"
    assert "Aidos" not in window._sidebar._active_teacher_label.text()


# ---- Classroom/student scoping wired through to teacher-facing pages --------


def test_class_management_page_scoped_to_teacher_a_classrooms() -> None:
    window = _make_window()
    _seed_two_teachers_two_classes(window)

    _login_via_page(window, "482915")
    window._class_management_page.on_enter()

    classroom_names = {c.name for c in window._class_management_page._classroom_repository.list_active()}
    assert classroom_names == {"8А", "8Б"}
    assert "8В" not in classroom_names


def test_class_management_page_scoped_to_teacher_b_classrooms_after_switch() -> None:
    window = _make_window()
    _seed_two_teachers_two_classes(window)
    _login_via_page(window, "482915")

    window._sidebar._switch_role_button.click()
    _login_via_page(window, "731426")
    window._class_management_page.on_enter()

    classroom_names = {c.name for c in window._class_management_page._classroom_repository.list_active()}
    assert classroom_names == {"8В"}


def test_student_browsing_is_scoped_through_teacher_assigned_classrooms() -> None:
    """§16 "Teacher -> Assigned Classes -> Students" — Teacher B (only
    8В) must never see Teacher A's student list even indirectly."""
    window = _make_window()
    _seed_two_teachers_two_classes(window)
    _login_via_page(window, "731426")
    window._class_management_page.on_enter()

    visible_classroom_ids = {
        c.id for c in window._class_management_page._classroom_repository.list_active()
    }
    assert visible_classroom_ids == {"c3"}
    students_in_scope = window.student_repository.list_by_classroom("c3")
    assert {s.id for s in students_in_scope} == {"s2"}


def test_teacher_dashboard_counts_scoped_to_active_teacher() -> None:
    window = _make_window()
    _seed_two_teachers_two_classes(window)

    _login_via_page(window, "482915")
    window._teacher_dashboard_page.on_enter()

    counts = window.student_progress_repository.compute_dashboard_counts(
        window._teacher_dashboard_page._allowed_classroom_ids()
    )
    assert counts["classrooms"] == 2


def test_analytics_page_classroom_list_scoped_to_active_teacher() -> None:
    window = _make_window()
    _seed_two_teachers_two_classes(window)

    _login_via_page(window, "731426")

    classroom_names = {c.name for c in window._analytics_page._classroom_repository.list_active()}
    assert classroom_names == {"8В"}


# ---- Teacher management -> Settings teacher count sync -----------------------


def test_adding_teacher_via_management_page_updates_settings_count() -> None:
    window = _make_window()
    from uuid import uuid4

    new_teacher = Teacher(
        id=str(uuid4()), full_name="New Teacher", pin_hash=hash_pin("555555"),
        created_at=_NOW, updated_at=_NOW,
    )
    window.teacher_repository.create(new_teacher)
    window._teacher_management_page.teachers_changed.emit()

    assert "2" in window._settings_page._teacher_count_label.text()


def test_manage_teachers_requested_navigates_to_teacher_management_route() -> None:
    window = _make_window()

    window._settings_page.manage_teachers_requested.emit()

    assert window._stack.currentWidget() is window._teacher_management_page


def test_teacher_management_back_returns_to_settings() -> None:
    window = _make_window()
    window._router.navigate("teacher_management")

    window._teacher_management_page.back_requested.emit()

    assert window._stack.currentWidget() is window._settings_page
