"""LiveGraphWidget үшін юнит-тесттер: configure_channels негізіндегі
уақыттық/X-Y режимдер.
"""

import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pyqtgraph as pg
import pytest
from PySide6.QtWidgets import QApplication, QSizePolicy

from domain.entities.experiment_definition import RateOfChangeConfig
from domain.entities.experiment_session import ExperimentSession
from domain.entities.measurement import Measurement
from domain.entities.sensor_channel import SensorChannel
from ui.widgets.live_graph import DERIVED_ANALYSIS_POWER_ENERGY, LiveGraphWidget


@pytest.fixture(scope="module", autouse=True)
def qt_application() -> QApplication:
    """QWidget-тер үшін жалғыз QApplication дана."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


VOLTAGE = SensorChannel(key="voltage", display_name="Кернеу", unit="V", decimals=3)
CURRENT = SensorChannel(key="current", display_name="Ток", unit="A", decimals=3)
POWER = SensorChannel(key="power", display_name="Қуат", unit="W", decimals=3, required=False)
TIME = SensorChannel(key="time", display_name="Уақыт", unit="s", decimals=2, required=False)


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


def test_apply_theme_updates_plot_background() -> None:
    from ui.themes.theme_manager import THEME_DARK, THEME_LIGHT, apply_application_theme

    graph = LiveGraphWidget()
    apply_application_theme(THEME_LIGHT)
    graph.apply_theme()
    light = graph._plot_widget.backgroundBrush().color().name().upper()
    assert light == "#FFFFFF"
    apply_application_theme(THEME_DARK)
    graph.apply_theme()
    dark = graph._plot_widget.backgroundBrush().color().name().upper()
    assert dark == "#2C2C2E"


def test_graph_has_no_curves_before_configure() -> None:
    graph = LiveGraphWidget()

    assert graph._curves == {}
    assert graph._checkboxes == {}


# ---- X-Y режим -------------------------------------------------------


def test_configure_xy_mode_creates_curve_only_for_y_channels() -> None:
    graph = LiveGraphWidget()

    graph.configure_channels((VOLTAGE, CURRENT, POWER), x_channel="voltage", y_channels=("current",))

    assert set(graph._curves.keys()) == {"current"}
    assert set(graph._checkboxes.keys()) == {"current"}


def test_xy_mode_voltage_current_appends_point() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels((VOLTAGE, CURRENT), x_channel="voltage", y_channels=("current",))

    graph.append_measurement(_make_measurement(values={"voltage": 5.0, "current": 0.5}))

    assert list(graph._x_data["current"]) == [5.0]
    assert list(graph._y_data["current"]) == [0.5]


def test_xy_mode_current_voltage_appends_point() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels((VOLTAGE, CURRENT), x_channel="current", y_channels=("voltage",))

    graph.append_measurement(_make_measurement(values={"voltage": 5.0, "current": 0.5}))

    assert list(graph._x_data["voltage"]) == [0.5]
    assert list(graph._y_data["voltage"]) == [5.0]


def test_xy_mode_missing_x_value_skips_point() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels((VOLTAGE, CURRENT), x_channel="voltage", y_channels=("current",))

    graph.append_measurement(_make_measurement(values={"current": 0.5}))  # voltage жоқ

    assert list(graph._x_data["current"]) == []
    assert list(graph._y_data["current"]) == []


def test_xy_mode_missing_y_value_skips_point() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels((VOLTAGE, CURRENT), x_channel="voltage", y_channels=("current",))

    graph.append_measurement(_make_measurement(values={"voltage": 5.0}))  # current жоқ

    assert list(graph._x_data["current"]) == []
    assert list(graph._y_data["current"]) == []


# ---- Уақыттық режим ---------------------------------------------------


def test_time_mode_power_channel_uses_elapsed_time() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels((POWER,), x_channel=None, y_channels=("power",))
    started_at = datetime.now(timezone.utc)

    graph.append_measurement(
        _make_measurement(derived_values={"power": 1.0}, timestamp=started_at)
    )
    graph.append_measurement(
        _make_measurement(
            derived_values={"power": 2.0}, timestamp=started_at + timedelta(seconds=1)
        )
    )

    assert list(graph._y_data["power"]) == [1.0, 2.0]
    assert list(graph._x_data["power"]) == pytest.approx([0.0, 1.0])


def test_time_mode_prefers_real_time_value_over_elapsed() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels((POWER, TIME), x_channel=None, y_channels=("power",))

    graph.append_measurement(
        _make_measurement(values={"time": 12.5}, derived_values={"power": 1.0})
    )

    assert list(graph._x_data["power"]) == [12.5]


# ---- clear / configure lifecycle --------------------------------------


def test_clear_preserves_configuration() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels((VOLTAGE, CURRENT), x_channel="voltage", y_channels=("current",))
    graph.append_measurement(_make_measurement(values={"voltage": 5.0, "current": 0.5}))

    graph.clear()

    assert list(graph._y_data["current"]) == []
    assert set(graph._curves.keys()) == {"current"}


def test_reconfigure_clears_old_curves_and_data() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels((VOLTAGE, CURRENT), x_channel="voltage", y_channels=("current",))
    graph.append_measurement(_make_measurement(values={"voltage": 5.0, "current": 0.5}))

    graph.configure_channels((POWER, TIME), x_channel=None, y_channels=("power",))

    assert "current" not in graph._curves
    assert set(graph._curves.keys()) == {"power"}
    assert list(graph._y_data["power"]) == []


def test_set_measurements_loads_multiple_points() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels((VOLTAGE,), x_channel=None, y_channels=("voltage",))
    started_at = datetime.now(timezone.utc)
    session = ExperimentSession(id="s1", experiment_id="E02", started_at=started_at)
    session.add_measurement(_make_measurement(values={"voltage": 1.0}, timestamp=started_at))
    session.add_measurement(
        _make_measurement(values={"voltage": 2.0}, timestamp=started_at + timedelta(seconds=1))
    )

    graph.set_measurements(session)

    assert list(graph._y_data["voltage"]) == [1.0, 2.0]
    assert list(graph._x_data["voltage"]) == pytest.approx([0.0, 1.0])


def test_empty_session_produces_no_points() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels((VOLTAGE,), x_channel=None, y_channels=("voltage",))
    session = ExperimentSession(
        id="s1", experiment_id="E02", started_at=datetime.now(timezone.utc)
    )

    graph.set_measurements(session)

    assert list(graph._y_data["voltage"]) == []


# ---- Checkbox / auto-scale ----------------------------------------------


def test_checkbox_toggles_curve_visibility() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels((VOLTAGE, CURRENT), x_channel="voltage", y_channels=("current",))

    graph._checkboxes["current"].setChecked(False)

    assert graph._curves["current"].isVisible() is False


def test_checkbox_label_uses_channel_display_name() -> None:
    graph = LiveGraphWidget()

    graph.configure_channels((VOLTAGE, CURRENT), x_channel="voltage", y_channels=("current",))

    assert graph._checkboxes["current"].text() == "Ток"


def test_auto_scale_can_be_toggled() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels((VOLTAGE,), x_channel=None, y_channels=("voltage",))
    view_box = graph._plot_widget.getViewBox()
    assert all(view_box.autoRangeEnabled())

    graph._auto_scale_checkbox.setChecked(False)

    assert not any(view_box.autoRangeEnabled())


def test_toolbar_clear_button_clears_graph() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels((VOLTAGE,), x_channel=None, y_channels=("voltage",))
    graph.append_measurement(_make_measurement(values={"voltage": 5.0}))

    graph._clear_button.click()

    assert list(graph._y_data["voltage"]) == []


def test_zoom_reset_button_calls_autorange_without_changing_checkbox() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels((VOLTAGE,), x_channel=None, y_channels=("voltage",))
    graph.append_measurement(_make_measurement(values={"voltage": 5.0}))
    calls: list[None] = []
    graph._plot_widget.autoRange = lambda: calls.append(None)

    graph._zoom_reset_button.click()

    assert len(calls) == 1
    assert graph._auto_scale_checkbox.isChecked() is True


def test_zoom_reset_button_updates_all_stacked_plots() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels(
        (VOLTAGE, CURRENT),
        x_channel=None,
        y_channels=("voltage", "current"),
        stacked=True,
    )
    calls: list[str] = []
    for key, plot_widget in graph._stacked_plot_widgets.items():
        plot_widget.autoRange = lambda key=key: calls.append(key)

    graph._zoom_reset_button.click()

    assert set(calls) == {"voltage", "current"}


# ---- Scatter (Vernier тәрізді, connect_points=False) ----------------------


def test_connect_points_false_creates_scatter_curve() -> None:
    graph = LiveGraphWidget()

    graph.configure_channels(
        (VOLTAGE, CURRENT), x_channel="current", y_channels=("voltage",), connect_points=False
    )

    curve = graph._curves["voltage"]
    opts = curve.opts
    assert opts["pen"] is None
    assert opts["symbol"] == "o"
    assert opts["symbolSize"] == 8


def test_connect_points_true_default_keeps_line_pen() -> None:
    graph = LiveGraphWidget()

    graph.configure_channels((VOLTAGE, CURRENT), x_channel="current", y_channels=("voltage",))

    curve = graph._curves["voltage"]
    assert curve.opts["pen"] is not None
    assert curve.opts["symbol"] is None


# ---- Dedup (тек graph презентация қабатында) -------------------------------


def test_duplicate_xy_point_within_tolerance_is_not_added_twice() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels(
        (VOLTAGE, CURRENT),
        x_channel="current",
        y_channels=("voltage",),
        dedup_x_tolerance=0.0005,
        dedup_y_tolerance=0.0005,
    )

    graph.append_measurement(_make_measurement(values={"voltage": 5.176, "current": 0.132}))
    graph.append_measurement(_make_measurement(values={"voltage": 5.176, "current": 0.132}))

    assert list(graph._x_data["voltage"]) == [0.132]
    assert list(graph._y_data["voltage"]) == [5.176]


def test_distinct_xy_points_outside_tolerance_are_both_added() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels(
        (VOLTAGE, CURRENT),
        x_channel="current",
        y_channels=("voltage",),
        dedup_x_tolerance=0.0005,
        dedup_y_tolerance=0.0005,
    )

    graph.append_measurement(_make_measurement(values={"voltage": 5.0, "current": 0.1}))
    graph.append_measurement(_make_measurement(values={"voltage": 6.0, "current": 0.2}))

    assert list(graph._x_data["voltage"]) == [0.1, 0.2]


def test_zero_dedup_tolerance_disables_deduplication() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels((VOLTAGE, CURRENT), x_channel="current", y_channels=("voltage",))

    graph.append_measurement(_make_measurement(values={"voltage": 5.0, "current": 0.1}))
    graph.append_measurement(_make_measurement(values={"voltage": 5.0, "current": 0.1}))

    assert list(graph._x_data["voltage"]) == [0.1, 0.1]


# ---- Linear fit (show_fit=True) -------------------------------------------


def test_fit_computes_slope_and_r_squared_for_perfect_line() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels(
        (VOLTAGE, CURRENT),
        x_channel="current",
        y_channels=("voltage",),
        show_fit=True,
        fit_result_prefix="R",
        fit_unit="Ω",
        fit_x_symbol="I",
        fit_y_symbol="U",
    )

    # U = 2*I + 1 — дәл сызықтық, R²=1.0 күтіледі.
    for current in (0.1, 0.2, 0.3, 0.4):
        graph.append_measurement(
            _make_measurement(values={"voltage": 2 * current + 1, "current": current})
        )

    fit_x, fit_y = graph._fit_curves["voltage"].getData()
    assert len(fit_x) == 2
    slope = (fit_y[-1] - fit_y[0]) / (fit_x[-1] - fit_x[0])
    assert slope == pytest.approx(2.0, abs=1e-6)
    fit_text = graph._fit_body_label.text()
    assert "R = 2.000 Ω" in fit_text
    assert "R² = 1.000" in fit_text
    assert "U = 2.000·I + 1.000" in fit_text
    assert not graph._fit_panel.isHidden()


def test_fit_shows_warning_when_slope_is_not_positive() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels(
        (VOLTAGE, CURRENT),
        x_channel="current",
        y_channels=("voltage",),
        show_fit=True,
        fit_result_prefix="R",
        fit_unit="Ω",
    )

    # U = -1*I + 5 — теріс slope, физикалық мағынасыз R.
    for current in (0.1, 0.2, 0.3):
        graph.append_measurement(
            _make_measurement(values={"voltage": -1 * current + 5, "current": current})
        )

    fit_text = graph._fit_body_label.text()
    assert "R = -1.000 Ω" in fit_text
    assert "Физикалық модельге сәйкес келмейді" in fit_text


def test_fit_requires_at_least_three_points() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels(
        (VOLTAGE, CURRENT), x_channel="current", y_channels=("voltage",), show_fit=True
    )

    graph.append_measurement(_make_measurement(values={"voltage": 1.0, "current": 0.1}))
    graph.append_measurement(_make_measurement(values={"voltage": 2.0, "current": 0.2}))

    fit_x, _ = graph._fit_curves["voltage"].getData()
    assert fit_x is None or len(fit_x) == 0
    assert graph._fit_body_label.text() == "Кемінде 3 нүкте сақтаңыз"


def test_fit_not_shown_with_single_distinct_x_value() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels(
        (VOLTAGE, CURRENT), x_channel="current", y_channels=("voltage",), show_fit=True
    )

    graph.append_measurement(_make_measurement(values={"voltage": 5.0, "current": 0.1}))

    fit_x, _ = graph._fit_curves["voltage"].getData()
    assert fit_x is None or len(fit_x) == 0
    assert graph._fit_body_label.text() == "Кемінде 3 нүкте сақтаңыз"


def test_fit_disabled_by_default() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels((VOLTAGE, CURRENT), x_channel="current", y_channels=("voltage",))

    assert graph._fit_curves == {}


def test_clear_resets_fit_line_and_panel() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels(
        (VOLTAGE, CURRENT), x_channel="current", y_channels=("voltage",), show_fit=True
    )
    graph.append_measurement(_make_measurement(values={"voltage": 5.0, "current": 0.1}))
    graph.append_measurement(_make_measurement(values={"voltage": 6.0, "current": 0.2}))
    graph.append_measurement(_make_measurement(values={"voltage": 7.0, "current": 0.3}))

    graph.clear()

    fit_x, _ = graph._fit_curves["voltage"].getData()
    assert fit_x is None or len(fit_x) == 0
    assert graph._fit_body_label.text() == "Кемінде 3 нүкте сақтаңыз"


# ---- Manual point capture (Vernier тәрізді "Нүктені сақтау" workflow) -----


def _configure_capture_graph(
    graph: LiveGraphWidget,
    *,
    capture_x_tolerance: float = 0.002,
    capture_y_tolerance: float = 0.02,
    capture_sample_count: int = 10,
    show_fit: bool = False,
    dedup_x_tolerance: float = 0.0,
    dedup_y_tolerance: float = 0.0,
) -> None:
    graph.configure_channels(
        (VOLTAGE, CURRENT),
        x_channel="current",
        y_channels=("voltage",),
        capture_mode=True,
        capture_sample_count=capture_sample_count,
        capture_x_tolerance=capture_x_tolerance,
        capture_y_tolerance=capture_y_tolerance,
        show_fit=show_fit,
        dedup_x_tolerance=dedup_x_tolerance,
        dedup_y_tolerance=dedup_y_tolerance,
    )


def test_capture_mode_raw_measurement_does_not_reach_graph() -> None:
    graph = LiveGraphWidget()
    _configure_capture_graph(graph)

    for _ in range(5):
        graph.append_measurement(_make_measurement(values={"voltage": 5.0, "current": 0.132}))

    assert list(graph._x_data["voltage"]) == []
    assert list(graph._y_data["voltage"]) == []
    assert len(graph._capture_samples) == 5


def test_capture_button_disabled_without_running_or_samples() -> None:
    graph = LiveGraphWidget()
    _configure_capture_graph(graph)

    assert graph._capture_button.isEnabled() is False

    graph.set_capture_running(True)
    assert graph._capture_button.isEnabled() is False  # буфер әлі бос

    graph.append_measurement(_make_measurement(values={"voltage": 5.0, "current": 0.132}))
    assert graph._capture_button.isEnabled() is True

    graph.set_capture_running(False)
    assert graph._capture_button.isEnabled() is False


def test_unstable_samples_do_not_produce_a_captured_point() -> None:
    graph = LiveGraphWidget()
    _configure_capture_graph(graph)
    graph.set_capture_running(True)
    statuses: list[str] = []
    graph.capture_status.connect(statuses.append)

    # current spread 0.01 > 0.002 tolerance — тұрақсыз.
    for current in (0.10, 0.11, 0.12):
        graph.append_measurement(_make_measurement(values={"voltage": 5.0, "current": current}))

    graph._on_capture_clicked()

    assert list(graph._x_data["voltage"]) == []
    assert statuses[-1] == "Мән тұрақталған жоқ. Бірнеше секунд күтіңіз."


def test_stable_samples_produce_a_captured_point_with_mean_values() -> None:
    graph = LiveGraphWidget()
    _configure_capture_graph(graph)
    graph.set_capture_running(True)

    for voltage, current in ((5.170, 0.1319), (5.180, 0.1321), (5.176, 0.1320)):
        graph.append_measurement(
            _make_measurement(values={"voltage": voltage, "current": current})
        )

    graph._on_capture_clicked()

    assert list(graph._x_data["voltage"]) == pytest.approx([0.132], abs=1e-3)
    assert list(graph._y_data["voltage"]) == pytest.approx([5.1753], abs=1e-3)


def test_capture_with_no_samples_emits_no_data_status() -> None:
    graph = LiveGraphWidget()
    _configure_capture_graph(graph)
    graph.set_capture_running(True)
    statuses: list[str] = []
    graph.capture_status.connect(statuses.append)

    graph._on_capture_clicked()

    assert statuses == ["Деректер жоқ."]
    assert list(graph._x_data["voltage"]) == []


def test_capture_near_zero_x_average_is_rejected() -> None:
    graph = LiveGraphWidget()
    _configure_capture_graph(graph)
    graph.set_capture_running(True)
    statuses: list[str] = []
    graph.capture_status.connect(statuses.append)

    for _ in range(3):
        graph.append_measurement(_make_measurement(values={"voltage": 0.001, "current": 0.0}))

    graph._on_capture_clicked()

    assert statuses[-1] == "Мән нөлге тым жақын — нүкте сақталмады."
    assert list(graph._x_data["voltage"]) == []


def test_duplicate_captured_point_is_rejected_and_reported() -> None:
    graph = LiveGraphWidget()
    _configure_capture_graph(graph, dedup_x_tolerance=0.0005, dedup_y_tolerance=0.0005)
    graph.set_capture_running(True)
    statuses: list[str] = []
    graph.capture_status.connect(statuses.append)

    for _ in range(3):
        graph.append_measurement(_make_measurement(values={"voltage": 5.176, "current": 0.132}))
    graph._on_capture_clicked()
    assert len(graph._x_data["voltage"]) == 1

    for _ in range(3):
        graph.append_measurement(_make_measurement(values={"voltage": 5.176, "current": 0.132}))
    graph._on_capture_clicked()

    assert len(graph._x_data["voltage"]) == 1  # екінші рет қосылмады
    assert statuses[-1] == "Бұл нүкте алдыңғы сақталған нүктеге тым жақын — қосылмады."


def test_fit_uses_only_captured_points_synthetic_r_100_ohm() -> None:
    graph = LiveGraphWidget()
    _configure_capture_graph(
        graph, show_fit=True, dedup_x_tolerance=0.0005, dedup_y_tolerance=0.0005
    )
    graph.set_capture_running(True)

    # R≈100Ω синтетикалық дерек, талап 16-дағы сценарий.
    points = [
        (0.010, 1.01),
        (0.020, 2.00),
        (0.030, 3.02),
        (0.040, 3.99),
        (0.050, 5.01),
    ]
    for current, voltage in points:
        for _ in range(3):  # тұрақтылық үшін буферде бірнеше бірдей үлгі
            graph.append_measurement(
                _make_measurement(values={"voltage": voltage, "current": current})
            )
        graph._on_capture_clicked()

    assert len(graph._x_data["voltage"]) == 5

    fit_x, fit_y = graph._fit_curves["voltage"].getData()
    slope = (fit_y[-1] - fit_y[0]) / (fit_x[-1] - fit_x[0])
    assert slope == pytest.approx(100.0, rel=0.05)
    fit_text = graph._fit_body_label.text()
    assert "R² = " in fit_text


def test_capture_hint_visible_until_first_point_then_hidden() -> None:
    graph = LiveGraphWidget()
    _configure_capture_graph(graph)
    graph.set_capture_running(True)

    assert not graph._hint_label.isHidden()

    for _ in range(3):
        graph.append_measurement(_make_measurement(values={"voltage": 5.0, "current": 0.132}))
    graph._on_capture_clicked()

    assert graph._hint_label.isHidden()


def test_capture_hint_hidden_when_not_capture_mode() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels((VOLTAGE, CURRENT), x_channel="current", y_channels=("voltage",))

    assert graph._hint_label.isHidden()


def test_checkbox_row_hidden_in_capture_mode() -> None:
    graph = LiveGraphWidget()
    _configure_capture_graph(graph)

    assert graph._checkboxes == {}


def test_clear_resets_captured_points_and_buffer_and_hint() -> None:
    graph = LiveGraphWidget()
    _configure_capture_graph(graph)
    graph.set_capture_running(True)
    for _ in range(3):
        graph.append_measurement(_make_measurement(values={"voltage": 5.0, "current": 0.132}))
    graph._on_capture_clicked()
    assert len(graph._x_data["voltage"]) == 1

    graph.clear()

    assert list(graph._x_data["voltage"]) == []
    assert len(graph._capture_samples) == 0
    assert not graph._hint_label.isHidden()


def test_capture_mode_false_preserves_automatic_v1_behavior() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels((VOLTAGE, CURRENT), x_channel="current", y_channels=("voltage",))

    graph.append_measurement(_make_measurement(values={"voltage": 5.0, "current": 0.1}))

    assert list(graph._x_data["voltage"]) == [0.1]
    assert graph._capture_button.isHidden()


# ---- Dual stacked time-series graph (V3, "Электр тізбегін құрастыру
# және ток күшін өлшеу") --------------------------------------------------


def _configure_stacked_graph(graph: LiveGraphWidget) -> None:
    graph.configure_channels(
        (VOLTAGE, CURRENT),
        x_channel=None,
        y_channels=("voltage", "current"),
        x_label="Уақыт, t",
        stacked=True,
        stacked_titles={
            "voltage": "Кернеудің уақыт бойынша өзгерісі",
            "current": "Ток күшінің уақыт бойынша өзгерісі",
        },
        stacked_y_labels={"voltage": "Кернеу, U", "current": "Ток күші, I"},
    )


def test_stacked_creates_one_plot_widget_per_channel() -> None:
    graph = LiveGraphWidget()

    _configure_stacked_graph(graph)

    assert set(graph._stacked_plot_widgets.keys()) == {"voltage", "current"}
    assert graph._plot_widget is None


def test_stacked_plots_share_linked_x_axis() -> None:
    graph = LiveGraphWidget()

    _configure_stacked_graph(graph)

    voltage_item = graph._stacked_plot_widgets["voltage"].getPlotItem()
    current_item = graph._stacked_plot_widgets["current"].getPlotItem()
    assert current_item.getViewBox().linkedView(0) is voltage_item.getViewBox()


def test_stacked_plot_titles_and_y_labels() -> None:
    graph = LiveGraphWidget()

    _configure_stacked_graph(graph)

    voltage_plot = graph._stacked_plot_widgets["voltage"]
    current_plot = graph._stacked_plot_widgets["current"]
    assert "Кернеудің уақыт бойынша өзгерісі" in voltage_plot.getPlotItem().titleLabel.text
    assert "Ток күшінің уақыт бойынша өзгерісі" in current_plot.getPlotItem().titleLabel.text
    assert voltage_plot.getAxis("left").labelText == "Кернеу, U"
    assert current_plot.getAxis("left").labelText == "Ток күші, I"


def test_stacked_only_last_plot_shows_x_label() -> None:
    graph = LiveGraphWidget()

    _configure_stacked_graph(graph)

    voltage_axis = graph._stacked_plot_widgets["voltage"].getAxis("bottom")
    current_axis = graph._stacked_plot_widgets["current"].getAxis("bottom")
    assert voltage_axis.labelText == ""
    assert current_axis.labelText == "Уақыт, t"


def test_stacked_has_no_checkboxes_or_capture_or_fit_ui() -> None:
    graph = LiveGraphWidget()

    _configure_stacked_graph(graph)

    assert graph._checkboxes == {}
    assert graph._capture_button.isHidden()
    assert graph._fit_toggle_checkbox.isHidden()
    assert graph._fit_panel.isHidden()


def test_stacked_append_measurement_updates_both_plots() -> None:
    graph = LiveGraphWidget()
    _configure_stacked_graph(graph)
    started_at = datetime.now(timezone.utc)

    for index, (voltage, current) in enumerate(
        ((1.0, 0.01), (2.0, 0.02), (3.0, 0.03))
    ):
        graph.append_measurement(
            _make_measurement(
                values={"voltage": voltage, "current": current},
                timestamp=started_at + timedelta(seconds=index),
            )
        )

    assert list(graph._y_data["voltage"]) == [1.0, 2.0, 3.0]
    assert list(graph._y_data["current"]) == [0.01, 0.02, 0.03]
    assert list(graph._x_data["voltage"]) == pytest.approx([0.0, 1.0, 2.0])


def test_stacked_autoscale_checkbox_affects_both_plots() -> None:
    graph = LiveGraphWidget()
    _configure_stacked_graph(graph)
    voltage_view_box = graph._stacked_plot_widgets["voltage"].getViewBox()
    current_view_box = graph._stacked_plot_widgets["current"].getViewBox()
    # current-тың X осі voltage-ге setXLink() арқылы байланған — өз алдына
    # X-autoRange-і pyqtgraph-та әрдайым False (X диапазонын master
    # анықтайды), тек Y autoRange тәуелсіз ауыстырылады.
    assert all(voltage_view_box.autoRangeEnabled())
    assert current_view_box.autoRangeEnabled()[1] is True

    graph._auto_scale_checkbox.setChecked(False)

    assert not any(voltage_view_box.autoRangeEnabled())
    assert current_view_box.autoRangeEnabled()[1] is False


def test_stacked_clear_resets_both_plots() -> None:
    graph = LiveGraphWidget()
    _configure_stacked_graph(graph)
    graph.append_measurement(_make_measurement(values={"voltage": 1.0, "current": 0.01}))

    graph.clear()

    assert list(graph._y_data["voltage"]) == []
    assert list(graph._y_data["current"]) == []


def test_reconfigure_from_stacked_to_single_plot_tears_down_stacked_widgets() -> None:
    graph = LiveGraphWidget()
    _configure_stacked_graph(graph)
    assert graph._stacked_plot_widgets

    graph.configure_channels((VOLTAGE, CURRENT), x_channel="current", y_channels=("voltage",))

    assert graph._stacked_plot_widgets == {}
    assert graph._plot_widget is not None


def test_non_stacked_time_series_unaffected_by_stacked_feature() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels((VOLTAGE,), x_channel=None, y_channels=("voltage",))

    assert graph._stacked_plot_widgets == {}
    assert graph._plot_widget is not None


# ---- Axis label / title override -------------------------------------------


def test_x_and_y_label_overrides_are_applied() -> None:
    graph = LiveGraphWidget()

    graph.configure_channels(
        (VOLTAGE, CURRENT),
        x_channel="current",
        y_channels=("voltage",),
        x_label="Ток, I",
        y_label="Кернеу, U",
    )

    bottom_axis = graph._plot_widget.getAxis("bottom")
    left_axis = graph._plot_widget.getAxis("left")
    assert bottom_axis.labelText == "Ток, I"
    assert bottom_axis.labelUnits == "A"
    assert left_axis.labelText == "Кернеу, U"
    assert left_axis.labelUnits == "V"


def test_axis_label_falls_back_to_display_name_without_override() -> None:
    graph = LiveGraphWidget()

    graph.configure_channels((VOLTAGE, CURRENT), x_channel="current", y_channels=("voltage",))

    left_axis = graph._plot_widget.getAxis("left")
    assert left_axis.labelText == "Кернеу"


def test_graph_title_is_applied_when_configured() -> None:
    graph = LiveGraphWidget()

    graph.configure_channels(
        (VOLTAGE, CURRENT),
        x_channel="current",
        y_channels=("voltage",),
        title="Кернеудің ток күшіне тәуелділігі",
    )

    assert "Кернеудің ток күшіне тәуелділігі" in graph._plot_widget.getPlotItem().titleLabel.text


def test_no_title_by_default() -> None:
    graph = LiveGraphWidget()

    graph.configure_channels((VOLTAGE, CURRENT), x_channel="current", y_channels=("voltage",))

    assert graph._plot_widget.getPlotItem().titleLabel.text == ""


# ---- 10 000 нүктелік шектеу ----------------------------------------------


def test_point_limit_is_ten_thousand() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels((VOLTAGE,), x_channel=None, y_channels=("voltage",))
    started_at = datetime.now(timezone.utc)

    for index in range(10_050):
        graph.append_measurement(
            _make_measurement(
                values={"voltage": float(index)},
                timestamp=started_at + timedelta(seconds=index),
            )
        )

    assert len(graph._y_data["voltage"]) == 10_000
    # Ескі нүктелер (deque maxlen) шыға беруі керек — соңғы мән әлі дұрыс.
    assert graph._y_data["voltage"][-1] == 10_049.0


# ---- Phase 32: shared workspace layout architecture -----------------------


def test_widget_has_expanding_size_policy_both_directions() -> None:
    graph = LiveGraphWidget()
    policy = graph.sizePolicy()
    assert policy.horizontalPolicy() == QSizePolicy.Policy.Expanding
    assert policy.verticalPolicy() == QSizePolicy.Policy.Expanding


def test_single_plot_widget_has_expanding_size_policy() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels((VOLTAGE,), x_channel=None, y_channels=("voltage",))
    policy = graph._plot_widget.sizePolicy()
    assert policy.horizontalPolicy() == QSizePolicy.Policy.Expanding
    assert policy.verticalPolicy() == QSizePolicy.Policy.Expanding


def test_single_plot_widget_receives_stretch_in_container_layout() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels((VOLTAGE,), x_channel=None, y_channels=("voltage",))
    layout = graph._plot_container_layout
    index = layout.indexOf(graph._plot_widget)
    assert index != -1
    assert layout.stretch(index) == 1


def test_stacked_plot_widgets_have_expanding_policy_and_equal_stretch() -> None:
    """Stacked режимде әр subplot тең stretch=1 алады — ешқайсысына
    фиксед height берілмейді, қолжетімді биіктік тең бөлінеді.
    """
    graph = LiveGraphWidget()
    _configure_stacked_graph(graph)

    layout = graph._plot_container_layout
    for plot_widget in graph._stacked_plot_widgets.values():
        policy = plot_widget.sizePolicy()
        assert policy.horizontalPolicy() == QSizePolicy.Policy.Expanding
        assert policy.verticalPolicy() == QSizePolicy.Policy.Expanding

        index = layout.indexOf(plot_widget)
        assert index != -1
        assert layout.stretch(index) == 1


# ---- Phase 33A: Scientific Graph Core ------------------------------------
#
# Shared graph core: crosshair/coordinate readout (nearest REAL sample
# only — no interpolation, no fake points), synchronized stacked-graph
# cursor, latest-point marker (only for actually plotted points, never
# the raw capture-mode streaming buffer), zoom/pan interaction modes
# (native pyqtgraph ViewBox), Auto/Follow-Live vs manual interaction,
# Reset View (never clears data), and Maximize/Restore (pure signal,
# layout owned by MeasurementWorkspace).


def test_crosshair_created_for_single_plot_widget() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels((VOLTAGE,), x_channel=None, y_channels=("voltage",))
    assert "__single__" in graph._crosshairs


def test_crosshairs_created_per_stacked_subplot() -> None:
    graph = LiveGraphWidget()
    _configure_stacked_graph(graph)
    assert set(graph._crosshairs.keys()) == {"voltage", "current"}


def test_stacked_crosshair_hover_synchronizes_other_subplots() -> None:
    """§6: бір subplot hover етілгенде, БАСҚА subplot-тар ДӘЛ СОЛ X-те
    (өз нақты деректерінен) crosshair көрсетуі керек — эксперимент ID-ге
    тәуелсіз, тек ``stacked=True`` шартына негізделген.
    """
    graph = LiveGraphWidget()
    _configure_stacked_graph(graph)
    graph.append_measurement(_make_measurement(values={"voltage": 5.0, "current": 0.5}))

    calls: list[float] = []
    graph._crosshairs["current"].show_at_x = calls.append

    graph._on_stacked_crosshair_hover("voltage", 3.7)

    assert calls == [3.7]
    # Өзінің crosshair-і қайта шақырылмайды (тек БАСҚАЛАРЫ).
    assert "voltage" not in graph._crosshairs or calls.count(3.7) == 1


def test_stacked_crosshair_hover_does_not_notify_source_itself() -> None:
    graph = LiveGraphWidget()
    _configure_stacked_graph(graph)

    voltage_calls: list[float] = []
    graph._crosshairs["voltage"].show_at_x = voltage_calls.append

    graph._on_stacked_crosshair_hover("voltage", 2.0)

    assert voltage_calls == []


def test_latest_marker_updates_on_new_point() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels((VOLTAGE,), x_channel=None, y_channels=("voltage",))

    graph.append_measurement(_make_measurement(values={"voltage": 5.5}))

    marker = graph._latest_markers["voltage"]
    data = marker.getData()
    assert list(data[1]) == [5.5]


def test_latest_marker_tracks_the_newest_point_only() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels((VOLTAGE,), x_channel=None, y_channels=("voltage",))

    for value in (1.0, 2.0, 3.0):
        graph.append_measurement(_make_measurement(values={"voltage": value}))

    marker = graph._latest_markers["voltage"]
    assert list(marker.getData()[1]) == [3.0]


def test_latest_marker_not_updated_by_raw_capture_buffer() -> None:
    """§7: capture_mode графиктерде continuous stream ЕШҚАШАН "captured"
    ретінде белгіленбейді — тек нақты "Нүктені сақтау" арқылы қосылған
    нүкте ғана маркер алады.
    """
    graph = LiveGraphWidget()
    graph.configure_channels(
        (VOLTAGE, CURRENT),
        x_channel="current",
        y_channels=("voltage",),
        capture_mode=True,
        capture_sample_count=3,
        capture_x_tolerance=1.0,
        capture_y_tolerance=1.0,
    )

    for _ in range(5):
        graph.append_measurement(_make_measurement(values={"voltage": 5.0, "current": 0.5}))

    marker = graph._latest_markers["voltage"]
    assert list(marker.getData()[0]) == []  # raw buffer ЕШҚАШАН маркерге ілінбейді

    graph._on_capture_clicked()  # енді нақты captured point қосылады

    assert list(marker.getData()[0]) == [0.5]


def test_zoom_mode_button_sets_rect_mode() -> None:
    import pyqtgraph as pg

    graph = LiveGraphWidget()
    graph.configure_channels((VOLTAGE,), x_channel=None, y_channels=("voltage",))

    graph._zoom_mode_button.click()

    assert graph._plot_widget.getViewBox().state["mouseMode"] == pg.ViewBox.RectMode


def test_pan_mode_button_sets_pan_mode() -> None:
    import pyqtgraph as pg

    graph = LiveGraphWidget()
    graph.configure_channels((VOLTAGE,), x_channel=None, y_channels=("voltage",))
    graph._zoom_mode_button.click()

    graph._pan_mode_button.click()

    assert graph._plot_widget.getViewBox().state["mouseMode"] == pg.ViewBox.PanMode


def test_mouse_mode_persists_across_reconfigure() -> None:
    """Zoom/Pan режимі тәжірибе ауысқанда да сақталуы керек — жаңа
    plot widget(тер) құрылғанда ағымдағы режим қайта қолданылады.
    """
    import pyqtgraph as pg

    graph = LiveGraphWidget()
    graph.configure_channels((VOLTAGE,), x_channel=None, y_channels=("voltage",))
    graph._zoom_mode_button.click()

    graph.configure_channels((CURRENT,), x_channel=None, y_channels=("current",))

    assert graph._plot_widget.getViewBox().state["mouseMode"] == pg.ViewBox.RectMode


def test_manual_range_change_disables_auto_scale_checkbox() -> None:
    """§8/§9/§10: "The user must never zoom in only for the next
    incoming sample to immediately reset the view" — қолмен zoom/pan
    pyqtgraph-тың НАҚТЫ ``sigRangeChangedManually`` сигналы арқылы
    Автоауқым-ды автоматты өшіреді.
    """
    graph = LiveGraphWidget()
    graph.configure_channels((VOLTAGE,), x_channel=None, y_channels=("voltage",))
    assert graph._auto_scale_checkbox.isChecked() is True

    graph._on_range_changed_manually()

    assert graph._auto_scale_checkbox.isChecked() is False
    assert list(graph._plot_widget.getViewBox().autoRangeEnabled()) == [False, False]


def test_auto_checkbox_restores_autorange_without_clearing_data() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels((VOLTAGE,), x_channel=None, y_channels=("voltage",))
    graph.append_measurement(_make_measurement(values={"voltage": 4.2}))
    graph._on_range_changed_manually()  # Auto өшеді
    assert graph._auto_scale_checkbox.isChecked() is False

    graph._auto_scale_checkbox.setChecked(True)  # §10: Auto басу

    assert list(graph._plot_widget.getViewBox().autoRangeEnabled()) != [False, False]
    # §10: "Do NOT clear data when Auto is pressed" — дерек сақталды.
    assert len(graph._x_data["voltage"]) == 1
    assert list(graph._y_data["voltage"]) == [4.2]


def test_reset_view_does_not_clear_data() -> None:
    """§11: Reset View мен Clear Data МҮЛДЕ бөлек әрекеттер."""
    graph = LiveGraphWidget()
    graph.configure_channels((VOLTAGE,), x_channel=None, y_channels=("voltage",))
    graph.append_measurement(_make_measurement(values={"voltage": 1.0}))
    graph.append_measurement(_make_measurement(values={"voltage": 2.0}))

    graph._on_zoom_reset_clicked()

    assert list(graph._y_data["voltage"]) == [1.0, 2.0]


def test_maximize_button_emits_maximize_toggled_signal() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels((VOLTAGE,), x_channel=None, y_channels=("voltage",))
    received: list[bool] = []
    graph.maximize_toggled.connect(received.append)

    graph._maximize_button.click()
    graph._maximize_button.click()

    assert received == [True, False]


def test_maximize_does_not_alter_graph_data() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels((VOLTAGE,), x_channel=None, y_channels=("voltage",))
    graph.append_measurement(_make_measurement(values={"voltage": 9.0}))

    graph._maximize_button.click()

    assert list(graph._y_data["voltage"]) == [9.0]


def test_escape_restores_from_maximize() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels((VOLTAGE,), x_channel=None, y_channels=("voltage",))
    graph._maximize_button.setChecked(True)

    graph._on_escape_pressed()

    assert graph._maximize_button.isChecked() is False


def test_escape_is_noop_when_not_maximized() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels((VOLTAGE,), x_channel=None, y_channels=("voltage",))

    graph._on_escape_pressed()  # exception шықпауы керек

    assert graph._maximize_button.isChecked() is False


def test_devices_ready_changes_empty_state_message() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels((VOLTAGE,), x_channel=None, y_channels=("voltage",))

    graph.set_devices_ready(False)
    assert "құрылғыларды қосыңыз" in graph._empty_state_label.text()

    graph.set_devices_ready(True)
    assert "«Бастау»" in graph._empty_state_label.text()


def test_crosshair_hover_creates_no_measurement_or_session_side_effects() -> None:
    """Crosshair/tooltip тек PRESENTATION — ешбір Measurement/session
    жазбасын жасамайды, тек нақты сақталған x_data/y_data-ны оқиды.
    """
    graph = LiveGraphWidget()
    graph.configure_channels((VOLTAGE,), x_channel=None, y_channels=("voltage",))
    graph.append_measurement(_make_measurement(values={"voltage": 5.0}))
    before_x = list(graph._x_data["voltage"])
    before_y = list(graph._y_data["voltage"])

    graph._crosshairs["__single__"].show_at_x(0.0)
    graph._crosshairs["__single__"].hide()

    assert list(graph._x_data["voltage"]) == before_x
    assert list(graph._y_data["voltage"]) == before_y


# ---- Phase 33A §19: Large dataset behavior -------------------------------


@pytest.mark.parametrize("point_count", [100, 1_000, 5_000])
def test_large_dataset_remains_correct_and_reasonably_fast(point_count: int) -> None:
    """Pixel-perfect емес — тек архитектуралық/уақыт контрактісін
    тексереді: барлық НАҚТЫ өлшеу сақталады (ЕШБІР жасырын decimation),
    ал crosshair hover әдеттегідей жылдам қалады.
    """
    import time

    graph = LiveGraphWidget()
    graph.configure_channels((VOLTAGE,), x_channel=None, y_channels=("voltage",))

    started_at = datetime.now(timezone.utc)
    for index in range(point_count):
        graph.append_measurement(
            _make_measurement(
                values={"voltage": float(index % 1000) / 100.0},
                timestamp=started_at + timedelta(milliseconds=index * 100),
            )
        )

    assert len(graph._x_data["voltage"]) == min(point_count, 10_000)  # _MAX_POINTS cap

    hover_started = time.monotonic()
    graph._crosshairs["__single__"].show_at_x(point_count / 2.0)
    hover_elapsed = time.monotonic() - hover_started

    # Жомарт шек — CI машинасының жылдамдығына тәуелсіз, тек "unusably
    # slow" емес екенін растайды (§19: "hover does not become unusably
    # slow").
    assert hover_elapsed < 1.0


# ---- Phase 33B §18: Region/interval selection & analysis ------------------


def test_region_items_hidden_before_toggle() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels((VOLTAGE,), x_channel=None, y_channels=("voltage",))

    assert graph._region_items["__single__"].isVisible() is False
    assert graph._analysis_panel.isHidden()


def test_region_button_toggle_shows_region_and_panel() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels((VOLTAGE,), x_channel=None, y_channels=("voltage",))
    graph.append_measurement(_make_measurement(values={"voltage": 1.0}))

    graph._region_button.setChecked(True)

    assert graph._region_items["__single__"].isVisible() is True
    assert graph._analysis_panel.isHidden() is False

    graph._region_button.setChecked(False)

    assert graph._region_items["__single__"].isVisible() is False
    assert graph._analysis_panel.isHidden() is True


def test_region_initializes_from_view_range_exactly_once_per_configure() -> None:
    """Регрессия-тесті: ``pg.LinearRegionItem`` values=(0,1) әдепкі мәнімен
    құрылады ((0,0) ЕМЕС), сондықтан ескі "region[0]==region[1]"
    тексеруі алғашқы toggle-де ЕШҚАШАН ЖІБЕРІЛМЕЙТІН еді — нәтижесінде
    аймақ нақты дерек ауқымына сәйкес келмей, статистика/энергия үнемі
    жалған "жеткіліксіз дерек" болып қалатын. Енді ``_region_positions_
    initialized`` жалаушасы арқылы бақыланады.
    """
    graph = LiveGraphWidget()
    graph.configure_channels((VOLTAGE,), x_channel=None, y_channels=("voltage",))
    graph.append_measurement(_make_measurement(values={"voltage": 1.0}))

    call_count = 0
    original = graph._initialize_region_from_view

    def _counting_wrapper() -> None:
        nonlocal call_count
        call_count += 1
        original()

    graph._initialize_region_from_view = _counting_wrapper  # type: ignore[method-assign]

    graph._region_button.setChecked(True)  # 1-ші қосу — инициализация ШАҚЫРЫЛУЫ керек
    graph._recompute_region_analysis()  # қосымша қайта есептеу — ЕКІНШІ РЕТ ШАҚЫРЫЛМАУЫ керек
    graph._region_button.setChecked(False)
    graph._region_button.setChecked(True)  # қайта қосу — позиция САҚТАЛУЫ керек, қайта init ЕМЕС

    assert call_count == 1


def test_region_reinitializes_after_configure_channels_reset() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels((VOLTAGE,), x_channel=None, y_channels=("voltage",))
    graph.append_measurement(_make_measurement(values={"voltage": 1.0}))
    graph._region_button.setChecked(True)

    assert graph._region_positions_initialized is True

    graph.configure_channels((VOLTAGE,), x_channel=None, y_channels=("voltage",))

    assert graph._region_positions_initialized is False
    assert graph._region_button.isChecked() is False


def test_region_drag_syncs_across_stacked_plots() -> None:
    graph = LiveGraphWidget()
    _configure_stacked_graph(graph)
    started_at = datetime.now(timezone.utc)
    for index, (voltage, current) in enumerate(((1.0, 0.01), (2.0, 0.02), (3.0, 0.03))):
        graph.append_measurement(
            _make_measurement(
                values={"voltage": voltage, "current": current},
                timestamp=started_at + timedelta(seconds=index),
            )
        )
    graph._region_button.setChecked(True)

    graph._region_items["voltage"].setRegion((0.5, 1.5))

    assert graph._region_items["current"].getRegion() == pytest.approx((0.5, 1.5))


def test_region_statistics_reflect_only_points_inside_range() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels((VOLTAGE,), x_channel=None, y_channels=("voltage",))
    started_at = datetime.now(timezone.utc)
    for index, voltage in enumerate((1.0, 2.0, 3.0, 4.0, 5.0)):
        graph.append_measurement(
            _make_measurement(
                values={"voltage": voltage},
                timestamp=started_at + timedelta(seconds=index),
            )
        )
    graph._region_button.setChecked(True)

    graph._set_all_regions((1.0, 3.0))  # индекстер 1..3 -> voltage 2.0,3.0,4.0
    graph._recompute_region_analysis()

    summary = graph._last_region_summary
    assert summary is not None
    channel = summary.channels[0]
    assert channel.n == 3
    assert channel.minimum == pytest.approx(2.0)
    assert channel.maximum == pytest.approx(4.0)
    assert channel.average == pytest.approx(3.0)


def test_region_statistics_empty_when_no_points_in_range() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels((VOLTAGE,), x_channel=None, y_channels=("voltage",))
    graph.append_measurement(_make_measurement(values={"voltage": 1.0}))
    graph._region_button.setChecked(True)

    graph._set_all_regions((100.0, 200.0))  # нақты деректен тыс
    graph._recompute_region_analysis()

    channel = graph._last_region_summary.channels[0]
    assert channel.n == 0


def test_regression_scope_toggle_changes_fit_dataset() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels(
        (VOLTAGE, CURRENT), x_channel="current", y_channels=("voltage",), show_fit=True
    )
    # I: 0.1..0.5 -> U = 10*I (сызықтық, тек region ішінде I: 0.1..0.2 -> U = 10*I те болса,
    # ал region сыртында бүлінген (сызықтық емес) нүкте қосамыз.
    for current, voltage in ((0.1, 1.0), (0.2, 2.0), (0.3, 3.0), (0.4, 40.0), (0.5, 5.0)):
        graph.append_measurement(_make_measurement(values={"voltage": voltage, "current": current}))
    graph._region_button.setChecked(True)
    graph._set_all_regions((0.1, 0.3))  # тек алғашқы 3 "таза" нүкте

    graph._analysis_panel._region_only_radio.setChecked(True)
    all_points_r2 = graph._latest_regression_result.r_squared

    graph._analysis_panel._all_points_radio.setChecked(True)
    all_data_r2 = graph._latest_regression_result.r_squared

    assert all_points_r2 == pytest.approx(1.0)
    assert all_data_r2 < 0.99  # бүлінген нүкте fit-ті нашарлатады


def test_regression_defaults_to_all_points_scope() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels(
        (VOLTAGE, CURRENT), x_channel="current", y_channels=("voltage",), show_fit=True
    )

    assert graph._analysis_panel.is_region_only_regression() is False
    assert graph._region_use_only_selection is False


def test_ohms_law_fit_result_unaffected_by_region_being_disabled() -> None:
    """Ohm's Law fit-і region мүлде ІСКЕ ҚОСЫЛМАСА да, ескі мінез-құлықпен
    БІРДЕЙ жұмыс істеуі керек (§9: "extend, do not duplicate").
    """
    graph = LiveGraphWidget()
    graph.configure_channels(
        (VOLTAGE, CURRENT),
        x_channel="current",
        y_channels=("voltage",),
        show_fit=True,
        fit_result_prefix="R",
        fit_unit="Ω",
        fit_x_symbol="I",
        fit_y_symbol="U",
    )
    resistance, intercept = 100.0, 0.02
    for current in (0.01, 0.02, 0.03, 0.04, 0.05):
        graph.append_measurement(
            _make_measurement(values={"voltage": resistance * current + intercept, "current": current})
        )

    fit_text = graph._fit_body_label.text()
    assert "R = 100.000 Ω" in fit_text
    assert "R² = 1.000" in fit_text
    assert graph._region_button.isChecked() is False


def test_power_energy_end_to_end_with_realistic_view_range() -> None:
    """Регрессия-тесті (§18/§22 "prove it"): виджет НАҚТЫ көрсетілгенде
    (``show()`` + ``processEvents()``) — pyqtgraph autorange-і НАҚТЫ дерек
    ауқымын есептейді (headless/көрсетілмеген жағдайда viewRange()
    [0,1]x[0,1] әдепкі күйінде қалады — бұл нақты қосымшада ЕШҚАШАН
    болмайды, себебі MainWindow әрқашан show()-ланған). Аймақ дұрыс
    инициализацияланса, энергия НАҚТЫ (None емес) мән болуы керек.
    """
    graph = LiveGraphWidget()
    graph.configure_channels(
        (VOLTAGE, CURRENT),
        x_channel=None,
        y_channels=("power",),
        derived_analysis=DERIVED_ANALYSIS_POWER_ENERGY,
    )
    graph.resize(900, 500)
    graph.show()
    QApplication.processEvents()
    QApplication.processEvents()
    try:
        started_at = datetime.now(timezone.utc)
        for index in range(20):
            graph.append_measurement(
                _make_measurement(
                    values={"voltage": 5.0, "current": 0.3, "power": 1.5},
                    timestamp=started_at + timedelta(seconds=index),
                )
            )
        QApplication.processEvents()
        graph._region_button.setChecked(True)
        QApplication.processEvents()

        summary = graph._last_region_summary
        assert summary is not None
        assert summary.channels[0].n > 1  # бірнеше НАҚТЫ нүкте аймаққа түсуі керек
        assert summary.energy is not None
        assert summary.power_avg == pytest.approx(1.5)
        assert summary.power_max == pytest.approx(1.5)
    finally:
        graph.close()


def test_power_energy_derived_section_hidden_without_derived_analysis() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels((VOLTAGE,), x_channel=None, y_channels=("voltage",))
    graph.append_measurement(_make_measurement(values={"voltage": 1.0}))
    graph._region_button.setChecked(True)

    assert graph._analysis_panel._derived_section.isVisible() is False


def test_export_analysis_noop_without_region_summary() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels((VOLTAGE,), x_channel=None, y_channels=("voltage",))

    with patch("ui.widgets.live_graph.QFileDialog.getSaveFileName") as mock_dialog:
        graph._on_export_analysis_clicked()

    mock_dialog.assert_not_called()


def test_export_analysis_writes_csv_with_region_data(tmp_path) -> None:
    graph = LiveGraphWidget()
    graph.configure_channels((VOLTAGE,), x_channel=None, y_channels=("voltage",))
    started_at = datetime.now(timezone.utc)
    for index, voltage in enumerate((1.0, 2.0, 3.0)):
        graph.append_measurement(
            _make_measurement(
                values={"voltage": voltage},
                timestamp=started_at + timedelta(seconds=index),
            )
        )
    graph._region_button.setChecked(True)
    graph._set_all_regions((0.0, 2.0))
    graph._recompute_region_analysis()

    output_path = tmp_path / "region_analysis.csv"
    with patch(
        "ui.widgets.live_graph.QFileDialog.getSaveFileName",
        return_value=(str(output_path), "CSV файлдары (*.csv)"),
    ):
        graph._on_export_analysis_clicked()

    assert output_path.exists()
    content = output_path.read_text(encoding="utf-8")
    assert VOLTAGE.display_name in content
    assert "3" in content  # N=3


def test_clear_data_preserves_region_enabled_state_and_refreshes_stats() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels((VOLTAGE,), x_channel=None, y_channels=("voltage",))
    graph.append_measurement(_make_measurement(values={"voltage": 1.0}))
    graph.append_measurement(_make_measurement(values={"voltage": 2.0}))
    graph._region_button.setChecked(True)
    graph._set_all_regions((0.0, 1.0))
    graph._recompute_region_analysis()
    assert graph._last_region_summary.channels[0].n > 0

    graph.clear()

    assert graph._region_button.isChecked() is True  # region өшірілмейді
    assert graph._region_items["__single__"].isVisible() is True
    assert graph._last_region_summary.channels[0].n == 0  # бірақ дерек тазарды


# =====================================================================
# Phase 34: A/B two-point Δ measurement tool
# =====================================================================


def test_delta_button_hidden_by_default() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels((VOLTAGE,), x_channel=None, y_channels=("voltage",))
    assert graph._delta_button.isHidden()


def test_delta_button_visible_when_allowed() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels(
        (VOLTAGE,), x_channel=None, y_channels=("voltage",), allow_delta_measurement=True
    )
    assert not graph._delta_button.isHidden()


def test_delta_cursor_snaps_to_nearest_real_sample_not_interpolated() -> None:
    """Ешбір интерполяция ЖОҚ: 1.0-ден 2.0-ге дейінгі аралықтағы X
    таргетке cursor қойылса, нәтиже НАҚТЫ сақталған екі нүктенің
    ЕҢ ЖАҚЫНЫНА тең болуы тиіс, ешбір "аралық" мән ЕШҚАШАН ойдан
    шығарылмайды.
    """
    graph = LiveGraphWidget()
    graph.configure_channels(
        (VOLTAGE,), x_channel=None, y_channels=("voltage",), allow_delta_measurement=True
    )
    started_at = datetime.now(timezone.utc)
    graph.append_measurement(
        _make_measurement(values={"voltage": 1.0}, timestamp=started_at)
    )
    graph.append_measurement(
        _make_measurement(values={"voltage": 9.0}, timestamp=started_at + timedelta(seconds=2))
    )
    graph._delta_button.setChecked(True)

    graph._place_delta_cursor(0.9)  # 0.0 секундқа жақынырақ

    resolved_x, values_at_x = graph._delta_cursor_a
    assert resolved_x == pytest.approx(0.0)
    assert values_at_x["voltage"] == pytest.approx(1.0)


def test_delta_cursor_a_then_b_then_cycles_to_new_a() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels(
        (VOLTAGE,), x_channel=None, y_channels=("voltage",), allow_delta_measurement=True
    )
    started_at = datetime.now(timezone.utc)
    for index, voltage in enumerate((1.0, 2.0, 3.0)):
        graph.append_measurement(
            _make_measurement(values={"voltage": voltage}, timestamp=started_at + timedelta(seconds=index))
        )
    graph._delta_button.setChecked(True)

    graph._place_delta_cursor(0.0)
    assert graph._delta_cursor_a is not None
    assert graph._delta_cursor_b is None

    graph._place_delta_cursor(2.0)
    assert graph._delta_cursor_a[0] == pytest.approx(0.0)
    assert graph._delta_cursor_b[0] == pytest.approx(2.0)

    graph._place_delta_cursor(1.0)  # үшінші клик — A/B циклі қайталанады
    assert graph._delta_cursor_a[0] == pytest.approx(1.0)
    assert graph._delta_cursor_b is None


def test_delta_clear_button_resets_cursors() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels(
        (VOLTAGE,), x_channel=None, y_channels=("voltage",), allow_delta_measurement=True
    )
    graph.append_measurement(_make_measurement(values={"voltage": 1.0}))
    graph._delta_button.setChecked(True)
    graph._place_delta_cursor(0.0)

    graph._on_delta_clear_clicked()

    assert graph._delta_cursor_a is None
    assert graph._delta_cursor_b is None
    assert graph._delta_body_label.text() == "Графикте A нүктесін таңдау үшін басыңыз."


def test_delta_and_region_are_mutually_exclusive() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels(
        (VOLTAGE,), x_channel=None, y_channels=("voltage",), allow_delta_measurement=True
    )

    graph._region_button.setChecked(True)
    graph._delta_button.setChecked(True)
    assert graph._region_button.isChecked() is False
    assert graph._delta_button.isChecked() is True

    graph._region_button.setChecked(True)
    assert graph._delta_button.isChecked() is False
    assert graph._region_button.isChecked() is True


def test_delta_mode_forces_pan_mouse_mode() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels(
        (VOLTAGE,), x_channel=None, y_channels=("voltage",), allow_delta_measurement=True
    )
    graph._zoom_mode_button.setChecked(True)
    graph._apply_mouse_mode(pg.ViewBox.RectMode)

    graph._delta_button.setChecked(True)

    assert graph._pan_mode_button.isChecked() is True
    assert graph._mouse_mode == pg.ViewBox.PanMode


def test_delta_panel_shows_ab_ratio_for_single_curve_xy_graph() -> None:
    """Ohm's Law тәрізді сценарий: I-U график, ΔU/ΔI = R көрсетілуі тиіс."""
    graph = LiveGraphWidget()
    graph.configure_channels(
        (VOLTAGE, CURRENT),
        x_channel="current",
        y_channels=("voltage",),
        show_fit=True,
        fit_x_symbol="I",
        fit_y_symbol="U",
        fit_unit="Ω",
        allow_delta_measurement=True,
    )
    graph.append_measurement(_make_measurement(values={"voltage": 1.75, "current": 0.020}))
    graph.append_measurement(_make_measurement(values={"voltage": 7.01, "current": 0.081}))
    graph._delta_button.setChecked(True)

    graph._place_delta_cursor(0.020)
    graph._place_delta_cursor(0.081)

    text = graph._delta_body_label.text()
    assert "ΔI" in text
    assert "ΔU" in text
    assert "ΔU/ΔI" in text
    expected_ratio = (7.01 - 1.75) / (0.081 - 0.020)
    assert f"{expected_ratio:.3f}" in text


