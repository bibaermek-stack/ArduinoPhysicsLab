"""DataJournalPage үшін юнит-тесттер (Data Journal V1)."""

import sys
from datetime import datetime, timedelta, timezone

import pytest
from PySide6.QtWidgets import QApplication, QFileDialog, QPushButton, QSizePolicy

from domain.entities.classroom import Classroom
from domain.entities.experiment_definition import ExperimentDefinition
from domain.entities.experiment_session import ExperimentSession
from domain.entities.measurement import Measurement
from domain.entities.student import Student
from domain.entities.user_role import UserRole
from domain.interfaces.i_physics_module import IPhysicsModule
from infrastructure.storage.sqlite_classroom_repository import SqliteClassroomRepository
from infrastructure.storage.sqlite_session_repository import SqliteSessionRepository
from infrastructure.storage.sqlite_student_progress_repository import SqliteStudentProgressRepository
from infrastructure.storage.sqlite_student_repository import SqliteStudentRepository
from modules.module_registry import ModuleRegistry
from ui.pages.data_journal_page import DataJournalPage

_NOW = datetime.now(timezone.utc)


@pytest.fixture(scope="module", autouse=True)
def qt_application() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


class FakeExporter:
    def __init__(self) -> None:
        self.export_calls: list[tuple[ExperimentSession, str]] = []

    def export(self, session: ExperimentSession, output_path: str) -> bool:
        self.export_calls.append((session, output_path))
        return True


def _make_session(
    session_id: str,
    experiment_id: str = "ohms-law",
    measurement_count: int = 3,
    started_offset_hours: float = 0.0,
) -> ExperimentSession:
    session = ExperimentSession(
        id=session_id,
        experiment_id=experiment_id,
        started_at=_NOW - timedelta(hours=started_offset_hours),
    )
    for i in range(measurement_count):
        session.add_measurement(
            Measurement(
                timestamp=_NOW + timedelta(seconds=i),
                values={"voltage": 5.0 + i, "current": 0.05},
                experiment_id=experiment_id,
                derived_values={"resistance": 100.0},
            )
        )
    session.stop()
    return session


def _make_experiment_metadata(
    id_: str = "ohms-law",
    title: str = "Тізбек бөлігі үшін кернеудің ток күшіне тәуелділігін зерттеу",
    display_number: int = 4,
) -> ExperimentDefinition:
    return ExperimentDefinition(id=id_, title=title, description="", display_number=display_number)


def _open_button(page: DataJournalPage, row: int) -> QPushButton:
    return page._table.cellWidget(row, page._table.columnCount() - 1)


# ---- Empty state / rendering -----------------------------------------------


def test_page_renders_without_crashing() -> None:
    page = DataJournalPage(session_repository=SqliteSessionRepository())
    assert page is not None


def test_empty_database_shows_empty_state() -> None:
    page = DataJournalPage(session_repository=SqliteSessionRepository())
    page.show()

    assert page._empty_state_title_label.isVisible() is True
    assert page._table.isVisible() is False


def test_one_saved_session_appears_as_one_row() -> None:
    repository = SqliteSessionRepository()
    repository.save_session(_make_session("s1"), _make_experiment_metadata())
    page = DataJournalPage(session_repository=repository)

    page.on_enter()

    assert page._table.rowCount() == 1


def test_multiple_sessions_sorted_newest_first() -> None:
    repository = SqliteSessionRepository()
    repository.save_session(
        _make_session("older", started_offset_hours=2), _make_experiment_metadata()
    )
    repository.save_session(_make_session("newer"), _make_experiment_metadata())
    page = DataJournalPage(session_repository=repository)

    page.on_enter()

    assert page._sessions[0].id == "newer"
    assert page._sessions[1].id == "older"


def test_row_shows_measurement_count_and_title() -> None:
    repository = SqliteSessionRepository()
    repository.save_session(
        _make_session("s1", measurement_count=42), _make_experiment_metadata()
    )
    page = DataJournalPage(session_repository=repository)
    page.on_enter()

    assert page._table.item(0, 3).text() == "42 өлшеу"
    assert (
        page._table.item(0, 1).text()
        == "4. Тізбек бөлігі үшін кернеудің ток күшіне тәуелділігін зерттеу"
    )


