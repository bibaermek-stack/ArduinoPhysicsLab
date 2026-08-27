"""Phase 4 (Raw Arduino Measurement Cloud Sync) PRIMARY ACCEPTANCE POC —
24-step two-client scenario:

    Student A (device 1) generates realistic multi-chunk Arduino data,
    partially syncs while "running", goes offline, keeps collecting,
    restarts (repository re-opened against the SAME db_path — restart
    safety), server returns, remaining batches sync. Teacher A (device 2,
    fully isolated local DB, assigned to Student A's classroom) pulls and
    reconstructs the RAW measurements locally — exact count/order/values,
    no duplicates. Unassigned Teacher B and unrelated Student B then both
    receive NOTHING for this session (authorization).

``test_sync_poc_phase3_multi_client.py``-мен БІРДЕЙ shared-server/
``TestClient`` паттернін қолданады, БІРАҚ бір ЖАҢА түзету қажет: Phase 4-те
``session_repo``/``batch_repo`` бір-бірінің ``measurements``/``measurement_
batches`` кестелерін КӨРУІ керек (§ ``create_pending_batches_for_session()``
екеуін де оқиды), сондықтан ЕКЕУІ де БІРДЕЙ, НАҚТЫ ``db_path``-пен
құрылады — Phase 1-3-тегі бос ``:memory:`` әдепкісі (әр repo ӨЗ БӨЛЕК
дерекқорымен) бұл жерде ЖЕТКІЛІКСІЗ (§ осы фазада табылған "device2
reconstructed count: 0" қатесінің НАҚТЫ түбір себебі).
"""

from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from domain.entities.classroom import Classroom
from domain.entities.measurement import Measurement
from domain.entities.student import Student
from domain.entities.teacher import Teacher
from domain.entities.user_role import UserRole
from domain.services.sync_engine import SyncEngine
from domain.services.teacher_pin import hash_pin
from infrastructure.storage.sqlite_classroom_repository import SqliteClassroomRepository
from infrastructure.storage.sqlite_measurement_batch_repository import SqliteMeasurementBatchRepository
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
_CHUNK_SIZE = 10


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


def _build_client(server: TestClient, role: str, sync_id: str, db_path: str, classroom_id: str = ""):
    """§ Phase 4 түзетуі: ``outbox``/``session_repo``/``batch_repo``
    БАРЛЫҒЫ ДӘЛ СОЛ ``db_path``-пен (§ ортақ физикалық файл — модуль
    докстрингіндегі түбір себеп түсіндірмесі)."""
    outbox = SqliteSyncOutboxRepository(db_path)
    classroom_repo = SqliteClassroomRepository(db_path, sync_outbox_repository=outbox)
    student_repo = SqliteStudentRepository(db_path, sync_outbox_repository=outbox)
    teacher_repo = SqliteTeacherRepository(db_path, sync_outbox_repository=outbox)
    session_repo = SqliteSessionRepository(db_path, sync_outbox_repository=outbox)
    batch_repo = SqliteMeasurementBatchRepository(db_path, sync_outbox_repository=outbox)
    progress_repo = SqliteStudentProgressRepository(
        db_path, session_repository=session_repo,
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
                id=sync_id, classroom_id=classroom_id, first_name="Student", last_name=sync_id,
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
        measurement_batch_repository=batch_repo,
        student_progress_repository=progress_repo,
        get_active_role_and_sync_id=lambda: (role, sync_id),
        get_cached_token=lambda: token_cache.get("token"),
        set_cached_token=lambda token, expires_at, r, s: token_cache.__setitem__("token", (token, expires_at, r, s)),
    )
    return {
        "engine": engine, "classroom": classroom_repo, "student": student_repo, "teacher": teacher_repo,
        "session": session_repo, "batch": batch_repo, "progress": progress_repo,
        "outbox": outbox, "api_client": api_client, "db_path": db_path,
    }


