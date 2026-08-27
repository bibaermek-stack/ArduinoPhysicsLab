"""DeviceManager үшін юнит-тесттер: application-lifetime persistent
құрылғы қосылымдары — бір рет identified порт alive болса, қайта HELLO
жасалмайды (reuse), тек физикалық ажыратуда/``shutdown_all()``-де жабылады.

Нақты Serial қолданылмайды — ``FakeSerialThreadController`` арқылы
``SerialThreadController`` monkeypatch етіледі (``DeviceIdentifier``
нақты HELLO parsing логикасын қолданады, тек транспорт fake).
"""

import sys

import pytest
from PySide6.QtCore import QCoreApplication, QObject, Signal

import infrastructure.serial_comm.device_manager as device_manager_module
from infrastructure.serial_comm.device_manager import DeviceManager

_VOLTAGE_HELLO = "TYPE=HELLO,DEV=APL-VOLTAGE-01,MODEL=V1,SENSOR=VOLTAGE,CHIP=INA226,FW=1.0"
_CURRENT_HELLO = "TYPE=HELLO,DEV=APL-CURRENT-01,MODEL=V1,SENSOR=CURRENT,CHIP=INA226,FW=1.0"


@pytest.fixture(scope="module", autouse=True)
def qt_application() -> QCoreApplication:
    """QObject/Signal механизмдері үшін жалғыз QCoreApplication дана."""
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication(sys.argv)
    return app


