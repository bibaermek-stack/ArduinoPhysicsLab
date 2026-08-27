"""ManagedDeviceCard — юнит-тесттер."""

import sys
from datetime import datetime, timezone

import pytest
from PySide6.QtWidgets import QApplication

from domain.entities.connected_device import ConnectedDevice
from ui.widgets.managed_device_card import (
    STATUS_CONNECTED,
    STATUS_DISCONNECTED,
    STATUS_ERROR,
    STATUS_UNKNOWN_DEVICE,
    ManagedDeviceCard,
)


@pytest.fixture(scope="module", autouse=True)
def qt_application() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def _make_device(
    sensor_type: str = "VOLTAGE",
    port_name: str = "COM6",
    serial_number: str | None = None,
    warnings: tuple[str, ...] = (),
) -> ConnectedDevice:
    return ConnectedDevice(
        device_id="APL-VOLTAGE-01",
        model="V1",
        sensor_type=sensor_type,
        firmware_version="1.0",
        chip="INA226",
        serial_number=serial_number,
        hardware_version=None,
        port_name=port_name,
        connected_at=datetime.now(timezone.utc),
        warnings=warnings,
    )


def test_voltage_display_label() -> None:
    card = ManagedDeviceCard(_make_device(sensor_type="VOLTAGE"))
    assert card._title_label.text() == "Кернеу датчигі"


def test_current_display_label() -> None:
    card = ManagedDeviceCard(_make_device(sensor_type="CURRENT"))
    assert card._title_label.text() == "Ток датчигі"


def test_unknown_sensor_type_fallback_uses_raw_type() -> None:
    card = ManagedDeviceCard(_make_device(sensor_type="THERMOMETER"))
    assert card._title_label.text() == "THERMOMETER"


def test_default_status_is_connected_after_set_device() -> None:
    card = ManagedDeviceCard(_make_device())
    assert "Қосылды" in card._status_text_label.text()


def test_set_status_updates_text() -> None:
    card = ManagedDeviceCard(_make_device())

    card.set_status(STATUS_ERROR)
    assert "Қате" in card._status_text_label.text()

    card.set_status(STATUS_DISCONNECTED)
    assert "Ажыратылды" in card._status_text_label.text()

    card.set_status(STATUS_CONNECTED)
    assert "Қосылды" in card._status_text_label.text()


def test_details_hidden_by_default() -> None:
    # QWidget.isVisible() виджет нақты экранда көрсетілгенде ғана True
    # қайтарады, сондықтан setVisible() дұрыс шақырылғанын тексеру үшін
    # карточканы show() ету қажет (test_device_panel.py-дегі паттерн).
    card = ManagedDeviceCard(_make_device())
    card.show()
    assert card.is_details_expanded() is False
    assert card._details_frame.isVisible() is False


def test_details_toggle_shows_details_frame() -> None:
    card = ManagedDeviceCard(_make_device())
    card.show()

    card._details_toggle_button.click()

    assert card.is_details_expanded() is True
    assert card._details_frame.isVisible() is True


def test_details_omit_missing_serial_number() -> None:
    card = ManagedDeviceCard(_make_device(serial_number=None))
    card._details_toggle_button.click()

    details_text = " ".join(
        card._details_layout.itemAt(i).widget().text()
        for i in range(card._details_layout.count())
    )

    assert "Serial number" not in details_text


def test_details_include_serial_number_when_present() -> None:
    card = ManagedDeviceCard(_make_device(serial_number="SN-123"))
    card._details_toggle_button.click()

    details_text = " ".join(
        card._details_layout.itemAt(i).widget().text()
        for i in range(card._details_layout.count())
    )

    assert "SN-123" in details_text


def test_details_include_warnings_when_present() -> None:
    card = ManagedDeviceCard(_make_device(warnings=("test warning",)))
    card._details_toggle_button.click()

    details_text = " ".join(
        card._details_layout.itemAt(i).widget().text()
        for i in range(card._details_layout.count())
    )

    assert "test warning" in details_text


def test_disconnect_button_emits_port_name() -> None:
    card = ManagedDeviceCard(_make_device(port_name="COM9"))
    received: list[str] = []
    card.disconnect_requested.connect(received.append)

    card._disconnect_button.click()

    assert received == ["COM9"]


def test_summary_shows_port_and_chip() -> None:
    card = ManagedDeviceCard(_make_device(port_name="COM6"))
    assert "COM6" in card._summary_label.text()
    assert "INA226" in card._summary_label.text()


# =====================================================================
# Phase 21 §5/§9: белгісіз сенсор түрі -> warning статус, TEMPERATURE
# канондық түрі.
# =====================================================================


def test_temperature_sensor_has_canonical_kazakh_name() -> None:
    card = ManagedDeviceCard(_make_device(sensor_type="TEMPERATURE"))
    assert card._title_label.text() == "Температура сенсоры"


def test_known_sensor_type_defaults_to_connected_status() -> None:
    card = ManagedDeviceCard(_make_device(sensor_type="VOLTAGE"))
    assert "Қосылды" in card._status_text_label.text()


def test_unknown_sensor_type_defaults_to_unknown_device_status() -> None:
    """§5 "Unknown device: warning" — HELLO сәтті өтті, бірақ sensor_type
    domain.constants.sensor_types.KNOWN_SENSOR_TYPES-те жоқ."""
    card = ManagedDeviceCard(_make_device(sensor_type="THERMOMETER"))
    assert "Белгісіз құрылғы" in card._status_text_label.text()


def test_set_status_supports_unknown_device() -> None:
    card = ManagedDeviceCard(_make_device())
    card.set_status(STATUS_UNKNOWN_DEVICE)
    assert "Белгісіз құрылғы" in card._status_text_label.text()


# =====================================================================
# Phase 21 §4/§15: соңғы өлшеу алдын ала көрінісі / соңғы дерек уақыты —
# ешбір жалған бастапқы мән ЕШҚАШАН көрсетілмейді.
# =====================================================================


def test_preview_hidden_until_explicitly_set() -> None:
    card = ManagedDeviceCard(_make_device())
    card.show()
    assert card._preview_label.isVisible() is False


def test_set_preview_shows_text() -> None:
    card = ManagedDeviceCard(_make_device())
    card.show()

    card.set_preview("U: 5.12 V")

    assert card._preview_label.isVisible() is True
    assert card._preview_label.text() == "U: 5.12 V"


def test_set_preview_none_hides_label_again() -> None:
    card = ManagedDeviceCard(_make_device())
    card.show()
    card.set_preview("U: 5.12 V")

    card.set_preview(None)

    assert card._preview_label.isVisible() is False


def test_last_data_hidden_until_explicitly_set() -> None:
    card = ManagedDeviceCard(_make_device())
    card.show()
    assert card._last_data_label.isVisible() is False


def test_set_last_data_at_shows_formatted_time() -> None:
    card = ManagedDeviceCard(_make_device())
    card.show()
    timestamp = datetime(2026, 1, 1, 14, 32, 7, tzinfo=timezone.utc)

    card.set_last_data_at(timestamp)

    expected = timestamp.astimezone().strftime("%H:%M:%S")
    assert card._last_data_label.isVisible() is True
    assert expected in card._last_data_label.text()