def test_stacked_delta_cursor_synchronizes_across_subplots() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels(
        (VOLTAGE, CURRENT),
        x_channel=None,
        y_channels=("voltage", "current"),
        stacked=True,
        allow_delta_measurement=True,
    )
    started_at = datetime.now(timezone.utc)
    for index, (voltage, current) in enumerate(((1.0, 0.01), (2.0, 0.02), (3.0, 0.03))):
        graph.append_measurement(
            _make_measurement(
                values={"voltage": voltage, "current": current},
                timestamp=started_at + timedelta(seconds=index),
            )
        )
    graph._delta_button.setChecked(True)

    graph._place_delta_cursor(1.0)

    resolved_x, values_at_x = graph._delta_cursor_a
    assert resolved_x == pytest.approx(1.0)
    assert values_at_x["voltage"] == pytest.approx(2.0)
    assert values_at_x["current"] == pytest.approx(0.02)


def test_delta_multi_channel_summary_shows_per_channel_delta() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels(
        (VOLTAGE, CURRENT),
        x_channel=None,
        y_channels=("voltage", "current"),
        stacked=True,
        allow_delta_measurement=True,
    )
    started_at = datetime.now(timezone.utc)
    graph.append_measurement(
        _make_measurement(values={"voltage": 5.61, "current": 0.066}, timestamp=started_at)
    )
    graph.append_measurement(
        _make_measurement(
            values={"voltage": 6.82, "current": 0.079},
            timestamp=started_at + timedelta(seconds=13.2),
        )
    )
    graph._delta_button.setChecked(True)

    graph._place_delta_cursor(0.0)
    graph._place_delta_cursor(13.2)

    text = graph._delta_body_label.text()
    assert "Δt" in text
    assert f"{6.82 - 5.61:.3f}" in text
    assert f"{0.079 - 0.066:.3f}" in text


