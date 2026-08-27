"""DeviceCard үшін юнит-тесттер."""

import sys
from datetime import datetime, timezone

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from domain.entities.connected_device import ConnectedDevice
from ui.widgets.device_card import DeviceCard


@pytest.fixture(scope="module", autouse=True)
def qt_application() -> QApplication:
    """QWidget-тер үшін жалғыз QApplication дана."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def _make_device(
    sensor_type: str = "VOLTAGE",
    device_id: str = "APL-VOLTAGE-01",
    chip: str | None = "INA226",
) -> ConnectedDevice:
    return ConnectedDevice(
        device_id=device_id,
        model="V1",
        sensor_type=sensor_type,
        firmware_version="1.0",
        chip=chip,
        serial_number=None,
        hardware_version=None,
        port_name="COM3",
        connected_at=datetime.now(timezone.utc),
        warnings=(),
    )


def _click(card: DeviceCard) -> None:
    """Карточканы тінтуірдің сол жақ батырмасымен басу оқиғасын жасайды."""
    event = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPoint(5, 5),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    card.mousePressEvent(event)


def test_connected_device_is_displayed_correctly() -> None:
    card = DeviceCard()
    device = _make_device()

    card.set_device(device)

    assert card.device() == device
    assert "APL-VOLTAGE-01" in card._device_id_label.text()
    assert "V1" in card._model_label.text()
    assert "1.0" in card._firmware_label.text()
    assert "INA226" in card._chip_label.text()
    assert "COM3" in card._port_label.text()


def test_voltage_sensor_type_translated_to_kazakh() -> None:
    card = DeviceCard()
    card.set_device(_make_device(sensor_type="VOLTAGE"))

    assert card._title_label.text() == "Кернеу датчигі"


def test_unknown_sensor_type_is_displayed() -> None:
    card = DeviceCard()
    card.set_device(_make_device(sensor_type="MAGNETIC"))

    assert card._title_label.text() == "Белгісіз датчик"


def test_missing_chip_shows_dash() -> None:
    card = DeviceCard()
    card.set_device(_make_device(chip=None))

    assert "—" in card._chip_label.text()


def test_selected_state_changes() -> None:
    card = DeviceCard()
    card.set_device(_make_device())

    assert card.is_selected() is False

    card.set_selected(True)
    assert card.is_selected() is True
    assert card.property("selected") == "true"

    card.set_selected(False)
    assert card.is_selected() is False


def test_model_firmware_chip_hidden_from_main_body() -> None:
    # Визуалды ықшамдау (V4): толық ақпарат tooltip-те, негізгі денеде жоқ.
    card = DeviceCard()
    card.set_device(_make_device())

    assert card._model_label.isHidden() is True
    assert card._firmware_label.isHidden() is True
    assert card._chip_label.isHidden() is True
    # Мәтін өзі сақталады — тек көрінбейді (ескі тесттер осыған тәуелді).
    assert "V1" in card._model_label.text()


def test_tooltip_contains_model_firmware_chip() -> None:
    card = DeviceCard()
    card.set_device(_make_device())

    tooltip = card.toolTip()
    assert "V1" in tooltip
    assert "1.0" in tooltip
    assert "INA226" in tooltip


# ---- kезeng 29: live measurement value ------------------------------------


def test_live_value_hidden_initially() -> None:
    card = DeviceCard()
    card.set_device(_make_device())

    assert card._live_value_label.isHidden() is True


def test_set_live_value_shows_text() -> None:
    card = DeviceCard()
    card.set_device(_make_device())

    card.set_live_value("5.333 V")

    assert card._live_value_label.text() == "5.333 V"
    assert card._live_value_label.isHidden() is False


def test_set_live_value_empty_hides_label() -> None:
    card = DeviceCard()
    card.set_device(_make_device())
    card.set_live_value("5.333 V")

    card.set_live_value("")

    assert card._live_value_label.isHidden() is True


def test_set_device_clears_previous_live_value() -> None:
    card = DeviceCard()
    card.set_device(_make_device())
    card.set_live_value("5.333 V")

    card.set_device(_make_device())  # жаңа/қайта identify — ескі мән тазалануы керек

    assert card._live_value_label.isHidden() is True


def test_card_click_emits_selected_signal() -> None:
    card = DeviceCard()
    device = _make_device()
    card.set_device(device)

    received: list[ConnectedDevice] = []
    card.selected.connect(received.append)

    _click(card)

    assert received == [device]
