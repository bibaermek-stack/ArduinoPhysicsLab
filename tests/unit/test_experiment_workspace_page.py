"""ExperimentWorkspacePage интеграциясы: ExperimentController сигналдары →
DevicePanel/MeasurementWorkspace.

Нақты SerialThreadController/QSerialPort қолданылмайды — осы файлда
анықталған ``FakeExperimentController`` (тест double) ``experiment_controller_factory``
арқылы бетке егіледі.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from PySide6.QtCore import QObject, QSettings, Signal
from PySide6.QtWidgets import QApplication, QFileDialog, QSizePolicy

from domain.entities.active_student_context import ActiveStudentContext
from domain.entities.connected_device import ConnectedDevice
from domain.entities.experiment_assessment import (
    ExperimentAssessmentDefinition,
    MultipleChoiceQuestion,
    OpenResponseQuestion,
    ReflectionQuestion,
)
from domain.entities.experiment_definition import (
    ExperimentDefinition,
    ExperimentDiagram,
    ExperimentGuide,
    ExperimentReport,
)
from domain.entities.experiment_feedback_result import TeacherAssessment
from domain.entities.experiment_session import ExperimentSession
from domain.entities.measurement import Measurement
from domain.entities.sensor_channel import SensorChannel
from domain.entities.user_role import UserRole
from infrastructure.serial_comm.device_scanner import DeviceScanner
from infrastructure.storage.app_preferences import AppPreferences
from infrastructure.storage.sqlite_active_student_repository import SqliteActiveStudentRepository
from infrastructure.storage.sqlite_measurement_batch_repository import SqliteMeasurementBatchRepository
from infrastructure.storage.sqlite_session_repository import SqliteSessionRepository
from infrastructure.storage.sqlite_sync_outbox_repository import SqliteSyncOutboxRepository
from modules.electricity.module import ElectricityModule
from modules.module_registry import ModuleRegistry
from ui.pages.experiment_workspace_page import ExperimentWorkspacePage
from ui.widgets.experiment_workflow_indicator import WorkflowStepState

# Phase 39B: бұл файлдағы тестердің басым бөлігі pipeline/device
# сигналдарын тексереді — белсенді оқушы гейтіне мүлде қатысы жоқ.
# ``_make_page()`` әдепкі бойынша алдын ала таңдалған "тест оқушысымен"
# оқушы гейтін АЙНАЛЫП ӨТЕДІ (§ "existing assertions should not need to
# change"); гейттің ӨЗІН тексеретін тесттер бос репозиторийді НАҚТЫ өзі
# қолмен береді (төменде, жаңа Phase 39B тесттер блогында).
def _make_seeded_active_student_repository() -> SqliteActiveStudentRepository:
    repository = SqliteActiveStudentRepository()
    repository.set(ActiveStudentContext(classroom_id="test-classroom", student_id="test-student"))
    return repository


@pytest.fixture(scope="module", autouse=True)
def qt_application() -> QApplication:
    """QWidget-тер үшін жалғыз QApplication дана."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


class FakeExperimentController(QObject):
    """ExperimentController-дің device identification бетін қайталайтын
    тест double.
    """

    device_identified = Signal(object)
    device_identification_failed = Signal(str)
    handshake_timeout = Signal(str)
    measurement_ready = Signal(object)
    error_occurred = Signal(str)
    disconnected = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.identify_calls: list[tuple[str, int]] = []
        self.start_calls = 0
        self.stop_calls = 0
        self.clear_session_calls = 0
        self.shutdown_calls = 0
        self._running = False
        self.session = ExperimentSession(
            id="fake-session", experiment_id="E02", started_at=datetime.now(timezone.utc)
        )

    def identify_device(self, port_name: str, baud_rate: int = 115200) -> None:
        self.identify_calls.append((port_name, baud_rate))

    def start_experiment(self) -> None:
        self.start_calls += 1
        self._running = True

    def stop_experiment(self) -> None:
        self.stop_calls += 1
        self._running = False

    def clear_session(self) -> None:
        self.clear_session_calls += 1

    def is_running(self) -> bool:
        return self._running

    def shutdown(self) -> None:
        self.shutdown_calls += 1


class FakeCoordinator(QObject):
    """MultiSensorExperimentCoordinator-дің public бетін қайталайтын тест
    double.
    """

    device_identified = Signal(object)
    device_identification_failed = Signal(str)
    handshake_timeout = Signal(str)
    measurement_ready = Signal(object)
    warning_occurred = Signal(str)
    port_error = Signal(str, str)
    port_disconnected = Signal(str)
    readiness_changed = Signal(object)
    experiment_started = Signal()
    start_failed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.start_calls = 0
        self.stop_calls = 0
        self.clear_session_calls = 0
        self.shutdown_calls = 0
        self._running = False
        self._ready = False
        self._elapsed_seconds = 0.0
        self.session = ExperimentSession(
            id="fake-session", experiment_id="ohms-law", started_at=datetime.now(timezone.utc)
        )

    def set_ready_for_test(self, ready: bool) -> None:
        self._ready = ready

    def set_elapsed_seconds_for_test(self, value: float) -> None:
        self._elapsed_seconds = value

    def elapsed_seconds(self) -> float:
        return self._elapsed_seconds

    def is_ready(self) -> bool:
        return self._ready

    def is_starting(self) -> bool:
        # Fake-те ACK-gating симуляциясы жоқ (start_experiment() бірден
        # "сәтті" эмуляцияланады, төмендегі комментарийді қараңыз) —
        # "starting" аралық күйі ешқашан болмайды.
        return False

    def start_experiment(self) -> None:
        self.start_calls += 1
        self._running = True
        # Fake-те ACK-gating симуляциясы жоқ — нақты coordinator-дың
        # ACK-gated мінез-құлқы бөлек test_multi_sensor_experiment_
        # coordinator.py-де тексеріледі. Бұл жерде тек ExperimentWorkspacePage-тің
        # experiment_started/start_failed сигналдарын дұрыс өңдейтінін
        # растау үшін бірден "сәтті" эмуляцияланады.
        self.experiment_started.emit()

    def stop_experiment(self) -> None:
        self.stop_calls += 1
        self._running = False

    def clear_session(self) -> None:
        self.clear_session_calls += 1

    def is_running(self) -> bool:
        return self._running

    def shutdown(self) -> None:
        self.shutdown_calls += 1

    def refresh_from_device_manager(self) -> None:
        # Persistent connection architecture: нақты coordinator-да бұрын
        # DeviceManager-де connected тұрған сенсорларды hydrate етеді.
        # Бұл fake DeviceManager-ді мүлде модельдемейді (device_identified/
        # readiness тесттерде тікелей coordinator сигналдарын emit ету
        # арқылы симуляцияланады), сондықтан no-op жеткілікті.
        pass


class FakeCSVExporter:
    """CSVExporter-дің public бетін қайталайтын тест double."""

    def __init__(self, result: bool = True) -> None:
        self.export_calls: list[tuple[ExperimentSession, str]] = []
        self._result = result

    def export(self, session: ExperimentSession, output_path: str) -> bool:
        self.export_calls.append((session, output_path))
        return self._result


class FakeExcelExporter:
    """ExcelExporter-дің public бетін қайталайтын тест double."""

    def __init__(self, result: bool = True) -> None:
        self.export_calls: list[tuple[ExperimentSession, str]] = []
        self._result = result

    def export(self, session: ExperimentSession, output_path: str) -> bool:
        self.export_calls.append((session, output_path))
        return self._result


class FakePDFExporter:
    """PDFExporter-дің public бетін қайталайтын тест double."""

    def __init__(self, result: bool = True) -> None:
        self.export_calls: list[tuple[ExperimentSession, str]] = []
        self._result = result

    def export(self, session: ExperimentSession, output_path: str) -> bool:
        self.export_calls.append((session, output_path))
        return self._result


def _make_experiment_definition(
    formulas: dict[str, str] | None = None, description: str = ""
) -> ExperimentDefinition:
    voltage = SensorChannel(key="voltage", display_name="Кернеу", unit="V", decimals=3)
    current = SensorChannel(key="current", display_name="Ток", unit="A", decimals=3)
    power = SensorChannel(
        key="power", display_name="Қуат", unit="W", decimals=3, required=False
    )
    return ExperimentDefinition(
        id="E02",
        title="Тізбек бөлігі үшін кернеудің ток күшіне тәуелділігін зерттеу",
        description=description,
        required_channels=(voltage, current),
        derived_channels=(power,),
        formulas=formulas or {},
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


def _make_measurement() -> Measurement:
    return Measurement(
        timestamp=datetime.now(timezone.utc),
        values={"voltage": 5.024, "current": 0.218},
        experiment_id="E02",
        derived_values={"power": 1.095},
    )


def _make_page(
    csv_exporter: FakeCSVExporter | None = None,
    excel_exporter: FakeExcelExporter | None = None,
    pdf_exporter: FakePDFExporter | None = None,
    module_registry: object | None = None,
) -> tuple[ExperimentWorkspacePage, FakeExperimentController]:
    fake_controller = FakeExperimentController()
    page = ExperimentWorkspacePage(
        device_scanner=DeviceScanner(),
        csv_exporter=csv_exporter or FakeCSVExporter(),
        excel_exporter=excel_exporter or FakeExcelExporter(),
        pdf_exporter=pdf_exporter or FakePDFExporter(),
        experiment_controller_factory=lambda _experiment: fake_controller,
        active_student_repository=_make_seeded_active_student_repository(),
        module_registry=module_registry,
    )
    page.on_enter(_make_experiment_definition())
    return page, fake_controller


def test_device_identified_creates_card() -> None:
    page, fake_controller = _make_page()
    device = _make_device()

    fake_controller.device_identified.emit(device)

    assert "COM3" in page._device_panel._cards_by_port
    assert page._device_panel._cards_by_port["COM3"].device() == device


def test_handshake_timeout_shows_message() -> None:
    page, fake_controller = _make_page()

    fake_controller.handshake_timeout.emit("COM5")

    assert "COM5" in page._device_panel._message_label.text()


def test_identification_failed_shows_message() -> None:
    page, fake_controller = _make_page()

    fake_controller.device_identification_failed.emit("HELLO пакеті жарамсыз")

    assert page._device_panel._message_label.text() == "HELLO пакеті жарамсыз"


def test_device_selected_updates_workspace() -> None:
    page, _fake_controller = _make_page()
    device = _make_device()

    page._device_panel.device_selected.emit(device)

    assert page._measurement_workspace._stack.currentWidget() is (
        page._measurement_workspace._device_page
    )
    assert page._measurement_workspace._device_id_label.text() == "APL-VOLTAGE-01"


def test_measurement_ready_updates_workspace() -> None:
    page, fake_controller = _make_page()
    page._measurement_workspace.set_device(_make_device())

    fake_controller.measurement_ready.emit(_make_measurement())

    assert page._measurement_workspace._value_labels["voltage"].text() == "5.024 V"
    assert page._measurement_workspace._value_labels["power"].text() == "1.095 W"


def test_measurement_ready_updates_workspace_graph() -> None:
    page, fake_controller = _make_page()
    page._measurement_workspace.set_device(_make_device())

    fake_controller.measurement_ready.emit(_make_measurement())

    live_graph = page._measurement_workspace._live_graph
    assert list(live_graph._y_data["voltage"]) == [5.024]
    assert list(live_graph._y_data["power"]) == [1.095]


def test_measurement_ready_appends_table_row() -> None:
    page, fake_controller = _make_page()
    page._measurement_workspace.set_device(_make_device())

    fake_controller.measurement_ready.emit(_make_measurement())

    table = page._measurement_workspace._measurement_table
    assert table._model.rowCount() == 1
    assert table._model.item(0, 1).text() == "5.024"


def test_device_change_clears_table() -> None:
    page, fake_controller = _make_page()
    page._measurement_workspace.set_device(_make_device())
    fake_controller.measurement_ready.emit(_make_measurement())

    table = page._measurement_workspace._measurement_table
    assert table._model.rowCount() == 1

    page._device_panel.device_selected.emit(_make_device())

    assert table._model.rowCount() == 0


# ---- Experiment lifecycle (Бастау/Тоқтату/Тазалау) -----------------------


def test_start_calls_controller_start_experiment() -> None:
    page, fake_controller = _make_page()
    page._device_panel.device_selected.emit(_make_device())

    page._measurement_workspace._start_button.click()

    assert fake_controller.start_calls == 1
    assert fake_controller.is_running() is True


def test_stop_calls_controller_stop_experiment() -> None:
    page, fake_controller = _make_page()
    page._device_panel.device_selected.emit(_make_device())
    page._measurement_workspace._start_button.click()

    page._measurement_workspace._stop_button.click()

    assert fake_controller.stop_calls == 1
    assert fake_controller.is_running() is False


def test_clear_calls_controller_clear_session() -> None:
    page, fake_controller = _make_page()
    page._device_panel.device_selected.emit(_make_device())
    calls_before = fake_controller.clear_session_calls

    page._measurement_workspace._clear_button.click()

    assert fake_controller.clear_session_calls == calls_before + 1


def test_clear_button_clears_workspace_data() -> None:
    page, fake_controller = _make_page()
    page._device_panel.device_selected.emit(_make_device())
    fake_controller.measurement_ready.emit(_make_measurement())
    assert page._measurement_workspace._measurement_table._model.rowCount() == 1

    page._measurement_workspace._clear_button.click()

    assert page._measurement_workspace._measurement_table._model.rowCount() == 0
    assert page._measurement_workspace._value_labels["voltage"].text() == "—"


def test_device_switch_while_running_stops_experiment() -> None:
    page, fake_controller = _make_page()
    page._device_panel.device_selected.emit(_make_device())
    page._measurement_workspace._start_button.click()
    assert fake_controller.is_running() is True

    page._device_panel.device_selected.emit(_make_device())

    assert fake_controller.stop_calls == 1
    assert fake_controller.is_running() is False


def test_device_switch_clears_workspace_history() -> None:
    page, fake_controller = _make_page()
    page._device_panel.device_selected.emit(_make_device())
    fake_controller.measurement_ready.emit(_make_measurement())
    assert page._measurement_workspace._measurement_table._model.rowCount() == 1

    page._device_panel.device_selected.emit(_make_device())

    assert page._measurement_workspace._measurement_table._model.rowCount() == 0
    assert list(page._measurement_workspace._live_graph._y_data["voltage"]) == []


def test_disconnect_clears_workspace() -> None:
    page, fake_controller = _make_page()
    page._device_panel.device_selected.emit(_make_device())

    fake_controller.disconnected.emit()

    # Phase 32.1 (§11): "device disconnects while stopped — the workspace
    # remains visible and returns to waiting/not-ready state" — device_page
    # ЕНДІ жасырылмайды, тек Start disabled/status "байланыс үзілді" болады.
    workspace = page._measurement_workspace
    assert workspace._stack.currentWidget() is workspace._device_page
    assert workspace._status_message_label.text() == "Құрылғымен байланыс үзілді"
    assert workspace._start_button.isEnabled() is False


def test_disconnect_while_running_stops_experiment() -> None:
    page, fake_controller = _make_page()
    page._device_panel.device_selected.emit(_make_device())
    page._measurement_workspace._start_button.click()
    assert fake_controller.is_running() is True

    fake_controller.disconnected.emit()

    assert fake_controller.stop_calls == 1
    assert fake_controller.is_running() is False


def test_controller_error_shows_status() -> None:
    page, fake_controller = _make_page()

    fake_controller.error_occurred.emit("Serial қатесі")

    assert page._measurement_workspace._status_message_label.text() == "Serial қатесі"


def test_repeated_start_does_not_crash() -> None:
    page, fake_controller = _make_page()
    page._device_panel.device_selected.emit(_make_device())

    page._measurement_workspace.start_requested.emit()
    page._measurement_workspace.start_requested.emit()

    assert fake_controller.start_calls == 2
    assert fake_controller.is_running() is True


def test_repeated_stop_does_not_crash() -> None:
    page, fake_controller = _make_page()
    page._device_panel.device_selected.emit(_make_device())
    page._measurement_workspace.start_requested.emit()

    page._measurement_workspace.stop_requested.emit()
    page._measurement_workspace.stop_requested.emit()

    assert fake_controller.stop_calls == 2
    assert fake_controller.is_running() is False


def test_clear_while_running_does_nothing() -> None:
    page, fake_controller = _make_page()
    page._device_panel.device_selected.emit(_make_device())
    page._measurement_workspace.start_requested.emit()
    fake_controller.measurement_ready.emit(_make_measurement())
    assert page._measurement_workspace._measurement_table._model.rowCount() == 1
    calls_before = fake_controller.clear_session_calls

    page._measurement_workspace.clear_requested.emit()

    assert fake_controller.clear_session_calls == calls_before
    assert page._measurement_workspace._measurement_table._model.rowCount() == 1


# ---- Экспорт (CSV/Excel/PDF) ------------------------------------------


def test_csv_export_action_calls_csv_exporter(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_exporter = FakeCSVExporter(result=True)
    page, fake_controller = _make_page(csv_exporter=fake_exporter)
    page._device_panel.device_selected.emit(_make_device())
    fake_controller.session.add_measurement(_make_measurement())

    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", lambda *args, **kwargs: ("C:/fake/export.csv", "")
    )

    page._measurement_workspace._csv_export_action.trigger()

    assert len(fake_exporter.export_calls) == 1
    assert fake_exporter.export_calls[0][0] is fake_controller.session
    assert fake_exporter.export_calls[0][1] == "C:/fake/export.csv"


def test_export_with_empty_session_shows_message_and_skips_dialog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dialog_calls: list[None] = []
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: dialog_calls.append(None) or ("C:/fake/export.csv", ""),
    )
    page, _fake_controller = _make_page()
    page._device_panel.device_selected.emit(_make_device())

    page._measurement_workspace._csv_export_action.trigger()

    assert dialog_calls == []
    assert page._measurement_workspace._status_message_label.text() == (
        "Экспорттайтын дерек жоқ"
    )


