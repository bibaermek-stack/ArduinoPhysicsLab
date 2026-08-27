"""ExperimentController үшін юнит-тесттер: raw line → Measurement pipeline.

Нақты QSerialPort/SerialThreadController қолданылмайды — оның орнына
осы файлда анықталған ``FakeSerialThreadController`` (тест double)
қолданылады.
"""

import sys

import pytest
from PySide6.QtCore import QCoreApplication, QObject, Signal

from domain.entities.connected_device import ConnectedDevice
from domain.entities.experiment_definition import ExperimentDefinition
from domain.entities.measurement import Measurement
from domain.entities.sensor_channel import SensorChannel
from modules.electricity.experiment_controller import ExperimentController


@pytest.fixture(scope="module", autouse=True)
def qt_application() -> QCoreApplication:
    """QObject/Signal механизмдері үшін жалғыз QCoreApplication дана."""
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication(sys.argv)
    return app


class FakeSerialThreadController(QObject):
    """SerialThreadController-дің public сигнал/әдіс бетін қайталайтын,
    нақты Serial-мен жұмыс істемейтін тест double.
    """

    connected = Signal(str)
    disconnected = Signal()
    line_received = Signal(str)
    error_occurred = Signal(str)
    state_changed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.connect_calls: list[tuple[str, int]] = []
        self.disconnect_calls: int = 0
        self.write_calls: list[str] = []
        self.stop_calls: int = 0
        self._running = False

    def connect_port(self, port_name: str, baud_rate: int) -> None:
        self.connect_calls.append((port_name, baud_rate))
        self._running = True

    def disconnect_port(self) -> None:
        self.disconnect_calls += 1
        self._running = False

    def stop(self) -> None:
        self.stop_calls += 1
        self._running = False

    def write_line(self, line: str) -> None:
        self.write_calls.append(line)

    def is_running(self) -> bool:
        return self._running


def _make_definition() -> ExperimentDefinition:
    voltage = SensorChannel(
        key="voltage", display_name="Кернеу", unit="V", minimum=0.0, maximum=10.0
    )
    current = SensorChannel(
        key="current", display_name="Ток күші", unit="A", minimum=0.0, maximum=2.0
    )
    resistance = SensorChannel(
        key="resistance", display_name="Кедергі", unit="Ω", required=False
    )
    return ExperimentDefinition(
        id="E02",
        title="Тізбек бөлігі үшін кернеудің ток күшіне тәуелділігін зерттеу",
        description="",
        required_channels=(voltage, current),
        derived_channels=(resistance,),
        formulas={"resistance": "R = U / I"},
    )


def _make_controller(
    definition: ExperimentDefinition | None = None,
) -> tuple[ExperimentController, FakeSerialThreadController]:
    fake_serial = FakeSerialThreadController()
    controller = ExperimentController(
        definition=definition or _make_definition(),
        serial_controller=fake_serial,
    )
    return controller, fake_serial


def test_valid_packet_creates_measurement() -> None:
    controller, fake_serial = _make_controller()
    controller.start_experiment()
    received: list[Measurement] = []
    controller.measurement_ready.connect(received.append)

    fake_serial.line_received.emit("EXP=E02,U=5.0,I=0.5")

    assert len(received) == 1
    measurement = received[0]
    assert measurement.experiment_id == "E02"
    assert measurement.values == {"voltage": 5.0, "current": 0.5}
    assert measurement.derived_values["resistance"] == pytest.approx(10.0)


def test_valid_packet_is_added_to_session() -> None:
    controller, fake_serial = _make_controller()
    controller.start_experiment()

    fake_serial.line_received.emit("EXP=E02,U=5.0,I=0.5")

    assert controller.session.measurement_count == 1


def test_invalid_packet_emits_parse_error() -> None:
    controller, fake_serial = _make_controller()
    controller.start_experiment()
    errors: list[str] = []
    controller.parse_error.connect(errors.append)

    fake_serial.line_received.emit("U=5.0,I=0.2")  # EXP жоқ

    assert errors
    assert controller.session.measurement_count == 0


def test_validation_failure_prevents_measurement() -> None:
    controller, fake_serial = _make_controller()
    controller.start_experiment()
    errors: list[str] = []
    controller.validation_error.connect(errors.append)

    fake_serial.line_received.emit("EXP=E02,U=999.0,I=0.5")  # voltage max=10.0-тан асып тұр

    assert errors
    assert controller.session.measurement_count == 0


def test_wrong_experiment_id_emits_warning() -> None:
    controller, fake_serial = _make_controller()
    controller.start_experiment()
    warnings: list[str] = []
    controller.warning_occurred.connect(warnings.append)

    fake_serial.line_received.emit("EXP=E99,U=5.0,I=0.5")

    assert warnings
    assert controller.session.measurement_count == 0


