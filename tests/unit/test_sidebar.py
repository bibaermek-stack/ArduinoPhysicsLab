"""Sidebar — global collapsible навигация панелінің юнит-тесттері.

Phase 37A: Sidebar ЕНДІ рөлге тәуелді (``ui.navigation.navigation_config.
NAVIGATION_ITEMS`` кестесінен сүзгіленген). Әдепкі ``role=UserRole.TEACHER``
(ескі, "барлығы қолжетімді" мінез-құлықты сақтайтын үлкейтілген рөл) —
ескі тесттердің көбі осы себепті өзгеріссіз қалады, тек "home"/
"reports"/"graphs"-қа тәуелді бірнешеуі ЖАҢА рөл моделіне сай жаңартылды.
"""

import sys
from datetime import datetime, timezone

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from domain.entities.connected_device import ConnectedDevice
from domain.entities.user_role import UserRole
from ui.widgets.sidebar import Sidebar


@pytest.fixture(scope="module", autouse=True)
def qt_application() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


class FakeDeviceManager(QObject):
    """``DeviceManager``-дің Sidebar қолданатын беті ғана қайталанатын
    жеңіл тест double-ы — нақты serial port ашылмайды.
    """

    device_identified = Signal(object)
    port_disconnected = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._devices: list[ConnectedDevice] = []

    def add_device(self, device: ConnectedDevice) -> None:
        self._devices.append(device)
        self.device_identified.emit(device)

    def remove_last(self, port_name: str) -> None:
        if self._devices:
            self._devices.pop()
        self.port_disconnected.emit(port_name)

    def get_connected_devices(self) -> tuple[ConnectedDevice, ...]:
        return tuple(self._devices)


def _make_device(port_name: str = "COM6") -> ConnectedDevice:
    return ConnectedDevice(
        device_id="APL-VOLTAGE-01",
        model="V1",
        sensor_type="VOLTAGE",
        firmware_version="1.0",
        chip="INA226",
        serial_number=None,
        hardware_version=None,
        port_name=port_name,
        connected_at=datetime.now(timezone.utc),
        warnings=(),
    )


def test_default_state_is_expanded() -> None:
    sidebar = Sidebar()

    assert sidebar.is_collapsed() is False
    assert sidebar.width() > 100


def test_collapse_button_toggles_width() -> None:
    sidebar = Sidebar()
    expanded_width = sidebar.width()

    sidebar.collapse_button.click()

    assert sidebar.is_collapsed() is True
    assert sidebar.width() < expanded_width

    sidebar.collapse_button.click()

    assert sidebar.is_collapsed() is False
    assert sidebar.width() == expanded_width


def test_collapse_toggled_signal_emits_new_state() -> None:
    sidebar = Sidebar()
    seen: list[bool] = []
    sidebar.collapse_toggled.connect(seen.append)

    sidebar.collapse_button.click()
    sidebar.collapse_button.click()

    assert seen == [True, False]


def test_expanded_state_allows_draggable_width_range() -> None:
    """Phase 41: жайылған күйде ЕНДІ setFixedWidth ЕМЕС — QSplitter drag
    handle-ге мағына беру үшін [min, max] аралығы орнатылады."""
    sidebar = Sidebar()

    assert sidebar.minimumWidth() < sidebar.maximumWidth()
    assert sidebar.maximumWidth() < 16777215  # Qt-дың "шексіз" QWIDGETSIZE_MAX мәні емес


def test_collapsed_state_is_fixed_width() -> None:
    sidebar = Sidebar()

    sidebar.collapse_button.click()

    assert sidebar.minimumWidth() == sidebar.maximumWidth()


def test_enabled_buttons_present_and_checkable() -> None:
    sidebar = Sidebar()  # default role=TEACHER

    for key in ("dashboard", "devices", "labs", "data_log", "settings", "help"):
        assert sidebar.buttons[key].isEnabled() is True
        assert sidebar.buttons[key].isCheckable() is True


def test_devices_button_click_emits_navigate_requested() -> None:
    sidebar = Sidebar()
    received: list[str] = []
    sidebar.navigate_requested.connect(received.append)

    sidebar.buttons["devices"].click()

    assert received == ["devices"]


def test_labs_button_click_emits_navigate_requested() -> None:
    sidebar = Sidebar()
    received: list[str] = []
    sidebar.navigate_requested.connect(received.append)

    sidebar.buttons["labs"].click()

    assert received == ["labs"]


def test_data_log_button_click_emits_navigate_requested() -> None:
    sidebar = Sidebar()
    received: list[str] = []
    sidebar.navigate_requested.connect(received.append)

    sidebar.buttons["data_log"].click()

    assert received == ["data_log"]


def test_home_button_click_emits_navigate_requested_for_student() -> None:
    sidebar = Sidebar(role=UserRole.STUDENT)
    received: list[str] = []
    sidebar.navigate_requested.connect(received.append)

    sidebar.buttons["home"].click()

    assert received == ["home"]


