"""Phase 9 (Production Deployment, Multi-PC Release Readiness &
Configuration) PRIMARY ACCEPTANCE test — Teacher installation A + Student
installation B, each with its own fully isolated SQLite database (as a
real separate PC would have), talking only through a shared FastAPI test
server. This is the automated stand-in for "two separate Windows PCs"
required by the Phase 9 brief's Part M — we cannot spin up real hardware
in CI, so isolation is simulated via separate temp-file SQLite databases
and a single shared in-memory server, reusing the exact `_build_client`
pattern already established by `test_sync_poc_phase7_teacher_notes.py`.

20-step scenario (§ Phase 9 brief Part M):
    1-4.   Central test server started; Student B and Teacher A each get
           their own isolated on-disk SQLite database, both configured
           against the same server.
    5-6.   Student and Teacher "log in" (bootstrap identity via
           apply_remote_upsert, matching the established client factory).
    7-8.   Student performs an experiment; measurements persist locally.
    9-10.  Student syncs; Teacher syncs and receives the data through the
           server (never a shared database).
    11.    Teacher classroom monitoring (Phase 6) AND per-student learning
           analytics (Phase 8) both see the authorized data.
    12.    Teacher sends feedback (a TeacherNote, Phase 7); it flows to
           the student on the student's next sync.
    13-14. Server "goes down" (no further sync calls made); Student
           continues working completely offline — new measurements are
           appended locally.
    15-16. Both client-side repository sets are rebuilt from the SAME
           on-disk database files (simulating an app restart / process
           relaunch) — all local data, including the offline-collected
           measurements, is confirmed to have survived intact.
    17-19. Server "comes back" (the shared TestClient is usable again);
           both clients run another sync cycle — the offline work
           catches up automatically, and repeated cycles produce no
           duplicate rows.
    20.    An unrelated/unauthorized teacher (Teacher C, assigned to a
           different classroom) sees none of Student B's data, even
           after running its own sync cycle — data crossed the server's
           authorization boundary, never a shared database.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from domain.entities.classroom import Classroom
from domain.entities.experiment_session import ExperimentSession
from domain.entities.measurement import Measurement
from domain.entities.monitoring_activity_state import MonitoringActivityState
from domain.entities.student import Student
from domain.entities.teacher import Teacher
from domain.entities.teacher_note import TeacherNote
from domain.entities.user_role import UserRole
from domain.services.learning_analytics import compute_students_learning_progress
from domain.services.sync_engine import SyncEngine
from domain.services.teacher_monitoring import compute_classroom_monitoring
from domain.services.teacher_pin import hash_pin
from infrastructure.storage.sqlite_classroom_repository import SqliteClassroomRepository
from infrastructure.storage.sqlite_measurement_batch_repository import SqliteMeasurementBatchRepository
from infrastructure.storage.sqlite_session_repository import SqliteSessionRepository
from infrastructure.storage.sqlite_student_progress_repository import SqliteStudentProgressRepository
from infrastructure.storage.sqlite_student_repository import SqliteStudentRepository
from infrastructure.storage.sqlite_sync_outbox_repository import SqliteSyncOutboxRepository
from infrastructure.storage.sqlite_teacher_note_repository import SqliteTeacherNoteRepository
from infrastructure.storage.sqlite_teacher_repository import SqliteTeacherRepository
from infrastructure.sync.http_sync_api_client import HttpSyncApiClient
from modules.module_registry import ModuleRegistry
from server.app.db.session import Base, get_db
from server.app.main import app as fastapi_app

_TEST_API_KEY = "dev-local-only-key"
_NOW = datetime.now(timezone.utc)
_CHUNK_SIZE = 10


@pytest.fixture()
def shared_server() -> TestClient:
    """§ "Start a central test server" — the one thing every isolated
    installation talks to; never a shared SQLite file between clients."""
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


def _build_installation(server: TestClient, role: str, sync_id: str, db_path: str, classroom_id: str = ""):
    """§ "Configure both to same server" — one isolated on-disk SQLite
    database (a stand-in for one PC's local install), built fresh each
    time this is called. Calling it AGAIN with the SAME ``db_path``
    simulates restarting the app: it reopens the persisted file, never
    creates a second identity or a second database."""
    outbox = SqliteSyncOutboxRepository(db_path)
    classroom_repo = SqliteClassroomRepository(db_path, sync_outbox_repository=outbox)
    student_repo = SqliteStudentRepository(db_path, sync_outbox_repository=outbox)
    teacher_repo = SqliteTeacherRepository(db_path, sync_outbox_repository=outbox)
    session_repo = SqliteSessionRepository(db_path, sync_outbox_repository=outbox)
    batch_repo = SqliteMeasurementBatchRepository(db_path, sync_outbox_repository=outbox)
    note_repo = SqliteTeacherNoteRepository(db_path, sync_outbox_repository=outbox)
    progress_repo = SqliteStudentProgressRepository(
        db_path, session_repository=session_repo,
        classroom_repository=classroom_repo, student_repository=student_repo,
        sync_outbox_repository=outbox,
    )
    # § 5-6. "Student/Teacher logs in" — idempotent upsert, safe to repeat
    # across a simulated restart (same identity, not a duplicate).
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
        student_progress_repository=progress_repo, teacher_note_repository=note_repo,
        get_active_role_and_sync_id=lambda: (role, sync_id),
        get_cached_token=lambda: token_cache.get("token"),
        set_cached_token=lambda token, expires_at, r, s: token_cache.__setitem__("token", (token, expires_at, r, s)),
    )
    return {
        "engine": engine, "classroom": classroom_repo, "student": student_repo, "teacher": teacher_repo,
        "session": session_repo, "batch": batch_repo, "progress": progress_repo, "note": note_repo,
        "outbox": outbox, "db_path": db_path,
    }


def _generate_measurements(count: int, offset: int = 0, base_time: datetime = _NOW) -> tuple[Measurement, ...]:
    return tuple(
        Measurement(
            timestamp=base_time - timedelta(seconds=(count - i)), values={"voltage": round(6.0 + (offset + i) * 0.01, 4)},
            experiment_id="ohms-law",
        )
        for i in range(count)
    )


def test_multi_pc_isolation_offline_reconnect_and_authorization(
    shared_server: TestClient, tmp_path: Path
) -> None:
    # ---- 1-4. Isolated Student B and Teacher A installations, same server. -
    # § each path lives in its own directory — a real per-PC install
    # (§ ``get_default_database_path()``) always creates its data
    # directory before connecting; this test does the same explicitly.
    (tmp_path / "teacher_pc").mkdir()
    (tmp_path / "student_pc").mkdir()
    (tmp_path / "unrelated_teacher_pc").mkdir()
    teacher_a_db = str(tmp_path / "teacher_pc" / "arduino_physics_lab.db")
    student_b_db = str(tmp_path / "student_pc" / "arduino_physics_lab.db")
    teacher_c_db = str(tmp_path / "unrelated_teacher_pc" / "arduino_physics_lab.db")
    # § separate physical files — NEVER the same db_path — is the actual
    # "crosses through the server, not through a shared DB" guarantee.
    assert teacher_a_db != student_b_db != teacher_c_db

    teacher_a = _build_installation(shared_server, "teacher", "ta", teacher_a_db)
    student_b = _build_installation(shared_server, "student", "sb", student_b_db, classroom_id="c1")
    teacher_c = _build_installation(shared_server, "teacher", "tc", teacher_c_db)

    teacher_a["classroom"].create(Classroom(id="c1", name="9B", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER)
    teacher_a["student"].create(
        Student(id="sb", classroom_id="c1", first_name="Student", last_name="B", created_at=_NOW, updated_at=_NOW, student_code="code-sb"),
        UserRole.TEACHER,
    )
    teacher_a["teacher"].set_assigned_classroom_ids("ta", ("c1",))
    teacher_a["engine"].run_sync()

    teacher_c["classroom"].create(Classroom(id="c2", name="Unrelated", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER)
    teacher_c["teacher"].set_assigned_classroom_ids("tc", ("c2",))
    teacher_c["engine"].run_sync()

    student_b["engine"].run_sync()

    # ---- 7-8. Student performs an experiment; data persists locally. -------
    student_b["progress"].link_session("sess-b", "sb", "c1", "ohms-law")
    student_b["session"].append_measurements(
        "sess-b", "ohms-law", _generate_measurements(10), started_at=_NOW - timedelta(seconds=10)
    )
    student_b["batch"].create_pending_batches_for_session("sess-b", chunk_size=_CHUNK_SIZE, finalize=False)
    assert len(student_b["session"].get_measurements("sess-b")) == 10  # § local-first, no sync required yet

    # ---- 9-10. Student syncs; Teacher syncs and receives it via the server. -
    assert student_b["engine"].run_sync().status.value == "synced"
    assert teacher_a["engine"].run_sync().status.value == "synced"

    # ---- 11. Teacher monitoring (Phase 6) AND analytics (Phase 8) see it. --
    monitoring_snapshot = compute_classroom_monitoring(
        "c1", classroom_repository=teacher_a["classroom"], student_repository=teacher_a["student"],
        student_progress_repository=teacher_a["progress"], session_repository=teacher_a["session"], now=_NOW,
    )
    student_snapshot = next(s for s in monitoring_snapshot.students if s.student_id == "sb")
    assert student_snapshot.activity_state is MonitoringActivityState.ACTIVE

    progress_list = teacher_a["progress"].list_all_progress(frozenset({"c1"}))
    learning_rows = compute_students_learning_progress(
        progress_list, student_repository=teacher_a["student"], classroom_repository=teacher_a["classroom"],
        module_registry=ModuleRegistry(),
    )
    assert any(row.student_id == "sb" for row in learning_rows)

    # ---- 12. Teacher sends feedback (Phase 7); flows on next student sync. -
    teacher_a["note"].create(
        TeacherNote(
            id="note-1", teacher_id="ta", student_id="sb", classroom_id="c1",
            message="Тамаша жұмыс, жалғастыр!", created_at=_NOW, experiment_id="ohms-law", session_id="sess-b",
        ),
        UserRole.TEACHER,
    )
    assert teacher_a["engine"].run_sync().status.value == "synced"
    assert student_b["engine"].run_sync().status.value == "synced"
    assert len(student_b["note"].list_for_student("sb")) == 1

    # ---- 13-14. Server "down" — student keeps working fully offline. -------
    # (no run_sync() calls below until step 17 — this IS the offline gap)
    student_b["session"].append_measurements(
        "sess-b", "ohms-law", _generate_measurements(10, offset=10), started_at=_NOW - timedelta(seconds=10)
    )
    student_b["batch"].create_pending_batches_for_session("sess-b", chunk_size=_CHUNK_SIZE, finalize=False)
    offline_measurement_count = len(student_b["session"].get_measurements("sess-b"))
    assert offline_measurement_count == 20  # § offline collection still works, no crash, no blocking network call

    # ---- 15-16. Simulate an app restart — rebuild repos from the SAME file.-
    student_b_restarted = _build_installation(shared_server, "student", "sb", student_b_db, classroom_id="c1")
    teacher_a_restarted = _build_installation(shared_server, "teacher", "ta", teacher_a_db)
    # § "existing developer databases must not be silently destroyed" —
    # everything collected while offline is still there after "restart".
    assert len(student_b_restarted["session"].get_measurements("sess-b")) == 20
    assert len(student_b_restarted["note"].list_for_student("sb")) == 1
    assert teacher_a_restarted["teacher"].list_assigned_classroom_ids("ta") == ("c1",)

    # ---- 17-19. Server "back up" — resync, no duplicates. -------------------
    assert student_b_restarted["engine"].run_sync().status.value == "synced"
    assert teacher_a_restarted["engine"].run_sync().status.value == "synced"
    # Repeat once more (§ "no duplicates" on a second, redundant cycle).
    student_b_restarted["engine"].run_sync()
    teacher_a_restarted["engine"].run_sync()

    final_measurements = teacher_a_restarted["session"].get_measurements("sess-b")
    assert len(final_measurements) == 20  # § no duplicate rows from the catch-up sync
    assert len(student_b_restarted["note"].list_for_student("sb")) == 1  # § note still exactly one

    # ---- 20. Unrelated/unauthorized Teacher C sees nothing. -----------------
    teacher_c["engine"].run_sync()
    assert teacher_c["session"].get_session("sess-b") is None
    assert teacher_c["session"].get_measurements("sess-b") == ()
    unauthorized_snapshot = compute_classroom_monitoring(
        "c1", classroom_repository=teacher_c["classroom"], student_repository=teacher_c["student"],
        student_progress_repository=teacher_c["progress"], session_repository=teacher_c["session"], now=_NOW,
    )
    assert unauthorized_snapshot is None