def test_stopped_experiment_ignores_packet() -> None:
    # kезeng 28: running=False кезінде сәйкес EXP пакеті келсе, ол ҮНСІЗ
    # (debug-лог ғана, APL_DEBUG_SERIAL=1 болмаса көрінбейді) өткізіп
    # жіберіледі — бұл ҚАЛЫПТЫ, күтілетін жағдай (Arduino ағыны Stop-қа
    # тәуелсіз үздіксіз жалғасады), сондықтан ЕНДІ көрінетін
    # warning_occurred эмиссиясы ЖОҚ. Пакет өзі әлі де толық тасталады.
    controller, fake_serial = _make_controller()
    # controller.start_experiment() әдейі шақырылмаған — running емес.
    warnings: list[str] = []
    controller.warning_occurred.connect(warnings.append)

    fake_serial.line_received.emit("EXP=E02,U=5.0,I=0.5")

    assert warnings == []
    assert controller.session.measurement_count == 0


def test_unknown_formula_key_emits_warning_but_creates_measurement() -> None:
    voltage = SensorChannel(key="voltage", display_name="Кернеу", unit="V")
    current = SensorChannel(key="current", display_name="Ток күші", unit="A")
    definition = ExperimentDefinition(
        id="E02",
        title="Тест",
        description="",
        required_channels=(voltage, current),
        formulas={"speed": "v = d / t"},  # CalculationEngine-де жоқ калькулятор
    )
    controller, fake_serial = _make_controller(definition)
    controller.start_experiment()

    warnings: list[str] = []
    received: list[Measurement] = []
    controller.warning_occurred.connect(warnings.append)
    controller.measurement_ready.connect(received.append)

    fake_serial.line_received.emit("EXP=E02,U=5.0,I=0.5")

    assert len(received) == 1
    assert any("speed" in warning for warning in warnings)
    assert any("speed" in warning for warning in received[0].warnings)
    assert "speed" not in received[0].derived_values


def test_serial_error_is_forwarded() -> None:
    controller, fake_serial = _make_controller()
    errors: list[str] = []
    controller.error_occurred.connect(errors.append)

    fake_serial.error_occurred.emit("Port access denied")

    assert errors == ["Port access denied"]


def test_empty_line_is_ignored() -> None:
    controller, fake_serial = _make_controller()
    controller.start_experiment()
    parse_errors: list[str] = []
    warnings: list[str] = []
    controller.parse_error.connect(parse_errors.append)
    controller.warning_occurred.connect(warnings.append)

    fake_serial.line_received.emit("")
    fake_serial.line_received.emit("   ")

    assert parse_errors == []
    assert warnings == []
    assert controller.session.measurement_count == 0


def test_multiple_valid_packets_preserve_order() -> None:
    controller, fake_serial = _make_controller()
    controller.start_experiment()

    fake_serial.line_received.emit("EXP=E02,U=1.0,I=0.5")
    fake_serial.line_received.emit("EXP=E02,U=2.0,I=0.5")
    fake_serial.line_received.emit("EXP=E02,U=3.0,I=0.5")

    assert controller.session.measurement_count == 3
    voltages = [m.values["voltage"] for m in controller.session.measurements]
    assert voltages == [1.0, 2.0, 3.0]


# ---- HELLO routing (DeviceIdentifier интеграциясы) ----------------------


def test_hello_packet_does_not_emit_parse_error() -> None:
    controller, fake_serial = _make_controller()
    controller.start_experiment()
    parse_errors: list[str] = []
    controller.parse_error.connect(parse_errors.append)

    fake_serial.line_received.emit(
        "TYPE=HELLO,DEV=APL-VOLTAGE-01,MODEL=V1,SENSOR=VOLTAGE,CHIP=INA226,FW=1.0"
    )

    assert parse_errors == []
    assert controller.session.measurement_count == 0


def test_measurement_packet_still_processed_after_hello_line() -> None:
    controller, fake_serial = _make_controller()
    controller.start_experiment()
    received: list[Measurement] = []
    controller.measurement_ready.connect(received.append)

    fake_serial.line_received.emit(
        "TYPE=HELLO,DEV=APL-VOLTAGE-01,MODEL=V1,SENSOR=VOLTAGE,CHIP=INA226,FW=1.0"
    )
    fake_serial.line_received.emit("EXP=E02,U=5.0,I=0.5")

    assert len(received) == 1
    assert received[0].values == {"voltage": 5.0, "current": 0.5}


def test_identified_device_is_registered() -> None:
    controller, fake_serial = _make_controller()

    controller.identify_device("COM3", 115200)
    fake_serial.connected.emit("COM3")
    fake_serial.line_received.emit(
        "TYPE=HELLO,DEV=APL-VOLTAGE-01,MODEL=V1,SENSOR=VOLTAGE,CHIP=INA226,FW=1.0"
    )

    registered = controller.device_registry.get_by_port("COM3")
    assert registered is not None
    assert registered.device_id == "APL-VOLTAGE-01"
    assert registered.model == "V1"


def test_shutdown_stops_serial_controller() -> None:
    controller, fake_serial = _make_controller()

    controller.shutdown()

    assert fake_serial.stop_calls == 1


def test_device_identified_signal_is_forwarded() -> None:
    controller, fake_serial = _make_controller()
    devices: list[ConnectedDevice] = []
    controller.device_identified.connect(devices.append)

    controller.identify_device("COM3", 115200)
    fake_serial.connected.emit("COM3")
    fake_serial.line_received.emit(
        "TYPE=HELLO,DEV=APL-CURRENT-01,MODEL=V1,SENSOR=CURRENT,CHIP=INA226,FW=1.0"
    )

    assert len(devices) == 1
    assert devices[0].sensor_type == "CURRENT"