def test_delta_state_resets_on_clear() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels(
        (VOLTAGE,), x_channel=None, y_channels=("voltage",), allow_delta_measurement=True
    )
    graph.append_measurement(_make_measurement(values={"voltage": 1.0}))
    graph._delta_button.setChecked(True)
    graph._place_delta_cursor(0.0)
    assert graph._delta_cursor_a is not None

    graph.clear()

    assert graph._delta_cursor_a is None
    assert graph._delta_cursor_b is None


def test_delta_cursor_placement_never_appends_raw_samples() -> None:
    """Критикалық ғылыми integrity тест: A/B cursor қою raw _x_data/
    _y_data-ды ЕШҚАШАН өзгертпеуі тиіс — тек ОҚУ, ешбір fake нүкте
    жасалмайды.
    """
    graph = LiveGraphWidget()
    graph.configure_channels(
        (VOLTAGE,), x_channel=None, y_channels=("voltage",), allow_delta_measurement=True
    )
    graph.append_measurement(_make_measurement(values={"voltage": 1.0}))
    graph.append_measurement(_make_measurement(values={"voltage": 2.0}))
    before_x = list(graph._x_data["voltage"])
    before_y = list(graph._y_data["voltage"])
    graph._delta_button.setChecked(True)

    graph._place_delta_cursor(0.0)
    graph._place_delta_cursor(1.0)

    assert list(graph._x_data["voltage"]) == before_x
    assert list(graph._y_data["voltage"]) == before_y


