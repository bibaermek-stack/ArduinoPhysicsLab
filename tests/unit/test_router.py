"""Router үшін юнит-тесттер."""

import sys

import pytest
from PySide6.QtWidgets import QApplication, QStackedWidget, QWidget

from ui.navigation.router import Router


@pytest.fixture(scope="module", autouse=True)
def qt_application() -> QApplication:
    """QWidget-тер үшін жалғыз QApplication дана."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


class _RecordingPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.on_enter_calls: list[dict[str, object]] = []

    def on_enter(self, **params: object) -> None:
        self.on_enter_calls.append(params)


def test_register_adds_page_to_stack() -> None:
    stack = QStackedWidget()
    router = Router(stack)
    page = QWidget()

    router.register("home", page)

    assert stack.indexOf(page) != -1


def test_register_duplicate_name_raises() -> None:
    stack = QStackedWidget()
    router = Router(stack)
    router.register("home", QWidget())

    with pytest.raises(ValueError):
        router.register("home", QWidget())


def test_navigate_switches_current_widget() -> None:
    stack = QStackedWidget()
    router = Router(stack)
    home = QWidget()
    other = QWidget()
    router.register("home", home)
    router.register("other", other)

    router.navigate("other")

    assert stack.currentWidget() is other


def test_navigate_calls_on_enter_with_params() -> None:
    stack = QStackedWidget()
    router = Router(stack)
    page = _RecordingPage()
    router.register("page", page)

    router.navigate("page", experiment="ohms-law")

    assert page.on_enter_calls == [{"experiment": "ohms-law"}]


def test_navigate_without_on_enter_does_not_crash() -> None:
    stack = QStackedWidget()
    router = Router(stack)
    page = QWidget()
    router.register("plain", page)

    router.navigate("plain")

    assert stack.currentWidget() is page


# =====================================================================
# Phase 37A: optional role-based navigation guard
# =====================================================================


def test_navigate_returns_true_on_success_without_guard() -> None:
    stack = QStackedWidget()
    router = Router(stack)
    page = QWidget()
    router.register("home", page)

    assert router.navigate("home") is True


def test_guard_none_by_default_is_fully_unrestricted() -> None:
    stack = QStackedWidget()
    router = Router(stack)  # is_route_allowed omitted
    page = QWidget()
    router.register("anything", page)

    assert router.navigate("anything") is True
    assert stack.currentWidget() is page


def test_guard_rejects_disallowed_route_and_keeps_current_widget() -> None:
    stack = QStackedWidget()
    router = Router(stack, is_route_allowed=lambda name: name != "devices")
    home = QWidget()
    devices = QWidget()
    router.register("home", home)
    router.register("devices", devices)
    router.navigate("home")

    result = router.navigate("devices")

    assert result is False
    assert stack.currentWidget() is home


def test_guard_allows_permitted_route() -> None:
    stack = QStackedWidget()
    router = Router(stack, is_route_allowed=lambda name: name != "devices")
    home = QWidget()
    router.register("home", home)

    assert router.navigate("home") is True
    assert stack.currentWidget() is home


def test_guard_rejected_route_does_not_call_on_enter() -> None:
    stack = QStackedWidget()
    router = Router(stack, is_route_allowed=lambda name: False)
    page = _RecordingPage()
    router.register("page", page)

    router.navigate("page", experiment="ohms-law")

    assert page.on_enter_calls == []


# =====================================================================
# Phase 41: route_changed signal (WorkspaceBackdrop hook)
# =====================================================================


def test_route_changed_emits_route_name_on_successful_navigate() -> None:
    stack = QStackedWidget()
    router = Router(stack)
    router.register("home", QWidget())
    router.register("devices", QWidget())
    seen: list[str] = []
    router.route_changed.connect(seen.append)

    router.navigate("home")
    router.navigate("devices")

    assert seen == ["home", "devices"]


def test_route_changed_not_emitted_when_guard_rejects() -> None:
    stack = QStackedWidget()
    router = Router(stack, is_route_allowed=lambda name: name != "devices")
    router.register("home", QWidget())
    router.register("devices", QWidget())
    seen: list[str] = []
    router.route_changed.connect(seen.append)

    router.navigate("home")
    result = router.navigate("devices")

    assert result is False
    assert seen == ["home"]
