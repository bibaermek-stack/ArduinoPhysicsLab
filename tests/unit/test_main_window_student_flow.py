"""MainWindow — белсенді оқушы ағыны: гейттелген қону, Оқушы кіру коды
арқылы кіру ағыны (§ Mode Switch + Student Access Screen Redesign),
Sidebar-дан ауыстыру (өлшеу жүріп жатқанда бұғатталады), Оқушы режимінен
"classes" route-ына тыйым салынған тікелей навигация.

Ескі ``StudentSelectionPage``-ке негізделген ағын (сынып/оқушы
combobox + "Жалғастыру") ЕНДІ Оқушы аутентификация UI ретінде
қолданылмайды (§ "should no longer be exposed as the Student
authentication UI") — барлық осы файлдағы тесттер ЕНДІ
``window._role_selection_page``-тің кіру-код формасын қолданады
(§ ``test_role_selection_page.py``-мен БІРДЕЙ бет, тек MainWindow
контексінде).
"""

import sys
from datetime import datetime, timezone

import pytest
from PySide6.QtWidgets import QApplication

from domain.entities.active_student_context import ActiveStudentContext
from domain.entities.classroom import Classroom
from domain.entities.student import Student
from domain.entities.user_role import UserRole
from domain.services.student_access_code import generate_unique_student_code
from infrastructure.storage.sqlite_active_student_repository import SqliteActiveStudentRepository
from infrastructure.storage.sqlite_classroom_repository import SqliteClassroomRepository
from infrastructure.storage.sqlite_student_repository import SqliteStudentRepository
from modules.module_registry import ModuleRegistry
from ui.main_window import MainWindow

from tests.unit.test_main_window import FakeExperimentWorkspacePage, FakeHomePage, FakeExperimentListPage

_NOW = datetime.now(timezone.utc)


@pytest.fixture(scope="module", autouse=True)
def qt_application() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def _make_window(
    initial_role: UserRole = UserRole.STUDENT,
    seed_active_student: bool = False,
) -> tuple[MainWindow, FakeExperimentWorkspacePage, SqliteActiveStudentRepository, SqliteClassroomRepository, SqliteStudentRepository]:
    classroom_repository = SqliteClassroomRepository()
    student_repository = SqliteStudentRepository()
    active_repository = SqliteActiveStudentRepository()

    classroom_repository.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    student_repository.create(
        Student(id="s1", classroom_id="c1", first_name="Айдос", last_name="Серіков",
                created_at=_NOW, updated_at=_NOW),
        UserRole.TEACHER,
    )
    if seed_active_student:
        active_repository.set(ActiveStudentContext(classroom_id="c1", student_id="s1"))

    home_page = FakeHomePage()
    experiment_list_page = FakeExperimentListPage()
    experiment_workspace_page = FakeExperimentWorkspacePage()

    window = MainWindow(
        module_registry=ModuleRegistry(),
        initial_role=initial_role,
        home_page=home_page,
        experiment_list_page=experiment_list_page,
        experiment_workspace_page=experiment_workspace_page,
        classroom_repository=classroom_repository,
        student_repository=student_repository,
        active_student_repository=active_repository,
    )
    return window, experiment_workspace_page, active_repository, classroom_repository, student_repository


def _student_code(student_repository: SqliteStudentRepository) -> str:
    """§ ``MainWindow.__init__`` ӨЗІ ``backfill_missing_student_codes()``-ты
    шақырады, сондықтан "s1" конструкциядан кейін әрдайым коды бар."""
    student = student_repository.get("s1")
    assert student is not None
    assert student.student_code
    return student.student_code


def _login_as_student_via_code(window: MainWindow, code: str) -> None:
    """§ ``RoleSelectionPage``-тің ӨЗІ кіру-код формасын толтырып,
    "Кіру →" батырмасын басу арқылы (нақты пайдаланушы әрекетімен БІРДЕЙ
    жол, ``student_login_succeeded`` MainWindow-ды тек хабарлайды)."""
    page = window._role_selection_page
    page.show_student_login()
    page._code_edit.setText(code)
    page._on_login_clicked()


def test_student_role_without_active_student_lands_on_student_login() -> None:
    window, _workspace, _active, _classrooms, _students = _make_window(
        initial_role=UserRole.STUDENT, seed_active_student=False
    )

    assert window._stack.currentWidget() is window._role_selection_page
    assert window._role_selection_page._student_login_view.isVisibleTo(
        window._role_selection_page
    )


def test_student_role_with_active_student_lands_on_home() -> None:
    window, _workspace, _active, _classrooms, _students = _make_window(
        initial_role=UserRole.STUDENT, seed_active_student=True
    )

    assert window._stack.currentWidget() is window._home_page


def test_teacher_role_never_gated_by_active_student() -> None:
    window, _workspace, _active, _classrooms, _students = _make_window(
        initial_role=UserRole.TEACHER, seed_active_student=False
    )

    assert window._stack.currentWidget() is window._teacher_dashboard_page


