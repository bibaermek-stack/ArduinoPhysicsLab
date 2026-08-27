"""MeasurementWorkspace үшін юнит-тесттер: configure_for_experiment
негізіндегі dynamic readouts/graph/table.
"""

import sys
from datetime import datetime, timezone

import pytest
from PySide6.QtWidgets import QApplication, QSizePolicy

from domain.entities.connected_device import ConnectedDevice
from domain.entities.experiment_definition import ExperimentDefinition
from domain.entities.measurement import Measurement
from domain.entities.sensor_channel import SensorChannel
from ui.widgets.live_graph import LiveGraphWidget
from ui.widgets.measurement_table import MeasurementTableWidget
from ui.widgets.measurement_workspace import MeasurementWorkspace


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
POWER = SensorChannel(key="power", display_name="Қуат", unit="W", decimals=3, required=False)
WORK = SensorChannel(key="work", display_name="Жұмыс", unit="J", decimals=3, required=False)
TIME = SensorChannel(key="time", display_name="Уақыт", unit="s", decimals=2, required=False)


def _current_voltage_experiment() -> ExperimentDefinition:
    return ExperimentDefinition(
        id="current-voltage",
        title="Электр тізбегін құрастыру және ток күшін өлшеу",
        description="",
        required_channels=(VOLTAGE, CURRENT),
        derived_channels=(POWER,),
        graph_x_channel="voltage",
        graph_y_channels=("current",),
    )


def _stacked_current_voltage_experiment() -> ExperimentDefinition:
    """Нақты production ``CURRENT_VOLTAGE_EXPERIMENT``-пен БІРДЕЙ
    ``graph_stacked=True`` конфигурациясы (§ modules/electricity/
    experiments_config.py) — Phase 3 регрессиясы дәл осы жол арқылы
    ғана шақырылады (``_build_stacked_plot_widgets()``). Бұрынғы
    ``_current_voltage_experiment()`` helper-і ЕШҚАШАН stacked=True
    орнатпаған, сондықтан бар тесттер бұл кодты мүлде тексермеген
    (§ Phase 3 есебі: "no test has ever exercised the 2-plot code
    path").
    """
    return ExperimentDefinition(
        id="stacked-current-voltage",
        title="Электр тізбегін құрастыру және ток күшін өлшеу",
        description="",
        required_channels=(VOLTAGE, CURRENT),
        derived_channels=(POWER,),
        graph_x_channel=None,
        graph_y_channels=("voltage", "current"),
        graph_stacked=True,
        graph_stacked_titles={
            "voltage": "Кернеудің уақыт бойынша өзгерісі",
            "current": "Ток күшінің уақыт бойынша өзгерісі",
        },
        graph_stacked_y_labels={"voltage": "Кернеу, U", "current": "Ток күші, I"},
    )


def _ohms_law_experiment() -> ExperimentDefinition:
    return ExperimentDefinition(
        id="ohms-law",
        title="Тізбек бөлігі үшін кернеудің ток күшіне тәуелділігін зерттеу",
        description="",
        required_channels=(VOLTAGE, CURRENT),
        derived_channels=(RESISTANCE,),
        graph_x_channel="current",
        graph_y_channels=("voltage",),
    )


def _current_work_power_experiment() -> ExperimentDefinition:
    return ExperimentDefinition(
        id="current-work-power",
        title="Ток жұмысы мен қуаты",
        description="",
        required_channels=(VOLTAGE, CURRENT, TIME),
        derived_channels=(POWER, WORK),
        graph_x_channel=None,
        graph_y_channels=("power",),
        display_channels=("time", "power", "work"),
    )


def _make_device() -> ConnectedDevice:
    return ConnectedDevice(
        device_id="APL-VOLTAGE-01",
        model="V1",
        sensor_type="VOLTAGE",
        firmware_version="1.0",
        chip="INA226",
        serial_number=None,
        hardware_version=None,
        port_name="COM3",
        connected_at=datetime.now(timezone.utc),
        warnings=(),
    )


def _make_measurement(
    values: dict[str, float] | None = None,
    derived_values: dict[str, float] | None = None,
) -> Measurement:
    return Measurement(
        timestamp=datetime.now(timezone.utc),
        values=values or {},
        experiment_id="E02",
        derived_values=derived_values or {},
    )


def test_no_device_screen_shown_initially() -> None:
    workspace = MeasurementWorkspace()

    assert workspace._stack.currentWidget() is workspace._no_device_page


def test_device_is_set() -> None:
    workspace = MeasurementWorkspace()
    device = _make_device()

    workspace.set_device(device)

    assert workspace._stack.currentWidget() is workspace._device_page
    assert workspace._title_label.text() == "Кернеу датчигі"
    assert workspace._device_id_label.text() == "APL-VOLTAGE-01"
    assert "1.0" in workspace._firmware_label.text()
    assert "V1" in workspace._model_label.text()
    assert "INA226" in workspace._chip_label.text()
    assert "Қосылды" in workspace._status_label.text()


def test_device_is_cleared() -> None:
    workspace = MeasurementWorkspace()
    workspace.set_device(_make_device())

    workspace.clear_device()

    # Phase 32.1 (§11): device_page ЕНДІ жасырылмайды — тек device info
    # (title/id/firmware/т.б.) тазаланады/жасырылады, workspace-тің ӨЗІ
    # (metric cards/graph/table) көрінуін жалғастырады.
    assert workspace._stack.currentWidget() is workspace._device_page
    assert workspace._device_info_section.isHidden() is True


# ---- configure_for_experiment: title + dynamic readouts -------------------


