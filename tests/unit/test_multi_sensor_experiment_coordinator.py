"""MultiSensorExperimentCoordinator үшін юнит-тесттер: ``DeviceManager``-ге
persistent connection-ды толығымен жүктеп, координатор ЕШБІР serial порт
иеленбейтінін (тек ``DeviceManager`` сигналдарына жазылатынын) растайды.

Voltage Sensor + Current Sensor екі бөлек fake порты Ohm's Law сценарийімен
тексеріледі.
"""

import sys
from datetime import datetime, timezone

import pytest
from PySide6.QtCore import QCoreApplication, QObject, Signal

import modules.electricity.multi_sensor_experiment_coordinator as coordinator_module
from domain.entities.connected_device import ConnectedDevice
from domain.entities.measurement import Measurement
from modules.electricity.experiments_config import (
    CURRENT_WORK_POWER_EXPERIMENT,
    OHMS_LAW_EXPERIMENT,
)
from modules.electricity.multi_sensor_experiment_coordinator import (
    MultiSensorExperimentCoordinator,
)


@pytest.fixture(scope="module", autouse=True)
def qt_application() -> QCoreApplication:
    """QObject/Signal механизмдері үшін жалғыз QCoreApplication дана."""
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication(sys.argv)
    return app


class FakeDeviceManager(QObject):
    """``DeviceManager``-дің public сигнал/әдіс бетін қайталайтын тест
    double. Нақты serial/QThread ешбір қатысы жоқ — координатордың
    ``DeviceManager``-ге тек СҰРАУ жіберетінін (порт ашу/жабуды өзі
    жасамайтынын) растау үшін жеткілікті.
    """

    device_identified = Signal(object)
    device_identification_failed = Signal(str)
    handshake_timeout = Signal(str)
    port_disconnected = Signal(str)
    port_error = Signal(str, str)
    line_received = Signal(str, str)

    def __init__(self) -> None:
        super().__init__()
        self.identify_calls: list[tuple[str, int]] = []
        self.write_calls: dict[str, list[str]] = {}
        self._connected_by_sensor_type: dict[str, ConnectedDevice] = {}

    def identify(self, port_name: str, baud_rate: int = 115200) -> None:
        self.identify_calls.append((port_name, baud_rate))

    def get_connected_device(self, sensor_type: str) -> ConnectedDevice | None:
        return self._connected_by_sensor_type.get(sensor_type.upper())

    def write_to_port(self, port_name: str, line: str) -> None:
        self.write_calls.setdefault(port_name, []).append(line)

    # ---- тест-хелперлер (нақты DeviceManager API-ы емес, симуляция) ------

    def simulate_identified(self, port_name: str, device: ConnectedDevice) -> None:
        self._connected_by_sensor_type[device.sensor_type.upper()] = device
        self.device_identified.emit(device)

    def simulate_line(self, port_name: str, line: str) -> None:
        self.line_received.emit(port_name, line)

    def simulate_port_disconnected(self, port_name: str, sensor_type: str) -> None:
        self._connected_by_sensor_type.pop(sensor_type.upper(), None)
        self.port_disconnected.emit(port_name)


def _make_voltage_device(port_name: str = "COM3") -> ConnectedDevice:
    return ConnectedDevice(
        device_id="APL-VOLTAGE-01",
        model="V1",
        sensor_type="VOLTAGE",
        firmware_version="1.0",
        chip="INA226",
        serial_number=None,
        hardware_version=None,
        port_name=port_name,
        connected_at=datetime.now(timezone.utc),
        warnings=(),
    )


def _make_current_device(port_name: str = "COM4") -> ConnectedDevice:
    return ConnectedDevice(
        device_id="APL-CURRENT-01",
        model="V1",
        sensor_type="CURRENT",
        firmware_version="1.0",
        chip="INA226",
        serial_number=None,
        hardware_version=None,
        port_name=port_name,
        connected_at=datetime.now(timezone.utc),
        warnings=(),
    )


def _make_energy_device(port_name: str = "COM5") -> ConnectedDevice:
    return ConnectedDevice(
        device_id="APL-ENERGY-01",
        model="V1",
        sensor_type="ENERGY",
        firmware_version="1.0",
        chip="INA226",
        serial_number=None,
        hardware_version=None,
        port_name=port_name,
        connected_at=datetime.now(timezone.utc),
        warnings=(),
    )