def test_logging_in_with_valid_code_navigates_home_and_updates_sidebar() -> None:
    window, workspace_page, active_repository, _classrooms, students = _make_window(
        initial_role=UserRole.STUDENT, seed_active_student=False
    )
    assert window._stack.currentWidget() is window._role_selection_page
    code = _student_code(students)

    _login_as_student_via_code(window, code)

    assert window._stack.currentWidget() is window._home_page
    assert active_repository.get() == ActiveStudentContext(classroom_id="c1", student_id="s1")
    assert "Серіков Айдос" in window._sidebar._active_student_label.text()
    assert workspace_page.refresh_active_student_calls == 1


def test_switch_student_navigates_to_role_selection_login_view_and_closes_dialogs() -> None:
    window, workspace_page, _active, _classrooms, _students = _make_window(
        initial_role=UserRole.STUDENT, seed_active_student=True
    )
    workspace_page._is_measurement_running = False

    window._sidebar.switch_student_requested.emit()

    assert window._stack.currentWidget() is window._role_selection_page
    assert window._role_selection_page._student_login_view.isVisibleTo(
        window._role_selection_page
    )
    assert workspace_page.close_open_dialogs_calls >= 1


def test_switch_student_blocked_while_measurement_running() -> None:
    window, workspace_page, _active, _classrooms, _students = _make_window(
        initial_role=UserRole.STUDENT, seed_active_student=True
    )
    workspace_page._is_measurement_running = True
    current_before = window._stack.currentWidget()

    window._sidebar.switch_student_requested.emit()

    assert window._stack.currentWidget() is current_before


def test_switching_student_refreshes_active_identity() -> None:
    """§ "Switching students must refresh the active identity" — екінші
    оқушыға логин жасағанда, ескі "s1" контексі жаңа оқушымен
    алмастырылады (§ жалғыз canonical дереккөз)."""
    window, workspace_page, active_repository, classrooms, students = _make_window(
        initial_role=UserRole.STUDENT, seed_active_student=True
    )
    assert active_repository.get().student_id == "s1"
    # § "New students receive a code" — тек ``_on_add_student_clicked()``
    # (ClassManagementPage) кодты автоматты генерациялайды, репозиторийге
    # тікелей жазу ЖОҚ (§ backfill тек ``MainWindow.__init__``-те бір
    # рет жүреді, соңынан құрылған жазбаларға қатысы жоқ), сондықтан
    # осында да ДӘЛ СОЛ ``generate_unique_student_code()`` қолданылады.
    code = generate_unique_student_code(students)
    students.create(
        Student(id="s2", classroom_id="c1", first_name="Гүлмира", last_name="Жаксыбек",
                created_at=_NOW, updated_at=_NOW, student_code=code),
        UserRole.TEACHER,
    )

    window._sidebar.switch_student_requested.emit()
    _login_as_student_via_code(window, code)

    assert active_repository.get() == ActiveStudentContext(classroom_id="c1", student_id="s2")
    assert "Жаксыбек Гүлмира" in window._sidebar._active_student_label.text()
    assert window._stack.currentWidget() is window._home_page


def test_measurement_running_changed_disables_sidebar_switch_button() -> None:
    window, workspace_page, _active, _classrooms, _students = _make_window(
        initial_role=UserRole.STUDENT, seed_active_student=True
    )

    workspace_page.measurement_running_changed.emit(True)
    assert window._sidebar._switch_student_button.isEnabled() is False

    workspace_page.measurement_running_changed.emit(False)
    assert window._sidebar._switch_student_button.isEnabled() is True


def test_student_role_cannot_directly_navigate_to_classes_route() -> None:
    window, _workspace, _active, _classrooms, _students = _make_window(
        initial_role=UserRole.STUDENT, seed_active_student=True
    )
    current_before = window._stack.currentWidget()

    result = window._router.navigate("classes")

    assert result is False
    assert window._stack.currentWidget() is current_before


def test_teacher_can_navigate_to_classes_route() -> None:
    window, _workspace, _active, _classrooms, _students = _make_window(
        initial_role=UserRole.TEACHER, seed_active_student=False
    )

    result = window._router.navigate("classes")

    assert result is True
    assert window._stack.currentWidget() is window._class_management_page


def test_student_role_cannot_directly_navigate_to_feedback_teacher_route() -> None:
    window, _workspace, _active, _classrooms, _students = _make_window(
        initial_role=UserRole.STUDENT, seed_active_student=True
    )
    current_before = window._stack.currentWidget()

    result = window._router.navigate("feedback_teacher")

    assert result is False
    assert window._stack.currentWidget() is current_before


def test_teacher_can_navigate_to_feedback_teacher_route() -> None:
    window, _workspace, _active, _classrooms, _students = _make_window(
        initial_role=UserRole.TEACHER, seed_active_student=False
    )

    result = window._router.navigate("feedback_teacher")

    assert result is True
    assert window._stack.currentWidget() is window._teacher_feedback_review_page


def test_role_switch_to_student_without_active_student_redirects_to_student_login() -> None:
    window, _workspace, active_repository, _classrooms, _students = _make_window(
        initial_role=UserRole.TEACHER, seed_active_student=False
    )

    window._role_selection_page.role_selected.emit(UserRole.STUDENT)

    assert window._current_role is UserRole.STUDENT
    assert window._stack.currentWidget() is window._role_selection_page
    assert window._role_selection_page._student_login_view.isVisibleTo(
        window._role_selection_page
    )