def test_configure_for_experiment_shows_experiment_title() -> None:
    workspace = MeasurementWorkspace()

    workspace.configure_for_experiment(_ohms_law_experiment())

    assert workspace._experiment_title_label.text() == "Тізбек бөлігі үшін кернеудің ток күшіне тәуелділігін зерттеу"


def test_current_voltage_readouts() -> None:
    workspace = MeasurementWorkspace()
    workspace.configure_for_experiment(_current_voltage_experiment())
    workspace.set_device(_make_device())

    workspace.set_measurement(
        _make_measurement(values={"voltage": 5.024, "current": 0.218}, derived_values={"power": 1.095})
    )

    assert set(workspace._value_labels.keys()) == {"voltage", "current", "power"}
    assert workspace._value_labels["voltage"].text() == "5.024 V"
    assert workspace._value_labels["current"].text() == "0.218 A"
    assert workspace._value_labels["power"].text() == "1.095 W"


def test_ohms_law_resistance_readout() -> None:
    workspace = MeasurementWorkspace()
    workspace.configure_for_experiment(_ohms_law_experiment())
    workspace.set_device(_make_device())

    workspace.set_measurement(
        _make_measurement(values={"voltage": 5.0, "current": 0.5}, derived_values={"resistance": 10.0})
    )

    assert set(workspace._value_labels.keys()) == {"voltage", "current", "resistance"}
    assert workspace._value_labels["resistance"].text() == "10.00 Ω"


def test_current_work_power_time_power_work_readouts() -> None:
    workspace = MeasurementWorkspace()
    workspace.configure_for_experiment(_current_work_power_experiment())
    workspace.set_device(_make_device())

    workspace.set_measurement(
        _make_measurement(
            values={"voltage": 5.0, "current": 0.5, "time": 12.5},
            derived_values={"power": 2.5, "work": 31.25},
        )
    )

    # voltage/current display_channels-та жоқ — readout ретінде көрсетілмейді.
    assert set(workspace._value_labels.keys()) == {"time", "power", "work"}
    assert workspace._value_labels["time"].text() == "12.50 s"
    assert workspace._value_labels["power"].text() == "2.500 W"
    assert workspace._value_labels["work"].text() == "31.250 J"


def test_derived_resistance_channel_is_displayed_with_configured_decimals() -> None:
    workspace = MeasurementWorkspace()
    workspace.configure_for_experiment(_ohms_law_experiment())

    workspace.set_measurement(
        _make_measurement(values={"voltage": 5.0, "current": 0.5}, derived_values={"resistance": 10.0})
    )

    assert workspace._value_labels["resistance"].text() == "10.00 Ω"


def test_derived_work_channel_is_displayed_with_configured_decimals() -> None:
    workspace = MeasurementWorkspace()
    workspace.configure_for_experiment(_current_work_power_experiment())

    workspace.set_measurement(_make_measurement(derived_values={"work": 31.25}))

    assert workspace._value_labels["work"].text() == "31.250 J"


# ---- kезeng 28: elapsed-time readout ("УАҚЫТ", Ток жұмысы мен қуаты) -----


def test_time_readout_initial_state_is_zero_not_dash() -> None:
    """§7: уақыт — PC-generated, әрдайым белгілі шама, сондықтан бастапқы
    күйде де басқа арналардай "—" емес, "0.00 s" болуы керек."""
    workspace = MeasurementWorkspace()

    workspace.configure_for_experiment(_current_work_power_experiment())

    assert workspace._value_labels["time"].text() == "0.00 s"
    # Басқа арналар (уақыт емес) өзгеріссіз "—" қалады.
    assert workspace._value_labels["power"].text() == "—"
    assert workspace._value_labels["work"].text() == "—"


def test_time_readout_unaffected_for_experiments_without_time_channel() -> None:
    workspace = MeasurementWorkspace()

    workspace.configure_for_experiment(_current_voltage_experiment())

    assert "time" not in workspace._value_labels
    assert workspace._value_labels["voltage"].text() == "—"


def test_update_elapsed_time_formats_with_configured_decimals_and_unit() -> None:
    workspace = MeasurementWorkspace()
    workspace.configure_for_experiment(_current_work_power_experiment())

    workspace.update_elapsed_time(2.5)

    assert workspace._value_labels["time"].text() == "2.50 s"


def test_update_elapsed_time_is_noop_when_no_time_channel_configured() -> None:
    workspace = MeasurementWorkspace()
    workspace.configure_for_experiment(_current_voltage_experiment())

    workspace.update_elapsed_time(2.5)  # exception шықпауы, ешбір readout өзгертпеуі керек

    assert "time" not in workspace._value_labels
    assert workspace._value_labels["voltage"].text() == "—"


def test_clear_measurements_resets_time_readout_to_zero_not_dash() -> None:
    workspace = MeasurementWorkspace()
    workspace.configure_for_experiment(_current_work_power_experiment())
    workspace.set_measurement(
        _make_measurement(
            values={"voltage": 5.0, "current": 0.5},
            derived_values={"time": 8.34, "power": 2.5, "work": 20.85},
        )
    )
    assert workspace._value_labels["time"].text() == "8.34 s"

    workspace.clear_measurements()

    assert workspace._value_labels["time"].text() == "0.00 s"
    assert workspace._value_labels["power"].text() == "—"


