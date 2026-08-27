"""RoleSelectionPage — юнит-тесттері (Mode Switch + Student Access Screen
Redesign фазасы; Teacher Login Redesign фазасы; Multi-Teacher Accounts
фазасы).

Мұғалім кіруі ЕНДІ модальды ``TeacherPinDialog`` ЕМЕС — ДӘЛ Оқушы кіру
бетімен БІРДЕЙ құрылымды толық экрандық "teacher_login" көрінісі (§
``role_selection_page.py``). ``TeacherPinDialog`` класының ӨЗІ де
ЖОЙЫЛМАҒАН, оның ОҚШАУЛАНҒАН тесттері ``test_teacher_pin_dialog.py``-де
ӨЗГЕРІССІЗ қалады, тек өндірістік ағында ЕНДІ ЕШҚАШАН ашылмайды (осы
файлдағы ``test_teacher_button_does_not_create_pin_dialog`` — теріс
растама).

§ Multi-Teacher Accounts: PIN тексеру логикасы ЕНДІ ЖАЛҒЫЗ ортақ PIN
ЕМЕС — ``domain.services.teacher_pin.resolve_teacher_by_pin()`` арқылы
БІРНЕШЕ ``Teacher`` жазбасы арасынан іздейді (§ ``test_teacher_pin_
resolution.py``-де бөлек тексеріледі, бұл жерде тек ROLE SELECTION UI
ағыны — PIN енгізу/қате/сәтті кіру/сессия жазылуы).

Оқушы батырмасы бірден ``role_selected`` шығармайды — "mode"
көрінісінен "student_login" көрінісіне ауысады. Мұғалім батырмасы да
дәл СОЛ сияқты — "mode" көрінісінен "teacher_login" көрінісіне ауысады,
рөл ТЕК дұрыс PIN расталғаннан кейін ғана ауысады.

Барлық тесттер бетті нақты ``.show()`` етеді — ``isVisible()``/
``hasFocus()`` тек нақты экранға шығарылған (real top-level shown)
виджеттерде дұрыс жұмыс істейді (headless orta да ``QTest.
qWaitForWindowExposed`` арқылы расталады).
"""

import sys
from datetime import datetime, timezone

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit

from domain.entities.active_student_context import ActiveStudentContext
from domain.entities.active_teacher_context import ActiveTeacherContext
from domain.entities.student import Student
from domain.entities.teacher import Teacher
from domain.entities.user_role import UserRole
from domain.services.teacher_pin import hash_pin
from infrastructure.storage.sqlite_active_student_repository import SqliteActiveStudentRepository
from infrastructure.storage.sqlite_active_teacher_repository import SqliteActiveTeacherRepository
from infrastructure.storage.sqlite_student_repository import SqliteStudentRepository
from infrastructure.storage.sqlite_teacher_repository import SqliteTeacherRepository
from ui.pages.role_selection_page import RoleSelectionPage
from ui.widgets.teacher_pin_dialog import TeacherPinDialog

_DEV_PIN = "1234"


@pytest.fixture(scope="module", autouse=True)
def qt_application() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def _make_student(code: str = "482731") -> Student:
    now = datetime.now(timezone.utc)
    return Student(
        id="s1",
        classroom_id="c1",
        first_name="Samat",
        last_name="Otarbai",
        created_at=now,
        updated_at=now,
        student_code=code,
    )


def _make_teacher(
    teacher_id: str = "t1", full_name: str = "Aidos Nurlanuly", pin: str = _DEV_PIN,
    is_active: bool = True,
) -> Teacher:
    now = datetime.now(timezone.utc)
    return Teacher(
        id=teacher_id, full_name=full_name, pin_hash=hash_pin(pin),
        created_at=now, updated_at=now, is_active=is_active,
    )


@pytest.fixture
def page_factory(qt_application: QApplication):
    created: list[RoleSelectionPage] = []

    def _factory(
        student: Student | None = None,
        teachers: tuple[Teacher, ...] = (),
    ) -> tuple[
        RoleSelectionPage, SqliteStudentRepository, SqliteActiveStudentRepository,
        SqliteTeacherRepository, SqliteActiveTeacherRepository,
    ]:
        student_repository = SqliteStudentRepository()
        active_student_repository = SqliteActiveStudentRepository()
        if student is not None:
            student_repository.create(student, UserRole.TEACHER)
        teacher_repository = SqliteTeacherRepository()
        active_teacher_repository = SqliteActiveTeacherRepository()
        for teacher in teachers:
            teacher_repository.create(teacher)
        page = RoleSelectionPage(
            student_repository=student_repository,
            active_student_repository=active_student_repository,
            teacher_repository=teacher_repository,
            active_teacher_repository=active_teacher_repository,
        )
        page.show()
        QTest.qWaitForWindowExposed(page)
        created.append(page)
        return (
            page, student_repository, active_student_repository,
            teacher_repository, active_teacher_repository,
        )

    yield _factory

    for page in created:
        page.hide()


