"""DataJournalPage — Phase 39C мануалды тағайындау тесттері: "Оқушы"
бағаны, тағайындалмаған сессия белгісі, тағайындау диалогы/әрекеті,
қайта тағайындау мүмкін ЕМЕС екенін растау.
"""

import sys
from datetime import datetime, timedelta, timezone

import pytest
from PySide6.QtWidgets import QApplication, QDialog

from domain.entities.classroom import Classroom
from domain.entities.experiment_session import ExperimentSession
from domain.entities.measurement import Measurement
from domain.entities.student import Student
from domain.entities.user_role import UserRole
from infrastructure.storage.sqlite_classroom_repository import SqliteClassroomRepository
from infrastructure.storage.sqlite_session_repository import SqliteSessionRepository
from infrastructure.storage.sqlite_student_progress_repository import SqliteStudentProgressRepository
from infrastructure.storage.sqlite_student_repository import SqliteStudentRepository
from ui.pages.data_journal_page import DataJournalPage, _AssignSessionDialog, _UNASSIGNED_TEXT

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
    student_repository.create(
        Student(id="s1", classroom_id="c1", first_name="Айдос", last_name="Серіков",
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


def test_unassigned_session_shows_honest_label_in_list() -> None:
    page, session_repository, _classrooms, _students, _progress = _make_page()
    session_repository.save_session(_make_session("sess1"))
    page.on_enter()

    # Phase 17: "Оқушы" бағаны ЕНДІ index 2-де (§ "Preferred visible
    # columns" реті: Күні/Зертханалық жұмыс/Оқушы/Өлшеулер/Басталды/
    # Аяқталды/Әрекет — бұрынғы 5-тен ауысты).
    assert page._table.item(0, 2).text() == _UNASSIGNED_TEXT


def test_assigned_session_shows_student_display_name_in_list() -> None:
    page, session_repository, _classrooms, _students, progress_repository = _make_page()
    session_repository.save_session(_make_session("sess1"))
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    page.on_enter()

    assert page._table.item(0, 2).text() == "Серіков Айдос"


def test_assign_button_visible_for_unassigned_session() -> None:
    page, session_repository, _classrooms, _students, _progress = _make_page()
    session_repository.save_session(_make_session("sess1"))
    page.on_enter()

    page._on_open_clicked("sess1")

    assert page._assign_button.isHidden() is False


def test_assign_button_hidden_for_already_assigned_session() -> None:
    page, session_repository, _classrooms, _students, progress_repository = _make_page()
    session_repository.save_session(_make_session("sess1"))
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    page.on_enter()

    page._on_open_clicked("sess1")

    assert page._assign_button.isHidden() is True


def test_assign_dialog_lists_classrooms_and_filters_students_by_classroom() -> None:
    _page, _sessions, classroom_repository, student_repository, _progress = _make_page()
    classroom_repository.create(
        Classroom(id="c2", name="8Ә", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    dialog = _AssignSessionDialog(classroom_repository, student_repository)

    names = [dialog._classroom_combo.itemText(i) for i in range(dialog._classroom_combo.count())]
    assert names == ["8А", "8Ә"]
    assert dialog._student_combo.count() == 1
    assert dialog._student_combo.itemText(0) == "Серіков Айдос"


def test_assign_dialog_rejects_confirm_without_full_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    # QMessageBox.warning() нақты модальды (.exec()) диалог — offscreen
    # тестте ешкім баспайтын батырманы шексіз күтіп қалады. Басқа
    # тесттер (мыс. StudentFormDialog) осы валидация жолын мүлде
    # тексермеген себебі де осы — monkeypatch арқылы ЕШБІР нақты диалог
    # көрсетілмейді, тек шақырылғаны расталады.
    warnings: list[str] = []
    monkeypatch.setattr(
        "ui.pages.data_journal_page.QMessageBox.warning",
        lambda *args, **kwargs: warnings.append(args[-1]),
    )
    _page, _sessions, classroom_repository, student_repository, _progress = _make_page()
    empty_classroom_repository = SqliteClassroomRepository()
    dialog = _AssignSessionDialog(empty_classroom_repository, student_repository)

    dialog._on_accept_clicked()

    assert dialog.result() != QDialog.DialogCode.Accepted
    assert len(warnings) == 1


def test_assigning_session_links_it_and_hides_button() -> None:
    page, session_repository, _classrooms, _students, progress_repository = _make_page()
    session_repository.save_session(_make_session("sess1"))
    page.on_enter()
    page._on_open_clicked("sess1")
    assert progress_repository.get_student_for_session("sess1") is None

    dialog = _AssignSessionDialog(page._classroom_repository, page._student_repository)
    dialog._classroom_combo.setCurrentIndex(0)
    dialog._student_combo.setCurrentIndex(0)
    dialog.accept()

    classroom_id, student_id = dialog.get_selection()
    progress_repository.link_session("sess1", student_id, classroom_id, "ohms-law")
    page._assign_button.setVisible(False)

    assert progress_repository.get_student_for_session("sess1") == "s1"
    assert page._assign_button.isHidden() is True


def test_no_reassignment_path_exists_for_already_linked_session() -> None:
    """§ "never silently move a session" — тағайындалған сессия үшін
    ЕШБІР UI әрекеті (батырма) мүлде жоқ, guard-пен де ЕМЕС."""
    page, session_repository, _classrooms, _students, progress_repository = _make_page()
    session_repository.save_session(_make_session("sess1"))
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    page.on_enter()

    page._on_open_clicked("sess1")

    assert page._assign_button.isVisible() is False


def test_legacy_session_without_any_classroom_seeded_still_renders() -> None:
    """Ешбір сынып/оқушы жасалмаған дерекқорда да бет құламауы тиіс —
    диалог бос комбо-бокспен ашылады, тек OK батырмасы бұғатталады."""
    session_repository = SqliteSessionRepository()
    classroom_repository = SqliteClassroomRepository()
    student_repository = SqliteStudentRepository()
    progress_repository = SqliteStudentProgressRepository(
        session_repository=session_repository,
        classroom_repository=classroom_repository,
        student_repository=student_repository,
    )
    session_repository.save_session(_make_session("sess1"))
    page = DataJournalPage(
        session_repository=session_repository,
        classroom_repository=classroom_repository,
        student_repository=student_repository,
        student_progress_repository=progress_repository,
    )
    page.on_enter()

    assert page._table.item(0, 2).text() == _UNASSIGNED_TEXT
    page._on_open_clicked("sess1")
    assert page._assign_button.isHidden() is False
