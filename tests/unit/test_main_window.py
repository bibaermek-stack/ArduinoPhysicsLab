"""MainWindow — навигация shell-інің юнит-тесттері.

MainWindow енді тек Router арқылы HomePage → ExperimentListPage →
ExperimentWorkspacePage ауысуын баптайды. Құрылғы/тәжірибе логикасы
(DevicePanel, MeasurementWorkspace, ExperimentController) осы файлда
тексерілмейді — олар test_experiment_workspace_page.py-де тексеріледі.
"""

import sys
from datetime import datetime, timezone

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication, QWidget

import infrastructure.serial_comm.device_manager as device_manager_module
from domain.entities.active_student_context import ActiveStudentContext
from domain.entities.experiment_definition import ExperimentDefinition
from domain.entities.measurement import Measurement
from domain.entities.user_role import UserRole
from domain.interfaces.i_active_student_repository import IActiveStudentRepository
from domain.interfaces.i_physics_module import IPhysicsModule
from infrastructure.storage.sqlite_active_student_repository import SqliteActiveStudentRepository
from modules.electricity.experiments_config import (
    CURRENT_VOLTAGE_EXPERIMENT,
    CURRENT_WORK_POWER_EXPERIMENT,
    METAL_RESISTANCE_TEMPERATURE_EXPERIMENT,
    OHMS_LAW_EXPERIMENT,
    PARALLEL_CONNECTION_EXPERIMENT,
    SERIES_CONNECTION_EXPERIMENT,
)
from modules.electricity.module import ElectricityModule
from modules.electromagnetism.module import ElectromagnetismModule
from modules.heat.module import HeatModule
from modules.light.module import LightModule
from modules.module_registry import ModuleRegistry
from ui.main_window import MainWindow


def _make_seeded_active_student_repository() -> SqliteActiveStudentRepository:
    """Phase 39B: бұл файлдағы тестердің басым бөлігі навигация/shell
    механикасын тексереді, белсенді оқушы гейтіне қатысы жоқ — алдын ала
    таңдалған "тест оқушысы" гейтті айналып өтеді. Гейттің ӨЗІН
    тексеретін тесттер бос репозиторийді НАҚТЫ өзі қолмен береді.
    """
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


class FakeHomePage(QWidget):
    module_selected = Signal(object)
    experiment_selected = Signal(object)
    devices_requested = Signal()
    labs_requested = Signal()
    results_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.devices_action_visible_calls: list[bool] = []
        self.student_context_calls: list[tuple] = []

    def set_devices_action_visible(self, visible: bool) -> None:
        self.devices_action_visible_calls.append(visible)

    def set_student_context(
        self, student_display_name: str | None, classroom_name: str | None, summary: object
    ) -> None:
        self.student_context_calls.append((student_display_name, classroom_name, summary))


class FakeExperimentListPage(QWidget):
    experiment_selected = Signal(object)
    back_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.on_enter_calls: list[IPhysicsModule | None] = []

    def on_enter(self, module: IPhysicsModule | None = None) -> None:
        self.on_enter_calls.append(module)


class FakeExperimentWorkspacePage(QWidget):
    back_requested = Signal()
    student_selection_requested = Signal()
    measurement_running_changed = Signal(bool)
    live_sample_ready = Signal(object, str)

    def __init__(self) -> None:
        super().__init__()
        self.on_enter_calls: list[ExperimentDefinition] = []
        self.set_role_calls: list[UserRole] = []
        self.close_open_dialogs_calls = 0
        self.active_student_header_text_calls: list[str | None] = []
        self.refresh_active_student_calls = 0
        self._is_measurement_running = False

    def on_enter(self, experiment: ExperimentDefinition) -> None:
        self.on_enter_calls.append(experiment)

    def set_role(self, role: UserRole) -> None:
        self.set_role_calls.append(role)

    def close_open_dialogs(self) -> None:
        self.close_open_dialogs_calls += 1

    def set_active_student_header_text(self, text: str | None) -> None:
        self.active_student_header_text_calls.append(text)

    def refresh_active_student(self) -> None:
        self.refresh_active_student_calls += 1

    def is_measurement_running(self) -> bool:
        return self._is_measurement_running

    def current_module_accent_key(self) -> str | None:
        return None


class _FakeModule(IPhysicsModule):
    def __init__(self, name: str) -> None:
        self._name = name

    def get_name(self) -> str:
        return self._name

    def get_icon(self) -> str | None:
        return None

    def get_experiments(self) -> tuple[ExperimentDefinition, ...]:
        return ()


def _make_window(
    initial_role: UserRole = UserRole.TEACHER,
    active_student_repository: IActiveStudentRepository | None = None,
    live_stream_controller=None,
) -> tuple[MainWindow, FakeHomePage, FakeExperimentListPage, FakeExperimentWorkspacePage]:
    home_page = FakeHomePage()
    experiment_list_page = FakeExperimentListPage()
    experiment_workspace_page = FakeExperimentWorkspacePage()
    window = MainWindow(
        module_registry=ModuleRegistry(),
        initial_role=initial_role,
        home_page=home_page,
        experiment_list_page=experiment_list_page,
        experiment_workspace_page=experiment_workspace_page,
        active_student_repository=active_student_repository or _make_seeded_active_student_repository(),
        live_stream_controller=live_stream_controller,
    )
    return window, home_page, experiment_list_page, experiment_workspace_page


def test_starts_on_dashboard_placeholder_for_default_teacher_role() -> None:
    """Phase 39B: "dashboard" route ЕНДІ нақты ``TeacherDashboardPage``
    (бұрынғы generic placeholder-дің орнына)."""
    window, _home_page, _list_page, _workspace_page = _make_window()

    assert window._stack.currentWidget() is window._teacher_dashboard_page


def test_starts_on_home_page_for_student_role() -> None:
    window, home_page, _list_page, _workspace_page = _make_window(
        initial_role=UserRole.STUDENT
    )

    assert window._stack.currentWidget() is home_page


