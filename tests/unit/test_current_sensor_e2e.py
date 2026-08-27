"""Current Sensor end-to-end интеграция тесттері.

Нақты Serial/Arduino қолданылмайды — ``FakeSerialThreadController`` арқылы
Arduino-ны имитациялайды. Voltage Sensor-мен бірдей firmware
архитектурасы (``firmware/current_sensor/current_sensor.ino``,
``docs/serial_protocol.md``). Мақсат: HELLO handshake (``SENSOR=CURRENT``),
SET_EXP/OK,EXP, measurement packet (``I=``), hardware ақаулары
(malformed line, disconnect/reconnect, port-agnostic identification) және
Voltage Sensor-мен ``MultiSensorExperimentCoordinator`` арқылы бірігуі
дұрыс өңделетінін растау.
"""

import sys

import pytest
from PySide6.QtCore import QCoreApplication, QObject, Signal

from domain.constants.sensor_types import CURRENT
from domain.entities.experiment_definition import ExperimentDefinition
from domain.entities.measurement import Measurement
from domain.entities.sensor_channel import SensorChannel
from infrastructure.serial_comm.device_identifier import DeviceIdentifier
from infrastructure.serial_comm.hello_packet_parser import HelloPacketParser
from infrastructure.serial_comm.packet_parser import PacketParser
from modules.electricity.experiment_controller import ExperimentController
from modules.electricity.experiments_config import OHMS_LAW_EXPERIMENT
from modules.electricity.multi_sensor_experiment_coordinator import (
    MultiSensorExperimentCoordinator,
)

_CURRENT_SENSOR_HELLO = (
    "TYPE=HELLO,DEV=APL-CURRENT-01,MODEL=V1,SENSOR=CURRENT,CHIP=INA226,FW=1.0"
)
_VOLTAGE_SENSOR_HELLO = (
    "TYPE=HELLO,DEV=APL-VOLTAGE-01,MODEL=V1,SENSOR=VOLTAGE,CHIP=INA226,FW=1.0"
)


@pytest.fixture(scope="module", autouse=True)
def qt_application() -> QCoreApplication:
    """QObject/Signal механизмдері үшін жалғыз QCoreApplication дана."""
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication(sys.argv)
    return app


class FakeSerialThreadController(QObject):
    """SerialThreadController-дің public сигнал/әдіс бетін қайталайтын,
    нақты Serial-мен жұмыс істемейтін тест double (Current Sensor-ды
    имитациялау үшін).
    """

    connected = Signal(str)
    disconnected = Signal()
    line_received = Signal(str)
    error_occurred = Signal(str)
    state_changed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.write_calls: list[str] = []
        self._running = False

    def connect_port(self, port_name: str, baud_rate: int) -> None:
        self._running = True
        self.connected.emit(port_name)

    def disconnect_port(self) -> None:
        self._running = False

    def write_line(self, line: str) -> None:
        self.write_calls.append(line)

    def is_running(self) -> bool:
        return self._running

    def stop(self) -> None:
        self._running = False


def _make_current_only_definition() -> ExperimentDefinition:
    """Тек "current" арнасын талап ететін минималды ExperimentDefinition —
    "pipeline механикасы" (HELLO/SET_EXP/parsing) тесттеріне арналған,
    production Ohm's-law семантикасына тәуелсіз (ол voltage-ды да талап
    етеді — 7-бөлім талабы бойынша ``CURRENT_CHANNEL.required=True``
    сақталады, сондықтан жалғыз Current Sensor-мен production
    OHMS_LAW_EXPERIMENT ешқашан валидті Measurement бермейді).
    """
    current = SensorChannel(key="current", display_name="Ток", unit="A", decimals=3)
    return ExperimentDefinition(
        id="ohms-law",
        title="Current-only сынақ",
        description="",
        required_channels=(current,),
    )


def _make_controller(
    definition: ExperimentDefinition | None = None,
) -> tuple[ExperimentController, FakeSerialThreadController]:
    fake_serial = FakeSerialThreadController()
    controller = ExperimentController(
        definition=definition or _make_current_only_definition(),
        serial_controller=fake_serial,
    )
    return controller, fake_serial


# ---- 1/2. HELLO Current Sensor parse + SENSOR=CURRENT дұрыс анықталады --


def test_hello_current_sensor_parses_correctly() -> None:
    result = HelloPacketParser().parse(_CURRENT_SENSOR_HELLO)

    assert result.success is True
    assert result.device_id == "APL-CURRENT-01"
    assert result.model == "V1"
    assert result.sensor_type == CURRENT
    assert result.chip == "INA226"
    assert result.firmware_version == "1.0"


