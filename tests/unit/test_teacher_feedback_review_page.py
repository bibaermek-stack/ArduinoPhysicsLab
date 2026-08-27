"""TeacherFeedbackReviewPage юнит-тесттері (Phase 40): барлық сынып/оқушы
бойынша жіберілген есептердің жалпақ тексеру кезегі — бос күй, бірнеше
есеп, сүзгі/іздеу/сұрыптау, тексеру статусы, Есепті ашу/Бағалау
батырмалары (диалогтарды қайта пайдалану, дублирленген рендеринг ЖОҚ),
рұқсат/регрессия тесттері.
"""

import sys
from datetime import datetime, timedelta, timezone

import pytest
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QPushButton

from domain.entities.classroom import Classroom
from domain.entities.experiment_assessment import ExperimentAssessmentDefinition, MultipleChoiceQuestion
from domain.entities.experiment_definition import ExperimentDefinition, ExperimentReport
from domain.entities.experiment_feedback_result import ExperimentFeedbackResult, TeacherAssessment
from domain.entities.experiment_session import ExperimentSession
from domain.entities.measurement import Measurement
from domain.entities.student import Student
from domain.entities.student_experiment_progress import ProgressStatus
from domain.entities.user_role import UserRole
from domain.interfaces.i_physics_module import IPhysicsModule
from infrastructure.storage.sqlite_classroom_repository import SqliteClassroomRepository
from infrastructure.storage.sqlite_feedback_repository import SqliteFeedbackRepository
from infrastructure.storage.sqlite_session_repository import SqliteSessionRepository
from infrastructure.storage.sqlite_student_progress_repository import SqliteStudentProgressRepository
from infrastructure.storage.sqlite_student_repository import SqliteStudentRepository
from modules.module_registry import ModuleRegistry
from ui.pages.teacher_feedback_review_page import TeacherFeedbackReviewPage

_NOW = datetime.now(timezone.utc)
_ASSESSMENT = ExperimentAssessmentDefinition(
    level1_questions=(MultipleChoiceQuestion(id="q1", prompt="?", options=("a", "b"), correct_option_index=0),),
    level2_questions=(), level3_questions=(),
)
_OHMS_LAW = ExperimentDefinition(
    id="ohms-law", title="Ом заңы", description="", display_number=4,
    report=ExperimentReport(), assessment=_ASSESSMENT,
)
_CURRENT_WORK = ExperimentDefinition(
    id="current-work", title="Ток жұмысы", description="", display_number=5,
    report=ExperimentReport(), assessment=_ASSESSMENT,
)


class _FakeModule(IPhysicsModule):
    def get_name(self) -> str:
        return "Электр құбылыстары"

    def get_icon(self) -> str | None:
        return "⚡"

    def get_experiments(self) -> tuple[ExperimentDefinition, ...]:
        return (_OHMS_LAW, _CURRENT_WORK)