# ---- Mode/login view switching --------------------------------------------


def test_both_mode_buttons_present(page_factory) -> None:
    page, _, _, _, _ = page_factory()

    assert page._student_button.text() == "Оқушы режимі"
    assert page._teacher_button.text() == "Мұғалім режимі"


def test_initial_state_shows_mode_view(page_factory) -> None:
    page, _, _, _, _ = page_factory()

    assert page._mode_view.isVisibleTo(page)
    assert not page._student_login_view.isVisibleTo(page)
    assert not page._teacher_login_view.isVisibleTo(page)


def test_student_button_switches_to_login_view_without_emitting_role(page_factory) -> None:
    page, _, _, _, _ = page_factory()
    received: list[UserRole] = []
    page.role_selected.connect(received.append)

    page._student_button.click()

    assert not page._mode_view.isVisibleTo(page)
    assert page._student_login_view.isVisibleTo(page)
    assert not page._teacher_login_view.isVisibleTo(page)
    assert received == []


def test_back_button_returns_to_mode_view(page_factory) -> None:
    page, _, _, _, _ = page_factory()
    page._student_button.click()

    page._login_back_button.click()

    assert page._mode_view.isVisibleTo(page)
    assert not page._student_login_view.isVisibleTo(page)


def test_on_enter_default_shows_mode_view(page_factory) -> None:
    page, _, _, _, _ = page_factory()
    page._student_button.click()

    page.on_enter()

    assert page._mode_view.isVisibleTo(page)


def test_on_enter_student_login_view_jumps_directly_to_login(page_factory) -> None:
    page, _, _, _, _ = page_factory()

    page.on_enter(view="student_login")

    assert not page._mode_view.isVisibleTo(page)
    assert page._student_login_view.isVisibleTo(page)


# ---- Focus-on-open ----------------------------------------------------------


def test_show_mode_selection_focuses_student_button(page_factory) -> None:
    page, _, _, _, _ = page_factory()
    page._student_button.click()  # move away first

    page.show_mode_selection()

    assert page._student_button.hasFocus()


def test_show_student_login_focuses_code_field(page_factory) -> None:
    page, _, _, _, _ = page_factory()

    page.show_student_login()

    assert page._code_edit.hasFocus()


# ---- Teacher login: full-page (no modal) -----------------------------------


def test_teacher_button_switches_to_teacher_login_view_without_emitting_role(page_factory) -> None:
    page, _, _, _, _ = page_factory()
    received: list[UserRole] = []
    page.role_selected.connect(received.append)

    page._teacher_button.click()

    assert not page._mode_view.isVisibleTo(page)
    assert page._teacher_login_view.isVisibleTo(page)
    assert not page._student_login_view.isVisibleTo(page)
    assert received == []


def test_teacher_button_does_not_create_pin_dialog(page_factory, qt_application: QApplication) -> None:
    page, _, _, _, _ = page_factory()

    page._teacher_button.click()

    assert not any(
        isinstance(widget, TeacherPinDialog) for widget in qt_application.topLevelWidgets()
    )


def test_teacher_login_back_button_returns_to_mode_view(page_factory) -> None:
    page, _, _, _, _ = page_factory()
    page._teacher_button.click()

    page._teacher_login_back_button.click()

    assert page._mode_view.isVisibleTo(page)
    assert not page._teacher_login_view.isVisibleTo(page)


def test_show_teacher_login_focuses_pin_field(page_factory) -> None:
    page, _, _, _, _ = page_factory()

    page.show_teacher_login()

    assert page._pin_edit.hasFocus()


def test_pin_field_uses_password_echo_mode(page_factory) -> None:
    page, _, _, _, _ = page_factory()

    assert page._pin_edit.echoMode() == QLineEdit.EchoMode.Password


def test_empty_pin_shows_validation(page_factory) -> None:
    page, _, _, _, _ = page_factory()
    page.show_teacher_login()

    page._on_teacher_login_clicked()

    assert page._pin_error_label.text() == "PIN кодын енгізіңіз"
    assert page._pin_error_label.isVisibleTo(page)


