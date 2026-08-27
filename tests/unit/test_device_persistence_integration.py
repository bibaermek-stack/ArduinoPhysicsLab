"""Persistent Sensor Connection Architecture — ЕҢ МАҢЫЗДЫ integration тест
(тапсырма спецификациясының 14-бөлімі).

Нақты ``ExperimentWorkspacePage`` + нақты ``MultiSensorExperimentCoordinator``
+ нақты ``DeviceManager`` бір fake serial транспортымен (``SerialThreadController``
monkeypatch) толық "Voltage/Current бір рет identify → ohms-law → Start/
Stop → Артқа → current-voltage → ЕШБІР қайта identify → Start → ohms-law-ға
қайта ору" сценарийін тексереді — дәл осы сценарий бұрын (persistent
connection архитектурасына дейін) сенсорларды "жоғалтатын" bug еді.
"""

import sys

import pytest
from PySide6.QtCore import QCoreApplication, QObject, Signal

import infrastructure.serial_comm.device_manager as device_manager_module
from domain.entities.active_student_context import ActiveStudentContext
from infrastructure.serial_comm.device_manager import DeviceManager
from infrastructure.serial_comm.device_scanner import DeviceScanner
from infrastructure.storage.sqlite_active_student_repository import SqliteActiveStudentRepository
from modules.electricity.experiments_config import (
    CURRENT_VOLTAGE_EXPERIMENT,
    ELECTRICITY_EXPERIMENTS,
    OHMS_LAW_EXPERIMENT,
)
from ui.pages.experiment_workspace_page import ExperimentWorkspacePage

# Phase 39B: бұл файлдағы тестер device/session persistence-ті тексереді,
# белсенді оқушы гейтіне қатысы жоқ — сондықтан алдын ала таңдалған "тест
# оқушысы" гейтті айналып өтеді (§ "existing assertions should not need
# to change").
def _make_seeded_active_student_repository() -> SqliteActiveStudentRepository:
    repository = SqliteActiveStudentRepository()
    repository.set(ActiveStudentContext(classroom_id="test-classroom", student_id="test-student"))
    return repository

_VOLTAGE_HELLO = "TYPE=HELLO,DEV=APL-VOLTAGE-01,MODEL=V1,SENSOR=VOLTAGE,CHIP=INA226,FW=1.0"
_CURRENT_HELLO = "TYPE=HELLO,DEV=APL-CURRENT-01,MODEL=V1,SENSOR=CURRENT,CHIP=INA226,FW=1.0"
# Phase 38B: metal-resistance-temperature (№8) қосымша TEMPERATURE
# сенсорын талап етеді — нақты firmware жоқ, бірақ HELLO хаттамасы
# кез келген SENSOR= мәнін генерик түрде қабылдайды, сондықтан бұл fake
# сол хаттаманы дәл солай эмуляциялайды.
_TEMPERATURE_HELLO = "TYPE=HELLO,DEV=APL-TEMPERATURE-01,MODEL=V1,SENSOR=TEMPERATURE,FW=1.0"


