"""Ашық/қараңғы тема палитрасы мен live QSS apply."""

import sys

import pytest
from PySide6.QtWidgets import QApplication

from ui.themes.theme_manager import (
    THEME_DARK,
    THEME_LIGHT,
    ThemeManager,
    apply_application_theme,
    current_theme,
    set_theme,
    theme_color,
)


@pytest.fixture(scope="module", autouse=True)
def qt_application() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture(autouse=True)
def restore_dark_theme() -> None:
    yield
    apply_application_theme(THEME_DARK)


def test_light_palette_uses_light_background() -> None:
    set_theme(THEME_LIGHT)
    assert current_theme() == THEME_LIGHT
    assert theme_color("COLOR_BACKGROUND") == "#EEF1F6"
    assert theme_color("COLOR_TEXT_PRIMARY") == "#111827"
    sheet = ThemeManager().build_stylesheet()
    assert "#EEF1F6" in sheet
    assert "#111827" in sheet


def test_dark_palette_uses_dark_background() -> None:
    set_theme(THEME_DARK)
    assert current_theme() == THEME_DARK
    assert theme_color("COLOR_BACKGROUND") == "#1C1C1E"
    sheet = ThemeManager().build_stylesheet()
    assert "#1C1C1E" in sheet


def test_apply_application_theme_sets_app_stylesheet(qt_application: QApplication) -> None:
    apply_application_theme(THEME_LIGHT)
    sheet = qt_application.styleSheet()
    assert "#EEF1F6" in sheet
    apply_application_theme(THEME_DARK)
    sheet = qt_application.styleSheet()
    assert "#1C1C1E" in sheet