def _make_coordinator() -> tuple[MultiSensorExperimentCoordinator, FakeDeviceManager]:
    device_manager = FakeDeviceManager()
    coordinator = MultiSensorExperimentCoordinator(
        definition=OHMS_LAW_EXPERIMENT, device_manager=device_manager
    )
    return coordinator, device_manager


def _identify(coordinator, device_manager, port_name, device) -> None:
    coordinator.identify_device(port_name, 115200)
    device_manager.simulate_identified(port_name, device)


def _ack(device_manager, port_name, experiment_id="ohms-law") -> None:
    """Fake Arduino-ның ``SET_EXP`` сұрауына сәйкес ``OK,EXP=<id>``
    растауын жібереді (ACK-gated start-ты тестілеу үшін)."""
    device_manager.simulate_line(port_name, f"OK,EXP={experiment_id}")


def _start_and_ack_both(coordinator, device_manager, experiment_id="ohms-law") -> None:
    """Start сұрап, екі порттан да сәйкес ACK келтіріп, ``running=True``
    болғанша жеткізетін ортақ хелпер (көптеген тестте ACK-gating
    механизмі назар нүктесі емес, тек Start-тан кейінгі жағдайды
    тексеру үшін қолданылады)."""
    coordinator.start_experiment()
    _ack(device_manager, "COM3", experiment_id)
    _ack(device_manager, "COM4", experiment_id)


def _wait_until(predicate, timeout_ms: int, step_ms: int = 5) -> bool:
    """``predicate()`` ақиқат болғанша (немесе ``timeout_ms`` таусылғанша)
    event loop-ты қысқа қадамдармен айналдырады. Бір рет фиксирленген
    ``QTest.qWait(N)``-нен айырмашылығы: system жүктемесі жоғары болса да
    (мыс. толық pytest suite астында) артық күтпей, шарт орындалысымен
    бірден қайтарады — сонымен қатар CI жүктемесіне төзімді болу үшін
    жоғарғы шекті (``timeout_ms``) кең қоюға болады."""
    from PySide6.QtTest import QTest

    elapsed = 0
    while not predicate() and elapsed < timeout_ms:
        QTest.qWait(step_ms)
        elapsed += step_ms
    return predicate()


def test_two_ports_identify_independently() -> None:
    coordinator, device_manager = _make_coordinator()
    identified: list[object] = []
    coordinator.device_identified.connect(identified.append)

    _identify(coordinator, device_manager, "COM3", _make_voltage_device())
    _identify(coordinator, device_manager, "COM4", _make_current_device())

    assert len(identified) == 2
    assert {d.sensor_type for d in identified} == {"VOLTAGE", "CURRENT"}


def test_is_ready_only_after_both_sensor_types_identified() -> None:
    coordinator, device_manager = _make_coordinator()

    assert coordinator.is_ready() is False

    _identify(coordinator, device_manager, "COM3", _make_voltage_device())
    assert coordinator.is_ready() is False
    assert coordinator.missing_sensor_types() == ("CURRENT",)

    _identify(coordinator, device_manager, "COM4", _make_current_device())
    assert coordinator.is_ready() is True
    assert coordinator.missing_sensor_types() == ()


def test_readiness_changed_emitted_on_each_identification() -> None:
    coordinator, device_manager = _make_coordinator()
    readiness_events: list[dict] = []
    coordinator.readiness_changed.connect(readiness_events.append)

    _identify(coordinator, device_manager, "COM3", _make_voltage_device())

    assert readiness_events[-1] == {"VOLTAGE": True, "CURRENT": False}

    _identify(coordinator, device_manager, "COM4", _make_current_device())

    assert readiness_events[-1] == {"VOLTAGE": True, "CURRENT": True}


def test_start_not_ready_does_nothing() -> None:
    coordinator, device_manager = _make_coordinator()
    warnings: list[str] = []
    coordinator.warning_occurred.connect(warnings.append)

    coordinator.start_experiment()

    assert coordinator.is_running() is False
    assert warnings


