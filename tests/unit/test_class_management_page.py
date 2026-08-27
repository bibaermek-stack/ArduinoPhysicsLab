"""ClassManagementPage юнит-тесттері: сынып/оқушы тізімдері, таңдау
синхрондауы, прогресс-шолу бағаны/сандары, Есеп/Кері байланыс
диалогтарын қайта пайдалану (дубликат рендерлеу жүйесі жоқ)."""

import sys
from datetime import datetime, timezone

import pytest
from PySide6.QtWidgets import QApplication, QPushButton

from domain.entities.classroom import Classroom
from domain.entities.experiment_definition import ExperimentDefinition, ExperimentReport
from domain.entities.experiment_feedback_result import ExperimentFeedbackResult
from domain.entities.experiment_session import ExperimentSession
from domain.entities.measurement import Measurement
from domain.entities.student import Student
from domain.entities.user_role import UserRole
from domain.interfaces.i_physics_module import IPhysicsModule
from infrastructure.storage.sqlite_classroom_repository import SqliteClassroomRepository
from infrastructure.storage.sqlite_feedback_repository import SqliteFeedbackRepository
from infrastructure.storage.sqlite_session_repository import SqliteSessionRepository
from infrastructure.storage.sqlite_student_progress_repository import SqliteStudentProgressRepository
from infrastructure.storage.sqlite_student_repository import SqliteStudentRepository
from modules.module_registry import ModuleRegistry
from ui.pages.class_management_page import ClassManagementPage

_NOW = datetime.now(timezone.utc)
_OHMS_LAW = ExperimentDefinition(
    id="ohms-law", title="Ом заңы", description="", display_number=4, report=ExperimentReport(),
)


class _FakeModule(IPhysicsModule):
    def get_name(self) -> str:
        return "Электр құбылыстары"

    def get_icon(self) -> str | None:
        return "⚡"

    def get_experiments(self) -> tuple[ExperimentDefinition, ...]:
        return (_OHMS_LAW,)


@pytest.fixture(scope="module", autouse=True)
def qt_application() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def _make_page() -> tuple[
    ClassManagementPage, SqliteClassroomRepository, SqliteStudentRepository,
    SqliteStudentProgressRepository, SqliteFeedbackRepository, SqliteSessionRepository,
]:
    classroom_repository = SqliteClassroomRepository()
    student_repository = SqliteStudentRepository()
    session_repository = SqliteSessionRepository()
    feedback_repository = SqliteFeedbackRepository()
    progress_repository = SqliteStudentProgressRepository(
        session_repository=session_repository, feedback_repository=feedback_repository,
        classroom_repository=classroom_repository, student_repository=student_repository,
    )
    module_registry = ModuleRegistry()
    module_registry.register(_FakeModule())

    page = ClassManagementPage(
        classroom_repository=classroom_repository,
        student_repository=student_repository,
        student_progress_repository=progress_repository,
        feedback_repository=feedback_repository,
        session_repository=session_repository,
        module_registry=module_registry,
    )
    return page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository


def _save_measured_session(session_repository: SqliteSessionRepository, session_id: str) -> None:
    session = ExperimentSession(id=session_id, experiment_id="ohms-law", started_at=_NOW)
    session.add_measurement(
        Measurement(timestamp=_NOW, values={"voltage": 5.0}, experiment_id="ohms-law")
    )
    session_repository.save_session(session)


def test_empty_state_has_no_classrooms() -> None:
    page, _classrooms, _students, _progress, _feedback, _sessions = _make_page()
    assert page._classroom_list.count() == 0
    assert page._detail_hint_label.isHidden() is False


def test_classroom_list_reflects_repository() -> None:
    """Phase 14: сынып атауы ЕНДІ ``QListWidgetItem.text()``-те ЕМЕС (§
    setItemWidget() итем мәтінін жасырмайды — қос рендер регрессиясынан
    сақтану үшін item.text() бос қалдырылады), нақты көрсетілетін атау
    ``_ClassroomRowWidget.name_label``-де."""
    page, classroom_repository, _students, _progress, _feedback, _sessions = _make_page()

    classroom_repository.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    page.on_enter()

    assert page._classroom_list.count() == 1
    row_widget = page._classroom_list.itemWidget(page._classroom_list.item(0))
    assert row_widget.name_label.text() == "8А"


