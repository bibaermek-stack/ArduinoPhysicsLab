"""Phase 2 (Experiment Session + Results + Feedback Cloud Sync) —
session/session_student_link/feedback_result/teacher_assessment
репозиторийлерінің outbox байланысы.

``tests/unit/test_sync_repository_outbox_wiring.py``-мен (Phase 1) БІРДЕЙ
принцип: outbox параметрі берілмесе no-op, жазу дұрыс OutboxEntry
кезектейді, remote apply/mark_synced ЕШБІР жаңа outbox жазбасын
жасамайды, бірнеше кезекті офлайн өзгеріс БІР ғана тиімді push-ке
коалесцияланады.
"""

from datetime import datetime, timezone

from domain.entities.classroom import Classroom
from domain.entities.experiment_feedback_result import (
    ExperimentFeedbackResult,
    MultipleChoiceAnswer,
    TeacherAssessment,
)
from domain.entities.experiment_session import ExperimentSession
from domain.entities.measurement import Measurement
from domain.entities.outbox_entry import OutboxOperation
from domain.entities.student import Student
from domain.entities.sync_state import SyncState
from domain.entities.user_role import UserRole
from infrastructure.storage.sqlite_classroom_repository import SqliteClassroomRepository
from infrastructure.storage.sqlite_feedback_repository import SqliteFeedbackRepository
from infrastructure.storage.sqlite_session_repository import SqliteSessionRepository
from infrastructure.storage.sqlite_student_progress_repository import SqliteStudentProgressRepository
from infrastructure.storage.sqlite_student_repository import SqliteStudentRepository
from infrastructure.storage.sqlite_sync_outbox_repository import SqliteSyncOutboxRepository

_NOW = datetime.now(timezone.utc)


def _make_session(session_id: str = "sess1") -> ExperimentSession:
    return ExperimentSession(
        id=session_id,
        experiment_id="ohms-law",
        started_at=_NOW,
        ended_at=_NOW,
        measurements=[
            Measurement(timestamp=_NOW, values={"voltage": 1.0}, experiment_id="ohms-law")
        ],
    )


# ---- ExperimentSession ----------------------------------------------------


def test_session_repository_without_outbox_never_enqueues() -> None:
    repo = SqliteSessionRepository()
    repo.save_session(_make_session())
    assert repo.exists("sess1")


def test_session_save_enqueues_upsert() -> None:
    outbox = SqliteSyncOutboxRepository()
    repo = SqliteSessionRepository(sync_outbox_repository=outbox)

    repo.save_session(_make_session())

    entries = outbox.list_all()
    assert len(entries) == 1
    assert entries[0].entity_type == "session"
    assert entries[0].entity_sync_id == "sess1"
    assert entries[0].operation is OutboxOperation.UPSERT


def test_session_repeated_saves_coalesce_to_one_outbox_entry() -> None:
    outbox = SqliteSyncOutboxRepository()
    repo = SqliteSessionRepository(sync_outbox_repository=outbox)

    for _ in range(3):
        repo.save_session(_make_session())

    assert outbox.count_pending() == 1


def test_session_apply_remote_does_not_enqueue() -> None:
    outbox = SqliteSyncOutboxRepository()
    repo = SqliteSessionRepository(sync_outbox_repository=outbox)

    repo.apply_remote_session(
        {
            "sync_id": "sess1",
            "experiment_id": "ohms-law",
            "experiment_title": "Ohm",
            "experiment_display_number": None,
            "started_at": _NOW.isoformat(),
            "ended_at": _NOW.isoformat(),
            "status": "finalized",
            "measurement_count": 5,
            "created_at": _NOW.isoformat(),
            "updated_at": _NOW.isoformat(),
            "server_revision": 1,
        }
    )

    assert outbox.count_pending() == 0
    payload = repo.get_sync_payload("sess1")
    assert payload is not None
    assert payload["sync_state"] == "synced"
    assert payload["measurement_count"] == 5


def test_session_mark_synced_does_not_enqueue() -> None:
    outbox = SqliteSyncOutboxRepository()
    repo = SqliteSessionRepository(sync_outbox_repository=outbox)
    repo.save_session(_make_session())
    outbox.mark_success(outbox.list_all()[0].id)

    repo.mark_session_synced("sess1", server_revision=1)

    assert outbox.count_pending() == 0
    assert repo.get_sync_payload("sess1")["sync_state"] == "synced"


