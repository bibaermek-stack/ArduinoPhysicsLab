"""Voltage Sensor end-to-end интеграция тесттері (V1.0 -> hardware кезеңі).

Нақты Serial/Arduino қолданылмайды — ``FakeSerialThreadController`` арқылы
Arduino-ны имитациялайды. Мақсат: HELLO handshake, measurement packet,
SET_EXP/OK,EXP хаттама кеңейтуі, және hardware ақаулары (malformed line,
disconnect, delayed first packet, repeated HELLO, reconnect) дұрыс
өңделетінін растау.

Multi-device аудиттен кейін (``CURRENT_CHANNEL.required=True`` қайта
қалпына келтірілді): жалғыз Voltage Sensor-мен ``current-voltage``/
``ohms-law`` секілді ЕКІ сенсор қажет ететін тәжірибелер енді толық
валидті Measurement бермейді (бұл — дұрыс физика, current өлшенбесе,
validation error шығуы тиіс). Осы файлдағы "pipeline механикасы"
тесттері (HELLO/SET_EXP/parsing) жалғыз-каналды локал ExperimentDefinition
қолданады — ``ExperimentController`` өзі single-sensor сынақтары үшін
өзгеріссіз қалады.
"""

import sys

import pytest
from PySide6.QtCore import QCoreApplication, QObject, Signal

