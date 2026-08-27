"""TeacherPinDialog — юнит-тесттері (Phase 37A)."""

import sys

import pytest
from PySide6.QtWidgets import QApplication, QDialog

from domain.services.teacher_pin import hash_pin
from ui.widgets.teacher_pin_dialog import TeacherPinDialog


@pytest.fixture(scope="module", autouse=True)
def qt_application() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def _dialog(expected_pin: str = "4321") -> TeacherPinDialog:
    return TeacherPinDialog(expected_pin_hash=hash_pin(expected_pin))


def test_wrong_pin_shows_error_and_does_not_accept() -> None:
    dialog = _dialog(expected_pin="4321")
    dialog._pin_edit.setText("0000")

    dialog._on_confirm_clicked()

    assert dialog._error_label.isHidden() is False
    assert dialog._error_label.text() != ""
    assert dialog.result() != QDialog.DialogCode.Accepted


def test_wrong_pin_clears_the_input_field() -> None:
    dialog = _dialog(expected_pin="4321")
    dialog._pin_edit.setText("0000")

    dialog._on_confirm_clicked()

    assert dialog._pin_edit.text() == ""


def test_correct_pin_accepts_dialog() -> None:
    dialog = _dialog(expected_pin="4321")
    dialog._pin_edit.setText("4321")

    dialog._on_confirm_clicked()

    assert dialog.result() == QDialog.DialogCode.Accepted


def test_error_label_hidden_before_any_attempt() -> None:
    dialog = _dialog()

    assert dialog._error_label.isHidden() is True


def test_cancel_button_rejects_dialog() -> None:
    dialog = _dialog()

    dialog._cancel_button.click()

    assert dialog.result() == QDialog.DialogCode.Rejected


def test_return_pressed_confirms_like_button_click() -> None:
    dialog = _dialog(expected_pin="4321")
    dialog._pin_edit.setText("4321")

    dialog._pin_edit.returnPressed.emit()

    assert dialog.result() == QDialog.DialogCode.Accepted


def test_uses_configured_default_when_no_explicit_hash_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("APL_TEACHER_PIN", raising=False)
    dialog = TeacherPinDialog()
    dialog._pin_edit.setText("1234")

    dialog._on_confirm_clicked()

    assert dialog.result() == QDialog.DialogCode.Accepted