def test_reconfigure_removes_old_readouts() -> None:
    workspace = MeasurementWorkspace()
    workspace.configure_for_experiment(_current_voltage_experiment())
    workspace.set_measurement(
        _make_measurement(values={"voltage": 5.0, "current": 0.5}, derived_values={"power": 2.5})
    )
    assert "power" in workspace._value_labels

    workspace.configure_for_experiment(_ohms_law_experiment())

    assert "power" not in workspace._value_labels
    assert set(workspace._value_labels.keys()) == {"voltage", "current", "resistance"}
    assert workspace._value_labels["resistance"].text() == "—"


def test_partial_measurement_shows_dash_for_missing_values() -> None:
    workspace = MeasurementWorkspace()
    workspace.configure_for_experiment(_current_voltage_experiment())
    workspace.set_device(_make_device())

    workspace.set_measurement(_make_measurement(values={"voltage": 5.0}))

    assert workspace._value_labels["voltage"].text() == "5.000 V"
    assert workspace._value_labels["current"].text() == "—"
    assert workspace._value_labels["power"].text() == "—"


def test_start_button_emits_signal() -> None:
    workspace = MeasurementWorkspace()
    workspace.configure_for_experiment(_current_voltage_experiment())
    workspace.set_device(_make_device())
    received: list[None] = []
    workspace.start_requested.connect(lambda: received.append(None))

    workspace._start_button.click()

    assert len(received) == 1


def test_stop_button_emits_signal() -> None:
    workspace = MeasurementWorkspace()
    workspace.set_device(_make_device())
    workspace.set_experiment_running(True)
    received: list[None] = []
    workspace.stop_requested.connect(lambda: received.append(None))

    workspace._stop_button.click()

    assert len(received) == 1


def test_clear_button_emits_signal() -> None:
    workspace = MeasurementWorkspace()
    workspace.set_device(_make_device())
    received: list[None] = []
    workspace.clear_requested.connect(lambda: received.append(None))

    workspace._clear_button.click()

    assert len(received) == 1


def test_ui_updates_when_measurement_changes() -> None:
    workspace = MeasurementWorkspace()
    workspace.configure_for_experiment(_current_voltage_experiment())
    workspace.set_device(_make_device())

    workspace.set_measurement(_make_measurement(values={"voltage": 1.0, "current": 0.1}))
    assert workspace._value_labels["voltage"].text() == "1.000 V"

    workspace.set_measurement(_make_measurement(values={"voltage": 2.0, "current": 0.1}))
    assert workspace._value_labels["voltage"].text() == "2.000 V"


def test_live_graph_and_measurement_table_are_present() -> None:
    workspace = MeasurementWorkspace()
    workspace.set_device(_make_device())

    assert isinstance(workspace._live_graph, LiveGraphWidget)
    assert isinstance(workspace._measurement_table, MeasurementTableWidget)


def test_set_measurement_forwards_to_live_graph() -> None:
    workspace = MeasurementWorkspace()
    workspace.configure_for_experiment(_current_voltage_experiment())
    workspace.set_device(_make_device())
    measurement = _make_measurement(values={"voltage": 5.0, "current": 0.5})

    workspace.set_measurement(measurement)

    assert list(workspace._live_graph._y_data["current"]) == [0.5]


def test_set_measurement_forwards_to_measurement_table() -> None:
    workspace = MeasurementWorkspace()
    workspace.configure_for_experiment(_current_voltage_experiment())
    workspace.set_device(_make_device())
    measurement = _make_measurement(values={"voltage": 5.0, "current": 0.5})

    workspace.set_measurement(measurement)

    assert workspace._measurement_table._model.rowCount() == 1
    assert workspace._measurement_table._model.item(0, 1).text() == "5.000"


def test_set_device_clears_measurement_table() -> None:
    workspace = MeasurementWorkspace()
    workspace.configure_for_experiment(_current_voltage_experiment())
    workspace.set_device(_make_device())
    workspace.set_measurement(_make_measurement(values={"voltage": 5.0}))
    assert workspace._measurement_table._model.rowCount() == 1

    workspace.set_device(_make_device())

    assert workspace._measurement_table._model.rowCount() == 0


# ---- Lifecycle: button states -------------------------------------------


def test_no_device_button_states() -> None:
    workspace = MeasurementWorkspace()

    assert workspace._start_button.isEnabled() is False
    assert workspace._stop_button.isEnabled() is False
    assert workspace._clear_button.isEnabled() is False


def test_idle_button_states_after_device_set() -> None:
    workspace = MeasurementWorkspace()

    workspace.set_device(_make_device())

    assert workspace._start_button.isEnabled() is True
    assert workspace._stop_button.isEnabled() is False
    assert workspace._clear_button.isEnabled() is True


def test_running_button_states() -> None:
    workspace = MeasurementWorkspace()
    workspace.set_device(_make_device())

    workspace.set_experiment_running(True)

    assert workspace._start_button.isEnabled() is False
    assert workspace._stop_button.isEnabled() is True
    assert workspace._clear_button.isEnabled() is False


def test_button_states_after_stop() -> None:
    workspace = MeasurementWorkspace()
    workspace.set_device(_make_device())
    workspace.set_experiment_running(True)

    workspace.set_experiment_running(False)

    assert workspace._start_button.isEnabled() is True
    assert workspace._stop_button.isEnabled() is False
    assert workspace._clear_button.isEnabled() is True


# ---- Lifecycle: clear_measurements ---------------------------------------


def test_clear_measurements_resets_readouts() -> None:
    workspace = MeasurementWorkspace()
    workspace.configure_for_experiment(_current_voltage_experiment())
    workspace.set_device(_make_device())
    workspace.set_measurement(_make_measurement(values={"voltage": 5.0}))

    workspace.clear_measurements()

    assert workspace._value_labels["voltage"].text() == "—"