class FakeSerialThreadController(QObject):
    """SerialThreadController-дің public сигнал/әдіс бетін қайталайтын
    тест double. ``stop()`` шақырылу санын санайды — persistent-connection
    кепілдіктерін (порт эксперимент ауысқанда жабылмайды) тексеру үшін.
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


def _make_device_manager(monkeypatch: pytest.MonkeyPatch):
    fakes_by_port: dict[str, FakeSerialThreadController] = {}

    class _PendingFake(FakeSerialThreadController):
        def connect_port(self, port_name: str, baud_rate: int) -> None:
            fakes_by_port[port_name] = self
            super().connect_port(port_name, baud_rate)

    monkeypatch.setattr(
        device_manager_module, "SerialThreadController", lambda *a, **k: _PendingFake()
    )
    return DeviceManager(), fakes_by_port


def test_identify_creates_new_connection_and_emits_device(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager, fakes = _make_device_manager(monkeypatch)
    identified: list[object] = []
    manager.device_identified.connect(identified.append)

    manager.identify("COM6", 115200)
    fakes["COM6"].line_received.emit(_VOLTAGE_HELLO)

    assert len(identified) == 1
    assert identified[0].sensor_type == "VOLTAGE"
    assert manager.is_port_connected("COM6") is True


def test_get_connected_device_by_sensor_type(monkeypatch: pytest.MonkeyPatch) -> None:
    manager, fakes = _make_device_manager(monkeypatch)
    manager.identify("COM6", 115200)
    fakes["COM6"].line_received.emit(_VOLTAGE_HELLO)

    device = manager.get_connected_device("voltage")

    assert device is not None
    assert device.port_name == "COM6"
    assert manager.get_connected_device("CURRENT") is None


def test_get_connected_devices_returns_all(monkeypatch: pytest.MonkeyPatch) -> None:
    manager, fakes = _make_device_manager(monkeypatch)
    manager.identify("COM6", 115200)
    fakes["COM6"].line_received.emit(_VOLTAGE_HELLO)
    manager.identify("COM11", 115200)
    fakes["COM11"].line_received.emit(_CURRENT_HELLO)

    devices = manager.get_connected_devices()

    assert {d.sensor_type for d in devices} == {"VOLTAGE", "CURRENT"}


def test_re_identify_on_alive_port_does_not_create_new_serial_controller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager, fakes = _make_device_manager(monkeypatch)
    manager.identify("COM6", 115200)
    fakes["COM6"].line_received.emit(_VOLTAGE_HELLO)
    first_fake = fakes["COM6"]

    identified: list[object] = []
    manager.device_identified.connect(identified.append)
    manager.identify("COM6", 115200)  # "Анықтау" қайта басылды

    # Жаңа HELLO жіберілмеді — тек кэштелген құрылғы қайта emit етілді.
    assert fakes["COM6"] is first_fake
    assert first_fake.write_calls == []  # HELLO? қайта жіберілген жоқ
    assert len(identified) == 1
    assert identified[0].sensor_type == "VOLTAGE"


def test_write_to_port_routes_to_correct_serial(monkeypatch: pytest.MonkeyPatch) -> None:
    manager, fakes = _make_device_manager(monkeypatch)
    manager.identify("COM6", 115200)
    fakes["COM6"].line_received.emit(_VOLTAGE_HELLO)

    manager.write_to_port("COM6", "SET_EXP=ohms-law")

    assert fakes["COM6"].write_calls == ["SET_EXP=ohms-law"]


def test_write_to_unknown_port_does_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    manager, _fakes = _make_device_manager(monkeypatch)

    manager.write_to_port("COM99", "SET_EXP=ohms-law")  # эксепшн шықпауы тиіс


def test_physical_disconnect_clears_tracking_and_emits_signal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager, fakes = _make_device_manager(monkeypatch)
    manager.identify("COM6", 115200)
    fakes["COM6"].line_received.emit(_VOLTAGE_HELLO)
    disconnected_ports: list[str] = []
    manager.port_disconnected.connect(disconnected_ports.append)

    fakes["COM6"].disconnected.emit()

    assert disconnected_ports == ["COM6"]
    assert manager.get_connected_device("VOLTAGE") is None
    assert manager.is_port_connected("COM6") is False


def test_reconnect_after_physical_disconnect_creates_fresh_handshake(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager, fakes = _make_device_manager(monkeypatch)
    manager.identify("COM6", 115200)
    fakes["COM6"].line_received.emit(_VOLTAGE_HELLO)
    fakes["COM6"].disconnected.emit()

    manager.identify("COM6", 115200)
    fakes["COM6"].line_received.emit(_VOLTAGE_HELLO)

    assert manager.get_connected_device("VOLTAGE") is not None
    assert manager.is_port_connected("COM6") is True


def test_explicit_disconnect_port_stops_serial(monkeypatch: pytest.MonkeyPatch) -> None:
    manager, fakes = _make_device_manager(monkeypatch)
    manager.identify("COM6", 115200)
    fakes["COM6"].line_received.emit(_VOLTAGE_HELLO)

    manager.disconnect_port("COM6")

    assert fakes["COM6"].stop_calls == 1
    assert manager.is_port_connected("COM6") is False


def test_shutdown_all_stops_every_managed_port(monkeypatch: pytest.MonkeyPatch) -> None:
    manager, fakes = _make_device_manager(monkeypatch)
    manager.identify("COM6", 115200)
    fakes["COM6"].line_received.emit(_VOLTAGE_HELLO)
    manager.identify("COM11", 115200)
    fakes["COM11"].line_received.emit(_CURRENT_HELLO)

    manager.shutdown_all()

    assert fakes["COM6"].stop_calls == 1
    assert fakes["COM11"].stop_calls == 1
    assert manager.get_connected_devices() == ()


def test_line_received_is_forwarded_with_port_name(monkeypatch: pytest.MonkeyPatch) -> None:
    manager, fakes = _make_device_manager(monkeypatch)
    manager.identify("COM6", 115200)
    fakes["COM6"].line_received.emit(_VOLTAGE_HELLO)
    lines: list[tuple[str, str]] = []
    manager.line_received.connect(lambda port, line: lines.append((port, line)))

    fakes["COM6"].line_received.emit("EXP=ohms-law,U=5.024")

    assert ("COM6", "EXP=ohms-law,U=5.024") in lines
