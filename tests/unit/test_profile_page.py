"""ProfilePage: шығу батырмасы сессияны тазалайды."""

from __future__ import annotations

import os
import sys
import tempfile

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QPushButton

from infrastructure.storage.app_preferences import AppPreferences
from ui.pages.profile_page import ProfilePage


@pytest.fixture(scope="module", autouse=True)
def qt_application() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def preferences() -> AppPreferences:
    handle = tempfile.NamedTemporaryFile(suffix=".ini", delete=False)
    handle.close()
    settings = QSettings(handle.name, QSettings.Format.IniFormat)
    yield AppPreferences(settings)
    os.unlink(handle.name)


def test_logout_button_clears_session_and_emits(preferences: AppPreferences) -> None:
    preferences.set_account_session(
        token="tok",
        account_id="acc-1",
        email="a@school.kz",
        display_name="Айгерім",
        role="teacher",
        public_id="T-01",
    )
    page = ProfilePage(preferences=preferences)
    received: list[None] = []
    page.logout_requested.connect(lambda: received.append(None))

    button = next(b for b in page.findChildren(QPushButton) if b.text() == "Шығу")
    button.click()

    assert received == [None]
    assert preferences.get_account_token() == ""
    assert preferences.get_account_email() == ""
    assert [item["email"] for item in preferences.list_saved_accounts()] == ["a@school.kz"]
    page.hide()


class _FakeMeClient:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def me(self) -> dict:
        return self._payload


def test_independent_student_sees_connect_button(preferences: AppPreferences) -> None:
    page = ProfilePage(preferences=preferences)
    page._client = _FakeMeClient(
        {
            "public_id": "S-AAAAAA",
            "role": "student",
            "display_name": "Оқушы",
            "link_status": "independent",
            "teacher": None,
        }
    )
    page.on_enter()
    assert "Дербес режим" in page._link_label.text()
    assert page._connect_btn.isHidden() is False
    page.hide()


def test_pending_student_hides_connect_button(preferences: AppPreferences) -> None:
    page = ProfilePage(preferences=preferences)
    page._client = _FakeMeClient(
        {
            "public_id": "S-CCCCCC",
            "role": "student",
            "display_name": "Оқушы",
            "link_status": "pending",
            "teacher": {"public_id": "T-LAB102", "display_name": "Ахметов А."},
        }
    )
    page.on_enter()
    assert "Қабылдау күтілуде" in page._link_label.text()
    assert page._connect_btn.isHidden() is True
    page.hide()


def test_linked_student_hides_connect_button(preferences: AppPreferences) -> None:
    page = ProfilePage(preferences=preferences)
    page._client = _FakeMeClient(
        {
            "public_id": "S-BBBBBB",
            "role": "student",
            "display_name": "Оқушы",
            "link_status": "active",
            "teacher": {"public_id": "T-LAB102", "display_name": "Ахметов А."},
        }
    )
    page.on_enter()
    assert "Ахметов А." in page._link_label.text()
    assert page._connect_btn.isHidden() is True
    page.hide()