def test_clear_measurements_clears_graph() -> None:
    workspace = MeasurementWorkspace()
    workspace.configure_for_experiment(_current_voltage_experiment())
    workspace.set_device(_make_device())
    workspace.set_measurement(_make_measurement(values={"voltage": 5.0, "current": 0.5}))

    workspace.clear_measurements()

    assert list(workspace._live_graph._y_data["current"]) == []


def test_clear_measurements_clears_table() -> None:
    workspace = MeasurementWorkspace()
    workspace.configure_for_experiment(_current_voltage_experiment())
    workspace.set_device(_make_device())
    workspace.set_measurement(_make_measurement(values={"voltage": 5.0}))

    workspace.clear_measurements()

    assert workspace._measurement_table._model.rowCount() == 0


def test_clear_measurements_preserves_device_info() -> None:
    workspace = MeasurementWorkspace()
    workspace.configure_for_experiment(_current_voltage_experiment())
    workspace.set_device(_make_device())
    workspace.set_measurement(_make_measurement(values={"voltage": 5.0}))

    workspace.clear_measurements()

    assert workspace._device is not None
    assert workspace._device_id_label.text() == "APL-VOLTAGE-01"
    assert workspace._stack.currentWidget() is workspace._device_page


# ---- Multi-device: set_ready() --------------------------------------------


def test_set_ready_true_enables_buttons_and_shows_device_page() -> None:
    workspace = MeasurementWorkspace()
    workspace.configure_for_experiment(_ohms_law_experiment())

    workspace.set_ready(True)

    assert workspace._stack.currentWidget() is workspace._device_page
    assert workspace._start_button.isEnabled() is True
    assert workspace._clear_button.isEnabled() is True
    assert workspace._export_button.isEnabled() is True


def test_set_ready_false_disables_buttons_and_keeps_device_page_visible() -> None:
    """Phase 32.1 root-cause fix: readiness=False (0/N немесе ішінара
    N/M) кезде БҮКІЛ workspace (metric cards/graph/table) ЖАСЫРЫЛМАЙДЫ —
    тек Start/Тазалау батырмалары disabled болады.
    """
    workspace = MeasurementWorkspace()
    workspace.configure_for_experiment(_ohms_law_experiment())
    workspace.set_ready(True)

    workspace.set_ready(False)

    assert workspace._stack.currentWidget() is workspace._device_page
    assert workspace._start_button.isEnabled() is False
    assert workspace._clear_button.isEnabled() is False


def test_set_ready_true_clears_previous_measurements() -> None:
    workspace = MeasurementWorkspace()
    workspace.configure_for_experiment(_ohms_law_experiment())
    workspace.set_ready(True)
    workspace.set_measurement(
        _make_measurement(values={"voltage": 5.0, "current": 0.5}, derived_values={"resistance": 10.0})
    )
    assert workspace._measurement_table._model.rowCount() == 1

    workspace.set_ready(True)

    assert workspace._measurement_table._model.rowCount() == 0
    assert workspace._value_labels["voltage"].text() == "—"


def test_set_ready_running_button_states() -> None:
    workspace = MeasurementWorkspace()
    workspace.configure_for_experiment(_ohms_law_experiment())
    workspace.set_ready(True)

    workspace.set_experiment_running(True)

    assert workspace._start_button.isEnabled() is False
    assert workspace._stop_button.isEnabled() is True
    assert workspace._clear_button.isEnabled() is False


# ---- Manual point capture (V2): running күйінің graph-қа жеткізілуі ------


def _manual_capture_ohms_law_experiment() -> ExperimentDefinition:
    return ExperimentDefinition(
        id="ohms-law",
        title="Тізбек бөлігі үшін кернеудің ток күшіне тәуелділігін зерттеу",
        description="",
        required_channels=(VOLTAGE, CURRENT),
        derived_channels=(RESISTANCE,),
        graph_x_channel="current",
        graph_y_channels=("voltage",),
        graph_capture_mode="manual",
    )


def test_set_experiment_running_forwards_to_live_graph_capture() -> None:
    workspace = MeasurementWorkspace()
    workspace.configure_for_experiment(_manual_capture_ohms_law_experiment())
    workspace.set_ready(True)
    workspace.set_measurement(_make_measurement(values={"voltage": 5.0, "current": 0.132}))

    workspace.set_experiment_running(True)
    assert workspace._live_graph._capture_button.isEnabled() is True

    workspace.set_experiment_running(False)
    assert workspace._live_graph._capture_button.isEnabled() is False


def test_live_graph_capture_status_forwards_to_workspace_status() -> None:
    workspace = MeasurementWorkspace()
    workspace.configure_for_experiment(_manual_capture_ohms_law_experiment())

    workspace._live_graph.capture_status.emit("Мән тұрақталған жоқ. Бірнеше секунд күтіңіз.")

    assert workspace._status_message_label.text() == "Мән тұрақталған жоқ. Бірнеше секунд күтіңіз."


# ---- Optional Power toggle (V3, "Электр тізбегін құрастыру және ток күшін өлшеу") --------------------------


def _current_voltage_power_toggle_experiment() -> ExperimentDefinition:
    return ExperimentDefinition(
        id="current-voltage",
        title="Электр тізбегін құрастыру және ток күшін өлшеу",
        description="",
        required_channels=(VOLTAGE, CURRENT),
        derived_channels=(POWER,),
        display_channels=("voltage", "current"),
        optional_display_channels=("power",),
        optional_display_show_label="Қуатты көрсету",
        optional_display_hide_label="Қуатты жасыру",
        graph_x_channel=None,
        graph_y_channels=("voltage", "current"),
        graph_stacked=True,
    )


