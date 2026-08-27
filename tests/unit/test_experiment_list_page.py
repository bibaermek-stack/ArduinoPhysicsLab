"""ExperimentListPage үшін юнит-тесттер."""

import re
import sys

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QPushButton

from domain.entities.experiment_definition import ExperimentDefinition
from domain.interfaces.i_physics_module import IPhysicsModule
from modules.module_registry import ModuleRegistry
from ui.pages.experiment_list_page import ExperimentListPage


@pytest.fixture(scope="module", autouse=True)
def qt_application() -> QApplication:
    """QWidget-тер үшін жалғыз QApplication дана."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def _make_experiment(id_: str, title: str) -> ExperimentDefinition:
    return ExperimentDefinition(id=id_, title=title, description=f"{title} сипаттамасы")


class _FakeModule(IPhysicsModule):
    def __init__(self, name: str, experiments: tuple[ExperimentDefinition, ...]) -> None:
        self._name = name
        self._experiments = experiments

    def get_name(self) -> str:
        return self._name

    def get_icon(self) -> str | None:
        return None

    def get_experiments(self) -> tuple[ExperimentDefinition, ...]:
        return self._experiments


def _select_button(page: ExperimentListPage) -> list[QPushButton]:
    return [
        button
        for button in page.findChildren(QPushButton)
        if button.text() == "Таңдау"
    ]


def test_on_enter_shows_module_experiments() -> None:
    experiments = (_make_experiment("e1", "Тізбек бөлігі үшін кернеудің ток күшіне тәуелділігін зерттеу"), _make_experiment("e2", "Электр тізбегін құрастыру және ток күшін өлшеу"))
    module = _FakeModule("Электр құбылыстары", experiments)
    page = ExperimentListPage()

    page.on_enter(module=module)

    assert len(_select_button(page)) == 2


def test_selecting_experiment_emits_experiment_selected() -> None:
    experiment = _make_experiment("e1", "Тізбек бөлігі үшін кернеудің ток күшіне тәуелділігін зерттеу")
    module = _FakeModule("Электр құбылыстары", (experiment,))
    page = ExperimentListPage()
    page.on_enter(module=module)
    selected: list[ExperimentDefinition] = []
    page.experiment_selected.connect(selected.append)

    _select_button(page)[0].click()

    assert selected == [experiment]


def test_back_button_emits_back_requested() -> None:
    page = ExperimentListPage()
    signals: list[None] = []
    page.back_requested.connect(lambda: signals.append(None))

    page._back_button.click()

    assert signals == [None]


def test_re_entering_with_different_module_replaces_cards() -> None:
    first_module = _FakeModule("Модуль 1", (_make_experiment("e1", "Жұмыс 1"),))
    second_module = _FakeModule(
        "Модуль 2", (_make_experiment("e2", "Жұмыс 2"), _make_experiment("e3", "Жұмыс 3"))
    )
    page = ExperimentListPage()

    page.on_enter(module=first_module)
    assert len(_select_button(page)) == 1

    page.on_enter(module=second_module)

    assert len(_select_button(page)) == 2


def test_planned_experiment_select_button_is_disabled() -> None:
    planned = ExperimentDefinition(
        id="planned-1", title="Жоспарланған жұмыс", description="", is_implemented=False
    )
    module = _FakeModule("Жылу құбылыстары", (planned,))
    page = ExperimentListPage()

    page.on_enter(module=module)

    disabled_buttons = [b for b in _select_button(page) if not b.isEnabled()]
    assert len(disabled_buttons) == 1


def test_planned_experiment_never_emits_experiment_selected() -> None:
    planned = ExperimentDefinition(
        id="planned-1", title="Жоспарланған жұмыс", description="", is_implemented=False
    )
    module = _FakeModule("Жылу құбылыстары", (planned,))
    page = ExperimentListPage()
    page.on_enter(module=module)
    selected: list[ExperimentDefinition] = []
    page.experiment_selected.connect(selected.append)

    for button in _select_button(page):
        button.click()

    assert selected == []


def _labs_section_cards(page: ExperimentListPage) -> list[QFrame]:
    return [
        frame
        for frame in page.findChildren(QFrame)
        if frame.objectName() == "LabsSectionCard"
    ]


def _labs_rows(page: ExperimentListPage) -> list[QFrame]:
    return [
        frame
        for frame in page.findChildren(QFrame)
        if frame.objectName() == "LabsExperimentRow"
    ]


def _click_row(row: QFrame) -> None:
    # ``DeviceCard``-та (ui/widgets/device_card.py) қолданылатын
    # mousePressEvent-негізді click simulation паттернімен бірдей.
    event = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPoint(5, 5),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    row.mousePressEvent(event)


def test_on_enter_without_module_shows_one_card_per_registered_section() -> None:
    registry = ModuleRegistry()
    registry.register(
        _FakeModule("Жылу құбылыстары", (_make_experiment("h1", "Жылу жұмысы"),))
    )
    registry.register(
        _FakeModule(
            "Электр құбылыстары",
            (_make_experiment("e1", "Тізбек бөлігі үшін кернеудің ток күшіне тәуелділігін зерттеу"), _make_experiment("e2", "Электр тізбегін құрастыру және ток күшін өлшеу")),
        )
    )
    page = ExperimentListPage(module_registry=registry)

    page.on_enter()

    assert len(_labs_section_cards(page)) == 2
    assert len(_labs_rows(page)) == 3
    section_titles = [
        label.text()
        for label in page.findChildren(QLabel)
        if label.objectName() == "LabsSectionTitle"
    ]
    assert "Жылу құбылыстары" in section_titles
    assert "Электр құбылыстары" in section_titles


def test_on_enter_without_module_shows_no_work_counts_or_planned_suffix() -> None:
    registry = ModuleRegistry()
    registry.register(
        _FakeModule(
            "Жылу құбылыстары",
            (
                ExperimentDefinition(
                    id="h1", title="Жылу жұмысы", description="", is_implemented=False
                ),
            ),
        )
    )
    page = ExperimentListPage(module_registry=registry)

    page.on_enter()

    all_texts = [label.text() for label in page.findChildren(QLabel)]
    all_texts += [button.text() for button in page.findChildren(QPushButton)]
    # "N жұмыс" саны толығымен алынып тасталуы тиіс (жол дәл осы форматта
    # болса ғана сәйкес келеді — "1. Жылу жұмысы" секілді нөмірленген
    # атауды жалған-позитив ретінде қаппауы үшін ``fullmatch`` қолданылды).
    assert not any(re.fullmatch(r"\d+\s+жұмыс", text) for text in all_texts)
    assert not any("(жоспарланған)" in text for text in all_texts)


def test_planned_experiment_row_is_disabled_in_catalog_mode() -> None:
    registry = ModuleRegistry()
    planned = ExperimentDefinition(
        id="planned-1", title="Жоспарланған жұмыс", description="", is_implemented=False
    )
    registry.register(_FakeModule("Жылу құбылыстары", (planned,)))
    page = ExperimentListPage(module_registry=registry)

    page.on_enter()

    rows = _labs_rows(page)
    assert len(rows) == 1
    assert rows[0].isEnabled() is False
    badge_texts = [
        label.text()
        for label in page.findChildren(QLabel)
        if label.objectName() == "LabsPlannedBadge"
    ]
    assert badge_texts == ["Жоспарланған"]


def test_implemented_experiment_row_is_clickable_in_catalog_mode() -> None:
    registry = ModuleRegistry()
    experiment = _make_experiment("e1", "Тізбек бөлігі үшін кернеудің ток күшіне тәуелділігін зерттеу")
    registry.register(_FakeModule("Электр құбылыстары", (experiment,)))
    page = ExperimentListPage(module_registry=registry)
    page.on_enter()
    selected: list[ExperimentDefinition] = []
    page.experiment_selected.connect(selected.append)

    _click_row(_labs_rows(page)[0])

    assert selected == [experiment]


def test_on_enter_without_module_sets_catalog_title() -> None:
    page = ExperimentListPage(module_registry=ModuleRegistry())

    page.on_enter()

    assert page._title_label.text() == "Зертханалық жұмыстар"


def test_on_enter_with_module_still_sets_module_title() -> None:
    module = _FakeModule("Электр құбылыстары", ())
    page = ExperimentListPage(module_registry=ModuleRegistry())

    page.on_enter(module=module)

    assert page._title_label.text() == "Электр құбылыстары"


# ---- "Модульдерге оралу" тек single-module режимінде (навигация bug fix) ---


def test_full_catalog_mode_has_no_back_button() -> None:
    page = ExperimentListPage(module_registry=ModuleRegistry())

    page.on_enter()  # module=None -> толық каталог

    assert page._back_button.isVisible() is False


def test_single_module_mode_still_shows_back_button() -> None:
    # QWidget.isVisible() виджет нақты экранда көрсетілгенде ғана True
    # қайтарады (test_device_panel.py-дегі established паттерн), сондықтан
    # show() қажет.
    module = _FakeModule("Электр құбылыстары", ())
    page = ExperimentListPage(module_registry=ModuleRegistry())
    page.show()

    page.on_enter(module=module)

    assert page._back_button.isVisible() is True


def test_disabled_row_click_in_catalog_mode_never_emits_experiment_selected() -> None:
    registry = ModuleRegistry()
    planned = ExperimentDefinition(
        id="planned-12",
        title="Жұқа линзаның фокус арақашықтығын анықтау",
        description="",
        display_number=12,
        is_implemented=False,
    )
    registry.register(_FakeModule("Жарық құбылыстары", (planned,)))
    page = ExperimentListPage(module_registry=registry)
    page.on_enter()
    selected: list[ExperimentDefinition] = []
    page.experiment_selected.connect(selected.append)

    _click_row(_labs_rows(page)[0])

    assert selected == []