def _rebuild_client(previous: dict, server: TestClient, role: str, sync_id: str, classroom_id: str = "") -> dict:
    """§ "restart safety": ЖАҢА Python объектілері, ДӘЛ СОЛ ``db_path``
    (§ "app closes/restarts" — pending batch/outbox күйі RAM-да ЕМЕС)."""
    return _build_client(server, role, sync_id, previous["db_path"], classroom_id=classroom_id)


def _link_and_generate_measurements(client: dict, session_id: str, student_id: str, classroom_id: str, count: int) -> None:
    """§ "do not wait until an experiment ends before synchronization
    can begin": incremental ``append_measurements()`` (§ ExperimentWorkspacePage
    incremental-persist tick) — тікелей ``save_session()`` ЕМЕС."""
    measurements = tuple(
        Measurement(
            timestamp=_NOW, values={"voltage": round(6.0 + i * 0.01, 4), "current": round(0.0078 + i * 0.0001, 6)},
            derived_values={"power": round((6.0 + i * 0.01) * (0.0078 + i * 0.0001), 6)},
            experiment_id="ohms-law",
        )
        for i in range(count)
    )
    client["session"].append_measurements(session_id, "ohms-law", measurements, started_at=_NOW)


@pytest.fixture()
def world(shared_server: TestClient, tmp_path: Path):
    """Teacher A -> 8A -> Student A (assigned). Teacher B (unassigned).
    Student B (unrelated, own classroom)."""
    teacher_a = _build_client(shared_server, "teacher", "ta", str(tmp_path / "teacher_a.db"))
    teacher_b = _build_client(shared_server, "teacher", "tb", str(tmp_path / "teacher_b.db"))
    student_a = _build_client(shared_server, "student", "sa", str(tmp_path / "student_a.db"), classroom_id="ca")
    student_b = _build_client(shared_server, "student", "sb", str(tmp_path / "student_b.db"), classroom_id="cb")

    teacher_a["classroom"].create(Classroom(id="ca", name="8A", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER)
    teacher_a["student"].create(
        Student(id="sa", classroom_id="ca", first_name="Student", last_name="A", created_at=_NOW, updated_at=_NOW, student_code="code-sa"),
        UserRole.TEACHER,
    )
    teacher_a["teacher"].set_assigned_classroom_ids("ta", ("ca",))
    teacher_a["engine"].run_sync()

    teacher_b["classroom"].create(Classroom(id="cb", name="8B", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER)
    # § student_b-ды НАҚТЫ жазбамен алдын ала provisioning (§ student_a-мен
    # БІРДЕЙ конвенция) — әйтпесе оның бірінші логині TOFU bootstrap-ты
    # (§ ``auth_service.py::authenticate_student()``) іске қосар еді, ол
    # ``classroom_sync_id``/``last_name``-ды бос қалдырады (§ login body-де
    # тек ``sync_id``/``student_code`` бар), кейін ӨЗ жазбасын pull еткенде
    # ``StudentOut`` pydantic валидациясы (``min_length=1``) сәтсіз аяқталады
    # — бұл Phase 3-тің ЖЕКЕ, осы тестке ЕШБІР қатысы жоқ мәселесі, сондықтан
    # Phase 4 authorization сценарийін ШАТАСТЫРМАУ үшін алдын ала болдырмаймыз.
    teacher_b["student"].create(
        Student(id="sb", classroom_id="cb", first_name="Student", last_name="B", created_at=_NOW, updated_at=_NOW, student_code="code-sb"),
        UserRole.TEACHER,
    )
    teacher_b["teacher"].set_assigned_classroom_ids("tb", ("cb",))
    teacher_b["engine"].run_sync()

    student_a["engine"].run_sync()
    student_b["engine"].run_sync()

    return {
        "shared_server": shared_server, "tmp_path": tmp_path,
        "teacher_a": teacher_a, "teacher_b": teacher_b, "student_a": student_a, "student_b": student_b,
    }


def test_full_two_client_measurement_sync_and_reconstruction(world) -> None:
    student_a = world["student_a"]

    # 1-4. Session-student link + realistic multi-chunk data (25 -> 2 full batches @10 + tail 5).
    student_a["progress"].link_session("sess-a", "sa", "ca", "ohms-law")
    _link_and_generate_measurements(student_a, "sess-a", "sa", "ca", count=25)
    created = student_a["batch"].create_pending_batches_for_session("sess-a", chunk_size=_CHUNK_SIZE, finalize=False)
    assert created == 2  # § "partial session upload while still running" — tail (5) стays unbatched

    # 5. Sync while "running" — session + link + 2 full batches push (tail NOT yet a batch).
    result_partial = student_a["engine"].run_sync()
    assert result_partial.status.value == "synced"
    assert student_a["batch"].list_pending_batch_ids_for_session("sess-a").__len__() == 2

    # 6-7. Server "goes down" — MORE data collected offline, local repo stays functional.
    monkeypatch_health = student_a["api_client"].check_health
    student_a["api_client"].check_health = lambda: False
    _link_and_generate_measurements(student_a, "sess-a", "sa", "ca", count=8)  # § total now 33
    assert len(student_a["session"].get_measurements("sess-a")) == 33  # § UI/graph data path stays live
    offline_result = student_a["engine"].run_sync()
    assert offline_result.status.value == "offline"

    # 8-9. App "closes and restarts" — rebuild repos against the SAME db_path.
    student_a_restarted = _rebuild_client(student_a, world["shared_server"], "student", "sa", classroom_id="ca")
    assert len(student_a_restarted["session"].get_measurements("sess-a")) == 33  # § restart safety
    # § experiment "resumes" after restart and finalizes the tail (33 - 20 covered = 13 remaining).
    created_after_restart = student_a_restarted["batch"].create_pending_batches_for_session(
        "sess-a", chunk_size=_CHUNK_SIZE, finalize=True
    )
    assert created_after_restart == 2  # § 1 full (10) + 1 tail (3)
    student_a_restarted["api_client"].check_health = monkeypatch_health  # § "server returns"

    # 10. Sync resumes, remaining batches upload; retry-safe (idempotent) second call.
    final_sync = student_a_restarted["engine"].run_sync()
    assert final_sync.status.value == "synced"
    assert student_a_restarted["outbox"].count_pending() == 0
    retry_sync = student_a_restarted["engine"].run_sync()
    assert retry_sync.status.value == "synced"

    # 11-16. Teacher A (assigned, ISOLATED local DB) pulls and reconstructs raw measurements.
    teacher_a = world["teacher_a"]
    pull_result = teacher_a["engine"].run_sync()
    assert pull_result.status.value == "synced"
    assert teacher_a["session"].exists("sess-a")
    reconstructed = teacher_a["session"].get_measurements("sess-a")
    original = student_a_restarted["session"].get_measurements("sess-a")
    assert len(reconstructed) == 33 == len(original)
    assert [m.values["voltage"] for m in reconstructed] == [m.values["voltage"] for m in original]
    assert [m.values["current"] for m in reconstructed] == [m.values["current"] for m in original]
    assert [m.derived_values["power"] for m in reconstructed] == [m.derived_values["power"] for m in original]

    # 17. No duplicates on a second teacher pull.
    teacher_a["engine"].run_sync()
    assert len(teacher_a["session"].get_measurements("sess-a")) == 33

    # 18. Pulled batches never re-enqueue (§ established "apply_remote_* never re-enqueues").
    assert teacher_a["outbox"].count_pending() == 0

    # 19-21. Unassigned Teacher B receives nothing for this session.
    teacher_b = world["teacher_b"]
    result_b = teacher_b["engine"].run_sync()
    assert result_b.status.value == "synced"
    assert teacher_b["session"].exists("sess-a") is False
    assert len(teacher_b["session"].get_measurements("sess-a")) == 0

    # 22-24. Unrelated Student B receives nothing for Student A's session.
    student_b = world["student_b"]
    result_sb = student_b["engine"].run_sync()
    assert result_sb.status.value == "synced"
    assert student_b["session"].exists("sess-a") is False
    assert len(student_b["session"].get_measurements("sess-a")) == 0