# ---- session_student_link ---------------------------------------------


def _make_progress_repo(outbox: SqliteSyncOutboxRepository | None = None):
    classroom_repo = SqliteClassroomRepository(sync_outbox_repository=outbox)
    student_repo = SqliteStudentRepository(sync_outbox_repository=outbox)
    classroom_repo.create(Classroom(id="c1", name="8A", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER)
    student_repo.create(
        Student(id="s1", classroom_id="c1", first_name="A", last_name="B", created_at=_NOW, updated_at=_NOW),
        UserRole.TEACHER,
    )
    progress_repo = SqliteStudentProgressRepository(
        classroom_repository=classroom_repo,
        student_repository=student_repo,
        sync_outbox_repository=outbox,
    )
    return progress_repo


def test_link_session_enqueues_upsert() -> None:
    outbox = SqliteSyncOutboxRepository()
    progress_repo = _make_progress_repo(outbox)

    progress_repo.link_session("sess1", "s1", "c1", "ohms-law")

    entries = [e for e in outbox.list_all() if e.entity_type == "session_student_link"]
    assert len(entries) == 1
    assert entries[0].entity_sync_id == "sess1"


def test_link_sync_payload_uses_global_sync_ids() -> None:
    outbox = SqliteSyncOutboxRepository()
    progress_repo = _make_progress_repo(outbox)
    progress_repo.link_session("sess1", "s1", "c1", "ohms-law")

    payload = progress_repo.get_link_sync_payload("sess1")

    assert payload["student_sync_id"] == "s1"
    assert payload["classroom_sync_id"] == "c1"
    assert payload["session_sync_id"] == "sess1"


def test_link_apply_remote_does_not_enqueue() -> None:
    outbox = SqliteSyncOutboxRepository()
    progress_repo = _make_progress_repo(outbox)
    # § "setup" ӨЗІ classroom/student create() арқылы outbox-қа 2 жазба
    # қосады — тексерілетіні тек apply_remote_link() ЖАҢА жазба
    # қоспайтыны (§ "pull арқылы алынған дерек серверге ҚАЙТА
    # жіберілмеуі керек").
    pending_before = outbox.count_pending()

    progress_repo.apply_remote_link(
        {
            "session_sync_id": "sess1",
            "student_sync_id": "s1",
            "classroom_sync_id": "c1",
            "experiment_id": "ohms-law",
            "linked_at": _NOW.isoformat(),
            "server_revision": 1,
        }
    )

    assert outbox.count_pending() == pending_before
    assert progress_repo.get_student_for_session("sess1") == "s1"


# ---- feedback_result + teacher_assessment (БІР физикалық жол) -----------


def _make_result(session_id: str = "sess1") -> ExperimentFeedbackResult:
    return ExperimentFeedbackResult(
        experiment_id="ohms-law",
        session_id=session_id,
        level1_answers=(MultipleChoiceAnswer(question_id="q1", selected_option_index=0),),
        level1_score=1,
        level1_total=1,
        level1_percentage=100.0,
    )


def test_feedback_draft_save_enqueues_feedback_result_only() -> None:
    outbox = SqliteSyncOutboxRepository()
    repo = SqliteFeedbackRepository(sync_outbox_repository=outbox)

    repo.save_draft(_make_result())

    entity_types = {e.entity_type for e in outbox.list_all()}
    assert entity_types == {"feedback_result"}


def test_teacher_assessment_save_enqueues_teacher_assessment_only() -> None:
    """§6: мұғалім бағасы БӨЛЕК entity_type ретінде кезектеледі — студент
    ешбір жоба сақтамаған сессияда да (§ pre-insert empty shell)."""
    outbox = SqliteSyncOutboxRepository()
    repo = SqliteFeedbackRepository(sync_outbox_repository=outbox)

    repo.save_teacher_assessment(
        "sess1", "ohms-law", TeacherAssessment(score=9, comment="Жақсы жұмыс"), UserRole.TEACHER
    )

    entity_types = {e.entity_type for e in outbox.list_all()}
    assert entity_types == {"teacher_assessment"}


def test_student_and_teacher_writes_do_not_clobber_each_others_sync_state() -> None:
    """§ "екі жазба тәуелсіз шақырылады, бірінің жазуы екіншісінің
    деректерін ЕШҚАШАН жоймайды" — sync метадатасы да СОЛ принципті
    сақтауы керек (§ Phase 2 Final Report "7. Feedback synchronization")."""
    outbox = SqliteSyncOutboxRepository()
    repo = SqliteFeedbackRepository(sync_outbox_repository=outbox)

    repo.save_submission(_make_result())
    repo.mark_feedback_synced("sess1", server_revision=1)

    repo.save_teacher_assessment(
        "sess1", "ohms-law", TeacherAssessment(score=9, comment="Жақсы"), UserRole.TEACHER
    )

    feedback_payload = repo.get_feedback_sync_payload("sess1")
    assert feedback_payload["sync_state"] == "synced"
    assert feedback_payload["server_revision"] == 1

    assessment_payload = repo.get_teacher_assessment_sync_payload("sess1")
    assert assessment_payload["sync_state"] == "pending_upload"

    repo.mark_teacher_assessment_synced("sess1", server_revision=1)

    editing_result = _make_result()
    repo.save_submission(editing_result)

    assessment_after = repo.get_teacher_assessment_sync_payload("sess1")
    assert assessment_after["score"] == 9
    assert assessment_after["sync_state"] == "synced"


def test_teacher_assessment_sync_payload_is_none_when_not_yet_scored() -> None:
    outbox = SqliteSyncOutboxRepository()
    repo = SqliteFeedbackRepository(sync_outbox_repository=outbox)
    repo.save_draft(_make_result())

    assert repo.get_teacher_assessment_sync_payload("sess1") is None


def test_feedback_apply_remote_preserves_teacher_columns() -> None:
    outbox = SqliteSyncOutboxRepository()
    repo = SqliteFeedbackRepository(sync_outbox_repository=outbox)
    repo.save_teacher_assessment(
        "sess1", "ohms-law", TeacherAssessment(score=7, comment="Орташа"), UserRole.TEACHER
    )

    repo.apply_remote_feedback(
        {
            "sync_id": "sess1",
            "experiment_id": "ohms-law",
            "is_draft": False,
            "level1_answers": [],
            "level1_score": 1,
            "level1_total": 1,
            "level1_percentage": 100.0,
            "level2_answers": [],
            "level3_answers": [],
            "self_assessment": None,
            "submitted_at": _NOW.isoformat(),
            "created_at": _NOW.isoformat(),
            "updated_at": _NOW.isoformat(),
            "server_revision": 1,
        }
    )

    result = repo.get_result("sess1")
    assert result.teacher_assessment.score == 7
    assert result.teacher_assessment.comment == "Орташа"


def test_teacher_assessment_apply_remote_preserves_student_columns() -> None:
    outbox = SqliteSyncOutboxRepository()
    repo = SqliteFeedbackRepository(sync_outbox_repository=outbox)
    repo.save_submission(_make_result())

    repo.apply_remote_teacher_assessment(
        {"sync_id": "sess1", "score": 8, "comment": "Жақсы", "reviewed": True, "server_revision": 1}
    )

    result = repo.get_result("sess1")
    assert result.level1_score == 1
    assert result.teacher_assessment.score == 8


def test_feedback_and_teacher_assessment_apply_remote_do_not_enqueue() -> None:
    outbox = SqliteSyncOutboxRepository()
    repo = SqliteFeedbackRepository(sync_outbox_repository=outbox)

    repo.apply_remote_feedback(
        {
            "sync_id": "sess1",
            "experiment_id": "ohms-law",
            "is_draft": True,
            "level1_answers": [],
            "level1_score": 0,
            "level1_total": 0,
            "level1_percentage": 0.0,
            "level2_answers": [],
            "level3_answers": [],
            "self_assessment": None,
            "submitted_at": None,
            "created_at": _NOW.isoformat(),
            "updated_at": _NOW.isoformat(),
            "server_revision": 1,
        }
    )
    repo.apply_remote_teacher_assessment(
        {"sync_id": "sess1", "score": 6, "comment": "", "reviewed": True, "server_revision": 1}
    )

    assert outbox.count_pending() == 0
