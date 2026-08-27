"""domain/services/sync_migration.py::backfill_session_sync_queue()
тесттері (Phase 2: Experiment Session + Results + Feedback Cloud Sync).

``test_sync_migration.py`` (Phase 1 ``backfill_sync_ids``) -мен БІРДЕЙ
принцип: ескі (Phase 2 кодынан бұрын жазылған) жазбаларды outbox-қа
идемпотентті түрде қосу. Сценарий екі кезеңнен тұрады: (1) "ескі"
деректі outbox-СЫЗ репозиторийлермен жазу (§ Phase 2 кодынан БҰРЫНғы
файлды имитациялау), (2) СОЛ физикалық файлды ЖАҢА, outbox-МЕН
репозиторийлермен қайта ашып, backfill-ды нақты өндірістік сценариймен
БІРДЕЙ (§ ``app.py``/``MainWindow.__init__`` де дәл осылай шақырады)
шақыру."""

import tempfile
from datetime import datetime, timezone
from pathlib import Path

from domain.entities.classroom import Classroom
from domain.entities.experiment_feedback_result import ExperimentFeedbackResult, TeacherAssessment
from domain.entities.experiment_session import ExperimentSession
from domain.entities.measurement import Measurement
from domain.entities.student import Student
from domain.entities.user_role import UserRole
from domain.services.sync_migration import backfill_session_sync_queue
from infrastructure.storage.sqlite_classroom_repository import SqliteClassroomRepository
from infrastructure.storage.sqlite_feedback_repository import SqliteFeedbackRepository
from infrastructure.storage.sqlite_session_repository import SqliteSessionRepository
from infrastructure.storage.sqlite_student_progress_repository import SqliteStudentProgressRepository
from infrastructure.storage.sqlite_student_repository import SqliteStudentRepository
from infrastructure.storage.sqlite_sync_outbox_repository import SqliteSyncOutboxRepository

_NOW = datetime.now(timezone.utc)


