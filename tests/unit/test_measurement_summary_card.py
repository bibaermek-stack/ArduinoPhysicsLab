"""MeasurementSummaryCard (Phase 38A) — таза презентациялық виджет
тестері: әдепкі жасырын, `show_summary()` дайын
`ChannelReportStatistics`-ті ЕШБІР жаңа есептеусіз көрсетеді (`None`
өрістер үшін "—", жалған 0.0 жоқ), `hide_summary()` қайта жасырады,
екі батырма да өз сигналын шығарады.
"""

import sys

import pytest
from PySide6.QtWidgets import QApplication

from domain.services.experiment_report_data import ChannelReportStatistics
from ui.widgets.measurement_summary_card import MeasurementSummaryCard


@pytest.fixture(scope="module", autouse=True)
def qt_application() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def _make_stats(
    n: int = 40,
    latest: float | None = 5.0,
    minimum: float | None = 3.5,
    maximum: float | None = 6.5,
    average: float | None = 5.0,
) -> ChannelReportStatistics:
    return ChannelReportStatistics(
        channel_key="voltage",
        display_name="Кернеу",
        unit="V",
        decimals=3,
        n=n,
        latest=latest,
        minimum=minimum,
        maximum=maximum,
        average=average,
    )


def test_hidden_by_default() -> None:
    card = MeasurementSummaryCard()

    assert card.isHidden()


def test_show_summary_renders_stats_and_becomes_visible() -> None:
    card = MeasurementSummaryCard()

    card.show_summary(_make_stats(n=40, average=5.0, minimum=3.5, maximum=6.5))

    assert not card.isHidden()
    assert "40" in card._count_label.text()
    assert "5.000 V" in card._average_label.text()
    assert "3.500 V" in card._minimum_label.text()
    assert "6.500 V" in card._maximum_label.text()


def test_show_summary_renders_dash_for_none_fields_without_fabricating_zero() -> None:
    card = MeasurementSummaryCard()

    card.show_summary(
        _make_stats(n=0, latest=None, minimum=None, maximum=None, average=None)
    )

    assert "—" in card._average_label.text()
    assert "—" in card._minimum_label.text()
    assert "—" in card._maximum_label.text()
    assert "0.000" not in card._average_label.text()


def test_hide_summary_hides_card_again() -> None:
    card = MeasurementSummaryCard()
    card.show_summary(_make_stats())

    card.hide_summary()

    assert card.isHidden()


def test_open_report_button_click_emits_signal() -> None:
    card = MeasurementSummaryCard()
    received: list[None] = []
    card.open_report_requested.connect(lambda: received.append(None))

    card._open_report_button.click()

    assert len(received) == 1


def test_remeasure_button_click_emits_signal() -> None:
    card = MeasurementSummaryCard()
    received: list[None] = []
    card.remeasure_requested.connect(lambda: received.append(None))

    card._remeasure_button.click()

    assert len(received) == 1


# ---- Phase 39A: "Кері байланысты бастау" батырмасы -------------------------


def test_feedback_button_hidden_and_disabled_by_default() -> None:
    card = MeasurementSummaryCard()

    assert card._start_feedback_button.isHidden() is True
    assert card._start_feedback_button.isEnabled() is False


def test_set_feedback_available_shows_button() -> None:
    card = MeasurementSummaryCard()

    card.set_feedback_available(True)
    assert card._start_feedback_button.isHidden() is False

    card.set_feedback_available(False)
    assert card._start_feedback_button.isHidden() is True


def test_set_feedback_button_enabled_toggles_enabled_state() -> None:
    card = MeasurementSummaryCard()

    card.set_feedback_button_enabled(True)
    assert card._start_feedback_button.isEnabled() is True

    card.set_feedback_button_enabled(False)
    assert card._start_feedback_button.isEnabled() is False


def test_feedback_button_click_emits_signal() -> None:
    card = MeasurementSummaryCard()
    card.set_feedback_available(True)
    card.set_feedback_button_enabled(True)
    received: list[None] = []
    card.feedback_requested.connect(lambda: received.append(None))

    card._start_feedback_button.click()

    assert len(received) == 1
