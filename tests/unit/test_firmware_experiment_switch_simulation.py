"""Multi-experiment SET_EXP hardware bug — host-side firmware simulation.

Бұл файл нақты hardware-сіз, толық Python ортасында, ``voltage_sensor.ino``/
``current_sensor.ino``-дағы SET_EXP/measurement-tagging логикасының дәл
1:1 моделін (``FakeArduinoFirmware``) қолданып, PC-жақтың
(``MultiSensorExperimentCoordinator``/``ExperimentWorkspacePage``/
``DeviceManager``) НАҚТЫ кодымен толық round-trip сценарийін тексереді.

Мақсаты екі жақты:
1. Нақты hardware-де табылған bug-тың root cause-ын (асимметриялы boot
   default нақты тәжірибе id-мен кездейсоқ сәйкес келуі мүмкін еді)
   дәлелдеу — ескі "ohms-law"/"current-voltage" default-тарды қайта
   құрастырып, класс ретінде қалай "silent" ақау тудыратынын көрсету.
2. Түзетілген (бос default) firmware моделінің барлық 5 іске асырылған
   электр тәжірибесі арасында ауысу кезінде дұрыс жұмыс істейтінін
   растау — ЕШБІР қайта identify/reconnect жасалмай.
"""

import sys

import pytest
from PySide6.QtCore import QObject, Signal

import infrastructure.serial_comm.device_manager as device_manager_module
from domain.entities.active_student_context import ActiveStudentContext
from infrastructure.serial_comm.device_manager import DeviceManager
from infrastructure.serial_comm.device_scanner import DeviceScanner
from infrastructure.serial_comm.packet_parser import PacketParser
from infrastructure.storage.sqlite_active_student_repository import SqliteActiveStudentRepository
from modules.electricity.experiments_config import (
    CURRENT_VOLTAGE_EXPERIMENT,
    CURRENT_WORK_POWER_EXPERIMENT,
    OHMS_LAW_EXPERIMENT,
    PARALLEL_CONNECTION_EXPERIMENT,
    SERIES_CONNECTION_EXPERIMENT,
)
from ui.pages.experiment_workspace_page import ExperimentWorkspacePage


def _make_seeded_active_student_repository() -> SqliteActiveStudentRepository:
    repository = SqliteActiveStudentRepository()
    repository.set(ActiveStudentContext(classroom_id="test-classroom", student_id="test-student"))
    return repository


_VOLTAGE_HELLO = "TYPE=HELLO,DEV=APL-VOLTAGE-01,MODEL=V1,SENSOR=VOLTAGE,CHIP=INA226,FW=1.0"
_CURRENT_HELLO = "TYPE=HELLO,DEV=APL-CURRENT-01,MODEL=V1,SENSOR=CURRENT,CHIP=INA226,FW=1.0"

# Спецификацияның 12-бөліміндегі нақты тексеру реті.
_FULL_EXPERIMENT_SWITCH_SEQUENCE = (
    OHMS_LAW_EXPERIMENT,
    CURRENT_VOLTAGE_EXPERIMENT,
    SERIES_CONNECTION_EXPERIMENT,
    PARALLEL_CONNECTION_EXPERIMENT,
    CURRENT_WORK_POWER_EXPERIMENT,
    OHMS_LAW_EXPERIMENT,
)


@pytest.fixture(scope="module", autouse=True)
def qt_application():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


_SUPPORTED_EXPERIMENT_IDS = frozenset(
    {
        "current-voltage",
        "series-connection",
        "parallel-connection",
        "current-work-power",
        "ohms-law",
    }
)