# =====================================================================
# Phase 34: residual analysis plot
# =====================================================================


def test_residual_toggle_hidden_unless_show_fit() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels((VOLTAGE,), x_channel=None, y_channels=("voltage",))
    assert graph._residual_toggle_button.isHidden()

    graph.configure_channels(
        (VOLTAGE, CURRENT), x_channel="current", y_channels=("voltage",), show_fit=True
    )
    assert not graph._residual_toggle_button.isHidden()


def test_residual_plot_hidden_by_default_when_fit_enabled() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels(
        (VOLTAGE, CURRENT), x_channel="current", y_channels=("voltage",), show_fit=True
    )
    assert graph._residual_plot_widget.isHidden()


def test_residual_values_match_measured_minus_fitted() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels(
        (VOLTAGE, CURRENT), x_channel="current", y_channels=("voltage",), show_fit=True
    )
    graph._residual_toggle_button.setChecked(True)

    # U = 2*I + 1 + шағын шу — residual нөлге жақын, бірақ дәл нөл емес.
    samples = [(0.1, 1.21), (0.2, 1.39), (0.3, 1.62), (0.4, 1.78)]
    for current, voltage in samples:
        graph.append_measurement(_make_measurement(values={"voltage": voltage, "current": current}))

    result = graph._latest_regression_result
    assert result is not None and result.valid
    residual_x, residual_y = graph._residual_curve.getData()
    expected = [voltage - (result.slope * current + result.intercept) for current, voltage in samples]
    assert list(residual_x) == pytest.approx([c for c, _ in samples])
    assert list(residual_y) == pytest.approx(expected)


