"""DevicesPage — юнит/интеграциялық тесттер.

Екі стиль қолданылады: (1) жеңіл fake ``DeviceManager``/``DeviceScanner``
double-тары (қарапайым рендеринг/күй тексерулері үшін), (2) нақты
``DeviceManager`` + ``FakeSerialThreadController`` (``test_device_manager.
py``-дегідей) — нақты HELLO handshake/identify ағынын ұштан-ұшқа тексеру
үшін.
"""

import sys
from datetime import datetime, timezone

import pytest
from PySide6.QtCore import QCoreApplication, QObject, Signal
from PySide6.QtWidgets import QApplication

import infrastructure.serial_comm.device_manager as device_manager_module
from domain.entities.active_student_context import ActiveStudentContext
from domain.entities.connected_device import ConnectedDevice
from infrastructure.serial_comm.device_manager import DeviceManager
from infrastructure.serial_comm.device_scanner import DeviceScanner, SerialDeviceInfo
from infrastructure.storage.sqlite_active_student_repository import SqliteActiveStudentRepository
from modules.electricity.experiments_config import OHMS_LAW_EXPERIMENT
from ui.pages.devices_page import DevicesPage
from ui.pages.experiment_workspace_page import ExperimentWorkspacePage

_VOLTAGE_HELLO = "TYPE=HELLO,DEV=APL-VOLTAGE-01,MODEL=V1,SENSOR=VOLTAGE,CHIP=INA226,FW=1.0"
_CURRENT_HELLO = "TYPE=HELLO,DEV=APL-CURRENT-01,MODEL=V1,SENSOR=CURRENT,CHIP=INA226,FW=1.0"


@pytest.fixture(scope="module", autouse=True)
def qt_application() -> QCoreApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


class FakeDeviceManager(QObject):
    """``DeviceManager``-дің public бетін қайталайтын жеңіл тест double."""

    device_identified = Signal(object)
    device_identification_failed = Signal(str)
    handshake_timeout = Signal(str)
    port_disconnected = Signal(str)
    port_error = Signal(str, str)
    line_received = Signal(str, str)

    def __init__(self) -> None:
        super().__init__()
        self._devices: dict[str, ConnectedDevice] = {}
        self.identify_calls: list[str] = []
        self.disconnect_calls: list[str] = []

    def identify(self, port_name: str, baud_rate: int = 115200) -> None:
        self.identify_calls.append(port_name)

    def disconnect_port(self, port_name: str) -> None:
        self.disconnect_calls.append(port_name)
        self._devices.pop(port_name, None)

    def get_connected_devices(self) -> tuple[ConnectedDevice, ...]:
        return tuple(self._devices.values())

    def is_port_connected(self, port_name: str) -> bool:
        return port_name in self._devices

    def add_connected(self, device: ConnectedDevice) -> None:
        self._devices[device.port_name] = device


class FakeDeviceScanner:
    def __init__(self, ports: tuple[SerialDeviceInfo, ...] = ()) -> None:
        self.ports = ports
        self.scan_calls = 0

    def scan(self) -> tuple[SerialDeviceInfo, ...]:
        self.scan_calls += 1
        return self.ports