class FakeArduinoFirmware:
    """``voltage_sensor.ino``/``current_sensor.ino``-дың SET_EXP/measurement
    logic-ының дәл 1:1 Python моделі (kезeng 27 түзетуінен КЕЙІНГІ нұсқа —
    бос boot default + whitelist validation, heap-based ``String`` ЖОҚ).

    ``handle_command()`` — firmware-дегі ``handleLine()``-мен бірдей:
    ``SET_EXP=<id>`` келсе, тек ``id`` ``SUPPORTED_EXPERIMENT_IDS``
    whitelist-інде болса ғана ``active_experiment_id``-ды жаңартады (қате/
    белгісіз id ЕШҚАШАН ескі мәнді "бос" етіп ауыстырмайды — firmware-дегі
    ``isSupportedExperiment()``/``copyExperimentId()`` жұбымен бірдей),
    әрдайым ``OK,EXP=<ағымдағы мән>``-ды қайтарады. ``measurement_line()``
    — ``sendMeasurement()``-пен бірдей: ағымдағы ``active_experiment_id``-ды
    пакетке тег ретінде қосады.

    **Ескерту:** бұл Python моделі firmware-дің ЛОГИКАСЫН (whitelist/
    boot-default семантикасын) дәл қайталайды, бірақ нақты hardware-де
    табылған root cause (ATmega328P heap фрагментациясынан Arduino
    ``String``-тің ұзын мәндерде silent түрде бос қалуы) Python-да ЕШҚАШАН
    қайталанбайды — Python жолдары AVR-стильді heap allocator қолданбайды.
    Сол нақты AVR-деңгейлі механизмнің дәлелі
    ``test_*_firmware_source.py``-дегі source-contract тесттерінде (String
    класы командалар парсингінде мүлде жоқ екенін растайтын), ал бұл
    файлдағы тесттер PC-жақтың ТОЛЫҚ pipeline-мен дұрыс жұмыс істейтінін
    растайды.
    """

    def __init__(self, value_key: str, boot_default: str = "") -> None:
        self.active_experiment_id = boot_default
        self._value_key = value_key  # "U" (voltage) немесе "I" (current)

    def handle_command(self, line: str) -> str | None:
        stripped = line.strip()
        if stripped.startswith("SET_EXP="):
            new_id = stripped[len("SET_EXP=") :].strip()
            if new_id in _SUPPORTED_EXPERIMENT_IDS:
                self.active_experiment_id = new_id
            return f"OK,EXP={self.active_experiment_id}"
        return None

    def measurement_line(self, value: float) -> str:
        return f"EXP={self.active_experiment_id},{self._value_key}={value}"


class FakeSerialThreadControllerWithFirmware(QObject):
    """``SerialThreadController``-дің public бетін қайталайтын double —
    ``write_line()`` шақырылғанда тіркелген ``FakeArduinoFirmware``
    объектісіне жіберіп, оның жауабын (бар болса) бірден ``line_received``
    арқылы "қайтарады" — нақты Arduino-ның SET_EXP->ACK round-trip-ін
    дәлірек модельдейді (қолмен ``_ack_both()`` шақырудың орнына).
    """

    connected = Signal(str)
    disconnected = Signal()
    line_received = Signal(str)
    error_occurred = Signal(str)
    state_changed = Signal(str)

    def __init__(self, firmware: FakeArduinoFirmware, drop_writes: bool = False) -> None:
        super().__init__()
        self.firmware = firmware
        self.drop_writes = drop_writes  # "SET_EXP жазуы физикалық жетпейді" симуляциясы
        self.write_calls: list[str] = []
        self.stop_calls = 0
        self._running = False

    def connect_port(self, port_name: str, baud_rate: int) -> None:
        self._running = True
        self.connected.emit(port_name)

    def disconnect_port(self) -> None:
        self._running = False

    def write_line(self, line: str) -> None:
        self.write_calls.append(line)
        if self.drop_writes:
            return  # write delivery ақауы симуляциясы — firmware ЕШТЕҢЕ алмайды
        response = self.firmware.handle_command(line)
        if response is not None:
            self.line_received.emit(response)

    def emit_measurement(self, value: float) -> None:
        self.line_received.emit(self.firmware.measurement_line(value))

    def is_running(self) -> bool:
        return self._running

    def stop(self) -> None:
        self.stop_calls += 1
        self._running = False