@pytest.fixture(scope="module", autouse=True)
def qt_application() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def _make_page() -> tuple[
    TeacherFeedbackReviewPage, SqliteClassroomRepository, SqliteStudentRepository,
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

    page = TeacherFeedbackReviewPage(
        classroom_repository=classroom_repository,
        student_repository=student_repository,
        student_progress_repository=progress_repository,
        feedback_repository=feedback_repository,
        session_repository=session_repository,
        module_registry=module_registry,
    )
    return page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository


def _save_measured_session(
    session_repository: SqliteSessionRepository, session_id: str, experiment_id: str = "ohms-law"
) -> None:
    session = ExperimentSession(id=session_id, experiment_id=experiment_id, started_at=_NOW)
    session.add_measurement(
        Measurement(timestamp=_NOW, values={"voltage": 5.0}, experiment_id=experiment_id)
    )
    session_repository.save_session(session)


def _submit_feedback(
    feedback_repository: SqliteFeedbackRepository,
    session_id: str,
    experiment_id: str = "ohms-law",
    submitted_at: datetime | None = None,
) -> None:
    feedback_repository.save_submission(
        ExperimentFeedbackResult(
            experiment_id=experiment_id, session_id=session_id, is_draft=False,
            submitted_at=submitted_at,
        )
    )


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


# ---- Бос күй ---------------------------------------------------------------


def test_empty_state_shown_when_no_submissions() -> None:
    page, _classrooms, _students, _progress, _feedback, _sessions = _make_page()

    assert page._empty_state_title_label.isHidden() is False
    assert page._table.isHidden() is True
    assert page._value_labels["total_submitted"].text() == "0"
    assert page._value_labels["waiting"].text() == "0"
    assert page._value_labels["reviewed"].text() == "0"


def test_measurement_completed_without_submission_is_excluded() -> None:
    """Тек өлшеу аяқталған (кері байланыс әлі жіберілмеген) жазба
    кезекте ЕШҚАШАН көрінбеуі тиіс — тек НАҚТЫ жіберілген есептер.
    """
    page, classroom_repository, student_repository, progress_repository, _feedback, session_repository = (
        _make_page()
    )
    _setup_student(classroom_repository, student_repository)
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")

    page.on_enter()

    assert page._table.rowCount() == 0
    assert page._value_labels["total_submitted"].text() == "0"


# ---- Тізім/статус ------------------------------------------------------


def test_submitted_report_appears_waiting_for_review() -> None:
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _setup_student(classroom_repository, student_repository)
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    _submit_feedback(feedback_repository, "sess1")

    page.on_enter()

    assert page._table.rowCount() == 1
    assert page._table.item(0, 0).text() == "Серіков Айдос"
    assert page._table.item(0, 1).text() == "8А"
    assert page._table.item(0, 2).text() == "Ом заңы"
    assert page._table.item(0, 4).text() == "Тексеруді күтуде"
    assert page._value_labels["total_submitted"].text() == "1"
    assert page._value_labels["waiting"].text() == "1"
    assert page._value_labels["reviewed"].text() == "0"


def test_reviewed_report_shows_teacher_score_and_status() -> None:
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _setup_student(classroom_repository, student_repository)
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    _submit_feedback(feedback_repository, "sess1")
    feedback_repository.save_teacher_assessment(
        "sess1", "ohms-law", TeacherAssessment(score=8, comment="Жақсы"), UserRole.TEACHER
    )

    page.on_enter()

    assert page._table.item(0, 4).text() == "Тексерілді"
    assert page._table.item(0, 5).text() == "8"
    assert page._value_labels["waiting"].text() == "0"
    assert page._value_labels["reviewed"].text() == "1"


# ---- Іздеу ------------------------------------------------------------


def test_search_filters_by_student_name() -> None:
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _setup_student(classroom_repository, student_repository)
    _setup_student(
        classroom_repository, student_repository, classroom_id="c1", classroom_name="8А",
        student_id="s2", first_name="Дана", last_name="Қалиева",
    )
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    _submit_feedback(feedback_repository, "sess1")
    progress_repository.link_session("sess2", "s2", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess2")
    _submit_feedback(feedback_repository, "sess2")
    page.on_enter()

    page._search_edit.setText("Дана")

    assert page._table.rowCount() == 1
    assert page._table.item(0, 0).text() == "Қалиева Дана"


def test_search_filters_by_classroom_name() -> None:
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _setup_student(classroom_repository, student_repository, classroom_id="c1", classroom_name="8А", student_id="s1")
    _setup_student(
        classroom_repository, student_repository, classroom_id="c2", classroom_name="9Б",
        student_id="s2", first_name="Дана", last_name="Қалиева",
    )
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    _submit_feedback(feedback_repository, "sess1")
    progress_repository.link_session("sess2", "s2", "c2", "ohms-law")
    _save_measured_session(session_repository, "sess2")
    _submit_feedback(feedback_repository, "sess2")
    page.on_enter()

    page._search_edit.setText("9Б")

    assert page._table.rowCount() == 1
    assert page._table.item(0, 1).text() == "9Б"


def test_search_filters_by_experiment_title() -> None:
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _setup_student(classroom_repository, student_repository)
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1", "ohms-law")
    _submit_feedback(feedback_repository, "sess1", "ohms-law")
    progress_repository.link_session("sess2", "s1", "c1", "current-work")
    _save_measured_session(session_repository, "sess2", "current-work")
    _submit_feedback(feedback_repository, "sess2", "current-work")
    page.on_enter()

    page._search_edit.setText("Ток")

    assert page._table.rowCount() == 1
    assert page._table.item(0, 2).text() == "Ток жұмысы"


# ---- Күй сүзгісі ---------------------------------------------------------


def _setup_waiting_and_reviewed(
    classroom_repository, student_repository, progress_repository, feedback_repository, session_repository
) -> None:
    _setup_student(classroom_repository, student_repository, student_id="s1", first_name="Айдос", last_name="Серіков")
    _setup_student(
        classroom_repository, student_repository, student_id="s2", first_name="Дана", last_name="Қалиева",
    )
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    _submit_feedback(feedback_repository, "sess1")

    progress_repository.link_session("sess2", "s2", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess2")
    _submit_feedback(feedback_repository, "sess2")
    feedback_repository.save_teacher_assessment(
        "sess2", "ohms-law", TeacherAssessment(score=9), UserRole.TEACHER
    )


def test_status_filter_waiting_for_review() -> None:
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _setup_waiting_and_reviewed(
        classroom_repository, student_repository, progress_repository, feedback_repository, session_repository
    )
    page.on_enter()

    index = page._status_filter_combo.findData("waiting")
    page._status_filter_combo.setCurrentIndex(index)

    assert page._table.rowCount() == 1
    assert page._table.item(0, 4).text() == "Тексеруді күтуде"


def test_status_filter_reviewed() -> None:
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _setup_waiting_and_reviewed(
        classroom_repository, student_repository, progress_repository, feedback_repository, session_repository
    )
    page.on_enter()

    index = page._status_filter_combo.findData("reviewed")
    page._status_filter_combo.setCurrentIndex(index)

    assert page._table.rowCount() == 1
    assert page._table.item(0, 4).text() == "Тексерілді"


def test_status_filter_all_shows_both() -> None:
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _setup_waiting_and_reviewed(
        classroom_repository, student_repository, progress_repository, feedback_repository, session_repository
    )
    page.on_enter()

    assert page._table.rowCount() == 2


# ---- Сұрыптау ----------------------------------------------------------


def test_sort_by_submission_date_newest_first_is_default() -> None:
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _setup_student(classroom_repository, student_repository, student_id="s1", first_name="Айдос", last_name="Серіков")
    _setup_student(classroom_repository, student_repository, student_id="s2", first_name="Дана", last_name="Қалиева")
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    _submit_feedback(feedback_repository, "sess1", submitted_at=_NOW - timedelta(days=2))
    progress_repository.link_session("sess2", "s2", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess2")
    _submit_feedback(feedback_repository, "sess2", submitted_at=_NOW)

    page.on_enter()

    assert page._table.item(0, 0).text() == "Қалиева Дана"
    assert page._table.item(1, 0).text() == "Серіков Айдос"


def test_sort_by_student_name() -> None:
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    # Ескерту: Python-дың қарапайым str салыстыруы Unicode кодтық
    # нүктелерімен жұмыс істейді (locale-негізді қазақ әліпбилік реті
    # ЕМЕС — SqliteStudentRepository.list_by_classroom()-мен БІРДЕЙ
    # шектеу), сондықтан тестте тек стандартты кириллица әріптерінен
    # басталатын тегтер қолданылады (А < С, дау тудырмайды).
    _setup_student(classroom_repository, student_repository, student_id="s1", first_name="Айдос", last_name="Серіков")
    _setup_student(classroom_repository, student_repository, student_id="s2", first_name="Дана", last_name="Ахметова")
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    _submit_feedback(feedback_repository, "sess1", submitted_at=_NOW - timedelta(days=2))
    progress_repository.link_session("sess2", "s2", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess2")
    _submit_feedback(feedback_repository, "sess2", submitted_at=_NOW)
    page.on_enter()

    index = page._sort_combo.findData("student")
    page._sort_combo.setCurrentIndex(index)

    assert page._table.item(0, 0).text() == "Ахметова Дана"
    assert page._table.item(1, 0).text() == "Серіков Айдос"


# ---- Диалогтарды қайта пайдалану -----------------------------------------


def test_open_report_button_reuses_experiment_report_dialog() -> None:
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _setup_student(classroom_repository, student_repository)
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    _submit_feedback(feedback_repository, "sess1")
    page.on_enter()

    row = page._filtered_sorted_rows()[0]
    page._on_open_report_clicked(row)

    from ui.widgets.experiment_report_dialog import ExperimentReportDialog

    assert isinstance(page._report_dialog, ExperimentReportDialog)
    page._report_dialog.close()


def test_grade_button_opens_feedback_dialog_with_existing_submission() -> None:
    """"Бағалау" батырмасы жіберілген жауаптарды (кемінде 1 деңгей
    жауабы) диалогтың дерек көзі ретінде тасымалдайды — "жалғастыру"
    ешбір қайталама тексеру диалогі жасамай-ақ жұмыс істейді.
    """
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _setup_student(classroom_repository, student_repository)
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    _submit_feedback(feedback_repository, "sess1")
    page.on_enter()

    row = page._filtered_sorted_rows()[0]
    page._on_open_feedback_clicked(row)

    from ui.widgets.experiment_feedback_dialog import ExperimentFeedbackDialog

    assert isinstance(page._feedback_dialog, ExperimentFeedbackDialog)
    page._feedback_dialog.close()


def test_grade_button_persists_teacher_assessment_and_refreshes_row() -> None:
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _setup_student(classroom_repository, student_repository)
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    _submit_feedback(feedback_repository, "sess1")
    page.on_enter()

    row = page._filtered_sorted_rows()[0]
    page._on_open_feedback_clicked(row)
    page._on_feedback_teacher_assessment_saved("sess1", "ohms-law", TeacherAssessment(score=7, comment="Жарайды"))

    result = feedback_repository.get_result("sess1")
    assert result.teacher_assessment.score == 7
    assert page._table.item(0, 4).text() == "Тексерілді"
    page._feedback_dialog.close()


# ---- Регрессия: қайталанған on_enter() виджет ағыны ---------------------


def test_repeated_on_enter_does_not_leak_action_buttons() -> None:
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _setup_student(classroom_repository, student_repository)
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    _submit_feedback(feedback_repository, "sess1")

    for _ in range(5):
        page.on_enter()
        QApplication.processEvents()

    buttons = page._table.viewport().findChildren(QPushButton)
    assert len(buttons) == 2  # Тексеру/Қарау + Есепті ашу (1 жол)


def test_on_enter_refreshes_after_new_submission() -> None:
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _setup_student(classroom_repository, student_repository)
    page.on_enter()
    assert page._table.rowCount() == 0

    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    _submit_feedback(feedback_repository, "sess1")
    page.on_enter()

    assert page._table.rowCount() == 1


# =====================================================================
# Phase 18 ("Teacher Feedback Review Page Audit + Safe Workflow Polish"):
# сынып/оқушы/тәжірибе сүзгісі, статус түсі, "Тексеру"/"Қарау" батырма
# мәтіні, 2 бөлек бос күй, деректер қауіпсіздігі.
# =====================================================================


def _setup_two_classrooms_with_submissions(
    classroom_repository, student_repository, progress_repository, feedback_repository, session_repository
):
    _setup_student(classroom_repository, student_repository, classroom_id="c1", classroom_name="8А", student_id="s1", first_name="Айдос", last_name="Серіков")
    _setup_student(classroom_repository, student_repository, classroom_id="c2", classroom_name="9Б", student_id="s2", first_name="Дана", last_name="Қалиева")
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1", "ohms-law")
    _submit_feedback(feedback_repository, "sess1", "ohms-law", submitted_at=_NOW)
    progress_repository.link_session("sess2", "s2", "c2", "current-work")
    _save_measured_session(session_repository, "sess2", "current-work")
    _submit_feedback(feedback_repository, "sess2", "current-work", submitted_at=_NOW)


# ---- Сынып сүзгісі + каскад ------------------------------------------


def test_classroom_filter_narrows_rows() -> None:
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _setup_two_classrooms_with_submissions(
        classroom_repository, student_repository, progress_repository, feedback_repository, session_repository
    )
    page.on_enter()
    assert page._table.rowCount() == 2

    index = page._classroom_filter_combo.findData("c1")
    page._classroom_filter_combo.setCurrentIndex(index)

    assert page._table.rowCount() == 1
    assert page._table.item(0, 0).text() == "Серіков Айдос"


def test_classroom_filter_all_restores_full_scope() -> None:
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _setup_two_classrooms_with_submissions(
        classroom_repository, student_repository, progress_repository, feedback_repository, session_repository
    )
    page.on_enter()
    page._classroom_filter_combo.setCurrentIndex(page._classroom_filter_combo.findData("c1"))
    assert page._table.rowCount() == 1

    page._classroom_filter_combo.setCurrentIndex(0)

    assert page._table.rowCount() == 2


def test_classroom_to_student_cascade() -> None:
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _setup_two_classrooms_with_submissions(
        classroom_repository, student_repository, progress_repository, feedback_repository, session_repository
    )
    page.on_enter()

    index = page._classroom_filter_combo.findData("c1")
    page._classroom_filter_combo.setCurrentIndex(index)

    student_names = [
        page._student_filter_combo.itemText(i) for i in range(page._student_filter_combo.count())
    ]
    assert student_names == ["Барлығы", "Серіков Айдос"]


def test_student_filter_narrows_rows() -> None:
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _setup_two_classrooms_with_submissions(
        classroom_repository, student_repository, progress_repository, feedback_repository, session_repository
    )
    page.on_enter()

    index = page._student_filter_combo.findData("s2")
    page._student_filter_combo.setCurrentIndex(index)

    assert page._table.rowCount() == 1
    assert page._table.item(0, 0).text() == "Қалиева Дана"


# ---- Тәжірибе сүзгісі ---------------------------------------------------


def test_experiment_filter_narrows_rows() -> None:
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _setup_two_classrooms_with_submissions(
        classroom_repository, student_repository, progress_repository, feedback_repository, session_repository
    )
    page.on_enter()
    assert page._table.rowCount() == 2

    index = page._experiment_filter_combo.findData("current-work")
    page._experiment_filter_combo.setCurrentIndex(index)

    assert page._table.rowCount() == 1
    assert page._table.item(0, 2).text() == "Ток жұмысы"


# ---- Аралас сүзгілер ---------------------------------------------------


def test_combined_classroom_student_experiment_filters() -> None:
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _setup_two_classrooms_with_submissions(
        classroom_repository, student_repository, progress_repository, feedback_repository, session_repository
    )
    page.on_enter()

    page._classroom_filter_combo.setCurrentIndex(page._classroom_filter_combo.findData("c1"))
    page._student_filter_combo.setCurrentIndex(page._student_filter_combo.findData("s1"))
    page._experiment_filter_combo.setCurrentIndex(page._experiment_filter_combo.findData("ohms-law"))

    assert page._table.rowCount() == 1
    assert page._table.item(0, 0).text() == "Серіков Айдос"


# ---- Статус түсі (§ ThemeManager семантикалық токендерін қайта пайдалану) -


def test_waiting_status_uses_warning_color() -> None:
    from ui.themes.theme_manager import COLOR_WARNING

    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _setup_student(classroom_repository, student_repository)
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    _submit_feedback(feedback_repository, "sess1")
    page.on_enter()

    color = page._table.item(0, 4).foreground().color()

    assert color.name() == QColor(COLOR_WARNING).name()


def test_reviewed_status_uses_success_color() -> None:
    from ui.themes.theme_manager import COLOR_SUCCESS

    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _setup_student(classroom_repository, student_repository)
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    _submit_feedback(feedback_repository, "sess1")
    feedback_repository.save_teacher_assessment("sess1", "ohms-law", TeacherAssessment(score=9), UserRole.TEACHER)
    page.on_enter()

    color = page._table.item(0, 4).foreground().color()

    assert color.name() == QColor(COLOR_SUCCESS).name()


# ---- "Тексеру"/"Қарау" батырма мәтіні ------------------------------------


def test_pending_row_uses_tekseru_label() -> None:
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _setup_student(classroom_repository, student_repository)
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    _submit_feedback(feedback_repository, "sess1")
    page.on_enter()

    action_widget = page._table.cellWidget(0, page._table.columnCount() - 1)
    labels = [b.text() for b in action_widget.findChildren(QPushButton)]

    assert "Тексеру" in labels
    assert "Қарау" not in labels


def test_reviewed_row_uses_qarau_label() -> None:
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _setup_student(classroom_repository, student_repository)
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    _submit_feedback(feedback_repository, "sess1")
    feedback_repository.save_teacher_assessment("sess1", "ohms-law", TeacherAssessment(score=9), UserRole.TEACHER)
    page.on_enter()

    action_widget = page._table.cellWidget(0, page._table.columnCount() - 1)
    labels = [b.text() for b in action_widget.findChildren(QPushButton)]

    assert "Қарау" in labels
    assert "Тексеру" not in labels


# ---- 2 бөлек бос күй -----------------------------------------------------


def test_zero_submission_empty_state_uses_case_a_text() -> None:
    page, _classrooms, _students, _progress, _feedback, _sessions = _make_page()
    page.show()
    page.on_enter()

    assert page._empty_state_title_label.text() == "Жіберілген жұмыстар жоқ"
    assert page._classroom_filter_combo.isVisible() is False


def test_filter_no_results_uses_case_b_text() -> None:
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _setup_student(classroom_repository, student_repository)
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    _submit_feedback(feedback_repository, "sess1")
    page.show()
    page.on_enter()

    page._search_edit.setText("zzzznotfound")

    assert page._empty_state_title_label.text() == "Сүзгіге сәйкес жұмыстар табылмады."
    assert page._empty_state_title_label.text() != "Жіберілген жұмыстар жоқ"
    assert page._search_edit.isVisible() is True


# ---- Деректер қауіпсіздігі ------------------------------------------------


def test_opening_report_dialog_does_not_mutate_feedback_result() -> None:
    """§15 "Browsing or opening a submission must be read-only until the
    teacher explicitly saves/completes a review"."""
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _setup_student(classroom_repository, student_repository)
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    _submit_feedback(feedback_repository, "sess1")
    page.on_enter()
    before = feedback_repository.get_result("sess1")

    row = page._filtered_sorted_rows()[0]
    page._on_open_report_clicked(row)
    page._report_dialog.close()

    after = feedback_repository.get_result("sess1")
    assert before == after


def test_opening_feedback_dialog_without_saving_does_not_mutate_result() -> None:
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _setup_student(classroom_repository, student_repository)
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    _submit_feedback(feedback_repository, "sess1")
    page.on_enter()
    before = feedback_repository.get_result("sess1")

    row = page._filtered_sorted_rows()[0]
    page._on_open_feedback_clicked(row)
    page._feedback_dialog.close()

    after = feedback_repository.get_result("sess1")
    assert before == after


def test_valid_score_can_be_saved() -> None:
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _setup_student(classroom_repository, student_repository)
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    _submit_feedback(feedback_repository, "sess1")
    page.on_enter()

    page._on_feedback_teacher_assessment_saved(
        "sess1", "ohms-law", TeacherAssessment(score=10, comment="Өте жақсы")
    )

    result = feedback_repository.get_result("sess1")
    assert result.teacher_assessment.score == 10


def test_invalid_score_rejected_by_existing_domain_rules() -> None:
    """§7 "The score control should validate against the actual domain
    constraints" — ``TeacherAssessment.validate()`` (§ 0-10 ауқымы,
    домен деңгейінде, бұрыннан бар) диапазоннан тыс мәнді қабылдамайды."""
    errors = TeacherAssessment(score=11).validate()
    assert len(errors) == 1

    errors_negative = TeacherAssessment(score=-1).validate()
    assert len(errors_negative) == 1

    errors_valid = TeacherAssessment(score=10).validate()
    assert errors_valid == []


def test_teacher_feedback_comment_saves_correctly() -> None:
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _setup_student(classroom_repository, student_repository)
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    _submit_feedback(feedback_repository, "sess1")
    page.on_enter()

    page._on_feedback_teacher_assessment_saved(
        "sess1", "ohms-law", TeacherAssessment(score=8, comment="Жақсы жұмыс, келесіде дәлдікке көбірек назар аудар.")
    )

    result = feedback_repository.get_result("sess1")
    assert result.teacher_assessment.comment == "Жақсы жұмыс, келесіде дәлдікке көбірек назар аудар."


def test_review_completion_transitions_status_to_reviewed() -> None:
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _setup_student(classroom_repository, student_repository)
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    _submit_feedback(feedback_repository, "sess1")
    page.on_enter()
    assert page._all_rows[0].progress.status is ProgressStatus.FEEDBACK_SUBMITTED

    page._on_feedback_teacher_assessment_saved("sess1", "ohms-law", TeacherAssessment(score=9))

    assert page._all_rows[0].progress.status is ProgressStatus.REVIEWED


def test_assessment_not_duplicated_on_repeated_refresh() -> None:
    """§16 "assessment is not duplicated on repeated refresh" — ортақ
    ``session_id``-мен UPSERT (§ SqliteFeedbackRepository), қайталама
    жол ЕШҚАШАН жасалмайды."""
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _setup_student(classroom_repository, student_repository)
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    _submit_feedback(feedback_repository, "sess1")
    page.on_enter()

    page._on_feedback_teacher_assessment_saved("sess1", "ohms-law", TeacherAssessment(score=6))
    page.on_enter()
    page.on_enter()
    page.on_enter()

    assert page._table.rowCount() == 1
    assert page._table.item(0, 5).text() == "6"


def test_reviewed_submission_retains_score_and_can_be_reopened() -> None:
    """§10 "If the existing system allows editing a review, preserve
    existing behavior" — ``ExperimentFeedbackDialog`` реттелген мәнді
    ЕШҚАШАН жоғалтпай қайта ашады (§ ``_restore_from_result()``)."""
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _setup_student(classroom_repository, student_repository)
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    _submit_feedback(feedback_repository, "sess1")
    feedback_repository.save_teacher_assessment("sess1", "ohms-law", TeacherAssessment(score=8), UserRole.TEACHER)
    page.on_enter()

    row = page._filtered_sorted_rows()[0]
    page._on_open_feedback_clicked(row)

    assert page._feedback_dialog._teacher_score_spin.value() == 8
    page._feedback_dialog.close()


def test_summary_counts_refresh_after_review() -> None:
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _setup_student(classroom_repository, student_repository)
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    _submit_feedback(feedback_repository, "sess1")
    page.on_enter()
    assert page._value_labels["waiting"].text() == "1"
    assert page._value_labels["reviewed"].text() == "0"

    page._on_feedback_teacher_assessment_saved("sess1", "ohms-law", TeacherAssessment(score=9))

    assert page._value_labels["waiting"].text() == "0"
    assert page._value_labels["reviewed"].text() == "1"


def test_filters_remain_valid_after_review() -> None:
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _setup_two_classrooms_with_submissions(
        classroom_repository, student_repository, progress_repository, feedback_repository, session_repository
    )
    page.on_enter()
    page._classroom_filter_combo.setCurrentIndex(page._classroom_filter_combo.findData("c1"))
    assert page._table.rowCount() == 1

    page._on_feedback_teacher_assessment_saved("sess1", "ohms-law", TeacherAssessment(score=9))

    assert page._classroom_filter_combo.currentData() == "c1"
    assert page._table.rowCount() == 1


def test_no_unrelated_repository_mutation_while_browsing() -> None:
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _setup_two_classrooms_with_submissions(
        classroom_repository, student_repository, progress_repository, feedback_repository, session_repository
    )
    page.on_enter()
    before_sessions = session_repository.count_sessions()
    before_classrooms = len(classroom_repository.list_active())

    row = page._filtered_sorted_rows()[0]
    page._on_open_report_clicked(row)
    page._report_dialog.close()
    page._classroom_filter_combo.setCurrentIndex(page._classroom_filter_combo.findData("c1"))
    page._status_filter_combo.setCurrentIndex(page._status_filter_combo.findData("waiting"))

    assert session_repository.count_sessions() == before_sessions
    assert len(classroom_repository.list_active()) == before_classrooms
