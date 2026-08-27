"""StudentFeedbackPage юнит-тесттері (Phase 41): белсенді оқушының өз
жіберілген кері байланысының күйін көрсететін бет — блокталған күй,
меншіктілік оқшаулануы (басқа оқушы/жобалар/тек өлшеу/тағайындалмаған
сессиялар мүлде көрінбейді), жинақы сандар, іздеу/сүзгі/сұрыптау,
мұғалім бағасы/пікірі рендерингі, есеп диалогын Оқушы-қауіпсіз режимде
қайта пайдалану, қайталанған on_enter() виджет ағыны регрессиясы.
"""

import sys
from datetime import datetime, timedelta, timezone

import pytest
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QSpinBox

from domain.entities.active_student_context import ActiveStudentContext
from domain.entities.experiment_assessment import ExperimentAssessmentDefinition, MultipleChoiceQuestion
from domain.entities.experiment_definition import ExperimentDefinition, ExperimentReport
from domain.entities.experiment_feedback_result import ExperimentFeedbackResult, TeacherAssessment
from domain.entities.experiment_session import ExperimentSession
from domain.entities.measurement import Measurement
from domain.entities.student import Student
from domain.entities.teacher_note import TeacherNote
from domain.entities.user_role import UserRole
from domain.interfaces.i_physics_module import IPhysicsModule
from infrastructure.storage.sqlite_active_student_repository import SqliteActiveStudentRepository
from infrastructure.storage.sqlite_feedback_repository import SqliteFeedbackRepository
from infrastructure.storage.sqlite_session_repository import SqliteSessionRepository
from infrastructure.storage.sqlite_student_progress_repository import SqliteStudentProgressRepository
from infrastructure.storage.sqlite_student_repository import SqliteStudentRepository
from infrastructure.storage.sqlite_teacher_note_repository import SqliteTeacherNoteRepository
from modules.module_registry import ModuleRegistry
from ui.pages.student_feedback_page import StudentFeedbackPage
from ui.widgets.experiment_report_dialog import ExperimentReportDialog

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
    StudentFeedbackPage, SqliteActiveStudentRepository, SqliteStudentRepository,
    SqliteStudentProgressRepository, SqliteFeedbackRepository, SqliteSessionRepository,
]:
    active_repository = SqliteActiveStudentRepository()
    student_repository = SqliteStudentRepository()
    session_repository = SqliteSessionRepository()
    feedback_repository = SqliteFeedbackRepository()
    progress_repository = SqliteStudentProgressRepository(
        session_repository=session_repository, feedback_repository=feedback_repository,
    )
    module_registry = ModuleRegistry()
    module_registry.register(_FakeModule())

    student_repository.create(
        Student(id="s1", classroom_id="c1", first_name="Айдос", last_name="Серіков",
                created_at=_NOW, updated_at=_NOW),
        UserRole.TEACHER,
    )
    student_repository.create(
        Student(id="s2", classroom_id="c1", first_name="Бекзат", last_name="Нұрлан",
                created_at=_NOW, updated_at=_NOW),
        UserRole.TEACHER,
    )

    # § Phase 7 (Teacher Actions, Feedback Delivery, and Session History)
    # — қайтарылатын tuple пішіні (реті/саны) ӘДЕЙІ ӨЗГЕРТІЛМЕГЕН (§
    # ондаған қолданыстағы шақырушы позициялық unpacking қолданады);
    # жаңа репозиторий тек ``page._teacher_note_repository`` арқылы
    # қолжетімді (§ бет ӨЗІ оны атрибут ретінде сақтайды).
    page = StudentFeedbackPage(
        active_student_repository=active_repository,
        student_repository=student_repository,
        student_progress_repository=progress_repository,
        feedback_repository=feedback_repository,
        session_repository=session_repository,
        module_registry=module_registry,
        teacher_note_repository=SqliteTeacherNoteRepository(),
    )
    return page, active_repository, student_repository, progress_repository, feedback_repository, session_repository


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
            submitted_at=submitted_at or _NOW,
        )
    )


def _save_draft_feedback(
    feedback_repository: SqliteFeedbackRepository, session_id: str, experiment_id: str = "ohms-law"
) -> None:
    feedback_repository.save_draft(
        ExperimentFeedbackResult(experiment_id=experiment_id, session_id=session_id, is_draft=True)
    )