class FakeSerialThreadController(QObject):
    """``test_device_manager.py``-дегі fake-пен бірдей — нақты HELLO ағынын
    тексеру үшін.
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


def _make_real_device_manager(monkeypatch: pytest.MonkeyPatch):
    fakes_by_port: dict[str, FakeSerialThreadController] = {}

    class _PendingFake(FakeSerialThreadController):
        def connect_port(self, port_name: str, baud_rate: int) -> None:
            fakes_by_port[port_name] = self
            super().connect_port(port_name, baud_rate)

    monkeypatch.setattr(
        device_manager_module, "SerialThreadController", lambda *a, **k: _PendingFake()
    )
    return DeviceManager(), fakes_by_port


def _make_device(port_name: str = "COM6", sensor_type: str = "VOLTAGE") -> ConnectedDevice:
    return ConnectedDevice(
        device_id="APL-VOLTAGE-01",
        model="V1",
        sensor_type=sensor_type,
        firmware_version="1.0",
        chip="INA226",
        serial_number=None,
        hardware_version=None,
        port_name=port_name,
        connected_at=datetime.now(timezone.utc),
        warnings=(),
    )


def _make_port(
    port_name: str,
    description: str = "USB Serial Device",
    manufacturer: str | None = None,
    vendor_id: int | None = None,
    product_id: int | None = None,
    is_likely_arduino: bool = False,
) -> SerialDeviceInfo:
    return SerialDeviceInfo(
        port_name=port_name,
        description=description,
        manufacturer=manufacturer,
        serial_number=None,
        vendor_id=vendor_id,
        product_id=product_id,
        is_likely_arduino=is_likely_arduino,
    )


# ---- Негізгі рендер/бос күй ------------------------------------------------


def test_page_renders_with_fakes() -> None:
    page = DevicesPage(device_manager=FakeDeviceManager(), device_scanner=FakeDeviceScanner())
    assert page._refresh_button.text() == "↻ Жаңарту"


def test_empty_state_shown_when_no_devices() -> None:
    page = DevicesPage(device_manager=FakeDeviceManager(), device_scanner=FakeDeviceScanner())
    page.show()

    assert page._empty_state_title_label.isVisible() is True
    assert page._connected_cards == {}


def test_summary_reflects_connected_and_available_counts() -> None:
    manager = FakeDeviceManager()
    manager.add_connected(_make_device("COM6", "VOLTAGE"))
    scanner = FakeDeviceScanner((_make_port("COM6"), _make_port("COM3")))

    page = DevicesPage(device_manager=manager, device_scanner=scanner)
    page.on_enter()

    assert page._value_labels["connected"].text() == "1"
    assert page._value_labels["available"].text() == "2"
    assert page._value_labels["errors"].text() == "0"


# ---- Connected device rendering --------------------------------------------


def test_existing_connected_device_appears_as_card() -> None:
    manager = FakeDeviceManager()
    manager.add_connected(_make_device("COM6", "VOLTAGE"))

    page = DevicesPage(device_manager=manager, device_scanner=FakeDeviceScanner())

    assert "COM6" in page._connected_cards
    assert page._connected_cards["COM6"]._title_label.text() == "Кернеу датчигі"


def test_current_sensor_display_label() -> None:
    manager = FakeDeviceManager()
    manager.add_connected(_make_device("COM11", "CURRENT"))

    page = DevicesPage(device_manager=manager, device_scanner=FakeDeviceScanner())

    assert page._connected_cards["COM11"]._title_label.text() == "Ток датчигі"


def test_unknown_sensor_type_does_not_crash_page() -> None:
    manager = FakeDeviceManager()
    manager.add_connected(_make_device("COM7", "THERMOMETER"))

    page = DevicesPage(device_manager=manager, device_scanner=FakeDeviceScanner())

    assert page._connected_cards["COM7"]._title_label.text() == "THERMOMETER"


def test_details_toggle_on_card_reveals_details() -> None:
    manager = FakeDeviceManager()
    manager.add_connected(_make_device("COM6", "VOLTAGE"))
    page = DevicesPage(device_manager=manager, device_scanner=FakeDeviceScanner())

    page._connected_cards["COM6"]._details_toggle_button.click()

    assert page._connected_cards["COM6"].is_details_expanded() is True


# ---- Available ports section ------------------------------------------------


def test_refresh_calls_scanner() -> None:
    scanner = FakeDeviceScanner((_make_port("COM3"),))
    page = DevicesPage(device_manager=FakeDeviceManager(), device_scanner=scanner)

    page._on_refresh_clicked()

    assert scanner.scan_calls >= 1


def test_managed_port_marked_in_use_and_disabled() -> None:
    manager = FakeDeviceManager()
    manager.add_connected(_make_device("COM6", "VOLTAGE"))
    scanner = FakeDeviceScanner((_make_port("COM6"),))

    page = DevicesPage(device_manager=manager, device_scanner=scanner)
    page.on_enter()

    button = page._port_buttons["COM6"]
    assert button.text() == "Қосылған"
    assert button.isEnabled() is False


def test_already_managed_port_cannot_be_reidentified() -> None:
    manager = FakeDeviceManager()
    manager.add_connected(_make_device("COM6", "VOLTAGE"))
    scanner = FakeDeviceScanner((_make_port("COM6"),))
    page = DevicesPage(device_manager=manager, device_scanner=scanner)
    page.on_enter()

    page._port_buttons["COM6"].click()  # disabled batырма — эффект болмауы тиіс

    assert manager.identify_calls == []


def test_free_port_shows_identify_button() -> None:
    scanner = FakeDeviceScanner((_make_port("COM3"),))
    page = DevicesPage(device_manager=FakeDeviceManager(), device_scanner=scanner)
    page.on_enter()

    button = page._port_buttons["COM3"]
    assert button.text() == "Қосу"
    assert button.isEnabled() is True


def test_identify_click_calls_device_manager_and_shows_pending() -> None:
    manager = FakeDeviceManager()
    scanner = FakeDeviceScanner((_make_port("COM3"),))
    page = DevicesPage(device_manager=manager, device_scanner=scanner)
    page.on_enter()

    page._port_buttons["COM3"].click()

    assert manager.identify_calls == ["COM3"]
    assert page._port_buttons["COM3"].text() == "Анықталуда..."
    assert page._port_buttons["COM3"].isEnabled() is False


def test_disconnect_button_calls_device_manager_disconnect() -> None:
    manager = FakeDeviceManager()
    manager.add_connected(_make_device("COM6", "VOLTAGE"))
    page = DevicesPage(device_manager=manager, device_scanner=FakeDeviceScanner())

    page._connected_cards["COM6"]._disconnect_button.click()

    assert manager.disconnect_calls == ["COM6"]
    assert "COM6" not in page._connected_cards


# ---- Error UX (sanitized text, no raw exceptions) ---------------------------


def test_handshake_timeout_shows_sanitized_message() -> None:
    manager = FakeDeviceManager()
    scanner = FakeDeviceScanner((_make_port("COM3"),))
    page = DevicesPage(device_manager=manager, device_scanner=scanner)
    page.on_enter()
    page._port_buttons["COM3"].click()

    manager.handshake_timeout.emit("COM3")

    assert page._message_label.text() == "Құрылғыны анықтау уақыты аяқталды"
    assert page._value_labels["errors"].text() == "1"
    assert "COM3" not in page._pending_ports


def test_port_error_shows_sanitized_message_with_port_name() -> None:
    manager = FakeDeviceManager()
    page = DevicesPage(device_manager=manager, device_scanner=FakeDeviceScanner())

    manager.port_error.emit("COM3", "raw pyserial traceback nonsense")

    assert page._message_label.text() == "COM3 портын ашу мүмкін болмады"
    assert "raw pyserial traceback nonsense" not in page._message_label.text()


def test_identification_failed_shows_sanitized_message() -> None:
    manager = FakeDeviceManager()
    page = DevicesPage(device_manager=manager, device_scanner=FakeDeviceScanner())

    manager.device_identification_failed.emit("some internal parser detail")

    assert page._message_label.text() == "Құрылғы жауап бермеді"


# ---- Persistence / leave-page guarantees ------------------------------------


def test_leaving_page_does_not_shutdown_device_manager(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager, fakes = _make_real_device_manager(monkeypatch)
    manager.identify("COM6", 115200)
    fakes["COM6"].line_received.emit(_VOLTAGE_HELLO)

    page = DevicesPage(device_manager=manager, device_scanner=FakeDeviceScanner())
    page.on_enter()
    page.setParent(None)
    page.deleteLater()

    assert fakes["COM6"].stop_calls == 0
    assert manager.is_port_connected("COM6") is True


# ---- Real HELLO handshake (integration, no fakes for DeviceManager itself) --


def test_successful_identify_makes_card_appear_via_real_signal_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager, fakes = _make_real_device_manager(monkeypatch)
    scanner = FakeDeviceScanner((_make_port("COM6"),))
    page = DevicesPage(device_manager=manager, device_scanner=scanner)
    page.on_enter()

    page._port_buttons["COM6"].click()
    fakes["COM6"].line_received.emit(_VOLTAGE_HELLO)

    assert "COM6" in page._connected_cards
    assert page._connected_cards["COM6"]._title_label.text() == "Кернеу датчигі"
    assert page._port_buttons["COM6"].text() == "Қосылған"


def test_experiment_workspace_sees_device_identified_from_devices_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Devices Page-те Identify етілген сенсорлар (§12) Ohm's Law
    ExperimentWorkspacePage-те ЕШБІР қайта Identify-сіз бірден ready
    болуы тиіс — екеуі ортақ ``DeviceManager``-ді қолданғандықтан.
    """
    manager, fakes = _make_real_device_manager(monkeypatch)
    devices_page = DevicesPage(
        device_manager=manager, device_scanner=FakeDeviceScanner((_make_port("COM6"), _make_port("COM11")))
    )
    devices_page.on_enter()

    devices_page._port_buttons["COM6"].click()
    fakes["COM6"].line_received.emit(_VOLTAGE_HELLO)
    devices_page._port_buttons["COM11"].click()
    fakes["COM11"].line_received.emit(_CURRENT_HELLO)

    active_student_repository = SqliteActiveStudentRepository()
    active_student_repository.set(
        ActiveStudentContext(classroom_id="test-classroom", student_id="test-student")
    )
    workspace_page = ExperimentWorkspacePage(
        device_scanner=DeviceScanner(),
        device_manager=manager,
        active_student_repository=active_student_repository,
    )
    workspace_page.on_enter(OHMS_LAW_EXPERIMENT)

    assert workspace_page._experiment_controller.is_ready() is True
    assert "COM6" in workspace_page._device_panel._cards_by_port
    assert "COM11" in workspace_page._device_panel._cards_by_port