def test_settings_and_help_buttons_emit_own_key() -> None:
    sidebar = Sidebar()
    received: list[str] = []
    sidebar.navigate_requested.connect(received.append)

    sidebar.buttons["settings"].click()
    sidebar.buttons["help"].click()

    assert received == ["settings", "help"]


def test_dashboard_selected_by_default_for_teacher() -> None:
    sidebar = Sidebar()  # default role=TEACHER

    assert sidebar.buttons["dashboard"].isChecked() is True


def test_home_selected_by_default_for_student() -> None:
    sidebar = Sidebar(role=UserRole.STUDENT)

    assert sidebar.buttons["home"].isChecked() is True


def test_selecting_settings_unchecks_dashboard() -> None:
    sidebar = Sidebar()

    sidebar.buttons["settings"].click()

    assert sidebar.buttons["settings"].isChecked() is True
    assert sidebar.buttons["dashboard"].isChecked() is False


def test_works_without_device_manager() -> None:
    sidebar = Sidebar(device_manager=None)

    assert sidebar._device_summary_label.text() == "🔌 Қосылған құрылғылар: 0"


def test_device_summary_updates_on_device_identified() -> None:
    fake_manager = FakeDeviceManager()
    sidebar = Sidebar(device_manager=fake_manager)

    fake_manager.add_device(_make_device())

    assert "1" in sidebar._device_summary_label.text()


def test_device_summary_updates_on_port_disconnected() -> None:
    fake_manager = FakeDeviceManager()
    fake_manager.add_device(_make_device())
    sidebar = Sidebar(device_manager=fake_manager)

    fake_manager.remove_last("COM6")

    assert "0" in sidebar._device_summary_label.text()


# =====================================================================
# Phase 37A: role-aware navigation
# =====================================================================


def test_student_sees_only_its_five_allowed_items() -> None:
    sidebar = Sidebar(role=UserRole.STUDENT)

    assert set(sidebar.buttons.keys()) == {
        "home",
        "labs",
        "my_results",
        "feedback_student",
        "profile",
        "people",
        "help",
    }


def test_teacher_sees_its_eleven_allowed_items() -> None:
    sidebar = Sidebar(role=UserRole.TEACHER)

    assert set(sidebar.buttons.keys()) == {
        "dashboard",
        "classes",
        "labs",
        "results",
        "data_log",
        "feedback_teacher",
        "analytics",
        "question_bank",
        "devices",
        "profile",
        "people",
        "settings",
        "help",
    }


def test_student_never_sees_teacher_only_items() -> None:
    sidebar = Sidebar(role=UserRole.STUDENT)

    for forbidden_key in (
        "devices",
        "settings",
        "data_log",
        "dashboard",
        "classes",
        "results",
        "analytics",
        "question_bank",
        "feedback_teacher",
    ):
        assert forbidden_key not in sidebar.buttons


def test_shared_items_present_for_both_roles() -> None:
    student_sidebar = Sidebar(role=UserRole.STUDENT)
    teacher_sidebar = Sidebar(role=UserRole.TEACHER)

    for shared_key in ("labs", "help"):
        assert shared_key in student_sidebar.buttons
        assert shared_key in teacher_sidebar.buttons


def test_set_role_rebuilds_button_set_safely() -> None:
    sidebar = Sidebar(role=UserRole.STUDENT)
    assert "home" in sidebar.buttons
    assert "devices" not in sidebar.buttons

    sidebar.set_role(UserRole.TEACHER)

    assert "home" not in sidebar.buttons
    assert "devices" in sidebar.buttons
    assert sidebar.role() is UserRole.TEACHER


def test_set_role_to_same_role_is_a_safe_no_op() -> None:
    sidebar = Sidebar(role=UserRole.STUDENT)
    original_home_button = sidebar.buttons["home"]

    sidebar.set_role(UserRole.STUDENT)

    assert sidebar.buttons["home"] is original_home_button


def test_role_indicator_reflects_current_role() -> None:
    sidebar = Sidebar(role=UserRole.STUDENT)
    assert sidebar._role_indicator_label.text() == "Оқушы режимі"

    sidebar.set_role(UserRole.TEACHER)
    assert sidebar._role_indicator_label.text() == "Мұғалім режимі"


def test_switch_role_button_is_hidden() -> None:
    sidebar = Sidebar()
    assert sidebar._switch_role_button.isHidden()


def test_switch_role_button_emits_signal() -> None:
    sidebar = Sidebar()
    received = []
    sidebar.switch_role_requested.connect(lambda: received.append(True))

    sidebar._switch_role_button.click()

    assert received == [True]


def test_rebuilt_nav_buttons_are_clickable_after_role_switch() -> None:
    sidebar = Sidebar(role=UserRole.STUDENT)
    sidebar.set_role(UserRole.TEACHER)
    received: list[str] = []
    sidebar.navigate_requested.connect(received.append)

    sidebar.buttons["devices"].click()

    assert received == ["devices"]