# ---- Detail view ------------------------------------------------------------


def test_open_shows_correct_session_details() -> None:
    repository = SqliteSessionRepository()
    repository.save_session(
        _make_session("s1", measurement_count=5), _make_experiment_metadata()
    )
    page = DataJournalPage(session_repository=repository)
    page.on_enter()

    _open_button(page, 0).click()

    assert page._stack.currentIndex() == 1
    assert (
        page._detail_title_label.text()
        == "4. Тізбек бөлігі үшін кернеудің ток күшіне тәуелділігін зерттеу"
    )
    assert "5 өлшеу" in page._detail_meta_label.text()


def test_open_loads_correct_measurement_row_count() -> None:
    repository = SqliteSessionRepository()
    repository.save_session(
        _make_session("s1", measurement_count=7), _make_experiment_metadata()
    )
    page = DataJournalPage(session_repository=repository)
    page.on_enter()

    _open_button(page, 0).click()

    assert page._detail_table._model.rowCount() == 7


def test_back_to_journal_returns_to_list() -> None:
    repository = SqliteSessionRepository()
    repository.save_session(_make_session("s1"), _make_experiment_metadata())
    page = DataJournalPage(session_repository=repository)
    page.on_enter()
    _open_button(page, 0).click()
    assert page._stack.currentIndex() == 1

    page._detail_back_button.click()

    assert page._stack.currentIndex() == 0


def test_detail_uses_module_registry_channels_when_available() -> None:
    class _FakeModule(IPhysicsModule):
        def get_name(self) -> str:
            return "Электр құбылыстары"

        def get_icon(self) -> str | None:
            return None

        def get_experiments(self) -> tuple[ExperimentDefinition, ...]:
            from domain.entities.sensor_channel import SensorChannel

            return (
                ExperimentDefinition(
                    id="ohms-law",
                    title="Тізбек бөлігі үшін кернеудің ток күшіне тәуелділігін зерттеу",
                    description="",
                    display_number=4,
                    required_channels=(
                        SensorChannel(key="voltage", display_name="Кернеу", unit="V"),
                        SensorChannel(key="current", display_name="Ток", unit="A"),
                    ),
                    derived_channels=(
                        SensorChannel(key="resistance", display_name="Кедергі", unit="Ω"),
                    ),
                ),
            )

    registry = ModuleRegistry()
    registry.register(_FakeModule())
    repository = SqliteSessionRepository()
    repository.save_session(_make_session("s1"), _make_experiment_metadata())
    page = DataJournalPage(session_repository=repository, module_registry=registry)
    page.on_enter()

    _open_button(page, 0).click()

    headers = [
        page._detail_table._model.horizontalHeaderItem(i).text()
        for i in range(page._detail_table._model.columnCount())
    ]
    assert "Кернеу (V)" in headers


# ---- CSV export ------------------------------------------------------------


def test_csv_export_exports_historical_session(monkeypatch: pytest.MonkeyPatch) -> None:
    repository = SqliteSessionRepository()
    repository.save_session(
        _make_session("s1", measurement_count=4), _make_experiment_metadata()
    )
    fake_exporter = FakeExporter()
    page = DataJournalPage(session_repository=repository, csv_exporter=fake_exporter)
    page.on_enter()
    _open_button(page, 0).click()

    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", lambda *args, **kwargs: ("C:/fake/out.csv", "")
    )
    page._detail_export_button.click()

    assert len(fake_exporter.export_calls) == 1
    session, path = fake_exporter.export_calls[0]
    assert path == "C:/fake/out.csv"
    assert len(session.measurements) == 4


def test_csv_export_cancel_does_not_call_exporter(monkeypatch: pytest.MonkeyPatch) -> None:
    repository = SqliteSessionRepository()
    repository.save_session(_make_session("s1"), _make_experiment_metadata())
    fake_exporter = FakeExporter()
    page = DataJournalPage(session_repository=repository, csv_exporter=fake_exporter)
    page.on_enter()
    _open_button(page, 0).click()

    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: ("", ""))
    page._detail_export_button.click()

    assert fake_exporter.export_calls == []