def test_sidebar_collapse_does_not_break_page_rendering() -> None:
    from ui.widgets.sidebar import Sidebar

    manager = FakeDeviceManager()
    manager.add_connected(_make_device("COM6", "VOLTAGE"))
    page = DevicesPage(device_manager=manager, device_scanner=FakeDeviceScanner())
    sidebar = Sidebar()

    sidebar.collapse_button.click()
    page.on_enter()

    assert "COM6" in page._connected_cards


def test_1366x768_smoke_layout() -> None:
    manager = FakeDeviceManager()
    manager.add_connected(_make_device("COM6", "VOLTAGE"))
    manager.add_connected(_make_device("COM11", "CURRENT"))
    scanner = FakeDeviceScanner((_make_port("COM6"), _make_port("COM11"), _make_port("COM4")))

    page = DevicesPage(device_manager=manager, device_scanner=scanner)
    page.resize(1366, 768)
    page.on_enter()
    page.show()

    assert page.width() == 1366
    assert len(page._connected_cards) == 2
    assert len(page._port_buttons) == 3


# =====================================================================
# Phase 21 §14 A: "COM порттар табылмады" бос күй.
# =====================================================================


def test_no_ports_found_shows_dedicated_empty_state() -> None:
    page = DevicesPage(device_manager=FakeDeviceManager(), device_scanner=FakeDeviceScanner(()))
    page.on_enter()

    assert page._ports_stack.currentIndex() == 0
    assert page._no_ports_title_label.text() == "COM порттар табылмады."