def test_real_actionable_warning_still_reaches_ui_unlike_protocol_diagnostics() -> None:
    """Phase 34.1 §2: тек протокол/пакет-роутинг диагностикасы
    (EXP/ACK сәйкессіздігі) жасырылды — нақты студентке ӘРЕКЕТ ЕТУГЕ
    болатын ескертулер (мыс. "барлық сенсор әлі анықталған жоқ")
    ӘЛІ ДЕ ``warning_occurred`` арқылы workspace статусына жетеді.
    """
    coordinator, device_manager = _make_coordinator()
    warnings: list[str] = []
    coordinator.warning_occurred.connect(warnings.append)

    coordinator.start_experiment()  # ешбір сенсор identify етілмеген

    assert any("сенсор" in w for w in warnings)


def test_start_sends_set_exp_to_both_ports() -> None:
    coordinator, device_manager = _make_coordinator()
    _identify(coordinator, device_manager, "COM3", _make_voltage_device())
    _identify(coordinator, device_manager, "COM4", _make_current_device())

    coordinator.start_experiment()

    assert device_manager.write_calls["COM3"] == ["SET_EXP=ohms-law"]
    assert device_manager.write_calls["COM4"] == ["SET_EXP=ohms-law"]
    # ACK-gated: екі порттан да ACK келгенше running әлі False.
    assert coordinator.is_running() is False
    assert coordinator.is_starting() is True

    _ack(device_manager, "COM3")
    assert coordinator.is_running() is False  # COM4 әлі ACK бермеген

    _ack(device_manager, "COM4")
    assert coordinator.is_running() is True
    assert coordinator.is_starting() is False


def test_partial_packet_from_single_port_does_not_create_measurement() -> None:
    coordinator, device_manager = _make_coordinator()
    _identify(coordinator, device_manager, "COM3", _make_voltage_device())
    _identify(coordinator, device_manager, "COM4", _make_current_device())
    _start_and_ack_both(coordinator, device_manager)
    received: list[Measurement] = []
    coordinator.measurement_ready.connect(received.append)

    device_manager.simulate_line("COM3", "EXP=ohms-law,U=5.024")

    assert received == []
    assert coordinator.session.measurement_count == 0


def test_combined_packets_from_both_ports_create_measurement_with_resistance() -> None:
    coordinator, device_manager = _make_coordinator()
    _identify(coordinator, device_manager, "COM3", _make_voltage_device())
    _identify(coordinator, device_manager, "COM4", _make_current_device())
    _start_and_ack_both(coordinator, device_manager)
    received: list[Measurement] = []
    coordinator.measurement_ready.connect(received.append)

    device_manager.simulate_line("COM3", "EXP=ohms-law,U=5.024")
    device_manager.simulate_line("COM4", "EXP=ohms-law,I=0.218")

    assert len(received) == 1
    measurement = received[0]
    assert measurement.values == {"voltage": 5.024, "current": 0.218}
    assert measurement.derived_values["resistance"] == pytest.approx(23.046, rel=1e-3)
    assert coordinator.session.measurement_count == 1


def test_exp_mismatch_on_one_port_does_not_affect_other_port() -> None:
    """Phase 34.1 §2: EXP-сәйкессіздігі — протокол/пакет-роутинг
    диагностикасы, студент интерфейсіне ЕШҚАШАН шықпайды (тек debug-
    логта, ``warning_occurred`` арқылы ЕМЕС). Пакет өзі әлі де толық
    ЕЛЕНБЕЙДІ/тасталады — тек көрінетін ескерту алынып тасталды.
    """
    coordinator, device_manager = _make_coordinator()
    _identify(coordinator, device_manager, "COM3", _make_voltage_device())
    _identify(coordinator, device_manager, "COM4", _make_current_device())
    _start_and_ack_both(coordinator, device_manager)
    warnings: list[str] = []
    received: list[Measurement] = []
    coordinator.warning_occurred.connect(warnings.append)
    coordinator.measurement_ready.connect(received.append)

    device_manager.simulate_line("COM3", "EXP=current-voltage,U=5.024")  # басқа тәжірибе
    device_manager.simulate_line("COM4", "EXP=ohms-law,I=0.218")

    assert received == []  # пакет ӘЛІ ДЕ тасталады (validation ӨЗГЕРІССІЗ)
    assert warnings == []  # бірақ ЕНДІ студент UI-ге көрінбейді