def test_residual_insufficient_message_shown_when_fit_unavailable() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels(
        (VOLTAGE, CURRENT), x_channel="current", y_channels=("voltage",), show_fit=True
    )
    graph._residual_toggle_button.setChecked(True)

    graph.append_measurement(_make_measurement(values={"voltage": 1.0, "current": 0.1}))

    assert not graph._residual_insufficient_label.isHidden()
    residual_x, _residual_y = graph._residual_curve.getData()
    assert residual_x is None or len(residual_x) == 0


def test_residual_setxlink_survives_reconfigure() -> None:
    """Plan-agent-тің тапқан тәуекелі: ``ViewBox.linkView`` weakref
    арқылы сақталады, ал ``self._plot_widget`` әр ``configure_channels()``
    сайын ауыстырылады — байланыс ӘР РЕТ қайта орнатылуы тиіс.
    """
    graph = LiveGraphWidget()
    graph.configure_channels(
        (VOLTAGE, CURRENT), x_channel="current", y_channels=("voltage",), show_fit=True
    )
    first_view_box = graph._plot_widget.getViewBox()
    assert graph._residual_plot_widget.getPlotItem().getViewBox().linkedView(0) is first_view_box

    graph.configure_channels(
        (VOLTAGE, CURRENT), x_channel="current", y_channels=("voltage",), show_fit=True
    )
    second_view_box = graph._plot_widget.getViewBox()
    assert second_view_box is not first_view_box
    assert graph._residual_plot_widget.getPlotItem().getViewBox().linkedView(0) is second_view_box