def test_module_selected_navigates_to_experiment_list() -> None:
    window, home_page, list_page, _workspace_page = _make_window()
    module = _FakeModule("Электр құбылыстары")

    home_page.module_selected.emit(module)

    assert window._stack.currentWidget() is list_page
    assert list_page.on_enter_calls == [module]


def test_experiment_list_back_navigates_to_home() -> None:
    window, home_page, list_page, _workspace_page = _make_window()
    home_page.module_selected.emit(_FakeModule("Электр құбылыстары"))

    list_page.back_requested.emit()

    assert window._stack.currentWidget() is home_page


def test_experiment_selected_navigates_to_workspace() -> None:
    window, home_page, list_page, workspace_page = _make_window()
    home_page.module_selected.emit(_FakeModule("Электр құбылыстары"))
    experiment = ExperimentDefinition(id="ohms-law", title="Тізбек бөлігі үшін кернеудің ток күшіне тәуелділігін зерттеу", description="")

    list_page.experiment_selected.emit(experiment)

    assert window._stack.currentWidget() is workspace_page
    assert workspace_page.on_enter_calls == [experiment]


def test_workspace_back_always_navigates_to_full_labs_catalog() -> None:
    # Bug fix (regression): "Тәжірибелерге оралу" ЕШҚАШАН MainWindow-дың
    # ескі/stale _current_module күйін пайдаланбауы тиіс — ол тек
    # HomePage-тен single-module drill-down жасалғанда орнатылатын, ал
    # эксперимент sidebar/Home-нің толық Labs каталогынан ашылуы мүмкін
    # (сол жағдайда _current_module МҮЛДЕ қатысы жоқ). Back әрдайым
    # толық каталогқа (module=None) апаруы керек.
    window, home_page, list_page, workspace_page = _make_window()
    stale_module = _FakeModule("Жарық құбылыстары")
    home_page.module_selected.emit(stale_module)  # _current_module ескіреді
    list_page.experiment_selected.emit(
        ExperimentDefinition(id="ohms-law", title="Тізбек бөлігі үшін кернеудің ток күшіне тәуелділігін зерттеу", description="")
    )

    workspace_page.back_requested.emit()

    assert window._stack.currentWidget() is list_page
    assert list_page.on_enter_calls == [stale_module, None]


def test_settings_button_navigates_to_settings_page() -> None:
    window, _home_page, _list_page, _workspace_page = _make_window()

    window._settings_button.click()

    assert window._stack.currentWidget() is window._settings_page


def test_settings_page_has_no_back_button() -> None:
    from PySide6.QtWidgets import QPushButton

    window, _home_page, _list_page, _workspace_page = _make_window()

    assert not hasattr(window._settings_page, "back_requested")
    assert all(
        button.text() != "← Артқа"
        for button in window._settings_page.findChildren(QPushButton)
    )


def test_about_button_navigates_to_about_page() -> None:
    window, _home_page, _list_page, _workspace_page = _make_window()

    window._about_button.click()

    assert window._stack.currentWidget() is window._about_page


def test_about_page_has_no_back_button() -> None:
    from PySide6.QtWidgets import QPushButton

    window, _home_page, _list_page, _workspace_page = _make_window()

    assert not hasattr(window._about_page, "back_requested")
    assert all(
        button.text() != "← Артқа"
        for button in window._about_page.findChildren(QPushButton)
    )


def test_sidebar_is_global_navigation_shell() -> None:
    from ui.widgets.sidebar import Sidebar

    window, _home_page, _list_page, _workspace_page = _make_window()

    assert isinstance(window._sidebar, Sidebar)
    assert window._settings_button is window._sidebar.buttons["settings"]
    assert window._about_button is window._sidebar.buttons["help"]


def test_sidebar_home_button_navigates_to_home() -> None:
    window, home_page, list_page, _workspace_page = _make_window(
        initial_role=UserRole.STUDENT
    )
    home_page.module_selected.emit(_FakeModule("Электр құбылыстары"))
    list_page.experiment_selected.emit(
        ExperimentDefinition(id="ohms-law", title="Тізбек бөлігі үшін кернеудің ток күшіне тәуелділігін зерттеу", description="")
    )

    window._sidebar.buttons["home"].click()

    assert window._stack.currentWidget() is home_page


def test_sidebar_collapse_shrinks_width_and_expands_content_area() -> None:
    window, _home_page, _list_page, _workspace_page = _make_window()
    expanded_width = window._sidebar.width()

    window._sidebar.collapse_button.click()

    assert window._sidebar.width() < expanded_width


def test_devices_route_registered_and_reachable_via_sidebar() -> None:
    from ui.pages.devices_page import DevicesPage

    window, _home_page, _list_page, _workspace_page = _make_window()

    assert isinstance(window._devices_page, DevicesPage)

    window._sidebar.buttons["devices"].click()

    assert window._stack.currentWidget() is window._devices_page


def test_data_journal_route_registered_and_reachable_via_sidebar() -> None:
    from ui.pages.data_journal_page import DataJournalPage

    window, _home_page, _list_page, _workspace_page = _make_window()

    assert isinstance(window._data_journal_page, DataJournalPage)

    window._sidebar.buttons["data_log"].click()

    assert window._stack.currentWidget() is window._data_journal_page


def test_data_journal_page_shares_session_repository_with_workspace() -> None:
    window = MainWindow(module_registry=ModuleRegistry())

    assert window._data_journal_page._session_repository is window.session_repository
    assert window._experiment_workspace_page._session_repository is window.session_repository


def test_labs_sidebar_button_navigates_to_experiment_list_catalog() -> None:
    window, _home_page, list_page, _workspace_page = _make_window()

    window._sidebar.buttons["labs"].click()

    assert window._stack.currentWidget() is list_page


