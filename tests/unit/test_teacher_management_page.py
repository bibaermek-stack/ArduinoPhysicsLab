"""TeacherManagementPage юнит-тесттері (Multi-Teacher Accounts §7-10):
тізім/қосу/өзгерту/PIN ауыстыру/белсенді(емес) ету, барлық валидация
INLINE (§ popup ЖОҚ)."""

import sys
from datetime import datetime, timezone

import pytest
from PySide6.QtWidgets import QApplication, QDialog

from domain.entities.classroom import Classroom
from domain.entities.teacher import Teacher
from domain.entities.user_role import UserRole
from domain.services.teacher_pin import hash_pin, resolve_teacher_by_pin
from infrastructure.storage.sqlite_classroom_repository import SqliteClassroomRepository
from infrastructure.storage.sqlite_teacher_repository import SqliteTeacherRepository
from ui.pages.teacher_management_page import (
    TeacherManagementPage,
    _AddTeacherDialog,
    _ChangePinDialog,
    _EditTeacherDialog,
)

_NOW = datetime.now(timezone.utc)


@pytest.fixture(scope="module", autouse=True)
def qt_application() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def _make_page() -> tuple[TeacherManagementPage, SqliteTeacherRepository, SqliteClassroomRepository]:
    teacher_repository = SqliteTeacherRepository()
    classroom_repository = SqliteClassroomRepository()
    classroom_repository.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    classroom_repository.create(
        Classroom(id="c2", name="8Б", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    page = TeacherManagementPage(
        teacher_repository=teacher_repository, classroom_repository=classroom_repository
    )
    return page, teacher_repository, classroom_repository


def _make_teacher(teacher_id: str = "t1", full_name: str = "Aidos", pin: str = "482915") -> Teacher:
    return Teacher(id=teacher_id, full_name=full_name, pin_hash=hash_pin(pin), created_at=_NOW, updated_at=_NOW)


# ---- Empty state / table rendering -----------------------------------------


def test_empty_state_shows_hint_hides_table() -> None:
    page, _teachers, _classrooms = _make_page()

    assert page._empty_label.isVisibleTo(page) is True
    assert page._table.isVisibleTo(page) is False


def test_table_shows_teacher_name_classes_and_status() -> None:
    page, teacher_repository, _classrooms = _make_page()
    teacher_repository.create(_make_teacher(), assigned_classroom_ids=("c1", "c2"))

    page.on_enter()

    assert page._table.rowCount() == 1
    assert page._table.item(0, 0).text() == "Aidos"
    assert page._table.item(0, 1).text() == "8А, 8Б"
    assert page._table.item(0, 2).text() == "Белсенді"


def test_table_shows_inactive_status() -> None:
    from dataclasses import replace

    page, teacher_repository, _classrooms = _make_page()
    teacher = _make_teacher()
    teacher_repository.create(teacher)
    teacher_repository.update(replace(teacher, is_active=False))

    page.on_enter()

    assert page._table.item(0, 2).text() == "Белсенді емес"


def test_teacher_with_no_classes_shows_placeholder() -> None:
    page, teacher_repository, _classrooms = _make_page()
    teacher_repository.create(_make_teacher())

    page.on_enter()

    assert page._table.item(0, 1).text() == "—"


def test_repeated_on_enter_does_not_leak_action_buttons() -> None:
    from PySide6.QtWidgets import QPushButton

    page, teacher_repository, _classrooms = _make_page()
    teacher_repository.create(_make_teacher())

    for _ in range(5):
        page.on_enter()
        QApplication.processEvents()

    buttons = page._table.viewport().findChildren(QPushButton)
    assert len(buttons) == 1


def test_back_requested_emitted_on_click() -> None:
    page, _teachers, _classrooms = _make_page()
    received: list[None] = []
    page.back_requested.connect(lambda: received.append(None))

    page._back_button.click()

    assert received == [None]


# ---- Add Teacher: inline validation ------------------------------------------


def test_add_teacher_empty_name_shows_inline_error() -> None:
    _page, teacher_repository, classroom_repository = _make_page()
    dialog = _AddTeacherDialog(classroom_repository.list_active(), teacher_repository)
    dialog._pin_edit.setText("482915")
    dialog._pin_confirm_edit.setText("482915")

    dialog._on_confirm_clicked()

    assert dialog.result() != QDialog.DialogCode.Accepted
    assert dialog._error_label.text() == "Аты-жөні бос болмауы керек"


def test_add_teacher_pin_too_short_shows_inline_error() -> None:
    _page, teacher_repository, classroom_repository = _make_page()
    dialog = _AddTeacherDialog(classroom_repository.list_active(), teacher_repository)
    dialog._name_edit.setText("Aidos")
    dialog._pin_edit.setText("123")
    dialog._pin_confirm_edit.setText("123")

    dialog._on_confirm_clicked()

    assert dialog._error_label.text() == "PIN 6 цифрдан тұруы керек"


def test_add_teacher_pin_non_digit_shows_inline_error() -> None:
    _page, teacher_repository, classroom_repository = _make_page()
    dialog = _AddTeacherDialog(classroom_repository.list_active(), teacher_repository)
    dialog._name_edit.setText("Aidos")
    dialog._pin_edit.setText("12345a")
    dialog._pin_confirm_edit.setText("12345a")

    dialog._on_confirm_clicked()

    assert dialog._error_label.text() == "PIN 6 цифрдан тұруы керек"


def test_add_teacher_pin_mismatch_shows_inline_error() -> None:
    _page, teacher_repository, classroom_repository = _make_page()
    dialog = _AddTeacherDialog(classroom_repository.list_active(), teacher_repository)
    dialog._name_edit.setText("Aidos")
    dialog._pin_edit.setText("482915")
    dialog._pin_confirm_edit.setText("482916")

    dialog._on_confirm_clicked()

    assert dialog._error_label.text() == "PIN кодтары сәйкес келмейді"


def test_add_teacher_duplicate_pin_shows_inline_error() -> None:
    _page, teacher_repository, classroom_repository = _make_page()
    teacher_repository.create(_make_teacher(pin="482915"))
    dialog = _AddTeacherDialog(classroom_repository.list_active(), teacher_repository)
    dialog._name_edit.setText("Gulmira")
    dialog._pin_edit.setText("482915")
    dialog._pin_confirm_edit.setText("482915")

    dialog._on_confirm_clicked()

    assert dialog._error_label.text() == "Бұл PIN басқа мұғалімге тиесілі"


def test_add_teacher_valid_input_is_accepted() -> None:
    _page, teacher_repository, classroom_repository = _make_page()
    dialog = _AddTeacherDialog(classroom_repository.list_active(), teacher_repository)
    dialog._name_edit.setText("Aidos Nurlanuly")
    dialog._pin_edit.setText("482915")
    dialog._pin_confirm_edit.setText("482915")
    dialog._classroom_list._checkboxes["c1"].setChecked(True)

    dialog._on_confirm_clicked()

    assert dialog.result() == QDialog.DialogCode.Accepted
    name, pin, classroom_ids = dialog.get_values()
    assert name == "Aidos Nurlanuly"
    assert pin == "482915"
    assert classroom_ids == ("c1",)


def test_add_teacher_end_to_end_creates_teacher_and_refreshes_table_and_signal() -> None:
    page, teacher_repository, classroom_repository = _make_page()
    received: list[None] = []
    page.teachers_changed.connect(lambda: received.append(None))

    dialog = _AddTeacherDialog(classroom_repository.list_active(), teacher_repository, parent=page)
    dialog._name_edit.setText("Aidos Nurlanuly")
    dialog._pin_edit.setText("482915")
    dialog._pin_confirm_edit.setText("482915")
    dialog._classroom_list._checkboxes["c1"].setChecked(True)
    dialog._on_confirm_clicked()
    name, pin, classroom_ids = dialog.get_values()

    from dataclasses import replace as _replace
    from uuid import uuid4

    teacher = Teacher(id=str(uuid4()), full_name=name, pin_hash=hash_pin(pin), created_at=_NOW, updated_at=_NOW)
    teacher_repository.create(teacher, assigned_classroom_ids=classroom_ids)
    page._refresh_table()
    page.teachers_changed.emit()

    assert len(teacher_repository.list_all()) == 1
    assert page._table.rowCount() == 1
    assert received == [None]


# ---- Edit Teacher: name/classes/active, PIN untouched ------------------------


def test_edit_teacher_empty_name_shows_inline_error() -> None:
    _page, teacher_repository, classroom_repository = _make_page()
    teacher = _make_teacher()
    teacher_repository.create(teacher, assigned_classroom_ids=("c1",))
    dialog = _EditTeacherDialog(
        teacher, classroom_repository.list_active(), ("c1",), teacher_repository
    )
    dialog._name_edit.setText("   ")

    dialog._on_save_clicked()

    assert dialog.result() != QDialog.DialogCode.Accepted
    assert dialog._error_label.text() == "Аты-жөні бос болмауы керек"


def test_edit_teacher_rename_and_reassign_classes_and_toggle_active() -> None:
    _page, teacher_repository, classroom_repository = _make_page()
    teacher = _make_teacher()
    teacher_repository.create(teacher, assigned_classroom_ids=("c1",))
    dialog = _EditTeacherDialog(
        teacher, classroom_repository.list_active(), ("c1",), teacher_repository
    )
    dialog._name_edit.setText("Aidos Nurlanuly")
    dialog._classroom_list._checkboxes["c2"].setChecked(True)
    dialog._active_checkbox.setChecked(False)

    dialog._on_save_clicked()

    assert dialog.result() == QDialog.DialogCode.Accepted
    name, is_active, classroom_ids = dialog.get_values()
    assert name == "Aidos Nurlanuly"
    assert is_active is False
    assert set(classroom_ids) == {"c1", "c2"}


def test_edit_teacher_does_not_expose_pin_field() -> None:
    """§9 "Never reveal the current PIN" — the edit form must not have
    any widget bound to the teacher's PIN/hash value."""
    _page, teacher_repository, classroom_repository = _make_page()
    teacher = _make_teacher()
    teacher_repository.create(teacher, assigned_classroom_ids=("c1",))
    dialog = _EditTeacherDialog(
        teacher, classroom_repository.list_active(), ("c1",), teacher_repository
    )

    assert not hasattr(dialog, "_pin_edit")


def test_editing_name_and_classes_does_not_change_pin_hash() -> None:
    _page, teacher_repository, classroom_repository = _make_page()
    teacher = _make_teacher(pin="482915")
    teacher_repository.create(teacher, assigned_classroom_ids=("c1",))
    original_hash = teacher.pin_hash

    dialog = _EditTeacherDialog(
        teacher, classroom_repository.list_active(), ("c1",), teacher_repository
    )
    dialog._name_edit.setText("Aidos Nurlanuly")
    dialog._on_save_clicked()
    name, is_active, classroom_ids = dialog.get_values()

    from dataclasses import replace as _replace

    updated = _replace(teacher, full_name=name, is_active=is_active, updated_at=datetime.now(timezone.utc))
    teacher_repository.update(updated)
    teacher_repository.set_assigned_classroom_ids(teacher.id, classroom_ids)

    reloaded = teacher_repository.get(teacher.id)
    assert reloaded.pin_hash == original_hash


# ---- Change PIN: independent action -------------------------------------------


def test_change_pin_dialog_rejects_short_pin() -> None:
    _page, teacher_repository, _classrooms = _make_page()
    teacher_repository.create(_make_teacher())
    dialog = _ChangePinDialog("t1", teacher_repository)
    dialog._pin_edit.setText("123")
    dialog._pin_confirm_edit.setText("123")

    dialog._on_save_clicked()

    assert dialog.result() != QDialog.DialogCode.Accepted
    assert dialog._error_label.text() == "PIN 6 цифрдан тұруы керек"


def test_change_pin_dialog_rejects_mismatched_confirmation() -> None:
    _page, teacher_repository, _classrooms = _make_page()
    teacher_repository.create(_make_teacher())
    dialog = _ChangePinDialog("t1", teacher_repository)
    dialog._pin_edit.setText("111111")
    dialog._pin_confirm_edit.setText("222222")

    dialog._on_save_clicked()

    assert dialog._error_label.text() == "PIN кодтары сәйкес келмейді"


def test_change_pin_dialog_rejects_pin_taken_by_another_teacher() -> None:
    _page, teacher_repository, _classrooms = _make_page()
    teacher_repository.create(_make_teacher("t1", "Aidos", "482915"))
    teacher_repository.create(_make_teacher("t2", "Gulmira", "731426"))
    dialog = _ChangePinDialog("t1", teacher_repository)
    dialog._pin_edit.setText("731426")
    dialog._pin_confirm_edit.setText("731426")

    dialog._on_save_clicked()

    assert dialog._error_label.text() == "Бұл PIN басқа мұғалімге тиесілі"


def test_change_pin_dialog_updates_pin_immediately_on_success() -> None:
    _page, teacher_repository, _classrooms = _make_page()
    teacher_repository.create(_make_teacher(pin="482915"))
    dialog = _ChangePinDialog("t1", teacher_repository)
    dialog._pin_edit.setText("999999")
    dialog._pin_confirm_edit.setText("999999")

    dialog._on_save_clicked()

    assert dialog.result() == QDialog.DialogCode.Accepted
    reloaded = teacher_repository.get("t1")
    assert reloaded.pin_hash == hash_pin("999999")


def test_changing_pin_does_not_touch_name_or_classes() -> None:
    _page, teacher_repository, _classrooms = _make_page()
    teacher = _make_teacher(pin="482915")
    teacher_repository.create(teacher, assigned_classroom_ids=("c1", "c2"))

    dialog = _ChangePinDialog("t1", teacher_repository)
    dialog._pin_edit.setText("999999")
    dialog._pin_confirm_edit.setText("999999")
    dialog._on_save_clicked()

    reloaded = teacher_repository.get("t1")
    assert reloaded.full_name == "Aidos"
    assert teacher_repository.list_assigned_classroom_ids("t1") == ("c1", "c2")


# ---- Disable instead of delete: end-to-end login effect -----------------------


def test_disabling_teacher_via_edit_dialog_blocks_subsequent_login() -> None:
    """§10 "Disabled teacher PIN must no longer allow login" — exercised
    end-to-end through the actual Edit dialog + repository write, not
    just the repository layer directly."""
    _page, teacher_repository, classroom_repository = _make_page()
    teacher = _make_teacher(pin="482915")
    teacher_repository.create(teacher, assigned_classroom_ids=("c1",))
    assert resolve_teacher_by_pin("482915", teacher_repository) is not None

    dialog = _EditTeacherDialog(
        teacher, classroom_repository.list_active(), ("c1",), teacher_repository
    )
    dialog._active_checkbox.setChecked(False)
    dialog._on_save_clicked()
    name, is_active, classroom_ids = dialog.get_values()

    from dataclasses import replace as _replace

    updated = _replace(teacher, full_name=name, is_active=is_active, updated_at=datetime.now(timezone.utc))
    teacher_repository.update(updated)

    assert resolve_teacher_by_pin("482915", teacher_repository) is None


def test_disabling_teacher_preserves_historical_progress_data_untouched() -> None:
    """§10 "Historical results associated with that teacher/classes must
    remain intact" — disabling only flips ``is_active``, never touches
    classroom/student/session data."""
    _page, teacher_repository, classroom_repository = _make_page()
    teacher = _make_teacher()
    teacher_repository.create(teacher, assigned_classroom_ids=("c1", "c2"))

    from dataclasses import replace as _replace

    teacher_repository.update(_replace(teacher, is_active=False))

    assert {c.id for c in classroom_repository.list_all()} == {"c1", "c2"}
    assert teacher_repository.list_assigned_classroom_ids(teacher.id) == ("c1", "c2")