def test_csv_export_success_shows_status(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_exporter = FakeCSVExporter(result=True)
    page, fake_controller = _make_page(csv_exporter=fake_exporter)
    page._device_panel.device_selected.emit(_make_device())
    fake_controller.session.add_measurement(_make_measurement())
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", lambda *args, **kwargs: ("C:/fake/export.csv", "")
    )

    page._measurement_workspace._csv_export_action.trigger()

    assert page._measurement_workspace._status_message_label.text() == "CSV сәтті сақталды"


def test_csv_export_exception_does_not_crash(monkeypatch: pytest.MonkeyPatch) -> None:
    class RaisingCSVExporter:
        def export(self, session: ExperimentSession, output_path: str) -> bool:
            raise OSError("Диск толы")

    page, fake_controller = _make_page(csv_exporter=RaisingCSVExporter())
    page._device_panel.device_selected.emit(_make_device())
    fake_controller.session.add_measurement(_make_measurement())
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", lambda *args, **kwargs: ("C:/fake/export.csv", "")
    )

    page._measurement_workspace._csv_export_action.trigger()

    assert "Экспорт қатесі" in page._measurement_workspace._status_message_label.text()


def test_excel_export_action_calls_excel_exporter(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_exporter = FakeExcelExporter(result=True)
    page, fake_controller = _make_page(excel_exporter=fake_exporter)
    page._device_panel.device_selected.emit(_make_device())
    fake_controller.session.add_measurement(_make_measurement())

    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: ("C:/fake/experiment_results.xlsx", ""),
    )

    page._measurement_workspace._excel_export_action.trigger()

    assert len(fake_exporter.export_calls) == 1
    assert fake_exporter.export_calls[0][0] is fake_controller.session
    assert fake_exporter.export_calls[0][1] == "C:/fake/experiment_results.xlsx"


def test_pdf_export_action_calls_pdf_exporter(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_exporter = FakePDFExporter(result=True)
    page, fake_controller = _make_page(pdf_exporter=fake_exporter)
    page._device_panel.device_selected.emit(_make_device())
    fake_controller.session.add_measurement(_make_measurement())

    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: ("C:/fake/experiment_results.pdf", ""),
    )

    page._measurement_workspace._pdf_export_action.trigger()

    assert len(fake_exporter.export_calls) == 1
    assert fake_exporter.export_calls[0][0] is fake_controller.session
    assert fake_exporter.export_calls[0][1] == "C:/fake/experiment_results.pdf"


def test_export_cancel_does_not_call_exporter(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_csv_exporter = FakeCSVExporter(result=True)
    fake_excel_exporter = FakeExcelExporter(result=True)
    page, fake_controller = _make_page(
        csv_exporter=fake_csv_exporter, excel_exporter=fake_excel_exporter
    )
    page._device_panel.device_selected.emit(_make_device())
    fake_controller.session.add_measurement(_make_measurement())

    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: ("", ""))

    page._measurement_workspace._csv_export_action.trigger()
    page._measurement_workspace._excel_export_action.trigger()

    assert fake_csv_exporter.export_calls == []
    assert fake_excel_exporter.export_calls == []


def test_on_enter_shows_experiment_title() -> None:
    page, _fake_controller = _make_page()

    assert page._title_label.text() == "Тізбек бөлігі үшін кернеудің ток күшіне тәуелділігін зерттеу"


def test_re_entering_updates_title() -> None:
    fake_controller = FakeExperimentController()
    page = ExperimentWorkspacePage(
        device_scanner=DeviceScanner(),
        experiment_controller_factory=lambda _experiment: fake_controller,
        active_student_repository=_make_seeded_active_student_repository(),
    )
    page.on_enter(ExperimentDefinition(id="e1", title="Бірінші жұмыс", description=""))

    page.on_enter(ExperimentDefinition(id="e2", title="Екінші жұмыс", description=""))

    assert page._title_label.text() == "Екінші жұмыс"


def test_on_enter_shows_description_when_present() -> None:
    page, _fake_controller = _make_page()

    assert page._description_label.text() == ""
    assert page._description_label.isHidden() is True


def test_on_enter_with_description_shows_it() -> None:
    page = ExperimentWorkspacePage(
        device_scanner=DeviceScanner(),
        experiment_controller_factory=lambda _experiment: FakeExperimentController(),
        active_student_repository=_make_seeded_active_student_repository(),
    )

    page.on_enter(_make_experiment_definition(description="Қысқа сипаттама"))

    assert page._description_label.text() == "Қысқа сипаттама"
    assert page._description_label.isHidden() is False


def test_on_enter_shows_formula_text() -> None:
    page = ExperimentWorkspacePage(
        device_scanner=DeviceScanner(),
        experiment_controller_factory=lambda _experiment: FakeExperimentController(),
        active_student_repository=_make_seeded_active_student_repository(),
    )

    page.on_enter(_make_experiment_definition(formulas={"power": "P = U × I"}))

    assert "P = U × I" in page._formula_label.text()
    assert page._formula_label.isHidden() is False


def test_on_enter_without_formula_hides_formula_label() -> None:
    page, _fake_controller = _make_page()

    assert page._formula_label.text() == ""
    assert page._formula_label.isHidden() is True


def test_on_enter_configures_measurement_workspace() -> None:
    page, _fake_controller = _make_page()

    assert page._measurement_workspace._experiment_title_label.text() == "Тізбек бөлігі үшін кернеудің ток күшіне тәуелділігін зерттеу"
    assert set(page._measurement_workspace._value_labels.keys()) == {
        "voltage",
        "current",
        "power",
    }


def test_re_entering_with_different_experiment_reconfigures_workspace() -> None:
    fake_controller = FakeExperimentController()
    page = ExperimentWorkspacePage(
        device_scanner=DeviceScanner(),
        experiment_controller_factory=lambda _experiment: fake_controller,
        active_student_repository=_make_seeded_active_student_repository(),
    )
    voltage = SensorChannel(key="voltage", display_name="Кернеу", unit="V")
    resistance = SensorChannel(
        key="resistance", display_name="Кедергі", unit="Ω", required=False
    )
    page.on_enter(_make_experiment_definition())
    assert "power" in page._measurement_workspace._value_labels

    page.on_enter(
        ExperimentDefinition(
            id="ohms-law",
            title="Тізбек бөлігі үшін кернеудің ток күшіне тәуелділігін зерттеу",
            description="",
            required_channels=(voltage,),
            derived_channels=(resistance,),
        )
    )

    assert set(page._measurement_workspace._value_labels.keys()) == {"voltage", "resistance"}


# ---- back_requested / on_enter lifecycle -------------------------------


def test_back_button_emits_back_requested() -> None:
    page, _fake_controller = _make_page()
    signals: list[None] = []
    page.back_requested.connect(lambda: signals.append(None))

    page._back_button.click()

    assert signals == [None]


def test_back_button_shuts_down_controller() -> None:
    page, fake_controller = _make_page()

    page._back_button.click()

    assert fake_controller.shutdown_calls == 1


def test_re_entering_shuts_down_previous_controller_and_resets_state() -> None:
    fake_first = FakeExperimentController()
    fake_second = FakeExperimentController()
    controllers = iter([fake_first, fake_second])
    page = ExperimentWorkspacePage(
        device_scanner=DeviceScanner(),
        experiment_controller_factory=lambda _experiment: next(controllers),
        active_student_repository=_make_seeded_active_student_repository(),
    )
    page.on_enter(_make_experiment_definition())
    page._device_panel.device_selected.emit(_make_device())
    fake_first.measurement_ready.emit(_make_measurement())
    assert page._measurement_workspace._measurement_table._model.rowCount() == 1

    page.on_enter(_make_experiment_definition())

    assert fake_first.shutdown_calls == 1
    assert page._device_panel._cards_by_port == {}
    assert page._measurement_workspace._measurement_table._model.rowCount() == 0


# ---- Multi-device (required_sensor_types >= 2) ----------------------------


def _make_multi_sensor_experiment_definition(
    display_number: int | None = None,
    guide: ExperimentGuide | None = None,
    report: ExperimentReport | None = None,
    diagram: ExperimentDiagram | None = None,
) -> ExperimentDefinition:
    voltage = SensorChannel(key="voltage", display_name="Кернеу", unit="V", decimals=3)
    current = SensorChannel(key="current", display_name="Ток", unit="A", decimals=3)
    resistance = SensorChannel(
        key="resistance", display_name="Кедергі", unit="Ω", decimals=2, required=False
    )
    return ExperimentDefinition(
        id="ohms-law",
        title="Тізбек бөлігі үшін кернеудің ток күшіне тәуелділігін зерттеу",
        description="",
        required_channels=(voltage, current),
        derived_channels=(resistance,),
        required_sensor_types=("VOLTAGE", "CURRENT"),
        display_number=display_number,
        guide=guide,
        report=report,
        diagram=diagram,
    )


class _FakeElectricityModule:
    """``IPhysicsModule``-ды дуck-typing арқылы қайталайтын тест double —
    category chip-тің catalog-тен оқылатынын растау үшін.
    """

    def get_name(self) -> str:
        return "Электр құбылыстары"

    def get_icon(self) -> str | None:
        return "⚡"

    def get_experiments(self) -> tuple[ExperimentDefinition, ...]:
        return (_make_multi_sensor_experiment_definition(),)


def _make_multi_device_page(
    coordinator: FakeCoordinator | None = None,
    module_registry: object | None = None,
    experiment: ExperimentDefinition | None = None,
) -> tuple[ExperimentWorkspacePage, FakeCoordinator]:
    fake_coordinator = coordinator or FakeCoordinator()
    page = ExperimentWorkspacePage(
        device_scanner=DeviceScanner(),
        multi_sensor_coordinator_factory=lambda _experiment: fake_coordinator,
        active_student_repository=_make_seeded_active_student_repository(),
        module_registry=module_registry,
    )
    page.on_enter(experiment or _make_multi_sensor_experiment_definition())
    return page, fake_coordinator


# ---- kезeng 29: header category chip / number badge / status detail ------


def test_category_chip_hidden_without_module_registry() -> None:
    page, _fake_coordinator = _make_multi_device_page(module_registry=None)

    assert page._category_chip_label.isHidden() is True


def test_category_chip_hidden_when_module_not_found() -> None:
    registry = ModuleRegistry()  # тіркелген модуль жоқ
    page, _fake_coordinator = _make_multi_device_page(module_registry=registry)

    assert page._category_chip_label.isHidden() is True


def test_category_chip_shows_owning_module_name_and_icon() -> None:
    registry = ModuleRegistry()
    registry.register(_FakeElectricityModule())
    page, _fake_coordinator = _make_multi_device_page(module_registry=registry)

    assert page._category_chip_label.isHidden() is False
    assert "ЭЛЕКТР ҚҰБЫЛЫСТАРЫ" in page._category_chip_label.text()
    assert "⚡" in page._category_chip_label.text()


# ---- Phase 41: current_module_accent_key() (WorkspaceBackdrop секция кілті) --


def test_current_module_accent_key_returns_electricity_for_electricity_module() -> None:
    registry = ModuleRegistry()
    registry.register(_FakeElectricityModule())
    page, _fake_coordinator = _make_multi_device_page(module_registry=registry)

    assert page.current_module_accent_key() == "electricity"


def test_current_module_accent_key_none_without_module_registry() -> None:
    page, _fake_coordinator = _make_multi_device_page(module_registry=None)

    assert page.current_module_accent_key() is None


def test_current_module_accent_key_none_when_module_not_found() -> None:
    registry = ModuleRegistry()  # тіркелген модуль жоқ
    page, _fake_coordinator = _make_multi_device_page(module_registry=registry)

    assert page.current_module_accent_key() is None


def test_number_badge_hidden_when_display_number_none() -> None:
    page, _fake_coordinator = _make_multi_device_page(
        experiment=_make_multi_sensor_experiment_definition(display_number=None)
    )

    assert page._number_badge_label.isHidden() is True


def test_number_badge_shows_display_number() -> None:
    page, _fake_coordinator = _make_multi_device_page(
        experiment=_make_multi_sensor_experiment_definition(display_number=9)
    )

    assert page._number_badge_label.isHidden() is False
    assert page._number_badge_label.text() == "№9"


def test_status_detail_empty_for_single_device_experiment() -> None:
    page, _fake_controller = _make_page()

    assert page._status_detail_label.text() == ""


def test_status_detail_shows_connected_device_count() -> None:
    page, fake_coordinator = _make_multi_device_page()

    fake_coordinator.readiness_changed.emit({"VOLTAGE": True, "CURRENT": False})

    assert "1 / 2" in page._status_detail_label.text()


def test_status_detail_shows_elapsed_time_while_running() -> None:
    fake_coordinator = FakeCoordinator()
    page, _fake_coordinator = _make_multi_device_page(coordinator=fake_coordinator)
    fake_coordinator.set_ready_for_test(True)
    fake_coordinator.set_elapsed_seconds_for_test(2.5)

    page._measurement_workspace.start_requested.emit()  # experiment_started бірден шығады (fake)
    page._on_elapsed_timer_tick()

    assert "2.50 с" in page._status_detail_label.text()