def _activate_student(active_repository: SqliteActiveStudentRepository, student_id: str = "s1") -> None:
    active_repository.set(ActiveStudentContext(classroom_id="c1", student_id=student_id))


# ---- Блокталған/бос күйлер ------------------------------------------------


def test_blocked_state_shown_when_no_active_student() -> None:
    page, _active, _students, _progress, _feedback, _sessions = _make_page()

    page.on_enter()

    assert page._stack.currentIndex() == 0


def test_empty_state_shown_when_active_student_has_no_submissions() -> None:
    page, active_repository, _students, _progress, _feedback, _sessions = _make_page()
    _activate_student(active_repository)

    page.on_enter()

    assert page._stack.currentIndex() == 1
    assert page._empty_state_title_label.text() == "Жіберілген кері байланыс жоқ"
    assert page._empty_state_title_label.isHidden() is False
    assert page._table.isHidden() is True
    assert page._value_labels["total_submitted"].text() == "0"


def test_search_no_match_shows_distinct_empty_state() -> None:
    page, active_repository, _students, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _activate_student(active_repository)
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    _submit_feedback(feedback_repository, "sess1")
    page.on_enter()

    page._search_edit.setText("Мүлдем сәйкес келмейтін мәтін")

    assert page._empty_state_title_label.text() == "Сұраныс бойынша нәтиже табылмады"
    assert page._table.isHidden() is True


# ---- Меншіктілік оқшаулануы (Phase 41 record rules) ------------------------


def test_draft_feedback_is_excluded() -> None:
    page, active_repository, _students, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _activate_student(active_repository)
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    _save_draft_feedback(feedback_repository, "sess1")

    page.on_enter()

    assert page._table.rowCount() == 0
    assert page._value_labels["total_submitted"].text() == "0"


def test_measurement_only_session_without_feedback_is_excluded() -> None:
    page, active_repository, _students, progress_repository, _feedback, session_repository = (
        _make_page()
    )
    _activate_student(active_repository)
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")

    page.on_enter()

    assert page._table.rowCount() == 0