def test_labs_sidebar_navigation_does_not_touch_device_manager(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Sidebar арқылы "Зертханалық жұмыстар" каталогына ауысу
    # DeviceManager-ге ЕШБІР қатысы жоқ болуы тиіс (persistence
    # architecture, [[project-arduino-physics-lab]] кезең 16).
    window, _home_page, _list_page, _workspace_page = _make_window(
        initial_role=UserRole.STUDENT
    )
    shutdown_calls = []
    monkeypatch.setattr(
        window.device_manager, "shutdown_all", lambda: shutdown_calls.append(1)
    )

    window._sidebar.buttons["labs"].click()
    window._sidebar.buttons["home"].click()

    assert shutdown_calls == []


# ---- Home Dashboard V2 wiring ----------------------------------------------


def test_home_page_receives_shared_device_manager() -> None:
    from ui.pages.home_page import HomePage

    window = MainWindow(module_registry=ModuleRegistry())

    assert isinstance(window._home_page, HomePage)
    assert window._home_page._device_manager is window.device_manager


def test_home_devices_requested_navigates_to_devices_page() -> None:
    window, home_page, _list_page, _workspace_page = _make_window()

    home_page.devices_requested.emit()

    assert window._stack.currentWidget() is window._devices_page


def test_home_labs_requested_navigates_to_experiment_list_catalog() -> None:
    window, home_page, list_page, _workspace_page = _make_window()

    home_page.labs_requested.emit()

    assert window._stack.currentWidget() is list_page


def test_home_experiment_selected_navigates_to_workspace() -> None:
    window, home_page, _list_page, workspace_page = _make_window()
    experiment = ExperimentDefinition(id="ohms-law", title="Тізбек бөлігі үшін кернеудің ток күшіне тәуелділігін зерттеу", description="")

    home_page.experiment_selected.emit(experiment)

    assert window._stack.currentWidget() is workspace_page
    assert workspace_page.on_enter_calls == [experiment]


# ---- Labs navigation bug fix: real MainWindow end-to-end regression -------
#
# FakeExperimentListPage/FakeExperimentWorkspacePage жоғарыдағы тесттерде
# жеткілікті (MainWindow-дың route wiring-ін тексереді), бірақ бұл бөлім
# НАҚТЫ ExperimentListPage/ExperimentWorkspacePage/DeviceManager-мен
# толық сценарийді тексереді — дәл хабарланған bug (#12-ге қате Back)
# осы нақты компоненттердің өзара әрекеттесуінен туындаған.

_VOLTAGE_HELLO = "TYPE=HELLO,DEV=APL-VOLTAGE-01,MODEL=V1,SENSOR=VOLTAGE,CHIP=INA226,FW=1.0"


class _FakeSerialThreadController(QObject):
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


def _make_real_window() -> MainWindow:
    registry = ModuleRegistry()
    registry.register(HeatModule())
    registry.register(ElectricityModule())
    registry.register(ElectromagnetismModule())
    registry.register(LightModule())
    return MainWindow(module_registry=registry)


def _open_full_labs_catalog(window: MainWindow) -> None:
    window._sidebar.buttons["labs"].click()
    assert window._experiment_list_page._showing_all is True


def _open_experiment_from_catalog(window: MainWindow, experiment: ExperimentDefinition) -> None:
    window._experiment_list_page.experiment_selected.emit(experiment)


def _click_workspace_back(window: MainWindow) -> None:
    window._experiment_workspace_page._on_back_clicked()


@pytest.mark.parametrize(
    "experiment",
    [
        CURRENT_VOLTAGE_EXPERIMENT,
        SERIES_CONNECTION_EXPERIMENT,
        PARALLEL_CONNECTION_EXPERIMENT,
        CURRENT_WORK_POWER_EXPERIMENT,
        OHMS_LAW_EXPERIMENT,
        METAL_RESISTANCE_TEMPERATURE_EXPERIMENT,
    ],
    ids=lambda e: e.id,
)
def test_back_from_any_implemented_experiment_returns_to_full_catalog(
    experiment: ExperimentDefinition,
) -> None:
    window = _make_real_window()
    _open_full_labs_catalog(window)

    _open_experiment_from_catalog(window, experiment)
    assert window._stack.currentWidget() is window._experiment_workspace_page

    _click_workspace_back(window)

    assert window._stack.currentWidget() is window._experiment_list_page
    assert window._experiment_list_page._showing_all is True
    assert window._experiment_list_page._module is None


def test_back_never_lands_on_experiment_twelve() -> None:
    window = _make_real_window()
    _open_full_labs_catalog(window)

    _open_experiment_from_catalog(window, OHMS_LAW_EXPERIMENT)
    _click_workspace_back(window)

    # #12 ешқашан ExperimentWorkspacePage-ке ашылмауы, тек Labs каталогы
    # көрінуі тиіс (жеке "Жарық құбылыстары" single-module беті ЕМЕС).
    assert window._stack.currentWidget() is window._experiment_list_page
    assert window._experiment_list_page._title_label.text() == "Зертханалық жұмыстар"


def test_back_emits_no_experiment_selected_signal() -> None:
    window = _make_real_window()
    _open_full_labs_catalog(window)
    _open_experiment_from_catalog(window, OHMS_LAW_EXPERIMENT)

    selected: list[ExperimentDefinition] = []
    window._experiment_list_page.experiment_selected.connect(selected.append)

    _click_workspace_back(window)

    assert selected == []


def test_device_manager_instance_unchanged_across_labs_experiment_back() -> None:
    window = _make_real_window()
    manager_before = window.device_manager

    _open_full_labs_catalog(window)
    _open_experiment_from_catalog(window, OHMS_LAW_EXPERIMENT)
    _click_workspace_back(window)

    assert window.device_manager is manager_before


def test_sensor_connection_remains_registered_across_labs_experiment_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fakes_by_port: dict[str, _FakeSerialThreadController] = {}

    class _PendingFake(_FakeSerialThreadController):
        def connect_port(self, port_name: str, baud_rate: int) -> None:
            fakes_by_port[port_name] = self
            super().connect_port(port_name, baud_rate)

    monkeypatch.setattr(
        device_manager_module, "SerialThreadController", lambda *a, **k: _PendingFake()
    )

    window = _make_real_window()
    window.device_manager.identify("COM6", 115200)
    fakes_by_port["COM6"].line_received.emit(_VOLTAGE_HELLO)
    assert window.device_manager.is_port_connected("COM6") is True

    _open_full_labs_catalog(window)
    _open_experiment_from_catalog(window, OHMS_LAW_EXPERIMENT)
    _click_workspace_back(window)

    assert window.device_manager.is_port_connected("COM6") is True
    assert fakes_by_port["COM6"].stop_calls == 0


def test_sidebar_labs_stays_active_after_back() -> None:
    window = _make_real_window()
    _open_full_labs_catalog(window)
    assert window._sidebar.buttons["labs"].isChecked() is True

    _open_experiment_from_catalog(window, OHMS_LAW_EXPERIMENT)
    _click_workspace_back(window)

    assert window._sidebar.buttons["labs"].isChecked() is True


def test_switch_role_button_navigates_to_role_selection_page() -> None:
    window, _home_page, _list_page, _workspace_page = _make_window()

    window._sidebar._switch_role_button.click()

    assert window._stack.currentWidget() is window._role_selection_page


def test_selecting_student_from_role_selection_updates_role_and_navigates_home() -> None:
    window, home_page, _list_page, _workspace_page = _make_window()  # default TEACHER

    window._role_selection_page.role_selected.emit(UserRole.STUDENT)

    assert window._current_role is UserRole.STUDENT
    assert window._stack.currentWidget() is home_page


def test_selecting_teacher_from_role_selection_updates_role_and_navigates_dashboard() -> None:
    window, _home_page, _list_page, _workspace_page = _make_window(
        initial_role=UserRole.STUDENT
    )

    window._role_selection_page.role_selected.emit(UserRole.TEACHER)

    assert window._current_role is UserRole.TEACHER
    assert window._stack.currentWidget() is window._teacher_dashboard_page


def test_role_switch_rebuilds_sidebar_button_set() -> None:
    window, _home_page, _list_page, _workspace_page = _make_window(
        initial_role=UserRole.STUDENT
    )
    assert "home" in window._sidebar.buttons
    assert "devices" not in window._sidebar.buttons

    window._role_selection_page.role_selected.emit(UserRole.TEACHER)

    assert "home" not in window._sidebar.buttons
    assert "devices" in window._sidebar.buttons


def test_role_switch_closes_open_workspace_dialogs() -> None:
    window, _home_page, _list_page, workspace_page = _make_window()
    assert workspace_page.close_open_dialogs_calls == 0

    window._role_selection_page.role_selected.emit(UserRole.STUDENT)

    assert workspace_page.close_open_dialogs_calls == 1


def test_role_switch_calls_set_role_on_workspace_page() -> None:
    window, _home_page, _list_page, workspace_page = _make_window()

    window._role_selection_page.role_selected.emit(UserRole.STUDENT)

    assert UserRole.STUDENT in workspace_page.set_role_calls


def test_role_switch_never_recreates_main_window_or_shared_pages() -> None:
    window, home_page, list_page, workspace_page = _make_window()

    window._role_selection_page.role_selected.emit(UserRole.STUDENT)

    assert window._home_page is home_page
    assert window._experiment_list_page is list_page
    assert window._experiment_workspace_page is workspace_page


def test_role_switch_never_recreates_device_manager_or_session_repository() -> None:
    window, _home_page, _list_page, _workspace_page = _make_window()
    device_manager = window.device_manager
    session_repository = window.session_repository

    window._role_selection_page.role_selected.emit(UserRole.STUDENT)

    assert window.device_manager is device_manager
    assert window.session_repository is session_repository


def test_forbidden_direct_router_navigate_rejected_for_student() -> None:
    window, _home_page, _list_page, _workspace_page = _make_window(
        initial_role=UserRole.STUDENT
    )
    current_before = window._stack.currentWidget()

    result = window._router.navigate("devices")

    assert result is False
    assert window._stack.currentWidget() is current_before


def test_teacher_can_navigate_directly_to_any_registered_route() -> None:
    window, _home_page, _list_page, _workspace_page = _make_window()  # TEACHER

    result = window._router.navigate("devices")

    assert result is True
    assert window._stack.currentWidget() is window._devices_page


def test_home_page_devices_action_hidden_for_default_student_construction() -> None:
    window, home_page, _list_page, _workspace_page = _make_window(
        initial_role=UserRole.STUDENT
    )

    assert home_page.devices_action_visible_calls[-1] is False


def test_home_page_devices_action_visible_for_teacher_construction() -> None:
    window, home_page, _list_page, _workspace_page = _make_window()  # TEACHER

    assert home_page.devices_action_visible_calls[-1] is True


def test_home_page_devices_action_updates_on_role_switch() -> None:
    window, home_page, _list_page, _workspace_page = _make_window()  # TEACHER

    window._role_selection_page.role_selected.emit(UserRole.STUDENT)

    assert home_page.devices_action_visible_calls[-1] is False


def test_role_indicator_updates_after_switch() -> None:
    window, _home_page, _list_page, _workspace_page = _make_window(
        initial_role=UserRole.STUDENT
    )
    assert window._sidebar._role_indicator_label.text() == "Оқушы режимі"

    window._role_selection_page.role_selected.emit(UserRole.TEACHER)

    assert window._sidebar._role_indicator_label.text() == "Мұғалім режимі"


def test_repeated_labs_experiment_back_cycles_never_go_stale() -> None:
    window = _make_real_window()
    _open_full_labs_catalog(window)

    for experiment in (
        CURRENT_VOLTAGE_EXPERIMENT,
        OHMS_LAW_EXPERIMENT,
        SERIES_CONNECTION_EXPERIMENT,
    ):
        _open_experiment_from_catalog(window, experiment)
        assert window._stack.currentWidget() is window._experiment_workspace_page

        _click_workspace_back(window)
        assert window._stack.currentWidget() is window._experiment_list_page


# =====================================================================
# Phase 41: QSplitter (Sidebar/жұмыс кеңістігі) + WorkspaceBackdrop
# =====================================================================


def test_sidebar_and_workspace_are_children_of_splitter() -> None:
    window, _home_page, _list_page, _workspace_page = _make_window()

    assert window._splitter.indexOf(window._sidebar) != -1
    assert window._splitter.indexOf(window._workspace_backdrop) != -1


def test_sidebar_minimum_width_is_practical() -> None:
    window, _home_page, _list_page, _workspace_page = _make_window()

    assert 200 <= window._sidebar.minimumWidth() <= 220


def test_splitter_children_not_collapsible_by_drag() -> None:
    window, _home_page, _list_page, _workspace_page = _make_window()

    assert window._splitter.childrenCollapsible() is False


def test_workspace_backdrop_never_collapses_to_zero() -> None:
    window, _home_page, _list_page, _workspace_page = _make_window()

    window._splitter.resize(1200, 800)
    window._splitter.setSizes([1, 999999])  # аса кіші сидебар мәнін мәжбүрлеп көру

    sizes = window._splitter.sizes()
    assert sizes[1] > 0


def test_resizing_splitter_preserves_current_page() -> None:
    window, home_page, _list_page, _workspace_page = _make_window()
    window._sidebar.buttons["devices"].click()
    assert window._stack.currentWidget() is window._devices_page

    window._splitter.resize(1600, 900)
    window._splitter.setSizes([300, 1300])

    assert window._stack.currentWidget() is window._devices_page


def test_resizing_splitter_does_not_recreate_main_window_or_pages() -> None:
    window, home_page, list_page, workspace_page = _make_window()
    home_id, list_id, workspace_id, window_id = id(home_page), id(list_page), id(workspace_page), id(window)

    window._splitter.resize(1600, 900)
    window._splitter.setSizes([300, 1300])
    window._splitter.setSizes([230, 1370])

    assert id(window) == window_id
    assert id(window._home_page) == home_id
    assert id(window._experiment_list_page) == list_id
    assert id(window._experiment_workspace_page) == workspace_id


def test_collapse_still_shrinks_splitter_sidebar_pane() -> None:
    window, _home_page, _list_page, _workspace_page = _make_window()
    expanded_size = window._splitter.sizes()[0]

    window._sidebar.collapse_button.click()

    assert window._splitter.sizes()[0] < expanded_size


def test_role_switch_still_works_after_splitter_present() -> None:
    window, _home_page, _list_page, _workspace_page = _make_window()  # TEACHER

    window._role_selection_page.role_selected.emit(UserRole.STUDENT)

    assert window._current_role is UserRole.STUDENT
    assert window._sidebar.role() is UserRole.STUDENT


def test_active_student_remains_selected_across_splitter_resize() -> None:
    active_repository = _make_seeded_active_student_repository()
    window, _home_page, _list_page, _workspace_page = _make_window(
        initial_role=UserRole.STUDENT, active_student_repository=active_repository
    )

    window._splitter.resize(1400, 800)
    window._splitter.setSizes([260, 1140])

    assert active_repository.get() is not None
    assert active_repository.get().student_id == "test-student"


def test_navigation_remains_functional_after_drag() -> None:
    window, home_page, _list_page, _workspace_page = _make_window()
    window._splitter.setSizes([300, 1300])

    window._sidebar.buttons["devices"].click()

    assert window._stack.currentWidget() is window._devices_page


# ---- route -> WorkspaceBackdrop секциясы ---------------------------------


def test_workspace_backdrop_updates_on_route_change() -> None:
    window, _home_page, _list_page, _workspace_page = _make_window(
        initial_role=UserRole.STUDENT
    )

    window._sidebar.buttons["home"].click()
    assert window._workspace_backdrop.current_category() == "home"

    window._router.navigate("about")
    assert window._workspace_backdrop.current_category() == "help"


def test_workspace_backdrop_teacher_routes() -> None:
    window, _home_page, _list_page, _workspace_page = _make_window()  # TEACHER

    window._sidebar.buttons["dashboard"].click()
    assert window._workspace_backdrop.current_category() == "home"

    window._sidebar.buttons["devices"].click()
    assert window._workspace_backdrop.current_category() == "devices"

    window._sidebar.buttons["data_log"].click()
    assert window._workspace_backdrop.current_category() == "results"

    window._sidebar.buttons["feedback_teacher"].click()
    assert window._workspace_backdrop.current_category() == "feedback"


def test_workspace_backdrop_unknown_route_falls_back_to_default() -> None:
    window, _home_page, _list_page, _workspace_page = _make_window()

    window._router.navigate("settings")

    assert window._workspace_backdrop.current_category() == "default"


def test_workspace_backdrop_experiment_workspace_uses_owning_module_category() -> None:
    window = _make_real_window()
    _open_full_labs_catalog(window)

    _open_experiment_from_catalog(window, OHMS_LAW_EXPERIMENT)

    assert window._workspace_backdrop.current_category() == "electricity"


# ---- Phase 41: feedback_student route -> StudentFeedbackPage -------------


def test_feedback_student_route_registered_to_student_feedback_page() -> None:
    window, _home_page, _list_page, _workspace_page = _make_window(
        initial_role=UserRole.STUDENT
    )

    window._router.navigate("feedback_student")

    assert window._stack.currentWidget() is window._student_feedback_page


def test_feedback_student_not_in_teacher_sidebar() -> None:
    """``feedback_student`` — Оқушы-тек nav item (§ navigation_config
    ``_STUDENT``). Router guard-ы ``TEACHER``-ге ЕШБІР route-ты ЕШҚАШАН
    шектемейді (§ "TEACHER — үлкейтілген рөл"), сондықтан НАҚТЫ қорғаныс
    осы жерде — sidebar-да батырма мүлде жоқ.
    """
    window, _home_page, _list_page, _workspace_page = _make_window()  # TEACHER

    assert "feedback_student" not in window._sidebar.buttons


# =====================================================================
# Phase 16 ("Results Page implementation"): "results" route ЕНДІ НАҚТЫ
# ``ResultsPage`` (бұрынғы ``PlaceholderPage``-дің орнына). Analytics/
# Question Bank ӘЛІ ДЕ placeholder күйінде қалуы, sidebar/su таңба
# геометриясы ӨЗГЕРІССІЗ болуы керек (§ "DO NOT TOUCH" тізімі).
# =====================================================================


def test_results_route_registered_to_results_page() -> None:
    from ui.pages.results_page import ResultsPage

    window, _home_page, _list_page, _workspace_page = _make_window()

    window._router.navigate("results")

    assert isinstance(window._results_page, ResultsPage)
    assert window._stack.currentWidget() is window._results_page


def test_results_sidebar_button_navigates_to_results_page() -> None:
    window, _home_page, _list_page, _workspace_page = _make_window()  # TEACHER

    window._sidebar.buttons["results"].click()

    assert window._stack.currentWidget() is window._results_page
    assert window._workspace_backdrop.current_category() == "results"


def test_results_page_no_longer_in_placeholder_pages() -> None:
    window, _home_page, _list_page, _workspace_page = _make_window()

    assert "results" not in window._placeholder_pages


def test_no_placeholder_pages_remain() -> None:
    """Phase 20: соңғы placeholder route ("question_bank") НАҚТЫ бетпен
    ауыстырылды — ``_placeholder_pages`` енді толығымен бос."""
    window, _home_page, _list_page, _workspace_page = _make_window()

    assert window._placeholder_pages == {}


def test_question_bank_route_registered_to_question_bank_page() -> None:
    """Phase 20: "question_bank" route ЕНДІ нақты ``QuestionBankPage``
    (бұрынғы ``PlaceholderPage``-дің орнына, § Results/Analytics-пен
    БІРДЕЙ үлгі)."""
    from ui.pages.question_bank_page import QuestionBankPage

    window, _home_page, _list_page, _workspace_page = _make_window()

    window._router.navigate("question_bank")

    assert isinstance(window._question_bank_page, QuestionBankPage)
    assert window._stack.currentWidget() is window._question_bank_page


def test_question_bank_sidebar_button_navigates_to_question_bank_page() -> None:
    window, _home_page, _list_page, _workspace_page = _make_window()  # TEACHER

    window._sidebar.buttons["question_bank"].click()

    assert window._stack.currentWidget() is window._question_bank_page
    assert window._workspace_backdrop.current_category() == "default"


def test_question_bank_page_has_no_back_button() -> None:
    """§2 "Remove the Back button completely" — Question Bank бірінші
    деңгейлі sidebar тағайыны, PlaceholderPage-тің "← Артқа" батырмасы
    ЖОҚ."""
    from PySide6.QtWidgets import QPushButton

    window, _home_page, _list_page, _workspace_page = _make_window()

    back_buttons = [
        b for b in window._question_bank_page.findChildren(QPushButton) if b.text() == "← Артқа"
    ]
    assert back_buttons == []


def test_analytics_route_registered_to_analytics_page() -> None:
    """Phase 19: "analytics" route ЕНДІ нақты ``AnalyticsPage`` (бұрынғы
    ``PlaceholderPage``-дің орнына, § Results-пен БІРДЕЙ Phase 16
    үлгісі)."""
    from ui.pages.analytics_page import AnalyticsPage

    window, _home_page, _list_page, _workspace_page = _make_window()

    window._router.navigate("analytics")

    assert isinstance(window._analytics_page, AnalyticsPage)
    assert window._stack.currentWidget() is window._analytics_page


def test_analytics_sidebar_button_navigates_to_analytics_page() -> None:
    window, _home_page, _list_page, _workspace_page = _make_window()  # TEACHER

    window._sidebar.buttons["analytics"].click()

    assert window._stack.currentWidget() is window._analytics_page
    assert window._workspace_backdrop.current_category() == "analytics"


def test_analytics_page_no_longer_in_placeholder_pages() -> None:
    window, _home_page, _list_page, _workspace_page = _make_window()

    assert "analytics" not in window._placeholder_pages


def test_analytics_page_has_no_back_button() -> None:
    """§2 "Remove the Back button completely" — Analytics бірінші деңгейлі
    sidebar тағайыны, PlaceholderPage-тің "← Артқа" батырмасы ЖОҚ."""
    from PySide6.QtWidgets import QPushButton

    window, _home_page, _list_page, _workspace_page = _make_window()

    back_buttons = [
        b for b in window._analytics_page.findChildren(QPushButton) if b.text() == "← Артқа"
    ]
    assert back_buttons == []


# =====================================================================
# Phase 8: analytics/dashboard → student_monitoring навигациясы
# =====================================================================


def test_analytics_student_monitoring_requested_navigates_with_params() -> None:
    """§ Phase 8 Architecture Decision #6 — ``classroom_monitoring_page.
    student_selected``-пен БІРДЕЙ пішін/мақсат route."""
    window, _home_page, _list_page, _workspace_page = _make_window()

    window._analytics_page.student_monitoring_requested.emit("s1", "ohms-law")

    assert window._stack.currentWidget() is window._student_monitoring_page
    assert window._student_monitoring_page._current_student_id == "s1"
    assert window._student_monitoring_page._current_experiment_id == "ohms-law"


def test_dashboard_student_monitoring_requested_navigates_with_params() -> None:
    window, _home_page, _list_page, _workspace_page = _make_window()

    window._teacher_dashboard_page.student_monitoring_requested.emit("s2", "current-voltage")

    assert window._stack.currentWidget() is window._student_monitoring_page
    assert window._student_monitoring_page._current_student_id == "s2"
    assert window._student_monitoring_page._current_experiment_id == "current-voltage"


def test_sidebar_width_unchanged_after_results_page_swap() -> None:
    window, _home_page, _list_page, _workspace_page = _make_window()
    window.resize(1366, 768)
    window.show()
    window._router.navigate("results")

    assert window._sidebar.width() == 230


# =====================================================================
# Mode Switch + Student Access Screen Redesign: sidebar hide/show
# =====================================================================


def test_switch_role_navigation_hides_sidebar() -> None:
    window, _home_page, _list_page, _workspace_page = _make_window()

    window._sidebar._switch_role_button.click()

    assert window._sidebar.isHidden()


def test_switch_student_action_stays_on_home_without_code_form() -> None:
    window, home_page, _list_page, _workspace_page = _make_window(
        initial_role=UserRole.STUDENT
    )

    window._sidebar.switch_student_requested.emit()

    assert window._stack.currentWidget() is home_page
    assert not window._role_selection_page._student_login_view.isVisibleTo(
        window._role_selection_page
    )
    assert not window._sidebar.isHidden()


def test_selecting_teacher_from_role_selection_restores_teacher_sidebar() -> None:
    window, _home_page, _list_page, _workspace_page = _make_window(
        initial_role=UserRole.STUDENT
    )
    window._sidebar._switch_role_button.click()
    assert window._sidebar.isHidden()

    window._role_selection_page.role_selected.emit(UserRole.TEACHER)

    assert not window._sidebar.isHidden()
    assert window._sidebar.role() is UserRole.TEACHER


def test_student_login_succeeded_restores_student_sidebar() -> None:
    window, _home_page, _list_page, _workspace_page = _make_window()  # TEACHER
    window._sidebar._switch_role_button.click()
    assert window._sidebar.isHidden()

    window._role_selection_page.student_login_succeeded.connect(lambda: None)
    window.active_student_repository.set(
        ActiveStudentContext(classroom_id="c1", student_id="s1")
    )
    window._role_selection_page.student_login_succeeded.emit()

    assert not window._sidebar.isHidden()
    assert window._sidebar.role() is UserRole.STUDENT


def test_student_login_succeeded_routes_to_student_home() -> None:
    window, home_page, _list_page, _workspace_page = _make_window()  # TEACHER
    window.active_student_repository.set(
        ActiveStudentContext(classroom_id="c1", student_id="s1")
    )

    window._role_selection_page.student_login_succeeded.emit()

    assert window._stack.currentWidget() is home_page


def test_student_login_succeeded_while_already_student_only_refreshes() -> None:
    active_repository = _make_seeded_active_student_repository()
    window, home_page, _list_page, workspace_page = _make_window(
        initial_role=UserRole.STUDENT, active_student_repository=active_repository
    )
    assert window._stack.currentWidget() is home_page

    window._role_selection_page.student_login_succeeded.emit()

    assert workspace_page.refresh_active_student_calls == 1
    assert window._stack.currentWidget() is home_page


def test_sidebar_width_unchanged_after_returning_from_entry_screen() -> None:
    window, _home_page, _list_page, _workspace_page = _make_window()
    window.resize(1366, 768)
    window.show()
    expected_width = window._sidebar.width()

    window._sidebar._switch_role_button.click()
    window._role_selection_page.role_selected.emit(UserRole.TEACHER)

    assert window._sidebar.width() == expected_width


def test_old_student_selection_route_no_longer_registered() -> None:
    window, _home_page, _list_page, _workspace_page = _make_window()

    assert "student_selection" not in window._router._pages
    assert not hasattr(window, "_student_selection_page")


def test_open_student_login_helper_stays_on_home_without_code_form() -> None:
    window, home_page, _list_page, workspace_page = _make_window(
        initial_role=UserRole.STUDENT
    )

    workspace_page.student_selection_requested.emit()

    assert window._stack.currentWidget() is home_page
    assert not window._role_selection_page._student_login_view.isVisibleTo(
        window._role_selection_page
    )


# ---- Phase 5: Connectivity-Aware Automatic Sync UI wiring ------------------


class FakeSyncThreadController(QObject):
    """§ ``SyncThreadController``-дің НАҚТЫ QThread/желі-сіз дублері —
    тек сигнал үлгісі (§ ``.connect()`` НАҚТЫ Qt Signal талап етеді)."""

    sync_started = Signal()
    sync_finished = Signal(str, int, int, str, int)
    error_occurred = Signal(str)
    connectivity_changed = Signal(bool, int)

    def __init__(self) -> None:
        super().__init__()
        self.run_sync_now_calls = 0

    def run_sync_now(self) -> None:
        self.run_sync_now_calls += 1


class FakeDashboardPage(QWidget):
    classes_requested = Signal()
    labs_requested = Signal()
    devices_requested = Signal()
    results_requested = Signal()
    classroom_monitoring_requested = Signal()
    student_monitoring_requested = Signal(str, str)

    def __init__(self) -> None:
        super().__init__()
        self.on_enter_calls = 0

    def on_enter(self) -> None:
        self.on_enter_calls += 1


def _make_window_with_sync(
    initial_role: UserRole = UserRole.TEACHER,
) -> tuple[MainWindow, FakeSyncThreadController, FakeDashboardPage]:
    sync_thread_controller = FakeSyncThreadController()
    dashboard_page = FakeDashboardPage()
    window = MainWindow(
        module_registry=ModuleRegistry(),
        initial_role=initial_role,
        home_page=FakeHomePage(),
        experiment_list_page=FakeExperimentListPage(),
        experiment_workspace_page=FakeExperimentWorkspacePage(),
        active_student_repository=_make_seeded_active_student_repository(),
        teacher_dashboard_page=dashboard_page,
        sync_thread_controller=sync_thread_controller,
    )
    return window, sync_thread_controller, dashboard_page


def test_connectivity_online_shows_online_status_when_idle() -> None:
    window, sync_thread_controller, _dashboard_page = _make_window_with_sync()

    sync_thread_controller.connectivity_changed.emit(True, 0)

    assert window._sidebar._sync_status_label.text() == "● Онлайн"


def test_connectivity_offline_shows_offline_status_with_pending_count() -> None:
    window, sync_thread_controller, _dashboard_page = _make_window_with_sync()

    sync_thread_controller.connectivity_changed.emit(False, 3)

    assert window._sidebar._sync_status_label.text() == "● Офлайн"
    assert "Синхрондауды күтуде: 3" in window._settings_page._sync_status_label.text()


def test_connectivity_change_never_overwrites_active_sync_cycle_text() -> None:
    """§9 "UI Status": "Синхрондалуда..." мәтіні ЕШҚАШАН connectivity
    ping-мен үстінен жазылмауы керек."""
    window, sync_thread_controller, _dashboard_page = _make_window_with_sync()

    sync_thread_controller.sync_started.emit()
    sync_thread_controller.connectivity_changed.emit(True, 0)

    assert window._sidebar._sync_status_label.text() == "● Синхрондалуда..."


def test_connectivity_change_resumes_after_sync_cycle_finishes() -> None:
    window, sync_thread_controller, _dashboard_page = _make_window_with_sync()
    sync_thread_controller.sync_started.emit()
    sync_thread_controller.sync_finished.emit("synced", 1, 0, "", 0)

    sync_thread_controller.connectivity_changed.emit(True, 0)

    assert window._sidebar._sync_status_label.text() == "● Онлайн"


def test_sync_finished_with_pulled_data_refreshes_current_dashboard_page() -> None:
    """§8 "Teacher Monitoring Update Strategy" — жаңа pull-мен келген
    дерек болса, ағымдағы (data-dependent) бет қайта жаңарады."""
    window, sync_thread_controller, dashboard_page = _make_window_with_sync()
    assert window._stack.currentWidget() is dashboard_page
    calls_before = dashboard_page.on_enter_calls

    sync_thread_controller.sync_finished.emit("synced", 0, 2, "", 0)

    assert dashboard_page.on_enter_calls == calls_before + 1


def test_sync_finished_with_no_pulled_data_does_not_refresh_page() -> None:
    window, sync_thread_controller, dashboard_page = _make_window_with_sync()
    calls_before = dashboard_page.on_enter_calls

    sync_thread_controller.sync_finished.emit("synced", 0, 0, "", 0)

    assert dashboard_page.on_enter_calls == calls_before


def test_sync_finished_does_not_refresh_non_data_dependent_route() -> None:
    """§ "home" ``_AUTO_REFRESHABLE_ROUTES``-те ЖОҚ — pull-мен жаңа
    дерек келсе де, полигон ретінде ЕШБІР ерікті бет қайта жанданбайды."""
    window, sync_thread_controller, dashboard_page = _make_window_with_sync(
        initial_role=UserRole.TEACHER
    )
    window._router.navigate("home")
    calls_before = dashboard_page.on_enter_calls

    sync_thread_controller.sync_finished.emit("synced", 0, 5, "", 0)

    assert dashboard_page.on_enter_calls == calls_before


def test_manual_sync_button_reuses_same_coalescing_controller() -> None:
    """§16 "Manual Sync must remain" — ДӘЛ СОЛ ``SyncThreadController.
    run_sync_now()`` (коалесцирлеу § ``SyncWorker``-дің ӨЗІНДЕ)."""
    window, sync_thread_controller, _dashboard_page = _make_window_with_sync()

    window.trigger_manual_sync()

    assert sync_thread_controller.run_sync_now_calls == 1


# ---- Live stream: queue samples without waiting on the socket -------------


class DummyLive:
    def __init__(self) -> None:
        self.items: list = []
        self.status: list = []

    def enqueue_measurement(self, measurement, session_id: str) -> None:
        self.items.append((measurement, session_id))

    def set_status(self, state: str, experiment_id: str) -> None:
        self.status.append((state, experiment_id))


def test_live_measurement_slot_queues_sample() -> None:
    dummy = DummyLive()
    window, _home, _list, _workspace = _make_window()
    window.live_stream_controller = dummy
    sample = Measurement(
        timestamp=datetime(2026, 9, 4, 12, tzinfo=timezone.utc),
        values={"voltage": 1.2},
        experiment_id="ohms-law",
    )
    window._on_live_measurement(sample)
    assert dummy.items[0][0] is sample
    assert dummy.status[-1] == ("measuring", "ohms-law")


def test_live_stream_controller_defaults_to_none() -> None:
    window, _home, _list, _workspace = _make_window()
    assert window.live_stream_controller is None
    sample = Measurement(
        timestamp=datetime(2026, 9, 4, 12, tzinfo=timezone.utc),
        values={"voltage": 1.2},
        experiment_id="ohms-law",
    )
    window._on_live_measurement(sample)


def test_live_status_idle_on_workspace_leave() -> None:
    dummy = DummyLive()
    window, _home, _list, workspace = _make_window()
    window.live_stream_controller = dummy
    workspace.back_requested.emit()
    assert dummy.status[-1] == ("idle", "")


def test_live_status_idle_when_measurement_stops() -> None:
    dummy = DummyLive()
    window, _home, _list, workspace = _make_window()
    window.live_stream_controller = dummy
    workspace.measurement_running_changed.emit(False)
    assert dummy.status[-1] == ("idle", "")


def test_live_measurement_uses_session_id_from_workspace() -> None:
    dummy = DummyLive()
    window, _home, _list, workspace = _make_window()
    window.live_stream_controller = dummy
    workspace._experiment_controller = type(
        "Controller", (), {"session": type("Session", (), {"id": "sess-9"})()}
    )()
    sample = Measurement(
        timestamp=datetime(2026, 9, 4, 12, tzinfo=timezone.utc),
        values={"voltage": 1.2},
        experiment_id="ohms-law",
    )
    window._on_live_measurement(sample)
    assert dummy.items[0][1] == "sess-9"


def test_live_sample_ready_signal_queues_without_waiting() -> None:
    dummy = DummyLive()
    window, _home, _list, workspace = _make_window(live_stream_controller=dummy)
    sample = Measurement(
        timestamp=datetime(2026, 9, 4, 12, tzinfo=timezone.utc),
        values={"voltage": 1.2},
        experiment_id="ohms-law",
    )
    workspace.live_sample_ready.emit(sample, "sess-1")
    assert dummy.items[0] == (sample, "sess-1")
    assert dummy.status[-1] == ("measuring", "ohms-law")
