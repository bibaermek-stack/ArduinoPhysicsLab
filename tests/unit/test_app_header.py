"""Үстіңгі AppHeader chrome жолағы."""

import sys

import pytest
from PySide6.QtWidgets import QApplication

from domain.entities.user_role import UserRole
from modules.electricity.experiments_config import OHMS_LAW_EXPERIMENT
from ui.widgets.app_header import AppHeader, header_visible_for_route, title_for_route
from tests.unit.test_main_window import _make_window


@pytest.fixture(scope="module", autouse=True)
def qt_application() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_title_for_known_routes() -> None:
    assert title_for_route("dashboard") == "Бақылау тақтасы"
    assert title_for_route("settings") == "Баптаулар"
    assert title_for_route("about") == "Анықтама"
    assert title_for_route("experiment_list") == "Зертханалық жұмыстар"
    assert title_for_route("data_journal") == "Деректер журналы"


def test_header_hidden_on_lab_and_login_routes() -> None:
    assert header_visible_for_route("role_selection") is False
    assert header_visible_for_route("experiment_workspace") is False
    assert header_visible_for_route("dashboard") is True


def test_app_header_sets_title_and_user() -> None:
    header = AppHeader()
    header.set_title("Баптаулар")
    header.set_user("Айдос Нұрланұлы", "Мұғалім")
    assert header._title_label.text() == "Баптаулар"
    assert header._user_label.text() == "Айдос Нұрланұлы"
    assert header._role_chip.text() == "Мұғалім"
    assert header._role_chip.isVisibleTo(header)


def test_main_window_header_shows_dashboard_title() -> None:
    window, _home, _list, _workspace = _make_window()
    assert window._app_header.isVisibleTo(window)
    assert window._app_header._title_label.text() == "Бақылау тақтасы"
    assert window._app_header._role_chip.text() == "Мұғалім"


def test_main_window_header_hidden_on_experiment_workspace() -> None:
    window, _home, _list, _workspace = _make_window()
    window._router.navigate("experiment_workspace", experiment=OHMS_LAW_EXPERIMENT)
    assert window._app_header.isHidden()


def test_main_window_header_updates_on_settings_navigation() -> None:
    window, _home, _list, _workspace = _make_window()
    window._router.navigate("settings")
    assert window._app_header.isVisibleTo(window)
    assert window._app_header._title_label.text() == "Баптаулар"


def test_student_header_uses_student_role_chip() -> None:
    window, _home, _list, _workspace = _make_window(initial_role=UserRole.STUDENT)
    assert window._app_header._role_chip.text() == "Оқушы"
    assert window._app_header._title_label.text() == "Басты бет"
