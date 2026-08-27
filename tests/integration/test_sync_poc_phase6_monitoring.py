"""Phase 6 (Teacher Live Classroom Monitoring Dashboard) PRIMARY
ACCEPTANCE test — Student Client A + Teacher Client B, real FastAPI
server (``TestClient``), verifying the ``domain/services/teacher_
monitoring.py`` READ MODEL reflects reality across the FULL Phase 1-5
sync pipeline (not just raw measurement reconstruction, § Phase 4/5's
own acceptance tests already cover that layer).

Scenario (§27 of the Phase 6 brief):
    1. teacher opens classroom dashboard — student has no active experiment
    2. student starts experiment, pushes first batch
    3. teacher automatically sees ACTIVE state (next sync + snapshot)
    4. student generates multiple more batches
    5. teacher graph receives updates without manual Sync (re-sync + detail)
    6. student loses connectivity, keeps collecting locally
    7. teacher retains last known data, eventually shows STALE/OFFLINE
       (§ injected ``now`` — NO real wall-clock sleep, avoids flakiness)
    8. connectivity returns, student uploads pending batches
    9. teacher automatically receives them, graph reconstructs the gap
    10. student finalizes -> teacher sees COMPLETED, exact final match
    11. unauthorized Teacher C sees NONE of Student A's data
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from domain.entities.classroom import Classroom
from domain.entities.measurement import Measurement
from domain.entities.monitoring_activity_state import MonitoringActivityState
from domain.entities.student import Student
from domain.entities.teacher import Teacher
from domain.entities.user_role import UserRole
from domain.services.sync_engine import SyncEngine
from domain.services.teacher_monitoring import compute_classroom_monitoring, compute_student_monitoring_detail
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
            Teacher(id=sync_id, full_name=f"Teacher {sync_id}", pin_hash=hash_pin(f"pin-{sync_id}"),
                    created_at=_NOW, updated_at=_NOW, sync_id=sync_id)
        )
    else:
        student_repo.apply_remote_upsert(
            Student(id=sync_id, classroom_id=classroom_id, first_name="Student", last_name=sync_id,
                    created_at=_NOW, updated_at=_NOW, student_code=f"code-{sync_id}", sync_id=sync_id)
        )
    api_client = HttpSyncApiClient(base_url="http://testserver", api_key=_TEST_API_KEY, client=server)
    cursors: dict[str, datetime] = {}
    token_cache: dict[str, tuple] = {}
    engine = SyncEngine(
        classroom_repo, student_repo, teacher_repo, outbox, api_client,
        get_pull_cursor=lambda entity_type: cursors.get(entity_type),
        set_pull_cursor=lambda entity_type, value: cursors.__setitem__(entity_type, value),
        session_repository=session_repo, measurement_batch_repository=batch_repo,
        student_progress_repository=progress_repo,
        get_active_role_and_sync_id=lambda: (role, sync_id),
        get_cached_token=lambda: token_cache.get("token"),
        set_cached_token=lambda token, expires_at, r, s: token_cache.__setitem__("token", (token, expires_at, r, s)),
    )
    return {
        "engine": engine, "classroom": classroom_repo, "student": student_repo, "teacher": teacher_repo,
        "session": session_repo, "batch": batch_repo, "progress": progress_repo, "outbox": outbox,
        "api_client": api_client, "db_path": db_path,
    }


def _generate_measurements(count: int, offset: int = 0, base_time: datetime = _NOW) -> tuple[Measurement, ...]:
    return tuple(
        Measurement(
            timestamp=base_time - timedelta(seconds=(count - i)), values={"voltage": round(6.0 + (offset + i) * 0.01, 4)},
            experiment_id="ohms-law",
        )
        for i in range(count)
    )


@pytest.fixture()
def world(shared_server: TestClient, tmp_path: Path):
    teacher_a = _build_client(shared_server, "teacher", "ta", str(tmp_path / "teacher_a.db"))
    teacher_c = _build_client(shared_server, "teacher", "tc", str(tmp_path / "teacher_c.db"))
    student_a = _build_client(shared_server, "student", "sa", str(tmp_path / "student_a.db"), classroom_id="ca")

    teacher_a["classroom"].create(Classroom(id="ca", name="8A", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER)
    teacher_a["student"].create(
        Student(id="sa", classroom_id="ca", first_name="Student", last_name="A", created_at=_NOW, updated_at=_NOW, student_code="code-sa"),
        UserRole.TEACHER,
    )
    teacher_a["teacher"].set_assigned_classroom_ids("ta", ("ca",))
    teacher_a["engine"].run_sync()

    # § Teacher C — толығымен басқа сынып, "ca"-ға МҮЛДЕ тағайындалмаған.
    teacher_c["classroom"].create(Classroom(id="cc", name="Unrelated", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER)
    teacher_c["teacher"].set_assigned_classroom_ids("tc", ("cc",))
    teacher_c["engine"].run_sync()

    student_a["engine"].run_sync()

    return {"shared_server": shared_server, "teacher_a": teacher_a, "teacher_c": teacher_c, "student_a": student_a}


def test_full_classroom_monitoring_acceptance_scenario(world) -> None:
    teacher_a = world["teacher_a"]
    student_a = world["student_a"]

    # ---- 1. Teacher opens classroom dashboard — student has NOT started. ---
    snapshot = compute_classroom_monitoring(
        "ca", classroom_repository=teacher_a["classroom"], student_repository=teacher_a["student"],
        student_progress_repository=teacher_a["progress"], session_repository=teacher_a["session"], now=_NOW,
    )
    assert snapshot is not None
    assert snapshot.total_students == 1
    assert snapshot.students[0].activity_state is MonitoringActivityState.NOT_STARTED

    # ---- 2. Student starts experiment, pushes first batch. ------------------
    student_a["progress"].link_session("sess-a", "sa", "ca", "ohms-law")
    student_a["session"].append_measurements("sess-a", "ohms-law", _generate_measurements(10), started_at=_NOW - timedelta(seconds=10))
    student_a["batch"].create_pending_batches_for_session("sess-a", chunk_size=_CHUNK_SIZE, finalize=False)
    push_result = student_a["engine"].run_sync()
    assert push_result.status.value == "synced"

    # ---- 3. Teacher automatically sees ACTIVE state (next sync). -----------
    pull_result = teacher_a["engine"].run_sync()
    assert pull_result.status.value == "synced"
    snapshot = compute_classroom_monitoring(
        "ca", classroom_repository=teacher_a["classroom"], student_repository=teacher_a["student"],
        student_progress_repository=teacher_a["progress"], session_repository=teacher_a["session"], now=_NOW,
    )
    student_snapshot = snapshot.students[0]
    assert student_snapshot.activity_state is MonitoringActivityState.ACTIVE
    assert student_snapshot.measurement_count == 10

    # ---- 4-5. More batches; teacher graph updates without manual Sync. -----
    student_a["session"].append_measurements("sess-a", "ohms-law", _generate_measurements(10, offset=10), started_at=_NOW - timedelta(seconds=10))
    student_a["batch"].create_pending_batches_for_session("sess-a", chunk_size=_CHUNK_SIZE, finalize=False)
    student_a["engine"].run_sync()
    teacher_a["engine"].run_sync()  # § "teacher auto-refresh" симуляциясы
    detail = compute_student_monitoring_detail(
        "sa", "ohms-law", student_repository=teacher_a["student"], classroom_repository=teacher_a["classroom"],
        student_progress_repository=teacher_a["progress"], session_repository=teacher_a["session"], now=_NOW,
    )
    assert detail is not None
    assert len(detail.measurements) == 20
    original_after_batch_2 = student_a["session"].get_measurements("sess-a")
    assert [m.values["voltage"] for m in detail.measurements] == [m.values["voltage"] for m in original_after_batch_2]

    # ---- 6-7. Student loses connectivity; teacher shows STALE/OFFLINE later. -
    # § толық 10-дық chunk (§ ``finalize=False`` тек ТОЛЫҚ chunk-тарды
    # batch-қа бөледі — "құйрық" тек §10-дағы ``finalize=True``-де).
    student_a["api_client"].check_health = lambda: False
    student_a["session"].append_measurements("sess-a", "ohms-law", _generate_measurements(10, offset=20), started_at=_NOW - timedelta(seconds=10))
    student_a["batch"].create_pending_batches_for_session("sess-a", chunk_size=_CHUNK_SIZE, finalize=False)
    offline_result = student_a["engine"].run_sync()
    assert offline_result.status.value == "offline"

    # § teacher ЕШБІР жаңа sync-сіз ЕСКІ (20 өлшеу) деректі сақтайды.
    snapshot_offline = compute_classroom_monitoring(
        "ca", classroom_repository=teacher_a["classroom"], student_repository=teacher_a["student"],
        student_progress_repository=teacher_a["progress"], session_repository=teacher_a["session"], now=_NOW,
    )
    assert snapshot_offline.students[0].measurement_count == 20

    # § "eventually shows stale/awaiting-data" — НАҚТЫ ұйқы ЖОҚ, тек
    # инъекцияланған ``now`` соңғы measurement уақытынан алыс жылжытылады.
    much_later = _NOW + timedelta(minutes=5)
    snapshot_stale = compute_classroom_monitoring(
        "ca", classroom_repository=teacher_a["classroom"], student_repository=teacher_a["student"],
        student_progress_repository=teacher_a["progress"], session_repository=teacher_a["session"], now=much_later,
    )
    assert snapshot_stale.students[0].activity_state is MonitoringActivityState.OFFLINE
    assert snapshot_stale.needs_attention_count == 1

    # ---- 8-9. Connectivity returns; teacher automatically catches up. ------
    student_a["api_client"].check_health = lambda: True
    reconnect_result = student_a["engine"].run_sync()
    assert reconnect_result.status.value == "synced"
    teacher_a["engine"].run_sync()
    detail_after_reconnect = compute_student_monitoring_detail(
        "sa", "ohms-law", student_repository=teacher_a["student"], classroom_repository=teacher_a["classroom"],
        student_progress_repository=teacher_a["progress"], session_repository=teacher_a["session"], now=_NOW,
    )
    assert len(detail_after_reconnect.measurements) == 30
    original_full = student_a["session"].get_measurements("sess-a")
    assert [m.values["voltage"] for m in detail_after_reconnect.measurements] == [m.values["voltage"] for m in original_full]

    # ---- 10. Student finalizes (with a partial tail) -> teacher sees --------
    # COMPLETED, exact final match. § Production ``_finalize_and_persist_
    # session()`` calls ``save_session()`` (sets ``ended_at`` — THE
    # authoritative "session_is_running" signal, § ``classify_activity()``
    # докстрингі) БІРІНШІ, СОДАН КЕЙІН finalize=True batch жасайды.
    from domain.entities.experiment_session import ExperimentSession

    student_a["session"].append_measurements("sess-a", "ohms-law", _generate_measurements(3, offset=30), started_at=_NOW - timedelta(seconds=10))
    all_measurements = student_a["session"].get_measurements("sess-a")
    student_a["session"].save_session(
        ExperimentSession(
            id="sess-a", experiment_id="ohms-law", started_at=_NOW - timedelta(seconds=40), ended_at=_NOW,
            measurements=list(all_measurements),
        )
    )
    student_a["batch"].create_pending_batches_for_session("sess-a", chunk_size=_CHUNK_SIZE, finalize=True)
    student_a["engine"].run_sync()
    teacher_a["engine"].run_sync()
    final_snapshot = compute_classroom_monitoring(
        "ca", classroom_repository=teacher_a["classroom"], student_repository=teacher_a["student"],
        student_progress_repository=teacher_a["progress"], session_repository=teacher_a["session"], now=_NOW,
    )
    assert final_snapshot.students[0].activity_state is MonitoringActivityState.COMPLETED
    assert final_snapshot.completed_count == 1
    assert final_snapshot.active_count == 0

    final_detail = compute_student_monitoring_detail(
        "sa", "ohms-law", student_repository=teacher_a["student"], classroom_repository=teacher_a["classroom"],
        student_progress_repository=teacher_a["progress"], session_repository=teacher_a["session"], now=_NOW,
    )
    assert final_detail.activity_state is MonitoringActivityState.COMPLETED
    assert len(final_detail.measurements) == 33
    assert final_detail.measurement_count == 33

    # ---- 11. Unauthorized Teacher C sees NONE of Student A's data. ---------
    teacher_c = world["teacher_c"]
    teacher_c["engine"].run_sync()
    unauthorized_snapshot = compute_classroom_monitoring(
        "ca", classroom_repository=teacher_c["classroom"], student_repository=teacher_c["student"],
        student_progress_repository=teacher_c["progress"], session_repository=teacher_c["session"], now=_NOW,
    )
    assert unauthorized_snapshot is None  # § "ca" ешқашан teacher C-ге pull етілмеген
    assert teacher_c["session"].exists("sess-a") is False
