"""StudentSelectionPage юнит-тесттері: бос күй хабары, сынып/оқушы
dropdown сүзгісі, Жалғастыру белсенді оқушыны сақтайды, редакторлау
контролдары мүлде жоқ."""

import sys
from datetime import datetime, timezone

import pytest
from PySide6.QtWidgets import QApplication, QComboBox, QLineEdit, QPushButton, QWidget

from domain.entities.active_student_context import ActiveStudentContext
from domain.entities.classroom import Classroom
from domain.entities.student import Student
from domain.entities.user_role import UserRole
from infrastructure.storage.sqlite_active_student_repository import SqliteActiveStudentRepository
from infrastructure.storage.sqlite_classroom_repository import SqliteClassroomRepository
from infrastructure.storage.sqlite_student_repository import SqliteStudentRepository
from ui.pages.student_selection_page import StudentSelectionPage

_NOW = datetime.now(timezone.utc)


@pytest.fixture(scope="module", autouse=True)
def qt_application() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def _make_page(seed: bool = True) -> tuple[
    StudentSelectionPage, SqliteClassroomRepository, SqliteStudentRepository, SqliteActiveStudentRepository
]:
    classroom_repository = SqliteClassroomRepository()
    student_repository = SqliteStudentRepository()
    active_repository = SqliteActiveStudentRepository()

    if seed:
        classroom_repository.create(
            Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
        )
        classroom_repository.create(
            Classroom(id="c2", name="8Ә", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
        )
        student_repository.create(
            Student(id="s1", classroom_id="c1", first_name="Айдос", last_name="Серіков",
                    created_at=_NOW, updated_at=_NOW),
            UserRole.TEACHER,
        )
        student_repository.create(
            Student(id="s2", classroom_id="c2", first_name="Бекзат", last_name="Нұрлан",
                    created_at=_NOW, updated_at=_NOW),
            UserRole.TEACHER,
        )

    page = StudentSelectionPage(
        classroom_repository=classroom_repository,
        student_repository=student_repository,
        active_student_repository=active_repository,
    )
    return page, classroom_repository, student_repository, active_repository


def test_empty_state_shown_when_no_classrooms_exist() -> None:
    page, _classrooms, _students, _active = _make_page(seed=False)

    assert page._empty_state_label.isHidden() is False
    assert page._form_container.isHidden() is True
    assert "Оқушылар тізімі әлі жасалмаған" in page._empty_state_label.text()


def test_form_shown_when_classrooms_and_students_exist() -> None:
    page, _classrooms, _students, _active = _make_page()

    assert page._form_container.isHidden() is False
    assert page._empty_state_label.isHidden() is True


def test_student_combo_filters_by_selected_classroom() -> None:
    page, _classrooms, _students, _active = _make_page()

    index = page._classroom_combo.findData("c1")
    page._classroom_combo.setCurrentIndex(index)

    names = [page._student_combo.itemText(i) for i in range(page._student_combo.count())]
    assert names == ["Серіков Айдос"]


def test_continue_disabled_when_selected_classroom_has_no_students() -> None:
    """Екі сынып бар, бірақ біреуінде ешбір оқушы жоқ болса, СОЛ сыныпты
    таңдағанда Жалғастыру қосылмауы тиіс (§ empty selection guard)."""
    classroom_repository = SqliteClassroomRepository()
    student_repository = SqliteStudentRepository()
    active_repository = SqliteActiveStudentRepository()
    classroom_repository.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    classroom_repository.create(
        Classroom(id="c2", name="8Ә (оқушысыз)", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    student_repository.create(
        Student(id="s1", classroom_id="c1", first_name="Айдос", last_name="Серіков",
                created_at=_NOW, updated_at=_NOW),
        UserRole.TEACHER,
    )
    page = StudentSelectionPage(
        classroom_repository=classroom_repository,
        student_repository=student_repository,
        active_student_repository=active_repository,
    )

    index = page._classroom_combo.findData("c2")
    page._classroom_combo.setCurrentIndex(index)

    assert page._student_combo.count() == 0
    assert page._continue_button.isEnabled() is False


def test_continue_click_sets_active_student_and_emits_signal() -> None:
    page, _classrooms, _students, active_repository = _make_page()
    index = page._classroom_combo.findData("c1")
    page._classroom_combo.setCurrentIndex(index)

    signals: list[None] = []
    page.student_selected.connect(lambda: signals.append(None))
    page._continue_button.click()

    assert signals == [None]
    assert active_repository.get() == ActiveStudentContext(classroom_id="c1", student_id="s1")


def test_no_editing_controls_exist_on_page() -> None:
    """§ "Do not expose class/student editing controls in Student mode" —
    бетте hiçbir "қосу"/"өзгерту"/"мұрағаттау" батырмасы жоқ екенін
    растайды (тек екі combo + Жалғастыру)."""
    page, _classrooms, _students, _active = _make_page()

    buttons = page.findChildren(QPushButton)
    button_texts = {button.text() for button in buttons}

    assert button_texts == {"Жалғастыру"}


def test_on_enter_refreshes_lists() -> None:
    page, classroom_repository, student_repository, _active = _make_page(seed=False)
    assert page._empty_state_label.isHidden() is False

    classroom_repository.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    student_repository.create(
        Student(id="s1", classroom_id="c1", first_name="Айдос", last_name="Серіков",
                created_at=_NOW, updated_at=_NOW),
        UserRole.TEACHER,
    )
    page.on_enter()

    assert page._form_container.isHidden() is False