# ---- Filter -----------------------------------------------------------------


def test_experiment_filter_narrows_list() -> None:
    repository = SqliteSessionRepository()
    repository.save_session(_make_session("ohms-1", experiment_id="ohms-law"), _make_experiment_metadata())
    repository.save_session(
        _make_session("cv-1", experiment_id="current-voltage"),
        _make_experiment_metadata(
            id_="current-voltage",
            title="Электр тізбегін құрастыру және ток күшін өлшеу",
            display_number=3,
        ),
    )
    page = DataJournalPage(session_repository=repository)
    page.on_enter()
    assert page._table.rowCount() == 2

    index = page._filter_combo.findData("ohms-law")
    page._filter_combo.setCurrentIndex(index)

    assert page._table.rowCount() == 1


# ---- Performance shape (spec §20/§34): list never loads measurements ------


def test_refresh_never_loads_measurements(monkeypatch: pytest.MonkeyPatch) -> None:
    repository = SqliteSessionRepository()
    repository.save_session(
        _make_session("s1", measurement_count=500), _make_experiment_metadata()
    )
    page = DataJournalPage(session_repository=repository)

    calls: list[str] = []
    original = repository.get_measurements

    def _spy(session_id: str):
        calls.append(session_id)
        return original(session_id)

    monkeypatch.setattr(repository, "get_measurements", _spy)

    page.on_enter()

    assert calls == []


def test_opening_one_session_calls_get_measurements_exactly_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = SqliteSessionRepository()
    repository.save_session(
        _make_session("s1", measurement_count=500), _make_experiment_metadata()
    )
    page = DataJournalPage(session_repository=repository)
    page.on_enter()

    calls: list[str] = []
    original = repository.get_measurements

    def _spy(session_id: str):
        calls.append(session_id)
        return original(session_id)

    monkeypatch.setattr(repository, "get_measurements", _spy)

    _open_button(page, 0).click()

    assert calls == ["s1"]


# ---- No device dependency ---------------------------------------------------


def test_data_journal_page_has_no_device_manager_dependency() -> None:
    import inspect

    signature = inspect.signature(DataJournalPage.__init__)
    assert "device_manager" not in signature.parameters


# ---- Phase 32: shared workspace layout architecture -----------------------
#
# Root cause fixed here: ``results_layout.addStretch(1)`` was added AFTER
# ``self._table`` with the table itself given no stretch — the explicit
# spacer absorbed 100% of the container's leftover height instead of the
# table, producing "huge blank region below the table" on tall windows.
#
# Phase 17: бұл stretch-негізді тәсіл ЖАҢА бag тудырды (§ "толығымен бос
# репозиторий" күйінде title/hint белгілері арасына фантом саңылаулар,
# скриншот аудитінде табылған) — results_container ЕНДІ ``QStackedWidget``
# (кесте/empty-state екі БӨЛЕК парақ, DataJournalPage-тің ӨЗІ тізім/
# бөлшек ауысуы үшін қолданатын ДӘЛ СОЛ паттерн), stretch-қайта-бөлу
# мүлде жоқ.


def test_table_fills_results_stack_when_populated() -> None:
    repository = SqliteSessionRepository()
    repository.save_session(_make_session("s1"), _make_experiment_metadata())
    page = DataJournalPage(session_repository=repository)
    page.on_enter()

    assert page._results_stack.currentWidget() is page._table


def test_empty_state_widget_shown_when_repository_empty() -> None:
    page = DataJournalPage(session_repository=SqliteSessionRepository())
    page.show()
    page.on_enter()

    assert page._results_stack.currentWidget() is not page._table
    assert page._empty_state_title_label.isVisible() is True


def test_table_has_expanding_size_policy() -> None:
    page = DataJournalPage(session_repository=SqliteSessionRepository())
    policy = page._table.sizePolicy()
    assert policy.horizontalPolicy() == QSizePolicy.Policy.Expanding
    assert policy.verticalPolicy() == QSizePolicy.Policy.Expanding


