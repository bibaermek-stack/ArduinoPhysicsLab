"""StudentResultsPage юнит-тесттері: блокталған күй, тек белсенді
оқушының нәтижелері, легаси/басқа оқушы сессиялары мүлде көрінбейді,
Мұғалім бағасы бағаны мүлде жоқ."""

import sys
from datetime import datetime, timezone

import pytest
from PySide6.QtWidgets import QApplication, QPushButton

from domain.entities.active_student_context import ActiveStudentContext
from domain.entities.experiment_definition import ExperimentDefinition, ExperimentReport
from domain.entities.experiment_feedback_result import ExperimentFeedbackResult, TeacherAssessment
from domain.entities.experiment_session import ExperimentSession
from domain.entities.measurement import Measurement
from domain.entities.student import Student
from domain.entities.user_role import UserRole
from domain.interfaces.i_physics_module import IPhysicsModule
from infrastructure.storage.sqlite_active_student_repository import SqliteActiveStudentRepository
from infrastructure.storage.sqlite_feedback_repository import SqliteFeedbackRepository
from infrastructure.storage.sqlite_session_repository import SqliteSessionRepository
from infrastructure.storage.sqlite_student_progress_repository import SqliteStudentProgressRepository
from infrastructure.storage.sqlite_student_repository import SqliteStudentRepository
from modules.module_registry import ModuleRegistry
from ui.pages.student_results_page import StudentResultsPage

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
    StudentResultsPage, SqliteActiveStudentRepository, SqliteStudentRepository,
    SqliteStudentProgressRepository, SqliteSessionRepository, SqliteFeedbackRepository,
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

    page = StudentResultsPage(
        active_student_repository=active_repository,
        student_repository=student_repository,
        student_progress_repository=progress_repository,
        feedback_repository=feedback_repository,
        session_repository=session_repository,
        module_registry=module_registry,
    )
    return page, active_repository, student_repository, progress_repository, session_repository, feedback_repository


def _save_measured_session(session_repository: SqliteSessionRepository, session_id: str) -> None:
    session = ExperimentSession(id=session_id, experiment_id="ohms-law", started_at=_NOW)
    session.add_measurement(
        Measurement(timestamp=_NOW, values={"voltage": 5.0}, experiment_id="ohms-law")
    )
    session_repository.save_session(session)


def test_blocked_state_shown_when_no_active_student() -> None:
    page, _active, _students, _progress, _sessions, _feedback = _make_page()

    assert page._stack.currentIndex() == 0


def test_results_view_shown_when_active_student_set() -> None:
    page, active_repository, _students, _progress, _sessions, _feedback = _make_page()
    active_repository.set(ActiveStudentContext(classroom_id="c1", student_id="s1"))

    page.on_enter()

    assert page._stack.currentIndex() == 1
    assert "Серіков Айдос" in page._active_student_label.text()


def test_not_started_experiments_are_omitted() -> None:
    page, active_repository, _students, _progress, _sessions, _feedback = _make_page()
    active_repository.set(ActiveStudentContext(classroom_id="c1", student_id="s1"))

    page.on_enter()

    assert page._table.rowCount() == 0


def test_only_active_students_own_session_appears() -> None:
    page, active_repository, _students, progress_repository, session_repository, _feedback = _make_page()
    active_repository.set(ActiveStudentContext(classroom_id="c1", student_id="s1"))
    progress_repository.link_session("sess-s1", "s1", "c1", "ohms-law")
    progress_repository.link_session("sess-s2", "s2", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess-s1")
    _save_measured_session(session_repository, "sess-s2")

    page.on_enter()

    assert page._table.rowCount() == 1


def test_legacy_unassigned_session_never_shown() -> None:
    page, active_repository, _students, _progress, session_repository, _feedback = _make_page()
    active_repository.set(ActiveStudentContext(classroom_id="c1", student_id="s1"))
    _save_measured_session(session_repository, "legacy-sess")  # ешбір link жоқ

    page.on_enter()

    assert page._table.rowCount() == 0


def test_no_teacher_score_column_in_headers() -> None:
    page, _active, _students, _progress, _sessions, _feedback = _make_page()

    headers = [
        page._table.horizontalHeaderItem(i).text() for i in range(page._table.columnCount())
    ]

    assert not any("Мұғалім" in header for header in headers)


def test_review_status_reflects_teacher_assessment_without_leaking_comment() -> None:
    page, active_repository, _students, progress_repository, session_repository, feedback_repository = (
        _make_page()
    )
    active_repository.set(ActiveStudentContext(classroom_id="c1", student_id="s1"))
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    feedback_repository.save_submission(
        ExperimentFeedbackResult(
            experiment_id="ohms-law", session_id="sess1", is_draft=False, submitted_at=_NOW,
        )
    )
    feedback_repository.save_teacher_assessment(
        "sess1", "ohms-law",
        TeacherAssessment(score=9, comment="ЖАСЫРЫН ПІКІР"),
        UserRole.TEACHER,
    )

    page.on_enter()

    status_item = page._table.item(0, 2)
    assert "Тексерілді" in status_item.text()
    # Ешбір ұяшық мәтінінде мұғалімнің пікірі көрінбеуі тиіс.
    all_cell_text = " ".join(
        page._table.item(0, column).text()
        for column in range(page._table.columnCount())
        if page._table.item(0, column) is not None
    )
    assert "ЖАСЫРЫН ПІКІР" not in all_cell_text


def test_repeated_on_enter_does_not_leak_open_result_buttons() -> None:
    """Бетке қайта кіру (Router.navigate() арқылы on_enter() қайта
    шақырылғанда) "Нәтижені ашу" батырмасының әр рет ЖАҢА данасы жасалуы
    керек — ескі cell widget-тер viewport-та жасырын түрде жиналмауы тиіс
    (§ DataJournalPage._render_list()-те расталған дәл осындай bug).
    """
    page, active_repository, _students, progress_repository, session_repository, _feedback = _make_page()
    active_repository.set(ActiveStudentContext(classroom_id="c1", student_id="s1"))
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")

    for _ in range(5):
        page.on_enter()
        QApplication.processEvents()

    buttons = page._table.viewport().findChildren(QPushButton)
    assert len(buttons) == 1
