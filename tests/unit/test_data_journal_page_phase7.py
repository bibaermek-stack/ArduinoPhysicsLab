"""DataJournalPage — Phase 7 (Teacher Actions, Feedback Delivery, and
Session History) tests: ``on_enter(student_id=..., session_id=...)``
арқылы ``StudentMonitoringDetailPage``-тен тереңдетілген сілтеме (§
"reuse ResultsPage/DataJournalPage if they already provide the
required functionality" — ЖАҢА бет ЖОҚ, тек екі ЕРІКТІ параметр).
"""

import sys
from datetime import datetime, timezone

import pytest
from PySide6.QtWidgets import QApplication

from domain.entities.classroom import Classroom
from domain.entities.experiment_session import ExperimentSession
from domain.entities.measurement import Measurement
from domain.entities.student import Student
from domain.entities.user_role import UserRole
from infrastructure.storage.sqlite_classroom_repository import SqliteClassroomRepository
from infrastructure.storage.sqlite_session_repository import SqliteSessionRepository
from infrastructure.storage.sqlite_student_progress_repository import SqliteStudentProgressRepository
from infrastructure.storage.sqlite_student_repository import SqliteStudentRepository
from ui.pages.data_journal_page import DataJournalPage

_NOW = datetime.now(timezone.utc)


@pytest.fixture(scope="module", autouse=True)
def qt_application() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def _make_session(session_id: str, experiment_id: str = "ohms-law") -> ExperimentSession:
    session = ExperimentSession(id=session_id, experiment_id=experiment_id, started_at=_NOW)
    session.add_measurement(
        Measurement(timestamp=_NOW, values={"voltage": 5.0}, experiment_id=experiment_id)
    )
    session.stop()
    return session


def _make_page() -> tuple[
    DataJournalPage, SqliteSessionRepository, SqliteClassroomRepository,
    SqliteStudentRepository, SqliteStudentProgressRepository,
]:
    session_repository = SqliteSessionRepository()
    classroom_repository = SqliteClassroomRepository()
    student_repository = SqliteStudentRepository()
    progress_repository = SqliteStudentProgressRepository(
        session_repository=session_repository,
        classroom_repository=classroom_repository,
        student_repository=student_repository,
    )
    classroom_repository.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    classroom_repository.create(
        Classroom(id="c2", name="9Б", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    student_repository.create(
        Student(id="s1", classroom_id="c1", first_name="Айдос", last_name="Серіков",
                created_at=_NOW, updated_at=_NOW),
        UserRole.TEACHER,
    )
    student_repository.create(
        Student(id="s2", classroom_id="c2", first_name="Бекзат", last_name="Нұрлан",
                created_at=_NOW, updated_at=_NOW),
        UserRole.TEACHER,
    )
    page = DataJournalPage(
        session_repository=session_repository,
        classroom_repository=classroom_repository,
        student_repository=student_repository,
        student_progress_repository=progress_repository,
    )
    return page, session_repository, classroom_repository, student_repository, progress_repository


def test_on_enter_without_params_preserves_old_reset_behavior() -> None:
    """§ backward compatibility — sidebar-дан қалыпты навигация
    (параметрсіз) мінез-құлқы Phase 7-ге дейінгідей: барлық сүзгі
    "Барлығы"-ге қайтарылады."""
    page, session_repository, _classrooms, _students, progress_repository = _make_page()
    session_repository.save_session(_make_session("sess1"))
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    page.on_enter()
    page._classroom_filter_combo.setCurrentIndex(page._classroom_filter_combo.findData("c1"))

    page.on_enter()

    assert page._classroom_filter_combo.currentData() is None
    assert page._student_filter_combo.currentData() is None


def test_on_enter_with_student_id_filters_to_that_student() -> None:
    page, session_repository, _classrooms, _students, progress_repository = _make_page()
    session_repository.save_session(_make_session("sess1"))
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    session_repository.save_session(_make_session("sess2"))
    progress_repository.link_session("sess2", "s2", "c2", "ohms-law")

    page.on_enter(student_id="s1")

    assert page._classroom_filter_combo.currentData() == "c1"
    assert page._student_filter_combo.currentData() == "s1"
    assert page._table.rowCount() == 1
    assert page._table.item(0, 2).text() == "Серіков Айдос"


def test_on_enter_with_unknown_student_id_falls_back_safely() -> None:
    """§ "Teacher B must not access unrelated students by manually
    navigating with IDs" — жергілікті базада ЖОҚ ``student_id`` ЕШБІР
    деректі ашпайды/құламайды, қауіпсіз "Барлығы" күйіне құлайды."""
    page, session_repository, _classrooms, _students, progress_repository = _make_page()
    session_repository.save_session(_make_session("sess1"))
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")

    page.on_enter(student_id="unauthorized-or-unknown-id")

    assert page._classroom_filter_combo.currentData() is None
    assert page._student_filter_combo.currentData() is None
    # § "no crash, safe fallback to the unfiltered (but still only
    # locally-present, i.e. sync-authorized) view" — ЕШБІР арнайы
    # деректі "рұқсат етілмеген" оқушыға көрсетпейді, себебі бұл id
    # жергілікті базада МҮЛДЕ ЖОҚ.
    assert page._table.rowCount() == 1


def test_on_enter_with_session_id_opens_detail_view_directly() -> None:
    page, session_repository, _classrooms, _students, progress_repository = _make_page()
    session_repository.save_session(_make_session("sess1"))
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")

    page.on_enter(student_id="s1", session_id="sess1")

    assert page._stack.currentIndex() == 1  # § detail view
    assert page._current_detail is not None
    assert page._current_detail[0].id == "sess1"


def test_on_enter_with_unknown_session_id_does_not_crash() -> None:
    page, _sessions, _classrooms, _students, _progress = _make_page()

    page.on_enter(student_id="s1", session_id="does-not-exist")

    assert page._stack.currentIndex() == 0  # § list view, тыныш жансыз құламады


def test_student_filter_scoped_by_classroom_does_not_leak_other_classroom_students() -> None:
    page, session_repository, _classrooms, _students, progress_repository = _make_page()
    session_repository.save_session(_make_session("sess1"))
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    session_repository.save_session(_make_session("sess2"))
    progress_repository.link_session("sess2", "s2", "c2", "ohms-law")

    page.on_enter(student_id="s2")

    assert page._classroom_filter_combo.currentData() == "c2"
    assert page._table.rowCount() == 1
    assert page._table.item(0, 2).text() == "Нұрлан Бекзат"