def test_hello_current_sensor_identifies_via_device_identifier() -> None:
    fake_serial = FakeSerialThreadController()
    identified: list[object] = []
    identifier = DeviceIdentifier(serial_controller=fake_serial)
    identifier.device_identified.connect(identified.append)

    identifier.identify("COM4", 115200)
    fake_serial.connected.emit("COM4")
    fake_serial.line_received.emit(_CURRENT_SENSOR_HELLO)

    assert len(identified) == 1
    assert identified[0].sensor_type == CURRENT
    assert identified[0].device_id == "APL-CURRENT-01"


# ---- 3. SET_EXP дұрыс жіберіледі --------------------------------------


def test_start_sends_set_exp_with_real_experiment_id() -> None:
    controller, fake_serial = _make_controller()

    controller.start_experiment()

    assert fake_serial.write_calls == [f"SET_EXP={OHMS_LAW_EXPERIMENT.id}"]


# ---- 4. OK,EXP acknowledgement дұрыс қабылданады -----------------------


def test_matching_set_exp_ack_produces_no_warning() -> None:
    controller, fake_serial = _make_controller()
    controller.start_experiment()
    warnings: list[str] = []
    controller.warning_occurred.connect(warnings.append)

    fake_serial.line_received.emit(f"OK,EXP={OHMS_LAW_EXPERIMENT.id}")

    assert warnings == []


def test_mismatched_set_exp_ack_emits_warning() -> None:
    controller, fake_serial = _make_controller()
    controller.start_experiment()
    warnings: list[str] = []
    controller.warning_occurred.connect(warnings.append)

    fake_serial.line_received.emit("OK,EXP=current-voltage")

    assert len(warnings) == 1
    assert "current-voltage" in warnings[0]
    assert OHMS_LAW_EXPERIMENT.id in warnings[0]


# ---- 5. Current measurement packet дұрыс parse болады -------------------


def test_current_measurement_packet_parses_with_real_experiment_id() -> None:
    result = PacketParser().parse_line(f"EXP={OHMS_LAW_EXPERIMENT.id},I=0.218")

    assert result.is_valid is True
    assert result.experiment_id == OHMS_LAW_EXPERIMENT.id
    assert result.values == {"current": 0.218}


def test_current_only_packet_creates_measurement_under_local_definition() -> None:
    controller, fake_serial = _make_controller()
    controller.start_experiment()
    received: list[Measurement] = []
    controller.measurement_ready.connect(received.append)

    fake_serial.line_received.emit(f"EXP={OHMS_LAW_EXPERIMENT.id},I=0.218")

    assert len(received) == 1
    assert received[0].values == {"current": 0.218}


# ---- 6. Қате EXP reject болады ------------------------------------------


def test_exp_mismatch_is_rejected() -> None:
    controller, fake_serial = _make_controller()
    controller.start_experiment()
    warnings: list[str] = []
    controller.warning_occurred.connect(warnings.append)

    fake_serial.line_received.emit("EXP=current-voltage,I=0.218")

    assert warnings
    assert controller.session.measurement_count == 0


# ---- 7. Malformed packet application-ды құлатпайды ----------------------


def test_malformed_line_does_not_crash() -> None:
    controller, fake_serial = _make_controller()
    controller.start_experiment()
    parse_errors: list[str] = []
    controller.parse_error.connect(parse_errors.append)

    fake_serial.line_received.emit("EXP=ohms-law,I=,,\x00GARBAGE")

    assert parse_errors
    assert controller.session.measurement_count == 0


# ---- 8. Disconnect/reconnect жұмыс істейді ------------------------------


def test_disconnect_then_reconnect_reidentifies_device() -> None:
    fake_serial = FakeSerialThreadController()
    identified: list[object] = []
    identifier = DeviceIdentifier(serial_controller=fake_serial)
    identifier.device_identified.connect(identified.append)

    identifier.identify("COM4", 115200)
    fake_serial.connected.emit("COM4")
    fake_serial.line_received.emit(_CURRENT_SENSOR_HELLO)
    assert len(identified) == 1

    fake_serial.disconnected.emit()
    identifier.identify("COM4", 115200)
    fake_serial.connected.emit("COM4")
    fake_serial.line_received.emit(_CURRENT_SENSOR_HELLO)

    assert len(identified) == 2
    assert identified[-1].sensor_type == CURRENT


# ---- 9. Current Sensor кез келген COM port-та анықталады ---------------


@pytest.mark.parametrize("port_name", ["COM4", "COM9", "COM12"])
def test_current_sensor_identifies_regardless_of_com_port(port_name: str) -> None:
    fake_serial = FakeSerialThreadController()
    identified: list[object] = []
    identifier = DeviceIdentifier(serial_controller=fake_serial)
    identifier.device_identified.connect(identified.append)

    identifier.identify(port_name, 115200)
    fake_serial.connected.emit(port_name)
    fake_serial.line_received.emit(_CURRENT_SENSOR_HELLO)

    assert len(identified) == 1
    assert identified[0].sensor_type == CURRENT
    assert identified[0].port_name == port_name