def test_wrong_pin_shows_inline_error_with_border_and_no_navigation(page_factory) -> None:
    page, _, _, _, _ = page_factory()
    page.show_teacher_login()
    page._pin_edit.setText("0000")
    received: list[UserRole] = []
    page.role_selected.connect(received.append)

    page._on_teacher_login_clicked()

    assert page._pin_error_label.text() == "PIN коды қате"
    assert page._pin_error_label.isVisibleTo(page)
    assert "border" in page._pin_edit.styleSheet()
    assert received == []
    assert page._teacher_login_view.isVisibleTo(page)  # бет ауыспаған


def test_typing_after_wrong_pin_clears_error(page_factory) -> None:
    page, _, _, _, _ = page_factory()
    page.show_teacher_login()
    page._pin_edit.setText("0000")
    page._on_teacher_login_clicked()

    page._pin_edit.setText("0001")
    page._on_pin_edited(page._pin_edit.text())

    assert not page._pin_error_label.isVisibleTo(page)


def test_correct_pin_emits_teacher_role(page_factory) -> None:
    page, _, _, _, _ = page_factory(teachers=(_make_teacher(),))
    page.show_teacher_login()
    page._pin_edit.setText(_DEV_PIN)
    received: list[UserRole] = []
    page.role_selected.connect(received.append)

    page._on_teacher_login_clicked()

    assert received == [UserRole.TEACHER]


def test_pin_not_belonging_to_any_teacher_is_rejected(page_factory) -> None:
    """§ Multi-Teacher Accounts: "do NOT hardcode a new teacher PIN" —
    login is resolved ONLY via ``ITeacherRepository``, never a fallback
    constant. A repository with one teacher must still reject a
    well-formed PIN nobody owns."""
    page, _, _, _, _ = page_factory(teachers=(_make_teacher(pin="482915"),))
    page.show_teacher_login()
    page._pin_edit.setText(_DEV_PIN)
    received: list[UserRole] = []
    page.role_selected.connect(received.append)

    page._on_teacher_login_clicked()

    assert received == []
    assert page._pin_error_label.text() == "PIN коды қате"


def test_correct_pin_clears_any_prior_error(page_factory) -> None:
    page, _, _, _, _ = page_factory(teachers=(_make_teacher(),))
    page.show_teacher_login()
    page._pin_edit.setText("0000")
    page._on_teacher_login_clicked()

    page._pin_edit.setText(_DEV_PIN)
    page._on_teacher_login_clicked()

    assert not page._pin_error_label.isVisibleTo(page)


def test_enter_key_submits_pin(page_factory) -> None:
    page, _, _, _, _ = page_factory(teachers=(_make_teacher(),))
    page.show_teacher_login()
    page._pin_edit.setText(_DEV_PIN)
    received: list[UserRole] = []
    page.role_selected.connect(received.append)

    QTest.keyClick(page._pin_edit, Qt.Key.Key_Return)

    assert received == [UserRole.TEACHER]


# ---- Multi-Teacher Accounts: session + multiple accounts --------------------


def test_valid_pin_sets_active_teacher_session(page_factory) -> None:
    page, _, _, _, active_teacher_repository = page_factory(teachers=(_make_teacher(teacher_id="ta"),))
    page.show_teacher_login()
    page._pin_edit.setText(_DEV_PIN)

    page._on_teacher_login_clicked()

    assert active_teacher_repository.get() == ActiveTeacherContext(teacher_id="ta")


def test_teacher_a_and_teacher_b_resolve_to_distinct_sessions(page_factory) -> None:
    teacher_a = _make_teacher(teacher_id="ta", full_name="Aidos Nurlanuly", pin="482915")
    teacher_b = _make_teacher(teacher_id="tb", full_name="Gulmira Serikkyzy", pin="731426")
    page, _, _, _, active_teacher_repository = page_factory(teachers=(teacher_a, teacher_b))

    page.show_teacher_login()
    page._pin_edit.setText("482915")
    page._on_teacher_login_clicked()
    assert active_teacher_repository.get() == ActiveTeacherContext(teacher_id="ta")

    page.show_teacher_login()
    page._pin_edit.setText("731426")
    page._on_teacher_login_clicked()
    assert active_teacher_repository.get() == ActiveTeacherContext(teacher_id="tb")