from domain.constants.sensor_types import VOLTAGE
from domain.entities.experiment_definition import ExperimentDefinition
from domain.entities.measurement import Measurement
from domain.entities.sensor_channel import SensorChannel
from infrastructure.serial_comm.device_identifier import DeviceIdentifier
from infrastructure.serial_comm.hello_packet_parser import HelloPacketParser
from infrastructure.serial_comm.packet_parser import PacketParser
from modules.electricity.experiment_controller import ExperimentController
from modules.electricity.experiments_config import (
    CURRENT_VOLTAGE_EXPERIMENT,
    OHMS_LAW_EXPERIMENT,
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
    нақты Serial-мен жұмыс істемейтін тест double (Voltage Sensor-ды
    имитациялау үшін).
    """

    connected = Signal(str)
    disconnected = Signal()
    line_received = Signal(str)
    error_occurred = Signal(str)
    state_changed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.connect_calls: list[tuple[str, int]] = []
        self.write_calls: list[str] = []
        self._running = False

    def connect_port(self, port_name: str, baud_rate: int) -> None:
        self.connect_calls.append((port_name, baud_rate))
        self._running = True

    def disconnect_port(self) -> None:
        self._running = False

    def write_line(self, line: str) -> None:
        self.write_calls.append(line)

    def is_running(self) -> bool:
        return self._running

    def stop(self) -> None:
        self._running = False


def _make_voltage_only_definition() -> ExperimentDefinition:
    """Тек "voltage" арнасын талап ететін минималды ExperimentDefinition —
    "pipeline механикасы" (HELLO шуы, keyінгі жол әлі парсингтеледі ме)
    тесттеріне арналған, production Ohm's-law семантикасына тәуелсіз.
    """
    voltage = SensorChannel(key="voltage", display_name="Кернеу", unit="V", decimals=3)
    return ExperimentDefinition(
        id="current-voltage", title="Voltage-only сынақ", description="",
        required_channels=(voltage,),
    )


def _make_controller(definition=None) -> tuple[ExperimentController, FakeSerialThreadController]:
    fake_serial = FakeSerialThreadController()
    controller = ExperimentController(
        definition=definition or CURRENT_VOLTAGE_EXPERIMENT,
        serial_controller=fake_serial,
    )
    return controller, fake_serial


# ---- 1. HELLO Voltage Sensor parse ---------------------------------------


def test_hello_voltage_sensor_parses_correctly() -> None:
    result = HelloPacketParser().parse(_VOLTAGE_SENSOR_HELLO)

    assert result.success is True
    assert result.device_id == "APL-VOLTAGE-01"
    assert result.model == "V1"
    assert result.sensor_type == VOLTAGE
    assert result.chip == "INA226"
    assert result.firmware_version == "1.0"


# ---- 2. Voltage measurement packet parse ---------------------------------


def test_voltage_measurement_packet_parses_with_real_experiment_id() -> None:
    result = PacketParser().parse_line(f"EXP={CURRENT_VOLTAGE_EXPERIMENT.id},U=5.024")

    assert result.is_valid is True
    assert result.experiment_id == CURRENT_VOLTAGE_EXPERIMENT.id
    assert result.values == {"voltage": 5.024}


# ---- 3. EXP mismatch бұрынғыдай reject -----------------------------------


def test_exp_mismatch_still_rejected() -> None:
    controller, fake_serial = _make_controller(CURRENT_VOLTAGE_EXPERIMENT)
    controller.start_experiment()
    warnings: list[str] = []
    controller.warning_occurred.connect(warnings.append)

    fake_serial.line_received.emit(f"EXP={OHMS_LAW_EXPERIMENT.id},U=5.024")

    assert warnings
    assert controller.session.measurement_count == 0


# ---- 4/6. SET_EXP command formatting + Start кезінде жіберіледі ---------


def test_no_set_exp_sent_before_start() -> None:
    _controller, fake_serial = _make_controller(CURRENT_VOLTAGE_EXPERIMENT)

    assert fake_serial.write_calls == []


def test_start_sends_set_exp_with_real_experiment_id() -> None:
    controller, fake_serial = _make_controller(OHMS_LAW_EXPERIMENT)

    controller.start_experiment()

    assert fake_serial.write_calls == [f"SET_EXP={OHMS_LAW_EXPERIMENT.id}"]


# ---- 5. SET_EXP acknowledgement parse/handling ---------------------------


def test_matching_set_exp_ack_produces_no_warning() -> None:
    controller, fake_serial = _make_controller(OHMS_LAW_EXPERIMENT)
    controller.start_experiment()
    warnings: list[str] = []
    controller.warning_occurred.connect(warnings.append)

    fake_serial.line_received.emit(f"OK,EXP={OHMS_LAW_EXPERIMENT.id}")

    assert warnings == []


def test_mismatched_set_exp_ack_emits_warning() -> None:
    controller, fake_serial = _make_controller(OHMS_LAW_EXPERIMENT)
    controller.start_experiment()
    warnings: list[str] = []
    controller.warning_occurred.connect(warnings.append)

    fake_serial.line_received.emit("OK,EXP=current-voltage")

    assert len(warnings) == 1
    assert "current-voltage" in warnings[0]
    assert OHMS_LAW_EXPERIMENT.id in warnings[0]


def test_set_exp_ack_does_not_emit_parse_error() -> None:
    controller, fake_serial = _make_controller(OHMS_LAW_EXPERIMENT)
    controller.start_experiment()
    parse_errors: list[str] = []
    controller.parse_error.connect(parse_errors.append)

    fake_serial.line_received.emit(f"OK,EXP={OHMS_LAW_EXPERIMENT.id}")

    assert parse_errors == []


# ---- 7. Experiment switch кезінде жаңа ID жіберіледі ---------------------


def test_experiment_switch_sends_different_id_to_new_controller() -> None:
    # Қолданыстағы архитектурада тәжірибе ауысу — жаңа ExperimentController
    # құру дегенді білдіреді (ExperimentWorkspacePage.on_enter), сондықтан
    # екі бөлек controller/serial жұбымен модельдейміз.
    first_controller, first_serial = _make_controller(CURRENT_VOLTAGE_EXPERIMENT)
    second_controller, second_serial = _make_controller(OHMS_LAW_EXPERIMENT)

    first_controller.start_experiment()
    second_controller.start_experiment()

    assert first_serial.write_calls == [f"SET_EXP={CURRENT_VOLTAGE_EXPERIMENT.id}"]
    assert second_serial.write_calls == [f"SET_EXP={OHMS_LAW_EXPERIMENT.id}"]


# ---- 8. Malformed Arduino line crash жасамайды ---------------------------


def test_malformed_line_does_not_crash() -> None:
    controller, fake_serial = _make_controller(CURRENT_VOLTAGE_EXPERIMENT)
    controller.start_experiment()
    parse_errors: list[str] = []
    controller.parse_error.connect(parse_errors.append)

    # Arduino reset/electrical noise кезінде пайда болуы мүмкін бұзылған жол.
    fake_serial.line_received.emit("EXP=current-voltage,U=,,\x00\x01GARBAGE")

    assert parse_errors  # errors шықты
    assert controller.session.measurement_count == 0  # бірақ құламады


def test_empty_and_whitespace_lines_do_not_crash() -> None:
    controller, fake_serial = _make_controller(CURRENT_VOLTAGE_EXPERIMENT)
    controller.start_experiment()
    parse_errors: list[str] = []
    controller.parse_error.connect(parse_errors.append)

    fake_serial.line_received.emit("")
    fake_serial.line_received.emit("   \t  ")

    assert parse_errors == []
    assert controller.session.measurement_count == 0


# ---- 9. Disconnect handling -----------------------------------------------


def test_disconnect_while_running_is_forwarded_without_crash() -> None:
    controller, fake_serial = _make_controller(CURRENT_VOLTAGE_EXPERIMENT)
    controller.start_experiment()
    disconnects: list[None] = []
    controller.disconnected.connect(lambda: disconnects.append(None))

    fake_serial.disconnected.emit()

    assert disconnects == [None]
    assert controller.is_running() is True  # ExperimentController өзі тоқтатпайды
    # — бұл жауапкершілік ExperimentWorkspacePage-те (жоғарғы деңгейде).


def test_usb_unplug_error_is_forwarded_without_crash() -> None:
    controller, fake_serial = _make_controller(CURRENT_VOLTAGE_EXPERIMENT)
    errors: list[str] = []
    controller.error_occurred.connect(errors.append)

    fake_serial.error_occurred.emit("Device disappeared from the system")

    assert errors == ["Device disappeared from the system"]


# ---- 10. Delayed first measurement ---------------------------------------


def test_delayed_first_measurement_after_warmup_noise() -> None:
    # voltage-only анықтама қолданылады — бұл тест pipeline механикасын
    # (HELLO шуынан кейін де келесі жол дұрыс парсингтеле ме) тексереді,
    # production Ohm's-law валидациясына қатысы жоқ (ол екі сенсорды талап
    # етеді, төмендегі test_voltage_only_packet_now_rejected_under_production_definition
    # тестін қараңыз).
    controller, fake_serial = _make_controller(_make_voltage_only_definition())
    controller.start_experiment()
    received: list[Measurement] = []
    controller.measurement_ready.connect(received.append)

    # Arduino қосылғаннан кейін бірден дайын болмауы мүмкін — бос
    # жолдар/HELLO handshake қалдықтары бірнеше "кадр" бойы келуі мүмкін,
    # содан кейін ғана нақты measurement келеді.
    fake_serial.line_received.emit("")
    fake_serial.line_received.emit(_VOLTAGE_SENSOR_HELLO)
    fake_serial.line_received.emit("")
    fake_serial.line_received.emit("EXP=current-voltage,U=5.024")

    assert len(received) == 1
    assert received[0].values == {"voltage": 5.024}


def test_voltage_only_packet_now_rejected_under_production_definition() -> None:
    # Audit-тың шешімі: CURRENT_CHANNEL.required=True қайта қалпына келді,
    # сондықтан жалғыз Voltage Sensor-мен (I= жоқ) production
    # CURRENT_VOLTAGE_EXPERIMENT ешқашан валидті Measurement бермеуі
    # керек — бұл дұрыс физика (multi-device аудитте расталған тәртіп).
    controller, fake_serial = _make_controller(CURRENT_VOLTAGE_EXPERIMENT)
    controller.start_experiment()
    received: list[Measurement] = []
    validation_errors: list[str] = []
    controller.measurement_ready.connect(received.append)
    controller.validation_error.connect(validation_errors.append)

    fake_serial.line_received.emit("EXP=current-voltage,U=5.024")

    assert received == []
    assert validation_errors


# ---- 11. Repeated HELLO ---------------------------------------------------


def test_repeated_hello_identify_calls_do_not_duplicate_or_crash() -> None:
    fake_serial = FakeSerialThreadController()
    identified: list[object] = []
    identifier = DeviceIdentifier(serial_controller=fake_serial)
    identifier.device_identified.connect(identified.append)

    identifier.identify("COM3", 115200)
    fake_serial.connected.emit("COM3")
    fake_serial.line_received.emit(_VOLTAGE_SENSOR_HELLO)

    # Пайдаланушы "Анықтау" батырмасын қайта басады (бұрынғы handshake
    # аяқталған болса да).
    identifier.identify("COM3", 115200)
    fake_serial.connected.emit("COM3")
    fake_serial.line_received.emit(_VOLTAGE_SENSOR_HELLO)

    assert len(identified) == 2
    assert all(device.device_id == "APL-VOLTAGE-01" for device in identified)


# ---- 12. Reconnect ---------------------------------------------------------


def test_reconnect_after_disconnect_reregisters_device() -> None:
    controller, fake_serial = _make_controller(CURRENT_VOLTAGE_EXPERIMENT)

    controller.identify_device("COM3", 115200)
    fake_serial.connected.emit("COM3")
    fake_serial.line_received.emit(_VOLTAGE_SENSOR_HELLO)
    assert controller.device_registry.get_by_port("COM3") is not None

    # USB ажыратылды, содан кейін қайта жалғанды (қайта identify).
    fake_serial.disconnected.emit()
    controller.identify_device("COM3", 115200)
    fake_serial.connected.emit("COM3")
    fake_serial.line_received.emit(_VOLTAGE_SENSOR_HELLO)

    device = controller.device_registry.get_by_port("COM3")
    assert device is not None
    assert device.device_id == "APL-VOLTAGE-01"
