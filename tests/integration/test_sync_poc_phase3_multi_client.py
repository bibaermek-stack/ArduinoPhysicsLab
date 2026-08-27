"""§12 "Live Demo / POC" / Multi-Client Acceptance Test (Phase 3:
Production Authentication + Authorization), acceptance items 25-29:

    Teacher A -> Classroom 8A -> Student A
    Teacher B -> Classroom 8B -> Student B

  25. Teacher A and Teacher B are isolated
  26. Student A and Student B are isolated
  27. authorized Student -> Cloud -> Teacher round trip works
  28. Teacher assessment -> Cloud -> correct Student works
  29. unauthorized second teacher receives no private records

Full desktop-client simulation (SyncEngine + real repositories, not raw
HTTP) — ``tests/integration/test_sync_poc_phase2_two_clients.py``-мен
БІРДЕЙ ``TestClient``-негізді shared-server паттерні."""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from domain.entities.classroom import Classroom
from domain.entities.experiment_feedback_result import (
    ExperimentFeedbackResult,
    ReflectionAnswer,
    TeacherAssessment,
)
from domain.entities.experiment_session import ExperimentSession
from domain.entities.measurement import Measurement
from domain.entities.student import Student
from domain.entities.teacher import Teacher
from domain.entities.user_role import UserRole
from domain.services.sync_engine import SyncEngine
from domain.services.teacher_pin import hash_pin
from infrastructure.storage.sqlite_classroom_repository import SqliteClassroomRepository
from infrastructure.storage.sqlite_feedback_repository import SqliteFeedbackRepository
from infrastructure.storage.sqlite_session_repository import SqliteSessionRepository
from infrastructure.storage.sqlite_student_progress_repository import SqliteStudentProgressRepository
from infrastructure.storage.sqlite_student_repository import SqliteStudentRepository
from infrastructure.storage.sqlite_sync_outbox_repository import SqliteSyncOutboxRepository
from infrastructure.storage.sqlite_teacher_repository import SqliteTeacherRepository
from infrastructure.sync.http_sync_api_client import HttpSyncApiClient
from server.app.db.session import Base, get_db
from server.app.main import app as fastapi_app

_TEST_API_KEY = "dev-local-only-key"
_NOW = datetime.now(timezone.utc)


@pytest.fixture()
def shared_server() -> TestClient:
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def _override_get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    fastapi_app.dependency_overrides[get_db] = _override_get_db
    with TestClient(fastapi_app) as test_client:
        yield test_client
    fastapi_app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)


def _build_client(server: TestClient, role: str, sync_id: str, classroom_id: str = ""):
    """Синтетикалық (§33 "POC data must be synthetic") клиент — толық
    Phase 1+2+3 репозиторийі + аутентификация."""
    outbox = SqliteSyncOutboxRepository()
    classroom_repo = SqliteClassroomRepository(sync_outbox_repository=outbox)
    student_repo = SqliteStudentRepository(sync_outbox_repository=outbox)
    teacher_repo = SqliteTeacherRepository(sync_outbox_repository=outbox)
    session_repo = SqliteSessionRepository(sync_outbox_repository=outbox)
    feedback_repo = SqliteFeedbackRepository(sync_outbox_repository=outbox)
    progress_repo = SqliteStudentProgressRepository(
        session_repository=session_repo, feedback_repository=feedback_repo,
        classroom_repository=classroom_repo, student_repository=student_repo,
        sync_outbox_repository=outbox,
    )
    if role == "teacher":
        teacher_repo.apply_remote_upsert(
            Teacher(
                id=sync_id, full_name=f"Teacher {sync_id}", pin_hash=hash_pin(f"pin-{sync_id}"),
                created_at=_NOW, updated_at=_NOW, sync_id=sync_id,
            )
        )
    else:
        student_repo.apply_remote_upsert(
            Student(
                id=sync_id, classroom_id=classroom_id, first_name=f"Student", last_name=sync_id,
                created_at=_NOW, updated_at=_NOW, student_code=f"code-{sync_id}", sync_id=sync_id,
            )
        )
    api_client = HttpSyncApiClient(base_url="http://testserver", api_key=_TEST_API_KEY, client=server)
    cursors: dict[str, datetime] = {}
    token_cache: dict[str, tuple] = {}
    engine = SyncEngine(
        classroom_repo, student_repo, teacher_repo, outbox, api_client,
        get_pull_cursor=lambda entity_type: cursors.get(entity_type),
        set_pull_cursor=lambda entity_type, value: cursors.__setitem__(entity_type, value),
        session_repository=session_repo,
        student_progress_repository=progress_repo,
        feedback_repository=feedback_repo,
        get_active_role_and_sync_id=lambda: (role, sync_id),
        get_cached_token=lambda: token_cache.get("token"),
        set_cached_token=lambda token, expires_at, r, s: token_cache.__setitem__("token", (token, expires_at, r, s)),
    )
    return {
        "engine": engine, "classroom": classroom_repo, "student": student_repo, "teacher": teacher_repo,
        "session": session_repo, "feedback": feedback_repo, "progress": progress_repo, "outbox": outbox,
    }


