"""QuestionBankPage юнит-тесттері (Phase 20): таза есептеу қабаты
(``compute_kpis``/``filter_records``/``sort_records``) және Qt виджет
интеграциясы (бос күй, KPI, сүзгі, қосу/өңдеу/өшіру, валидация, route/
back-button, репозиторий изоляциясы).
"""

import sys
from datetime import datetime, timedelta, timezone

import pytest
from PySide6.QtWidgets import QApplication, QPushButton

from domain.entities.experiment_assessment import (
    MultipleChoiceQuestion,
    OpenResponseQuestion,
    ReflectionQuestion,
)
from domain.entities.experiment_definition import ExperimentDefinition
from domain.entities.question_record import QuestionRecord
from domain.entities.user_role import UserRole
from domain.interfaces.i_physics_module import IPhysicsModule
from infrastructure.storage.sqlite_question_repository import SqliteQuestionRepository
from modules.module_registry import ModuleRegistry
from ui.pages.question_bank_page import (
    QuestionBankPage,
    QuestionFormDialog,
    compute_kpis,
    filter_records,
    format_experiment_label,
    iter_catalog_experiments,
    sort_records,
)
from ui.themes.theme_manager import ThemeManager

_NOW = datetime.now(timezone.utc)
_OHMS_LAW = ExperimentDefinition(id="ohms-law", title="Ом заңы", description="", display_number=4)
_CURRENT_WORK = ExperimentDefinition(
    id="current-work", title="Ток жұмысы", description="", display_number=5
)


class _FakeModule(IPhysicsModule):
    def get_name(self) -> str:
        return "Электр құбылыстары"

    def get_icon(self) -> str | None:
        return "⚡"

    def get_experiments(self) -> tuple[ExperimentDefinition, ...]:
        return (_OHMS_LAW, _CURRENT_WORK)


def _mc_record(
    question_id="q1", experiment_id="ohms-law", level=1, prompt="Ток күші?",
    is_active=True, created_at=_NOW,
) -> QuestionRecord:
    return QuestionRecord(
        id=question_id, experiment_id=experiment_id, level=level,
        question=MultipleChoiceQuestion(
            id=question_id, prompt=prompt, options=("A", "B"), correct_option_index=0,
        ),
        is_active=is_active, created_at=created_at,
    )


# =====================================================================
# Таза есептеу қабаты
# =====================================================================


def test_compute_kpis_empty_state_shows_dash_average() -> None:
    kpis = compute_kpis(())

    assert kpis.total_text == "0"
    assert kpis.experiments_with_questions_text == "0"
    assert kpis.active_text == "0"
    assert kpis.average_text == "—"


def test_compute_kpis_total_includes_archived_but_active_excludes_them() -> None:
    records = (
        _mc_record("q1", is_active=True),
        _mc_record("q2", is_active=False),
    )

    kpis = compute_kpis(records)

    assert kpis.total_text == "2"
    assert kpis.active_text == "1"


def test_compute_kpis_experiments_with_questions_counts_only_active() -> None:
    """§4 "distinct catalog experiments that currently have at least one
    [active] question" — тек архивтелген сұрағы бар тәжірибе есептелмейді."""
    records = (
        _mc_record("q1", experiment_id="ohms-law", is_active=False),
        _mc_record("q2", experiment_id="current-work", is_active=True),
    )

    kpis = compute_kpis(records)

    assert kpis.experiments_with_questions_text == "1"


def test_compute_kpis_average_denominator_documented() -> None:
    records = (
        _mc_record("q1", experiment_id="ohms-law", is_active=True),
        _mc_record("q2", experiment_id="ohms-law", is_active=True),
        _mc_record("q3", experiment_id="current-work", is_active=True),
    )

    kpis = compute_kpis(records)

    assert kpis.average_text == "1.5"  # 3 белсенді / 2 тәжірибе


def test_filter_records_applies_all_filters_with_and_logic() -> None:
    records = (
        _mc_record("q1", experiment_id="ohms-law", level=1, prompt="Ток туралы сұрақ"),
        _mc_record("q2", experiment_id="ohms-law", level=2, prompt="Ток туралы сұрақ"),
        _mc_record("q3", experiment_id="current-work", level=1, prompt="Ток туралы сұрақ"),
    )

    filtered = filter_records(records, "ohms-law", 1, None, "ток")

    assert [r.id for r in filtered] == ["q1"]


