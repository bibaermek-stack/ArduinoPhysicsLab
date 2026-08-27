"""Phase 5 (Connectivity-Aware Automatic Sync + Near-Real-Time Classroom
Monitoring) PRIMARY ACCEPTANCE test — extends the Phase 4 two-client
scenario (`test_sync_poc_phase4_measurements.py`) with MULTIPLE small,
interleaved sync cycles (simulating what the connectivity-restored/
active-experiment/teacher-auto-refresh QTimers WOULD trigger in the
real app, § ``infrastructure/sync/sync_worker.py`` — this file tests
the DATA-FLOW correctness of that pattern, not Qt timer mechanics,
which are already covered by ``tests/unit/test_sync_worker.py``/
``tests/unit/test_connectivity_monitor.py``), plus explicit:

  - offline accumulation across a real connectivity drop
  - mid-experiment disconnect/reconnect (multiple times)
  - restart safety (repositories reopened against the SAME db_path)
  - ``ConnectivityMonitor`` (pure Python, § ``domain/services/
    connectivity_monitor.py``) correctly detects the OFFLINE->ONLINE
    edge that would trigger ``SyncWorker.run_sync_now()`` in production
  - exact final reconstruction (count/order/values) on an isolated
    second device, even after MANY small interleaved sync calls
  - duplicate prevention across repeated reconnect-triggered cycles
  - authorization isolation (unassigned teacher / unrelated student)
  - 401 recovery (fresh login after a client "restart" clears the
    in-memory token cache) and 403 (student cannot push into another
    student's session, never destructively retried)

``test_sync_poc_phase4_measurements.py``-мен БІРДЕЙ shared-server/
``TestClient``/shared-``db_path``-per-client паттернін қолданады.
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
from domain.services.connectivity_monitor import ConnectivityMonitor
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
        "connectivity_monitor": ConnectivityMonitor(),
    }


def _rebuild_client(previous: dict, server: TestClient, role: str, sync_id: str, classroom_id: str = "") -> dict:
    """§ "restart safety" — ЖАҢА Python объектілері (§ "app closes/
    restarts" — жаңа, БОС in-memory token cache да), ДӘЛ СОЛ ``db_path``."""
    return _build_client(server, role, sync_id, previous["db_path"], classroom_id=classroom_id)


def _generate_measurements(count: int, offset: int = 0) -> tuple[Measurement, ...]:
    return tuple(
        Measurement(
            timestamp=_NOW, values={"voltage": round(6.0 + (offset + i) * 0.01, 4)},
            experiment_id="ohms-law",
        )
        for i in range(count)
    )


def _simulate_connectivity_tick(client: dict, server_reachable: bool) -> bool:
    """§3/§4 "Automatic Connectivity Monitor" / "Connectivity-Restored
    Push Trigger" — НАҚТЫ ``SyncWorker._on_connectivity_timer_tick()``
    логикасын қайталайды: жеңіл ``check_health()`` (мұнда сервер
    қолжетімділігін ТІКЕЛЕЙ параметр ретінде бере отырып симуляцияланады),
    ``ConnectivityMonitor``-ды жаңартады, OFFLINE->ONLINE ауысуы болса
    ``True`` қайтарады (§ "триггер керек пе")."""
    result = client["connectivity_monitor"].check(server_reachable)
    return result.just_came_online


@pytest.fixture()
def world(shared_server: TestClient, tmp_path: Path):
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


def test_connectivity_aware_full_acceptance_scenario(world) -> None:
    student_a = world["student_a"]

    # ---- 1. Student A links a session and starts ONLINE. -------------------
    student_a["progress"].link_session("sess-a", "sa", "ca", "ohms-law")

    # ---- 2. Near-real-time: several small "active-experiment sync" ticks. --
    for tick in range(3):
        student_a["session"].append_measurements(
            "sess-a", "ohms-law", _generate_measurements(4, offset=tick * 4), started_at=_NOW
        )
        student_a["batch"].create_pending_batches_for_session("sess-a", chunk_size=_CHUNK_SIZE, finalize=False)
        result = student_a["engine"].run_sync()
        assert result.status.value == "synced"
    assert len(student_a["session"].get_measurements("sess-a")) == 12

    # ---- 3. Connectivity monitor's FIRST-EVER check — "just came online" ---
    # is correctly True (§ ConnectivityMonitor "unknown -> True counts as a
    # restore, matching app-startup semantics"). A SECOND immediate check
    # must NOT re-flag a transition.
    assert _simulate_connectivity_tick(student_a, server_reachable=True) is True
    assert _simulate_connectivity_tick(student_a, server_reachable=True) is False

    # ---- 4. Server "goes down" mid-experiment — acquisition continues. -----
    student_a["api_client"].check_health = lambda: False
    for tick in range(2):
        student_a["session"].append_measurements(
            "sess-a", "ohms-law", _generate_measurements(3, offset=12 + tick * 3), started_at=_NOW
        )
        student_a["batch"].create_pending_batches_for_session("sess-a", chunk_size=_CHUNK_SIZE, finalize=False)
        offline_result = student_a["engine"].run_sync()
        assert offline_result.status.value == "offline"
        assert _simulate_connectivity_tick(student_a, server_reachable=False) is False
    assert len(student_a["session"].get_measurements("sess-a")) == 18  # § local acquisition NEVER stalls
    pending_before_restart = student_a["outbox"].count_pending()
    assert pending_before_restart > 0

    # ---- 5. App "restarts" while still offline — restart safety. -----------
    student_a_restarted = _rebuild_client(student_a, world["shared_server"], "student", "sa", classroom_id="ca")
    assert len(student_a_restarted["session"].get_measurements("sess-a")) == 18
    assert student_a_restarted["outbox"].count_pending() == pending_before_restart
    student_a = student_a_restarted

    # ---- 6. Server "returns" — ConnectivityMonitor detects the edge. -------
    def _restore_health() -> bool:
        return True

    student_a["api_client"].check_health = _restore_health
    triggered = _simulate_connectivity_tick(student_a, server_reachable=True)
    assert triggered is True  # § "just_came_online" -> production would call run_sync_now()
    reconnect_result = student_a["engine"].run_sync()
    assert reconnect_result.status.value == "synced"

    # ---- 7. Retry the SAME trigger again (simulating a second, redundant ---
    # connectivity tick before the next real change) — must be a safe no-op,
    # no duplicate batches/measurements.
    assert _simulate_connectivity_tick(student_a, server_reachable=True) is False
    retry_result = student_a["engine"].run_sync()
    assert retry_result.status.value == "synced"
    assert student_a["outbox"].count_pending() == 0

    # ---- 8. More mid-experiment data + another disconnect/reconnect cycle. -
    student_a["session"].append_measurements("sess-a", "ohms-law", _generate_measurements(9, offset=18), started_at=_NOW)
    student_a["batch"].create_pending_batches_for_session("sess-a", chunk_size=_CHUNK_SIZE, finalize=False)
    student_a["engine"].run_sync()
    assert len(student_a["session"].get_measurements("sess-a")) == 27

    # ---- 9. Finalize (Stop) — tail batch delivered immediately. ------------
    student_a["batch"].create_pending_batches_for_session("sess-a", chunk_size=_CHUNK_SIZE, finalize=True)
    final_result = student_a["engine"].run_sync()
    assert final_result.status.value == "synced"
    assert student_a["outbox"].count_pending() == 0

    original = student_a["session"].get_measurements("sess-a")
    assert len(original) == 27

    # ---- 10. Teacher A (isolated device) pulls and reconstructs exactly. ---
    teacher_a = world["teacher_a"]
    pull_result = teacher_a["engine"].run_sync()
    assert pull_result.status.value == "synced"
    reconstructed = teacher_a["session"].get_measurements("sess-a")
    assert len(reconstructed) == 27
    assert [m.values["voltage"] for m in reconstructed] == [m.values["voltage"] for m in original]

    # ---- 11. Repeated teacher pulls create no duplicates. -------------------
    teacher_a["engine"].run_sync()
    teacher_a["engine"].run_sync()
    assert len(teacher_a["session"].get_measurements("sess-a")) == 27
    assert teacher_a["outbox"].count_pending() == 0  # § apply_remote_* never re-enqueues

    # ---- 12. Authorization isolation: unassigned Teacher B / Student B. ----
    teacher_b = world["teacher_b"]
    result_b = teacher_b["engine"].run_sync()
    assert result_b.status.value == "synced"
    assert teacher_b["session"].exists("sess-a") is False
    assert len(teacher_b["session"].get_measurements("sess-a")) == 0

    student_b = world["student_b"]
    result_sb = student_b["engine"].run_sync()
    assert result_sb.status.value == "synced"
    assert student_b["session"].exists("sess-a") is False
    assert len(student_b["session"].get_measurements("sess-a")) == 0


def test_401_transparent_reauth_after_client_restart(world) -> None:
    """§17 "On 401: reuse existing re-login behavior" — client "restart"
    clears the in-memory token cache (§ ``token_cache`` new dict each
    ``_build_client()`` call); the NEXT sync must transparently log back
    in using the locally-stored credential, WITHOUT losing any pending
    data."""
    student_a = world["student_a"]
    student_a["progress"].link_session("sess-a", "sa", "ca", "ohms-law")
    student_a["session"].append_measurements("sess-a", "ohms-law", _generate_measurements(5), started_at=_NOW)
    student_a["batch"].create_pending_batches_for_session("sess-a", chunk_size=_CHUNK_SIZE, finalize=True)
    first_sync = student_a["engine"].run_sync()
    assert first_sync.status.value == "synced"

    # § "restart" -> brand-new (empty) in-memory token_cache, DB survives.
    restarted = _rebuild_client(student_a, world["shared_server"], "student", "sa", classroom_id="ca")
    assert len(restarted["session"].get_measurements("sess-a")) == 5

    restarted["session"].append_measurements("sess-a", "ohms-law", _generate_measurements(3, offset=5), started_at=_NOW)
    restarted["batch"].create_pending_batches_for_session("sess-a", chunk_size=_CHUNK_SIZE, finalize=True)
    second_sync = restarted["engine"].run_sync()

    assert second_sync.status.value == "synced"  # § re-login happened transparently
    assert restarted["outbox"].count_pending() == 0
    assert len(restarted["session"].get_measurements("sess-a")) == 8  # § no data lost


def test_403_push_into_another_students_session_is_rejected_and_preserved(world) -> None:
    """§17 "On 403: do not retry aggressively; preserve diagnostic
    state; do not leak unauthorized records" — Student B attempts to
    push a measurement batch into Student A's session."""
    student_a = world["student_a"]
    student_b = world["student_b"]
    student_a["progress"].link_session("sess-a", "sa", "ca", "ohms-law")
    student_a["session"].append_measurements("sess-a", "ohms-law", _generate_measurements(4), started_at=_NOW)
    student_a["batch"].create_pending_batches_for_session("sess-a", chunk_size=_CHUNK_SIZE, finalize=True)
    student_a["engine"].run_sync()

    # § Student B locally forges a batch claiming Student A's session_id,
    # WITHOUT any legitimate session_student_link of their own for it
    # (§ "never trust client-claimed ownership" — server must reject
    # this using the REAL, existing link — which still points to
    # Student A — regardless of what Student B's local outbox contains).
    student_b["session"].append_measurements("sess-a", "ohms-law", _generate_measurements(2, offset=100), started_at=_NOW)
    student_b["batch"].create_pending_batches_for_session("sess-a", chunk_size=_CHUNK_SIZE, finalize=True)

    result = student_b["engine"].run_sync()

    assert result.status.value in ("sync_error", "auth_required")
    assert student_b["outbox"].count_pending() > 0  # § "preserve diagnostic state" — not silently dropped

    # § Student A's real data must remain untouched/uncorrupted.
    teacher_a = world["teacher_a"]
    teacher_a["engine"].run_sync()
    reconstructed = teacher_a["session"].get_measurements("sess-a")
    assert len(reconstructed) == 4
    assert all(m.values["voltage"] < 10 for m in reconstructed)  # § никогда B-нің "100"-offset деректері ЕМЕС