def test_archived_classroom_marked_in_list() -> None:
    page, classroom_repository, _students, _progress, _feedback, _sessions = _make_page()
    classroom_repository.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    classroom_repository.archive("c1", UserRole.TEACHER)

    page.on_enter()

    row_widget = page._classroom_list.itemWidget(page._classroom_list.item(0))
    assert "мұрағатталған" in row_widget.name_label.text()


def test_selecting_classroom_populates_student_list() -> None:
    page, classroom_repository, student_repository, _progress, _feedback, _sessions = _make_page()
    classroom_repository.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    student_repository.create(
        Student(id="s1", classroom_id="c1", first_name="Айдос", last_name="Серіков",
                created_at=_NOW, updated_at=_NOW),
        UserRole.TEACHER,
    )
    page.on_enter()

    assert page._student_list.count() == 1
    assert page._student_list.item(0).text() == "Серіков Айдос"


def test_selecting_student_shows_detail_panel() -> None:
    page, classroom_repository, student_repository, _progress, _feedback, _sessions = _make_page()
    classroom_repository.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    student_repository.create(
        Student(id="s1", classroom_id="c1", first_name="Айдос", last_name="Серіков",
                created_at=_NOW, updated_at=_NOW),
        UserRole.TEACHER,
    )
    page.on_enter()

    assert page._detail_hint_label.isHidden() is True
    assert page._student_name_label.text() == "Серіков Айдос"
    assert page._progress_table.rowCount() == 1  # каталогта 1 тәжірибе


def test_progress_counts_reflect_real_status() -> None:
    """Phase 14: жинақы 4-cell summary — ескі бір ``_counts_label``
    жолы ЕНДІ ``_stat_value_labels`` сөздігіне ауыстырылды (§ "Replace
    the current compressed inline text... with a compact visual
    summary")."""
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    classroom_repository.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    student_repository.create(
        Student(id="s1", classroom_id="c1", first_name="Айдос", last_name="Серіков",
                created_at=_NOW, updated_at=_NOW),
        UserRole.TEACHER,
    )
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")

    page.on_enter()

    assert page._stat_value_labels["completed"].text() == "0"
    assert page._stat_value_labels["not_started"].text() == "0"


def test_report_action_opens_report_dialog_reusing_existing_widget() -> None:
    page, classroom_repository, student_repository, progress_repository, _feedback, session_repository = (
        _make_page()
    )
    classroom_repository.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    student_repository.create(
        Student(id="s1", classroom_id="c1", first_name="Айдос", last_name="Серіков",
                created_at=_NOW, updated_at=_NOW),
        UserRole.TEACHER,
    )
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    page.on_enter()

    progress = progress_repository.get_progress("s1", "ohms-law")
    page._on_open_report_clicked(_OHMS_LAW, progress)

    from ui.widgets.experiment_report_dialog import ExperimentReportDialog

    assert isinstance(page._report_dialog, ExperimentReportDialog)
    page._report_dialog.close()


def test_feedback_action_persists_teacher_assessment() -> None:
    from domain.entities.experiment_assessment import ExperimentAssessmentDefinition, MultipleChoiceQuestion
    from domain.entities.experiment_feedback_result import TeacherAssessment

    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    assessment = ExperimentAssessmentDefinition(
        level1_questions=(MultipleChoiceQuestion(id="q1", prompt="?", options=("a", "b"), correct_option_index=0),),
        level2_questions=(), level3_questions=(),
    )
    experiment = ExperimentDefinition(
        id="ohms-law", title="Ом заңы", description="", report=ExperimentReport(), assessment=assessment,
    )
    classroom_repository.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    student_repository.create(
        Student(id="s1", classroom_id="c1", first_name="Айдос", last_name="Серіков",
                created_at=_NOW, updated_at=_NOW),
        UserRole.TEACHER,
    )
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    page.on_enter()

    progress = progress_repository.get_progress("s1", "ohms-law")
    page._on_open_feedback_clicked(experiment, progress)
    page._on_feedback_teacher_assessment_saved("sess1", "ohms-law", TeacherAssessment(score=8, comment="Жақсы"))

    result = feedback_repository.get_result("sess1")
    assert result.teacher_assessment.score == 8
    page._feedback_dialog.close()