def test_filter_records_search_is_case_insensitive() -> None:
    records = (_mc_record("q1", prompt="Ампер деген НЕ?"),)

    assert filter_records(records, None, None, None, "амп") == records
    assert filter_records(records, None, None, None, "АМП") == records


def test_filter_records_status_active_and_inactive() -> None:
    records = (
        _mc_record("q1", is_active=True),
        _mc_record("q2", is_active=False),
    )

    assert [r.id for r in filter_records(records, None, None, "active", "")] == ["q1"]
    assert [r.id for r in filter_records(records, None, None, "inactive", "")] == ["q2"]


def test_sort_records_by_display_number_then_level_then_created_at() -> None:
    experiments_by_id = {"ohms-law": _OHMS_LAW, "current-work": _CURRENT_WORK}
    t1 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    t2 = datetime(2026, 1, 2, tzinfo=timezone.utc)
    records = (
        _mc_record("cw-l1", experiment_id="current-work", level=1, created_at=t1),
        _mc_record("ol-l2", experiment_id="ohms-law", level=2, created_at=t1),
        _mc_record("ol-l1-new", experiment_id="ohms-law", level=1, created_at=t2),
        _mc_record("ol-l1-old", experiment_id="ohms-law", level=1, created_at=t1),
    )

    ordered = sort_records(records, experiments_by_id)

    assert [r.id for r in ordered] == ["ol-l1-old", "ol-l1-new", "ol-l2", "cw-l1"]


def test_sort_records_unknown_experiment_sorted_last() -> None:
    experiments_by_id = {"ohms-law": _OHMS_LAW}
    records = (
        _mc_record("unknown", experiment_id="ghost-experiment"),
        _mc_record("known", experiment_id="ohms-law"),
    )

    ordered = sort_records(records, experiments_by_id)

    assert [r.id for r in ordered] == ["known", "unknown"]


def test_format_experiment_label_uses_display_number() -> None:
    assert format_experiment_label(_OHMS_LAW) == "№4 Ом заңы"


def test_iter_catalog_experiments_reads_from_module_registry() -> None:
    registry = ModuleRegistry()
    registry.register(_FakeModule())

    experiments = iter_catalog_experiments(registry)

    assert experiments == (_OHMS_LAW, _CURRENT_WORK)


# =====================================================================
# Qt виджет интеграциясы
# =====================================================================


@pytest.fixture(scope="module", autouse=True)
def qt_application() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def _make_page() -> tuple[QuestionBankPage, SqliteQuestionRepository, ModuleRegistry]:
    question_repository = SqliteQuestionRepository()
    module_registry = ModuleRegistry()
    module_registry.register(_FakeModule())
    page = QuestionBankPage(question_repository=question_repository, module_registry=module_registry)
    return page, question_repository, module_registry


def test_page_has_no_back_button() -> None:
    page, _repo, _reg = _make_page()

    back_buttons = [b for b in page.findChildren(QPushButton) if b.text() == "← Артқа"]

    assert back_buttons == []


def test_page_title_is_first_top_level_layout_element() -> None:
    page, _repo, _reg = _make_page()

    first_widget = page.layout().itemAt(0).widget()

    assert first_widget.text() == "Сұрақтар банкі"


def test_empty_state_case_a_shown_when_no_questions_exist() -> None:
    page, _repo, _reg = _make_page()

    assert page._results_stack.currentWidget() is page._empty_state_widget
    assert page._empty_title_label.text() == "Сұрақтар әлі қосылмаған."


def test_empty_state_watermark_wrapper_uses_global_qss_not_instance_stylesheet() -> None:
    """§12 "Do not accidentally create an opaque root QWidget that hides
    the watermark" — ``QuestionBankEmptyState`` object-name арқылы
    ГЛОБАЛ (ThemeManager) селектормен мөлдір етіледі, instance-деңгейлік
    ``setStyleSheet()`` ЕМЕС (§ соңғысы ІШІНДЕГІ #PrimaryButton
    баласының ӨЗ фонын жоғалтатыны эмпирикалық түрде расталған,
    question_bank_page.py-дегі түсініктеме)."""
    page, _repo, _reg = _make_page()

    assert page._empty_state_widget.objectName() == "QuestionBankEmptyState"
    assert page._empty_state_widget.styleSheet() == ""
    assert "QuestionBankEmptyState" in ThemeManager().build_stylesheet()