def _seed_pre_phase2_data(db_path: str) -> None:
    """Outbox-СЫЗ репозиторийлер арқылы "ескі" (Phase 2 outbox
    сымдалуынан БҰРЫНғы) деректі жазады — ЕШБІР outbox жазбасы жасалмайды."""
    classroom_repo = SqliteClassroomRepository(db_path)
    student_repo = SqliteStudentRepository(db_path)
    session_repo = SqliteSessionRepository(db_path)
    feedback_repo = SqliteFeedbackRepository(db_path)
    progress_repo = SqliteStudentProgressRepository(
        db_path,
        session_repository=session_repo,
        feedback_repository=feedback_repo,
        classroom_repository=classroom_repo,
        student_repository=student_repo,
    )

    classroom_repo.create(Classroom(id="c1", name="8A", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER)
    student_repo.create(
        Student(id="s1", classroom_id="c1", first_name="A", last_name="B", created_at=_NOW, updated_at=_NOW),
        UserRole.TEACHER,
    )
    progress_repo.link_session("sess1", "s1", "c1", "ohms-law")
    session_repo.save_session(
        ExperimentSession(
            id="sess1", experiment_id="ohms-law", started_at=_NOW, ended_at=_NOW,
            measurements=[Measurement(timestamp=_NOW, values={"v": 1.0}, experiment_id="ohms-law")],
        )
    )
    feedback_repo.save_submission(
        ExperimentFeedbackResult(experiment_id="ohms-law", session_id="sess1", submitted_at=_NOW)
    )
    feedback_repo.save_teacher_assessment(
        "sess1", "ohms-law", TeacherAssessment(score=8, comment="Жақсы"), UserRole.TEACHER
    )


def _reopen_with_outbox(db_path: str, outbox: SqliteSyncOutboxRepository) -> tuple:
    """§ Нақты өндірістік сценарий: қолданба ЖАҢАРТЫЛЫП, ЕНДІ outbox-пен
    сымдалған репозиторийлермен СОЛ файлды қайта ашады (§ ``app.py::
    build_main_window()``-пен БІРДЕЙ композиция)."""
    classroom_repo = SqliteClassroomRepository(db_path, sync_outbox_repository=outbox)
    student_repo = SqliteStudentRepository(db_path, sync_outbox_repository=outbox)
    session_repo = SqliteSessionRepository(db_path, sync_outbox_repository=outbox)
    feedback_repo = SqliteFeedbackRepository(db_path, sync_outbox_repository=outbox)
    progress_repo = SqliteStudentProgressRepository(
        db_path,
        session_repository=session_repo,
        feedback_repository=feedback_repo,
        classroom_repository=classroom_repo,
        student_repository=student_repo,
        sync_outbox_repository=outbox,
    )
    return session_repo, progress_repo, feedback_repo


def test_backfill_enqueues_pre_existing_session_link_feedback_and_assessment() -> None:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db_path = str(Path(tmp) / "test.db")
        _seed_pre_phase2_data(db_path)
        outbox = SqliteSyncOutboxRepository(db_path)
        session_repo, progress_repo, feedback_repo = _reopen_with_outbox(db_path, outbox)

        updated_count = backfill_session_sync_queue(session_repo, progress_repo, feedback_repo)

        assert updated_count == 4  # session + link + feedback_result + teacher_assessment
        entity_types = {entry.entity_type for entry in outbox.list_all()}
        assert entity_types == {"session", "session_student_link", "feedback_result", "teacher_assessment"}


def test_backfill_is_idempotent_when_run_multiple_times() -> None:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db_path = str(Path(tmp) / "test.db")
        _seed_pre_phase2_data(db_path)
        outbox = SqliteSyncOutboxRepository(db_path)
        session_repo, progress_repo, feedback_repo = _reopen_with_outbox(db_path, outbox)

        first = backfill_session_sync_queue(session_repo, progress_repo, feedback_repo)
        second = backfill_session_sync_queue(session_repo, progress_repo, feedback_repo)

        assert first == 4
        assert second == 4  # § sync_state ӘЛІ 'synced' емес (ешбір push болған жоқ) — қайта кезектеу заңды
        assert outbox.count_pending() == 4  # ешбір дубликат жазба (§ UNIQUE constraint)


def test_backfill_skips_already_synced_records() -> None:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db_path = str(Path(tmp) / "test.db")
        _seed_pre_phase2_data(db_path)
        outbox = SqliteSyncOutboxRepository(db_path)
        session_repo, progress_repo, feedback_repo = _reopen_with_outbox(db_path, outbox)
        session_repo.mark_session_synced("sess1", server_revision=1)
        progress_repo.mark_link_synced("sess1", server_revision=1)
        feedback_repo.mark_feedback_synced("sess1", server_revision=1)
        feedback_repo.mark_teacher_assessment_synced("sess1", server_revision=1)

        updated_count = backfill_session_sync_queue(session_repo, progress_repo, feedback_repo)

        assert updated_count == 0


def test_pending_outbox_entries_survive_restart() -> None:
    """§17/§29 "Restart Safety": outbox durable — репозиторийлер ЖАҢА
    Python данасымен қайта ашылса да (§ "restart the application"),
    күтілетін жазбалар жоғалмайды."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db_path = str(Path(tmp) / "test.db")
        outbox = SqliteSyncOutboxRepository(db_path)
        session_repo = SqliteSessionRepository(db_path, sync_outbox_repository=outbox)
        session_repo.save_session(
            ExperimentSession(
                id="sess1", experiment_id="ohms-law", started_at=_NOW, ended_at=_NOW,
                measurements=[Measurement(timestamp=_NOW, values={"v": 1.0}, experiment_id="ohms-law")],
            )
        )

        # "Рестарт" — тіпті ЖАҢА Python объектілерімен, СОЛ файлды қайта ашу.
        reopened_outbox = SqliteSyncOutboxRepository(db_path)

        assert reopened_outbox.count_pending() == 1
        assert reopened_outbox.list_all()[0].entity_type == "session"