# ---- 10. Voltage + Current MultiSensorExperimentCoordinator арқылы бірігеді


def test_voltage_and_current_combine_via_coordinator(monkeypatch: pytest.MonkeyPatch) -> None:
    # Persistent connection architecture: coordinator енді SerialThreadController-ды
    # өзі жасамайды — DeviceManager арқылы ғана. Fake осында сол модульге
    # ендіріледі, DeviceIdentifier/HELLO parsing НАҚТЫ жұмыс істейді.
    import infrastructure.serial_comm.device_manager as device_manager_module
    from infrastructure.serial_comm.device_manager import DeviceManager

    fakes_by_port: dict[str, FakeSerialThreadController] = {}

    class _PendingFake(FakeSerialThreadController):
        def connect_port(self, port_name: str, baud_rate: int) -> None:
            fakes_by_port[port_name] = self
            super().connect_port(port_name, baud_rate)

    monkeypatch.setattr(
        device_manager_module, "SerialThreadController", lambda *a, **k: _PendingFake()
    )

    device_manager = DeviceManager()
    coordinator = MultiSensorExperimentCoordinator(
        definition=OHMS_LAW_EXPERIMENT, device_manager=device_manager
    )
    received: list[Measurement] = []
    coordinator.measurement_ready.connect(received.append)

    # Voltage Sensor-ды тіркеу (кез келген порт атауы — мыс. COM7).
    coordinator.identify_device("COM7", 115200)
    fakes_by_port["COM7"].line_received.emit(_VOLTAGE_SENSOR_HELLO)

    # Current Sensor-ды тіркеу (кез келген порт атауы — мыс. COM5, реті
    # де маңызды емес).
    coordinator.identify_device("COM5", 115200)
    fakes_by_port["COM5"].line_received.emit(_CURRENT_SENSOR_HELLO)

    assert coordinator.is_ready() is True

    coordinator.start_experiment()
    # ACK-gated start: running=True тек екі порттан да сәйкес SET_EXP
    # ACK келгеннен кейін ғана болады.
    fakes_by_port["COM7"].line_received.emit(f"OK,EXP={OHMS_LAW_EXPERIMENT.id}")
    fakes_by_port["COM5"].line_received.emit(f"OK,EXP={OHMS_LAW_EXPERIMENT.id}")
    assert coordinator.is_running() is True

    fakes_by_port["COM7"].line_received.emit(f"EXP={OHMS_LAW_EXPERIMENT.id},U=5.024")
    assert received == []  # тек voltage келді — current әлі жоқ

    fakes_by_port["COM5"].line_received.emit(f"EXP={OHMS_LAW_EXPERIMENT.id},I=0.218")

    assert len(received) == 1
    measurement = received[0]
    assert measurement.values == {"voltage": 5.024, "current": 0.218}
    assert measurement.derived_values["resistance"] == pytest.approx(23.046, rel=1e-3)


def test_voltage_only_still_rejected_without_current_sensor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 7-бөлім талабы: CURRENT_CHANNEL.required=True сақталады, сондықтан
    # Current Sensor қосылмаса, тек Voltage Sensor-мен Measurement
    # жасалмауы керек (Ohm's Law-да ток та шынымен қажет).
    import infrastructure.serial_comm.device_manager as device_manager_module
    from infrastructure.serial_comm.device_manager import DeviceManager

    fakes_by_port: dict[str, FakeSerialThreadController] = {}

    class _PendingFake(FakeSerialThreadController):
        def connect_port(self, port_name: str, baud_rate: int) -> None:
            fakes_by_port[port_name] = self
            super().connect_port(port_name, baud_rate)

    monkeypatch.setattr(
        device_manager_module, "SerialThreadController", lambda *a, **k: _PendingFake()
    )

    device_manager = DeviceManager()
    coordinator = MultiSensorExperimentCoordinator(
        definition=OHMS_LAW_EXPERIMENT, device_manager=device_manager
    )
    received: list[Measurement] = []
    coordinator.measurement_ready.connect(received.append)

    coordinator.identify_device("COM7", 115200)
    fakes_by_port["COM7"].line_received.emit(_VOLTAGE_SENSOR_HELLO)

    assert coordinator.is_ready() is False

    # is_ready()==False болғандықтан start_experiment() ештеңе істемейді,
    # бірақ тіпті running=True мәжбүрлеп қойылса да (соft-defense), aggregator
    # current ешқашан келмегендіктен толық snapshot қайтармайды.
    coordinator.start_experiment()
    fakes_by_port["COM7"].line_received.emit(f"EXP={OHMS_LAW_EXPERIMENT.id},U=5.024")

    assert received == []