def test_status_detail_cleared_on_teardown() -> None:
    page, fake_coordinator = _make_multi_device_page()
    fake_coordinator.readiness_changed.emit({"VOLTAGE": True, "CURRENT": True})
    assert page._status_detail_label.text() != ""

    page._on_back_clicked()

    assert page._status_detail_label.text() == ""


# ---- kезeng 29: measurement -> DevicePanel live-value forwarding ----------


def test_measurement_ready_forwards_live_value_to_device_panel() -> None:
    page, fake_controller = _make_page()
    device = _make_device()
    fake_controller.device_identified.emit(device)

    fake_controller.measurement_ready.emit(_make_measurement())

    card = page._device_panel._cards_by_port["COM3"]
    assert card._live_value_label.text() == "5.024 V"


def test_multi_sensor_experiment_creates_coordinator_not_controller() -> None:
    page, fake_coordinator = _make_multi_device_page()

    assert page._is_multi_device is True
    assert page._experiment_controller is fake_coordinator


def test_multi_sensor_experiment_configures_device_panel_checklist() -> None:
    page, _fake_coordinator = _make_multi_device_page()

    assert page._device_panel._readiness_container.isHidden() is False
    assert set(page._device_panel._readiness_labels.keys()) == {"VOLTAGE", "CURRENT"}


def test_readiness_changed_updates_checklist_and_start_button() -> None:
    page, fake_coordinator = _make_multi_device_page()

    fake_coordinator.readiness_changed.emit({"VOLTAGE": True, "CURRENT": False})
    assert page._measurement_workspace._start_button.isEnabled() is False

    fake_coordinator.readiness_changed.emit({"VOLTAGE": True, "CURRENT": True})
    assert page._measurement_workspace._start_button.isEnabled() is True


def test_start_blocked_when_not_ready() -> None:
    page, fake_coordinator = _make_multi_device_page()
    fake_coordinator.set_ready_for_test(False)

    page._measurement_workspace.start_requested.emit()

    assert fake_coordinator.start_calls == 0
    assert page._measurement_workspace._status_message_label.text() == (
        "Алдымен құрылғыны таңдаңыз"
    )


def test_start_allowed_when_ready() -> None:
    page, fake_coordinator = _make_multi_device_page()
    fake_coordinator.set_ready_for_test(True)
    fake_coordinator.readiness_changed.emit({"VOLTAGE": True, "CURRENT": True})

    page._measurement_workspace.start_requested.emit()

    assert fake_coordinator.start_calls == 1


def test_port_disconnected_stops_and_shows_status() -> None:
    page, fake_coordinator = _make_multi_device_page()
    fake_coordinator.set_ready_for_test(True)
    fake_coordinator.readiness_changed.emit({"VOLTAGE": True, "CURRENT": True})
    page._measurement_workspace.start_requested.emit()
    assert fake_coordinator.is_running() is True

    fake_coordinator.port_disconnected.emit("COM3")

    assert "COM3" in page._measurement_workspace._status_message_label.text()


def test_device_card_click_is_ignored_in_multi_device_mode() -> None:
    page, fake_coordinator = _make_multi_device_page()

    page._device_panel.device_selected.emit(_make_device())

    assert fake_coordinator.clear_session_calls == 0
    assert page._selected_device is None


def test_back_button_shuts_down_coordinator() -> None:
    page, fake_coordinator = _make_multi_device_page()

    page._back_button.click()

    assert fake_coordinator.shutdown_calls == 1


def test_switching_from_multi_to_single_device_experiment_resets_mode() -> None:
    page, fake_coordinator = _make_multi_device_page()
    assert page._is_multi_device is True

    fake_single = FakeExperimentController()
    page._controller_factory = lambda _experiment: fake_single
    page.on_enter(_make_experiment_definition())

    assert page._is_multi_device is False
    assert fake_coordinator.shutdown_calls == 1
    assert page._device_panel._readiness_container.isHidden() is True


# ---- Header status indicator (Visual System V4) ---------------------------


def test_initial_status_is_waiting() -> None:
    page, _fake_controller = _make_page()

    assert page._status_text_label.text() == "Құрылғылар күтілуде"


def test_status_becomes_ready_after_device_selected() -> None:
    page, _fake_controller = _make_page()

    page._device_panel.device_selected.emit(_make_device())

    assert page._status_text_label.text() == "Дайын"


def test_status_becomes_running_after_start() -> None:
    page, fake_controller = _make_page()
    page._device_panel.device_selected.emit(_make_device())

    page._measurement_workspace._start_button.click()

    assert page._status_text_label.text() == "Өлшеу жүріп жатыр"


def test_status_becomes_stopped_after_stop() -> None:
    page, fake_controller = _make_page()
    page._device_panel.device_selected.emit(_make_device())
    page._measurement_workspace._start_button.click()

    page._measurement_workspace._stop_button.click()

    assert page._status_text_label.text() == "Тоқтатылды"


def test_status_becomes_waiting_after_disconnect() -> None:
    page, fake_controller = _make_page()
    page._device_panel.device_selected.emit(_make_device())

    fake_controller.disconnected.emit()

    assert page._status_text_label.text() == "Құрылғылар күтілуде"


def test_status_resets_to_waiting_on_re_entry() -> None:
    page, fake_controller = _make_page()
    page._device_panel.device_selected.emit(_make_device())
    page._measurement_workspace._start_button.click()
    assert page._status_text_label.text() == "Өлшеу жүріп жатыр"

    page.on_enter(_make_experiment_definition())

    assert page._status_text_label.text() == "Құрылғылар күтілуде"


def test_multi_device_status_ready_only_when_all_sensors_ready() -> None:
    page, fake_coordinator = _make_multi_device_page()

    fake_coordinator.readiness_changed.emit({"VOLTAGE": True, "CURRENT": False})
    assert page._status_text_label.text() == "Құрылғылар күтілуде"

    fake_coordinator.readiness_changed.emit({"VOLTAGE": True, "CURRENT": True})
    assert page._status_text_label.text() == "Дайын"


# ---- "Схема" — қосылым суреті диалогы (Phase 36.1) -------------------------


def _sample_diagram() -> ExperimentDiagram:
    return ExperimentDiagram(
        image_path=str(
            Path(__file__).resolve().parents[2]
            / "ui"
            / "resources"
            / "images"
            / "current_voltage_wiring.png"
        ),
        caption="Қызыл сым — оң полюс, қара сым — теріс полюс.",
    )


def test_diagram_button_hidden_when_experiment_has_no_diagram() -> None:
    page, _fake_controller = _make_page()

    assert page._diagram_button.isHidden() is True


def test_diagram_button_visible_when_experiment_has_diagram() -> None:
    page = ExperimentWorkspacePage(
        device_scanner=DeviceScanner(),
        experiment_controller_factory=lambda _experiment: FakeExperimentController(),
        active_student_repository=_make_seeded_active_student_repository(),
    )

    page.on_enter(
        ExperimentDefinition(id="e1", title="Тест", description="", diagram=_sample_diagram())
    )

    assert page._diagram_button.isHidden() is False


def test_diagram_button_click_opens_dialog_with_correct_title() -> None:
    page = ExperimentWorkspacePage(
        device_scanner=DeviceScanner(),
        experiment_controller_factory=lambda _experiment: FakeExperimentController(),
        active_student_repository=_make_seeded_active_student_repository(),
    )
    page.on_enter(
        ExperimentDefinition(id="e1", title="Электр тізбегін құрастыру және ток күшін өлшеу", description="", diagram=_sample_diagram())
    )

    page._diagram_button.click()

    assert page._diagram_dialog is not None
    assert "Электр тізбегін құрастыру және ток күшін өлшеу" in page._diagram_dialog.windowTitle()
    assert page._diagram_dialog.isVisible() is True

    page._diagram_dialog.close()


def test_diagram_button_click_does_nothing_when_no_diagram_configured() -> None:
    page, _fake_controller = _make_page()  # diagram=None (әдепкі)

    page._on_diagram_button_clicked()  # батырма жасырын болса да, тікелей шақыру

    assert page._diagram_dialog is None


def test_switching_experiment_closes_stale_diagram_dialog() -> None:
    page = ExperimentWorkspacePage(
        device_scanner=DeviceScanner(),
        experiment_controller_factory=lambda _experiment: FakeExperimentController(),
        active_student_repository=_make_seeded_active_student_repository(),
    )
    page.on_enter(
        ExperimentDefinition(id="e1", title="Тест", description="", diagram=_sample_diagram())
    )
    page._diagram_button.click()
    stale_dialog = page._diagram_dialog
    assert stale_dialog.isVisible() is True

    page.on_enter(_make_experiment_definition())  # diagram=None

    assert stale_dialog.isVisible() is False
    assert page._diagram_dialog is None


def test_switching_experiment_after_diagram_dialog_self_closed_does_not_crash() -> None:
    """Регрессия: Guide/Report диалогтарында табылған dangling C++
    reference қатесінің (Phase 36) диаграмма диалогында да ҚАЙТАЛАНБАУЫН
    тексереді.
    """
    page = ExperimentWorkspacePage(
        device_scanner=DeviceScanner(),
        experiment_controller_factory=lambda _experiment: FakeExperimentController(),
        active_student_repository=_make_seeded_active_student_repository(),
    )
    page.on_enter(
        ExperimentDefinition(id="e1", title="Тест", description="", diagram=_sample_diagram())
    )
    page._diagram_button.click()
    page._diagram_dialog._close_button.click()  # диалог ӨЗ батырмасымен жабылады
    QApplication.instance().processEvents()
    assert page._diagram_dialog is None  # дереу тазаланды

    # Бұл жол дангling сілтеме болса RuntimeError шығарар еді.
    page.on_enter(_make_experiment_definition())

    assert page._diagram_dialog is None


def test_repeated_diagram_open_close_does_not_accumulate_dialogs() -> None:
    page = ExperimentWorkspacePage(
        device_scanner=DeviceScanner(),
        experiment_controller_factory=lambda _experiment: FakeExperimentController(),
        active_student_repository=_make_seeded_active_student_repository(),
    )
    page.on_enter(
        ExperimentDefinition(id="e1", title="Тест", description="", diagram=_sample_diagram())
    )

    for _ in range(3):
        page._diagram_button.click()
        page._diagram_dialog.close()

    app = QApplication.instance()
    for _ in range(5):
        app.processEvents()

    remaining = [
        widget
        for widget in QApplication.instance().topLevelWidgets()
        if widget.__class__.__name__ == "ExperimentDiagramDialog"
    ]
    assert remaining == []


# ---- Data Journal V1: session persistence lifecycle (spec §29) ------------


def _make_page_with_repository() -> tuple[
    ExperimentWorkspacePage, FakeExperimentController, SqliteSessionRepository
]:
    fake_controller = FakeExperimentController()
    repository = SqliteSessionRepository()  # :memory:
    page = ExperimentWorkspacePage(
        device_scanner=DeviceScanner(),
        experiment_controller_factory=lambda _experiment: fake_controller,
        session_repository=repository,
        active_student_repository=_make_seeded_active_student_repository(),
    )
    page.on_enter(_make_experiment_definition())
    return page, fake_controller, repository


def _add_measurements(controller: FakeExperimentController, count: int) -> None:
    for _ in range(count):
        controller.session.add_measurement(_make_measurement())


def test_stop_with_measurements_saves_one_session() -> None:
    page, fake_controller, repository = _make_page_with_repository()
    page._device_panel.device_selected.emit(_make_device())
    page._measurement_workspace._start_button.click()
    _add_measurements(fake_controller, 3)

    page._measurement_workspace._stop_button.click()

    assert repository.count_sessions() == 1
    summary = repository.get_session("fake-session")
    assert summary is not None
    assert summary.measurement_count == 3
    assert summary.experiment_title == "Тізбек бөлігі үшін кернеудің ток күшіне тәуелділігін зерттеу"


def test_stop_with_zero_measurements_saves_nothing() -> None:
    page, _fake_controller, repository = _make_page_with_repository()
    page._device_panel.device_selected.emit(_make_device())
    page._measurement_workspace._start_button.click()

    page._measurement_workspace._stop_button.click()

    assert repository.count_sessions() == 0


def test_back_with_measurements_saves_session_once() -> None:
    page, fake_controller, repository = _make_page_with_repository()
    page._device_panel.device_selected.emit(_make_device())
    page._measurement_workspace._start_button.click()
    _add_measurements(fake_controller, 5)

    page._on_back_clicked()

    assert repository.count_sessions() == 1
    assert repository.get_session("fake-session").measurement_count == 5


def test_switching_experiment_saves_old_session_once() -> None:
    page, fake_controller, repository = _make_page_with_repository()
    page._device_panel.device_selected.emit(_make_device())
    page._measurement_workspace._start_button.click()
    _add_measurements(fake_controller, 4)

    # Жаңа тәжірибеге ауысу — on_enter() алдымен _teardown_pipeline()
    # арқылы ЕСКІ сессияны сақтайды.
    page.on_enter(
        ExperimentDefinition(id="e-new", title="Жаңа тәжірибе", description="")
    )

    assert repository.count_sessions() == 1
    assert repository.get_session("fake-session").measurement_count == 4


def test_stop_then_back_then_quit_saves_exactly_one_row_no_duplicates() -> None:
    page, fake_controller, repository = _make_page_with_repository()
    page._device_panel.device_selected.emit(_make_device())
    page._measurement_workspace._start_button.click()
    _add_measurements(fake_controller, 7)

    page._measurement_workspace._stop_button.click()  # 1-ші сақтау
    page._on_back_clicked()  # 2-ші сақтау (сол сессия, идемпотентті)
    page.finalize_active_session()  # app quit safety-net — pipeline None, no-op

    assert repository.count_sessions() == 1
    assert repository.get_session("fake-session").measurement_count == 7


def test_clear_does_not_delete_historical_session() -> None:
    page, fake_controller, repository = _make_page_with_repository()
    page._device_panel.device_selected.emit(_make_device())
    page._measurement_workspace._start_button.click()
    _add_measurements(fake_controller, 2)
    page._measurement_workspace._stop_button.click()
    assert repository.count_sessions() == 1

    # Clear тек live workspace буферін тазалайды — тарихи DB жазбасын
    # ЕШҚАШАН өшірмейді.
    page._measurement_workspace._clear_button.click()

    assert repository.count_sessions() == 1
    assert repository.get_session("fake-session").measurement_count == 2


def test_finalize_active_session_is_safe_with_no_active_pipeline() -> None:
    page, _fake_controller, repository = _make_page_with_repository()
    page._on_back_clicked()  # pipeline-ды жояды (бос сессия, сақталмайды)

    page.finalize_active_session()  # controller=None — қатесіз ешнәрсе істемейді

    assert repository.count_sessions() == 0


def test_device_manager_unaffected_by_session_persistence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page, fake_controller, _repository = _make_page_with_repository()
    shutdown_calls = []
    monkeypatch.setattr(
        page._device_manager, "shutdown_all", lambda: shutdown_calls.append(1)
    )
    page._device_panel.device_selected.emit(_make_device())
    page._measurement_workspace._start_button.click()
    _add_measurements(fake_controller, 3)

    page._measurement_workspace._stop_button.click()
    page._on_back_clicked()

    assert shutdown_calls == []


# ---- kезeng 28: Current Work/Power elapsed-time QTimer lifecycle ----------


def test_elapsed_timer_inactive_before_start() -> None:
    page, _fake_coordinator = _make_multi_device_page()

    assert page._elapsed_timer.isActive() is False