@pytest.fixture
def firmware_env(monkeypatch: pytest.MonkeyPatch):
    """COM6 -> Voltage firmware, COM11 -> Current firmware — екеуі де
    түзетілген (бос) boot default-пен.
    """
    firmwares = {
        "COM6": FakeArduinoFirmware(value_key="U"),
        "COM11": FakeArduinoFirmware(value_key="I"),
    }
    fakes_by_port: dict[str, FakeSerialThreadControllerWithFirmware] = {}
    construction_count = {"n": 0}

    def factory(*_args, **_kwargs):
        construction_count["n"] += 1
        # DeviceManager _create_managed_port() әр порт үшін БӨЛЕК шақырады,
        # бірақ port_name-ды осы жерде білмейміз — connect_port() алдында
        # placeholder жасап, порт аты белгілі болған кезде дұрыс firmware-ге
        # "матч" жасаймыз (пending pattern, test_device_persistence_
        # integration.py-дегімен бірдей идея).
        pending = _PendingFirmwareFake()
        return pending

    class _PendingFirmwareFake(FakeSerialThreadControllerWithFirmware):
        def __init__(self) -> None:
            super().__init__(firmware=None)

        def connect_port(self, port_name: str, baud_rate: int) -> None:
            self.firmware = firmwares[port_name]
            fakes_by_port[port_name] = self
            super().connect_port(port_name, baud_rate)

    monkeypatch.setattr(device_manager_module, "SerialThreadController", factory)
    return fakes_by_port, construction_count, firmwares


def _identify(page: ExperimentWorkspacePage, fakes, port_name: str, hello_line: str) -> None:
    page._device_panel.identify_requested.emit(port_name, 115200)
    fakes[port_name].line_received.emit(hello_line)


def test_full_five_experiment_switch_sequence_with_simulated_firmware(firmware_env) -> None:
    """Спецификация §12/§22-12: identify БІР рет, содан кейін 5 іске
    асырылған электр тәжірибесінің бәрі арасында (ohms-law ->
    current-voltage -> тізбектей -> параллель -> жұмыс/қуат -> ohms-law)
    қайта identify-сіз ауысу, әр қадамда SET_EXP дұрыс жіберіліп,
    симуляцияланған firmware дұрыс ACK беріп, дұрыс EXP-пен measurement
    жіберетінін тексереді.
    """
    fakes, construction_count, _firmwares = firmware_env
    device_manager = DeviceManager()
    page = ExperimentWorkspacePage(
        device_scanner=DeviceScanner(),
        device_manager=device_manager,
        active_student_repository=_make_seeded_active_student_repository(),
    )

    page.on_enter(_FULL_EXPERIMENT_SWITCH_SEQUENCE[0])
    _identify(page, fakes, "COM6", _VOLTAGE_HELLO)
    _identify(page, fakes, "COM11", _CURRENT_HELLO)
    voltage_fake, current_fake = fakes["COM6"], fakes["COM11"]

    for index, experiment in enumerate(_FULL_EXPERIMENT_SWITCH_SEQUENCE):
        if index > 0:
            page.on_enter(experiment)

        page._measurement_workspace._start_button.click()

        assert voltage_fake.write_calls[-1] == f"SET_EXP={experiment.id}"
        assert current_fake.write_calls[-1] == f"SET_EXP={experiment.id}"
        # Firmware моделі АВТОМАТТЫ дұрыс ACK қайтарды (write_line ішінде).
        assert page._experiment_controller.is_running() is True

        measurements: list[object] = []
        page._experiment_controller.measurement_ready.connect(measurements.append)
        voltage_fake.emit_measurement(5.0 + index)
        current_fake.emit_measurement(0.05 + index * 0.001)

        assert len(measurements) == 1
        assert measurements[0].experiment_id == experiment.id

        page._measurement_workspace._stop_button.click()
        page._on_back_clicked()

    # Ешбір жаңа SerialThreadController жасалмаған (тек 2 порт — Voltage/
    # Current), яғни ЕШБІР қайта identify/reconnect болмаған. DeviceManager
    # сол бір данасы бүкіл тізбек бойы қолданылды (жаңа объект жоқ).
    assert construction_count["n"] == 2
    assert voltage_fake.stop_calls == 0
    assert current_fake.stop_calls == 0
    assert page._device_manager is device_manager


