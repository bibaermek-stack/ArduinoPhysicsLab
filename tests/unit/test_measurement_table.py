"""MeasurementTableWidget үшін юнит-тесттер: configure_channels негізіндегі
динамикалық бағандар.
"""

import sys
from datetime import datetime, timezone

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QApplication, QSizePolicy

from domain.entities.measurement import Measurement
from domain.entities.sensor_channel import SensorChannel
from ui.widgets.measurement_table import MeasurementTableWidget


@pytest.fixture(scope="module", autouse=True)
def qt_application() -> QApplication:
    """QWidget-тер үшін жалғыз QApplication дана."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


VOLTAGE = SensorChannel(key="voltage", display_name="Кернеу", unit="V", decimals=3)
CURRENT = SensorChannel(key="current", display_name="Ток", unit="A", decimals=3)
RESISTANCE = SensorChannel(
    key="resistance", display_name="Кедергі", unit="Ω", decimals=2, required=False
)
WORK = SensorChannel(key="work", display_name="Жұмыс", unit="J", decimals=3, required=False)


def _make_measurement(
    values: dict[str, float] | None = None,
    derived_values: dict[str, float] | None = None,
    timestamp: datetime | None = None,
) -> Measurement:
    return Measurement(
        timestamp=timestamp or datetime.now(timezone.utc),
        values=values or {},
        experiment_id="E02",
        derived_values=derived_values or {},
    )


def test_table_has_only_row_number_column_before_configure() -> None:
    table = MeasurementTableWidget()

    assert table._model.columnCount() == 1
    assert table._model.headerData(0, Qt.Orientation.Horizontal) == "№"


def test_configure_channels_sets_dynamic_headers() -> None:
    table = MeasurementTableWidget()

    table.configure_channels((VOLTAGE, CURRENT, RESISTANCE))

    headers = [
        table._model.headerData(i, Qt.Orientation.Horizontal) for i in range(4)
    ]
    assert headers == ["№", "Кернеу (V)", "Ток (A)", "Кедергі (Ω)"]


def test_append_measurement_adds_row_with_configured_values() -> None:
    table = MeasurementTableWidget()
    table.configure_channels((VOLTAGE, CURRENT, RESISTANCE))
    measurement = _make_measurement(
        values={"voltage": 5.024, "current": 0.218}, derived_values={"resistance": 23.046}
    )

    table.append_measurement(measurement)

    assert table._model.rowCount() == 1
    assert table._model.item(0, 0).text() == "1"
    assert table._model.item(0, 1).text() == "5.024"
    assert table._model.item(0, 2).text() == "0.218"
    assert table._model.item(0, 3).text() == "23.05"


def test_derived_work_channel_is_displayed() -> None:
    table = MeasurementTableWidget()
    table.configure_channels((WORK,))

    table.append_measurement(_make_measurement(derived_values={"work": 12.5}))

    assert table._model.item(0, 1).text() == "12.500"


def test_missing_value_shows_dash() -> None:
    table = MeasurementTableWidget()
    table.configure_channels((VOLTAGE, CURRENT))
    measurement = _make_measurement(values={"voltage": 5.0})

    table.append_measurement(measurement)

    assert table._model.item(0, 1).text() == "5.000"
    assert table._model.item(0, 2).text() == "—"


def test_row_numbering_increments() -> None:
    table = MeasurementTableWidget()
    table.configure_channels((VOLTAGE,))

    table.append_measurement(_make_measurement(values={"voltage": 1.0}))
    table.append_measurement(_make_measurement(values={"voltage": 2.0}))

    assert table._model.item(0, 0).text() == "1"
    assert table._model.item(1, 0).text() == "2"


def test_configure_channels_clears_existing_rows() -> None:
    table = MeasurementTableWidget()
    table.configure_channels((VOLTAGE,))
    table.append_measurement(_make_measurement(values={"voltage": 1.0}))
    assert table._model.rowCount() == 1

    table.configure_channels((CURRENT,))

    assert table._model.rowCount() == 0
    assert table._model.columnCount() == 2
    assert table._model.headerData(1, Qt.Orientation.Horizontal) == "Ток (A)"


def test_clear_removes_all_rows_but_keeps_header() -> None:
    table = MeasurementTableWidget()
    table.configure_channels((VOLTAGE,))
    table.append_measurement(_make_measurement(values={"voltage": 5.0}))

    table.clear()

    assert table._model.rowCount() == 0
    assert table._model.columnCount() == 2
    assert table._model.headerData(1, Qt.Orientation.Horizontal) == "Кернеу (V)"


def test_auto_scroll_called_on_append() -> None:
    table = MeasurementTableWidget()
    table.configure_channels((VOLTAGE,))
    calls: list[None] = []
    table._table_view.scrollToBottom = lambda: calls.append(None)

    table.append_measurement(_make_measurement(values={"voltage": 5.0}))

    assert len(calls) == 1


def test_table_is_read_only_and_single_selection() -> None:
    table = MeasurementTableWidget()

    assert (
        table._table_view.editTriggers() == QAbstractItemView.EditTrigger.NoEditTriggers
    )
    assert (
        table._table_view.selectionMode() == QAbstractItemView.SelectionMode.SingleSelection
    )
    assert (
        table._table_view.selectionBehavior() == QAbstractItemView.SelectionBehavior.SelectRows
    )


# ---- Column visibility (V3: optional Power toggle) -------------------------


def test_column_hidden_by_default_is_visible() -> None:
    table = MeasurementTableWidget()
    table.configure_channels((VOLTAGE, CURRENT))

    assert table._table_view.isColumnHidden(2) is False


def test_set_column_visible_false_hides_column() -> None:
    table = MeasurementTableWidget()
    table.configure_channels((VOLTAGE, CURRENT))

    table.set_column_visible("current", False)

    assert table._table_view.isColumnHidden(2) is True
    assert table._table_view.isColumnHidden(1) is False


def test_set_column_visible_true_shows_previously_hidden_column() -> None:
    table = MeasurementTableWidget()
    table.configure_channels((VOLTAGE, CURRENT))
    table.set_column_visible("current", False)

    table.set_column_visible("current", True)

    assert table._table_view.isColumnHidden(2) is False


def test_hidden_column_data_is_preserved_and_shown_after_unhide() -> None:
    # Power toggle OFF-та да баған деректері толады, тек view-де жасырылады —
    # ON еткенде бұрынғы жолдардың мәні дереу дұрыс көрінеді (backfill қажет
    # емес).
    table = MeasurementTableWidget()
    table.configure_channels((VOLTAGE, CURRENT))
    table.set_column_visible("current", False)

    table.append_measurement(_make_measurement(values={"voltage": 5.0, "current": 0.218}))
    table.append_measurement(_make_measurement(values={"voltage": 6.0, "current": 0.3}))

    assert table._model.item(0, 2).text() == "0.218"
    assert table._model.item(1, 2).text() == "0.300"

    table.set_column_visible("current", True)

    assert table._table_view.isColumnHidden(2) is False
    assert table._model.item(0, 2).text() == "0.218"
    assert table._model.item(1, 2).text() == "0.300"


def test_set_column_visible_unknown_key_does_not_raise() -> None:
    table = MeasurementTableWidget()
    table.configure_channels((VOLTAGE,))

    table.set_column_visible("bogus_key", False)  # эксепшн шықпауы тиіс


def test_table_view_has_dedicated_object_name() -> None:
    # kезeng 29: ThemeManager-дің осы кестеге ғана арналған QSS селекторы
    # (басқа QTableView-терге ортақ емес) үшін.
    table = MeasurementTableWidget()

    assert table._table_view.objectName() == "MeasurementTableView"


# ---- Phase 32: shared workspace layout architecture -----------------------


def test_widget_has_expanding_size_policy_both_directions() -> None:
    table = MeasurementTableWidget()
    policy = table.sizePolicy()
    assert policy.horizontalPolicy() == QSizePolicy.Policy.Expanding
    assert policy.verticalPolicy() == QSizePolicy.Policy.Expanding


def test_table_view_has_expanding_size_policy_both_directions() -> None:
    table = MeasurementTableWidget()
    policy = table._table_view.sizePolicy()
    assert policy.horizontalPolicy() == QSizePolicy.Policy.Expanding
    assert policy.verticalPolicy() == QSizePolicy.Policy.Expanding