def test_repeated_on_enter_does_not_leak_progress_action_buttons() -> None:
    """Бетке қайта кіру (Router.navigate() арқылы on_enter() қайта
    шақырылғанда) прогресс кестесінің әрекет батырмалары (Есепті ашу/
    Кері байланысты ашу/Бағалау) әр рет ЖАҢА данамен ауыстырылуы керек —
    ескі cell widget-тер viewport-та жасырын түрде жиналмауы тиіс
    (§ DataJournalPage._render_list()-те расталған дәл осындай bug).
    """
    page, classroom_repository, student_repository, progress_repository, _feedback, session_repository = (
        _make_page()
    )
    classroom_repository.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    student_repository.create(
        Student(id="s1", classroom_id="c1", first_name="Айдос", last_name="Серіков",
                created_at=_NOW, updated_at=_NOW),
        UserRole.TEACHER,
    )
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")

    for _ in range(5):
        page.on_enter()
        QApplication.processEvents()

    buttons = page._progress_table.viewport().findChildren(QPushButton)
    assert len(buttons) == 3  # Есепті ашу + Кері байланысты ашу + Бағалау (1 жол)


# =====================================================================
# Phase 14 — "Classes & Students Page Polish"
# =====================================================================


def test_classroom_header_shows_real_count() -> None:
    page, classroom_repository, _students, _progress, _feedback, _sessions = _make_page()
    classroom_repository.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    classroom_repository.create(
        Classroom(id="c2", name="9А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )

    page.on_enter()

    assert page._classroom_header_label.text() == "Сыныптар · 2"


def test_student_header_shows_real_count_for_selected_classroom() -> None:
    page, classroom_repository, student_repository, _progress, _feedback, _sessions = _make_page()
    classroom_repository.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    for i in range(3):
        student_repository.create(
            Student(id=f"s{i}", classroom_id="c1", first_name=f"Аты{i}", last_name="Т",
                    created_at=_NOW, updated_at=_NOW),
            UserRole.TEACHER,
        )

    page.on_enter()

    assert page._student_header_label.text() == "Оқушылар · 3"


def test_classroom_row_shows_real_student_count() -> None:
    page, classroom_repository, student_repository, _progress, _feedback, _sessions = _make_page()
    classroom_repository.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    for i in range(4):
        student_repository.create(
            Student(id=f"s{i}", classroom_id="c1", first_name=f"Аты{i}", last_name="Т",
                    created_at=_NOW, updated_at=_NOW),
            UserRole.TEACHER,
        )

    page.on_enter()

    row_widget = page._classroom_list.itemWidget(page._classroom_list.item(0))
    assert row_widget.count_label.text() == "4"


def test_classroom_accent_matches_phase13_deterministic_mapping() -> None:
    """§11 "CLASSROOM COLOR CONSISTENCY" — ЖАЛҒЫЗ ``classroom_accent_color()``
    Teacher Dashboard-та ҚОЛДАНЫЛАТЫН ДӘЛ СОЛ функциямен есептеледі
    (импорт, дубликат ЕМЕС)."""
    from ui.widgets.class_activity_carousel import classroom_accent_color

    page, classroom_repository, _students, _progress, _feedback, _sessions = _make_page()
    classroom_repository.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )

    page.on_enter()

    row_widget = page._classroom_list.itemWidget(page._classroom_list.item(0))
    expected = classroom_accent_color("c1", "8А")
    assert row_widget._accent_color == expected


def test_no_duplicate_classroom_color_mapping_module() -> None:
    """§11: ``class_management_page``-де ӨЗ classroom_accent_color()
    анықтамасы ЖОҚ — ол тек ``class_activity_carousel``-ден import
    етіледі (§ модуль деңгейінде бірегей "ащы шындық" функциясы)."""
    import ui.pages.class_management_page as class_management_module
    from ui.widgets.class_activity_carousel import classroom_accent_color as canonical

    assert class_management_module.classroom_accent_color is canonical


def test_selected_classroom_badge_uses_correct_accent() -> None:
    from ui.widgets.class_activity_carousel import classroom_accent_color

    page, classroom_repository, student_repository, _progress, _feedback, _sessions = _make_page()
    classroom_repository.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    student_repository.create(
        Student(id="s1", classroom_id="c1", first_name="Айдос", last_name="Серіков",
                created_at=_NOW, updated_at=_NOW),
        UserRole.TEACHER,
    )

    page.on_enter()

    accent = classroom_accent_color("c1", "8А")
    assert accent in page._classroom_name_label.styleSheet()
    assert page._classroom_name_label.text() == "8А"


def test_progress_summary_stat_cells_reflect_real_counts() -> None:
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    classroom_repository.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    student_repository.create(
        Student(id="s1", classroom_id="c1", first_name="Айдос", last_name="Серіков",
                created_at=_NOW, updated_at=_NOW),
        UserRole.TEACHER,
    )
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")

    page.on_enter()

    assert page._stat_value_labels["total"].text() == "1"
    assert page._stat_value_labels["completed"].text() == "0"
    assert page._stat_value_labels["in_progress"].text() == "0"
    assert page._stat_value_labels["not_started"].text() == "0"
    assert "Тексеруді күтуде: 0" in page._review_counts_label.text()
    assert "Тексерілді: 0" in page._review_counts_label.text()


def test_overall_progress_percentage_calculation() -> None:
    """§6: ``completed / total * 100``, "Аяқталған" — осы беттің ӨЗ,
    бұрыннан бар REVIEWED анықтамасымен (§ "Do not invent a second
    completion definition")."""
    from domain.entities.experiment_feedback_result import TeacherAssessment

    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    classroom_repository.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    student_repository.create(
        Student(id="s1", classroom_id="c1", first_name="Айдос", last_name="Серіков",
                created_at=_NOW, updated_at=_NOW),
        UserRole.TEACHER,
    )
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    feedback_repository.save_submission(
        ExperimentFeedbackResult(experiment_id="ohms-law", session_id="sess1", is_draft=False, submitted_at=_NOW)
    )
    feedback_repository.save_teacher_assessment(
        "sess1", "ohms-law", TeacherAssessment(score=9, comment="Жақсы"), UserRole.TEACHER
    )

    page.on_enter()

    # 1 тәжірибе каталогта, соның бірі REVIEWED -> 100%.
    assert page._overall_progress_bar.value() == 100
    assert page._overall_progress_percentage_label.text() == "100%"


def test_overall_progress_zero_total_is_safe() -> None:
    """§6/§7 регрессия-қорғаныс: каталогта тіпті тәжірибе жоқ болса
    (edge case), ZeroDivisionError ЕШҚАШАН шықпайды, 0% көрсетіледі."""
    classroom_repository = SqliteClassroomRepository()
    student_repository = SqliteStudentRepository()
    session_repository = SqliteSessionRepository()
    feedback_repository = SqliteFeedbackRepository()
    progress_repository = SqliteStudentProgressRepository(
        session_repository=session_repository, feedback_repository=feedback_repository,
        classroom_repository=classroom_repository, student_repository=student_repository,
    )
    empty_module_registry = ModuleRegistry()  # ешбір модуль тіркелмеген
    page = ClassManagementPage(
        classroom_repository=classroom_repository,
        student_repository=student_repository,
        student_progress_repository=progress_repository,
        feedback_repository=feedback_repository,
        session_repository=session_repository,
        module_registry=empty_module_registry,
    )
    classroom_repository.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    student_repository.create(
        Student(id="s1", classroom_id="c1", first_name="Айдос", last_name="Серіков",
                created_at=_NOW, updated_at=_NOW),
        UserRole.TEACHER,
    )

    page.on_enter()  # ешбір exception шықпауы керек

    assert page._overall_progress_bar.value() == 0
    assert page._overall_progress_percentage_label.text() == "0%"
    assert page._progress_empty_label.isHidden() is False
    assert page._progress_table.isHidden() is True


def test_existing_progress_statuses_still_all_represented() -> None:
    """§7 "Preserve... state/status" — Phase 14 БАРЛЫҚ 6 ``ProgressStatus``
    мәнін жоғалтпайды (тек статус мәтінінің түсі қосылды)."""
    from domain.entities.student_experiment_progress import ProgressStatus
    from ui.pages.class_management_page import _STATUS_COLOR, _STATUS_TEXT

    for status in ProgressStatus:
        assert status in _STATUS_TEXT
        assert status in _STATUS_COLOR


def test_search_still_filters_student_list() -> None:
    page, classroom_repository, student_repository, _progress, _feedback, _sessions = _make_page()
    classroom_repository.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    student_repository.create(
        Student(id="s1", classroom_id="c1", first_name="Айдос", last_name="Серіков",
                created_at=_NOW, updated_at=_NOW),
        UserRole.TEACHER,
    )
    student_repository.create(
        Student(id="s2", classroom_id="c1", first_name="Ерлан", last_name="Қасымов",
                created_at=_NOW, updated_at=_NOW),
        UserRole.TEACHER,
    )
    page.on_enter()
    assert page._student_list.count() == 2

    page._search_edit.setText("Ерлан")

    assert page._student_list.count() == 1
    assert page._student_list.item(0).text() == "Қасымов Ерлан"


def test_add_student_button_disabled_without_classroom_selection() -> None:
    page, _classrooms, _students, _progress, _feedback, _sessions = _make_page()

    assert page._add_student_button.isEnabled() is False


def test_add_student_button_enabled_after_classroom_selected() -> None:
    page, classroom_repository, _students, _progress, _feedback, _sessions = _make_page()
    classroom_repository.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )

    page.on_enter()

    assert page._add_student_button.isEnabled() is True