def test_elapsed_timer_starts_only_after_experiment_started() -> None:
    page, fake_coordinator = _make_multi_device_page()
    fake_coordinator.set_ready_for_test(True)

    # FakeCoordinator.start_experiment() experiment_started-ты бірден
    # (синхронды) шығарады — нақты ACK-gated coordinator-дың мінез-құлқы
    # test_multi_sensor_experiment_coordinator.py-де бөлек тексеріледі,
    # бұл жерде тек ExperimentWorkspacePage-тің сол сигналға дұрыс жауап
    # беретінін (таймерді бастауын) растаймыз.
    page._measurement_workspace.start_requested.emit()

    assert page._elapsed_timer.isActive() is True


def test_elapsed_timer_stops_on_stop_requested() -> None:
    page, fake_coordinator = _make_multi_device_page()
    fake_coordinator.set_ready_for_test(True)
    page._measurement_workspace.start_requested.emit()
    assert page._elapsed_timer.isActive() is True

    page._measurement_workspace.stop_requested.emit()

    assert page._elapsed_timer.isActive() is False


def test_elapsed_timer_stops_on_back_button() -> None:
    page, fake_coordinator = _make_multi_device_page()
    fake_coordinator.set_ready_for_test(True)
    page._measurement_workspace.start_requested.emit()
    assert page._elapsed_timer.isActive() is True

    page._back_button.click()

    assert page._elapsed_timer.isActive() is False


def test_elapsed_timer_stops_on_experiment_switch() -> None:
    page, fake_coordinator = _make_multi_device_page()
    fake_coordinator.set_ready_for_test(True)
    page._measurement_workspace.start_requested.emit()
    assert page._elapsed_timer.isActive() is True

    page.on_enter(_make_multi_sensor_experiment_definition())  # жаңа on_enter() — teardown

    assert page._elapsed_timer.isActive() is False


def test_elapsed_timer_stops_on_port_disconnected() -> None:
    page, fake_coordinator = _make_multi_device_page()
    fake_coordinator.set_ready_for_test(True)
    page._measurement_workspace.start_requested.emit()
    assert page._elapsed_timer.isActive() is True

    fake_coordinator.port_disconnected.emit("COM3")

    assert page._elapsed_timer.isActive() is False


def test_elapsed_timer_never_started_on_start_failed() -> None:
    page, fake_coordinator = _make_multi_device_page()

    fake_coordinator.start_failed.emit("ACK келмеді")

    assert page._elapsed_timer.isActive() is False


def test_elapsed_timer_tick_updates_workspace_with_coordinator_elapsed_seconds() -> None:
    page, fake_coordinator = _make_multi_device_page()
    fake_coordinator.set_ready_for_test(True)
    page._measurement_workspace.start_requested.emit()
    fake_coordinator.set_elapsed_seconds_for_test(2.5)
    calls: list[float] = []
    page._measurement_workspace.update_elapsed_time = calls.append

    page._on_elapsed_timer_tick()

    assert calls == [2.5]


def test_elapsed_timer_tick_is_noop_for_single_device_experiment() -> None:
    page, _fake_controller = _make_page()  # single-device (ExperimentController) жол

    # single-device FakeExperimentController-де elapsed_seconds() ЖОҚ —
    # _on_elapsed_timer_tick() _is_multi_device=False-пен қорғалғандықтан
    # оны ешқашан шақырмауы керек (AttributeError болмайды).
    page._on_elapsed_timer_tick()  # exception шықпауы керек

    assert page._elapsed_timer.isActive() is False


def test_stop_syncs_final_elapsed_value_after_timer_stops() -> None:
    page, fake_coordinator = _make_multi_device_page()
    fake_coordinator.set_ready_for_test(True)
    page._measurement_workspace.start_requested.emit()
    fake_coordinator.set_elapsed_seconds_for_test(8.34)
    calls: list[float] = []
    page._measurement_workspace.update_elapsed_time = calls.append

    page._measurement_workspace.stop_requested.emit()

    # Stop сәтінде дәл соңғы (frozen) мәнмен бір мәрте синхрондалады.
    assert calls == [8.34]


# ---- Phase 32: shared workspace layout architecture -----------------------
#
# Root cause: ExperimentWorkspacePage's top-level QVBoxLayout added
# body_layout (DevicePanel + MeasurementWorkspace) without an explicit
# stretch factor. This worked implicitly (MeasurementWorkspace's own
# expanding size policy absorbed the surplus), but was not architecturally
# explicit/testable. These tests assert the stretch/size-policy CONTRACT,
# not pixel geometry, so they hold regardless of experiment type, metric
# card count, or window resolution — verified with both the single-device
# (_make_page) and multi-sensor (_make_multi_device_page, the path every
# production experiment actually uses) pipelines.


def test_body_layout_gives_measurement_workspace_the_stretch() -> None:
    """Phase 32.2: DevicePanel ЕНДІ body_layout-тың бөлігі ЕМЕС (dedicated
    "Құрылғылар" бетімен дублирленетін, горизонталь орынды тегін алатын
    sidebar алынып тасталды) — MeasurementWorkspace ЖАЛҒЫЗ item, барлық
    енді иеленеді.
    """
    page, _fake_controller = _make_page()

    # Phase 39B: MeasurementWorkspace ЕНДІ ``_body_stack`` (QStackedWidget)
    # ІШІНДЕ — "Оқушы таңдалмаған" блокталған күйімен бөліседі (§ session
    # ownership gating). ``_body_layout``-тың ЖАЛҒЫЗ item-і ЕНДІ
    # ``_body_stack`` өзі, стретчті ОСЫ алады — MeasurementWorkspace-тің
    # ӨЗІ (стек ІШІНДЕ) әлі де толық ені/биіктігін алады (QStackedWidget
    # әдепкі бойынша ағымдағы виджеттің sizeHint-іне сай өседі).
    layout = page._body_layout
    device_panel_index = layout.indexOf(page._device_panel)
    stack_index = layout.indexOf(page._body_stack)

    assert device_panel_index == -1
    assert stack_index != -1
    assert layout.stretch(stack_index) == 1
    assert page._body_stack.indexOf(page._measurement_workspace) != -1


def test_main_workspace_row_receives_the_page_level_stretch() -> None:
    """Header (top_row/category_row/title_row/description/formula/diagram)
    компакт қалады, тек body_layout (DevicePanel+MeasurementWorkspace)
    беттің ҚАЛҒАН барлық биіктігін иеленеді.
    """
    page, _fake_controller = _make_page()

    page_layout = page.layout()
    body_layout_index = None
    for index in range(page_layout.count()):
        item = page_layout.itemAt(index)
        if item.layout() is page._body_layout:
            body_layout_index = index
            break

    assert body_layout_index is not None
    assert page_layout.stretch(body_layout_index) == 1
    for index in range(page_layout.count()):
        if index != body_layout_index:
            assert page_layout.stretch(index) == 0


def test_measurement_workspace_uses_expanding_size_policy() -> None:
    page, _fake_controller = _make_page()
    policy = page._measurement_workspace.sizePolicy()
    assert policy.horizontalPolicy() == QSizePolicy.Policy.Expanding
    assert policy.verticalPolicy() == QSizePolicy.Policy.Expanding


def test_device_panel_does_not_consume_full_available_width() -> None:
    page, _fake_controller = _make_page()
    policy = page._device_panel.sizePolicy()
    assert policy.horizontalPolicy() != QSizePolicy.Policy.Expanding
    assert page._device_panel.maximumWidth() <= 300


def test_multi_sensor_production_pipeline_shares_the_same_stretch_contract() -> None:
    """Барлық production тәжірибесі MultiSensorExperimentCoordinator
    қолданады — сол жол да ДӘЛ СОЛ layout-контрактіні бөлісетінін
    растайды (эксперимент-специфик geometry ЖОҚ).
    """
    page, fake_coordinator = _make_multi_device_page()
    fake_coordinator.set_ready_for_test(True)
    page._on_readiness_changed({"VOLTAGE": True, "CURRENT": True})

    layout = page._body_layout
    assert layout.stretch(layout.indexOf(page._body_stack)) == 1
    # Root cause bug: multi-device flow ЕШҚАШАН set_device() шақырмайды,
    # сондықтан device_info_section МІНДЕТТІ ТҮРДЕ жасырын қалуы керек
    # (metric cards тікелей секцияның орнынан басталуы үшін).
    assert page._measurement_workspace._device_info_section.isHidden() is True


# ---- Phase 32.1: hardware-independent workspace / waiting-for-devices ----
#
# Root cause: MultiSensorExperimentCoordinator.readiness_changed тек
# _register_assigned_device()/_on_device_manager_port_disconnected()-тен
# ғана emit етіледі — ЕШҚАШАН coordinator құрылған сәтте ЕМЕС. 0 құрылғымен
# refresh_from_device_manager() ешбір нәрсе hydrate етпейді, демек
# readiness_changed ЕШҚАШАН келмейді, ExperimentWorkspacePage._on_readiness_
# changed() ЕШҚАШАН шақырылмайды, MeasurementWorkspace.set_ready()
# ЕШҚАШАН шақырылмайды — workspace _no_device_page-де ілініп қалады.
# Түзету: MeasurementWorkspace.configure_for_experiment() бетті бірден
# _device_page-ге ауыстырады; set_ready()/clear_device() ЕНДІ page-ты
# ЖАСЫРМАЙДЫ, тек Start/Тоқтату/Тазалау батырмаларын басқарады.


def test_zero_device_workspace_is_fully_visible() -> None:
    page, _fake_coordinator = _make_multi_device_page()

    workspace = page._measurement_workspace
    assert workspace._stack.currentWidget() is workspace._device_page


def test_zero_device_metric_cards_show_unavailable_placeholders() -> None:
    page, _fake_coordinator = _make_multi_device_page()

    workspace = page._measurement_workspace
    assert workspace._value_labels["voltage"].text() == "—"
    assert workspace._value_labels["current"].text() == "—"


def test_zero_device_graph_card_is_visible_with_axes_and_toolbar() -> None:
    page, _fake_coordinator = _make_multi_device_page()

    live_graph = page._measurement_workspace._live_graph
    assert live_graph.isHidden() is False
    assert live_graph._clear_button.isHidden() is False
    assert live_graph._auto_scale_checkbox.isHidden() is False
    # Ешбір fake нүкте жасалмаған — қисықтар толығымен бос.
    assert all(len(points) == 0 for points in live_graph._x_data.values())


def test_zero_device_table_is_visible_with_experiment_columns_and_no_rows() -> None:
    page, _fake_coordinator = _make_multi_device_page()

    table = page._measurement_workspace._measurement_table
    assert table.isHidden() is False
    assert table._model.columnCount() > 1  # "№" + кем дегенде бір арна
    assert table._model.rowCount() == 0  # fake жол ЖОҚ


def test_zero_device_start_button_is_disabled() -> None:
    page, _fake_coordinator = _make_multi_device_page()

    assert page._measurement_workspace._start_button.isEnabled() is False


def test_zero_device_status_shows_waiting_with_zero_of_total_count() -> None:
    page, _fake_coordinator = _make_multi_device_page()

    assert page._status_text_label.text() == "Құрылғылар күтілуде"
    assert "0 / 2" in page._status_detail_label.text()


def test_partial_readiness_one_of_two_start_still_disabled() -> None:
    page, fake_coordinator = _make_multi_device_page()

    fake_coordinator.readiness_changed.emit({"VOLTAGE": True, "CURRENT": False})

    workspace = page._measurement_workspace
    assert workspace._stack.currentWidget() is workspace._device_page
    assert workspace._start_button.isEnabled() is False
    assert page._status_text_label.text() == "Құрылғылар күтілуде"
    assert "1 / 2" in page._status_detail_label.text()
    assert page._device_panel._readiness_labels["VOLTAGE"].text() == "✓ Кернеу датчигі"
    assert (
        page._device_panel._readiness_labels["CURRENT"].text()
        == "○ Ток датчигі — Қосылмаған"
    )


def test_full_readiness_enables_start_via_existing_mechanism_only() -> None:
    """Start тек coordinator-дың readiness_changed(барлығы True) сигналы
    арқылы ғана enabled болады — ешбір жаңа/қосымша readiness state
    machine қосылмаған.
    """
    page, fake_coordinator = _make_multi_device_page()
    assert page._measurement_workspace._start_button.isEnabled() is False

    fake_coordinator.readiness_changed.emit({"VOLTAGE": True, "CURRENT": True})

    assert page._measurement_workspace._start_button.isEnabled() is True
    assert page._status_text_label.text() == "Дайын"


def test_hot_plug_updates_existing_page_without_recreation() -> None:
    """Құрылғылар кезек-кезек қосылғанда (0/2 → 1/2 → 2/2), БІРДЕЙ
    MeasurementWorkspace/graph/table объектілері сақталады — бет
    ешқашан қайта құрылмайды.
    """
    page, fake_coordinator = _make_multi_device_page()
    workspace = page._measurement_workspace
    original_workspace = workspace
    original_graph = workspace._live_graph
    original_table = workspace._measurement_table

    fake_coordinator.readiness_changed.emit({"VOLTAGE": True, "CURRENT": False})
    assert page._measurement_workspace is original_workspace
    assert page._measurement_workspace._live_graph is original_graph
    assert page._measurement_workspace._measurement_table is original_table
    assert "1 / 2" in page._status_detail_label.text()

    fake_coordinator.readiness_changed.emit({"VOLTAGE": True, "CURRENT": True})
    assert page._measurement_workspace is original_workspace
    assert page._measurement_workspace._live_graph is original_graph
    assert page._measurement_workspace._measurement_table is original_table
    assert "2 / 2" in page._status_detail_label.text()
    assert page._measurement_workspace._start_button.isEnabled() is True


def test_disconnect_after_ready_returns_to_not_ready_presentation() -> None:
    page, fake_coordinator = _make_multi_device_page()
    fake_coordinator.readiness_changed.emit({"VOLTAGE": True, "CURRENT": True})
    assert page._measurement_workspace._start_button.isEnabled() is True

    fake_coordinator.readiness_changed.emit({"VOLTAGE": True, "CURRENT": False})

    workspace = page._measurement_workspace
    assert workspace._stack.currentWidget() is workspace._device_page
    assert workspace._start_button.isEnabled() is False
    assert page._status_text_label.text() == "Құрылғылар күтілуде"


def test_zero_device_navigation_never_requires_a_real_com_port() -> None:
    """§10: Laboratory → тәжірибе ашу → Артқа → басқа тәжірибе ашу —
    ешбір нақты DeviceScanner/serial port шақырылмайды (тек DeviceScanner
    инстанциясы беріледі, ешбір scan() шақырылмайды).
    """
    experiments = list(ElectricityModule().get_experiments())
    implemented = [e for e in experiments if e.is_implemented]
    assert len(implemented) == 6  # барлық 6 электр тәжірибесі (Phase 38B)

    fake_coordinator = FakeCoordinator()
    page = ExperimentWorkspacePage(
        device_scanner=DeviceScanner(),
        multi_sensor_coordinator_factory=lambda _e: fake_coordinator,
        active_student_repository=_make_seeded_active_student_repository(),
    )
    for experiment in implemented:
        page.on_enter(experiment)
        workspace = page._measurement_workspace
        assert workspace._stack.currentWidget() is workspace._device_page
        page._on_back_clicked()


