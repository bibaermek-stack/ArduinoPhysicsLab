"""DevicePanel үшін юнит-тесттер."""

import sys
from datetime import datetime, timezone

import pytest
from PySide6.QtWidgets import QApplication, QSizePolicy

from domain.entities.connected_device import ConnectedDevice
from infrastructure.serial_comm.device_scanner import SerialDeviceInfo
from ui.widgets.device_card import DeviceCard
from ui.widgets.device_panel import _NO_PORT_SELECTED_MESSAGE, DevicePanel


@pytest.fixture(scope="module", autouse=True)
def qt_application() -> QApplication:
    """QWidget-тер үшін жалғыз QApplication дана."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def _make_port(port_name: str, is_arduino: bool = False) -> SerialDeviceInfo:
    return SerialDeviceInfo(
        port_name=port_name,
        description="Arduino Nano" if is_arduino else "USB Serial",
        manufacturer=None,
        serial_number=None,
        vendor_id=0x2341 if is_arduino else None,
        product_id=None,
        is_likely_arduino=is_arduino,
    )


def _make_device(
    device_id: str = "APL-VOLTAGE-01",
    sensor_type: str = "VOLTAGE",
    port_name: str = "COM3",
) -> ConnectedDevice:
    return ConnectedDevice(
        device_id=device_id,
        model="V1",
        sensor_type=sensor_type,
        firmware_version="1.0",
        chip="INA226",
        serial_number=None,
        hardware_version=None,
        port_name=port_name,
        connected_at=datetime.now(timezone.utc),
        warnings=(),
    )


def _visible_card_order(panel: DevicePanel) -> list[DeviceCard]:
    cards: list[DeviceCard] = []
    for i in range(panel._cards_layout.count()):
        widget = panel._cards_layout.itemAt(i).widget()
        if isinstance(widget, DeviceCard):
            cards.append(widget)
    return cards


def test_ports_populate_combo_box() -> None:
    panel = DevicePanel()
    panel.set_ports((_make_port("COM3", True), _make_port("COM4")))

    assert panel._port_combo.count() == 2
    assert panel._port_combo.itemData(0) == "COM3"
    assert "[Arduino]" in panel._port_combo.itemText(0)
    assert panel._port_combo.itemData(1) == "COM4"


def test_devices_are_sorted_by_sensor_type() -> None:
    panel = DevicePanel()

    panel.add_or_update_device(_make_device(device_id="OHM-01", sensor_type="OHMMETER", port_name="COM6"))
    panel.add_or_update_device(_make_device(device_id="CUR-01", sensor_type="CURRENT", port_name="COM4"))
    panel.add_or_update_device(_make_device(device_id="VOLT-01", sensor_type="VOLTAGE", port_name="COM3"))
    panel.add_or_update_device(_make_device(device_id="ENE-01", sensor_type="ENERGY", port_name="COM5"))

    ordered_types = [card.device().sensor_type for card in _visible_card_order(panel)]
    assert ordered_types == ["VOLTAGE", "CURRENT", "ENERGY", "OHMMETER"]


def test_device_is_added() -> None:
    panel = DevicePanel()
    device = _make_device()

    panel.add_or_update_device(device)

    assert len(panel._cards_by_port) == 1
    assert panel._cards_by_port["COM3"].device() == device


def test_same_port_device_is_updated_not_duplicated() -> None:
    panel = DevicePanel()
    panel.add_or_update_device(_make_device(device_id="APL-VOLTAGE-01", port_name="COM3"))
    updated = ConnectedDevice(
        device_id="APL-VOLTAGE-01",
        model="V2",
        sensor_type="VOLTAGE",
        firmware_version="2.0",
        chip="INA226",
        serial_number=None,
        hardware_version=None,
        port_name="COM3",
        connected_at=datetime.now(timezone.utc),
        warnings=(),
    )

    panel.add_or_update_device(updated)

    assert len(panel._cards_by_port) == 1
    assert panel._cards_by_port["COM3"].device().firmware_version == "2.0"


def test_device_moving_to_new_port_removes_old_card() -> None:
    panel = DevicePanel()
    panel.add_or_update_device(_make_device(device_id="APL-VOLTAGE-01", port_name="COM3"))

    panel.add_or_update_device(_make_device(device_id="APL-VOLTAGE-01", port_name="COM5"))

    assert "COM3" not in panel._cards_by_port
    assert "COM5" in panel._cards_by_port
    assert len(panel._cards_by_port) == 1


def test_device_selection_is_forwarded() -> None:
    panel = DevicePanel()
    device = _make_device()
    panel.add_or_update_device(device)

    received: list[ConnectedDevice] = []
    panel.device_selected.connect(received.append)

    card = panel._cards_by_port["COM3"]
    card.selected.emit(device)

    assert received == [device]
    assert card.is_selected() is True


def test_clear_devices_shows_empty_state() -> None:
    # QWidget.isVisible() виджет нақты экранда көрсетілгенде ғана True
    # қайтарады (бүкіл ата-тек тізбегі visible болуы керек), сондықтан
    # setVisible() дұрыс шақырылғанын тексеру үшін панельді show() ету қажет.
    panel = DevicePanel()
    panel.show()
    panel.add_or_update_device(_make_device())

    panel.clear_devices()

    assert panel._cards_by_port == {}
    assert panel._empty_state_label.isVisible() is True


def test_identify_button_emits_port_and_baud() -> None:
    panel = DevicePanel()
    panel.set_ports((_make_port("COM3"),))

    received: list[tuple[str, int]] = []
    panel.identify_requested.connect(lambda port, baud: received.append((port, baud)))

    panel._identify_button.click()

    assert received == [("COM3", 115200)]


def test_identify_without_selected_port_does_not_emit() -> None:
    panel = DevicePanel()

    received: list[tuple[str, int]] = []
    panel.identify_requested.connect(lambda port, baud: received.append((port, baud)))

    panel._identify_button.click()

    assert received == []
    assert panel._message_label.text() == _NO_PORT_SELECTED_MESSAGE


# ---- Multi-device readiness checklist -------------------------------------


def test_readiness_checklist_hidden_for_single_or_no_sensor_types() -> None:
    panel = DevicePanel()

    panel.set_required_sensor_types(())
    assert panel._readiness_container.isHidden() is True

    panel.set_required_sensor_types(("VOLTAGE",))
    assert panel._readiness_container.isHidden() is True


def test_readiness_checklist_shown_for_multiple_sensor_types() -> None:
    panel = DevicePanel()

    panel.set_required_sensor_types(("VOLTAGE", "CURRENT"))

    assert panel._readiness_container.isHidden() is False
    assert set(panel._readiness_labels.keys()) == {"VOLTAGE", "CURRENT"}
    # Phase 32.1: hardware-тәуелсіз workspace-те "әлі қосылмаған" екенін
    # тек ○ иконасына сүйенбей, мәтінмен де көрсету.
    assert panel._readiness_labels["VOLTAGE"].text() == "○ Кернеу датчигі — Қосылмаған"
    assert panel._readiness_labels["CURRENT"].text() == "○ Ток датчигі — Қосылмаған"


def test_set_sensor_readiness_updates_checkmarks() -> None:
    panel = DevicePanel()
    panel.set_required_sensor_types(("VOLTAGE", "CURRENT"))

    panel.set_sensor_readiness({"VOLTAGE": True, "CURRENT": False})

    assert panel._readiness_labels["VOLTAGE"].text() == "✓ Кернеу датчигі"
    assert panel._readiness_labels["CURRENT"].text() == "○ Ток датчигі — Қосылмаған"


def test_readiness_checklist_shows_temperature_sensor_type() -> None:
    # Phase 38B: metal-resistance-temperature (№8) — TEMPERATURE ЕНДІ
    # ENERGY/OHMMETER-мен БІРДЕЙ "hardware adapter белсенді емес" статуста
    # checklist-те көрінеді (нақты firmware жоқ болса да, UI дайын).
    panel = DevicePanel()

    panel.set_required_sensor_types(("VOLTAGE", "CURRENT", "TEMPERATURE"))

    assert set(panel._readiness_labels.keys()) == {"VOLTAGE", "CURRENT", "TEMPERATURE"}
    assert (
        panel._readiness_labels["TEMPERATURE"].text()
        == "○ Температура датчигі — Қосылмаған"
    )


def test_re_setting_required_sensor_types_replaces_checklist() -> None:
    panel = DevicePanel()
    panel.set_required_sensor_types(("VOLTAGE", "CURRENT"))
    panel.set_sensor_readiness({"VOLTAGE": True, "CURRENT": True})

    panel.set_required_sensor_types(())

    assert panel._readiness_container.isHidden() is True
    assert panel._readiness_labels == {}


# ---- kезeng 29: live measurement value forwarding -------------------------


def test_update_measurement_value_sets_matching_card() -> None:
    panel = DevicePanel()
    panel.add_or_update_device(_make_device(sensor_type="VOLTAGE", port_name="COM3"))
    panel.add_or_update_device(
        _make_device(device_id="APL-CURRENT-01", sensor_type="CURRENT", port_name="COM4")
    )

    panel.update_measurement_value({"voltage": 5.333, "current": 0.0664})

    assert panel._cards_by_port["COM3"]._live_value_label.text() == "5.333 V"
    assert panel._cards_by_port["COM4"]._live_value_label.text() == "0.066 A"


def test_update_measurement_value_ignores_unknown_channel_keys() -> None:
    panel = DevicePanel()
    panel.add_or_update_device(_make_device(sensor_type="VOLTAGE", port_name="COM3"))

    panel.update_measurement_value({"resistance": 100.0, "power": 1.5})  # exception шықпауы керек

    assert panel._cards_by_port["COM3"]._live_value_label.isHidden() is True


def test_update_measurement_value_noop_without_matching_card() -> None:
    panel = DevicePanel()

    panel.update_measurement_value({"voltage": 5.0})  # карточка жоқ — exception шықпауы керек


# ---- Phase 32: shared workspace layout architecture -----------------------


def test_panel_width_is_bounded_and_does_not_expand_horizontally() -> None:
    panel = DevicePanel()
    policy = panel.sizePolicy()
    assert policy.horizontalPolicy() != QSizePolicy.Policy.Expanding
    assert panel.maximumWidth() <= 300


def test_panel_uses_expanding_vertical_size_policy() -> None:
    panel = DevicePanel()
    policy = panel.sizePolicy()
    assert policy.verticalPolicy() == QSizePolicy.Policy.Expanding

    assert panel._cards_by_port == {}