def test_empty_state_add_button_keeps_primary_styling_inside_transparent_wrapper() -> None:
    """Регрессия сақтандыруы — дәл осы bag үшін: контейнер мөлдір
    болғанда, ІШІНДЕГІ #PrimaryButton батырмасы ӨЗ көк фонын/ақ мәтінін
    жоғалтпауы керек."""
    page, _repo, _reg = _make_page()

    assert page._empty_add_button.objectName() == "PrimaryButton"
    assert page._empty_add_button.styleSheet() == ""


def test_kpi_cards_reflect_seeded_questions() -> None:
    page, repository, _reg = _make_page()
    repository.create(_mc_record("q1", experiment_id="ohms-law"), UserRole.TEACHER)
    repository.create(_mc_record("q2", experiment_id="ohms-law"), UserRole.TEACHER)

    page.on_enter()

    assert page._value_labels["total"].text() == "2"
    assert page._value_labels["active"].text() == "2"
    assert page._value_labels["experiments"].text() == "1"


def test_experiment_filter_populated_from_module_registry_with_counts() -> None:
    page, repository, _reg = _make_page()
    repository.create(_mc_record("q1", experiment_id="ohms-law"), UserRole.TEACHER)

    page.on_enter()

    labels = [
        page._experiment_filter_combo.itemText(i)
        for i in range(page._experiment_filter_combo.count())
    ]
    assert "Барлығы" in labels
    assert any("Ом заңы" in label and "(1)" in label for label in labels)
    assert any("Ток жұмысы" in label and "(0)" in label for label in labels)


def test_level_filter_narrows_table_rows() -> None:
    page, repository, _reg = _make_page()
    repository.create(_mc_record("q1", level=1), UserRole.TEACHER)
    repository.create(
        QuestionRecord(
            id="q2", experiment_id="ohms-law", level=2,
            question=OpenResponseQuestion(id="q2", prompt="Талдау сұрағы"),
            is_active=True, created_at=_NOW,
        ),
        UserRole.TEACHER,
    )
    page.on_enter()

    level_index = page._level_filter_combo.findData(2)
    page._level_filter_combo.setCurrentIndex(level_index)

    assert page._table.rowCount() == 1
    assert page._table.item(0, 3).text() == "Талдау сұрағы"


def test_search_filters_by_question_text() -> None:
    page, repository, _reg = _make_page()
    repository.create(_mc_record("q1", prompt="Ток күші қандай?"), UserRole.TEACHER)
    repository.create(_mc_record("q2", prompt="Кернеу қандай?"), UserRole.TEACHER)
    page.on_enter()

    page._search_edit.setText("ток")

    assert page._table.rowCount() == 1


def test_filtered_empty_state_case_b_shown_for_zero_matches() -> None:
    page, repository, _reg = _make_page()
    repository.create(_mc_record("q1", prompt="Ток күші қандай?"), UserRole.TEACHER)
    page.on_enter()

    page._search_edit.setText("мүлдем сәйкессіз мәтін")

    assert page._results_stack.currentWidget() is page._empty_state_widget
    assert page._empty_title_label.text() == "Таңдалған сүзгіге сай сұрақтар табылмады."


def test_add_question_persists_and_refreshes_table() -> None:
    page, repository, _reg = _make_page()
    page.on_enter()

    dialog = QuestionFormDialog(iter_catalog_experiments(_module_registry_of(page)), existing=None, parent=page)
    dialog._experiment_combo.setCurrentIndex(dialog._experiment_combo.findData("ohms-law"))
    dialog._level_combo.setCurrentIndex(dialog._level_combo.findData(2))
    dialog._prompt_edit.setPlainText("Жаңа сұрақ мәтіні")
    experiment_id, level, question, is_active = dialog.get_values()
    repository.create(
        QuestionRecord(
            id=question.id, experiment_id=experiment_id, level=level,
            question=question, is_active=is_active, created_at=_NOW,
        ),
        UserRole.TEACHER,
    )
    page._refresh()

    assert page._value_labels["total"].text() == "1"
    assert page._table.item(0, 3).text() == "Жаңа сұрақ мәтіні"


def _module_registry_of(page: QuestionBankPage) -> ModuleRegistry:
    return page._module_registry