def test_residual_unlinked_when_switching_to_stacked() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels(
        (VOLTAGE, CURRENT), x_channel="current", y_channels=("voltage",), show_fit=True
    )
    _configure_stacked_graph(graph)

    assert graph._residual_plot_widget.getPlotItem().getViewBox().linkedView(0) is None


def test_residual_follows_region_fit_scope_toggle() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels(
        (VOLTAGE, CURRENT), x_channel="current", y_channels=("voltage",), show_fit=True
    )
    graph._residual_toggle_button.setChecked(True)
    # I: 0.1..0.5 сызықты, тек 0.1..0.2 аралығында fit region scope-пен шектеледі.
    for current in (0.1, 0.2, 0.3, 0.4, 0.5):
        graph.append_measurement(
            _make_measurement(values={"voltage": 10 * current, "current": current})
        )
    graph._region_button.setChecked(True)
    graph._set_all_regions((0.1, 0.2))
    graph._recompute_region_analysis()
    graph._analysis_panel._region_only_radio.setChecked(True)

    # Region-де тек 2 нүкте (0.1, 0.2) бар — _MIN_FIT_POINTS=3-тен аз,
    # сондықтан fit "жеткіліксіз" болады да residual тазаланады (ЕСКІ
    # мінез-құлықпен бірдей: getData() кейде None қайтарады, бос emes).
    residual_x, _residual_y = graph._residual_curve.getData()
    assert residual_x is None or len(residual_x) < 5  # region scope-қа сай тек 0.1-0.2 аралығы