def test_ports_available_shows_ports_stack_page() -> None:
    scanner = FakeDeviceScanner((_make_port("COM3"),))
    page = DevicesPage(device_manager=FakeDeviceManager(), device_scanner=scanner)
    page.on_enter()

    assert page._ports_stack.currentIndex() == 1


def test_no_ports_empty_state_wrapper_uses_global_qss_not_instance_stylesheet() -> None:
    """§16 "Ensure content wrappers remain transparent" — QuestionBank-
    пен БІРДЕЙ дәлелденген object-name конвенциясы (instance ``setStyleSheet()``
    ЕМЕС, § Phase 20 регрессиясы)."""
    from ui.themes.theme_manager import ThemeManager

    page = DevicesPage(device_manager=FakeDeviceManager(), device_scanner=FakeDeviceScanner(()))
    page.on_enter()

    no_ports_widget = page._ports_stack.widget(0)
    assert no_ports_widget.objectName() == "DevicesNoPortsEmptyState"
    assert no_ports_widget.styleSheet() == ""
    assert "DevicesNoPortsEmptyState" in ThemeManager().build_stylesheet()


# =====================================================================
# Phase 21 §6/§14 D: port metadata (manufacturer/VID/PID/Arduino hint) +
# busy-port detection.
# =====================================================================


def test_port_row_shows_manufacturer_and_vid_pid() -> None:
    scanner = FakeDeviceScanner(
        (_make_port("COM5", description="USB-SERIAL CH340", manufacturer="wch.cn", vendor_id=0x1A86, product_id=0x7523),)
    )
    page = DevicesPage(device_manager=FakeDeviceManager(), device_scanner=scanner)
    page.on_enter()

    from PySide6.QtWidgets import QLabel as _QLabel

    row = page._ports_layout.itemAt(0).widget()
    labels_text = " ".join(w.text() for w in row.findChildren(_QLabel))
    assert "wch.cn" in labels_text
    assert "VID:1A86 PID:7523" in labels_text