@pytest.fixture()
def two_teacher_world(shared_server: TestClient):
    """Teacher A -> 8A -> Student A. Teacher B -> 8B -> Student B."""
    teacher_a = _build_client(shared_server, "teacher", "ta")
    teacher_b = _build_client(shared_server, "teacher", "tb")
    student_a = _build_client(shared_server, "student", "sa", classroom_id="ca")
    student_b = _build_client(shared_server, "student", "sb", classroom_id="cb")

    teacher_a["classroom"].create(Classroom(id="ca", name="8A", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER)
    teacher_a["student"].create(
        Student(id="sa", classroom_id="ca", first_name="Student", last_name="A", created_at=_NOW, updated_at=_NOW, student_code="code-sa"),
        UserRole.TEACHER,
    )
    teacher_a["teacher"].set_assigned_classroom_ids("ta", ("ca",))
    teacher_a["engine"].run_sync()

    teacher_b["classroom"].create(Classroom(id="cb", name="8B", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER)
    teacher_b["student"].create(
        Student(id="sb", classroom_id="cb", first_name="Student", last_name="B", created_at=_NOW, updated_at=_NOW, student_code="code-sb"),
        UserRole.TEACHER,
    )
    teacher_b["teacher"].set_assigned_classroom_ids("tb", ("cb",))
    teacher_b["engine"].run_sync()

    student_a["engine"].run_sync()
    student_b["engine"].run_sync()

    return {"teacher_a": teacher_a, "teacher_b": teacher_b, "student_a": student_a, "student_b": student_b}


def _submit(client: dict, session_id: str, student_id: str, classroom_id: str, note: str) -> None:
    client["progress"].link_session(session_id, student_id, classroom_id, "ohms-law")
    client["session"].save_session(
        ExperimentSession(
            id=session_id, experiment_id="ohms-law", started_at=_NOW, ended_at=_NOW,
            measurements=[Measurement(timestamp=_NOW, values={"v": 1.0}, experiment_id="ohms-law")],
        )
    )
    client["feedback"].save_submission(
        ExperimentFeedbackResult(
            experiment_id="ohms-law", session_id=session_id,
            level3_answers=(ReflectionAnswer(question_id="r1", response_text=note),), submitted_at=_NOW,
        )
    )


# ---- 25. Teacher A and Teacher B are isolated -------------------------------


def test_teacher_a_and_teacher_b_are_isolated(two_teacher_world) -> None:
    teacher_a, teacher_b = two_teacher_world["teacher_a"], two_teacher_world["teacher_b"]

    result_a = teacher_a["engine"].run_sync()
    result_b = teacher_b["engine"].run_sync()

    assert result_a.status.value == "synced"
    assert result_b.status.value == "synced"
    assert teacher_a["classroom"].get("cb") is None  # § Teacher A never receives 8B
    assert teacher_a["student"].get("sb") is None
    assert teacher_b["classroom"].get("ca") is None  # § Teacher B never receives 8A
    assert teacher_b["student"].get("sa") is None


# ---- 26. Student A and Student B are isolated -------------------------------


def test_student_a_and_student_b_are_isolated(two_teacher_world) -> None:
    student_a, student_b = two_teacher_world["student_a"], two_teacher_world["student_b"]
    _submit(student_a, "sess-a", "sa", "ca", "A-дың құпия жауабы")
    _submit(student_b, "sess-b", "sb", "cb", "B-нің құпия жауабы")

    student_a["engine"].run_sync()
    student_b["engine"].run_sync()

    assert student_a["feedback"].get_result("sess-b") is None  # § Student A never receives B's feedback
    assert student_a["session"].exists("sess-b") is False
    assert student_b["feedback"].get_result("sess-a") is None
    assert student_b["session"].exists("sess-a") is False


# ---- 27/28. Authorized round trip: student -> cloud -> teacher -> cloud -> student ----


def test_authorized_student_teacher_round_trip(two_teacher_world) -> None:
    teacher_a, student_a = two_teacher_world["teacher_a"], two_teacher_world["student_a"]
    _submit(student_a, "sess-a", "sa", "ca", "Тәжірибе сәтті өтті")

    result_submit = student_a["engine"].run_sync()
    assert result_submit.status.value == "synced"

    result_pull = teacher_a["engine"].run_sync()
    assert result_pull.status.value == "synced"
    progress = teacher_a["progress"].get_progress("sa", "ohms-law")
    assert progress.status.name == "FEEDBACK_SUBMITTED"

    teacher_a["feedback"].save_teacher_assessment(
        "sess-a", "ohms-law", TeacherAssessment(score=10, comment="Керемет жұмыс"), UserRole.TEACHER
    )
    result_grade = teacher_a["engine"].run_sync()
    assert result_grade.status.value == "synced"

    result_student_pull = student_a["engine"].run_sync()
    assert result_student_pull.status.value == "synced"
    final = student_a["feedback"].get_result("sess-a")
    assert final.teacher_assessment is not None
    assert final.teacher_assessment.score == 10
    assert final.teacher_assessment.comment == "Керемет жұмыс"


# ---- 29. Unauthorized second teacher receives no private records -----------


def test_unauthorized_second_teacher_receives_no_private_records(two_teacher_world) -> None:
    """§16 "Live Demo": "Teacher B -> must NOT receive Student A private
    experiment data" — тіпті A-ның ТОЛЫҚ жұмысы бағаланғаннан кейін де."""
    teacher_a, teacher_b, student_a = (
        two_teacher_world["teacher_a"], two_teacher_world["teacher_b"], two_teacher_world["student_a"]
    )
    _submit(student_a, "sess-a", "sa", "ca", "Құпия зерттеу нәтижесі")
    student_a["engine"].run_sync()
    teacher_a["engine"].run_sync()
    teacher_a["feedback"].save_teacher_assessment(
        "sess-a", "ohms-law", TeacherAssessment(score=7, comment="Жақсы"), UserRole.TEACHER
    )
    teacher_a["engine"].run_sync()

    result_b = teacher_b["engine"].run_sync()

    assert result_b.status.value == "synced"  # § сервер қолжетімді, жай ғана ЕШБІР жеке дерек жоқ
    assert teacher_b["session"].exists("sess-a") is False
    assert teacher_b["feedback"].get_result("sess-a") is None
    assert teacher_b["student"].get("sa") is None
    assert teacher_b["progress"].get_progress("sa", "ohms-law").status.name == "NOT_STARTED"


def test_offline_student_then_reconnect_authenticated_sync_completes(two_teacher_world, monkeypatch) -> None:
    """§12 "Live Demo": stop server -> student local action succeeds
    offline, outbox retains pending op -> restart -> authentication
    restored -> sync completes."""
    student_a = two_teacher_world["student_a"]
    api_client = student_a["engine"]._api_client
    monkeypatch.setattr(api_client, "check_health", lambda: False)

    _submit(student_a, "sess-a", "sa", "ca", "Офлайн кездегі жұмыс")
    offline_result = student_a["engine"].run_sync()

    assert offline_result.status.value == "offline"
    assert student_a["outbox"].count_pending() == 3
    assert student_a["session"].exists("sess-a")

    monkeypatch.undo()
    online_result = student_a["engine"].run_sync()

    assert online_result.status.value == "synced"
    assert student_a["outbox"].count_pending() == 0