def test_power_readout_hidden_by_default() -> None:
    workspace = MeasurementWorkspace()

    workspace.configure_for_experiment(_current_voltage_power_toggle_experiment())

    assert set(workspace._value_labels.keys()) == {"voltage", "current", "power"}
    assert workspace._optional_readout_widgets["power"].isHidden()


def test_power_toggle_button_shows_power_readout() -> None:
    workspace = MeasurementWorkspace()
    workspace.configure_for_experiment(_current_voltage_power_toggle_experiment())

    workspace._optional_toggle_button.click()

    assert not workspace._optional_readout_widgets["power"].isHidden()
    assert workspace._optional_toggle_button.text() == "⚡ Қуатты жасыру"


def test_power_toggle_button_clicked_twice_hides_again() -> None:
    workspace = MeasurementWorkspace()
    workspace.configure_for_experiment(_current_voltage_power_toggle_experiment())

    workspace._optional_toggle_button.click()
    workspace._optional_toggle_button.click()

    assert workspace._optional_readout_widgets["power"].isHidden()
    assert workspace._optional_toggle_button.text() == "⚡ Қуатты көрсету"


def test_power_readout_updates_live_even_while_hidden() -> None:
    workspace = MeasurementWorkspace()
    workspace.configure_for_experiment(_current_voltage_power_toggle_experiment())

    workspace.set_measurement(
        _make_measurement(values={"voltage": 5.0, "current": 0.2}, derived_values={"power": 1.0})
    )

    assert workspace._value_labels["power"].text() == "1.000 W"
    assert workspace._optional_readout_widgets["power"].isHidden()


def test_power_toggle_does_not_clear_measurements_or_session() -> None:
    workspace = MeasurementWorkspace()
    workspace.configure_for_experiment(_current_voltage_power_toggle_experiment())
    workspace.set_ready(True)
    workspace.set_measurement(
        _make_measurement(values={"voltage": 5.0, "current": 0.2}, derived_values={"power": 1.0})
    )
    assert workspace._measurement_table._model.rowCount() == 1

    workspace._optional_toggle_button.click()

    assert workspace._measurement_table._model.rowCount() == 1
    assert workspace._value_labels["voltage"].text() == "5.000 V"


def test_power_table_column_hidden_by_default() -> None:
    workspace = MeasurementWorkspace()
    workspace.configure_for_experiment(_current_voltage_power_toggle_experiment())

    assert workspace._measurement_table._table_view.isColumnHidden(3) is True


def test_power_table_column_visible_after_toggle() -> None:
    workspace = MeasurementWorkspace()
    workspace.configure_for_experiment(_current_voltage_power_toggle_experiment())

    workspace._optional_toggle_button.click()

    assert workspace._measurement_table._table_view.isColumnHidden(3) is False


def test_power_table_column_retains_previously_collected_rows() -> None:
    workspace = MeasurementWorkspace()
    workspace.configure_for_experiment(_current_voltage_power_toggle_experiment())
    workspace.set_ready(True)

    for voltage, current, power in ((5.0, 0.2, 1.0), (6.0, 0.3, 1.8)):
        workspace.set_measurement(
            _make_measurement(
                values={"voltage": voltage, "current": current},
                derived_values={"power": power},
            )
        )

    workspace._optional_toggle_button.click()

    assert workspace._measurement_table._model.item(0, 3).text() == "1.000"
    assert workspace._measurement_table._model.item(1, 3).text() == "1.800"


def test_optional_toggle_button_hidden_for_experiments_without_optional_channels() -> None:
    workspace = MeasurementWorkspace()

    workspace.configure_for_experiment(_ohms_law_experiment())

    assert workspace._optional_toggle_button.isHidden()


def test_optional_toggle_resets_on_experiment_switch() -> None:
    workspace = MeasurementWorkspace()
    workspace.configure_for_experiment(_current_voltage_power_toggle_experiment())
    workspace._optional_toggle_button.click()
    assert not workspace._optional_readout_widgets["power"].isHidden()

    workspace.configure_for_experiment(_current_voltage_power_toggle_experiment())

    assert workspace._optional_readout_widgets["power"].isHidden()
    assert workspace._optional_toggle_button.text() == "⚡ Қуатты көрсету"


# ---- kезeng 29: control toolbar / graph card / graph stats / splitter -----


def test_start_button_is_primary() -> None:
    workspace = MeasurementWorkspace()

    assert workspace._start_button.objectName() == "PrimaryButton"


def test_graph_table_splitter_stretch_ratio_favors_graph() -> None:
    # QSplitter setStretchFactor()-ды кейін оқитын getter бермейді, ал
    # widget нақты көрсетілмей sizes() мағынасыз (0/минимал болады) —
    # сондықтан нақты ~65:35 арақатынасын растау үшін widget-ты show()
    # етіп, нақты layout-тан кейінгі sizes()-ті тексереміз.
    #
    # Ені 1366px (бұрын 1000px болатын): Phase 33A/33B-де ғылыми
    # toolbar-ға заңды, tooltip-пен құжатталған батырмалар қосылды
    # (zoom/pan/reset/maximize/region) — graph_card-тың минималды ені
    # енді 1000px-те splitter-дің минимал-өлшем шектеуімен қақтығысады
    # (эмпирикалық түрде расталды: 1000px-те ratio 0.83-ке дейін
    # бұрмаланады, БІРАҚ 1200px+-те тұрақты ~0.67-де қалады). 1366px —
    # Phase 33A-дың ӨЗ құжатталған минималды target resolution-ы
    # ("graph should remain readable at 1366×768"), сондықтан бұл тест
    # ені сол СОЛ келісімшартты тексереді — ratio шектері (0.55-0.75)
    # ӨЗГЕРТІЛМЕДІ.
    workspace = MeasurementWorkspace()
    workspace.configure_for_experiment(_current_voltage_experiment())
    workspace.set_ready(True)
    workspace.resize(1366, 768)
    workspace.show()
    QApplication.processEvents()

    sizes = workspace._graph_table_splitter.sizes()

    assert sum(sizes) > 0
    graph_ratio = sizes[0] / sum(sizes)
    assert 0.55 < graph_ratio < 0.75