def test_wrong_sensor_type_for_role_emits_warning_and_not_counted() -> None:
    coordinator, device_manager = _make_coordinator()
    warnings: list[str] = []
    coordinator.warning_occurred.connect(warnings.append)

    # COM5 порты күтпеген ENERGY сенсорын identify етеді.
    coordinator.identify_device("COM5", 115200)
    device_manager.simulate_identified("COM5", _make_energy_device())

    assert coordinator.is_ready() is False
    assert any("ENERGY" in w for w in warnings)


def test_set_exp_ack_mismatch_is_not_exposed_as_warning_but_port_not_acked() -> None:
    """Phase 34.1 §2: ескі/басқа тәжірибенің ACK-і — протокол
    диагностикасы, студент UI-ге ЕШҚАШАН шықпайды (тек debug-логта).
    Бірақ порт "starting" растауы ретінде ЕСЕПТЕЛМЕЙДІ (ниет
    ӨЗГЕРІССІЗ) — сәйкессіз ACK ешқашан толық Start-қа әкелмейді.
    """
    coordinator, device_manager = _make_coordinator()
    _identify(coordinator, device_manager, "COM3", _make_voltage_device())
    _identify(coordinator, device_manager, "COM4", _make_current_device())
    coordinator.start_experiment()
    warnings: list[str] = []
    coordinator.warning_occurred.connect(warnings.append)

    device_manager.simulate_line("COM3", "OK,EXP=current-voltage")

    assert warnings == []  # студент UI-ге ешбір көрінетін ескерту жоқ
    assert coordinator.is_starting() is True  # сәйкессіз ACK "starting"-ті аяқтамайды
    assert coordinator.is_running() is False


def test_set_exp_ack_match_emits_no_warning() -> None:
    coordinator, device_manager = _make_coordinator()
    _identify(coordinator, device_manager, "COM3", _make_voltage_device())
    _identify(coordinator, device_manager, "COM4", _make_current_device())
    coordinator.start_experiment()
    warnings: list[str] = []
    coordinator.warning_occurred.connect(warnings.append)

    device_manager.simulate_line("COM3", "OK,EXP=ohms-law")

    assert warnings == []


def test_disconnect_one_port_stops_experiment_and_updates_readiness() -> None:
    coordinator, device_manager = _make_coordinator()
    _identify(coordinator, device_manager, "COM3", _make_voltage_device())
    _identify(coordinator, device_manager, "COM4", _make_current_device())
    _start_and_ack_both(coordinator, device_manager)
    assert coordinator.is_running() is True

    disconnected_ports: list[str] = []
    coordinator.port_disconnected.connect(disconnected_ports.append)
    readiness_events: list[dict] = []
    coordinator.readiness_changed.connect(readiness_events.append)

    device_manager.simulate_port_disconnected("COM3", "VOLTAGE")

    assert coordinator.is_running() is False
    assert coordinator.is_ready() is False
    assert coordinator.missing_sensor_types() == ("VOLTAGE",)
    assert disconnected_ports == ["COM3"]
    assert readiness_events[-1] == {"VOLTAGE": False, "CURRENT": True}


def test_shutdown_does_not_touch_device_manager_ports() -> None:
    """Persistent connection architecture-тың негізгі кепілдігі: coordinator
    ``shutdown()``-ы DeviceManager-дің ешбір портын жаппайды — тек
    сигналдарынан unsubscribe етеді.
    """
    coordinator, device_manager = _make_coordinator()
    _identify(coordinator, device_manager, "COM3", _make_voltage_device())
    _identify(coordinator, device_manager, "COM4", _make_current_device())

    coordinator.shutdown()

    # FakeDeviceManager-де "port жабу" әдісі жоқ — coordinator оны
    # ешқашан шақырмауы керек. Тексеру: shutdown()-нан кейін device_manager
    # әлі де сол құрылғыларды "connected" деп біледі (coordinator оны
    # тазалаған жоқ).
    assert device_manager.get_connected_device("VOLTAGE") is not None
    assert device_manager.get_connected_device("CURRENT") is not None


def test_shutdown_unsubscribes_from_device_manager_signals() -> None:
    coordinator, device_manager = _make_coordinator()
    _identify(coordinator, device_manager, "COM3", _make_voltage_device())

    coordinator.shutdown()

    # shutdown-нан кейін device_manager сигналдары келсе де, координатор
    # ЕНДІ ешбір нәтиже бермеуі керек (unsubscribed).
    identified: list[object] = []
    coordinator.device_identified.connect(identified.append)
    device_manager.simulate_identified("COM4", _make_current_device())

    assert identified == []
    assert coordinator.is_ready() is False