def test_classroom_edit_archive_disabled_without_selection() -> None:
    page, _classrooms, _students, _progress, _feedback, _sessions = _make_page()

    assert page._edit_classroom_button.isEnabled() is False
    assert page._archive_classroom_button.isEnabled() is False


def test_classroom_edit_archive_enabled_after_selection() -> None:
    page, classroom_repository, _students, _progress, _feedback, _sessions = _make_page()
    classroom_repository.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )

    page.on_enter()

    assert page._edit_classroom_button.isEnabled() is True
    assert page._archive_classroom_button.isEnabled() is True


def test_student_edit_archive_disabled_without_selection() -> None:
    page, classroom_repository, _students, _progress, _feedback, _sessions = _make_page()
    classroom_repository.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )

    page.on_enter()  # сынып бар, бірақ оқушы жоқ -> ешбір оқушы таңдалмайды

    assert page._edit_student_button.isEnabled() is False
    assert page._archive_student_button.isEnabled() is False


def test_student_edit_archive_enabled_after_selection() -> None:
    page, classroom_repository, student_repository, _progress, _feedback, _sessions = _make_page()
    classroom_repository.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    student_repository.create(
        Student(id="s1", classroom_id="c1", first_name="Айдос", last_name="Серіков",
                created_at=_NOW, updated_at=_NOW),
        UserRole.TEACHER,
    )

    page.on_enter()

    assert page._edit_student_button.isEnabled() is True
    assert page._archive_student_button.isEnabled() is True


