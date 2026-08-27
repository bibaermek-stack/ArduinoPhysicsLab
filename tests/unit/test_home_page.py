"""HomePage (Student Home Dashboard Redesign) юнит-тесттері."""

import sys
from datetime import datetime, timezone

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QPushButton

from domain.entities.connected_device import ConnectedDevice
from domain.entities.experiment_definition import ExperimentDefinition
from domain.interfaces.i_physics_module import IPhysicsModule
from domain.services.student_home_summary import (
    CategoryProgress,
    RecentResult,
    ResumableExperiment,
    StudentHomeSummary,
)
from modules.module_registry import ModuleRegistry
from ui.pages.home_page import HomePage


@pytest.fixture(scope="module", autouse=True)
def qt_application() -> QApplication:
    """QWidget-тер үшін жалғыз QApplication дана."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


class FakeDeviceManager(QObject):
    """``DeviceManager``-дің HomePage қолданатын беті ғана қайталанатын
    жеңіл тест double-ы — нақты serial port ашылмайды, `disconnect_port`/
    `shutdown_all`/`stop` шақырылғанын бақылайды (HomePage оларды
    ЕШҚАШАН шақырмауы тиіс).
    """

    device_identified = Signal(object)
    port_disconnected = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._devices: list[ConnectedDevice] = []
        self.shutdown_all_calls = 0
        self.disconnect_port_calls: list[str] = []
        self.stop_calls = 0

    def add_device(self, device: ConnectedDevice) -> None:
        self._devices.append(device)
        self.device_identified.emit(device)

    def remove_last(self, port_name: str) -> None:
        if self._devices:
            self._devices.pop()
        self.port_disconnected.emit(port_name)

    def get_connected_devices(self) -> tuple[ConnectedDevice, ...]:
        return tuple(self._devices)

    def shutdown_all(self) -> None:
        self.shutdown_all_calls += 1

    def disconnect_port(self, port_name: str) -> None:
        self.disconnect_port_calls.append(port_name)

    def stop(self) -> None:
        self.stop_calls += 1


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


class _FakeModule(IPhysicsModule):
    def __init__(
        self, name: str, experiments: tuple[ExperimentDefinition, ...] = (), icon: str = "🔧"
    ) -> None:
        self._name = name
        self._experiments = experiments
        self._icon = icon

    def get_name(self) -> str:
        return self._name

    def get_icon(self) -> str | None:
        return self._icon

    def get_experiments(self) -> tuple[ExperimentDefinition, ...]:
        return self._experiments


def _category_cards(page: HomePage) -> list[QFrame]:
    return [f for f in page.findChildren(QFrame) if f.objectName() == "HomeModuleCard"]


def _category_action_buttons(page: HomePage) -> list[QPushButton]:
    return [
        b for b in page.findChildren(QPushButton) if b.objectName() == "HomeModuleCardAction"
    ]


def _find_button(page: HomePage, text: str) -> QPushButton:
    return next(b for b in page.findChildren(QPushButton) if b.text() == text)


# =====================================================================
# §1-3: Сәлемдесу header — белсенді оқушы аты/сынып/ауысу.
# =====================================================================


def test_home_page_renders_without_crashing() -> None:
    page = HomePage(ModuleRegistry())
    assert page is not None


def test_greeting_neutral_by_default_no_fabricated_identity() -> None:
    page = HomePage(ModuleRegistry())
    assert page._greeting_label.text() == "Сәлем!"


def test_greeting_resolves_active_student_name() -> None:
    page = HomePage(ModuleRegistry())

    page.set_student_context("Отарбай Самат", "8Б", None)

    assert page._greeting_label.text() == "Сәлем, Отарбай Самат!"


def test_greeting_resolves_classroom_name() -> None:
    page = HomePage(ModuleRegistry())

    page.set_student_context("Отарбай Самат", "8Б", None)

    assert "8Б сыныбы" in page._greeting_subtitle_label.text()


def test_greeting_omits_classroom_clause_when_classroom_unknown() -> None:
    page = HomePage(ModuleRegistry())

    page.set_student_context("Отарбай Самат", None, None)

    assert "сыныбы" not in page._greeting_subtitle_label.text()


def test_student_switching_refreshes_greeting() -> None:
    page = HomePage(ModuleRegistry())
    page.set_student_context("Отарбай Самат", "8Б", None)
    assert page._greeting_label.text() == "Сәлем, Отарбай Самат!"

    page.set_student_context("Бекзат Нұрлан", "9А", None)

    assert page._greeting_label.text() == "Сәлем, Бекзат Нұрлан!"
    assert "9А сыныбы" in page._greeting_subtitle_label.text()


def test_header_cta_emits_labs_requested() -> None:
    page = HomePage(ModuleRegistry())
    received: list[None] = []
    page.labs_requested.connect(lambda: received.append(None))

    page._labs_action_button.click()

    assert received == [None]
    assert page._labs_action_button.text() == "Зертханалық жұмысты бастау →"


# =====================================================================
# §4-5: 4 KPI карточка.
# =====================================================================


def test_exactly_four_kpi_cards_rendered() -> None:
    page = HomePage(ModuleRegistry())

    cards = [f for f in page.findChildren(QFrame) if f.objectName() == "HomeSummaryCard"]

    assert len(cards) == 4


def test_kpi_captions_match_spec() -> None:
    page = HomePage(ModuleRegistry())

    labels = [label.text() for label in page.findChildren(QLabel) if label.property("role") == "cardLabel"]

    assert labels == ["Орындалып жатыр", "Аяқталған", "Тексеруді күтуде", "Қосылған құрылғы"]


def test_kpi_values_reflect_pushed_summary() -> None:
    page = HomePage(ModuleRegistry())
    summary = StudentHomeSummary(
        in_progress_count=2, completed_count=5, awaiting_review_count=1,
        resumable=None, category_progress=(), recent_results=(),
    )

    page.set_student_context("Айдос", "8А", summary)

    assert page._kpi_value_labels["in_progress"].text() == "2"
    assert page._kpi_value_labels["completed"].text() == "5"
    assert page._kpi_value_labels["awaiting_review"].text() == "1"


def test_kpi_values_zero_when_no_active_student() -> None:
    page = HomePage(ModuleRegistry())

    page.set_student_context(None, None, None)

    assert page._kpi_value_labels["in_progress"].text() == "0"
    assert page._kpi_value_labels["completed"].text() == "0"
    assert page._kpi_value_labels["awaiting_review"].text() == "0"


def test_kpi_cards_have_equal_stretch_factor() -> None:
    page = HomePage(ModuleRegistry())

    devices_card = page._kpi_value_labels["devices"].parentWidget()
    row = devices_card.parentWidget()
    layout = row.layout()

    assert layout.stretch(layout.indexOf(devices_card)) == 1


# =====================================================================
# §6-8: "Жалғастыру" карточкасы.
# =====================================================================


_EXPERIMENT = ExperimentDefinition(
    id="current-voltage",
    title="Электр тізбегін құрастыру және ток күшін өлшеу",
    description="",
    display_number=3,
    required_sensor_types=("VOLTAGE", "CURRENT"),
)


def test_no_active_student_shows_no_in_progress_state() -> None:
    page = HomePage(ModuleRegistry())
    page.show()

    page.set_student_context(None, None, None)

    assert page._continue_empty_container.isVisible() is True
    assert page._continue_populated_container.isVisible() is False


def test_in_progress_summary_selects_valid_resumable_item() -> None:
    page = HomePage(ModuleRegistry())
    page.show()
    module = _FakeModule("Электр құбылыстары", (_EXPERIMENT,), icon="⚡")
    summary = StudentHomeSummary(
        in_progress_count=1, completed_count=0, awaiting_review_count=0,
        resumable=ResumableExperiment(experiment=_EXPERIMENT, module=module),
        category_progress=(), recent_results=(),
    )

    page.set_student_context("Айдос", "8А", summary)

    assert page._continue_populated_container.isVisible() is True
    assert page._continue_empty_container.isVisible() is False
    assert "№3" in page._continue_experiment_label.text()
    assert "Электр тізбегін құрастыру" in page._continue_experiment_label.text()
    assert "⚡" in page._continue_category_label.text()
    assert "Электр құбылыстары" in page._continue_category_label.text()
    assert "Кернеу датчигі" in page._continue_sensors_label.text()
    assert "Ток датчигі" in page._continue_sensors_label.text()


def test_no_in_progress_state_renders_correctly() -> None:
    page = HomePage(ModuleRegistry())
    page.show()
    summary = StudentHomeSummary(
        in_progress_count=0, completed_count=3, awaiting_review_count=0,
        resumable=None, category_progress=(), recent_results=(),
    )

    page.set_student_context("Айдос", "8А", summary)

    assert page._continue_empty_container.isVisible() is True
    assert page._continue_populated_container.isVisible() is False


def test_continue_cta_emits_experiment_selected_with_resumable_experiment() -> None:
    page = HomePage(ModuleRegistry())
    module = _FakeModule("Электр құбылыстары", (_EXPERIMENT,), icon="⚡")
    summary = StudentHomeSummary(
        in_progress_count=1, completed_count=0, awaiting_review_count=0,
        resumable=ResumableExperiment(experiment=_EXPERIMENT, module=module),
        category_progress=(), recent_results=(),
    )
    page.set_student_context("Айдос", "8А", summary)
    selected: list[ExperimentDefinition] = []
    page.experiment_selected.connect(selected.append)

    page._continue_button.click()

    assert selected == [_EXPERIMENT]


def test_empty_continue_cta_emits_labs_requested() -> None:
    page = HomePage(ModuleRegistry())
    received: list[None] = []
    page.labs_requested.connect(lambda: received.append(None))

    page._continue_empty_button.click()

    assert received == [None]


# =====================================================================
# Final polish §2: "Тағы N орындалып жатқан жұмыс" secondary indicator.
# =====================================================================


def _summary_with_in_progress_count(count: int) -> StudentHomeSummary:
    module = _FakeModule("Электр құбылыстары", (_EXPERIMENT,), icon="⚡")
    return StudentHomeSummary(
        in_progress_count=count, completed_count=0, awaiting_review_count=0,
        resumable=ResumableExperiment(experiment=_EXPERIMENT, module=module),
        category_progress=(), recent_results=(),
    )


def test_more_in_progress_link_hidden_when_only_one_in_progress() -> None:
    page = HomePage(ModuleRegistry())

    page.set_student_context("Айдос", "8А", _summary_with_in_progress_count(1))

    assert page._continue_more_in_progress_button.isVisible() is False


def test_more_in_progress_link_shown_when_multiple_in_progress() -> None:
    page = HomePage(ModuleRegistry())
    page.show()

    page.set_student_context("Айдос", "8А", _summary_with_in_progress_count(4))

    assert page._continue_more_in_progress_button.isVisible() is True
    assert page._continue_more_in_progress_button.text() == "Тағы 3 орындалып жатқан жұмыс"


def test_more_in_progress_link_n_calculation_is_count_minus_one() -> None:
    page = HomePage(ModuleRegistry())
    page.show()

    page.set_student_context("Айдос", "8А", _summary_with_in_progress_count(6))

    assert page._continue_more_in_progress_button.text() == "Тағы 5 орындалып жатқан жұмыс"


def test_more_in_progress_link_hidden_when_zero_in_progress() -> None:
    page = HomePage(ModuleRegistry())

    page.set_student_context("Айдос", "8А", _summary_with_in_progress_count(0))

    # § count=0 -> resumable=None логикалық жағынан мүмкін емес нақты
    # деректе, бірақ қорғаныс ретінде де сілтеме көрінбеуі тиіс.
    assert page._continue_more_in_progress_button.isVisible() is False


def test_more_in_progress_link_click_emits_labs_requested() -> None:
    page = HomePage(ModuleRegistry())
    page.show()
    page.set_student_context("Айдос", "8А", _summary_with_in_progress_count(3))
    received: list[None] = []
    page.labs_requested.connect(lambda: received.append(None))

    page._continue_more_in_progress_button.click()

    assert received == [None]


# =====================================================================
# §9-11: 4 категория карточкасы.
# =====================================================================


def test_four_registered_modules_produce_four_cards() -> None:
    registry = ModuleRegistry()
    for name in ["Жылу құбылыстары", "Электр құбылыстары", "Электромагниттік құбылыстар", "Жарық құбылыстары"]:
        registry.register(_FakeModule(name))
    page = HomePage(registry)

    assert len(_category_cards(page)) == 4


def test_category_cards_follow_registry_order() -> None:
    registry = ModuleRegistry()
    registry.register(_FakeModule("Модуль А"))
    registry.register(_FakeModule("Модуль Б"))
    page = HomePage(registry)

    titles = [
        label.text()
        for label in page.findChildren(QLabel)
        if label.objectName() == "HomeModuleCardTitle"
    ]
    assert titles == ["Модуль А", "Модуль Б"]


def test_category_denominator_comes_from_real_catalog() -> None:
    registry = ModuleRegistry()
    registry.register(
        _FakeModule(
            "Электр құбылыстары",
            (
                ExperimentDefinition(id="e1", title="E1", description=""),
                ExperimentDefinition(id="e2", title="E2", description=""),
                ExperimentDefinition(id="e3", title="E3", description=""),
            ),
        )
    )
    page = HomePage(registry)

    labels = [label.text() for label in page.findChildren(QLabel)]
    # § "do not hardcode 2/6" — белсенді оқушы жоқ болса да, denominator
    # (жалпы 3) НАҚТЫ каталогтан.
    assert "0 / 3 орындалды" in labels


def test_category_completed_count_uses_real_progress() -> None:
    module = _FakeModule(
        "Электр құбылыстары",
        (
            ExperimentDefinition(id="e1", title="E1", description=""),
            ExperimentDefinition(id="e2", title="E2", description=""),
        ),
    )
    registry = ModuleRegistry()
    registry.register(module)
    page = HomePage(registry)
    summary = StudentHomeSummary(
        in_progress_count=0, completed_count=1, awaiting_review_count=0,
        resumable=None,
        category_progress=(CategoryProgress(module=module, completed=1, total=2),),
        recent_results=(),
    )

    page.set_student_context("Айдос", "8А", summary)

    labels = [label.text() for label in page.findChildren(QLabel)]
    assert "1 / 2 орындалды" in labels


# =====================================================================
# Final polish §4: category progress bar (X / Y ratio).
# =====================================================================


def test_category_progress_bar_value_matches_ratio() -> None:
    module = _FakeModule(
        "Электр құбылыстары",
        (
            ExperimentDefinition(id="e1", title="E1", description=""),
            ExperimentDefinition(id="e2", title="E2", description=""),
            ExperimentDefinition(id="e3", title="E3", description=""),
            ExperimentDefinition(id="e4", title="E4", description=""),
        ),
    )
    registry = ModuleRegistry()
    registry.register(module)
    page = HomePage(registry)
    summary = StudentHomeSummary(
        in_progress_count=0, completed_count=1, awaiting_review_count=0,
        resumable=None,
        category_progress=(CategoryProgress(module=module, completed=1, total=4),),
        recent_results=(),
    )

    page.set_student_context("Айдос", "8А", summary)

    bar = page._category_progress_bars["Электр құбылыстары"]
    assert bar.value() == 25  # 1/4 = 25%


def test_category_progress_bar_zero_by_default() -> None:
    registry = ModuleRegistry()
    registry.register(
        _FakeModule("Электр құбылыстары", (ExperimentDefinition(id="e1", title="E1", description=""),))
    )
    page = HomePage(registry)

    bar = page._category_progress_bars["Электр құбылыстары"]
    assert bar.value() == 0


def test_category_progress_bar_safe_when_total_is_zero() -> None:
    registry = ModuleRegistry()
    registry.register(_FakeModule("Бос бөлім", ()))
    page = HomePage(registry)

    bar = page._category_progress_bars["Бос бөлім"]
    assert bar.value() == 0


def test_category_action_click_emits_module_selected() -> None:
    registry = ModuleRegistry()
    module = _FakeModule("Электр құбылыстары")
    registry.register(module)
    page = HomePage(registry)
    selected: list[IPhysicsModule] = []
    page.module_selected.connect(selected.append)

    _category_action_buttons(page)[0].click()

    assert selected == [module]


def test_empty_registry_does_not_crash() -> None:
    page = HomePage(ModuleRegistry())

    assert _category_cards(page) == []


# =====================================================================
# §12: Ескі "Дайын жұмыстар" ұзын тізімі МҮЛДЕ ЖОҚ.
# =====================================================================


def test_old_quick_labs_list_is_absent() -> None:
    registry = ModuleRegistry()
    registry.register(
        _FakeModule("Электр құбылыстары", (ExperimentDefinition(id="e1", title="E1", description=""),))
    )
    page = HomePage(registry)

    assert page.findChildren(QPushButton, "HomeQuickLabButton") == []
    labels = [label.text() for label in page.findChildren(QLabel)]
    assert "Дайын жұмыстар" not in labels


def test_old_large_branding_hero_is_absent() -> None:
    page = HomePage(ModuleRegistry())

    labels = [label.text() for label in page.findChildren(QLabel)]
    assert "⚛ Arduino Physics Lab" not in labels
    assert "Smart Educational Measurement System" not in labels


# =====================================================================
# §13-15: "Соңғы нәтижелер".
# =====================================================================


_ICE_MELT = ExperimentDefinition(id="ice-melt", title="Мұздың балқуы", description="", display_number=2)
_HEAT_COMPARE = ExperimentDefinition(id="heat-cmp", title="Жылу мөлшерін салыстыру", description="", display_number=1)


def test_recent_results_empty_state_by_default() -> None:
    page = HomePage(ModuleRegistry())
    page.show()

    page.set_student_context("Айдос", "8А", None)

    assert page._recent_results_empty_title_label.isVisible() is True
    assert page._recent_results_container.isVisible() is False


def test_recent_results_renders_up_to_three_rows() -> None:
    page = HomePage(ModuleRegistry())
    page.show()
    summary = StudentHomeSummary(
        in_progress_count=0, completed_count=3, awaiting_review_count=0,
        resumable=None, category_progress=(),
        recent_results=(
            RecentResult(experiment=_ICE_MELT, teacher_score=8),
            RecentResult(experiment=_HEAT_COMPARE, teacher_score=9),
        ),
    )

    page.set_student_context("Айдос", "8А", summary)

    assert page._recent_results_empty_title_label.isVisible() is False
    assert page._recent_results_container.isVisible() is True
    assert page._recent_results_layout.count() == 2
    labels = [label.text() for label in page.findChildren(QLabel)]
    assert any("№2" in text and "Мұздың балқуы" in text for text in labels)
    assert "8 / 10" in labels
    assert "9 / 10" in labels


def test_recent_results_score_not_fabricated_shows_dash() -> None:
    page = HomePage(ModuleRegistry())
    summary = StudentHomeSummary(
        in_progress_count=0, completed_count=1, awaiting_review_count=1,
        resumable=None, category_progress=(),
        recent_results=(RecentResult(experiment=_ICE_MELT, teacher_score=None),),
    )

    page.set_student_context("Айдос", "8А", summary)

    labels = [label.text() for label in page.findChildren(QLabel)]
    assert "—" in labels
    assert not any(" / 10" in text for text in labels if "№" not in text and text != "—")


def test_view_all_results_button_emits_results_requested() -> None:
    page = HomePage(ModuleRegistry())
    received: list[None] = []
    page.results_requested.connect(lambda: received.append(None))

    _find_button(page, "Барлық нәтижелер →").click()

    assert received == [None]


# =====================================================================
# §16-17, §18 (device action visibility): "Құрылғы күйі".
# =====================================================================


def test_device_status_empty_state_shown_when_no_devices() -> None:
    manager = FakeDeviceManager()
    page = HomePage(ModuleRegistry(), device_manager=manager)
    page.show()

    assert page._device_empty_title_label.isVisible() is True
    assert page._device_summary_label.isVisible() is False


def test_device_status_connected_state_shows_real_fields() -> None:
    manager = FakeDeviceManager()
    manager.add_device(_make_device("COM4", "VOLTAGE"))
    page = HomePage(ModuleRegistry(), device_manager=manager)
    page.show()

    assert page._device_empty_title_label.isVisible() is False
    assert page._device_summary_label.isVisible() is True
    assert page._device_summary_label.text() == "1 құрылғы қосылған"
    labels = [label.text() for label in page.findChildren(QLabel)]
    assert "Кернеу датчигі" in labels
    assert "COM4" in labels
    assert "Дайын" in labels


def test_kpi_devices_count_reflects_device_manager() -> None:
    manager = FakeDeviceManager()
    manager.add_device(_make_device("COM6", "VOLTAGE"))
    manager.add_device(_make_device("COM11", "CURRENT"))

    page = HomePage(ModuleRegistry(), device_manager=manager)

    assert page._kpi_value_labels["devices"].text() == "2"


def test_kpi_devices_count_updates_on_signal() -> None:
    manager = FakeDeviceManager()
    page = HomePage(ModuleRegistry(), device_manager=manager)
    assert page._kpi_value_labels["devices"].text() == "0"

    manager.add_device(_make_device("COM6", "VOLTAGE"))
    assert page._kpi_value_labels["devices"].text() == "1"

    manager.remove_last("COM6")
    assert page._kpi_value_labels["devices"].text() == "0"


def test_device_action_visible_by_default() -> None:
    page = HomePage(ModuleRegistry())

    assert page._manage_devices_button.isHidden() is False


def test_set_devices_action_visible_false_hides_button() -> None:
    page = HomePage(ModuleRegistry())

    page.set_devices_action_visible(False)

    assert page._manage_devices_button.isHidden() is True


def test_set_devices_action_visible_true_shows_button_again() -> None:
    page = HomePage(ModuleRegistry())
    page.set_devices_action_visible(False)

    page.set_devices_action_visible(True)

    assert page._manage_devices_button.isHidden() is False


def test_device_action_button_emits_devices_requested() -> None:
    page = HomePage(ModuleRegistry())
    received: list[None] = []
    page.devices_requested.connect(lambda: received.append(None))

    page._manage_devices_button.click()

    assert received == [None]


# =====================================================================
# Persistence guarantees (unchanged from V1).
# =====================================================================


def test_home_page_never_shuts_down_device_manager() -> None:
    manager = FakeDeviceManager()
    page = HomePage(ModuleRegistry(), device_manager=manager)
    page.on_enter()
    manager.add_device(_make_device("COM6", "VOLTAGE"))
    manager.remove_last("COM6")

    assert manager.shutdown_all_calls == 0
    assert manager.disconnect_port_calls == []
    assert manager.stop_calls == 0


# =====================================================================
# §20: "← Артқа" батырмасы ЖОҚ.
# =====================================================================


def test_no_back_button() -> None:
    page = HomePage(ModuleRegistry())
    assert all(button.text() != "← Артқа" for button in page.findChildren(QPushButton))
    assert not hasattr(page, "back_requested")


# =====================================================================
# §21: Watermark/theme.
# =====================================================================


def test_home_page_listed_in_transparent_root_classes() -> None:
    from ui.themes.theme_manager import ThemeManager

    assert "HomePage" in ThemeManager().build_stylesheet()


def test_home_page_root_has_no_instance_level_stylesheet() -> None:
    page = HomePage(ModuleRegistry())
    assert page.styleSheet() == ""


# =====================================================================
# Responsive width (Phase 32.2, unchanged) — HomeContent max-width/centering.
# =====================================================================


def _home_content(page: HomePage) -> "QWidget":  # noqa: F821 - forward ref for typing
    from PySide6.QtWidgets import QWidget

    return page.findChild(QWidget, "HomeContent")


def test_home_content_has_expanding_horizontal_size_policy() -> None:
    from PySide6.QtWidgets import QSizePolicy

    page = HomePage(ModuleRegistry())
    content = _home_content(page)
    assert content.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding


def test_home_content_still_has_a_sensible_max_width_cap() -> None:
    page = HomePage(ModuleRegistry())
    content = _home_content(page)
    assert content.maximumWidth() > 0
    assert content.maximumWidth() < 16777215  # Qt "шексіз" мәні ЕМЕС


def test_home_content_grows_wider_between_1366_and_1920() -> None:
    page = HomePage(ModuleRegistry())
    page.show()

    content = _home_content(page)

    page.resize(1366, 768)
    page.show()
    for _ in range(2):
        QApplication.processEvents()
    width_1366 = content.geometry().width()

    page.resize(1920, 1080)
    for _ in range(2):
        QApplication.processEvents()
    width_1920 = content.geometry().width()

    assert width_1920 > width_1366


def test_home_content_reaches_the_max_width_cap_on_a_wide_window() -> None:
    page = HomePage(ModuleRegistry())
    content = _home_content(page)

    page.resize(1920, 1080)
    page.show()
    for _ in range(2):
        QApplication.processEvents()

    assert content.geometry().width() == content.maximumWidth()


def test_home_content_stays_reasonably_centered_on_very_wide_window() -> None:
    page = HomePage(ModuleRegistry())
    content = _home_content(page)

    page.resize(2560, 1440)
    page.show()
    for _ in range(2):
        QApplication.processEvents()

    left_margin = content.geometry().x()
    right_margin = page.width() - (content.geometry().x() + content.geometry().width())
    assert abs(left_margin - right_margin) <= 2  # rounding tolerance


# =====================================================================
# Геометрия — 1366x768 (§14).
# =====================================================================


def test_1366x768_smoke_layout_no_crash() -> None:
    registry = ModuleRegistry()
    for name in ["Жылу құбылыстары", "Электр құбылыстары", "Электромагниттік құбылыстар", "Жарық құбылыстары"]:
        registry.register(_FakeModule(name, (ExperimentDefinition(id=f"{name}-1", title="X", description=""),)))
    page = HomePage(registry)
    page.resize(1366, 768)
    page.show()

    assert page.width() == 1366
    assert len(_category_cards(page)) == 4