def test_clear_session_resets_aggregator() -> None:
    coordinator, device_manager = _make_coordinator()
    _identify(coordinator, device_manager, "COM3", _make_voltage_device())
    _identify(coordinator, device_manager, "COM4", _make_current_device())
    _start_and_ack_both(coordinator, device_manager)
    device_manager.simulate_line("COM3", "EXP=ohms-law,U=5.024")

    coordinator.clear_session()

    received: list[Measurement] = []
    coordinator.measurement_ready.connect(received.append)
    device_manager.simulate_line("COM4", "EXP=ohms-law,I=0.218")

    # voltage clear_session()-мен тазаланды, тек current келгендіктен
    # толық жиынтық әлі жасалмауы керек.
    assert received == []


def test_malformed_line_on_one_port_does_not_crash() -> None:
    coordinator, device_manager = _make_coordinator()
    _identify(coordinator, device_manager, "COM3", _make_voltage_device())
    _identify(coordinator, device_manager, "COM4", _make_current_device())
    coordinator.start_experiment()
    parse_errors: list[str] = []
    coordinator.parse_error.connect(parse_errors.append)

    device_manager.simulate_line("COM3", "EXP=ohms-law,U=,,\x00GARBAGE")

    assert parse_errors
    assert coordinator.session.measurement_count == 0


# ---- ACK-gated start (real hardware Start bug fix, kezең 15) ---------------


def test_start_does_not_set_running_before_any_ack() -> None:
    coordinator, device_manager = _make_coordinator()
    _identify(coordinator, device_manager, "COM3", _make_voltage_device())
    _identify(coordinator, device_manager, "COM4", _make_current_device())

    coordinator.start_experiment()

    assert coordinator.is_running() is False
    assert coordinator.is_starting() is True


def test_one_ack_only_running_remains_false() -> None:
    coordinator, device_manager = _make_coordinator()
    _identify(coordinator, device_manager, "COM3", _make_voltage_device())
    _identify(coordinator, device_manager, "COM4", _make_current_device())
    coordinator.start_experiment()

    _ack(device_manager, "COM3")

    assert coordinator.is_running() is False
    assert coordinator.is_starting() is True


def test_both_acks_set_running_true_and_emit_experiment_started() -> None:
    coordinator, device_manager = _make_coordinator()
    _identify(coordinator, device_manager, "COM3", _make_voltage_device())
    _identify(coordinator, device_manager, "COM4", _make_current_device())
    started_events: list[None] = []
    coordinator.experiment_started.connect(lambda: started_events.append(None))
    coordinator.start_experiment()

    _ack(device_manager, "COM3")
    assert started_events == []
    _ack(device_manager, "COM4")

    assert started_events == [None]
    assert coordinator.is_running() is True
    assert coordinator.is_starting() is False


def test_measurement_only_processed_after_both_acks() -> None:
    # Дәл осы сценарий нақты hardware bug-ты растайды: ACK-сыз кезде
    # measurement пакеттері келсе де ешбір Measurement жасалмайды.
    coordinator, device_manager = _make_coordinator()
    _identify(coordinator, device_manager, "COM3", _make_voltage_device())
    _identify(coordinator, device_manager, "COM4", _make_current_device())
    coordinator.start_experiment()
    received: list[Measurement] = []
    coordinator.measurement_ready.connect(received.append)

    device_manager.simulate_line("COM3", "EXP=ohms-law,U=5.024")
    device_manager.simulate_line("COM4", "EXP=ohms-law,I=0.218")
    assert received == []  # ACK әлі келген жоқ — running=False

    _ack(device_manager, "COM3")
    _ack(device_manager, "COM4")
    device_manager.simulate_line("COM3", "EXP=ohms-law,U=5.024")
    device_manager.simulate_line("COM4", "EXP=ohms-law,I=0.218")

    assert len(received) == 1


