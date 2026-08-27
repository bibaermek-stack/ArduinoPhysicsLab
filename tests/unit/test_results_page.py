"""ResultsPage юнит-тесттері (Phase 16): "Нәтижелер" беті — жинақы
карталар, сынып/оқушы/тәжірибе/күй сүзгілері, іздеу, сұрыптау, бос
күйлер, "Қарау" (ExperimentReportDialog қайта пайдалану), Артқа
батырмасының ЖОҚтығы.
"""

import sys
from datetime import datetime, timedelta, timezone

import pytest
from PySide6.QtWidgets import QApplication, QPushButton

from domain.entities.classroom import Classroom
from domain.entities.experiment_assessment import ExperimentAssessmentDefinition, MultipleChoiceQuestion
from domain.entities.experiment_definition import ExperimentDefinition, ExperimentReport
from domain.entities.experiment_feedback_result import ExperimentFeedbackResult, TeacherAssessment
from domain.entities.experiment_session import ExperimentSession
from domain.entities.measurement import Measurement
from domain.entities.student import Student
from domain.entities.student_experiment_progress import ProgressStatus, StudentExperimentProgress
from domain.entities.user_role import UserRole
from domain.interfaces.i_physics_module import IPhysicsModule
from infrastructure.storage.sqlite_classroom_repository import SqliteClassroomRepository
from infrastructure.storage.sqlite_feedback_repository import SqliteFeedbackRepository
from infrastructure.storage.sqlite_session_repository import SqliteSessionRepository
from infrastructure.storage.sqlite_student_progress_repository import SqliteStudentProgressRepository
from infrastructure.storage.sqlite_student_repository import SqliteStudentRepository
from modules.module_registry import ModuleRegistry
from ui.pages.results_page import ResultsPage

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
    ResultsPage, SqliteClassroomRepository, SqliteStudentRepository,
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

    page = ResultsPage(
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


# ---- Артқа батырмасының ЖОҚтығы -------------------------------------------


def test_no_back_button_anywhere_on_page() -> None:
    page, *_ = _make_page()

    buttons = [b for b in page.findChildren(QPushButton) if b.text() == "← Артқа"]

    assert buttons == []


# ---- Бос күй (репозиторий бос) ---------------------------------------------


def test_empty_repository_state() -> None:
    page, *_ = _make_page()

    assert page._empty_title_label.isHidden() is False
    assert page._empty_title_label.text() == "Әзірге зертханалық жұмыс нәтижелері жоқ."
    assert page._table.isHidden() is True
    assert page._value_labels["total"].text() == "0"
    assert page._value_labels["completed"].text() == "0"
    assert page._value_labels["waiting"].text() == "0"
    assert page._value_labels["average"].text() == "—"
    assert page._classroom_filter_combo.isHidden() is True
    assert page._search_edit.isHidden() is True


def test_measurement_completed_without_submission_is_excluded() -> None:
    page, classroom_repository, student_repository, progress_repository, _feedback, session_repository = (
        _make_page()
    )
    _setup_student(classroom_repository, student_repository)
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")

    page.on_enter()

    assert page._table.rowCount() == 0
    assert page._value_labels["total"].text() == "0"


# ---- Жол толтыру / статус мэппингі -----------------------------------------


def test_submitted_row_populated_with_real_data() -> None:
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _setup_student(classroom_repository, student_repository)
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    _submit_feedback(feedback_repository, "sess1", submitted_at=_NOW)

    page.on_enter()

    assert page._table.rowCount() == 1
    assert page._table.item(0, 0).text() == "Серіков Айдос"
    assert page._table.item(0, 1).text() == "8А"
    assert page._table.item(0, 2).text() == "Ом заңы"
    assert page._table.item(0, 3).text() == _NOW.astimezone().strftime("%d.%m.%Y")
    assert page._table.item(0, 4).text() == "Тексеруді күтуде"
    assert page._table.item(0, 5).text() == "—"  # әлі бағаланбаған
    assert page._value_labels["total"].text() == "1"
    assert page._value_labels["waiting"].text() == "1"
    assert page._value_labels["completed"].text() == "0"


def test_reviewed_row_shows_teacher_score_and_status() -> None:
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _setup_student(classroom_repository, student_repository)
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    _submit_feedback(feedback_repository, "sess1", submitted_at=_NOW)
    feedback_repository.save_teacher_assessment(
        "sess1", "ohms-law", TeacherAssessment(score=8, comment="Жақсы"), UserRole.TEACHER
    )

    page.on_enter()

    assert page._table.item(0, 4).text() == "Тексерілді"
    assert page._table.item(0, 5).text() == "8"
    assert page._value_labels["completed"].text() == "1"
    assert page._value_labels["waiting"].text() == "0"
    assert page._value_labels["average"].text() == "8.0"


def test_missing_submitted_at_shows_dash_for_date() -> None:
    """§ ``SqliteFeedbackRepository._save()``: НАҚТЫ жіберу (``is_draft=
    False``) кезінде ``submitted_at`` берілмесе, репозиторий ӨЗІ "қазір"
    уақытын қояды — production-де ЕШҚАШАН ``None`` болмайды. Осы тест
    сол теориялық-мүмкін, БІРАҚ шынайы репозиторий арқылы жетуге
    БОЛМАЙТЫН жағдайды тікелей ``_populate_row()``-ды синтетикалық
    ``_ResultRow``-мен шақырып, тек ҚОРҒАНЫС render логикасын тексереді
    (§ Phase 16 талабы: "missing date -> '—'").
    """
    from ui.pages.results_page import _ResultRow

    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _setup_student(classroom_repository, student_repository)
    student = student_repository.get("s1")
    classroom = classroom_repository.get("c1")
    progress = StudentExperimentProgress(
        student_id="s1", experiment_id="ohms-law", status=ProgressStatus.FEEDBACK_SUBMITTED,
        latest_session_id="sess1", submitted_at=None,
    )
    row = _ResultRow(student=student, classroom=classroom, experiment=_OHMS_LAW, progress=progress)
    page._table.setRowCount(1)

    page._populate_row(0, row)

    assert page._table.item(0, 3).text() == "—"


def test_average_score_computed_from_multiple_reviewed_records() -> None:
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _setup_student(classroom_repository, student_repository, student_id="s1", first_name="Айдос", last_name="Серіков")
    _setup_student(classroom_repository, student_repository, student_id="s2", first_name="Дана", last_name="Қалиева")
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    _submit_feedback(feedback_repository, "sess1", submitted_at=_NOW)
    feedback_repository.save_teacher_assessment("sess1", "ohms-law", TeacherAssessment(score=7), UserRole.TEACHER)
    progress_repository.link_session("sess2", "s2", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess2")
    _submit_feedback(feedback_repository, "sess2", submitted_at=_NOW)
    feedback_repository.save_teacher_assessment("sess2", "ohms-law", TeacherAssessment(score=10), UserRole.TEACHER)

    page.on_enter()

    assert page._value_labels["average"].text() == "8.5"


def test_no_fabricated_average_when_zero_reviewed() -> None:
    """Тек жіберілген (waiting), БІРАҚ ЕШБІР тексерілмеген жазба —
    "Орташа нәтиже" ойдан шығарылған 0 ЕМЕС, "—" болуы керек."""
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _setup_student(classroom_repository, student_repository)
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    _submit_feedback(feedback_repository, "sess1", submitted_at=_NOW)

    page.on_enter()

    assert page._value_labels["average"].text() == "—"


# ---- Сынып сүзгісі -----------------------------------------------------


def _setup_two_classrooms(classroom_repository, student_repository, progress_repository, feedback_repository, session_repository):
    _setup_student(classroom_repository, student_repository, classroom_id="c1", classroom_name="8А", student_id="s1", first_name="Айдос", last_name="Серіков")
    _setup_student(classroom_repository, student_repository, classroom_id="c2", classroom_name="9Б", student_id="s2", first_name="Дана", last_name="Қалиева")
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    _submit_feedback(feedback_repository, "sess1", submitted_at=_NOW)
    progress_repository.link_session("sess2", "s2", "c2", "ohms-law")
    _save_measured_session(session_repository, "sess2")
    _submit_feedback(feedback_repository, "sess2", submitted_at=_NOW)


def test_classroom_filter_narrows_rows() -> None:
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _setup_two_classrooms(classroom_repository, student_repository, progress_repository, feedback_repository, session_repository)
    page.on_enter()
    assert page._table.rowCount() == 2

    index = page._classroom_filter_combo.findData("c1")
    page._classroom_filter_combo.setCurrentIndex(index)

    assert page._table.rowCount() == 1
    assert page._table.item(0, 1).text() == "8А"


def test_classroom_filter_shows_existing_classrooms_only() -> None:
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _setup_two_classrooms(classroom_repository, student_repository, progress_repository, feedback_repository, session_repository)
    page.on_enter()

    names = [page._classroom_filter_combo.itemText(i) for i in range(page._classroom_filter_combo.count())]

    assert names == ["Барлығы", "8А", "9Б"]


def test_classroom_filter_reset_to_all_restores_full_list() -> None:
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _setup_two_classrooms(classroom_repository, student_repository, progress_repository, feedback_repository, session_repository)
    page.on_enter()
    index = page._classroom_filter_combo.findData("c1")
    page._classroom_filter_combo.setCurrentIndex(index)
    assert page._table.rowCount() == 1

    page._classroom_filter_combo.setCurrentIndex(0)

    assert page._table.rowCount() == 2


# ---- Оқушы сүзгісі (сынып->оқушы каскады) ------------------------------


def test_student_filter_lists_only_selected_classroom_students() -> None:
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _setup_two_classrooms(classroom_repository, student_repository, progress_repository, feedback_repository, session_repository)
    page.on_enter()

    index = page._classroom_filter_combo.findData("c1")
    page._classroom_filter_combo.setCurrentIndex(index)

    student_names = [
        page._student_filter_combo.itemText(i) for i in range(page._student_filter_combo.count())
    ]
    assert student_names == ["Барлығы", "Серіков Айдос"]


def test_student_filter_without_classroom_shows_all_students() -> None:
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _setup_two_classrooms(classroom_repository, student_repository, progress_repository, feedback_repository, session_repository)

    page.on_enter()

    student_names = {
        page._student_filter_combo.itemText(i) for i in range(page._student_filter_combo.count())
    }
    assert student_names == {"Барлығы", "Серіков Айдос", "Қалиева Дана"}


def test_student_filter_narrows_rows() -> None:
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _setup_two_classrooms(classroom_repository, student_repository, progress_repository, feedback_repository, session_repository)
    page.on_enter()

    index = page._student_filter_combo.findData("s2")
    page._student_filter_combo.setCurrentIndex(index)

    assert page._table.rowCount() == 1
    assert page._table.item(0, 0).text() == "Қалиева Дана"


def test_correct_classroom_student_relationship_in_filter() -> None:
    """Сынып таңдалғанда оқушы тізімі ТЕК сол сыныпқа жататын
    оқушыларды көрсетуі керек — қате қатынас ЖОҚ."""
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _setup_two_classrooms(classroom_repository, student_repository, progress_repository, feedback_repository, session_repository)
    page.on_enter()

    index = page._classroom_filter_combo.findData("c2")
    page._classroom_filter_combo.setCurrentIndex(index)

    student_ids = {
        page._student_filter_combo.itemData(i) for i in range(page._student_filter_combo.count())
    }
    assert student_ids == {None, "s2"}


# ---- Тәжірибе сүзгісі ---------------------------------------------------


def test_experiment_filter_narrows_rows() -> None:
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _setup_student(classroom_repository, student_repository)
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1", "ohms-law")
    _submit_feedback(feedback_repository, "sess1", "ohms-law", submitted_at=_NOW)
    progress_repository.link_session("sess2", "s1", "c1", "current-work")
    _save_measured_session(session_repository, "sess2", "current-work")
    _submit_feedback(feedback_repository, "sess2", "current-work", submitted_at=_NOW)
    page.on_enter()
    assert page._table.rowCount() == 2

    index = page._experiment_filter_combo.findData("current-work")
    page._experiment_filter_combo.setCurrentIndex(index)

    assert page._table.rowCount() == 1
    assert page._table.item(0, 2).text() == "Ток жұмысы"


def test_experiment_filter_populated_from_catalog_not_hardcoded() -> None:
    page, *_ = _make_page()

    titles = {page._experiment_filter_combo.itemText(i) for i in range(page._experiment_filter_combo.count())}

    assert titles == {"Барлығы", "Ом заңы", "Ток жұмысы"}


# ---- Күй сүзгісі ---------------------------------------------------------


def _setup_waiting_and_reviewed(classroom_repository, student_repository, progress_repository, feedback_repository, session_repository) -> None:
    _setup_student(classroom_repository, student_repository, student_id="s1", first_name="Айдос", last_name="Серіков")
    _setup_student(classroom_repository, student_repository, student_id="s2", first_name="Дана", last_name="Қалиева")
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    _submit_feedback(feedback_repository, "sess1", submitted_at=_NOW)

    progress_repository.link_session("sess2", "s2", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess2")
    _submit_feedback(feedback_repository, "sess2", submitted_at=_NOW)
    feedback_repository.save_teacher_assessment("sess2", "ohms-law", TeacherAssessment(score=9), UserRole.TEACHER)


def test_status_filter_waiting() -> None:
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _setup_waiting_and_reviewed(classroom_repository, student_repository, progress_repository, feedback_repository, session_repository)
    page.on_enter()

    index = page._status_filter_combo.findData("waiting")
    page._status_filter_combo.setCurrentIndex(index)

    assert page._table.rowCount() == 1
    assert page._table.item(0, 4).text() == "Тексеруді күтуде"


def test_status_filter_reviewed() -> None:
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _setup_waiting_and_reviewed(classroom_repository, student_repository, progress_repository, feedback_repository, session_repository)
    page.on_enter()

    index = page._status_filter_combo.findData("reviewed")
    page._status_filter_combo.setCurrentIndex(index)

    assert page._table.rowCount() == 1
    assert page._table.item(0, 4).text() == "Тексерілді"


def test_status_filter_all_shows_both() -> None:
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _setup_waiting_and_reviewed(classroom_repository, student_repository, progress_repository, feedback_repository, session_repository)
    page.on_enter()

    assert page._table.rowCount() == 2


# ---- Іздеу ------------------------------------------------------------


def test_search_filters_by_student_name() -> None:
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _setup_two_classrooms(classroom_repository, student_repository, progress_repository, feedback_repository, session_repository)
    page.on_enter()

    page._search_edit.setText("дана")  # регистрге сезімтал ЕМЕС

    assert page._table.rowCount() == 1
    assert page._table.item(0, 0).text() == "Қалиева Дана"


def test_search_filters_by_classroom_name() -> None:
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _setup_two_classrooms(classroom_repository, student_repository, progress_repository, feedback_repository, session_repository)
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
    _submit_feedback(feedback_repository, "sess1", "ohms-law", submitted_at=_NOW)
    progress_repository.link_session("sess2", "s1", "c1", "current-work")
    _save_measured_session(session_repository, "sess2", "current-work")
    _submit_feedback(feedback_repository, "sess2", "current-work", submitted_at=_NOW)
    page.on_enter()

    page._search_edit.setText("Ток")

    assert page._table.rowCount() == 1
    assert page._table.item(0, 2).text() == "Ток жұмысы"


# ---- Аралас сүзгілер (спецификацияның меншікті мысалы) ----------------


def test_combined_classroom_student_experiment_filters() -> None:
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _setup_student(classroom_repository, student_repository, classroom_id="c1", classroom_name="8А", student_id="s1", first_name="Нұржалғас", last_name="Өтемісов")
    _setup_student(classroom_repository, student_repository, classroom_id="c1", classroom_name="8А", student_id="s2", first_name="Дана", last_name="Қалиева")
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1", "ohms-law")
    _submit_feedback(feedback_repository, "sess1", "ohms-law", submitted_at=_NOW)
    progress_repository.link_session("sess2", "s1", "c1", "current-work")
    _save_measured_session(session_repository, "sess2", "current-work")
    _submit_feedback(feedback_repository, "sess2", "current-work", submitted_at=_NOW)
    progress_repository.link_session("sess3", "s2", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess3", "ohms-law")
    _submit_feedback(feedback_repository, "sess3", "ohms-law", submitted_at=_NOW)
    page.on_enter()
    assert page._table.rowCount() == 3

    page._classroom_filter_combo.setCurrentIndex(page._classroom_filter_combo.findData("c1"))
    page._student_filter_combo.setCurrentIndex(page._student_filter_combo.findData("s1"))
    page._experiment_filter_combo.setCurrentIndex(page._experiment_filter_combo.findData("ohms-law"))

    assert page._table.rowCount() == 1
    assert page._table.item(0, 0).text() == "Өтемісов Нұржалғас"
    assert page._table.item(0, 2).text() == "Ом заңы"


# ---- Бос сүзгі нәтижесі (CASE B) -------------------------------------


def test_no_search_results_state() -> None:
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _setup_student(classroom_repository, student_repository)
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    _submit_feedback(feedback_repository, "sess1", submitted_at=_NOW)
    page.on_enter()

    page._search_edit.setText("zzzznotfound")

    assert page._table.isHidden() is True
    assert page._empty_title_label.isHidden() is False
    assert page._empty_title_label.text() == "Нәтиже табылмады."
    assert page._empty_hint_label.text() == "Іздеу немесе сүзгі параметрлерін өзгертіп көріңіз."
    # Сүзгілер ӨЗДЕРІ көрінуін жалғастыруы керек (§ репозиторийде дерек
    # бар, тек ФИЛЬТР нәтижесі бос) — толық бос репозиторий күйінен
    # ерекшеленеді.
    assert page._search_edit.isHidden() is False


# ---- Сұрыптау -----------------------------------------------------------


def test_default_sort_prioritizes_waiting_then_newest() -> None:
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _setup_student(classroom_repository, student_repository, student_id="s1", first_name="Айдос", last_name="Серіков")
    _setup_student(classroom_repository, student_repository, student_id="s2", first_name="Дана", last_name="Қалиева")
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    _submit_feedback(feedback_repository, "sess1", submitted_at=_NOW)
    feedback_repository.save_teacher_assessment("sess1", "ohms-law", TeacherAssessment(score=9), UserRole.TEACHER)
    progress_repository.link_session("sess2", "s2", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess2")
    _submit_feedback(feedback_repository, "sess2", submitted_at=_NOW - timedelta(days=1))

    page.on_enter()

    # sess2 (waiting) бірінші болуы керек, дегенмен sess1 ЖАҢАРАҚ (§ 1)
    # тексеруді күтуде, 2) ЕҢ жаңа, 3) қалғандары).
    assert page._table.item(0, 4).text() == "Тексеруді күтуде"
    assert page._table.item(1, 4).text() == "Тексерілді"


def test_sort_by_student_name() -> None:
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _setup_student(classroom_repository, student_repository, student_id="s1", first_name="Айдос", last_name="Серіков")
    _setup_student(classroom_repository, student_repository, student_id="s2", first_name="Дана", last_name="Ахметова")
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    _submit_feedback(feedback_repository, "sess1", submitted_at=_NOW)
    progress_repository.link_session("sess2", "s2", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess2")
    _submit_feedback(feedback_repository, "sess2", submitted_at=_NOW)
    page.on_enter()

    index = page._sort_combo.findData("student")
    page._sort_combo.setCurrentIndex(index)

    assert page._table.item(0, 0).text() == "Ахметова Дана"
    assert page._table.item(1, 0).text() == "Серіков Айдос"


def test_sort_by_date_ascending() -> None:
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _setup_student(classroom_repository, student_repository, student_id="s1", first_name="Айдос", last_name="Серіков")
    _setup_student(classroom_repository, student_repository, student_id="s2", first_name="Дана", last_name="Қалиева")
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    _submit_feedback(feedback_repository, "sess1", submitted_at=_NOW)
    progress_repository.link_session("sess2", "s2", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess2")
    _submit_feedback(feedback_repository, "sess2", submitted_at=_NOW - timedelta(days=2))
    page.on_enter()

    index = page._sort_combo.findData("date_asc")
    page._sort_combo.setCurrentIndex(index)

    assert page._table.item(0, 0).text() == "Қалиева Дана"
    assert page._table.item(1, 0).text() == "Серіков Айдос"


# ---- "Қарау": ExperimentReportDialog қайта пайдалану ----------------------


def test_open_report_button_reuses_experiment_report_dialog() -> None:
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _setup_student(classroom_repository, student_repository)
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    _submit_feedback(feedback_repository, "sess1", submitted_at=_NOW)
    page.on_enter()

    row = page._filtered_sorted_rows()[0]
    page._on_open_report_clicked(row)

    from ui.widgets.experiment_report_dialog import ExperimentReportDialog

    assert isinstance(page._report_dialog, ExperimentReportDialog)
    page._report_dialog.close()


def test_view_button_disabled_when_experiment_has_no_report() -> None:
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    page._module_registry = ModuleRegistry()

    class _NoReportModule(IPhysicsModule):
        def get_name(self) -> str:
            return "M"

        def get_icon(self) -> str | None:
            return None

        def get_experiments(self) -> tuple[ExperimentDefinition, ...]:
            return (ExperimentDefinition(id="no-report", title="Есепсіз", description="", report=None),)

    page._module_registry.register(_NoReportModule())
    _setup_student(classroom_repository, student_repository)
    progress_repository.link_session("sess1", "s1", "c1", "no-report")
    _save_measured_session(session_repository, "sess1", "no-report")
    _submit_feedback(feedback_repository, "sess1", "no-report", submitted_at=_NOW)

    page.on_enter()

    from PySide6.QtWidgets import QWidget

    action_widget = page._table.cellWidget(0, 6)
    report_button = action_widget.findChild(QPushButton)
    assert report_button.isEnabled() is False


# ---- Регрессия: қайталанған on_enter() виджет ағыны ---------------------


def test_repeated_on_enter_does_not_leak_action_buttons() -> None:
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _setup_student(classroom_repository, student_repository)
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    _submit_feedback(feedback_repository, "sess1", submitted_at=_NOW)

    for _ in range(5):
        page.on_enter()
        QApplication.processEvents()

    buttons = page._table.viewport().findChildren(QPushButton)
    assert len(buttons) == 1  # Қарау (1 жол)


def test_on_enter_refreshes_after_new_submission() -> None:
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _setup_student(classroom_repository, student_repository)
    page.on_enter()
    assert page._table.rowCount() == 0

    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    _submit_feedback(feedback_repository, "sess1", submitted_at=_NOW)
    page.on_enter()

    assert page._table.rowCount() == 1