def test_graph_card_title_defaults_when_no_graph_title() -> None:
    workspace = MeasurementWorkspace()

    workspace.configure_for_experiment(_current_voltage_experiment())  # graph_title жоқ

    assert workspace._graph_card_title_label.text() == "Нақты уақыт графигі"


def test_graph_card_title_uses_definition_graph_title() -> None:
    workspace = MeasurementWorkspace()
    experiment = ExperimentDefinition(
        id="custom",
        title="Custom",
        description="",
        required_channels=(VOLTAGE, CURRENT),
        graph_y_channels=("voltage",),
        graph_title="Кернеудің уақыт бойынша өзгерісі",
    )

    workspace.configure_for_experiment(experiment)

    assert workspace._graph_card_title_label.text() == "Кернеудің уақыт бойынша өзгерісі"


def test_graph_card_live_badge_follows_running_state() -> None:
    workspace = MeasurementWorkspace()
    workspace.configure_for_experiment(_current_voltage_experiment())

    assert workspace._graph_card_live_badge.isHidden() is True

    workspace.set_experiment_running(True)
    assert workspace._graph_card_live_badge.isHidden() is False

    workspace.set_experiment_running(False)
    assert workspace._graph_card_live_badge.isHidden() is True


def test_graph_stats_hidden_without_y_channels() -> None:
    workspace = MeasurementWorkspace()
    experiment = ExperimentDefinition(
        id="no-graph", title="No graph", description="", required_channels=(VOLTAGE,)
    )

    workspace.configure_for_experiment(experiment)

    assert workspace._graph_stats_label.isHidden() is True


def test_graph_stats_min_avg_max_for_primary_y_channel() -> None:
    workspace = MeasurementWorkspace()
    workspace.configure_for_experiment(_current_voltage_experiment())  # graph_y_channels=("current",)
    workspace.set_device(_make_device())

    workspace.set_measurement(_make_measurement(values={"voltage": 1.0, "current": 0.1}))
    workspace.set_measurement(_make_measurement(values={"voltage": 1.0, "current": 0.3}))
    workspace.set_measurement(_make_measurement(values={"voltage": 1.0, "current": 0.2}))

    text = workspace._graph_stats_label.text()
    assert "MIN 0.100" in text
    assert "AVG 0.200" in text
    assert "MAX 0.300" in text


def test_graph_stats_label_is_prefixed_with_the_plotted_channel_name() -> None:
    """Phase 33A §17: MIN/AVG/MAX қай айнымалыға қатысты екенін
    presentation-деңгейінде НАҚТЫ көрсету (жаңа статистика
    архитектурасы ЕМЕС, тек лейблдеу) — current-voltage-де statistics
    graph_y_channels[0]="current"-ке ғана қатысты, "voltage"-ке ЕМЕС.
    """
    workspace = MeasurementWorkspace()
    workspace.configure_for_experiment(_current_voltage_experiment())
    workspace.set_device(_make_device())

    workspace.set_measurement(_make_measurement(values={"voltage": 1.0, "current": 0.1}))

    text = workspace._graph_stats_label.text()
    assert text.startswith("Ток:")


def test_graph_stats_reset_on_clear_measurements() -> None:
    workspace = MeasurementWorkspace()
    workspace.configure_for_experiment(_current_voltage_experiment())
    workspace.set_device(_make_device())
    workspace.set_measurement(_make_measurement(values={"voltage": 1.0, "current": 0.1}))
    assert workspace._graph_stats_label.text() != ""

    workspace.clear_measurements()

    assert workspace._graph_stats_label.text() == ""


def test_graph_stats_reset_on_reconfigure() -> None:
    workspace = MeasurementWorkspace()
    workspace.configure_for_experiment(_current_voltage_experiment())
    workspace.set_measurement(_make_measurement(values={"voltage": 1.0, "current": 0.1}))
    assert workspace._graph_stats_label.text() != ""

    workspace.configure_for_experiment(_ohms_law_experiment())

    assert workspace._graph_stats_label.text() == ""


# ---- Phase 32: shared workspace layout architecture ----------------------
#
# Root cause fixed here: ``_build_device_info_section()`` (title/id/
# firmware/model/chip/status — legacy single-device UI) used to ALWAYS
# reserve ~125px of layout height above the metric cards, even though it
# is only ever populated via ``set_device()`` (the single-device
# ``ExperimentController`` path). Every production experiment uses
# ``MultiSensorExperimentCoordinator`` and never calls ``set_device()``,
# so the section was permanently empty yet still layout-visible. These
# tests assert the *contract* (size policy / stretch factors), not pixel
# geometry, and are exercised across three structurally different
# experiments (2 metric cards, 3 metric cards, XY/scatter) to prove the
# fix is architectural, not experiment-specific.