def test_port_row_shows_arduino_hint_when_likely_arduino() -> None:
    scanner = FakeDeviceScanner((_make_port("COM5", is_likely_arduino=True),))
    page = DevicesPage(device_manager=FakeDeviceManager(), device_scanner=scanner)
    page.on_enter()

    from PySide6.QtWidgets import QLabel as _QLabel

    row = page._ports_layout.itemAt(0).widget()
    labels_text = " ".join(w.text() for w in row.findChildren(_QLabel))
    assert "Arduino / ESP32 құрылғысы болуы мүмкін" in labels_text


def test_port_error_with_busy_keyword_marks_port_busy_and_disables_retry_label() -> None:
    manager = FakeDeviceManager()
    scanner = FakeDeviceScanner((_make_port("COM3"),))
    page = DevicesPage(device_manager=manager, device_scanner=scanner)
    page.on_enter()
    page._port_buttons["COM3"].click()

    manager.port_error.emit("COM3", "Permission error: Access is denied")

    assert page._port_buttons["COM3"].text() == "Қолжетімсіз"
    assert page._value_labels["errors"].text() == "1"


def test_port_error_without_busy_keyword_does_not_mark_row_busy() -> None:
    """§ "Do not fabricate" — түсініксіз OS қатесі тұрақты "busy" деп
    белгіленбейді, тек transient toast көрсетіледі."""
    manager = FakeDeviceManager()
    scanner = FakeDeviceScanner((_make_port("COM3"),))
    page = DevicesPage(device_manager=manager, device_scanner=scanner)
    page.on_enter()
    page._port_buttons["COM3"].click()

    manager.port_error.emit("COM3", "some unrelated hardware fault")

    assert page._port_buttons["COM3"].text() == "Қосу"
    assert page._value_labels["errors"].text() == "0"


def test_handshake_timeout_marks_port_with_persistent_failed_state() -> None:
    manager = FakeDeviceManager()
    scanner = FakeDeviceScanner((_make_port("COM3"),))
    page = DevicesPage(device_manager=manager, device_scanner=scanner)
    page.on_enter()
    page._port_buttons["COM3"].click()

    manager.handshake_timeout.emit("COM3")

    from PySide6.QtWidgets import QLabel as _QLabel

    row = page._ports_layout.itemAt(0).widget()
    labels_text = " ".join(w.text() for w in row.findChildren(_QLabel))
    assert "Құрылғы анықталмады." in labels_text
    assert "Порт табылды, бірақ Arduino Physics Lab құрылғысы ретінде расталмады." in labels_text
    # Retry button remains usable (§10 "port remains available for retry").
    assert page._port_buttons["COM3"].text() == "Қосу"
    assert page._port_buttons["COM3"].isEnabled() is True


def test_retry_identify_clears_previous_failed_state() -> None:
    manager = FakeDeviceManager()
    scanner = FakeDeviceScanner((_make_port("COM3"),))
    page = DevicesPage(device_manager=manager, device_scanner=scanner)
    page.on_enter()
    page._port_buttons["COM3"].click()
    manager.handshake_timeout.emit("COM3")

    page._port_buttons["COM3"].click()

    assert "COM3" not in page._port_issues


def test_refresh_clears_issue_state_for_vanished_port_only() -> None:
    manager = FakeDeviceManager()
    scanner = FakeDeviceScanner((_make_port("COM3"), _make_port("COM4")))
    page = DevicesPage(device_manager=manager, device_scanner=scanner)
    page.on_enter()
    page._port_buttons["COM3"].click()
    manager.handshake_timeout.emit("COM3")
    page._port_buttons["COM4"].click()
    manager.handshake_timeout.emit("COM4")
    assert page._value_labels["errors"].text() == "2"

    # COM4 physically disappears; COM3 remains.
    scanner.ports = (_make_port("COM3"),)
    page._on_refresh_clicked()

    assert "COM3" in page._port_issues
    assert "COM4" not in page._port_issues
    assert page._value_labels["errors"].text() == "1"


# =====================================================================
# Phase 21 §11/§12: ажырату release/reconnect, hot-plug re-scan.
# =====================================================================


