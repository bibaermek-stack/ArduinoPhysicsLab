"""Phase 7 (Teacher Actions, Feedback Delivery, and Session History)
PRIMARY ACCEPTANCE test — Teacher A + Student A (+ unauthorized Teacher
C + unrelated Student B), real FastAPI server (``TestClient``),
verifying the full teacher-note push/pull cycle AND session-history
reconstruction across the real Phase 1-6 sync pipeline.

17-step scenario (§ Phase 7 brief "Two-Client Acceptance Test"):
    1-2.  Teacher A + Student A authenticate (bootstrap via apply_remote_upsert).
    3-4.  Student A begins an experiment; measurements persisted incrementally.
    5.    Teacher monitoring sees Student A ACTIVE.
    6.    Teacher A sends feedback (a TeacherNote).
    7-8.  Student A automatically receives it — NO manual Sync call anywhere
          in this test, every delivery goes through ``engine.run_sync()``
          exactly as the real SyncWorker/SyncEngine pipeline does.
    9-10. Student A continues measuring; teacher sees further updates.
    11-12. Student A finishes; teacher sees COMPLETED.
    13-14. Teacher opens the completed session from monitoring — exact
           measurement sequence reconstructs (§ DataJournalPage's own
           underlying data access path: ISessionRepository.get_session()/
           get_measurements()).
    15.   Unauthorized Teacher C gets neither feedback-send access nor
          history access to Student A.
    16.   Unrelated Student B never receives Student A's note.
    17.   Repeated sync cycles produce no duplicate notes/measurements.
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
from domain.entities.teacher_note import TeacherNote
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
from infrastructure.storage.sqlite_teacher_note_repository import SqliteTeacherNoteRepository
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
    note_repo = SqliteTeacherNoteRepository(db_path, sync_outbox_repository=outbox)
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
        student_progress_repository=progress_repo, teacher_note_repository=note_repo,
        get_active_role_and_sync_id=lambda: (role, sync_id),
        get_cached_token=lambda: token_cache.get("token"),
        set_cached_token=lambda token, expires_at, r, s: token_cache.__setitem__("token", (token, expires_at, r, s)),
    )
    return {
        "engine": engine, "classroom": classroom_repo, "student": student_repo, "teacher": teacher_repo,
        "session": session_repo, "batch": batch_repo, "progress": progress_repo, "note": note_repo,
        "outbox": outbox, "api_client": api_client, "db_path": db_path,
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
    student_b = _build_client(shared_server, "student", "sb", str(tmp_path / "student_b.db"), classroom_id="ca")

    teacher_a["classroom"].create(Classroom(id="ca", name="8A", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER)
    teacher_a["student"].create(
        Student(id="sa", classroom_id="ca", first_name="Student", last_name="A", created_at=_NOW, updated_at=_NOW, student_code="code-sa"),
        UserRole.TEACHER,
    )
    teacher_a["student"].create(
        Student(id="sb", classroom_id="ca", first_name="Student", last_name="B", created_at=_NOW, updated_at=_NOW, student_code="code-sb"),
        UserRole.TEACHER,
    )
    teacher_a["teacher"].set_assigned_classroom_ids("ta", ("ca",))
    teacher_a["engine"].run_sync()

    # § Teacher C — толығымен басқа сынып, "ca"-ға МҮЛДЕ тағайындалмаған.
    teacher_c["classroom"].create(Classroom(id="cc", name="Unrelated", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER)
    teacher_c["teacher"].set_assigned_classroom_ids("tc", ("cc",))
    teacher_c["engine"].run_sync()

    student_a["engine"].run_sync()
    student_b["engine"].run_sync()

    return {
        "shared_server": shared_server, "teacher_a": teacher_a, "teacher_c": teacher_c,
        "student_a": student_a, "student_b": student_b,
    }


def test_full_teacher_note_and_session_history_acceptance_scenario(world) -> None:
    teacher_a = world["teacher_a"]
    teacher_c = world["teacher_c"]
    student_a = world["student_a"]
    student_b = world["student_b"]

    # ---- 3-4. Student A begins an experiment, measurements persist. --------
    student_a["progress"].link_session("sess-a", "sa", "ca", "ohms-law")
    student_a["session"].append_measurements("sess-a", "ohms-law", _generate_measurements(10), started_at=_NOW - timedelta(seconds=10))
    student_a["batch"].create_pending_batches_for_session("sess-a", chunk_size=_CHUNK_SIZE, finalize=False)
    assert student_a["engine"].run_sync().status.value == "synced"

    # ---- 5. Teacher monitoring sees Student A ACTIVE. -----------------------
    assert teacher_a["engine"].run_sync().status.value == "synced"
    snapshot = compute_classroom_monitoring(
        "ca", classroom_repository=teacher_a["classroom"], student_repository=teacher_a["student"],
        student_progress_repository=teacher_a["progress"], session_repository=teacher_a["session"], now=_NOW,
    )
    student_snapshot = next(s for s in snapshot.students if s.student_id == "sa")
    assert student_snapshot.activity_state is MonitoringActivityState.ACTIVE

    # ---- 6. Teacher A sends feedback (a TeacherNote). -----------------------
    teacher_a["note"].create(
        TeacherNote(
            id="note-1", teacher_id="ta", student_id="sa", classroom_id="ca",
            message="Өлшеуді қайта тексер", created_at=_NOW, experiment_id="ohms-law", session_id="sess-a",
        ),
        UserRole.TEACHER,
    )
    push_result = teacher_a["engine"].run_sync()
    assert push_result.status.value == "synced"

    # ---- 7-8. Student A automatically receives it — no manual Sync. --------
    pull_result = student_a["engine"].run_sync()
    assert pull_result.status.value == "synced"
    received_notes = student_a["note"].list_for_student("sa")
    assert len(received_notes) == 1
    assert received_notes[0].message == "Өлшеуді қайта тексер"

    # ---- 9-10. Student A continues measuring; teacher sees further updates. -
    student_a["session"].append_measurements("sess-a", "ohms-law", _generate_measurements(10, offset=10), started_at=_NOW - timedelta(seconds=10))
    student_a["batch"].create_pending_batches_for_session("sess-a", chunk_size=_CHUNK_SIZE, finalize=False)
    student_a["engine"].run_sync()  # § student continues collecting WHILE feedback already arrived
    teacher_a["engine"].run_sync()
    detail = compute_student_monitoring_detail(
        "sa", "ohms-law", student_repository=teacher_a["student"], classroom_repository=teacher_a["classroom"],
        student_progress_repository=teacher_a["progress"], session_repository=teacher_a["session"], now=_NOW,
    )
    assert len(detail.measurements) == 20

    # ---- 11-12. Student A finishes; teacher sees COMPLETED. -----------------
    from domain.entities.experiment_session import ExperimentSession

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
    final_student_snapshot = next(s for s in final_snapshot.students if s.student_id == "sa")
    assert final_student_snapshot.activity_state is MonitoringActivityState.COMPLETED

    # ---- 13-14. Teacher opens the completed session from monitoring — ------
    # exact measurement sequence reconstructs (§ DataJournalPage's own
    # ISessionRepository.get_session()/get_measurements() access path).
    history_summary = teacher_a["session"].get_session("sess-a")
    assert history_summary is not None
    history_measurements = teacher_a["session"].get_measurements("sess-a")
    assert len(history_measurements) == 20
    original_values = [m.values["voltage"] for m in all_measurements]
    history_values = [m.values["voltage"] for m in history_measurements]
    assert history_values == original_values

    # ---- 15. Unauthorized Teacher C: neither send access nor history. ------
    teacher_c["engine"].run_sync()
    # § "history access" — Teacher C's local DB never received "ca"'s
    # session/measurements in the first place (server-side pull filter).
    assert teacher_c["session"].get_session("sess-a") is None
    assert teacher_c["session"].get_measurements("sess-a") == ()
    unauthorized_snapshot = compute_classroom_monitoring(
        "ca", classroom_repository=teacher_c["classroom"], student_repository=teacher_c["student"],
        student_progress_repository=teacher_c["progress"], session_repository=teacher_c["session"], now=_NOW,
    )
    assert unauthorized_snapshot is None
    # § "send access" — server-side push authorization rejects it outright
    # (already unit/server-tested explicitly; re-verified here end-to-end).
    from domain.interfaces.i_sync_api_client import SyncAuthorizationError

    teacher_c["note"].create(
        TeacherNote(id="note-forbidden", teacher_id="tc", student_id="sa", classroom_id="ca",
                    message="unauthorized", created_at=_NOW),
        UserRole.TEACHER,
    )
    with pytest.raises(SyncAuthorizationError):
        teacher_c["api_client"].push(
            "teacher_note", [teacher_c["note"].get_note_sync_payload("note-forbidden")]
        )

    # ---- 16. Unrelated Student B never receives Student A's feedback. ------
    student_b["engine"].run_sync()
    assert student_b["note"].list_for_student("sb") == ()

    # ---- 17. Repeated sync cycles produce no duplicate notes/measurements. -
    teacher_a["engine"].run_sync()
    student_a["engine"].run_sync()
    assert len(student_a["note"].list_for_student("sa")) == 1
    assert len(teacher_a["session"].get_measurements("sess-a")) == 20