def test_start_timeout_emits_start_failed_and_resets_starting() -> None:
    coordinator, device_manager = _make_coordinator()
    coordinator._start_timeout_timer.setInterval(20)
    _identify(coordinator, device_manager, "COM3", _make_voltage_device())
    _identify(coordinator, device_manager, "COM4", _make_current_device())
    failures: list[str] = []
    coordinator.start_failed.connect(failures.append)

    coordinator.start_experiment()
    _ack(device_manager, "COM3")  # тек біреу ACK береді, COM4 ешқашан бермейді

    # Тұрақты timer интервалы (20ms) болғанымен, бір рет фиксирленген
    # QTest.qWait(N) орнына шартты қайталап тексеретін циклды қолданамыз:
    # толық pytest suite жүктелуінде (GC, OS scheduling) фиксирленген
    # margin жеткіліксіз болып, flaky test-ке әкелетін. Бұл цикл әр
    # қысқа qWait итерациясынан кейін нәтижені тексереді, сондықтан
    # system жүктемесі көбейсе де — тек нақты timeout болғанша күте
    # береді (жоғарғы шек 5s), ал әдейі "сынбайды".
    _wait_until(lambda: len(failures) == 1, timeout_ms=5000)

    assert len(failures) == 1
    assert "COM4" in failures[0]
    assert coordinator.is_starting() is False
    assert coordinator.is_running() is False


def test_stop_during_starting_cancels_pending_ack_wait() -> None:
    coordinator, device_manager = _make_coordinator()
    _identify(coordinator, device_manager, "COM3", _make_voltage_device())
    _identify(coordinator, device_manager, "COM4", _make_current_device())
    coordinator.start_experiment()
    assert coordinator.is_starting() is True

    coordinator.stop_experiment()

    assert coordinator.is_starting() is False
    assert coordinator.is_running() is False

    # Кешігіп келген ACK енді ешбір эффект бермеуі керек.
    started_events: list[None] = []
    coordinator.experiment_started.connect(lambda: started_events.append(None))
    _ack(device_manager, "COM3")
    _ack(device_manager, "COM4")
    assert started_events == []
    assert coordinator.is_running() is False


def test_double_start_while_starting_does_not_resend_set_exp() -> None:
    coordinator, device_manager = _make_coordinator()
    _identify(coordinator, device_manager, "COM3", _make_voltage_device())
    _identify(coordinator, device_manager, "COM4", _make_current_device())

    coordinator.start_experiment()
    calls_after_first = len(device_manager.write_calls["COM3"])
    coordinator.start_experiment()  # "starting" кезінде қайта басу

    assert len(device_manager.write_calls["COM3"]) == calls_after_first


# ---- Persistent connection: automatic reuse (жаңа архитектура) ------------


def test_refresh_from_device_manager_hydrates_already_connected_sensors() -> None:
    """Алдыңғы тәжірибеден DeviceManager-де ҚАЗІРДІҢ ӨЗІНДЕ connected
    тұрған сенсорлар — ЖАҢА identify-сіз бірден "assigned" болуы тиіс
    (automatic reuse, персистентті connection architecture-тың негізгі
    мақсаты).
    """
    device_manager = FakeDeviceManager()
    # "Алдыңғы тәжірибеден" сақталған, бұрыннан connected сенсорлар:
    device_manager.simulate_identified("COM6", _make_voltage_device(port_name="COM6"))
    device_manager.simulate_identified("COM11", _make_current_device(port_name="COM11"))

    coordinator = MultiSensorExperimentCoordinator(
        definition=OHMS_LAW_EXPERIMENT, device_manager=device_manager
    )
    identified: list[object] = []
    coordinator.device_identified.connect(identified.append)
    readiness_events: list[dict] = []
    coordinator.readiness_changed.connect(readiness_events.append)

    assert coordinator.is_ready() is False  # __init__ өзі hydrate ЕТПЕЙДІ

    coordinator.refresh_from_device_manager()

    assert coordinator.is_ready() is True
    assert coordinator.missing_sensor_types() == ()
    assert readiness_events[-1] == {"VOLTAGE": True, "CURRENT": True}
    # device_identified ЖІБЕРІЛУІ міндетті — DevicePanel осы сигналмен
    # карточканы қалпына келтіреді (эксперимент ауысқанда панель бос
    # көрінбеу үшін).
    assert {d.sensor_type for d in identified} == {"VOLTAGE", "CURRENT"}