def test_workspace_has_expanding_size_policy_both_directions() -> None:
    workspace = MeasurementWorkspace()
    policy = workspace.sizePolicy()
    assert policy.horizontalPolicy() == QSizePolicy.Policy.Expanding
    assert policy.verticalPolicy() == QSizePolicy.Policy.Expanding


def test_device_info_section_hidden_by_default() -> None:
    # ``isHidden()`` widget-тің ӨЗІНІҢ explicit setVisible(False) күйін
    # тексереді — ата-ана шынымен show() етілмегеніне (real screen
    # visibility) тәуелсіз, сондықтан бұл тесттер headless/pytest ортада
    # да нақты тексереді.
    workspace = MeasurementWorkspace()
    assert workspace._device_info_section.isHidden() is True


def test_device_info_section_shown_only_for_single_device_path() -> None:
    workspace = MeasurementWorkspace()
    workspace.set_device(_make_device())
    assert workspace._device_info_section.isHidden() is False


def test_device_info_section_hidden_again_after_clear_device() -> None:
    workspace = MeasurementWorkspace()
    workspace.set_device(_make_device())
    workspace.clear_device()
    assert workspace._device_info_section.isHidden() is True


def test_device_info_section_stays_hidden_in_multi_device_ready_flow() -> None:
    # Multi-sensor coordinator flow: set_device() ЕШҚАШАН шақырылмайды,
    # тек set_ready(True) — root cause-тың нақ өзі осы жол.
    workspace = MeasurementWorkspace()
    workspace.configure_for_experiment(_current_voltage_experiment())
    workspace.set_ready(True)
    assert workspace._device_info_section.isHidden() is True


@pytest.mark.parametrize(
    "experiment_factory",
    [_current_voltage_experiment, _current_work_power_experiment, _ohms_law_experiment],
)
def test_placeholders_section_is_the_only_stretched_item_in_device_page(
    experiment_factory,
) -> None:
    """metrics/toolbar компакт (stretch=0), graph/table scroll area primary
    stretch=1 алады — ҮШ құрылымдық түрлі тәжірибеде де (2 карточка,
    3 карточка, XY/scatter) дәл СОЛ ортақ layout, эксперимент-специфик
    геометрия жоқ.

    Phase 3 (Experiment Workspace graph geometry fix): splitter ЕНДІ
    ``_device_page_layout``-тың ТІКЕЛЕЙ баласы ЕМЕС — ол ``QScrollArea``
    (``_graph_table_scroll_area``) ІШІНДЕ, сол scroll area осы
    layout-тағы ЖАЛҒЫЗ stretch=1 алушы (§ QStackedWidget-тің минимум
    өлшемін үлкейтпеу үшін).
    """
    workspace = MeasurementWorkspace()
    workspace.configure_for_experiment(experiment_factory())

    layout = workspace._device_page_layout
    scroll_index = layout.indexOf(workspace._graph_table_scroll_area)
    assert scroll_index != -1
    assert layout.stretch(scroll_index) == 1
    assert workspace._graph_table_scroll_area.widget() is workspace._graph_table_splitter

    for index in range(layout.count()):
        if index == scroll_index:
            continue
        assert layout.stretch(index) == 0


def test_graph_table_splitter_has_expanding_size_policy() -> None:
    workspace = MeasurementWorkspace()
    policy = workspace._graph_table_splitter.sizePolicy()
    assert policy.horizontalPolicy() == QSizePolicy.Policy.Expanding
    assert policy.verticalPolicy() == QSizePolicy.Policy.Expanding


def test_graph_card_has_expanding_size_policy() -> None:
    workspace = MeasurementWorkspace()
    graph_card = workspace._graph_table_splitter.widget(0)
    policy = graph_card.sizePolicy()
    assert policy.horizontalPolicy() == QSizePolicy.Policy.Expanding
    assert policy.verticalPolicy() == QSizePolicy.Policy.Expanding


def test_measurement_table_has_expanding_size_policy() -> None:
    workspace = MeasurementWorkspace()
    policy = workspace._measurement_table.sizePolicy()
    assert policy.horizontalPolicy() == QSizePolicy.Policy.Expanding
    assert policy.verticalPolicy() == QSizePolicy.Policy.Expanding


def test_live_graph_has_expanding_size_policy() -> None:
    workspace = MeasurementWorkspace()
    policy = workspace._live_graph.sizePolicy()
    assert policy.horizontalPolicy() == QSizePolicy.Policy.Expanding
    assert policy.verticalPolicy() == QSizePolicy.Policy.Expanding


@pytest.mark.parametrize(
    "experiment_factory",
    [_current_voltage_experiment, _current_work_power_experiment, _ohms_law_experiment],
)
def test_no_fixed_or_maximum_height_on_graph_table_workspace(experiment_factory) -> None:
    """graph/table splitter-де кездейсоқ setMaximumHeight()/setFixedHeight()
    жоқ екенін тексереді — терезе биіктелген сайын splitter шексіз өсе
    алуы керек.
    """
    workspace = MeasurementWorkspace()
    workspace.configure_for_experiment(experiment_factory())
    assert workspace._graph_table_splitter.maximumHeight() >= 16777215 - 1


# =====================================================================
# Phase 3: Experiment Workspace graph geometry fix — stacked (2-plot)
# graphs must never be silently crushed below a usable height. Root
# cause: no plot widget had a minimum height, and the page lives inside
# a QStackedWidget that force-fits it to the window size regardless of
# content need. Fix: minimum height on each plot + QScrollArea fallback
# around the graph/table splitter (§ measurement_workspace.py).
# =====================================================================


