"""Sidebar — Phase 39B белсенді оқушы индикаторы/ауыстыру батырмасы
тесттері (Sidebar-дың негізгі нав/collapse тестері test_sidebar.py-де)."""

import sys

import pytest
from PySide6.QtWidgets import QApplication

from domain.entities.user_role import UserRole
from ui.widgets.sidebar import Sidebar


@pytest.fixture(scope="module", autouse=True)
def qt_application() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_student_section_hidden_for_teacher_role() -> None:
    sidebar = Sidebar(role=UserRole.TEACHER)
    assert sidebar._switch_student_button.isHidden() is True


def test_student_section_visible_for_student_role() -> None:
    sidebar = Sidebar(role=UserRole.STUDENT)
    assert sidebar._switch_student_button.isHidden() is False


def test_set_role_shows_student_section_when_switching_to_student() -> None:
    sidebar = Sidebar(role=UserRole.TEACHER)
    sidebar.set_role(UserRole.STUDENT)
    assert sidebar._switch_student_button.isHidden() is False


def test_set_role_hides_student_section_when_switching_to_teacher() -> None:
    sidebar = Sidebar(role=UserRole.STUDENT)
    sidebar.set_role(UserRole.TEACHER)
    assert sidebar._switch_student_button.isHidden() is True


def test_set_active_student_text_updates_label() -> None:
    sidebar = Sidebar(role=UserRole.STUDENT)
    sidebar.set_active_student_text("Оқушы: Айдос С.\nСынып: 8А")
    assert sidebar._active_student_label.text() == "Оқушы: Айдос С.\nСынып: 8А"


def test_set_active_student_text_none_clears_label() -> None:
    sidebar = Sidebar(role=UserRole.STUDENT)
    sidebar.set_active_student_text("Оқушы: Айдос С.")
    sidebar.set_active_student_text(None)
    assert sidebar._active_student_label.text() == ""


def test_switch_student_requested_emitted_on_click() -> None:
    sidebar = Sidebar(role=UserRole.STUDENT)
    signals: list[None] = []
    sidebar.switch_student_requested.connect(lambda: signals.append(None))

    sidebar._switch_student_button.click()

    assert signals == [None]


def test_set_switch_student_enabled_toggles_button() -> None:
    sidebar = Sidebar(role=UserRole.STUDENT)
    sidebar.set_switch_student_enabled(False)
    assert sidebar._switch_student_button.isEnabled() is False

    sidebar.set_switch_student_enabled(True)
    assert sidebar._switch_student_button.isEnabled() is True