def test_empty_classroom_list_shows_hint_and_hides_list() -> None:
    page, _classrooms, _students, _progress, _feedback, _sessions = _make_page()

    assert page._classroom_empty_label.isHidden() is False
    assert page._classroom_list.isHidden() is True
    assert page._classroom_empty_label.text() == "Сыныптар әлі қосылмаған"


def test_classroom_with_no_students_shows_hint() -> None:
    page, classroom_repository, _students, _progress, _feedback, _sessions = _make_page()
    classroom_repository.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )

    page.on_enter()

    assert page._student_empty_label.isHidden() is False
    assert page._student_empty_label.text() == "Бұл сыныпта оқушылар жоқ"


def test_search_no_results_shows_distinct_hint() -> None:
    page, classroom_repository, student_repository, _progress, _feedback, _sessions = _make_page()
    classroom_repository.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    student_repository.create(
        Student(id="s1", classroom_id="c1", first_name="Айдос", last_name="Серіков",
                created_at=_NOW, updated_at=_NOW),
        UserRole.TEACHER,
    )
    page.on_enter()

    page._search_edit.setText("Мүлдем-табылмайтын-сұрау")

    assert page._student_empty_label.isHidden() is False
    assert page._student_empty_label.text() == "Іздеу нәтижесі табылмады"