def test_neutral_boot_default_produces_invalid_packet_before_first_set_exp() -> None:
    """Бос boot default (bug fix) — SET_EXP әлі жіберілмеген firmware
    пакеті PacketParser бойынша ӘРҚАШАН invalid ("EXP мәні бос"),
    сондықтан ешқашан кездейсоқ "дұрыс" деп қабылданбайды.
    """
    firmware = FakeArduinoFirmware(value_key="U")  # boot_default="" әдепкі

    line = firmware.measurement_line(5.0)  # "EXP=,U=5.0"
    result = PacketParser().parse_line(line)

    assert result.is_valid is False
    assert any("EXP" in error for error in result.errors)


def test_stuck_old_style_default_reproduces_real_hardware_symptom(firmware_env) -> None:
    """Root cause дәлелдеуі (нақты hardware-де байқалған дәл симптом):
    бір порттың SET_EXP жазуы физикалық жетпесе (write delivery ақауы
    немесе ескі firmware SET_EXP-ті танымайды), ол порт ЕСКІ-стиль
    хардкодталған "ohms-law" default-те мәңгі ілініп қалады.

    Бұл ACK-gating арқасында "running=True болып, бірақ бұрыс деректі
    көрсету" секілді нашарырақ ақауды ТУДЫРМАЙДЫ (Current-тен ACK
    ешқашан келмейді — coordinator "starting" күйінде қалады, кейін
    timeout), бірақ дәл КӨРСЕТІЛГЕН симптомды толық қайталайды:
    Voltage сенсорынан "OK,EXP=ohms-law" ACK келгенімен, Current
    сенсорынан ешбір ACK келмейді → measurement ешқашан шықпайды,
    ал Arduino үздіксіз ағыны (протокол бойынша Start-қа тәуелсіз)
    "EXP mismatch" ескертуін қайта-қайта тудырады — дәл пайдаланушы
    хабарлаған "readouts remain '—', EXP mismatch warning" суреті.
    """
    fakes, _construction_count, firmwares = firmware_env
    # Current Sensor-дың ЕСКІ (bug) boot default-ын қолдан модельдейміз —
    # СОНЫМЕН ҚАТАР сол порттың SET_EXP жазуын "жетпейтіндей" етеміз
    # (нақты silent write-delivery/ескі firmware ақауының моделі).
    firmwares["COM11"] = FakeArduinoFirmware(value_key="I", boot_default="ohms-law")

    device_manager = DeviceManager()
    page = ExperimentWorkspacePage(
        device_scanner=DeviceScanner(),
        device_manager=device_manager,
        active_student_repository=_make_seeded_active_student_repository(),
    )

    page.on_enter(OHMS_LAW_EXPERIMENT)
    _identify(page, fakes, "COM6", _VOLTAGE_HELLO)
    _identify(page, fakes, "COM11", _CURRENT_HELLO)
    voltage_fake, current_fake = fakes["COM6"], fakes["COM11"]
    current_fake.drop_writes = True  # SET_EXP жазуы бұл портқа ЕШҚАШАН жетпейді

    page._measurement_workspace._start_button.click()

    # Voltage ACK берді (write дропталмаған), бірақ Current-тен ЕШБІР ACK
    # келмейді — ACK-gating дұрыс жұмыс істеп, "starting" күйінде қалады
    # (running=True ЕШҚАШАН болмайды, тіпті ескі default кездейсоқ сәйкес
    # келсе де).
    assert page._experiment_controller.is_starting() is True
    assert page._experiment_controller.is_running() is False

    # Arduino (нақты hardware-дегідей) Start-қа тәуелсіз үздіксіз ағын
    # жібере береді — Current сенсорының ескі "ohms-law" тегі осы кезде
    # де EXP mismatch ескертуін ЕМЕС (себебі running=False, "starting"
    # тексерісі бірінші), ал validation ешқашан running-ге жетпейді:
    measurements: list[object] = []
    page._experiment_controller.measurement_ready.connect(measurements.append)
    voltage_fake.emit_measurement(5.0)
    current_fake.emit_measurement(0.05)

    assert measurements == []


