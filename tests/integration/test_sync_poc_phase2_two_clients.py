"""§36 "Automated Tests — Two Clients" (Phase 2: Experiment Session +
Results + Feedback Cloud Sync) — PRIMARY acceptance scenario (§16):

    Client A = student computer
    Client B = teacher computer

Seed shared Teacher/Classroom/Student (§ Phase 1 entities, reused
unchanged). Student on A submits a synthetic experiment result, syncs.
Teacher on B syncs, discovers the submission via the EXISTING
``IStudentProgressRepository``/``IFeedbackRepository`` abstractions
(no cloud-only UI code), reviews with score 9/10 + Kazakh comment,
saves locally, syncs. Student on A syncs and sees the reviewed result.

Also covers §17 "Offline Student Scenario" and §18 "Offline Teacher
Scenario" within the same shared-server fixture, and duplicate-
prevention/restart-safety per §29.

``tests/integration/test_sync_poc_two_clients.py`` (Phase 1) -мен БІРДЕЙ
``TestClient``-негізді shared-server паттерні (§ ASGITransport
sync/async алшақтығын жабу үшін)."""

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


_SHARED_TEACHER_PIN_HASH = hash_pin("135790")
_SHARED_STUDENT_CODE = "424242"


def _build_client(server: TestClient, role: str, sync_id: str):
    """Синтетикалық (§33 "POC data must be synthetic") клиент — БАРЛЫҚ
    Phase 1 + Phase 2 репозиторийі, ОРТАҚ outbox-пен, толық ``app.py::
    build_main_window()``-мен БІРДЕЙ композиция.

    § Phase 3: ``role``/``sync_id`` — бұл клиенттің аутентификацияланған
    сәйкестігі (§ ``get_active_role_and_sync_id``). Тиісті жергілікті
    жазба ``apply_remote_upsert()`` арқылы АЛДЫН АЛА провизияланады
    (§ ЕШБІР outbox жазуы — тек credential шешу үшін, § ``tests/
    integration/test_sync_poc_two_clients.py``-мен БІРДЕЙ bootstrap
    принципі)."""
    outbox = SqliteSyncOutboxRepository()
    classroom_repo = SqliteClassroomRepository(sync_outbox_repository=outbox)
    student_repo = SqliteStudentRepository(sync_outbox_repository=outbox)
    teacher_repo = SqliteTeacherRepository(sync_outbox_repository=outbox)
    session_repo = SqliteSessionRepository(sync_outbox_repository=outbox)
    feedback_repo = SqliteFeedbackRepository(sync_outbox_repository=outbox)
    progress_repo = SqliteStudentProgressRepository(
        session_repository=session_repo,
        feedback_repository=feedback_repo,
        classroom_repository=classroom_repo,
        student_repository=student_repo,
        sync_outbox_repository=outbox,
    )
    if role == "teacher" and teacher_repo.get(sync_id) is None:
        teacher_repo.apply_remote_upsert(
            Teacher(
                id=sync_id, full_name="Мұғалім Тест", pin_hash=_SHARED_TEACHER_PIN_HASH,
                created_at=_NOW, updated_at=_NOW, sync_id=sync_id,
            )
        )
    elif role == "student" and student_repo.get(sync_id) is None:
        student_repo.apply_remote_upsert(
            Student(
                id=sync_id, classroom_id="c1", first_name="Айдана", last_name="Тест",
                created_at=_NOW, updated_at=_NOW, student_code=_SHARED_STUDENT_CODE, sync_id=sync_id,
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
        "engine": engine,
        "classroom": classroom_repo,
        "student": student_repo,
        "teacher": teacher_repo,
        "session": session_repo,
        "feedback": feedback_repo,
        "progress": progress_repo,
        "outbox": outbox,
        "api_client": api_client,
    }


def _seed_shared_roster(client_teacher: dict, client_student: dict) -> None:
    """Ортақ Teacher/Classroom/Student-ды МҰҒАЛІМ клиентінде құрып (§
    нақты рөл — тек мұғалім классрум/оқушы құра алады, § authorization.
    py), екі клиентке де синхрондайды (§16 "Seed/sync shared: Teacher,
    Classroom, Student")."""
    client_teacher["classroom"].create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    client_teacher["student"].create(
        Student(
            id="s1", classroom_id="c1", first_name="Айдана", last_name="Тест",
            created_at=_NOW, updated_at=_NOW, student_code=_SHARED_STUDENT_CODE,
        ),
        UserRole.TEACHER,
    )
    client_teacher["teacher"].set_assigned_classroom_ids("t1", ("c1",))
    client_teacher["engine"].run_sync()
    client_student["engine"].run_sync()


def _student_submits(client: dict, session_id: str = "sess1") -> None:
    """§8 "Local-First Student Submission" — толық жергілікті ағын:
    link -> session (measurements-пен) -> feedback submission."""
    client["progress"].link_session(session_id, "s1", "c1", "ohms-law")
    client["session"].save_session(
        ExperimentSession(
            id=session_id, experiment_id="ohms-law", started_at=_NOW, ended_at=_NOW,
            measurements=[Measurement(timestamp=_NOW, values={"voltage": 2.5}, experiment_id="ohms-law")],
        )
    )
    client["feedback"].save_submission(
        ExperimentFeedbackResult(
            experiment_id="ohms-law",
            session_id=session_id,
            level3_answers=(ReflectionAnswer(question_id="r1", response_text="Тәжірибе сәтті өтті"),),
            submitted_at=_NOW,
        )
    )


def test_primary_acceptance_scenario_student_submit_teacher_review_student_sees_result(
    shared_server: TestClient,
) -> None:
    """§16/§41 "Final Acceptance Scenario" — Phase 2-нің НЕГІЗГІ сценарийі."""
    client_a = _build_client(shared_server, "student", "s1")  # student PC
    client_b = _build_client(shared_server, "teacher", "t1")  # teacher PC
    _seed_shared_roster(client_b, client_a)

    # --- Client A: student submits a synthetic experiment result ---
    _student_submits(client_a)
    result_a1 = client_a["engine"].run_sync()
    assert result_a1.status.value == "synced"
    assert result_a1.pushed == 3  # session + session_student_link + feedback_result

    # --- Client B: teacher syncs, discovers the submission via EXISTING repos ---
    result_b1 = client_b["engine"].run_sync()
    assert result_b1.status.value == "synced"
    assert result_b1.pulled == 3

    progress = client_b["progress"].get_progress("s1", "ohms-law")
    assert progress.status.name == "FEEDBACK_SUBMITTED"
    feedback_seen_by_teacher = client_b["feedback"].get_result("sess1")
    assert feedback_seen_by_teacher is not None
    assert feedback_seen_by_teacher.level3_answers[0].response_text == "Тәжірибе сәтті өтті"

    # --- Client B: teacher reviews (score 9/10 + Kazakh comment), saves locally ---
    client_b["feedback"].save_teacher_assessment(
        "sess1", "ohms-law", TeacherAssessment(score=9, comment="Өте жақсы орындалған жұмыс"), UserRole.TEACHER
    )
    assert client_b["progress"].get_progress("s1", "ohms-law").status.name == "REVIEWED"

    result_b2 = client_b["engine"].run_sync()
    assert result_b2.pushed == 1  # teacher_assessment only

    # --- Client A: student syncs, sees the reviewed result ---
    result_a2 = client_a["engine"].run_sync()
    assert result_a2.pulled == 1

    final_result = client_a["feedback"].get_result("sess1")
    assert final_result.teacher_assessment is not None
    assert final_result.teacher_assessment.score == 9
    assert final_result.teacher_assessment.comment == "Өте жақсы орындалған жұмыс"
    final_progress = client_a["progress"].get_progress("s1", "ohms-law")
    assert final_progress.status.name == "REVIEWED"
    assert final_progress.teacher_score == 9


def test_no_duplicate_records_after_repeated_sync_cycles(shared_server: TestClient) -> None:
    """§12 "Idempotent Server Upsert" / §36 "assert no duplicates"."""
    client_a = _build_client(shared_server, "student", "s1")
    client_b = _build_client(shared_server, "teacher", "t1")
    _seed_shared_roster(client_b, client_a)
    _student_submits(client_a)
    client_a["engine"].run_sync()

    for _ in range(3):
        client_b["engine"].run_sync()

    login_response = shared_server.post(
        "/api/v1/auth/teacher-login",
        json={"sync_id": "t1", "pin_hash": _SHARED_TEACHER_PIN_HASH},
        headers={"X-API-Key": _TEST_API_KEY},
    )
    token = login_response.json()["access_token"]
    pulled = shared_server.get(
        "/api/v1/sync/sessions",
        headers={"X-API-Key": _TEST_API_KEY, "Authorization": f"Bearer {token}"},
    ).json()["items"]
    assert len(pulled) == 1


def test_offline_student_scenario(shared_server: TestClient, monkeypatch) -> None:
    """§17 "Offline Student Scenario": server down -> student submits ->
    local save succeeds -> outbox has pending records -> server comes
    back -> sync -> teacher pulls -> submission appears exactly once."""
    client_a = _build_client(shared_server, "student", "s1")
    client_b = _build_client(shared_server, "teacher", "t1")
    _seed_shared_roster(client_b, client_a)

    monkeypatch.setattr(client_a["api_client"], "check_health", lambda: False)
    _student_submits(client_a)
    offline_result = client_a["engine"].run_sync()
    assert offline_result.status.value == "offline"

    # Local save fully succeeded despite the server being "down".
    assert client_a["session"].exists("sess1")
    assert client_a["feedback"].get_result("sess1") is not None
    assert client_a["outbox"].count_pending() == 3

    monkeypatch.undo()
    online_result = client_a["engine"].run_sync()
    assert online_result.status.value == "synced"
    assert client_a["outbox"].count_pending() == 0

    client_b["engine"].run_sync()
    progress = client_b["progress"].get_progress("s1", "ohms-law")
    assert progress.status.name == "FEEDBACK_SUBMITTED"


def test_offline_teacher_scenario(shared_server: TestClient, monkeypatch) -> None:
    """§18 "Offline Teacher Scenario": teacher already has the
    submission locally -> server goes down -> teacher reviews -> local
    REVIEWED state -> server returns -> assessment syncs -> student
    pulls it."""
    client_a = _build_client(shared_server, "student", "s1")
    client_b = _build_client(shared_server, "teacher", "t1")
    _seed_shared_roster(client_b, client_a)
    _student_submits(client_a)
    client_a["engine"].run_sync()
    client_b["engine"].run_sync()

    monkeypatch.setattr(client_b["api_client"], "check_health", lambda: False)
    client_b["feedback"].save_teacher_assessment(
        "sess1", "ohms-law", TeacherAssessment(score=6, comment="Қанағаттанарлық"), UserRole.TEACHER
    )
    assert client_b["progress"].get_progress("s1", "ohms-law").status.name == "REVIEWED"
    offline_result = client_b["engine"].run_sync()
    assert offline_result.status.value == "offline"
    assert client_b["outbox"].count_pending() == 1

    monkeypatch.undo()
    client_b["engine"].run_sync()
    client_a["engine"].run_sync()

    assert client_a["feedback"].get_result("sess1").teacher_assessment.score == 6


def test_pending_records_survive_restart_then_sync_successfully(shared_server: TestClient) -> None:
    """§29 "Restart Safety": pending session/link/feedback outbox
    жазбалары ЖАҢА, физикалық файлды қайта ашатын репозиторий
    данасымен (§ "restart the desktop app") де сақталады, содан кейін
    қалыпты синхрондалады."""
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db_path = str(Path(tmp) / "client_a.db")
        outbox = SqliteSyncOutboxRepository(db_path)
        classroom_repo = SqliteClassroomRepository(db_path, sync_outbox_repository=outbox)
        student_repo = SqliteStudentRepository(db_path, sync_outbox_repository=outbox)
        teacher_repo = SqliteTeacherRepository(db_path, sync_outbox_repository=outbox)
        session_repo = SqliteSessionRepository(db_path, sync_outbox_repository=outbox)
        feedback_repo = SqliteFeedbackRepository(db_path, sync_outbox_repository=outbox)
        progress_repo = SqliteStudentProgressRepository(
            db_path, session_repository=session_repo, feedback_repository=feedback_repo,
            classroom_repository=classroom_repo, student_repository=student_repo,
            sync_outbox_repository=outbox,
        )
        classroom_repo.create(Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER)
        student_repo.create(
            Student(id="s1", classroom_id="c1", first_name="A", last_name="B", created_at=_NOW, updated_at=_NOW),
            UserRole.TEACHER,
        )
        teacher_repo.create(
            Teacher(id="t1", full_name="T", pin_hash=hash_pin("111111"), created_at=_NOW, updated_at=_NOW),
            assigned_classroom_ids=("c1",),
        )
        progress_repo.link_session("sess1", "s1", "c1", "ohms-law")
        session_repo.save_session(
            ExperimentSession(
                id="sess1", experiment_id="ohms-law", started_at=_NOW, ended_at=_NOW,
                measurements=[Measurement(timestamp=_NOW, values={"v": 1.0}, experiment_id="ohms-law")],
            )
        )

        # "Рестарт" — ЖАҢА Python объектілерімен СОЛ файлды қайта ашу.
        reopened_outbox = SqliteSyncOutboxRepository(db_path)
        # classroom + student + teacher + teacher_classroom + session_student_link + session
        assert reopened_outbox.count_pending() == 6

        reopened_classroom = SqliteClassroomRepository(db_path, sync_outbox_repository=reopened_outbox)
        reopened_student = SqliteStudentRepository(db_path, sync_outbox_repository=reopened_outbox)
        reopened_teacher = SqliteTeacherRepository(db_path, sync_outbox_repository=reopened_outbox)
        reopened_session = SqliteSessionRepository(db_path, sync_outbox_repository=reopened_outbox)
        reopened_feedback = SqliteFeedbackRepository(db_path, sync_outbox_repository=reopened_outbox)
        reopened_progress = SqliteStudentProgressRepository(
            db_path, session_repository=reopened_session, feedback_repository=reopened_feedback,
            classroom_repository=reopened_classroom, student_repository=reopened_student,
            sync_outbox_repository=reopened_outbox,
        )
        api_client = HttpSyncApiClient(base_url="http://testserver", api_key=_TEST_API_KEY, client=shared_server)
        cursors: dict[str, datetime] = {}
        token_cache: dict[str, tuple] = {}
        engine = SyncEngine(
            reopened_classroom, reopened_student, reopened_teacher, reopened_outbox, api_client,
            get_pull_cursor=lambda entity_type: cursors.get(entity_type),
            set_pull_cursor=lambda entity_type, value: cursors.__setitem__(entity_type, value),
            get_active_role_and_sync_id=lambda: ("teacher", "t1"),
            get_cached_token=lambda: token_cache.get("token"),
            set_cached_token=lambda token, expires_at, r, s: token_cache.__setitem__("token", (token, expires_at, r, s)),
            session_repository=reopened_session,
            student_progress_repository=reopened_progress,
            feedback_repository=reopened_feedback,
        )

        result = engine.run_sync()

        assert result.status.value == "synced"
        assert reopened_outbox.count_pending() == 0