def test_refresh_does_not_call_identify_again() -> None:
    device_manager = FakeDeviceManager()
    device_manager.simulate_identified("COM6", _make_voltage_device(port_name="COM6"))
    device_manager.simulate_identified("COM11", _make_current_device(port_name="COM11"))

    coordinator = MultiSensorExperimentCoordinator(
        definition=OHMS_LAW_EXPERIMENT, device_manager=device_manager
    )
    coordinator.refresh_from_device_manager()

    assert device_manager.identify_calls == []


def test_start_after_refresh_writes_set_exp_to_persisted_ports() -> None:
    device_manager = FakeDeviceManager()
    device_manager.simulate_identified("COM6", _make_voltage_device(port_name="COM6"))
    device_manager.simulate_identified("COM11", _make_current_device(port_name="COM11"))

    coordinator = MultiSensorExperimentCoordinator(
        definition=OHMS_LAW_EXPERIMENT, device_manager=device_manager
    )
    coordinator.refresh_from_device_manager()

    coordinator.start_experiment()

    assert device_manager.write_calls["COM6"] == ["SET_EXP=ohms-law"]
    assert device_manager.write_calls["COM11"] == ["SET_EXP=ohms-law"]


# ---- kезeng 28: Current Work/Power — PC-owned, ACK-gated monotonic elapsed time