@pytest.fixture(scope="module", autouse=True)
def qt_application() -> QCoreApplication:
    """QWidget/Signal механизмдері үшін жалғыз QApplication дана."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


class FakeSerialThreadController(QObject):
    """SerialThreadController-дің public бетін қайталайтын, нақты
    Serial-мен жұмыс істемейтін тест double. ``stop_calls`` — "порт
    жабылды ма" деген негізгі кепілдікті тексеру үшін.
    """

    connected = Signal(str)
    disconnected = Signal()
    line_received = Signal(str)
    error_occurred = Signal(str)
    state_changed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
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

    def is_running(self) -> bool:
        return self._running

    def stop(self) -> None:
        self.stop_calls += 1
        self._running = False


@pytest.fixture
def fake_serial_env(monkeypatch: pytest.MonkeyPatch):
    """``DeviceManager`` ішінде жасалатын әр ``SerialThreadController()``-ды
    fake-пен ауыстырады. ``fakes_by_port``/``construction_count`` арқылы
    "жаңа port қайта ашылмады ма" деген негізгі кепілдіктерді тексеруге
    болады.
    """
    fakes_by_port: dict[str, FakeSerialThreadController] = {}
    construction_count = {"n": 0}

    class _PendingFake(FakeSerialThreadController):
        def connect_port(self, port_name: str, baud_rate: int) -> None:
            fakes_by_port[port_name] = self
            super().connect_port(port_name, baud_rate)

    def factory(*_args, **_kwargs):
        construction_count["n"] += 1
        return _PendingFake()

    monkeypatch.setattr(device_manager_module, "SerialThreadController", factory)
    return fakes_by_port, construction_count


def _identify(page: ExperimentWorkspacePage, fakes, port_name: str, hello_line: str) -> None:
    page._device_panel.identify_requested.emit(port_name, 115200)
    fakes[port_name].line_received.emit(hello_line)


def _ack_both(fakes, experiment_id: str) -> None:
    fakes["COM6"].line_received.emit(f"OK,EXP={experiment_id}")
    fakes["COM11"].line_received.emit(f"OK,EXP={experiment_id}")


def test_full_persistence_lifecycle_across_experiment_switches(fake_serial_env) -> None:
    fakes, construction_count = fake_serial_env
    device_manager = DeviceManager()
    page = ExperimentWorkspacePage(
        device_scanner=DeviceScanner(),
        device_manager=device_manager,
        active_student_repository=_make_seeded_active_student_repository(),
    )

    # ---- 1. ohms-law ашып, екі сенсорды бір рет Identify ету ----------
    page.on_enter(OHMS_LAW_EXPERIMENT)
    _identify(page, fakes, "COM6", _VOLTAGE_HELLO)
    _identify(page, fakes, "COM11", _CURRENT_HELLO)

    assert page._experiment_controller.is_ready() is True
    assert "COM6" in page._device_panel._cards_by_port
    assert "COM11" in page._device_panel._cards_by_port
    voltage_fake, current_fake = fakes["COM6"], fakes["COM11"]
    assert construction_count["n"] == 2  # тек 2 порт — Voltage/Current

    # ---- 2. Start/Stop — порттар ашық қалуы тиіс -----------------------
    page._measurement_workspace._start_button.click()
    _ack_both(fakes, OHMS_LAW_EXPERIMENT.id)
    assert page._experiment_controller.is_running() is True

    page._measurement_workspace._stop_button.click()
    assert voltage_fake.stop_calls == 0
    assert current_fake.stop_calls == 0

    # ---- 3. "Артқа" — портты ЖАППАУЫ тиіс -------------------------------
    page._on_back_clicked()
    assert voltage_fake.stop_calls == 0
    assert current_fake.stop_calls == 0
    assert device_manager.is_port_connected("COM6") is True
    assert device_manager.is_port_connected("COM11") is True

    # ---- 4. current-voltage-ге ауысу — ЕШБІР қайта Identify қажет ЕМЕС -
    page.on_enter(CURRENT_VOLTAGE_EXPERIMENT)

    assert construction_count["n"] == 2  # жаңа SerialThreadController жасалмады
    assert page._experiment_controller.is_ready() is True
    assert "COM6" in page._device_panel._cards_by_port
    assert "COM11" in page._device_panel._cards_by_port
    assert page._measurement_workspace._start_button.isEnabled() is True

    # ---- 5. SET_EXP жаңа id-мен жіберіледі, дәл сол fake serial-ға -----
    page._measurement_workspace._start_button.click()
    assert voltage_fake.write_calls[-1] == f"SET_EXP={CURRENT_VOLTAGE_EXPERIMENT.id}"
    assert current_fake.write_calls[-1] == f"SET_EXP={CURRENT_VOLTAGE_EXPERIMENT.id}"
    _ack_both(fakes, CURRENT_VOLTAGE_EXPERIMENT.id)
    assert page._experiment_controller.is_running() is True

    voltage_fake.line_received.emit(f"EXP={CURRENT_VOLTAGE_EXPERIMENT.id},U=4.820")
    current_fake.line_received.emit(f"EXP={CURRENT_VOLTAGE_EXPERIMENT.id},I=0.047")

    assert page._measurement_workspace._value_labels["voltage"].text() == "4.820 V"
    assert page._measurement_workspace._measurement_table._model.rowCount() == 1

    page._measurement_workspace._stop_button.click()

    # ---- 6. ohms-law-ға қайта ору — дереу дайын, дубликат порт жоқ -----
    page.on_enter(OHMS_LAW_EXPERIMENT)

    assert construction_count["n"] == 2  # порттар әлі де сол 2-ақ
    assert page._experiment_controller.is_ready() is True
    assert page._measurement_workspace._start_button.isEnabled() is True
    assert voltage_fake.stop_calls == 0
    assert current_fake.stop_calls == 0


def test_stale_packet_before_ack_is_rejected_after_switch(fake_serial_env) -> None:
    """current-voltage-ге ауысып Start басқаннан кейін, ACK келгенше
    ескі (Ohm's Law) EXP-тегі пакет келсе — қабылданбауы, running=False
    күйінде қалуы және measurement_ready шықпауы тиіс.
    """
    fakes, _construction_count = fake_serial_env
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

    page._measurement_workspace._start_button.click()
    _ack_both(fakes, OHMS_LAW_EXPERIMENT.id)
    page._measurement_workspace._stop_button.click()
    page._on_back_clicked()

    page.on_enter(CURRENT_VOLTAGE_EXPERIMENT)
    coordinator = page._experiment_controller
    warnings: list[str] = []
    measurements: list[object] = []
    coordinator.warning_occurred.connect(warnings.append)
    coordinator.measurement_ready.connect(measurements.append)

    page._measurement_workspace._start_button.click()
    assert voltage_fake.write_calls[-1] == f"SET_EXP={CURRENT_VOLTAGE_EXPERIMENT.id}"

    # ACK әлі келген жоқ — осы кезде ескі EXP-тегі "stale" пакет келеді.
    voltage_fake.line_received.emit(f"EXP={OHMS_LAW_EXPERIMENT.id},U=5.000")

    # Phase 34.1 §2: EXP-сәйкессіздігі — протокол диагностикасы, ЕНДІ
    # студент UI-ге (warning_occurred арқылы) шықпайды, тек debug-логта
    # (APL_DEBUG_SERIAL=1). Пакет өзі ӘЛІ ДЕ толық тасталады — validation
    # ӨЗГЕРІССІЗ (running=False, measurement жасалмайды).
    assert coordinator.is_running() is False
    assert measurements == []
    assert warnings == []

    _ack_both(fakes, CURRENT_VOLTAGE_EXPERIMENT.id)
    assert coordinator.is_running() is True

    voltage_fake.line_received.emit(f"EXP={CURRENT_VOLTAGE_EXPERIMENT.id},U=4.820")
    current_fake.line_received.emit(f"EXP={CURRENT_VOLTAGE_EXPERIMENT.id},I=0.047")

    assert len(measurements) == 1


def test_full_round_trip_ohm_currentvoltage_ohm_resyncs_set_exp(fake_serial_env) -> None:
    """Спецификацияның 10-бөлімі: OHM -> CURRENT-VOLTAGE -> OHM, ешбір
    қайта identify/reconnect жасалмай, әр Start дәл сол persistent
    COM6/COM11 fake-ке ӨЗ SET_EXP=<id>-ін жіберетінін тексереді.
    """
    fakes, construction_count = fake_serial_env
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

    page._measurement_workspace._start_button.click()
    assert voltage_fake.write_calls[-1] == f"SET_EXP={OHMS_LAW_EXPERIMENT.id}"
    assert current_fake.write_calls[-1] == f"SET_EXP={OHMS_LAW_EXPERIMENT.id}"
    _ack_both(fakes, OHMS_LAW_EXPERIMENT.id)
    assert page._experiment_controller.is_running() is True
    page._measurement_workspace._stop_button.click()
    page._on_back_clicked()

    page.on_enter(CURRENT_VOLTAGE_EXPERIMENT)
    page._measurement_workspace._start_button.click()
    assert voltage_fake.write_calls[-1] == f"SET_EXP={CURRENT_VOLTAGE_EXPERIMENT.id}"
    assert current_fake.write_calls[-1] == f"SET_EXP={CURRENT_VOLTAGE_EXPERIMENT.id}"
    _ack_both(fakes, CURRENT_VOLTAGE_EXPERIMENT.id)
    assert page._experiment_controller.is_running() is True
    page._measurement_workspace._stop_button.click()
    page._on_back_clicked()

    # ---- ohms-law-ға ҮШІНШІ рет ору — SET_EXP қайта "ohms-law" болып ---
    # ЕШБІР жаңа SerialThreadController/re-identify болмауы тиіс.
    page.on_enter(OHMS_LAW_EXPERIMENT)
    assert construction_count["n"] == 2
    coordinator = page._experiment_controller
    measurements: list[object] = []
    coordinator.measurement_ready.connect(measurements.append)

    page._measurement_workspace._start_button.click()
    assert voltage_fake.write_calls[-1] == f"SET_EXP={OHMS_LAW_EXPERIMENT.id}"
    assert current_fake.write_calls[-1] == f"SET_EXP={OHMS_LAW_EXPERIMENT.id}"
    _ack_both(fakes, OHMS_LAW_EXPERIMENT.id)
    assert coordinator.is_running() is True

    voltage_fake.line_received.emit(f"EXP={OHMS_LAW_EXPERIMENT.id},U=3.300")
    current_fake.line_received.emit(f"EXP={OHMS_LAW_EXPERIMENT.id},I=0.150")

    assert len(measurements) == 1
    assert voltage_fake.stop_calls == 0
    assert current_fake.stop_calls == 0


_IMPLEMENTED_ELECTRICITY_EXPERIMENTS = tuple(
    e for e in ELECTRICITY_EXPERIMENTS if e.is_implemented
)


@pytest.mark.parametrize(
    "experiment", _IMPLEMENTED_ELECTRICITY_EXPERIMENTS, ids=lambda e: e.id
)
def test_start_sends_each_experiments_own_set_exp_id(fake_serial_env, experiment) -> None:
    """Спецификацияның 11-бөлімі: барлық НАҚТЫ ІСКЕ АСЫРЫЛҒАН электр
    тәжірибесі SET_EXP ретінде дәл ӨЗ ``ExperimentDefinition.id``-ін
    жібереді (тек current-voltage үшін ғана хардкодталмаған). Каталог-қана
    (is_implemented=False) жазба бұл тестке қатыспайды — ол ешқашан
    MultiSensorExperimentCoordinator арқылы Start/SET_EXP ағынын жүргізбейді.
    """
    fakes, _construction_count = fake_serial_env
    device_manager = DeviceManager()
    page = ExperimentWorkspacePage(
        device_scanner=DeviceScanner(),
        device_manager=device_manager,
        active_student_repository=_make_seeded_active_student_repository(),
    )

    page.on_enter(experiment)
    _identify(page, fakes, "COM6", _VOLTAGE_HELLO)
    _identify(page, fakes, "COM11", _CURRENT_HELLO)
    if "TEMPERATURE" in experiment.required_sensor_types:
        _identify(page, fakes, "COM12", _TEMPERATURE_HELLO)

    page._measurement_workspace._start_button.click()

    assert fakes["COM6"].write_calls[-1] == f"SET_EXP={experiment.id}"
    assert fakes["COM11"].write_calls[-1] == f"SET_EXP={experiment.id}"
    if "TEMPERATURE" in experiment.required_sensor_types:
        assert fakes["COM12"].write_calls[-1] == f"SET_EXP={experiment.id}"


def test_application_shutdown_closes_all_ports(fake_serial_env) -> None:
    fakes, _construction_count = fake_serial_env
    device_manager = DeviceManager()
    page = ExperimentWorkspacePage(
        device_scanner=DeviceScanner(),
        device_manager=device_manager,
        active_student_repository=_make_seeded_active_student_repository(),
    )
    page.on_enter(OHMS_LAW_EXPERIMENT)
    _identify(page, fakes, "COM6", _VOLTAGE_HELLO)
    _identify(page, fakes, "COM11", _CURRENT_HELLO)

    device_manager.shutdown_all()

    assert fakes["COM6"].stop_calls == 1
    assert fakes["COM11"].stop_calls == 1