def test_all_five_implemented_experiments_render_without_hardware() -> None:
    """§8/§16: current-voltage (2 карточка), series-connection,
    parallel-connection, current-work-power (3 карточка), ohms-law
    (XY/scatter+fit+capture) — БӘРІ 0 құрылғымен толық көрінеді, тек
    ЖАЛҒЫЗ ортақ MeasurementWorkspace/DevicePanel архитектурасы арқылы
    (эксперимент-специфик "no-device" бет ЖОҚ).
    """
    experiments = [e for e in ElectricityModule().get_experiments() if e.is_implemented]

    for experiment in experiments:
        page, _fake_coordinator = _make_multi_device_page(experiment=experiment)
        workspace = page._measurement_workspace

        assert workspace._stack.currentWidget() is workspace._device_page
        assert workspace._start_button.isEnabled() is False
        assert workspace._measurement_table._model.rowCount() == 0
        assert all(len(pts) == 0 for pts in workspace._live_graph._x_data.values())
        # Кемінде бір metric card болуы керек, барлығы "—" placeholder-де.
        assert len(workspace._value_labels) > 0
        for key, label in workspace._value_labels.items():
            if key == "time":
                continue  # PC-generated, "0.00 s" — §2-де нақты рұқсат етілген
            assert label.text() == "—"


def test_ohms_law_capture_hint_shown_instead_of_generic_empty_state() -> None:
    """Ohm's Law-дың ӨЗ capture hint-і бар (§8: "manual capture
    controls" эксперимент-специфик UI ретінде сақталуы керек) —
    жалпы LiveGraphWidget empty-state хабарламасымен қосарланбайды.
    """
    ohms_law = next(
        e for e in ElectricityModule().get_experiments() if e.id == "ohms-law"
    )
    page, _fake_coordinator = _make_multi_device_page(experiment=ohms_law)

    live_graph = page._measurement_workspace._live_graph
    assert live_graph._capture_button.isHidden() is False
    assert live_graph._hint_label.isHidden() is False
    assert live_graph._empty_state_label.isHidden() is True


def test_zero_device_current_voltage_graph_shows_generic_empty_state_message() -> None:
    current_voltage = next(
        e for e in ElectricityModule().get_experiments() if e.id == "current-voltage"
    )
    page, _fake_coordinator = _make_multi_device_page(experiment=current_voltage)

    assert page._measurement_workspace._live_graph._empty_state_label.isHidden() is False


def test_no_fake_measurement_flows_with_zero_devices() -> None:
    """Workspace/coordinator арасында ешбір fake Measurement generate
    етілмейді — set_measurement() тек НАҚТЫ coordinator.measurement_
    ready сигналымен шақырылады, ал 0 құрылғымен ол ЕШҚАШАН emit
    етілмейді (fake-те де, нақты coordinator-да да).
    """
    page, fake_coordinator = _make_multi_device_page()
    calls: list[object] = []
    page._measurement_workspace.set_measurement = calls.append

    # readiness signal-дар (0/2, 1/2) ешбір Measurement генерацияламайды.
    fake_coordinator.readiness_changed.emit({"VOLTAGE": True, "CURRENT": False})

    assert calls == []


# ---- Phase 32.2: remove redundant experiment sidebar/title ---------------
#
# Root cause #1: DevicePanel-ды ExperimentWorkspacePage.__init__() body_
# layout-қа (maxWidth=260, stretch=0) қосатын — dedicated "Құрылғылар"
# бетімен (DevicesPage) толық дублирленетін функционалдылық, тек
# горизонталь орынды тегін алатын. Түзету: DevicePanel ЕНДІ body_layout-
# қа ЕШҚАШАН қосылмайды әрі әдепкі бойынша жасырын (объект өзі ескі
# single-device сигнал wiring/тесттер үшін сақталды, DevicePanel класы
# ӨЗІ бұзылмады/жойылмады — "Do NOT remove or break DevicePanel
# globally").
#
# Root cause #2: MeasurementWorkspace._experiment_title_label
# ExperimentWorkspacePage._title_label-мен ДӘЛ БІРДЕЙ мәтінді (experiment.
# title) екінші рет көрсететін. Түзету: MeasurementWorkspace-тегі
# көшірме әдепкі бойынша жасырын (Qt: hidden widget layout-та орын
# алмайды).


def test_device_panel_is_never_added_to_the_visible_body_layout() -> None:
    page, _fake_controller = _make_page()
    assert page._body_layout.indexOf(page._device_panel) == -1


def test_device_panel_is_hidden_and_has_zero_visual_footprint() -> None:
    page, _fake_controller = _make_page()
    assert page._device_panel.isHidden() is True


def test_measurement_workspace_is_the_sole_body_layout_item() -> None:
    """DevicePanel алынғаннан кейін ``_body_stack`` (MeasurementWorkspace/
    блокталған күй контейнері) body_layout-тың ЖАЛҒЫЗ item-і, барлық
    қолжетімді енін алады (Phase 39B: MeasurementWorkspace ЕНДІ осы
    стектің ІШІНДЕ, тікелей body_layout-та ЕМЕС).
    """
    page, _fake_controller = _make_page()
    layout = page._body_layout
    assert layout.count() == 1
    assert layout.itemAt(0).widget() is page._body_stack
    assert page._body_stack.currentWidget() is page._measurement_workspace


def test_duplicate_workspace_title_is_hidden() -> None:
    page, _fake_controller = _make_page()
    assert page._measurement_workspace._experiment_title_label.isHidden() is True


def test_page_header_title_still_shows_experiment_title() -> None:
    page, _fake_controller = _make_page()
    assert page._title_label.text() == "Тізбек бөлігі үшін кернеудің ток күшіне тәуелділігін зерттеу"
    assert page._title_label.isHidden() is False


@pytest.mark.parametrize(
    "experiment_factory",
    [
        lambda: next(
            e for e in ElectricityModule().get_experiments() if e.id == "current-voltage"
        ),
        lambda: next(
            e for e in ElectricityModule().get_experiments() if e.id == "ohms-law"
        ),
        lambda: next(
            e
            for e in ElectricityModule().get_experiments()
            if e.id == "current-work-power"
        ),
        lambda: next(
            e
            for e in ElectricityModule().get_experiments()
            if e.id == "series-connection"
        ),
        lambda: next(
            e
            for e in ElectricityModule().get_experiments()
            if e.id == "parallel-connection"
        ),
    ],
)
def test_all_five_experiments_have_no_sidebar_and_no_duplicate_title(
    experiment_factory,
) -> None:
    """Шеред architecture — эксперимент ID-ге тәуелсіз, барлық 5
    implemented electricity тәжірибесінде sidebar ЖОҚ, title бір
    жерде ғана.
    """
    experiment = experiment_factory()
    page, _fake_coordinator = _make_multi_device_page(experiment=experiment)

    assert page._body_layout.indexOf(page._device_panel) == -1
    assert page._device_panel.isHidden() is True
    assert page._measurement_workspace._experiment_title_label.isHidden() is True
    assert page._title_label.text() == experiment.title
    # Sidebar алынғаннан кейін де zero-hardware workspace толық көрінеді
    # (Phase 32.1 regression-ды болдырмау).
    workspace = page._measurement_workspace
    assert workspace._stack.currentWidget() is workspace._device_page
    assert workspace._start_button.isEnabled() is False


# =====================================================================
# Phase 35: Experiment Guide button + state preservation
# =====================================================================


def _sample_guide() -> ExperimentGuide:
    return ExperimentGuide(
        objective=("Мақсат.",),
        formulas=("U = I × R",),
        procedure=("Қадам 1.", "Қадам 2."),
    )


def test_guide_button_hidden_when_experiment_has_no_guide() -> None:
    page, _fake_coordinator = _make_multi_device_page(
        experiment=_make_multi_sensor_experiment_definition(guide=None)
    )

    assert page._guide_button.isHidden() is True


def test_guide_button_visible_when_experiment_has_guide() -> None:
    page, _fake_coordinator = _make_multi_device_page(
        experiment=_make_multi_sensor_experiment_definition(guide=_sample_guide())
    )

    assert page._guide_button.isHidden() is False


def test_guide_button_click_opens_dialog_with_correct_title() -> None:
    page, _fake_coordinator = _make_multi_device_page(
        experiment=_make_multi_sensor_experiment_definition(guide=_sample_guide())
    )

    page._guide_button.click()

    assert page._guide_dialog is not None
    assert "Тізбек бөлігі үшін кернеудің ток күшіне тәуелділігін зерттеу" in page._guide_dialog.windowTitle()
    assert page._guide_dialog.isVisible() is True

    page._guide_dialog.close()  # тестаралық "ілінген" диалогтарды болдырмау


def test_guide_button_click_does_nothing_when_no_guide_configured() -> None:
    page, _fake_coordinator = _make_multi_device_page(
        experiment=_make_multi_sensor_experiment_definition(guide=None)
    )

    page._on_guide_button_clicked()  # батырма жасырын болса да, тікелей шақыру

    assert page._guide_dialog is None


def test_switching_experiment_closes_stale_guide_dialog() -> None:
    page, _fake_coordinator = _make_multi_device_page(
        experiment=_make_multi_sensor_experiment_definition(guide=_sample_guide())
    )
    page._guide_button.click()
    stale_dialog = page._guide_dialog
    assert stale_dialog.isVisible() is True

    page.on_enter(_make_multi_sensor_experiment_definition(guide=None))

    assert stale_dialog.isVisible() is False
    assert page._guide_dialog is None


def test_switching_experiment_after_guide_dialog_self_closed_does_not_crash() -> None:
    """Регрессия: диалог ӨЗ "Жабу" батырмасымен (``on_enter()`` арқылы
    ЕМЕС) жабылса, ``page._guide_dialog`` ЕСКІ (енді C++ жағынан жойылған)
    данаға сілтеме ретінде "ілінбеуі" тиіс — әйтпесе кейінгі on_enter()
    "Internal C++ object already deleted" қатесімен құлайды (нақты
    қолданбада ашылған терезе жабылып, басқа тәжірибеге ауысу сценарийі).
    """
    page, _fake_coordinator = _make_multi_device_page(
        experiment=_make_multi_sensor_experiment_definition(guide=_sample_guide())
    )
    page._guide_button.click()
    page._guide_dialog._close_button.click()  # диалог ӨЗ батырмасымен жабылады
    QApplication.instance().processEvents()
    assert page._guide_dialog is None  # дереу тазаланды

    # Бұл жол бұрын RuntimeError шығаратын (ілінген сілтеме).
    page.on_enter(_make_multi_sensor_experiment_definition(guide=None))

    assert page._guide_dialog is None


def test_repeated_open_close_does_not_accumulate_dialogs() -> None:
    page, _fake_coordinator = _make_multi_device_page(
        experiment=_make_multi_sensor_experiment_definition(guide=_sample_guide())
    )

    for _ in range(3):
        page._guide_button.click()
        page._guide_dialog.close()

    # WA_DeleteOnClose deleteLater() арқылы КЕЙІНГІ event loop
    # итерацияларында жояды — нақты тексеру үшін events бірнеше рет
    # өңделуі керек (бір рет жеткіліксіз болуы мүмкін).
    app = QApplication.instance()
    for _ in range(5):
        app.processEvents()

    remaining = [
        widget
        for widget in QApplication.instance().topLevelWidgets()
        if widget.__class__.__name__ == "ExperimentGuideDialog"
    ]
    assert remaining == []


def test_guide_open_close_preserves_running_measurement_state() -> None:
    page, fake_coordinator = _make_multi_device_page(
        experiment=_make_multi_sensor_experiment_definition(guide=_sample_guide())
    )
    fake_coordinator.set_ready_for_test(True)
    fake_coordinator.readiness_changed.emit({"VOLTAGE": True, "CURRENT": True})
    page._measurement_workspace._start_button.click()
    assert fake_coordinator.is_running() is True

    page._guide_button.click()
    page._guide_dialog.close()

    assert fake_coordinator.is_running() is True
    assert fake_coordinator.stop_calls == 0


def test_guide_open_close_preserves_ab_cursor_state() -> None:
    page, _fake_coordinator = _make_multi_device_page(
        experiment=_make_multi_sensor_experiment_definition(guide=_sample_guide())
    )
    graph = page._measurement_workspace._live_graph
    graph.append_measurement(_make_measurement())
    graph._delta_button.setChecked(True)
    graph._place_delta_cursor(0.0)
    cursor_before = graph._delta_cursor_a

    page._guide_button.click()
    page._guide_dialog.close()

    assert graph._delta_cursor_a == cursor_before
    assert graph._delta_button.isChecked() is True


def test_guide_open_close_preserves_region_state() -> None:
    page, _fake_coordinator = _make_multi_device_page(
        experiment=_make_multi_sensor_experiment_definition(guide=_sample_guide())
    )
    graph = page._measurement_workspace._live_graph
    graph.append_measurement(_make_measurement())
    graph._region_button.setChecked(True)
    graph._set_all_regions((0.0, 1.0))
    region_before = graph._region_items["__single__"].getRegion()

    page._guide_button.click()
    page._guide_dialog.close()

    assert graph._region_items["__single__"].getRegion() == pytest.approx(region_before)
    assert graph._region_button.isChecked() is True
    assert graph._region_items["__single__"].isVisible() is True


def test_guide_open_close_preserves_graph_view_range() -> None:
    page, _fake_coordinator = _make_multi_device_page(
        experiment=_make_multi_sensor_experiment_definition(guide=_sample_guide())
    )
    graph = page._measurement_workspace._live_graph
    graph.append_measurement(_make_measurement())
    graph._plot_widget.setXRange(0.0, 5.0, padding=0)
    graph._plot_widget.setYRange(1.0, 9.0, padding=0)
    before_range = graph._plot_widget.getPlotItem().vb.viewRange()

    page._guide_button.click()
    page._guide_dialog.close()

    after_range = graph._plot_widget.getPlotItem().vb.viewRange()
    (before_x, before_y), (after_x, after_y) = before_range, after_range
    assert before_x == pytest.approx(after_x)
    assert before_y == pytest.approx(after_y)


# =====================================================================
# Phase 36: Laboratory Report button + state preservation
# =====================================================================


def test_report_button_hidden_when_experiment_has_no_report() -> None:
    page, _fake_coordinator = _make_multi_device_page(
        experiment=_make_multi_sensor_experiment_definition(report=None)
    )

    assert page._report_button.isHidden() is True


def test_report_button_visible_when_experiment_has_report() -> None:
    page, _fake_coordinator = _make_multi_device_page(
        experiment=_make_multi_sensor_experiment_definition(report=ExperimentReport())
    )

    assert page._report_button.isHidden() is False


def test_report_button_click_opens_dialog_with_correct_title() -> None:
    page, _fake_coordinator = _make_multi_device_page(
        experiment=_make_multi_sensor_experiment_definition(report=ExperimentReport())
    )

    page._report_button.click()

    assert page._report_dialog is not None
    assert "Тізбек бөлігі үшін кернеудің ток күшіне тәуелділігін зерттеу" in page._report_dialog.windowTitle()
    assert page._report_dialog.isVisible() is True

    page._report_dialog.close()  # тестаралық "ілінген" диалогтарды болдырмау


def test_report_button_click_does_nothing_when_no_report_configured() -> None:
    page, _fake_coordinator = _make_multi_device_page(
        experiment=_make_multi_sensor_experiment_definition(report=None)
    )

    page._on_report_button_clicked()

    assert page._report_dialog is None


def test_switching_experiment_closes_stale_report_dialog() -> None:
    page, _fake_coordinator = _make_multi_device_page(
        experiment=_make_multi_sensor_experiment_definition(report=ExperimentReport())
    )
    page._report_button.click()
    stale_dialog = page._report_dialog
    assert stale_dialog.isVisible() is True

    page.on_enter(_make_multi_sensor_experiment_definition(report=None))

    assert stale_dialog.isVisible() is False
    assert page._report_dialog is None