def test_question_form_dialog_rejects_empty_prompt() -> None:
    registry = ModuleRegistry()
    registry.register(_FakeModule())
    dialog = QuestionFormDialog(iter_catalog_experiments(registry), existing=None)
    dialog._level_combo.setCurrentIndex(dialog._level_combo.findData(2))
    dialog._prompt_edit.setPlainText("   ")

    from unittest.mock import patch

    with patch("ui.pages.question_bank_page.QMessageBox.warning") as mock_warning:
        dialog._on_accept_clicked()

    mock_warning.assert_called_once()


def test_question_form_dialog_rejects_level1_without_correct_answer_selected() -> None:
    registry = ModuleRegistry()
    registry.register(_FakeModule())
    dialog = QuestionFormDialog(iter_catalog_experiments(registry), existing=None)
    dialog._prompt_edit.setPlainText("1-деңгей сұрағы")
    for row in dialog._option_rows():
        row.text_edit.setText("Нұсқа мәтіні")
    dialog._options_group.setExclusive(False)
    for row in dialog._option_rows():
        row.radio.setChecked(False)
    dialog._options_group.setExclusive(True)

    from unittest.mock import patch

    with patch("ui.pages.question_bank_page.QMessageBox.warning") as mock_warning:
        dialog._on_accept_clicked()

    mock_warning.assert_called_once()


def test_question_form_dialog_edit_mode_preloads_existing_values() -> None:
    registry = ModuleRegistry()
    registry.register(_FakeModule())
    existing = _mc_record("q1", experiment_id="ohms-law", prompt="Бар сұрақ")
    dialog = QuestionFormDialog(iter_catalog_experiments(registry), existing=existing)

    assert dialog._prompt_edit.toPlainText() == "Бар сұрақ"
    assert dialog._experiment_combo.currentData() == "ohms-law"
    assert dialog.windowTitle() == "Сұрақты өзгерту"


def test_cancel_leaves_repository_unchanged() -> None:
    page, repository, _reg = _make_page()
    repository.create(_mc_record("q1"), UserRole.TEACHER)
    page.on_enter()
    before = repository.list_all(include_archived=True)

    dialog = QuestionFormDialog(iter_catalog_experiments(page._module_registry), existing=None, parent=page)
    dialog.reject()

    after = repository.list_all(include_archived=True)
    assert before == after


def test_delete_archives_instead_of_hard_deleting() -> None:
    """§10 "DO NOT hard-delete... archive/disable/soft-delete"."""
    page, repository, _reg = _make_page()
    repository.create(_mc_record("q1"), UserRole.TEACHER)

    repository.archive("q1", UserRole.TEACHER, archived=True)

    record = repository.get("q1")
    assert record is not None
    assert record.is_active is False


def test_editing_one_experiment_does_not_alter_another() -> None:
    """§16 "editing a question does not alter unrelated experiments"."""
    page, repository, _reg = _make_page()
    repository.create(_mc_record("q1", experiment_id="ohms-law", prompt="Ом заңы сұрағы"), UserRole.TEACHER)
    repository.create(_mc_record("q2", experiment_id="current-work", prompt="Ток жұмысы сұрағы"), UserRole.TEACHER)

    repository.update(
        QuestionRecord(
            id="q1", experiment_id="ohms-law", level=1,
            question=MultipleChoiceQuestion(id="q1", prompt="Өзгертілген сұрақ", options=("A", "B"), correct_option_index=1),
            is_active=True, created_at=_NOW,
        ),
        UserRole.TEACHER,
    )

    unrelated = repository.get("q2")
    assert unrelated.question.prompt == "Ток жұмысы сұрағы"


def test_stable_ordering_across_refresh_calls() -> None:
    page, repository, _reg = _make_page()
    t1 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    t2 = datetime(2026, 1, 2, tzinfo=timezone.utc)
    repository.create(_mc_record("q2", level=1, created_at=t2), UserRole.TEACHER)
    repository.create(_mc_record("q1", level=1, created_at=t1), UserRole.TEACHER)

    page.on_enter()
    first_pass_ids = [page._table.item(r, 3).text() for r in range(page._table.rowCount())]
    page.on_enter()
    second_pass_ids = [page._table.item(r, 3).text() for r in range(page._table.rowCount())]

    assert first_pass_ids == second_pass_ids