def test_stacked_plots_each_have_a_usable_minimum_height() -> None:
    from ui.widgets.live_graph import _MIN_STACKED_PLOT_HEIGHT

    workspace = MeasurementWorkspace()
    workspace.configure_for_experiment(_stacked_current_voltage_experiment())

    plot_widgets = workspace._live_graph._stacked_plot_widgets
    assert len(plot_widgets) == 2
    for plot_widget in plot_widgets.values():
        assert plot_widget.minimumHeight() >= _MIN_STACKED_PLOT_HEIGHT


def test_single_plot_also_has_a_usable_minimum_height() -> None:
    from ui.widgets.live_graph import _MIN_SINGLE_PLOT_HEIGHT

    workspace = MeasurementWorkspace()
    workspace.configure_for_experiment(_ohms_law_experiment())

    assert workspace._live_graph._plot_widget.minimumHeight() >= _MIN_SINGLE_PLOT_HEIGHT


@pytest.mark.parametrize("width,height", [(1366, 768), (1920, 1080)])
def test_stacked_plots_receive_near_equal_non_trivial_height(width, height) -> None:
    """Екі stacked subplot та ТЕҢ дерлік (near-equal) биіктік алуы
    керек — ешқайсысы екіншісінен айтарлықтай кіші болмауы тиіс, әрі
    екеуі де НАҚТЫ пайдалы (non-trivial, минимумнан төмен емес) биіктік
    алуы керек, 1366×768-де ДЕ, 1920×1080-де ДЕ.
    """
    from ui.widgets.live_graph import _MIN_STACKED_PLOT_HEIGHT

    workspace = MeasurementWorkspace()
    workspace.configure_for_experiment(_stacked_current_voltage_experiment())
    workspace.set_ready(True)
    workspace.resize(width, height)
    workspace.show()
    QApplication.processEvents()

    heights = [pw.height() for pw in workspace._live_graph._stacked_plot_widgets.values()]
    assert len(heights) == 2
    for h in heights:
        assert h >= _MIN_STACKED_PLOT_HEIGHT
    assert abs(heights[0] - heights[1]) <= 4


def test_graph_table_scroll_area_scrolls_instead_of_crushing_plots_when_too_short() -> None:
    """Терезе биіктігі stacked графиктің шынайы минимумына (2 subplot +
    toolbar + карточка header) жетпейтіндей тым аз болса, plot-тар
    минимумынан ТӨМЕН сығылмауы керек — оның орнына scroll area тік
    scrollbar ұсынуы тиіс (§ "prefer stretch, scroll only if genuinely
    cannot fit").
    """
    from ui.widgets.live_graph import _MIN_STACKED_PLOT_HEIGHT

    workspace = MeasurementWorkspace()
    workspace.configure_for_experiment(_stacked_current_voltage_experiment())
    workspace.set_ready(True)
    workspace.resize(1366, 320)  # әдейі тым аз — толық сыюы мүмкін емес
    workspace.show()
    QApplication.processEvents()

    for plot_widget in workspace._live_graph._stacked_plot_widgets.values():
        assert plot_widget.height() >= _MIN_STACKED_PLOT_HEIGHT

    scroll_area = workspace._graph_table_scroll_area
    assert scroll_area.widget().height() > scroll_area.viewport().height()


@pytest.mark.parametrize("width,height", [(1366, 768), (1920, 1080)])
def test_graph_table_split_ratio_within_target_range_at_both_resolutions(width, height) -> None:
    """Graph:table арақатынасы (§ "Graph pane: approximately 65-72%,
    Table pane: approximately 28-35%") 1366×768 ЖӘНЕ 1920×1080-де ДЕ
    сақталуы керек.
    """
    workspace = MeasurementWorkspace()
    workspace.configure_for_experiment(_stacked_current_voltage_experiment())
    workspace.set_ready(True)
    workspace.resize(width, height)
    workspace.show()
    QApplication.processEvents()

    sizes = workspace._graph_table_splitter.sizes()
    assert sum(sizes) > 0
    graph_ratio = sizes[0] / sum(sizes)
    assert 0.55 < graph_ratio < 0.75


# =====================================================================
# Phase 37A: connect-device action visibility (role AND readiness)
# =====================================================================


def test_connect_action_hidden_by_default() -> None:
    workspace = MeasurementWorkspace()

    assert workspace._connect_device_button.isHidden() is True


def test_connect_action_visible_for_student_role_when_not_ready() -> None:
    workspace = MeasurementWorkspace()

    workspace.set_connect_action_visible(True)

    assert workspace._connect_device_button.isHidden() is False


def test_connect_action_auto_hides_once_ready() -> None:
    workspace = MeasurementWorkspace()
    workspace.set_connect_action_visible(True)
    assert workspace._connect_device_button.isHidden() is False

    workspace.set_ready(True)

    assert workspace._connect_device_button.isHidden() is True


def test_connect_action_reappears_if_ready_becomes_false_again() -> None:
    workspace = MeasurementWorkspace()
    workspace.set_connect_action_visible(True)
    workspace.set_ready(True)
    assert workspace._connect_device_button.isHidden() is True

    workspace.set_ready(False)

    assert workspace._connect_device_button.isHidden() is False


def test_connect_action_stays_hidden_for_teacher_role_regardless_of_readiness() -> None:
    workspace = MeasurementWorkspace()
    workspace.set_connect_action_visible(False)

    workspace.set_ready(False)
    assert workspace._connect_device_button.isHidden() is True

    workspace.set_ready(True)
    assert workspace._connect_device_button.isHidden() is True