def test_switching_experiment_after_report_dialog_self_closed_does_not_crash() -> None:
    """Регрессия — guide-мен БІРДЕЙ (§ жоғарыдағы guide тестін қараңыз)."""
    page, _fake_coordinator = _make_multi_device_page(
        experiment=_make_multi_sensor_experiment_definition(report=ExperimentReport())
    )
    page._report_button.click()
    page._report_dialog._close_button.click()
    QApplication.instance().processEvents()
    assert page._report_dialog is None

    page.on_enter(_make_multi_sensor_experiment_definition(report=None))

    assert page._report_dialog is None


def test_repeated_report_open_close_does_not_accumulate_dialogs() -> None:
    page, _fake_coordinator = _make_multi_device_page(
        experiment=_make_multi_sensor_experiment_definition(report=ExperimentReport())
    )

    for _ in range(3):
        page._report_button.click()
        page._report_dialog.close()

    app = QApplication.instance()
    for _ in range(5):
        app.processEvents()

    remaining = [
        widget
        for widget in app.topLevelWidgets()
        if widget.__class__.__name__ == "ExperimentReportDialog"
    ]
    assert remaining == []


def test_report_shows_real_measured_statistics() -> None:
    page, fake_coordinator = _make_multi_device_page(
        experiment=_make_multi_sensor_experiment_definition(report=ExperimentReport())
    )
    # FakeCoordinator.session.experiment_id == "ohms-law" (__init__-де
    # орнатылған) — session.add_measurement() сәйкессіздікте ValueError
    # шығарады, сондықтан _make_measurement()-тің "E02"-і ЕМЕС, сәйкес
    # experiment_id қолданамыз.
    fake_coordinator.session.add_measurement(
        Measurement(
            timestamp=datetime.now(timezone.utc),
            values={"voltage": 5.024, "current": 0.218},
            experiment_id="ohms-law",
        )
    )

    page._report_button.click()

    from PySide6.QtWidgets import QLabel

    texts = "\n".join(label.text() for label in page._report_dialog.findChildren(QLabel))
    assert "N=1" in texts
    page._report_dialog.close()


def test_report_graph_section_present_when_data_plotted() -> None:
    page, _fake_coordinator = _make_multi_device_page(
        experiment=_make_multi_sensor_experiment_definition(report=ExperimentReport())
    )
    graph = page._measurement_workspace._live_graph
    graph.append_measurement(_make_measurement())

    page._report_button.click()

    from PySide6.QtWidgets import QLabel

    texts = [label.text() for label in page._report_dialog.findChildren(QLabel)]
    assert any("График" in text for text in texts)
    page._report_dialog.close()


def test_report_open_close_preserves_running_measurement_state() -> None:
    page, fake_coordinator = _make_multi_device_page(
        experiment=_make_multi_sensor_experiment_definition(report=ExperimentReport())
    )
    fake_coordinator.set_ready_for_test(True)
    fake_coordinator.readiness_changed.emit({"VOLTAGE": True, "CURRENT": True})
    page._measurement_workspace._start_button.click()
    assert fake_coordinator.is_running() is True

    page._report_button.click()
    page._report_dialog.close()

    assert fake_coordinator.is_running() is True
    assert fake_coordinator.stop_calls == 0


def test_report_open_close_preserves_ab_cursor_state() -> None:
    page, _fake_coordinator = _make_multi_device_page(
        experiment=_make_multi_sensor_experiment_definition(report=ExperimentReport())
    )
    graph = page._measurement_workspace._live_graph
    graph.append_measurement(_make_measurement())
    graph._delta_button.setChecked(True)
    graph._place_delta_cursor(0.0)
    cursor_before = graph._delta_cursor_a

    page._report_button.click()
    page._report_dialog.close()

    assert graph._delta_cursor_a == cursor_before
    assert graph._delta_button.isChecked() is True


def test_report_open_close_preserves_region_state() -> None:
    page, _fake_coordinator = _make_multi_device_page(
        experiment=_make_multi_sensor_experiment_definition(report=ExperimentReport())
    )
    graph = page._measurement_workspace._live_graph
    graph.append_measurement(_make_measurement())
    graph._region_button.setChecked(True)
    graph._set_all_regions((0.0, 1.0))
    region_before = graph._region_items["__single__"].getRegion()

    page._report_button.click()
    page._report_dialog.close()

    assert graph._region_items["__single__"].getRegion() == pytest.approx(region_before)
    assert graph._region_button.isChecked() is True
    assert graph._region_items["__single__"].isVisible() is True


def test_report_open_close_preserves_graph_view_range() -> None:
    page, _fake_coordinator = _make_multi_device_page(
        experiment=_make_multi_sensor_experiment_definition(report=ExperimentReport())
    )
    graph = page._measurement_workspace._live_graph
    graph.append_measurement(_make_measurement())
    graph._plot_widget.setXRange(0.0, 5.0, padding=0)
    graph._plot_widget.setYRange(1.0, 9.0, padding=0)
    before_range = graph._plot_widget.getPlotItem().vb.viewRange()

    page._report_button.click()
    page._report_dialog.close()

    after_range = graph._plot_widget.getPlotItem().vb.viewRange()
    (before_x, before_y), (after_x, after_y) = before_range, after_range
    assert before_x == pytest.approx(after_x)
    assert before_y == pytest.approx(after_y)


# =====================================================================
# Phase 36.1: Wiring diagram button + state preservation
# =====================================================================


def test_diagram_button_hidden_when_multi_sensor_experiment_has_no_diagram() -> None:
    page, _fake_coordinator = _make_multi_device_page(
        experiment=_make_multi_sensor_experiment_definition(diagram=None)
    )

    assert page._diagram_button.isHidden() is True


def test_diagram_button_visible_when_multi_sensor_experiment_has_diagram() -> None:
    page, _fake_coordinator = _make_multi_device_page(
        experiment=_make_multi_sensor_experiment_definition(diagram=_sample_diagram())
    )

    assert page._diagram_button.isHidden() is False


def test_diagram_open_close_preserves_running_measurement_state() -> None:
    page, fake_coordinator = _make_multi_device_page(
        experiment=_make_multi_sensor_experiment_definition(diagram=_sample_diagram())
    )
    fake_coordinator.set_ready_for_test(True)
    fake_coordinator.readiness_changed.emit({"VOLTAGE": True, "CURRENT": True})
    page._measurement_workspace._start_button.click()
    assert fake_coordinator.is_running() is True

    page._diagram_button.click()
    page._diagram_dialog.close()

    assert fake_coordinator.is_running() is True
    assert fake_coordinator.stop_calls == 0


def test_diagram_open_close_preserves_ab_cursor_state() -> None:
    page, _fake_coordinator = _make_multi_device_page(
        experiment=_make_multi_sensor_experiment_definition(diagram=_sample_diagram())
    )
    graph = page._measurement_workspace._live_graph
    graph.append_measurement(_make_measurement())
    graph._delta_button.setChecked(True)
    graph._place_delta_cursor(0.0)
    cursor_before = graph._delta_cursor_a

    page._diagram_button.click()
    page._diagram_dialog.close()

    assert graph._delta_cursor_a == cursor_before
    assert graph._delta_button.isChecked() is True


def test_diagram_open_close_preserves_region_state() -> None:
    page, _fake_coordinator = _make_multi_device_page(
        experiment=_make_multi_sensor_experiment_definition(diagram=_sample_diagram())
    )
    graph = page._measurement_workspace._live_graph
    graph.append_measurement(_make_measurement())
    graph._region_button.setChecked(True)
    graph._set_all_regions((0.0, 1.0))
    region_before = graph._region_items["__single__"].getRegion()

    page._diagram_button.click()
    page._diagram_dialog.close()

    assert graph._region_items["__single__"].getRegion() == pytest.approx(region_before)
    assert graph._region_button.isChecked() is True
    assert graph._region_items["__single__"].isVisible() is True


def test_diagram_open_close_preserves_graph_view_range() -> None:
    page, _fake_coordinator = _make_multi_device_page(
        experiment=_make_multi_sensor_experiment_definition(diagram=_sample_diagram())
    )
    graph = page._measurement_workspace._live_graph
    graph.append_measurement(_make_measurement())
    graph._plot_widget.setXRange(0.0, 5.0, padding=0)
    graph._plot_widget.setYRange(1.0, 9.0, padding=0)
    before_range = graph._plot_widget.getPlotItem().vb.viewRange()

    page._diagram_button.click()
    page._diagram_dialog.close()

    after_range = graph._plot_widget.getPlotItem().vb.viewRange()
    (before_x, before_y), (after_x, after_y) = before_range, after_range
    assert before_x == pytest.approx(after_x)
    assert before_y == pytest.approx(after_y)


# =====================================================================
# Phase 37A: role-aware connect-device flow + close_open_dialogs()
# =====================================================================


def test_default_role_is_student() -> None:
    page, _fake_coordinator = _make_multi_device_page()

    assert page._current_role is UserRole.STUDENT


def test_set_role_student_shows_connect_action() -> None:
    page, _fake_coordinator = _make_multi_device_page()
    page.set_role(UserRole.TEACHER)

    page.set_role(UserRole.STUDENT)

    assert page._measurement_workspace._connect_device_button.isHidden() is False


def test_set_role_teacher_hides_connect_action() -> None:
    page, _fake_coordinator = _make_multi_device_page()

    page.set_role(UserRole.TEACHER)

    assert page._measurement_workspace._connect_device_button.isHidden() is True


def test_on_enter_reapplies_connect_action_visibility_for_current_role() -> None:
    page, _fake_coordinator = _make_multi_device_page()
    page.set_role(UserRole.TEACHER)

    page.on_enter(_make_multi_sensor_experiment_definition())

    assert page._measurement_workspace._connect_device_button.isHidden() is True


def test_connect_device_button_click_opens_dialog_reusing_device_panel() -> None:
    page, _fake_coordinator = _make_multi_device_page()

    page._measurement_workspace._connect_device_button.click()

    assert page._connect_dialog is not None
    assert page._connect_dialog._device_panel is page._device_panel
    page._connect_dialog.close()


def test_connect_dialog_auto_closes_when_coordinator_becomes_ready() -> None:
    page, fake_coordinator = _make_multi_device_page()
    page._measurement_workspace._connect_device_button.click()
    assert page._connect_dialog is not None

    fake_coordinator.set_ready_for_test(True)
    fake_coordinator.readiness_changed.emit({"VOLTAGE": True, "CURRENT": True})

    assert page._connect_dialog is None
    assert page._device_panel.isHidden() is True


def test_connect_dialog_self_closed_then_experiment_switch_does_not_crash() -> None:
    """Guide/Report/Diagram диалогтарында табылған dangling C++ reference
    класты қатенің осы жаңа диалогта да ҚАЙТАЛАНБАУЫН тексереді.
    """
    page, _fake_coordinator = _make_multi_device_page()
    page._measurement_workspace._connect_device_button.click()
    page._connect_dialog._close_button.click()
    QApplication.instance().processEvents()
    assert page._connect_dialog is None

    # Бұл жол дангling сілтеме болса RuntimeError шығарар еді.
    page.on_enter(_make_multi_sensor_experiment_definition())

    assert page._connect_dialog is None


def test_repeated_connect_dialog_open_close_does_not_accumulate() -> None:
    page, _fake_coordinator = _make_multi_device_page()

    for _ in range(3):
        page._measurement_workspace._connect_device_button.click()
        page._connect_dialog.close()

    app = QApplication.instance()
    for _ in range(5):
        app.processEvents()

    remaining = [
        widget
        for widget in QApplication.instance().topLevelWidgets()
        if widget.__class__.__name__ == "SimplifiedDeviceConnectDialog"
    ]
    assert remaining == []


def test_teacher_role_never_shows_connect_button_even_when_requested() -> None:
    page, _fake_coordinator = _make_multi_device_page()
    page.set_role(UserRole.TEACHER)

    # Тікелей шақыру (батырма жасырын болса да) — диалог сонда да ашылады
    # (ешбір қорғаныс жоқ, себебі мұғалім бұл ағынды мүлде қолданбайды),
    # бірақ БАТЫРМА көрінбейтінін растау — нақты негізгі кепілдік.
    assert page._measurement_workspace._connect_device_button.isHidden() is True


# =====================================================================
# Phase 38A: experiment workflow progress indicator + measurement summary
# =====================================================================


def _make_summary_experiment_definition() -> ExperimentDefinition:
    """graph_y_channels="voltage" орнатылған тәжірибе — қорытынды
    карточканың қай арнаны таңдайтынын тексеру үшін.
    """
    voltage = SensorChannel(key="voltage", display_name="Кернеу", unit="V", decimals=3)
    current = SensorChannel(key="current", display_name="Ток", unit="A", decimals=3)
    return ExperimentDefinition(
        id="ohms-law",
        title="Тізбек бөлігі үшін кернеудің ток күшіне тәуелділігін зерттеу",
        description="",
        required_channels=(voltage, current),
        required_sensor_types=("VOLTAGE", "CURRENT"),
        graph_y_channels=("voltage",),
    )


def _make_summary_measurement(voltage: float, current: float = 0.2) -> Measurement:
    return Measurement(
        timestamp=datetime.now(timezone.utc),
        values={"voltage": voltage, "current": current},
        experiment_id="ohms-law",
    )


def test_guide_button_click_marks_guide_step_completed() -> None:
    page, _fake_coordinator = _make_multi_device_page(
        experiment=_make_multi_sensor_experiment_definition(guide=ExperimentGuide())
    )

    page._guide_button.click()

    assert page._workflow_indicator._guide_label.text() == "✓ Нұсқаулық"
    page._guide_dialog.close()


def test_diagram_button_click_marks_diagram_step_completed() -> None:
    page, _fake_coordinator = _make_multi_device_page(
        experiment=_make_multi_sensor_experiment_definition(
            diagram=ExperimentDiagram(image_path="dummy.png")
        )
    )

    page._diagram_button.click()

    assert page._workflow_indicator._diagram_label.text() == "✓ Схема"
    page._diagram_dialog.close()


def test_report_button_click_marks_report_step_completed() -> None:
    page, _fake_coordinator = _make_multi_device_page(
        experiment=_make_multi_sensor_experiment_definition(report=ExperimentReport())
    )

    page._report_button.click()

    assert page._workflow_indicator._report_label.text() == "✓ Есеп"
    page._report_dialog.close()


def test_on_enter_seeds_completed_for_unavailable_guide_diagram_report() -> None:
    page, _fake_coordinator = _make_multi_device_page(
        experiment=_make_multi_sensor_experiment_definition(guide=None, diagram=None, report=None)
    )

    assert page._workflow_indicator._guide_label.text() == "✓ Нұсқаулық"
    assert page._workflow_indicator._diagram_label.text() == "✓ Схема"
    assert page._workflow_indicator._report_label.text() == "✓ Есеп"


def test_readiness_changed_drives_device_step() -> None:
    page, fake_coordinator = _make_multi_device_page()

    fake_coordinator.readiness_changed.emit({"VOLTAGE": False, "CURRENT": True})
    assert page._workflow_indicator._device_label.text() == "! Құрылғы"

    fake_coordinator.set_ready_for_test(True)
    fake_coordinator.readiness_changed.emit({"VOLTAGE": True, "CURRENT": True})
    assert page._workflow_indicator._device_label.text() == "✓ Құрылғы"


def test_start_and_stop_drive_measurement_step_through_states() -> None:
    page, fake_coordinator = _make_multi_device_page()
    assert page._workflow_indicator._measurement_label.text() == "○ Өлшеу"

    fake_coordinator.set_ready_for_test(True)
    fake_coordinator.readiness_changed.emit({"VOLTAGE": True, "CURRENT": True})
    page._measurement_workspace._start_button.click()

    assert page._workflow_indicator._measurement_label.text() == "● Өлшеу"

    page._measurement_workspace._stop_button.click()

    assert page._workflow_indicator._measurement_label.text() == "✓ Өлшеу"