def test_residual_hidden_data_does_not_mutate_raw_samples() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels(
        (VOLTAGE, CURRENT), x_channel="current", y_channels=("voltage",), show_fit=True
    )
    for current in (0.1, 0.2, 0.3):
        graph.append_measurement(
            _make_measurement(values={"voltage": 2 * current + 1, "current": current})
        )
    before_x = list(graph._x_data["voltage"])
    before_y = list(graph._y_data["voltage"])

    graph._residual_toggle_button.setChecked(True)

    assert list(graph._x_data["voltage"]) == before_x
    assert list(graph._y_data["voltage"]) == before_y


# =====================================================================
# Phase 34: SEM / rate-of-change in region analysis
# =====================================================================


def test_sem_appears_in_region_channel_statistics() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels((VOLTAGE,), x_channel=None, y_channels=("voltage",))
    started_at = datetime.now(timezone.utc)
    for index, voltage in enumerate((6.21, 6.87, 6.54, 6.40, 6.68)):
        graph.append_measurement(
            _make_measurement(values={"voltage": voltage}, timestamp=started_at + timedelta(seconds=index))
        )
    graph._region_button.setChecked(True)
    graph._set_all_regions((-1.0, 10.0))
    graph._recompute_region_analysis()

    assert "SEM" in graph._analysis_panel._channel_rows["voltage"].text()
    assert not graph._analysis_panel._sem_caption_label.isHidden()


def test_rate_of_change_hidden_when_not_configured() -> None:
    graph = LiveGraphWidget()
    _configure_stacked_graph(graph)
    graph.append_measurement(_make_measurement(values={"voltage": 1.0, "current": 0.1}))
    graph._region_button.setChecked(True)
    graph._set_all_regions((-1.0, 10.0))
    graph._recompute_region_analysis()

    assert graph._analysis_panel._rate_of_change_rows == {}


def test_rate_of_change_computed_over_selected_region() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels(
        (VOLTAGE, CURRENT),
        x_channel=None,
        y_channels=("voltage", "current"),
        stacked=True,
        rate_of_change=(
            RateOfChangeConfig(
                channel_key="voltage", symbol="dU/dt", display_name="Кернеу жылдамдығы", unit="V/s"
            ),
        ),
    )
    started_at = datetime.now(timezone.utc)
    # voltage(t) = 2*t (сызықты өсу) -> dU/dt = 2.0 V/s дәл болуы тиіс.
    for index in range(5):
        graph.append_measurement(
            _make_measurement(
                values={"voltage": 2.0 * index, "current": 0.01},
                timestamp=started_at + timedelta(seconds=index),
            )
        )
    graph._region_button.setChecked(True)
    graph._set_all_regions((-1.0, 10.0))
    graph._recompute_region_analysis()

    text = graph._analysis_panel._rate_of_change_rows["dU/dt"].text()
    assert "dU/dt" in text
    assert "2.000" in text


# =====================================================================
# Phase 34: legend for show_fit scatter graphs
# =====================================================================


def test_legend_present_for_single_curve_fit_graph() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels(
        (VOLTAGE, CURRENT), x_channel="current", y_channels=("voltage",), show_fit=True
    )
    assert graph._plot_widget.getPlotItem().legend is not None


def test_no_legend_for_single_curve_without_fit() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels((VOLTAGE,), x_channel=None, y_channels=("voltage",))
    assert graph._plot_widget.getPlotItem().legend is None


# =====================================================================
# Phase 34: copy analysis summary
# =====================================================================


def test_copy_summary_fit_only_produces_expected_text() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels(
        (VOLTAGE, CURRENT),
        x_channel="current",
        y_channels=("voltage",),
        show_fit=True,
        fit_result_prefix="R",
        fit_unit="Ω",
        fit_x_symbol="I",
        fit_y_symbol="U",
        experiment_title="Тізбек бөлігі үшін кернеудің ток күшіне тәуелділігін зерттеу",
    )
    for current, voltage in ((0.020, 1.75), (0.081, 7.01), (0.05, 4.38)):
        graph.append_measurement(_make_measurement(values={"voltage": voltage, "current": current}))

    text = graph._build_analysis_summary_text()

    assert text.startswith("Тізбек бөлігі үшін кернеудің ток күшіне тәуелділігін зерттеу")
    assert "N = 3" in text
    assert "R =" in text
    assert "R² =" in text


def test_copy_summary_region_active_indicates_selected_interval() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels(
        (VOLTAGE,),
        x_channel=None,
        y_channels=("voltage",),
        experiment_title="Электр тізбегін құрастыру және ток күшін өлшеу",
    )
    started_at = datetime.now(timezone.utc)
    for index, voltage in enumerate((1.0, 2.0, 3.0)):
        graph.append_measurement(
            _make_measurement(values={"voltage": voltage}, timestamp=started_at + timedelta(seconds=index))
        )
    graph._region_button.setChecked(True)
    graph._set_all_regions((0.0, 2.0))
    graph._recompute_region_analysis()

    text = graph._build_analysis_summary_text()

    assert text.startswith("Электр тізбегін құрастыру және ток күшін өлшеу")
    assert "Таңдалған аралық" in text


def test_copy_summary_button_copies_to_clipboard() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels(
        (VOLTAGE, CURRENT),
        x_channel="current",
        y_channels=("voltage",),
        show_fit=True,
        experiment_title="Тізбек бөлігі үшін кернеудің ток күшіне тәуелділігін зерттеу",
    )
    for current, voltage in ((0.1, 1.0), (0.2, 2.0), (0.3, 3.0)):
        graph.append_measurement(_make_measurement(values={"voltage": voltage, "current": current}))

    graph._on_copy_summary_clicked()

    assert QApplication.clipboard().text().startswith(
        "Тізбек бөлігі үшін кернеудің ток күшіне тәуелділігін зерттеу"
    )


def test_copy_summary_empty_when_no_fit_or_region() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels((VOLTAGE, CURRENT), x_channel=None, y_channels=("voltage", "current"))
    graph.append_measurement(_make_measurement(values={"voltage": 1.0, "current": 0.1}))

    assert graph._build_analysis_summary_text() == ""


# =====================================================================
# Phase 34: image export (PNG/SVG)
# =====================================================================


def test_image_export_noop_without_file_path() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels((VOLTAGE,), x_channel=None, y_channels=("voltage",))
    graph.append_measurement(_make_measurement(values={"voltage": 1.0}))

    with patch(
        "ui.widgets.live_graph.QFileDialog.getSaveFileName", return_value=("", "")
    ):
        graph._on_image_export_clicked()  # exception шықпауы керек, файл жазылмайды


def test_image_export_png_writes_file_single_plot(tmp_path) -> None:
    graph = LiveGraphWidget()
    graph.configure_channels((VOLTAGE,), x_channel=None, y_channels=("voltage",))
    graph.append_measurement(_make_measurement(values={"voltage": 1.0}))
    graph.resize(400, 300)

    output_path = tmp_path / "graph.png"
    with patch(
        "ui.widgets.live_graph.QFileDialog.getSaveFileName",
        return_value=(str(output_path), "PNG суреттер (*.png)"),
    ):
        graph._on_image_export_clicked()

    assert output_path.exists()


def test_image_export_png_writes_file_stacked(tmp_path) -> None:
    graph = LiveGraphWidget()
    _configure_stacked_graph(graph)
    graph.append_measurement(_make_measurement(values={"voltage": 1.0, "current": 0.1}))
    graph.resize(400, 300)

    output_path = tmp_path / "graph_stacked.png"
    with patch(
        "ui.widgets.live_graph.QFileDialog.getSaveFileName",
        return_value=(str(output_path), "PNG суреттер (*.png)"),
    ):
        graph._on_image_export_clicked()

    assert output_path.exists()


def test_image_export_svg_uses_native_exporter_for_single_plot_only(tmp_path) -> None:
    """SVGExporter-дің нақты SVG рендерингі (headless/offscreen ортада
    белгілі pyqtgraph coordinate-parsing ақауы — тіпті бос PlotWidget-те
    де қайталанады, ЕШБІР біздің кодқа қатысы жоқ, тексерілді) осы
    тестте THIRD-PARTY детаіл ретінде мокталады — біз тек өз
    orchestration логикамызды (single-plot-те SVGExporter НАҚТЫ
    ағымдағы PlotItem-мен шақырылатынын) тексереміз.
    """
    graph = LiveGraphWidget()
    graph.configure_channels(
        (VOLTAGE, CURRENT), x_channel="current", y_channels=("voltage",), show_fit=True
    )
    for current, voltage in ((0.1, 1.0), (0.2, 2.0), (0.3, 3.0)):
        graph.append_measurement(_make_measurement(values={"voltage": voltage, "current": current}))
    graph.resize(400, 300)

    output_path = tmp_path / "graph.svg"
    with patch(
        "ui.widgets.live_graph.QFileDialog.getSaveFileName",
        return_value=(str(output_path), "SVG суреттер (*.svg)"),
    ), patch("ui.widgets.live_graph.pg_exporters.SVGExporter") as mock_exporter_cls:
        graph._on_image_export_clicked()

    mock_exporter_cls.assert_called_once_with(graph._plot_widget.getPlotItem())
    mock_exporter_cls.return_value.export.assert_called_once_with(str(output_path))


def test_image_export_stacked_does_not_offer_svg_filter() -> None:
    graph = LiveGraphWidget()
    _configure_stacked_graph(graph)
    graph.append_measurement(_make_measurement(values={"voltage": 1.0, "current": 0.1}))

    with patch(
        "ui.widgets.live_graph.QFileDialog.getSaveFileName", return_value=("", "")
    ) as mock_dialog:
        graph._on_image_export_clicked()

    filters_used = mock_dialog.call_args[0][3]
    assert "SVG" not in filters_used