# ---- kезeng 27: REAL HARDWARE SET_EXP PARSER BUG regression tests ---------
#
# Нақты hardware-де (Serial Monitor арқылы қолмен) табылған симптом: қысқа
# "ohms-law" (8 таңба) сәтті ACK алады, бірақ ұзынырақ id-лер
# ("series-connection", "current-voltage" т.б.) "OK,EXP=" (бос) қайтаратын.
# Осы төмендегі тесттер PC-жақ pipeline-де БАРЛЫҚ 5 іске асырылған id үшін
# дұрыс SET_EXP->ACK->measurement-tag тізбегін, әрі "ешбір валидті SET_EXP
# ешқашан бос ACK бермейді" деген инвариантты растайды.

_ALL_FIVE_EXPERIMENT_IDS = (
    "current-voltage",
    "series-connection",
    "parallel-connection",
    "current-work-power",
    "ohms-law",
)


@pytest.mark.parametrize("experiment_id", _ALL_FIVE_EXPERIMENT_IDS)
def test_each_implemented_id_acks_with_matching_id_not_empty(experiment_id: str) -> None:
    """Регрессия: `SET_EXP=<id>` -> `OK,EXP=<дәл сол id>` барлық 5
    іске асырылған id үшін, ұзындығына қарамастан (bug fix-тен КЕЙІН).
    """
    firmware = FakeArduinoFirmware(value_key="U")

    response = firmware.handle_command(f"SET_EXP={experiment_id}")

    assert response == f"OK,EXP={experiment_id}"
    assert response != "OK,EXP="
    assert firmware.active_experiment_id == experiment_id
    assert firmware.active_experiment_id != ""


@pytest.mark.parametrize("experiment_id", _ALL_FIVE_EXPERIMENT_IDS)
def test_measurement_after_set_exp_carries_the_same_id(experiment_id: str) -> None:
    """Спецификацияның нақты талабы: SET_EXP ACK-тен КЕЙІНГІ measurement
    пакеті ДӘЛ сол EXP тегін алып жүруі керек — қысқа/ұзын id-ге
    тәуелсіз."""
    firmware = FakeArduinoFirmware(value_key="I")

    firmware.handle_command(f"SET_EXP={experiment_id}")
    measurement = firmware.measurement_line(1.23)

    assert measurement == f"EXP={experiment_id},I=1.23"
    parsed = PacketParser().parse_line(measurement)
    assert parsed.is_valid is True
    assert parsed.experiment_id == experiment_id


def test_no_valid_set_exp_ever_produces_empty_ack() -> None:
    """Спецификацияның нақты тыйымы: 'Never ACK: OK,EXP= for a failed
    parse' — барлық 5 id тізбектей жіберілгенде ешқайсысы бос ACK
    бермеуі керек (ұзындық/парсинг ақауы жоқ)."""
    firmware = FakeArduinoFirmware(value_key="U")

    responses = [firmware.handle_command(f"SET_EXP={exp_id}") for exp_id in _ALL_FIVE_EXPERIMENT_IDS]

    assert "OK,EXP=" not in responses
    for exp_id, response in zip(_ALL_FIVE_EXPERIMENT_IDS, responses):
        assert response == f"OK,EXP={exp_id}"


def test_unsupported_experiment_id_does_not_overwrite_active_experiment() -> None:
    """Спецификацияның нақты талабы: белгісіз/support етілмейтін id келсе,
    ``activeExperiment`` ӨЗГЕРМЕУІ керек (ешқашан оны бос/қате мәнге
    ауыстырмау) — тек whitelist-тегі 5 id ғана қабылданады."""
    firmware = FakeArduinoFirmware(value_key="U")
    firmware.handle_command("SET_EXP=ohms-law")

    response = firmware.handle_command("SET_EXP=circuit-current-measurement")

    # circuit-current-measurement — is_implemented=False (әлі жоспарлы),
    # whitelist-те жоқ, сондықтан ескі "ohms-law" САҚТАЛАДЫ.
    assert response == "OK,EXP=ohms-law"
    assert firmware.active_experiment_id == "ohms-law"