# ---- Cell widget leak regression (setRowCount(0) alone does not delete
# QTableWidget cell widgets — see _render_list()) -----------------------------


def test_repeated_on_enter_does_not_leak_open_buttons() -> None:
    """Бетке қайта кіру (Router.navigate() арқылы on_enter() қайта
    шақырылғанда) әр рет "Ашу" батырмасының ЖАҢА данасын жасайды — ескі
    cell widget-тер viewport-та жасырын түрде жиналмауы керек
    (QTableWidget.setCellWidget()-пен орнатылған виджеттерге QTableWidget
    иелік етпейді, тек setRowCount(0) шақыру оларды объект ағашынан
    өшірмейді).
    """
    repository = SqliteSessionRepository()
    repository.save_session(_make_session("s1"), _make_experiment_metadata())
    page = DataJournalPage(session_repository=repository)

    for _ in range(5):
        page.on_enter()
        QApplication.processEvents()

    buttons = page._table.viewport().findChildren(QPushButton)
    assert len(buttons) == 1


def test_table_height_grows_with_window_height() -> None:
    """Pixel-perfect емес, тек РЕЛЯТИВТІ өсуді тексереді: терезе биіктеу
    болса, кесте де биіктеу болуы керек (артық биіктік бос орынға емес,
    кестеге ағуы тиіс).
    """
    repository = SqliteSessionRepository()
    repository.save_session(_make_session("s1"), _make_experiment_metadata())
    page = DataJournalPage(session_repository=repository)
    page.on_enter()
    page.show()

    page.resize(1366, 768)
    short_height = page._table.height()

    page.resize(1366, 1080)
    tall_height = page._table.height()

    assert tall_height > short_height


# =====================================================================
# Phase 17 ("Data Journal Audit + Safe Redesign"): сынып/оқушы/күні
# сүзгілері, іздеу, аралас сүзгілер, 2 бөлек бос күй, graph.
# =====================================================================


def _make_full_page(
    session_repository: SqliteSessionRepository | None = None,
    module_registry: ModuleRegistry | None = None,
) -> tuple[
    DataJournalPage, SqliteSessionRepository, SqliteClassroomRepository,
    SqliteStudentRepository, SqliteStudentProgressRepository,
]:
    session_repository = session_repository or SqliteSessionRepository()
    classroom_repository = SqliteClassroomRepository()
    student_repository = SqliteStudentRepository()
    progress_repository = SqliteStudentProgressRepository(
        session_repository=session_repository,
        classroom_repository=classroom_repository,
        student_repository=student_repository,
    )
    page = DataJournalPage(
        session_repository=session_repository,
        module_registry=module_registry,
        classroom_repository=classroom_repository,
        student_repository=student_repository,
        student_progress_repository=progress_repository,
    )
    return page, session_repository, classroom_repository, student_repository, progress_repository