def test_image_export_does_not_mutate_curve_or_region_state(tmp_path) -> None:
    """Критикалық integrity тест: экспорт әрекеті graph күйіне
    (raw дерек, region позициясы, crosshair) ЕШБІР тиіспеуі тиіс.
    """
    graph = LiveGraphWidget()
    graph.configure_channels((VOLTAGE,), x_channel=None, y_channels=("voltage",))
    graph.append_measurement(_make_measurement(values={"voltage": 1.0}))
    graph.append_measurement(_make_measurement(values={"voltage": 2.0}))
    graph._region_button.setChecked(True)
    graph._set_all_regions((0.0, 1.0))
    before_x = list(graph._x_data["voltage"])
    before_y = list(graph._y_data["voltage"])
    before_region = graph._region_items["__single__"].getRegion()
    graph.resize(400, 300)

    output_path = tmp_path / "graph.png"
    with patch(
        "ui.widgets.live_graph.QFileDialog.getSaveFileName",
        return_value=(str(output_path), "PNG суреттер (*.png)"),
    ):
        graph._on_image_export_clicked()

    assert list(graph._x_data["voltage"]) == before_x
    assert list(graph._y_data["voltage"]) == before_y
    assert graph._region_items["__single__"].getRegion() == pytest.approx(before_region)
    assert graph._region_items["__single__"].isVisible() is True  # export-тан кейін қалпына келді


# =====================================================================
# Phase 34 §14: Performance sanity (region recompute must stay cheap)
# =====================================================================


@pytest.mark.parametrize("point_count", [100, 1000, 5000, 10000])
def test_region_recompute_stays_fast_at_scale(point_count: int) -> None:
    import time

    graph = LiveGraphWidget()
    graph.configure_channels((VOLTAGE,), x_channel=None, y_channels=("voltage",))
    started_at = datetime.now(timezone.utc)
    for index in range(point_count):
        graph.append_measurement(
            _make_measurement(
                values={"voltage": 1.0 + (index % 7) * 0.01},
                timestamp=started_at + timedelta(milliseconds=index * 10),
            )
        )
    graph._region_button.setChecked(True)
    graph._set_all_regions((0.0, point_count * 0.01))

    start = time.perf_counter()
    graph._recompute_region_analysis()
    elapsed = time.perf_counter() - start

    assert elapsed < 0.5


# =====================================================================
# Phase 34.1: tooltip clipping fix — widget-level (stacked/maximized)
# =====================================================================


def _viewbox_scene_rect(plot_widget):
    from PySide6.QtCore import QRectF

    view_box = plot_widget.getPlotItem().vb
    (x_min, x_max), (y_min, y_max) = view_box.viewRange()
    top_left = view_box.mapViewToScene(pg.Point(x_min, y_max))
    bottom_right = view_box.mapViewToScene(pg.Point(x_max, y_min))
    return QRectF(top_left, bottom_right).normalized()


def _assert_tooltip_fully_contained(crosshair, plot_widget, tolerance_px: float = 1.0) -> None:
    """Phase 34.1.1: tooltip-тің НАҚТЫ scene тіктөртбұрышы (рендерленген
    өлшемімен) ViewBox-тың scene ауданының ІШІНДЕ жатуын тексереді —
    жай pos()-ты data-ауқымда тексеруден МҮЛДЕ өзгеше (ол әрқашан
    "өтеді", себебі соңғы clamp оны кепілдендіреді, бірақ Phase 34.1-дегі
    бастапқы түзетудің НАҚТЫ жеткіліксіздігін байқамаған еді).
    """
    readout = crosshair._readout
    tooltip_rect = readout.mapRectToScene(readout.boundingRect())
    view_rect = _viewbox_scene_rect(plot_widget)
    inflated = view_rect.adjusted(-tolerance_px, -tolerance_px, tolerance_px, tolerance_px)
    assert inflated.contains(tooltip_rect), (
        f"Tooltip scene rect {tooltip_rect} escapes ViewBox scene rect {view_rect}"
    )


def test_stacked_crosshair_tooltip_stays_inside_viewbox_near_edge() -> None:
    """Электр тізбегін құрастыру және ток күшін өлшеу тәрізді stacked
    синхрондалған графикте де,
    subplot-тың кез келген шетіне жақын нүктеде tooltip clip болмауы
    тиіс (Phase 34.1.1 §1) — НАҚТЫ рендерленген tooltip өлшемімен,
    stacked subplot-тың ШЕКТЕУЛІ (толық графиктің жартысындай)
    биіктігінде тексеріледі (дәл осы жағдайда бастапқы Phase 34.1
    түзету жеткіліксіз болған).
    """
    graph = LiveGraphWidget()
    _configure_stacked_graph(graph)
    graph.resize(1200, 700)
    graph.show()
    QApplication.instance().processEvents()
    graph._stacked_plot_widgets["voltage"].setYRange(0.0, 10.0, padding=0)
    started_at = datetime.now(timezone.utc)
    # voltage 9.85 — жоғарғы шетке (10.0) өте жақын.
    graph.append_measurement(
        _make_measurement(values={"voltage": 9.85, "current": 0.05}, timestamp=started_at)
    )
    QApplication.instance().processEvents()

    graph._crosshairs["voltage"].show_at_x(0.0)
    QApplication.instance().processEvents()

    _assert_tooltip_fully_contained(graph._crosshairs["voltage"], graph._stacked_plot_widgets["voltage"])
    # Синхрондалған current subplot-тың tooltip-і де сыюы тиіс.
    graph._on_stacked_crosshair_hover("voltage", 0.0)
    QApplication.instance().processEvents()
    _assert_tooltip_fully_contained(graph._crosshairs["current"], graph._stacked_plot_widgets["current"])


def test_maximized_graph_tooltip_still_contained_near_edge() -> None:
    """Graph maximized режимінде де (zoom/crosshair логикасы тимейді,
    тек presentation) tooltip дұрыс контейнде қалуы тиіс.
    """
    graph = LiveGraphWidget()
    graph.configure_channels((VOLTAGE,), x_channel=None, y_channels=("voltage",))
    graph.resize(1200, 700)
    graph.show()
    QApplication.instance().processEvents()
    graph._plot_widget.setYRange(0.0, 10.0, padding=0)
    graph.append_measurement(_make_measurement(values={"voltage": 9.9}))
    QApplication.instance().processEvents()

    graph._maximize_button.setChecked(True)
    graph._crosshairs["__single__"].show_at_x(0.0)
    QApplication.instance().processEvents()

    _assert_tooltip_fully_contained(graph._crosshairs["__single__"], graph._plot_widget)


def test_geometry_containment_across_zoom_pan_reset_maximize_resize() -> None:
    """§5: autoscale/zoom/pan/reset-view/maximize/restore/window-resize
    әрқайсысынан кейін де tooltip contain болуы тиіс — әрбір hover/
    readout жаңартылуында АҒЫМДАҒЫ ViewBox геометриясы қайта оқылады.
    """
    graph = LiveGraphWidget()
    graph.configure_channels((VOLTAGE,), x_channel=None, y_channels=("voltage",))
    graph.resize(1200, 700)
    graph.show()
    QApplication.instance().processEvents()
    graph.append_measurement(_make_measurement(values={"voltage": 9.85}))
    graph._plot_widget.setYRange(0.0, 10.0, padding=0)
    QApplication.instance().processEvents()

    # 1. Қалыпты күй.
    graph._crosshairs["__single__"].show_at_x(0.0)
    QApplication.instance().processEvents()
    _assert_tooltip_fully_contained(graph._crosshairs["__single__"], graph._plot_widget)

    # 2. Қолмен zoom (ViewBox ауқымы тарылады).
    graph._plot_widget.setYRange(8.0, 10.0, padding=0)
    QApplication.instance().processEvents()
    graph._crosshairs["__single__"].show_at_x(0.0)
    QApplication.instance().processEvents()
    _assert_tooltip_fully_contained(graph._crosshairs["__single__"], graph._plot_widget)

    # 3. Reset View (zoom_reset батырмасы).
    graph._on_zoom_reset_clicked()
    QApplication.instance().processEvents()
    graph._crosshairs["__single__"].show_at_x(0.0)
    QApplication.instance().processEvents()
    _assert_tooltip_fully_contained(graph._crosshairs["__single__"], graph._plot_widget)

    # 4. Maximize.
    graph._maximize_button.setChecked(True)
    QApplication.instance().processEvents()
    graph._crosshairs["__single__"].show_at_x(0.0)
    QApplication.instance().processEvents()
    _assert_tooltip_fully_contained(graph._crosshairs["__single__"], graph._plot_widget)

    # 5. Restore.
    graph._maximize_button.setChecked(False)
    QApplication.instance().processEvents()
    graph._crosshairs["__single__"].show_at_x(0.0)
    QApplication.instance().processEvents()
    _assert_tooltip_fully_contained(graph._crosshairs["__single__"], graph._plot_widget)

    # 6. Window resize.
    graph.resize(700, 450)
    QApplication.instance().processEvents()
    graph._crosshairs["__single__"].show_at_x(0.0)
    QApplication.instance().processEvents()
    _assert_tooltip_fully_contained(graph._crosshairs["__single__"], graph._plot_widget)


# =====================================================================
# Phase 34.1 §3: empty/ready graph state overlay reset
# =====================================================================


def test_devices_ready_true_clears_stale_region_selection() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels((VOLTAGE,), x_channel=None, y_channels=("voltage",))
    graph.append_measurement(_make_measurement(values={"voltage": 1.0}))
    graph._region_button.setChecked(True)
    graph._set_all_regions((0.0, 1.0))
    assert graph._region_enabled is True

    graph.set_devices_ready(True)

    assert graph._region_enabled is False
    assert graph._region_button.isChecked() is False
    assert graph._region_items["__single__"].isVisible() is False


def test_devices_ready_true_clears_stale_delta_cursors() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels(
        (VOLTAGE,), x_channel=None, y_channels=("voltage",), allow_delta_measurement=True
    )
    graph.append_measurement(_make_measurement(values={"voltage": 1.0}))
    graph._delta_button.setChecked(True)
    graph._place_delta_cursor(0.0)
    assert graph._delta_cursor_a is not None

    graph.set_devices_ready(True)

    assert graph._delta_cursor_a is None
    assert graph._delta_cursor_b is None
    assert graph._delta_button.isChecked() is False
    assert graph._delta_panel.isHidden()


def test_devices_ready_true_hides_stale_crosshair() -> None:
    graph = LiveGraphWidget()
    graph.configure_channels((VOLTAGE,), x_channel=None, y_channels=("voltage",))
    graph.append_measurement(_make_measurement(values={"voltage": 1.0}))
    graph._crosshairs["__single__"].show_at_x(0.0)
    assert graph._crosshairs["__single__"]._v_line.isVisible() is True

    graph.set_devices_ready(True)

    assert graph._crosshairs["__single__"]._v_line.isVisible() is False


def test_devices_ready_false_does_not_touch_overlays() -> None:
    """``ready=False`` — құрылғылар әлі қосылмаған/ажыратылған — жаңа
    сессия оқиғасы ЕМЕС, сондықтан ағымдағы region/A-B күйіне тимейді
    (тек presentation мәтінін жаңартады).
    """
    graph = LiveGraphWidget()
    graph.configure_channels((VOLTAGE,), x_channel=None, y_channels=("voltage",))
    graph.append_measurement(_make_measurement(values={"voltage": 1.0}))
    graph._region_button.setChecked(True)

    graph.set_devices_ready(False)

    assert graph._region_button.isChecked() is True