def test_other_students_submissions_never_appear() -> None:
    page, active_repository, _students, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _activate_student(active_repository, "s1")
    progress_repository.link_session("sess-s1", "s1", "c1", "ohms-law")
    progress_repository.link_session("sess-s2", "s2", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess-s1")
    _save_measured_session(session_repository, "sess-s2")
    _submit_feedback(feedback_repository, "sess-s1")
    _submit_feedback(feedback_repository, "sess-s2")

    page.on_enter()

    assert page._table.rowCount() == 1


def test_legacy_unassigned_session_never_shown() -> None:
    page, active_repository, _students, _progress, feedback_repository, session_repository = (
        _make_page()
    )
    _activate_student(active_repository)
    _save_measured_session(session_repository, "legacy-sess")  # ешбір link жоқ
    _submit_feedback(feedback_repository, "legacy-sess")

    page.on_enter()

    assert page._table.rowCount() == 0


# ---- Тізім/статус/жинақы сандар --------------------------------------------


def test_submitted_report_appears_waiting_for_review() -> None:
    page, active_repository, _students, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _activate_student(active_repository)
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    _submit_feedback(feedback_repository, "sess1")

    page.on_enter()

    assert page._table.rowCount() == 1
    assert page._table.item(0, 0).text() == "Ом заңы"
    assert page._table.item(0, 2).text() == "Тексеруді күтуде"
    assert page._table.item(0, 3).text() == "—"
    assert page._table.item(0, 4).text() == "—"
    assert page._value_labels["total_submitted"].text() == "1"
    assert page._value_labels["waiting"].text() == "1"
    assert page._value_labels["reviewed"].text() == "0"


def test_reviewed_report_shows_real_score_and_comment() -> None:
    page, active_repository, _students, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _activate_student(active_repository)
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    _submit_feedback(feedback_repository, "sess1")
    feedback_repository.save_teacher_assessment(
        "sess1", "ohms-law", TeacherAssessment(score=8, comment="Жақсы жұмыс"), UserRole.TEACHER
    )

    page.on_enter()

    assert page._table.item(0, 2).text() == "Тексерілді"
    assert page._table.item(0, 3).text() == "8"
    assert page._table.item(0, 4).text() == "Жақсы жұмыс"
    assert page._value_labels["waiting"].text() == "0"
    assert page._value_labels["reviewed"].text() == "1"


def test_long_teacher_comment_is_truncated_in_table_preview() -> None:
    page, active_repository, _students, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _activate_student(active_repository)
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    _submit_feedback(feedback_repository, "sess1")
    long_comment = "Бұл өте ұзақ мұғалім пікірі " * 5
    feedback_repository.save_teacher_assessment(
        "sess1", "ohms-law", TeacherAssessment(score=7, comment=long_comment), UserRole.TEACHER
    )

    page.on_enter()

    preview = page._table.item(0, 4).text()
    assert len(preview) < len(long_comment)
    assert preview.endswith("…")


# ---- Іздеу/сүзгі/сұрыптау ---------------------------------------------------


def test_search_filters_by_experiment_title() -> None:
    page, active_repository, _students, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _activate_student(active_repository)
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1", "ohms-law")
    _submit_feedback(feedback_repository, "sess1", "ohms-law")
    progress_repository.link_session("sess2", "s1", "c1", "current-work")
    _save_measured_session(session_repository, "sess2", "current-work")
    _submit_feedback(feedback_repository, "sess2", "current-work")
    page.on_enter()

    page._search_edit.setText("Ток")

    assert page._table.rowCount() == 1
    assert page._table.item(0, 0).text() == "Ток жұмысы"


def _setup_waiting_and_reviewed(progress_repository, feedback_repository, session_repository) -> None:
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1", "ohms-law")
    _submit_feedback(feedback_repository, "sess1", "ohms-law")

    progress_repository.link_session("sess2", "s1", "c1", "current-work")
    _save_measured_session(session_repository, "sess2", "current-work")
    _submit_feedback(feedback_repository, "sess2", "current-work")
    feedback_repository.save_teacher_assessment(
        "sess2", "current-work", TeacherAssessment(score=9), UserRole.TEACHER
    )


def test_status_filter_all_options() -> None:
    page, active_repository, _students, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _activate_student(active_repository)
    _setup_waiting_and_reviewed(progress_repository, feedback_repository, session_repository)
    page.on_enter()

    assert page._table.rowCount() == 2

    index = page._status_filter_combo.findData("waiting")
    page._status_filter_combo.setCurrentIndex(index)
    assert page._table.rowCount() == 1
    assert page._table.item(0, 2).text() == "Тексеруді күтуде"

    index = page._status_filter_combo.findData("reviewed")
    page._status_filter_combo.setCurrentIndex(index)
    assert page._table.rowCount() == 1
    assert page._table.item(0, 2).text() == "Тексерілді"

    index = page._status_filter_combo.findData("all")
    page._status_filter_combo.setCurrentIndex(index)
    assert page._table.rowCount() == 2


def test_sort_newest_first_is_default() -> None:
    page, active_repository, _students, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _activate_student(active_repository)
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1", "ohms-law")
    _submit_feedback(feedback_repository, "sess1", "ohms-law", submitted_at=_NOW - timedelta(days=2))
    progress_repository.link_session("sess2", "s1", "c1", "current-work")
    _save_measured_session(session_repository, "sess2", "current-work")
    _submit_feedback(feedback_repository, "sess2", "current-work", submitted_at=_NOW)

    page.on_enter()

    assert page._table.item(0, 0).text() == "Ток жұмысы"
    assert page._table.item(1, 0).text() == "Ом заңы"


def test_sort_oldest_first() -> None:
    page, active_repository, _students, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _activate_student(active_repository)
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1", "ohms-law")
    _submit_feedback(feedback_repository, "sess1", "ohms-law", submitted_at=_NOW - timedelta(days=2))
    progress_repository.link_session("sess2", "s1", "c1", "current-work")
    _save_measured_session(session_repository, "sess2", "current-work")
    _submit_feedback(feedback_repository, "sess2", "current-work", submitted_at=_NOW)
    page.on_enter()

    index = page._sort_combo.findData("date_asc")
    page._sort_combo.setCurrentIndex(index)

    assert page._table.item(0, 0).text() == "Ом заңы"
    assert page._table.item(1, 0).text() == "Ток жұмысы"


def test_sort_by_experiment_title() -> None:
    page, active_repository, _students, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _activate_student(active_repository)
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1", "ohms-law")
    _submit_feedback(feedback_repository, "sess1", "ohms-law")
    progress_repository.link_session("sess2", "s1", "c1", "current-work")
    _save_measured_session(session_repository, "sess2", "current-work")
    _submit_feedback(feedback_repository, "sess2", "current-work")
    page.on_enter()

    index = page._sort_combo.findData("title")
    page._sort_combo.setCurrentIndex(index)

    assert page._table.item(0, 0).text() == "Ом заңы"
    assert page._table.item(1, 0).text() == "Ток жұмысы"


# ---- Есеп диалогын Оқушы-қауіпсіз режимде қайта пайдалану ------------------


def test_opening_waiting_record_reuses_report_dialog_without_teacher_section() -> None:
    page, active_repository, _students, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _activate_student(active_repository)
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    _submit_feedback(feedback_repository, "sess1")
    page.on_enter()

    row = page._filtered_sorted_rows()[0]
    page._on_open_clicked(row)

    assert isinstance(page._report_dialog, ExperimentReportDialog)
    # Мұғалім бағасы/пікірі жоқ (тексерілмеген) — секция мүлде жоқ.
    assert page._report_dialog.findChildren(QSpinBox) == []
    page._report_dialog.close()


def test_opening_reviewed_record_shows_score_and_comment_read_only() -> None:
    page, active_repository, _students, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _activate_student(active_repository)
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    _submit_feedback(feedback_repository, "sess1")
    feedback_repository.save_teacher_assessment(
        "sess1", "ohms-law", TeacherAssessment(score=8, comment="Жақсы"), UserRole.TEACHER
    )
    page.on_enter()

    row = page._filtered_sorted_rows()[0]
    page._on_open_clicked(row)

    assert isinstance(page._report_dialog, ExperimentReportDialog)
    # Student-safe: ЕШБІР мұғалім бағасын өзгертетін контрол (QSpinBox)
    # диалогта мүлде жоқ — тек оқу-режимдегі QLabel-дар (§ ExperimentReportDialog
    # рөлге тәуелсіз, тек берілген деректің teacher_assessment бар/жоғына сүйенеді).
    assert page._report_dialog.findChildren(QSpinBox) == []
    all_labels_text = " ".join(
        label.text() for label in page._report_dialog.findChildren(QLabel)
    )
    assert "8" in all_labels_text
    assert "Жақсы" in all_labels_text
    page._report_dialog.close()


def test_opening_record_never_lets_student_edit_teacher_fields() -> None:
    """§ 'Do not allow the student to modify the teacher's score, teacher
    comment, or reviewed state' — StudentFeedbackPage мүлде
    ExperimentFeedbackDialog-ты (Teacher режимінде) ашпайды, тек
    оқу-режимдегі ExperimentReportDialog-ты ғана қолданады.
    """
    page, active_repository, _students, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _activate_student(active_repository)
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    _submit_feedback(feedback_repository, "sess1")
    feedback_repository.save_teacher_assessment(
        "sess1", "ohms-law", TeacherAssessment(score=8, comment="Жақсы"), UserRole.TEACHER
    )
    page.on_enter()

    row = page._filtered_sorted_rows()[0]
    page._on_open_clicked(row)

    assert not hasattr(page, "_feedback_dialog")
    page._report_dialog.close()


# ---- Белсенді оқушы ауысуы --------------------------------------------------


def test_switching_active_student_replaces_rows() -> None:
    page, active_repository, _students, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _activate_student(active_repository, "s1")
    progress_repository.link_session("sess-s1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess-s1")
    _submit_feedback(feedback_repository, "sess-s1")
    page.on_enter()
    assert page._table.rowCount() == 1
    assert page._table.item(0, 0).text() == "Ом заңы"

    _activate_student(active_repository, "s2")
    progress_repository.link_session("sess-s2", "s2", "c1", "current-work")
    _save_measured_session(session_repository, "sess-s2", "current-work")
    _submit_feedback(feedback_repository, "sess-s2", "current-work")
    page.on_enter()

    assert page._table.rowCount() == 1
    assert page._table.item(0, 0).text() == "Ток жұмысы"


def test_clearing_active_student_returns_to_blocked_view() -> None:
    page, active_repository, _students, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _activate_student(active_repository, "s1")
    page.on_enter()
    assert page._stack.currentIndex() == 1

    active_repository.clear()
    page.on_enter()

    assert page._stack.currentIndex() == 0


# ---- Регрессия: қайталанған on_enter() виджет ағыны -------------------------


def test_repeated_on_enter_does_not_leak_open_buttons() -> None:
    page, active_repository, _students, progress_repository, feedback_repository, session_repository = (
        _make_page()
    )
    _activate_student(active_repository)
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    _submit_feedback(feedback_repository, "sess1")

    for _ in range(5):
        page.on_enter()
        QApplication.processEvents()

    buttons = page._table.viewport().findChildren(QPushButton)
    assert len(buttons) == 1


# ---- Мұғалім пікірі лентасы (Phase 7 Part B) --------------------------------


def test_no_notes_shows_placeholder() -> None:
    page, active_repository, _students, _progress, _feedback, _sessions = _make_page()
    _activate_student(active_repository)

    page.on_enter()

    assert page._notes_list.count() == 1
    assert "пікір" in page._notes_list.item(0).text()


def test_teacher_note_appears_in_feed() -> None:
    page, active_repository, _students, _progress, _feedback, _sessions = _make_page()
    _activate_student(active_repository)
    page._teacher_note_repository.create(
        TeacherNote(
            id="note-1", teacher_id="t1", student_id="s1", classroom_id="c1",
            message="Өлшеуді қайта тексер", created_at=_NOW,
        ),
        UserRole.TEACHER,
    )

    page.on_enter()

    assert page._notes_list.count() == 1
    assert "Өлшеуді қайта тексер" in page._notes_list.item(0).text()


def test_notes_never_show_other_students_notes() -> None:
    page, active_repository, _students, _progress, _feedback, _sessions = _make_page()
    _activate_student(active_repository, "s1")
    page._teacher_note_repository.create(
        TeacherNote(id="note-s1", teacher_id="t1", student_id="s1", classroom_id="c1",
                    message="Для s1", created_at=_NOW),
        UserRole.TEACHER,
    )
    page._teacher_note_repository.create(
        TeacherNote(id="note-s2", teacher_id="t1", student_id="s2", classroom_id="c1",
                    message="Для s2", created_at=_NOW),
        UserRole.TEACHER,
    )

    page.on_enter()

    assert page._notes_list.count() == 1
    assert "Для s1" in page._notes_list.item(0).text()


def test_notes_marked_read_locally_after_display() -> None:
    """§ "seen it" cadence — панель ашылғаннан кейін пікір жергілікті
    "оқылды" деп белгіленеді (§ ешбір қосымша клик қажет ЕМЕС)."""
    page, active_repository, _students, _progress, _feedback, _sessions = _make_page()
    _activate_student(active_repository)
    page._teacher_note_repository.create(
        TeacherNote(id="note-1", teacher_id="t1", student_id="s1", classroom_id="c1",
                    message="Хабарлама", created_at=_NOW),
        UserRole.TEACHER,
    )

    page.on_enter()

    notes = page._teacher_note_repository.list_for_student("s1")
    assert notes[0].read_at is not None


def test_notes_newest_first() -> None:
    page, active_repository, _students, _progress, _feedback, _sessions = _make_page()
    _activate_student(active_repository)
    page._teacher_note_repository.create(
        TeacherNote(id="note-1", teacher_id="t1", student_id="s1", classroom_id="c1",
                    message="Бірінші", created_at=_NOW - timedelta(minutes=5)),
        UserRole.TEACHER,
    )
    page._teacher_note_repository.create(
        TeacherNote(id="note-2", teacher_id="t1", student_id="s1", classroom_id="c1",
                    message="Екінші", created_at=_NOW),
        UserRole.TEACHER,
    )

    page.on_enter()

    assert "Екінші" in page._notes_list.item(0).text()
    assert "Бірінші" in page._notes_list.item(1).text()
