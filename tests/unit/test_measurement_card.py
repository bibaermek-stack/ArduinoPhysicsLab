"""MeasurementCard үшін юнит-тесттер."""

import sys

import pytest
from PySide6.QtWidgets import QApplication

from ui.widgets.measurement_card import MeasurementCard


@pytest.fixture(scope="module", autouse=True)
def qt_application() -> QApplication:
    """QWidget-тер үшін жалғыз QApplication дана."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_label_is_uppercased() -> None:
    card = MeasurementCard("Кернеу")

    assert card._label_widget.text() == "КЕРНЕУ"


def test_value_defaults_to_dash() -> None:
    card = MeasurementCard("Кернеу")

    assert card.value_label.text() == "—"


def test_value_label_can_be_updated() -> None:
    card = MeasurementCard("Кернеу")

    card.value_label.setText("5.024 V")

    assert card.value_label.text() == "5.024 V"


def test_object_name_is_set_for_qss_targeting() -> None:
    card = MeasurementCard("Кернеу")

    assert card.objectName() == "MeasurementCard"
    assert card._label_widget.property("role") == "cardLabel"
    assert card.value_label.property("role") == "cardValue"