def test_stop_with_zero_measurements_does_not_show_summary_card() -> None:
    page, fake_coordinator = _make_multi_device_page()
    fake_coordinator.set_ready_for_test(True)
    fake_coordinator.readiness_changed.emit({"VOLTAGE": True, "CURRENT": True})
    page._measurement_workspace._start_button.click()

    page._measurement_workspace._stop_button.click()

    assert page._summary_card.isHidden()


def test_stop_with_measurements_shows_summary_card_with_reused_stats() -> None:
    page, fake_coordinator = _make_multi_device_page(
        experiment=_make_summary_experiment_definition()
    )
    fake_coordinator.set_ready_for_test(True)
    fake_coordinator.readiness_changed.emit({"VOLTAGE": True, "CURRENT": True})
    page._measurement_workspace._start_button.click()

    for voltage in (4.0, 5.0, 6.0):
        fake_coordinator.session.add_measurement(_make_summary_measurement(voltage))

    page._measurement_workspace._stop_button.click()

    assert not page._summary_card.isHidden()
    assert "3" in page._summary_card._count_label.text()
    assert "5.000 V" in page._summary_card._average_label.text()
    assert "4.000 V" in page._summary_card._minimum_label.text()
    assert "6.000 V" in page._summary_card._maximum_label.text()


def test_remeasure_button_clears_session_hides_card_and_resets_measurement_step() -> None:
    page, fake_coordinator = _make_multi_device_page(
        experiment=_make_summary_experiment_definition()
    )
    fake_coordinator.set_ready_for_test(True)
    fake_coordinator.readiness_changed.emit({"VOLTAGE": True, "CURRENT": True})
    page._measurement_workspace._start_button.click()
    fake_coordinator.session.add_measurement(_make_summary_measurement(5.0))
    page._measurement_workspace._stop_button.click()
    assert not page._summary_card.isHidden()

    page._summary_card._remeasure_button.click()

    assert fake_coordinator.clear_session_calls == 1
    assert page._summary_card.isHidden()
    assert page._workflow_indicator._measurement_label.text() == "○ Өлшеу"


def _make_summary_experiment_definition_with_report() -> ExperimentDefinition:
    voltage = SensorChannel(key="voltage", display_name="Кернеу", unit="V", decimals=3)
    current = SensorChannel(key="current", display_name="Ток", unit="A", decimals=3)
    return ExperimentDefinition(
        id="ohms-law",
        title="Тізбек бөлігі үшін кернеудің ток күшіне тәуелділігін зерттеу",
        description="",
        required_channels=(voltage, current),
        required_sensor_types=("VOLTAGE", "CURRENT"),
        graph_y_channels=("voltage",),
        report=ExperimentReport(),
    )


def test_summary_card_open_report_button_opens_existing_report_dialog() -> None:
    page, fake_coordinator = _make_multi_device_page(
        experiment=_make_summary_experiment_definition_with_report()
    )
    fake_coordinator.set_ready_for_test(True)
    fake_coordinator.readiness_changed.emit({"VOLTAGE": True, "CURRENT": True})
    page._measurement_workspace._start_button.click()
    fake_coordinator.session.add_measurement(_make_summary_measurement(5.0))
    page._measurement_workspace._stop_button.click()

    page._summary_card._open_report_button.click()

    assert page._report_dialog is not None
    page._report_dialog.close()


def test_on_enter_resets_workflow_indicator_and_hides_summary_card() -> None:
    page, fake_coordinator = _make_multi_device_page(
        experiment=_make_summary_experiment_definition()
    )
    fake_coordinator.set_ready_for_test(True)
    fake_coordinator.readiness_changed.emit({"VOLTAGE": True, "CURRENT": True})
    page._measurement_workspace._start_button.click()
    fake_coordinator.session.add_measurement(_make_summary_measurement(5.0))
    page._measurement_workspace._stop_button.click()
    assert not page._summary_card.isHidden()

    page.on_enter(_make_summary_experiment_definition())

    assert page._summary_card.isHidden()
    assert page._workflow_indicator._measurement_label.text() == "○ Өлшеу"
    assert page._workflow_indicator._device_label.text() == "! Құрылғы"


def test_teacher_role_sees_identical_workflow_bar_and_can_trigger_connect() -> None:
    page, _fake_coordinator = _make_multi_device_page()
    page.set_role(UserRole.TEACHER)

    assert page._workflow_indicator.isHidden() is False
    page._workflow_indicator._connect_device_button.click()

    assert page._connect_dialog is not None
    page._connect_dialog.close()


# =====================================================================
# Phase 39A: үш деңгейлі кері байланыс/бағалау
# =====================================================================


def _make_feedback_assessment() -> ExperimentAssessmentDefinition:
    return ExperimentAssessmentDefinition(
        level1_questions=(MultipleChoiceQuestion("l1-1", "Q?", ("A", "B"), correct_option_index=0),),
        level2_questions=(OpenResponseQuestion("l2-1", "Analyze?"),),
        level3_questions=(ReflectionQuestion("l3-1", "What did you learn?"),),
    )


_UNSET = object()


def _make_feedback_experiment_definition(assessment=_UNSET) -> ExperimentDefinition:
    """``assessment`` берілмесе (``_UNSET``), әдепкі бойынша нақты
    жарамды ``ExperimentAssessmentDefinition`` қолданылады.
    ``assessment=None`` НАҚТЫ берілсе, тәжірибеде бағалау
    конфигурацияланбаған дегенді білдіреді — екеуін шатастырмау үшін
    sentinel қолданылады (``None`` — заңды, мағыналы мән).
    """
    voltage = SensorChannel(key="voltage", display_name="Кернеу", unit="V", decimals=3)
    current = SensorChannel(key="current", display_name="Ток", unit="A", decimals=3)
    return ExperimentDefinition(
        id="ohms-law",
        title="Тізбек бөлігі үшін кернеудің ток күшіне тәуелділігін зерттеу",
        description="",
        required_channels=(voltage, current),
        required_sensor_types=("VOLTAGE", "CURRENT"),
        graph_y_channels=("voltage",),
        report=ExperimentReport(),
        assessment=_make_feedback_assessment() if assessment is _UNSET else assessment,
    )


def test_feedback_button_hidden_when_assessment_is_none() -> None:
    page, _fake_coordinator = _make_multi_device_page(
        experiment=_make_feedback_experiment_definition(assessment=None)
    )
    assert page._summary_card._start_feedback_button.isHidden() is True


def test_feedback_button_visible_when_assessment_configured() -> None:
    page, _fake_coordinator = _make_multi_device_page(
        experiment=_make_feedback_experiment_definition()
    )
    assert page._summary_card._start_feedback_button.isHidden() is False


def test_feedback_button_disabled_before_measurement_and_report() -> None:
    page, _fake_coordinator = _make_multi_device_page(
        experiment=_make_feedback_experiment_definition()
    )
    assert page._summary_card._start_feedback_button.isEnabled() is False


def test_feedback_button_stays_disabled_after_measurement_without_report() -> None:
    page, fake_coordinator = _make_multi_device_page(
        experiment=_make_feedback_experiment_definition()
    )
    fake_coordinator.set_ready_for_test(True)
    fake_coordinator.readiness_changed.emit({"VOLTAGE": True, "CURRENT": True})
    page._measurement_workspace._start_button.click()
    fake_coordinator.session.add_measurement(_make_summary_measurement(5.0))
    page._measurement_workspace._stop_button.click()

    # Report never opened yet — button must remain disabled (no fabricated completion).
    assert page._summary_card._start_feedback_button.isEnabled() is False


def test_feedback_button_enabled_after_measurement_and_report_opened() -> None:
    page, fake_coordinator = _make_multi_device_page(
        experiment=_make_feedback_experiment_definition()
    )
    fake_coordinator.set_ready_for_test(True)
    fake_coordinator.readiness_changed.emit({"VOLTAGE": True, "CURRENT": True})
    page._measurement_workspace._start_button.click()
    fake_coordinator.session.add_measurement(_make_summary_measurement(5.0))
    page._measurement_workspace._stop_button.click()
    page._report_button.click()
    page._report_dialog.close()

    assert page._summary_card._start_feedback_button.isEnabled() is True


def test_feedback_button_disabled_when_report_opened_but_zero_measurements() -> None:
    page, fake_coordinator = _make_multi_device_page(
        experiment=_make_feedback_experiment_definition()
    )
    page._report_button.click()
    page._report_dialog.close()

    assert page._summary_card._start_feedback_button.isEnabled() is False


def test_start_feedback_requested_opens_dialog_and_sets_current_state() -> None:
    page, fake_coordinator = _make_multi_device_page(
        experiment=_make_feedback_experiment_definition()
    )
    fake_coordinator.set_ready_for_test(True)
    fake_coordinator.readiness_changed.emit({"VOLTAGE": True, "CURRENT": True})
    page._measurement_workspace._start_button.click()
    fake_coordinator.session.add_measurement(_make_summary_measurement(5.0))
    page._measurement_workspace._stop_button.click()
    page._report_button.click()
    page._report_dialog.close()

    page._summary_card._start_feedback_button.click()

    assert page._feedback_dialog is not None
    assert page._workflow_indicator._feedback_label.text() == "● Кері байланыс"
    page._feedback_dialog.close()


def test_feedback_draft_saved_persists_to_repository() -> None:
    page, fake_coordinator = _make_multi_device_page(
        experiment=_make_feedback_experiment_definition()
    )
    fake_coordinator.set_ready_for_test(True)
    fake_coordinator.readiness_changed.emit({"VOLTAGE": True, "CURRENT": True})
    page._measurement_workspace._start_button.click()
    fake_coordinator.session.add_measurement(_make_summary_measurement(5.0))
    page._measurement_workspace._stop_button.click()
    page._report_button.click()
    page._report_dialog.close()
    page._summary_card._start_feedback_button.click()

    page._feedback_dialog._level2_edits["l2-1"].setPlainText("my draft analysis")
    page._feedback_dialog._on_save_draft_clicked()

    session_id = fake_coordinator.session.id
    stored = page._feedback_repository.get_result(session_id)
    assert stored is not None
    assert stored.is_draft is True
    assert stored.level2_answers[0].response_text == "my draft analysis"
    page._feedback_dialog.close()


def test_feedback_submission_persists_and_completes_workflow_step() -> None:
    page, fake_coordinator = _make_multi_device_page(
        experiment=_make_feedback_experiment_definition()
    )
    fake_coordinator.set_ready_for_test(True)
    fake_coordinator.readiness_changed.emit({"VOLTAGE": True, "CURRENT": True})
    page._measurement_workspace._start_button.click()
    fake_coordinator.session.add_measurement(_make_summary_measurement(5.0))
    page._measurement_workspace._stop_button.click()
    page._report_button.click()
    page._report_dialog.close()
    page._summary_card._start_feedback_button.click()

    dialog = page._feedback_dialog
    dialog._level1_groups["l1-1"].button(0).setChecked(True)
    dialog._level2_edits["l2-1"].setPlainText("analysis")
    dialog._level3_edits["l3-1"].setPlainText("reflection")
    dialog._self_assessment_buttons[4].setChecked(True)
    dialog._on_submit_clicked()

    session_id = fake_coordinator.session.id
    stored = page._feedback_repository.get_result(session_id)
    assert stored is not None
    assert stored.is_draft is False
    assert stored.level1_score == 1
    assert page._workflow_indicator._feedback_label.text() == "✓ Кері байланыс"
    dialog.close()


def test_re_entering_experiment_resets_feedback_step_and_button() -> None:
    page, fake_coordinator = _make_multi_device_page(
        experiment=_make_feedback_experiment_definition()
    )
    fake_coordinator.set_ready_for_test(True)
    fake_coordinator.readiness_changed.emit({"VOLTAGE": True, "CURRENT": True})
    page._measurement_workspace._start_button.click()
    fake_coordinator.session.add_measurement(_make_summary_measurement(5.0))
    page._measurement_workspace._stop_button.click()
    page._report_button.click()
    page._report_dialog.close()
    assert page._summary_card._start_feedback_button.isEnabled() is True

    page.on_enter(_make_feedback_experiment_definition())

    assert page._workflow_indicator._feedback_label.text() == "○ Кері байланыс"
    assert page._summary_card._start_feedback_button.isEnabled() is False


def test_closing_feedback_dialog_clears_reference() -> None:
    page, fake_coordinator = _make_multi_device_page(
        experiment=_make_feedback_experiment_definition()
    )
    fake_coordinator.set_ready_for_test(True)
    fake_coordinator.readiness_changed.emit({"VOLTAGE": True, "CURRENT": True})
    page._measurement_workspace._start_button.click()
    fake_coordinator.session.add_measurement(_make_summary_measurement(5.0))
    page._measurement_workspace._stop_button.click()
    page._report_button.click()
    page._report_dialog.close()
    page._summary_card._start_feedback_button.click()

    page._feedback_dialog.close()
    QApplication.instance().processEvents()

    assert page._feedback_dialog is None


def test_close_open_dialogs_closes_feedback_dialog_safely() -> None:
    page, fake_coordinator = _make_multi_device_page(
        experiment=_make_feedback_experiment_definition()
    )
    fake_coordinator.set_ready_for_test(True)
    fake_coordinator.readiness_changed.emit({"VOLTAGE": True, "CURRENT": True})
    page._measurement_workspace._start_button.click()
    fake_coordinator.session.add_measurement(_make_summary_measurement(5.0))
    page._measurement_workspace._stop_button.click()
    page._report_button.click()
    page._report_dialog.close()
    page._summary_card._start_feedback_button.click()
    assert page._feedback_dialog is not None

    page.close_open_dialogs()

    assert page._feedback_dialog is None


def test_switching_experiment_after_feedback_dialog_self_closed_does_not_crash() -> None:
    """Guide/Report/Diagram диалогтарында табылған dangling C++ reference
    қатесінің осы жаңа диалогта да қайталанбауын тексереді.
    """
    page, fake_coordinator = _make_multi_device_page(
        experiment=_make_feedback_experiment_definition()
    )
    fake_coordinator.set_ready_for_test(True)
    fake_coordinator.readiness_changed.emit({"VOLTAGE": True, "CURRENT": True})
    page._measurement_workspace._start_button.click()
    fake_coordinator.session.add_measurement(_make_summary_measurement(5.0))
    page._measurement_workspace._stop_button.click()
    page._report_button.click()
    page._report_dialog.close()
    page._summary_card._start_feedback_button.click()
    page._feedback_dialog.close()
    QApplication.instance().processEvents()
    assert page._feedback_dialog is None

    page.on_enter(_make_feedback_experiment_definition())

    assert page._feedback_dialog is None


def test_teacher_assessment_saved_persists_via_repository() -> None:
    page, fake_coordinator = _make_multi_device_page(
        experiment=_make_feedback_experiment_definition()
    )
    page.set_role(UserRole.TEACHER)
    fake_coordinator.set_ready_for_test(True)
    fake_coordinator.readiness_changed.emit({"VOLTAGE": True, "CURRENT": True})
    page._measurement_workspace._start_button.click()
    fake_coordinator.session.add_measurement(_make_summary_measurement(5.0))
    page._measurement_workspace._stop_button.click()
    page._report_button.click()
    page._report_dialog.close()
    page._summary_card._start_feedback_button.click()

    dialog = page._feedback_dialog
    dialog._teacher_score_spin.setValue(9)
    dialog._teacher_comment_edit.setPlainText("Good work")
    dialog._on_teacher_save_clicked()

    session_id = fake_coordinator.session.id
    stored = page._feedback_repository.get_result(session_id)
    assert stored is not None
    assert stored.teacher_assessment.score == 9
    assert stored.teacher_assessment.comment == "Good work"
    dialog.close()