def test_inactive_teacher_pin_shows_generic_invalid_error(page_factory) -> None:
    """§12 "invalid login should simply show 'PIN коды қате'... do not
    say Teacher X exists but PIN is incorrect" — a disabled teacher's
    correct PIN must fail with the SAME generic message as a wrong PIN."""
    inactive_teacher = _make_teacher(pin="482915", is_active=False)
    page, _, _, _, active_teacher_repository = page_factory(teachers=(inactive_teacher,))
    page.show_teacher_login()
    page._pin_edit.setText("482915")
    received: list[UserRole] = []
    page.role_selected.connect(received.append)

    page._on_teacher_login_clicked()

    assert received == []
    assert page._pin_error_label.text() == "PIN коды қате"
    assert active_teacher_repository.get() is None


def test_showing_teacher_login_clears_previous_pin_and_error(page_factory) -> None:
    page, _, _, _, _ = page_factory()
    page.show_teacher_login()
    page._pin_edit.setText("0000")
    page._on_teacher_login_clicked()  # error шығады

    page.show_mode_selection()
    page.show_teacher_login()

    assert page._pin_edit.text() == ""
    assert not page._pin_error_label.isVisibleTo(page)


# ---- Student login validation ----------------------------------------------


def test_empty_code_shows_validation_without_repository_lookup(page_factory) -> None:
    student = _make_student()
    page, _, _, _, _ = page_factory(student)
    page.show_student_login()

    page._on_login_clicked()

    assert page._error_label.text() == "Кіру кодын енгізіңіз."
    assert page._error_label.isVisibleTo(page)


def test_invalid_code_shows_inline_error_with_border(page_factory) -> None:
    student = _make_student()
    page, _, _, _, _ = page_factory(student)
    page.show_student_login()
    page._code_edit.setText("999999")

    page._on_login_clicked()

    assert page._error_label.text() == "Кіру коды дұрыс емес."
    assert page._error_label.isVisibleTo(page)
    assert "border" in page._code_edit.styleSheet()


def test_invalid_code_does_not_clear_input(page_factory) -> None:
    student = _make_student()
    page, _, _, _, _ = page_factory(student)
    page.show_student_login()
    page._code_edit.setText("999999")

    page._on_login_clicked()

    assert page._code_edit.text() == "999999"


def test_typing_after_error_clears_error(page_factory) -> None:
    student = _make_student()
    page, _, _, _, _ = page_factory(student)
    page.show_student_login()
    page._code_edit.setText("999999")
    page._on_login_clicked()

    page._code_edit.setText("999998")
    page._on_code_edited(page._code_edit.text())

    assert not page._error_label.isVisibleTo(page)


def test_valid_code_resolves_correct_student_and_sets_active_student(page_factory) -> None:
    student = _make_student(code="482731")
    page, _, active_student_repository, _, _ = page_factory(student)
    page.show_student_login()
    page._code_edit.setText("482731")

    page._on_login_clicked()

    context = active_student_repository.get()
    assert context == ActiveStudentContext(classroom_id="c1", student_id="s1")


def test_valid_code_emits_student_login_succeeded(page_factory) -> None:
    student = _make_student(code="482731")
    page, _, _, _, _ = page_factory(student)
    page.show_student_login()
    page._code_edit.setText("482731")
    received: list[None] = []
    page.student_login_succeeded.connect(lambda: received.append(None))

    page._on_login_clicked()

    assert len(received) == 1


def test_valid_code_clears_any_prior_error(page_factory) -> None:
    student = _make_student(code="482731")
    page, _, _, _, _ = page_factory(student)
    page.show_student_login()
    page._code_edit.setText("999999")
    page._on_login_clicked()

    page._code_edit.setText("482731")
    page._on_login_clicked()

    assert not page._error_label.isVisibleTo(page)


def test_code_with_surrounding_whitespace_still_resolves(page_factory) -> None:
    student = _make_student(code="482731")
    page, _, active_student_repository, _, _ = page_factory(student)
    page.show_student_login()
    page._code_edit.setText("  482731  ")

    page._on_login_clicked()

    assert active_student_repository.get() == ActiveStudentContext(
        classroom_id="c1", student_id="s1"
    )


# ---- Enter key --------------------------------------------------------------


def test_enter_key_triggers_login_when_code_field_focused(page_factory) -> None:
    student = _make_student(code="482731")
    page, _, active_student_repository, _, _ = page_factory(student)
    page.show_student_login()
    page._code_edit.setText("482731")

    QTest.keyClick(page._code_edit, Qt.Key.Key_Return)

    assert active_student_repository.get() == ActiveStudentContext(
        classroom_id="c1", student_id="s1"
    )