def test_classroom_switching_refreshes_student_list() -> None:
    page, classroom_repository, student_repository, _progress, _feedback, _sessions = _make_page()
    classroom_repository.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    classroom_repository.create(
        Classroom(id="c2", name="9А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    student_repository.create(
        Student(id="s1", classroom_id="c1", first_name="Айдос", last_name="Серіков",
                created_at=_NOW, updated_at=_NOW),
        UserRole.TEACHER,
    )
    student_repository.create(
        Student(id="s2", classroom_id="c2", first_name="Ерлан", last_name="Қасымов",
                created_at=_NOW, updated_at=_NOW),
        UserRole.TEACHER,
    )
    page.on_enter()
    assert page._student_list.item(0).text() == "Серіков Айдос"

    page._classroom_list.setCurrentRow(1)

    assert page._student_list.count() == 1
    assert page._student_list.item(0).text() == "Қасымов Ерлан"


def test_student_switching_refreshes_detail_panel() -> None:
    page, classroom_repository, student_repository, _progress, _feedback, _sessions = _make_page()
    classroom_repository.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    student_repository.create(
        Student(id="s1", classroom_id="c1", first_name="Айдос", last_name="Серіков",
                created_at=_NOW, updated_at=_NOW),
        UserRole.TEACHER,
    )
    student_repository.create(
        Student(id="s2", classroom_id="c1", first_name="Ерлан", last_name="Қасымов",
                created_at=_NOW, updated_at=_NOW),
        UserRole.TEACHER,
    )
    page.on_enter()
    assert page._student_name_label.text() == "Серіков Айдос"

    page._student_list.setCurrentRow(1)

    assert page._student_name_label.text() == "Қасымов Ерлан"


# =====================================================================
# Mode Switch + Student Access Screen Redesign: teacher-side access code
# =====================================================================


def test_selected_student_detail_shows_access_code() -> None:
    page, classroom_repository, student_repository, _progress, _feedback, _sessions = _make_page()
    classroom_repository.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    student_repository.create(
        Student(id="s1", classroom_id="c1", first_name="Айдос", last_name="Серіков",
                created_at=_NOW, updated_at=_NOW, student_code="482731"),
        UserRole.TEACHER,
    )

    page.on_enter()

    assert page._student_code_label.text() == "Кіру коды: 482731"
    assert page._copy_code_button.isVisibleTo(page)
    assert page._regenerate_code_button.isVisibleTo(page)


def test_no_student_selection_hides_code_actions() -> None:
    page, classroom_repository, _students, _progress, _feedback, _sessions = _make_page()
    classroom_repository.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )

    page.on_enter()  # сынып бар, оқушы жоқ -> ешбір оқушы таңдалмайды

    assert page._student_code_label.text() == ""
    assert not page._copy_code_button.isVisibleTo(page)
    assert not page._regenerate_code_button.isVisibleTo(page)


def test_copy_code_action_copies_exact_code_to_clipboard() -> None:
    page, classroom_repository, student_repository, _progress, _feedback, _sessions = _make_page()
    classroom_repository.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    student_repository.create(
        Student(id="s1", classroom_id="c1", first_name="Айдос", last_name="Серіков",
                created_at=_NOW, updated_at=_NOW, student_code="482731"),
        UserRole.TEACHER,
    )
    page.on_enter()

    page._on_copy_code_clicked()

    assert QApplication.clipboard().text() == "482731"


def test_regenerate_code_requires_confirmation(monkeypatch: pytest.MonkeyPatch) -> None:
    page, classroom_repository, student_repository, _progress, _feedback, _sessions = _make_page()
    classroom_repository.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    student_repository.create(
        Student(id="s1", classroom_id="c1", first_name="Айдос", last_name="Серіков",
                created_at=_NOW, updated_at=_NOW, student_code="482731"),
        UserRole.TEACHER,
    )
    page.on_enter()
    monkeypatch.setattr(
        "ui.pages.class_management_page.confirm_regenerate_code", lambda parent: False
    )

    page._on_regenerate_code_clicked()

    assert student_repository.get("s1").student_code == "482731"


def test_regenerate_code_replaces_old_code_and_old_code_stops_resolving(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page, classroom_repository, student_repository, _progress, _feedback, _sessions = _make_page()
    classroom_repository.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    student_repository.create(
        Student(id="s1", classroom_id="c1", first_name="Айдос", last_name="Серіков",
                created_at=_NOW, updated_at=_NOW, student_code="482731"),
        UserRole.TEACHER,
    )
    page.on_enter()
    monkeypatch.setattr(
        "ui.pages.class_management_page.confirm_regenerate_code", lambda parent: True
    )

    page._on_regenerate_code_clicked()

    new_code = student_repository.get("s1").student_code
    assert new_code != "482731"
    assert student_repository.get_by_code("482731") is None
    assert student_repository.get_by_code(new_code).id == "s1"
    assert page._student_code_label.text() == f"Кіру коды: {new_code}"


def test_new_student_creation_auto_fills_generated_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from PySide6.QtWidgets import QDialog

    from ui.pages.class_management_page import _StudentFormDialog

    page, classroom_repository, student_repository, _progress, _feedback, _sessions = _make_page()
    classroom_repository.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    page.on_enter()

    captured_codes: list[str] = []

    def _fake_exec(self: _StudentFormDialog) -> int:
        captured_codes.append(self._code_edit.text())
        self._first_name_edit.setText("Данияр")
        self._last_name_edit.setText("Омаров")
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(_StudentFormDialog, "exec", _fake_exec)

    page._on_add_student_clicked()

    assert len(captured_codes[0]) == 6
    assert captured_codes[0].isdigit()
    created_student = next(
        s for s in student_repository.list_by_classroom("c1") if s.first_name == "Данияр"
    )
    assert created_student.student_code == captured_codes[0]