def test_student_role_report_never_includes_teacher_assessment() -> None:
    page, fake_coordinator = _make_multi_device_page(
        experiment=_make_feedback_experiment_definition()
    )
    page.set_role(UserRole.TEACHER)
    fake_coordinator.set_ready_for_test(True)
    fake_coordinator.readiness_changed.emit({"VOLTAGE": True, "CURRENT": True})
    page._measurement_workspace._start_button.click()
    fake_coordinator.session.add_measurement(_make_summary_measurement(5.0))
    page._measurement_workspace._stop_button.click()
    page._report_button.click()
    page._report_dialog.close()
    page._summary_card._start_feedback_button.click()
    dialog = page._feedback_dialog
    dialog._teacher_score_spin.setValue(9)
    dialog._teacher_comment_edit.setPlainText("Confidential")
    dialog._on_teacher_save_clicked()
    dialog.close()

    # Switch to Student and reopen the report — teacher fields must be absent.
    page.set_role(UserRole.STUDENT)
    page._report_button.click()

    from PySide6.QtWidgets import QLabel

    texts = "\n".join(label.text() for label in page._report_dialog.findChildren(QLabel))
    assert "Confidential" not in texts
    assert "Мұғалім бағасы" not in texts
    page._report_dialog.close()


def test_teacher_role_report_includes_teacher_assessment() -> None:
    page, fake_coordinator = _make_multi_device_page(
        experiment=_make_feedback_experiment_definition()
    )
    page.set_role(UserRole.TEACHER)
    fake_coordinator.set_ready_for_test(True)
    fake_coordinator.readiness_changed.emit({"VOLTAGE": True, "CURRENT": True})
    page._measurement_workspace._start_button.click()
    fake_coordinator.session.add_measurement(_make_summary_measurement(5.0))
    page._measurement_workspace._stop_button.click()
    page._report_button.click()
    page._report_dialog.close()
    page._summary_card._start_feedback_button.click()
    dialog = page._feedback_dialog
    dialog._teacher_score_spin.setValue(9)
    dialog._teacher_comment_edit.setPlainText("Visible to teacher")
    dialog._on_teacher_save_clicked()
    dialog.close()

    page._report_button.click()

    from PySide6.QtWidgets import QLabel

    texts = "\n".join(label.text() for label in page._report_dialog.findChildren(QLabel))
    assert "Visible to teacher" in texts
    assert "Мұғалім бағасы" in texts
    page._report_dialog.close()


def test_old_report_without_assessment_configured_renders_unaffected() -> None:
    """assessment=None тәжірибе (мыс. ескі/басқа модуль) - есеп диалогы
    ЕШБІР жаңа секциясыз, дәл бұрынғыдай рендерленеді.
    """
    page, fake_coordinator = _make_multi_device_page(
        experiment=_make_feedback_experiment_definition(assessment=None)
    )
    fake_coordinator.set_ready_for_test(True)
    fake_coordinator.readiness_changed.emit({"VOLTAGE": True, "CURRENT": True})
    page._measurement_workspace._start_button.click()
    fake_coordinator.session.add_measurement(_make_summary_measurement(5.0))
    page._measurement_workspace._stop_button.click()

    page._report_button.click()

    from PySide6.QtWidgets import QLabel

    texts = "\n".join(label.text() for label in page._report_dialog.findChildren(QLabel))
    assert "1-деңгей" not in texts
    assert "Мұғалім бағасы" not in texts


# =====================================================================
# Phase 20 (Question Bank): §16 "student-side laboratory workflow
# retrieves that same updated question" — критикалық интеграция тесті.
# ExperimentWorkspacePage-тің ӨЗ (fake coordinator-мен) конструкциясы
# ЕМЕС, тікелей ``ExperimentWorkspacePage(question_repository=...)``
# арқылы — Question Bank репозиторийіндегі жазба НАҚТЫ
# ExperimentFeedbackDialog-қа жететінін дәлелдеу үшін.
# =====================================================================


def _make_question_bank_experiment() -> ExperimentDefinition:
    """Статик каталогта ӨЗ (ескі) сұрағы бар тәжірибе — Question Bank
    репозиторийі оны ауыстырғанда КӨРІНЕТІН айырмашылық болу үшін."""
    voltage = SensorChannel(key="voltage", display_name="Кернеу", unit="V", decimals=3)
    current = SensorChannel(key="current", display_name="Ток", unit="A", decimals=3)
    return ExperimentDefinition(
        id="ohms-law",
        title="Ом заңы",
        description="",
        required_channels=(voltage, current),
        required_sensor_types=("VOLTAGE", "CURRENT"),
        graph_y_channels=("voltage",),
        report=ExperimentReport(),
        assessment=ExperimentAssessmentDefinition(
            level1_questions=(
                MultipleChoiceQuestion("static-l1-1", "Ескі статик сұрақ", ("A", "B"), correct_option_index=0),
            ),
        ),
    )


def test_question_bank_edited_question_reaches_feedback_dialog() -> None:
    """Мұғалім Question Bank-та (репозиторий деңгейінде) сұрақты
    ӨЗГЕРТСЕ/ҚОССА, ExperimentWorkspacePage-тің "Кері байланысты бастау"
    диалогы ДӘЛ СОЛ жаңартылған сұрақты көрсетуі керек — ЕШБІР қосарлы
    (parallel) сақтау жоқ."""
    from datetime import datetime, timezone

    from domain.entities.question_record import QuestionRecord
    from infrastructure.storage.sqlite_question_repository import SqliteQuestionRepository

    question_repository = SqliteQuestionRepository()
    question_repository.create(
        QuestionRecord(
            id="static-l1-1", experiment_id="ohms-law", level=1,
            question=MultipleChoiceQuestion(
                "static-l1-1", "Question Bank-та жаңартылған сұрақ", ("X", "Y", "Z"), correct_option_index=2,
            ),
            is_active=True, created_at=datetime.now(timezone.utc),
        ),
        UserRole.TEACHER,
    )

    fake_coordinator = FakeCoordinator()
    page = ExperimentWorkspacePage(
        device_scanner=DeviceScanner(),
        multi_sensor_coordinator_factory=lambda _experiment: fake_coordinator,
        active_student_repository=_make_seeded_active_student_repository(),
        question_repository=question_repository,
    )
    page.on_enter(_make_question_bank_experiment())
    fake_coordinator.set_ready_for_test(True)
    fake_coordinator.readiness_changed.emit({"VOLTAGE": True, "CURRENT": True})
    page._measurement_workspace._start_button.click()
    fake_coordinator.session.add_measurement(_make_summary_measurement(5.0))
    page._measurement_workspace._stop_button.click()
    page._report_button.click()
    page._report_dialog.close()

    page._summary_card._start_feedback_button.click()

    from PySide6.QtWidgets import QLabel

    texts = "\n".join(label.text() for label in page._feedback_dialog.findChildren(QLabel))
    assert "Question Bank-та жаңартылған сұрақ" in texts
    assert "Ескі статик сұрақ" not in texts
    page._feedback_dialog.close()


def test_question_bank_empty_for_experiment_falls_back_to_static_catalog() -> None:
    """Репозиторийде БАСҚА тәжірибенің сұрағы болса да, ОСЫ тәжірибеге
    ЕШБІР әсер етпейді (§16 "editing a question does not alter unrelated
    experiments") — статик каталог fallback-і сол қалпы жұмыс істейді."""
    from datetime import datetime, timezone

    from domain.entities.question_record import QuestionRecord
    from infrastructure.storage.sqlite_question_repository import SqliteQuestionRepository

    question_repository = SqliteQuestionRepository()
    question_repository.create(
        QuestionRecord(
            id="other-l1-1", experiment_id="some-other-experiment", level=1,
            question=MultipleChoiceQuestion("other-l1-1", "Басқа тәжірибенің сұрағы", ("A", "B"), correct_option_index=0),
            is_active=True, created_at=datetime.now(timezone.utc),
        ),
        UserRole.TEACHER,
    )

    fake_coordinator = FakeCoordinator()
    page = ExperimentWorkspacePage(
        device_scanner=DeviceScanner(),
        multi_sensor_coordinator_factory=lambda _experiment: fake_coordinator,
        active_student_repository=_make_seeded_active_student_repository(),
        question_repository=question_repository,
    )
    page.on_enter(_make_question_bank_experiment())
    fake_coordinator.set_ready_for_test(True)
    fake_coordinator.readiness_changed.emit({"VOLTAGE": True, "CURRENT": True})
    page._measurement_workspace._start_button.click()
    fake_coordinator.session.add_measurement(_make_summary_measurement(5.0))
    page._measurement_workspace._stop_button.click()
    page._report_button.click()
    page._report_dialog.close()

    page._summary_card._start_feedback_button.click()

    from PySide6.QtWidgets import QLabel

    texts = "\n".join(label.text() for label in page._feedback_dialog.findChildren(QLabel))
    assert "Ескі статик сұрақ" in texts
    assert "Басқа тәжірибенің сұрағы" not in texts
    page._feedback_dialog.close()


# ---- Phase 5: Active-Experiment Near-Real-Time Sync trigger ----------------


class FakeSyncThreadController:
    """§ ``run_sync_now()``-ды НАҚТЫ QThread/желі-сіз санайтын жеңіл дублер
    — ExperimentWorkspacePage тек осы БІР әдісті шақырады, § "reuse the
    existing Phase 4 persist timer" тексеруі үшін жеткілікті."""

    def __init__(self, raise_on_call: bool = False) -> None:
        self.run_sync_now_call_count = 0
        self._raise_on_call = raise_on_call

    def run_sync_now(self) -> None:
        self.run_sync_now_call_count += 1
        if self._raise_on_call:
            raise RuntimeError("simulated sync trigger failure")


def _make_page_with_sync(tmp_path, sync_thread_controller=None, app_preferences=None):
    fake_controller = FakeExperimentController()
    db_path = str(tmp_path / "sync_trigger_test.db")
    outbox = SqliteSyncOutboxRepository(db_path)
    session_repository = SqliteSessionRepository(db_path, sync_outbox_repository=outbox)
    batch_repository = SqliteMeasurementBatchRepository(db_path, sync_outbox_repository=outbox)
    page = ExperimentWorkspacePage(
        device_scanner=DeviceScanner(),
        experiment_controller_factory=lambda _experiment: fake_controller,
        session_repository=session_repository,
        measurement_batch_repository=batch_repository,
        active_student_repository=_make_seeded_active_student_repository(),
        sync_thread_controller=sync_thread_controller,
        app_preferences=app_preferences,
    )
    page.on_enter(_make_experiment_definition())
    return page, fake_controller, session_repository, batch_repository


def test_incremental_persist_tick_triggers_sync_when_new_data_persisted(tmp_path) -> None:
    fake_sync = FakeSyncThreadController()
    page, fake_controller, _session_repo, _batch_repo = _make_page_with_sync(
        tmp_path, sync_thread_controller=fake_sync
    )
    _add_measurements(fake_controller, 5)

    page._on_incremental_persist_timer_tick()

    assert fake_sync.run_sync_now_call_count == 1


def test_incremental_persist_tick_does_not_trigger_sync_when_nothing_new(tmp_path) -> None:
    """§ "do not make the measurement acquisition loop wait for sync" —
    жаңа дерек жоқ болса, ЕШБІР сұрау жіберілмейді (§ early-return сақталады)."""
    fake_sync = FakeSyncThreadController()
    page, _fake_controller, _session_repo, _batch_repo = _make_page_with_sync(
        tmp_path, sync_thread_controller=fake_sync
    )

    page._on_incremental_persist_timer_tick()

    assert fake_sync.run_sync_now_call_count == 0


def test_incremental_persist_tick_without_sync_controller_is_safe_noop(tmp_path) -> None:
    page, fake_controller, _session_repo, _batch_repo = _make_page_with_sync(
        tmp_path, sync_thread_controller=None
    )
    _add_measurements(fake_controller, 3)

    page._on_incremental_persist_timer_tick()  # § exception шығармауы керек


def test_incremental_persist_tick_survives_sync_trigger_exception(tmp_path) -> None:
    """§ "sync must never block acquisition" — тіпті ``run_sync_now()``
    күтпеген қате шығарса да, тіркеу тоқтамайды/exception сыртқа шықпайды."""
    fake_sync = FakeSyncThreadController(raise_on_call=True)
    page, fake_controller, session_repo, _batch_repo = _make_page_with_sync(
        tmp_path, sync_thread_controller=fake_sync
    )
    _add_measurements(fake_controller, 2)

    page._on_incremental_persist_timer_tick()  # § exception шығармауы керек

    assert fake_sync.run_sync_now_call_count == 1
    assert len(session_repo.get_measurements("fake-session")) == 2  # § жазу ӨЗІ сәтті болды


def test_stop_button_triggers_sync_for_tail_batch(tmp_path) -> None:
    """§ acceptance §7 "stopping/finalizing the experiment delivers the
    tail batch" — Тоқтату батырмасы ДЕРЕУ sync-ты кезекке қояды."""
    fake_sync = FakeSyncThreadController()
    page, fake_controller, _session_repo, _batch_repo = _make_page_with_sync(
        tmp_path, sync_thread_controller=fake_sync
    )
    page._device_panel.device_selected.emit(_make_device())
    page._measurement_workspace._start_button.click()
    _add_measurements(fake_controller, 4)

    page._measurement_workspace._stop_button.click()

    assert fake_sync.run_sync_now_call_count == 1


def test_stop_button_with_zero_measurements_does_not_trigger_sync(tmp_path) -> None:
    fake_sync = FakeSyncThreadController()
    page, _fake_controller, _session_repo, _batch_repo = _make_page_with_sync(
        tmp_path, sync_thread_controller=fake_sync
    )
    page._device_panel.device_selected.emit(_make_device())
    page._measurement_workspace._start_button.click()

    page._measurement_workspace._stop_button.click()

    assert fake_sync.run_sync_now_call_count == 0


def test_active_experiment_sync_interval_is_configurable(tmp_path) -> None:
    handle_path = tmp_path / "prefs.ini"
    settings = QSettings(str(handle_path), QSettings.Format.IniFormat)
    preferences = AppPreferences(settings)
    preferences.set_active_experiment_sync_interval_seconds(3)

    page, _fake_controller, _session_repo, _batch_repo = _make_page_with_sync(
        tmp_path, app_preferences=preferences
    )

    assert page._incremental_persist_timer.interval() == 3000


def test_incremental_persist_tick_creates_full_batches_for_teacher_pull(tmp_path) -> None:
    """§ "reuse Phase 4 batching" — sync триггерінен БӨЛЕК, batch-тың ӨЗІ
    де дұрыс жиналатынын растайды (§ регрессия, Phase 4 мінез-құлқы
    Phase 5 өзгерістерінен КЕЙІН де сақталады)."""
    fake_sync = FakeSyncThreadController()
    page, fake_controller, _session_repo, batch_repo = _make_page_with_sync(
        tmp_path, sync_thread_controller=fake_sync
    )
    _add_measurements(fake_controller, 260)  # § > 250 (әдепкі chunk_size)

    page._on_incremental_persist_timer_tick()

    assert len(batch_repo.list_pending_batch_ids_for_session("fake-session")) == 1  # § 260/250 -> 1 толық batch