class _FakeClock:
    """``time.monotonic()``-ты алмастыратын, қолмен басқарылатын жалған
    сағат — нақты уақыт күтуін (sleep) болдырмау үшін.
    """

    def __init__(self, start: float = 1_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def fake_clock(monkeypatch: pytest.MonkeyPatch) -> _FakeClock:
    clock = _FakeClock()
    monkeypatch.setattr(coordinator_module.time, "monotonic", clock)
    return clock


def _make_work_power_coordinator() -> tuple[MultiSensorExperimentCoordinator, FakeDeviceManager]:
    device_manager = FakeDeviceManager()
    coordinator = MultiSensorExperimentCoordinator(
        definition=CURRENT_WORK_POWER_EXPERIMENT, device_manager=device_manager
    )
    return coordinator, device_manager


def _identify_and_start(coordinator, device_manager, fake_clock: _FakeClock) -> None:
    _identify(coordinator, device_manager, "COM3", _make_voltage_device())
    _identify(coordinator, device_manager, "COM4", _make_current_device())
    _start_and_ack_both(coordinator, device_manager, experiment_id="current-work-power")


def test_elapsed_seconds_is_zero_before_start(fake_clock: _FakeClock) -> None:
    coordinator, _device_manager = _make_work_power_coordinator()
    assert coordinator.elapsed_seconds() == 0.0


def test_elapsed_seconds_is_zero_while_starting_ack_pending(fake_clock: _FakeClock) -> None:
    coordinator, device_manager = _make_work_power_coordinator()
    _identify(coordinator, device_manager, "COM3", _make_voltage_device())
    _identify(coordinator, device_manager, "COM4", _make_current_device())

    coordinator.start_experiment()
    fake_clock.advance(5.0)  # ACK әлі келген жоқ

    assert coordinator.is_starting() is True
    assert coordinator.elapsed_seconds() == 0.0


def test_elapsed_seconds_resets_to_zero_exactly_when_both_acks_received(
    fake_clock: _FakeClock,
) -> None:
    coordinator, device_manager = _make_work_power_coordinator()
    _identify(coordinator, device_manager, "COM3", _make_voltage_device())
    _identify(coordinator, device_manager, "COM4", _make_current_device())
    coordinator.start_experiment()
    fake_clock.advance(5.0)  # Start мен ACK арасындағы кідіріс (SET_EXP round-trip)

    _ack(device_manager, "COM3", "current-work-power")
    _ack(device_manager, "COM4", "current-work-power")

    assert coordinator.is_running() is True
    assert coordinator.elapsed_seconds() == 0.0  # Start-click емес, ACK сәтінен басталады


def test_elapsed_seconds_advances_with_fake_monotonic_clock(fake_clock: _FakeClock) -> None:
    coordinator, device_manager = _make_work_power_coordinator()
    _identify_and_start(coordinator, device_manager, fake_clock)

    fake_clock.advance(2.5)

    assert coordinator.elapsed_seconds() == pytest.approx(2.5)


def test_measurement_time_value_matches_elapsed_seconds(fake_clock: _FakeClock) -> None:
    coordinator, device_manager = _make_work_power_coordinator()
    _identify_and_start(coordinator, device_manager, fake_clock)
    received: list[Measurement] = []
    coordinator.measurement_ready.connect(received.append)

    fake_clock.advance(2.5)
    device_manager.simulate_line("COM3", "EXP=current-work-power,U=5.0")
    device_manager.simulate_line("COM4", "EXP=current-work-power,I=0.2")

    assert len(received) == 1
    measurement = received[0]
    assert measurement.get_value("time") == pytest.approx(2.5)
    # Power/Work бұрынғы формуласымен (P=U*I, A=P*t) есептеледі, тек
    # elapsed-time дереккөзі ауысты — жаңа "time" оқылымымен ДӘЛ БІРДЕЙ.
    assert measurement.get_value("power") == pytest.approx(1.0)
    # Бірінші үлгіде ∫P dt аралығы жоқ — жұмыс 0. P×t_elapsed емес.
    assert measurement.get_value("work") == pytest.approx(0.0)


def test_stop_freezes_elapsed_seconds(fake_clock: _FakeClock) -> None:
    coordinator, device_manager = _make_work_power_coordinator()
    _identify_and_start(coordinator, device_manager, fake_clock)
    fake_clock.advance(8.34)

    coordinator.stop_experiment()

    assert coordinator.elapsed_seconds() == pytest.approx(8.34)


def test_elapsed_seconds_does_not_advance_after_stop(fake_clock: _FakeClock) -> None:
    coordinator, device_manager = _make_work_power_coordinator()
    _identify_and_start(coordinator, device_manager, fake_clock)
    fake_clock.advance(8.34)
    coordinator.stop_experiment()

    fake_clock.advance(100.0)  # Stop-тан кейін сағат әрі жүре берсе де...

    assert coordinator.elapsed_seconds() == pytest.approx(8.34)  # ...мән өзгермейді


def test_new_start_after_stop_resets_elapsed_to_zero(fake_clock: _FakeClock) -> None:
    coordinator, device_manager = _make_work_power_coordinator()
    _identify_and_start(coordinator, device_manager, fake_clock)
    fake_clock.advance(8.34)
    coordinator.stop_experiment()

    coordinator.start_experiment()
    _ack(device_manager, "COM3", "current-work-power")
    _ack(device_manager, "COM4", "current-work-power")

    assert coordinator.elapsed_seconds() == 0.0


def test_clear_while_stopped_resets_elapsed_to_zero(fake_clock: _FakeClock) -> None:
    coordinator, device_manager = _make_work_power_coordinator()
    _identify_and_start(coordinator, device_manager, fake_clock)
    fake_clock.advance(8.34)
    coordinator.stop_experiment()

    coordinator.clear_session()

    assert coordinator.elapsed_seconds() == 0.0


def test_clear_while_running_does_not_reset_elapsed(fake_clock: _FakeClock) -> None:
    coordinator, device_manager = _make_work_power_coordinator()
    _identify_and_start(coordinator, device_manager, fake_clock)
    fake_clock.advance(3.0)

    coordinator.clear_session()  # белсенді run кезінде Clear (running=True)

    assert coordinator.elapsed_seconds() == pytest.approx(3.0)


def test_stopped_state_matching_exp_packet_no_longer_emits_visible_warning(
    fake_clock: _FakeClock,
) -> None:
    """kезeng 28, B бөлімі: running=False кезінде сәйкес EXP пакеті келсе,
    ЕНДІ көрінетін ``warning_occurred`` эмиссиясы жоқ (тек debug-лог) —
    пакет өзі әлі де толық тасталады (Measurement жасалмайды).
    """
    coordinator, device_manager = _make_work_power_coordinator()
    _identify(coordinator, device_manager, "COM3", _make_voltage_device())
    _identify(coordinator, device_manager, "COM4", _make_current_device())
    # start_experiment() ӘДЕЙІ шақырылмаған — running=False.
    warnings: list[str] = []
    received: list[Measurement] = []
    coordinator.warning_occurred.connect(warnings.append)
    coordinator.measurement_ready.connect(received.append)

    device_manager.simulate_line("COM3", "EXP=current-work-power,U=5.0")
    device_manager.simulate_line("COM4", "EXP=current-work-power,I=0.2")

    assert warnings == []
    assert received == []