def test_disconnect_then_reconnect_works_immediately(monkeypatch: pytest.MonkeyPatch) -> None:
    manager, fakes = _make_real_device_manager(monkeypatch)
    scanner = FakeDeviceScanner((_make_port("COM6"),))
    page = DevicesPage(device_manager=manager, device_scanner=scanner)
    page.on_enter()
    page._port_buttons["COM6"].click()
    fakes["COM6"].line_received.emit(_VOLTAGE_HELLO)
    assert "COM6" in page._connected_cards

    page._connected_cards["COM6"]._disconnect_button.click()
    assert "COM6" not in page._connected_cards
    assert fakes["COM6"].stop_calls == 1

    page._port_buttons["COM6"].click()
    fakes["COM6"].line_received.emit(_VOLTAGE_HELLO)

    assert "COM6" in page._connected_cards


def test_hot_plug_disconnect_rescans_and_removes_vanished_port() -> None:
    """§12 hot-plug: физикалық ажырау кезінде порт мүлде жоғалса, келесі
    рендерде қолжетімді тізімнен де кетуі тиіс (§7-мен БІРДЕЙ re-scan)."""
    manager = FakeDeviceManager()
    manager.add_connected(_make_device("COM6", "VOLTAGE"))
    scanner = FakeDeviceScanner((_make_port("COM6"),))
    page = DevicesPage(device_manager=manager, device_scanner=scanner)
    page.on_enter()
    assert page._value_labels["available"].text() == "1"

    # Физикалық USB ажырағанда, порт сканерден де жоғалады.
    scanner.ports = ()
    manager.port_disconnected.emit("COM6")

    assert scanner.scan_calls >= 2
    assert page._value_labels["available"].text() == "0"


# =====================================================================
# Phase 21 §15: НАҚТЫ (fabrication-сыз) соңғы өлшеу алдын ала көрінісі.
# =====================================================================


def test_line_received_updates_connected_card_preview() -> None:
    manager = FakeDeviceManager()
    manager.add_connected(_make_device("COM6", "VOLTAGE"))
    page = DevicesPage(device_manager=manager, device_scanner=FakeDeviceScanner())
    page.show()

    manager.line_received.emit("COM6", "EXP=ohms-law,U=5.123,I=0.184")

    card = page._connected_cards["COM6"]
    assert card._preview_label.isVisible() is True
    assert "U: 5.12 V" in card._preview_label.text()
    assert "I: 0.18 A" in card._preview_label.text()
    assert card._last_data_label.isVisible() is True


def test_line_received_for_unknown_port_is_ignored() -> None:
    manager = FakeDeviceManager()
    page = DevicesPage(device_manager=manager, device_scanner=FakeDeviceScanner())

    # Ешбір exception шықпауы тиіс — карточка жоқ порт үшін үнсіз өткізіледі.
    manager.line_received.emit("COM9", "EXP=ohms-law,U=5.0")


def test_invalid_packet_does_not_update_preview() -> None:
    manager = FakeDeviceManager()
    manager.add_connected(_make_device("COM6", "VOLTAGE"))
    page = DevicesPage(device_manager=manager, device_scanner=FakeDeviceScanner())

    manager.line_received.emit("COM6", "not a valid packet")

    card = page._connected_cards["COM6"]
    assert card._preview_label.isVisible() is False


# =====================================================================
# Phase 21 §5: белгісіз sensor_type -> warning статус карточкада.
# =====================================================================


def test_unknown_sensor_type_shows_warning_status_on_card() -> None:
    manager = FakeDeviceManager()
    manager.add_connected(_make_device("COM7", "THERMOMETER"))

    page = DevicesPage(device_manager=manager, device_scanner=FakeDeviceScanner())

    assert "Белгісіз құрылғы" in page._connected_cards["COM7"]._status_text_label.text()


def test_port_error_on_already_connected_device_marks_card_error() -> None:
    """§5 "Error: red semantic status" — БЕЛСЕНДІ құрылғының портында
    толық ажыраусыз қате пайда болса, карточка ҚЫЗЫЛ түске ауысады."""
    manager = FakeDeviceManager()
    manager.add_connected(_make_device("COM6", "VOLTAGE"))
    page = DevicesPage(device_manager=manager, device_scanner=FakeDeviceScanner())

    manager.port_error.emit("COM6", "some transient serial glitch")

    assert "Қате" in page._connected_cards["COM6"]._status_text_label.text()