def _setup_student(
    classroom_repository: SqliteClassroomRepository,
    student_repository: SqliteStudentRepository,
    classroom_id: str = "c1",
    classroom_name: str = "8А",
    student_id: str = "s1",
    first_name: str = "Айдос",
    last_name: str = "Серіков",
) -> None:
    if classroom_repository.get(classroom_id) is None:
        classroom_repository.create(
            Classroom(id=classroom_id, name=classroom_name, created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
        )
    student_repository.create(
        Student(id=student_id, classroom_id=classroom_id, first_name=first_name, last_name=last_name,
                created_at=_NOW, updated_at=_NOW),
        UserRole.TEACHER,
    )


# ---- Ескі тағайындалмаған сессия ---------------------------------------


def test_legacy_session_shows_unassigned_label() -> None:
    page, session_repository, _cr, _sr, _pr = _make_full_page()
    session_repository.save_session(_make_session("legacy1"), _make_experiment_metadata())

    page.on_enter()

    assert page._table.item(0, 2).text() == "Тағайындалмаған ескі сессия"


def test_legacy_session_label_uses_muted_color_not_error_color() -> None:
    from PySide6.QtGui import QColor

    from ui.themes.theme_manager import COLOR_ERROR, COLOR_TEXT_MUTED

    page, session_repository, _cr, _sr, _pr = _make_full_page()
    session_repository.save_session(_make_session("legacy1"), _make_experiment_metadata())
    page.on_enter()

    color = page._table.item(0, 2).foreground().color()

    assert color.name() == QColor(COLOR_TEXT_MUTED).name()
    assert color.name() != QColor(COLOR_ERROR).name()


def test_student_linked_session_displays_student_name() -> None:
    page, session_repository, classroom_repository, student_repository, progress_repository = (
        _make_full_page()
    )
    _setup_student(classroom_repository, student_repository)
    session_repository.save_session(_make_session("s1"), _make_experiment_metadata())
    progress_repository.link_session("s1", "s1", "c1", "ohms-law")

    page.on_enter()

    assert page._table.item(0, 2).text() == "Серіков Айдос"


def test_legacy_session_remains_visible_and_selectable() -> None:
    page, session_repository, _cr, _sr, _pr = _make_full_page()
    session_repository.save_session(_make_session("legacy1"), _make_experiment_metadata())
    page.on_enter()

    assert page._table.rowCount() == 1
    button = _open_button(page, 0)
    assert button.isEnabled()
    button.click()
    assert page._stack.currentIndex() == 1


# ---- Сынып сүзгісі -------------------------------------------------------


def _setup_two_classrooms_with_sessions(session_repository, classroom_repository, student_repository, progress_repository):
    _setup_student(classroom_repository, student_repository, classroom_id="c1", classroom_name="8А", student_id="s1", first_name="Айдос", last_name="Серіков")
    _setup_student(classroom_repository, student_repository, classroom_id="c2", classroom_name="9Б", student_id="s2", first_name="Дана", last_name="Қалиева")
    session_repository.save_session(_make_session("sess1"), _make_experiment_metadata())
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    session_repository.save_session(_make_session("sess2", started_offset_hours=1), _make_experiment_metadata())
    progress_repository.link_session("sess2", "s2", "c2", "ohms-law")
    session_repository.save_session(_make_session("legacy1", started_offset_hours=2), _make_experiment_metadata())


def test_classroom_filter_narrows_rows() -> None:
    page, session_repository, classroom_repository, student_repository, progress_repository = (
        _make_full_page()
    )
    _setup_two_classrooms_with_sessions(session_repository, classroom_repository, student_repository, progress_repository)
    page.on_enter()
    assert page._table.rowCount() == 3

    index = page._classroom_filter_combo.findData("c1")
    page._classroom_filter_combo.setCurrentIndex(index)

    assert page._table.rowCount() == 1
    assert page._table.item(0, 2).text() == "Серіков Айдос"


def test_classroom_filter_barlygy_restores_legacy_sessions() -> None:
    """§ "Filtering must not accidentally make legacy data permanently
    inaccessible" — "Барлығы" таңдалғанда ескі сессия қайта көрінеді."""
    page, session_repository, classroom_repository, student_repository, progress_repository = (
        _make_full_page()
    )
    _setup_two_classrooms_with_sessions(session_repository, classroom_repository, student_repository, progress_repository)
    page.on_enter()
    page._classroom_filter_combo.setCurrentIndex(page._classroom_filter_combo.findData("c1"))
    assert page._table.rowCount() == 1

    page._classroom_filter_combo.setCurrentIndex(0)

    assert page._table.rowCount() == 3


# ---- Сынып->Оқушы каскады -------------------------------------------------


def test_student_filter_cascades_from_classroom() -> None:
    page, session_repository, classroom_repository, student_repository, progress_repository = (
        _make_full_page()
    )
    _setup_two_classrooms_with_sessions(session_repository, classroom_repository, student_repository, progress_repository)
    page.on_enter()

    index = page._classroom_filter_combo.findData("c1")
    page._classroom_filter_combo.setCurrentIndex(index)

    student_names = [
        page._student_filter_combo.itemText(i) for i in range(page._student_filter_combo.count())
    ]
    assert student_names == ["Барлығы", "Серіков Айдос"]


def test_student_filter_narrows_rows() -> None:
    page, session_repository, classroom_repository, student_repository, progress_repository = (
        _make_full_page()
    )
    _setup_two_classrooms_with_sessions(session_repository, classroom_repository, student_repository, progress_repository)
    page.on_enter()

    index = page._student_filter_combo.findData("s2")
    page._student_filter_combo.setCurrentIndex(index)

    assert page._table.rowCount() == 1
    assert page._table.item(0, 2).text() == "Қалиева Дана"


# ---- Тәжірибе сүзгісі (бұрыннан бар, кеңейтілген комбинациямен) -----------


def test_experiment_filter_still_works_with_new_filters() -> None:
    repository = SqliteSessionRepository()
    repository.save_session(_make_session("ohms-1", experiment_id="ohms-law"), _make_experiment_metadata())
    repository.save_session(
        _make_session("cv-1", experiment_id="current-voltage"),
        _make_experiment_metadata(id_="current-voltage", title="Электр тізбегін құрастыру", display_number=3),
    )
    page = DataJournalPage(session_repository=repository)
    page.on_enter()
    assert page._table.rowCount() == 2

    index = page._filter_combo.findData("ohms-law")
    page._filter_combo.setCurrentIndex(index)

    assert page._table.rowCount() == 1


# ---- Күні сүзгісі ----------------------------------------------------


def test_date_filter_narrows_rows() -> None:
    repository = SqliteSessionRepository()
    repository.save_session(_make_session("today"), _make_experiment_metadata())
    repository.save_session(_make_session("yesterday", started_offset_hours=30), _make_experiment_metadata())
    page = DataJournalPage(session_repository=repository)
    page.on_enter()
    assert page._table.rowCount() == 2

    today_key = _NOW.astimezone().strftime("%d.%m.%Y")
    index = page._date_filter_combo.findData(today_key)
    page._date_filter_combo.setCurrentIndex(index)

    assert page._table.rowCount() == 1


# ---- Іздеу ------------------------------------------------------------


def test_search_filters_by_student_name() -> None:
    page, session_repository, classroom_repository, student_repository, progress_repository = (
        _make_full_page()
    )
    _setup_two_classrooms_with_sessions(session_repository, classroom_repository, student_repository, progress_repository)
    page.on_enter()

    page._search_edit.setText("дана")

    assert page._table.rowCount() == 1
    assert page._table.item(0, 2).text() == "Қалиева Дана"


def test_search_filters_by_classroom_name() -> None:
    page, session_repository, classroom_repository, student_repository, progress_repository = (
        _make_full_page()
    )
    _setup_two_classrooms_with_sessions(session_repository, classroom_repository, student_repository, progress_repository)
    page.on_enter()

    page._search_edit.setText("9Б")

    assert page._table.rowCount() == 1


# ---- Аралас сүзгілер ---------------------------------------------------


def test_combined_classroom_and_student_filters() -> None:
    page, session_repository, classroom_repository, student_repository, progress_repository = (
        _make_full_page()
    )
    _setup_two_classrooms_with_sessions(session_repository, classroom_repository, student_repository, progress_repository)
    page.on_enter()

    page._classroom_filter_combo.setCurrentIndex(page._classroom_filter_combo.findData("c1"))
    page._student_filter_combo.setCurrentIndex(page._student_filter_combo.findData("s1"))

    assert page._table.rowCount() == 1
    assert page._table.item(0, 2).text() == "Серіков Айдос"


# ---- Бос күйлер (2 бөлек себеп) ---------------------------------------


def test_empty_repository_state_uses_case_a_text() -> None:
    page = DataJournalPage(session_repository=SqliteSessionRepository())
    page.on_enter()

    assert page._empty_state_title_label.text() == "Әзірге сақталған өлшеу деректері жоқ."
    assert page._classroom_filter_combo.isHidden() is True


def test_filter_no_results_uses_case_b_text() -> None:
    repository = SqliteSessionRepository()
    repository.save_session(_make_session("s1"), _make_experiment_metadata())
    page = DataJournalPage(session_repository=repository)
    page.on_enter()

    page._search_edit.setText("zzzznotfound")

    assert page._empty_state_title_label.text() == "Сүзгіге сәйкес деректер табылмады."
    assert page._empty_state_title_label.text() != "Әзірге сақталған өлшеу деректері жоқ."
    # Сүзгілер ӨЗДЕРІ көрінуін жалғастыруы керек (§ репозиторийде дерек
    # бар, тек ФИЛЬТР нәтижесі бос).
    assert page._search_edit.isHidden() is False


# ---- Refresh дубликат жасамайды ----------------------------------------


def test_refresh_does_not_duplicate_rows() -> None:
    repository = SqliteSessionRepository()
    repository.save_session(_make_session("s1"), _make_experiment_metadata())
    page = DataJournalPage(session_repository=repository)
    page.on_enter()
    assert page._table.rowCount() == 1

    page._refresh_button.click()
    page._refresh_button.click()
    page._refresh_button.click()

    assert page._table.rowCount() == 1


def test_refresh_preserves_current_filter_selection() -> None:
    """§9 "Preserve sensible filters" — Жаңарту (refresh) қолмен
    таңдалған сүзгіні САҚТАЙДЫ, тек ``on_enter()`` (жаңа навигация) оны
    "Барлығы"-ға қайтарады."""
    page, session_repository, classroom_repository, student_repository, progress_repository = (
        _make_full_page()
    )
    _setup_two_classrooms_with_sessions(session_repository, classroom_repository, student_repository, progress_repository)
    page.on_enter()
    page._classroom_filter_combo.setCurrentIndex(page._classroom_filter_combo.findData("c1"))
    assert page._table.rowCount() == 1

    page._refresh_button.click()

    assert page._classroom_filter_combo.currentData() == "c1"
    assert page._table.rowCount() == 1


# ---- Graph нақты өлшеулерді қолданады ------------------------------------


def test_detail_graph_receives_real_measurements() -> None:
    repository = SqliteSessionRepository()
    repository.save_session(_make_session("s1", measurement_count=5), _make_experiment_metadata())
    page = DataJournalPage(session_repository=repository)
    page.on_enter()

    _open_button(page, 0).click()

    assert page._detail_graph is not None
    x_data = page._detail_graph._x_data
    assert any(len(values) > 0 for values in x_data.values())


def test_legacy_session_graph_still_works() -> None:
    """§7 "For a legacy session, graphing must work exactly the same if
    measurements exist"."""
    repository = SqliteSessionRepository()
    repository.save_session(_make_session("legacy1", measurement_count=5), _make_experiment_metadata())
    page = DataJournalPage(session_repository=repository)
    page.on_enter()

    _open_button(page, 0).click()

    x_data = page._detail_graph._x_data
    assert any(len(values) > 0 for values in x_data.values())


def test_detail_header_shows_student_and_classroom_when_assigned() -> None:
    page, session_repository, classroom_repository, student_repository, progress_repository = (
        _make_full_page()
    )
    _setup_student(classroom_repository, student_repository)
    session_repository.save_session(_make_session("s1"), _make_experiment_metadata())
    progress_repository.link_session("s1", "s1", "c1", "ohms-law")
    page.on_enter()

    _open_button(page, 0).click()

    assert "Серіков Айдос" in page._detail_meta_label.text()
    assert "8А" in page._detail_meta_label.text()


# ---- Жаңарту/browsing ешбір sessions-ты бұзбайды -------------------------


def test_browsing_does_not_mutate_session_count() -> None:
    repository = SqliteSessionRepository()
    repository.save_session(_make_session("s1"), _make_experiment_metadata())
    page = DataJournalPage(session_repository=repository)
    page.on_enter()
    _open_button(page, 0).click()
    page._detail_back_button.click()
    page._refresh_button.click()

    assert repository.count_sessions() == 1


# ---- Геометрия: 1366x768 overflow ЖОҚ -------------------------------------


def test_filter_row_fits_within_1366_width() -> None:
    page, session_repository, classroom_repository, student_repository, progress_repository = (
        _make_full_page()
    )
    _setup_two_classrooms_with_sessions(session_repository, classroom_repository, student_repository, progress_repository)
    page.on_enter()
    page.resize(1366 - 230, 768)
    page.show()

    assert page._search_edit.width() >= 100
