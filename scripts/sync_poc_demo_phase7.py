"""§12 "Live Demo / POC" — Phase 7 (Teacher Actions, Feedback Delivery,
and Session History).

Real (but ephemeral, isolated-test-database) manual demonstration,
against a REAL ``uvicorn`` server on a real socket, of the Phase 7
teacher-note feedback delivery + session-history reconstruction built
on top of the Phase 1-6 sync architecture:

    Cloud server
    Teacher A -> Classroom 8A -> Student A (assigned), Student B (assigned)
    Teacher C -> Classroom 8C (NOT assigned to Student A/B)

  1.  Start the server, authenticate all clients. Teacher A opens the
      classroom dashboard -- Student A has not started yet.
  2.  Student A starts an experiment and pushes the first batch; a
      sync makes it visible.
  3.  Teacher A's classroom snapshot shows Student A as ACTIVE.
  4.  Teacher A sends a short feedback note to Student A.
  5.  Student A automatically receives it on the next sync -- no
      manual "send"/"read" action beyond the same ``run_sync()`` the
      real periodic timer calls.
  6.  Student A continues collecting measurements; teacher sees the
      updated count without any manual Sync button.
  7.  Student A disconnects mid-experiment, keeps collecting locally,
      reconnects -- teacher automatically catches up to the full
      backlog.
  8.  Student A finishes the experiment -- teacher sees COMPLETED.
  9.  Teacher A opens the completed session from the monitoring
      workflow (the same ``ISessionRepository`` read path
      ``DataJournalPage`` uses) -- exact measurement sequence
      reconstructs.
  10. Repeated sync cycles create no duplicate notes/measurements.
  11. Unauthorized Teacher C gets neither history access nor send
      access (a direct push attempt is rejected with 403) to
      Student A.
  12. Unrelated Student B never receives Student A's note.

Prints a concise PASS/FAIL summary at the end. Uses only temp files/an
ephemeral port/synthetic names -- the user's real classroom data and
real database are never touched.

    python scripts/sync_poc_demo_phase7.py
"""

from __future__ import annotations

import socket
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from domain.entities.classroom import Classroom  # noqa: E402
from domain.entities.experiment_session import ExperimentSession  # noqa: E402
from domain.entities.measurement import Measurement  # noqa: E402
from domain.entities.monitoring_activity_state import MonitoringActivityState  # noqa: E402
from domain.entities.student import Student  # noqa: E402
from domain.entities.teacher import Teacher  # noqa: E402
from domain.entities.teacher_note import TeacherNote  # noqa: E402
from domain.entities.user_role import UserRole  # noqa: E402
from domain.interfaces.i_sync_api_client import SyncAuthorizationError  # noqa: E402
from domain.services.sync_engine import SyncEngine  # noqa: E402
from domain.services.teacher_monitoring import (  # noqa: E402
    compute_classroom_monitoring,
    compute_student_monitoring_detail,
)
from domain.services.teacher_pin import hash_pin  # noqa: E402
from infrastructure.storage.sqlite_classroom_repository import SqliteClassroomRepository  # noqa: E402
from infrastructure.storage.sqlite_measurement_batch_repository import (  # noqa: E402
    SqliteMeasurementBatchRepository,
)
from infrastructure.storage.sqlite_session_repository import SqliteSessionRepository  # noqa: E402
from infrastructure.storage.sqlite_student_progress_repository import (  # noqa: E402
    SqliteStudentProgressRepository,
)
from infrastructure.storage.sqlite_student_repository import SqliteStudentRepository  # noqa: E402
from infrastructure.storage.sqlite_sync_outbox_repository import SqliteSyncOutboxRepository  # noqa: E402
from infrastructure.storage.sqlite_teacher_note_repository import SqliteTeacherNoteRepository  # noqa: E402
from infrastructure.storage.sqlite_teacher_repository import SqliteTeacherRepository  # noqa: E402
from infrastructure.sync.http_sync_api_client import HttpSyncApiClient  # noqa: E402
from server.app.main import app as fastapi_app  # noqa: E402

_API_KEY = "dev-local-only-key"
_CHUNK_SIZE = 10
_checks: list[tuple[str, bool]] = []


def _check(name: str, condition: bool) -> None:
    _checks.append((name, condition))
    print(f"   [{'PASS' if condition else 'FAIL'}] {name}")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _start_server(db_path: Path, port: int) -> uvicorn.Server:
    import os

    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ["APL_SYNC_API_KEY"] = _API_KEY
    config = uvicorn.Config(fastapi_app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    return server


def _build_client(db_dir: Path, label: str, base_url: str, role: str, sync_id: str, classroom_id: str = ""):
    now = datetime.now(timezone.utc)
    db_path = db_dir / f"data_{label}.db"
    outbox = SqliteSyncOutboxRepository(db_path)
    classroom_repo = SqliteClassroomRepository(db_path, sync_outbox_repository=outbox)
    student_repo = SqliteStudentRepository(db_path, sync_outbox_repository=outbox)
    teacher_repo = SqliteTeacherRepository(db_path, sync_outbox_repository=outbox)
    session_repo = SqliteSessionRepository(db_path, sync_outbox_repository=outbox)
    batch_repo = SqliteMeasurementBatchRepository(db_path, sync_outbox_repository=outbox)
    note_repo = SqliteTeacherNoteRepository(db_path, sync_outbox_repository=outbox)
    progress_repo = SqliteStudentProgressRepository(
        db_path, session_repository=session_repo,
        classroom_repository=classroom_repo, student_repository=student_repo, sync_outbox_repository=outbox,
    )
    if role == "teacher":
        teacher_repo.apply_remote_upsert(
            Teacher(id=sync_id, full_name=f"Teacher {sync_id}", pin_hash=hash_pin(f"pin-{sync_id}"),
                    created_at=now, updated_at=now, sync_id=sync_id)
        )
    else:
        student_repo.apply_remote_upsert(
            Student(id=sync_id, classroom_id=classroom_id, first_name="Demo", last_name=sync_id,
                    created_at=now, updated_at=now, student_code=f"code-{sync_id}", sync_id=sync_id)
        )
    api_client = HttpSyncApiClient(base_url=base_url, api_key=_API_KEY)
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
    closeables = (classroom_repo, student_repo, teacher_repo, session_repo, batch_repo, note_repo, progress_repo, outbox)
    return {"engine": engine, "classroom": classroom_repo, "student": student_repo, "teacher": teacher_repo,
            "session": session_repo, "batch": batch_repo, "note": note_repo, "progress": progress_repo,
            "outbox": outbox, "api_client": api_client, "closeables": closeables}


def _generate_measurements(count: int, offset: int, base_time: datetime) -> tuple[Measurement, ...]:
    return tuple(
        Measurement(timestamp=base_time - timedelta(seconds=(count - i)), values={"voltage": round(6.0 + (offset + i) * 0.01, 4)}, experiment_id="ohms-law")
        for i in range(count)
    )


def main() -> None:
    now = datetime.now(timezone.utc)
    all_closeables: list = []
    server = None

    with tempfile.TemporaryDirectory(prefix="apl_sync_poc_phase7_", ignore_cleanup_errors=True) as tmp:
        try:
            tmp_dir = Path(tmp)
            port = _free_port()
            base_url = f"http://127.0.0.1:{port}"

            print(f"1. Starting FastAPI server on {base_url} (isolated temp DB)...")
            server = _start_server(tmp_dir / "server.db", port)

            print("2. Authenticating Teacher A / 8A / Student A / Student B and Teacher C / 8C (unassigned)...")
            teacher_a = _build_client(tmp_dir, "teacher_a", base_url, "teacher", "ta")
            teacher_c = _build_client(tmp_dir, "teacher_c", base_url, "teacher", "tc")
            student_a = _build_client(tmp_dir, "student_a", base_url, "student", "sa", classroom_id="ca")
            student_b = _build_client(tmp_dir, "student_b", base_url, "student", "sb", classroom_id="ca")
            for c in (teacher_a, teacher_c, student_a, student_b):
                all_closeables.extend(c["closeables"])

            teacher_a["classroom"].create(Classroom(id="ca", name="Demo 8A", created_at=now, updated_at=now), UserRole.TEACHER)
            teacher_a["student"].create(
                Student(id="sa", classroom_id="ca", first_name="Demo", last_name="StudentA", created_at=now, updated_at=now, student_code="code-sa"),
                UserRole.TEACHER,
            )
            teacher_a["student"].create(
                Student(id="sb", classroom_id="ca", first_name="Demo", last_name="StudentB", created_at=now, updated_at=now, student_code="code-sb"),
                UserRole.TEACHER,
            )
            teacher_a["teacher"].set_assigned_classroom_ids("ta", ("ca",))
            teacher_a["engine"].run_sync()
            teacher_c["classroom"].create(Classroom(id="cc", name="Demo 8C", created_at=now, updated_at=now), UserRole.TEACHER)
            teacher_c["teacher"].set_assigned_classroom_ids("tc", ("cc",))
            teacher_c["engine"].run_sync()
            student_a["engine"].run_sync()
            student_b["engine"].run_sync()

            print("   Teacher A opens the classroom dashboard -- Student A has not started...")
            snapshot = compute_classroom_monitoring(
                "ca", classroom_repository=teacher_a["classroom"], student_repository=teacher_a["student"],
                student_progress_repository=teacher_a["progress"], session_repository=teacher_a["session"], now=now,
            )
            _check(
                "Classroom visible with 2 students, Student A NOT_STARTED",
                snapshot is not None and snapshot.total_students == 2
                and next(s for s in snapshot.students if s.student_id == "sa").activity_state
                is MonitoringActivityState.NOT_STARTED,
            )

            print("3. Student A starts an experiment and pushes the first batch...")
            student_a["progress"].link_session("sess-a", "sa", "ca", "ohms-law")
            student_a["session"].append_measurements("sess-a", "ohms-law", _generate_measurements(10, 0, now), started_at=now - timedelta(seconds=10))
            student_a["batch"].create_pending_batches_for_session("sess-a", chunk_size=_CHUNK_SIZE, finalize=False)
            student_a["engine"].run_sync()
            teacher_a["engine"].run_sync()
            snapshot = compute_classroom_monitoring(
                "ca", classroom_repository=teacher_a["classroom"], student_repository=teacher_a["student"],
                student_progress_repository=teacher_a["progress"], session_repository=teacher_a["session"], now=now,
            )
            student_a_snapshot = next(s for s in snapshot.students if s.student_id == "sa")
            _check(
                "Teacher A automatically sees Student A ACTIVE with 10 measurements",
                student_a_snapshot.activity_state is MonitoringActivityState.ACTIVE
                and student_a_snapshot.measurement_count == 10,
            )

            print("4. Teacher A sends a short feedback note to Student A...")
            teacher_a["note"].create(
                TeacherNote(id="note-1", teacher_id="ta", student_id="sa", classroom_id="ca",
                            message="Кернеу мәніне назар аудар", created_at=now, experiment_id="ohms-law", session_id="sess-a"),
                UserRole.TEACHER,
            )
            push_result = teacher_a["engine"].run_sync()
            _check("Feedback note pushed successfully (Жеткізілді)", push_result.status.value == "synced")

            print("5. Student A automatically receives the note on the next sync (no manual action)...")
            student_a["engine"].run_sync()
            received = student_a["note"].list_for_student("sa")
            _check(
                "Student A automatically received the exact note text",
                len(received) == 1 and received[0].message == "Кернеу мәніне назар аудар",
            )

            print("6. Student A continues measuring; teacher sees updated count with no manual Sync...")
            student_a["session"].append_measurements("sess-a", "ohms-law", _generate_measurements(10, 10, now), started_at=now - timedelta(seconds=10))
            student_a["batch"].create_pending_batches_for_session("sess-a", chunk_size=_CHUNK_SIZE, finalize=False)
            student_a["engine"].run_sync()
            teacher_a["engine"].run_sync()
            detail = compute_student_monitoring_detail(
                "sa", "ohms-law", student_repository=teacher_a["student"], classroom_repository=teacher_a["classroom"],
                student_progress_repository=teacher_a["progress"], session_repository=teacher_a["session"], now=now,
            )
            _check("Teacher sees updated measurement count (20) without any manual Sync button", len(detail.measurements) == 20)

            print("7. Student A disconnects, keeps collecting locally, then reconnects...")
            student_a["api_client"].check_health = lambda: False
            student_a["session"].append_measurements("sess-a", "ohms-law", _generate_measurements(10, 20, now), started_at=now - timedelta(seconds=10))
            student_a["batch"].create_pending_batches_for_session("sess-a", chunk_size=_CHUNK_SIZE, finalize=False)
            offline_result = student_a["engine"].run_sync()
            student_a["api_client"].check_health = lambda: True
            reconnect_result = student_a["engine"].run_sync()
            teacher_a["engine"].run_sync()
            detail_after_reconnect = compute_student_monitoring_detail(
                "sa", "ohms-law", student_repository=teacher_a["student"], classroom_repository=teacher_a["classroom"],
                student_progress_repository=teacher_a["progress"], session_repository=teacher_a["session"], now=now,
            )
            _check(
                "Offline collection + automatic reconnect catch-up to 30 measurements",
                offline_result.status.value == "offline" and reconnect_result.status.value == "synced"
                and len(detail_after_reconnect.measurements) == 30,
            )

            print("8. Student A finishes the experiment...")
            student_a["session"].append_measurements("sess-a", "ohms-law", _generate_measurements(3, 30, now), started_at=now - timedelta(seconds=10))
            all_measurements = student_a["session"].get_measurements("sess-a")
            student_a["session"].save_session(
                ExperimentSession(id="sess-a", experiment_id="ohms-law", started_at=now - timedelta(seconds=40), ended_at=now, measurements=list(all_measurements))
            )
            student_a["batch"].create_pending_batches_for_session("sess-a", chunk_size=_CHUNK_SIZE, finalize=True)
            student_a["engine"].run_sync()
            teacher_a["engine"].run_sync()
            final_snapshot = compute_classroom_monitoring(
                "ca", classroom_repository=teacher_a["classroom"], student_repository=teacher_a["student"],
                student_progress_repository=teacher_a["progress"], session_repository=teacher_a["session"], now=now,
            )
            final_student_a = next(s for s in final_snapshot.students if s.student_id == "sa")
            _check("Teacher sees Student A COMPLETED after finishing", final_student_a.activity_state is MonitoringActivityState.COMPLETED)

            print("9. Teacher A opens the completed session from the monitoring workflow (session history)...")
            history_summary = teacher_a["session"].get_session("sess-a")
            history_measurements = teacher_a["session"].get_measurements("sess-a")
            original_values = [m.values["voltage"] for m in all_measurements]
            history_values = [m.values["voltage"] for m in history_measurements]
            _check(
                "Session history opens with exact measurement sequence reconstructed (33 samples)",
                history_summary is not None and len(history_measurements) == 33 and history_values == original_values,
            )

            print("10. Repeated sync cycles create no duplicates...")
            teacher_a["engine"].run_sync()
            student_a["engine"].run_sync()
            _check(
                "Repeated sync produces no duplicate notes/measurements",
                len(student_a["note"].list_for_student("sa")) == 1
                and len(teacher_a["session"].get_measurements("sess-a")) == 33,
            )

            print("11. Unauthorized Teacher C gets neither history nor send access to Student A...")
            teacher_c["engine"].run_sync()
            no_history = teacher_c["session"].get_session("sess-a") is None
            unauthorized_snapshot = compute_classroom_monitoring(
                "ca", classroom_repository=teacher_c["classroom"], student_repository=teacher_c["student"],
                student_progress_repository=teacher_c["progress"], session_repository=teacher_c["session"], now=now,
            )
            teacher_c["note"].create(
                TeacherNote(id="note-forbidden", teacher_id="tc", student_id="sa", classroom_id="ca", message="unauthorized", created_at=now),
                UserRole.TEACHER,
            )
            send_rejected = False
            try:
                teacher_c["api_client"].push("teacher_note", [teacher_c["note"].get_note_sync_payload("note-forbidden")])
            except SyncAuthorizationError:
                send_rejected = True
            _check(
                "Unauthorized Teacher C: no history access, send attempt rejected (403)",
                no_history and unauthorized_snapshot is None and send_rejected,
            )

            print("12. Unrelated Student B never receives Student A's note...")
            student_b["engine"].run_sync()
            _check("Unrelated Student B receives no notes", student_b["note"].list_for_student("sb") == ())

            server.should_exit = True
            time.sleep(0.3)
        finally:
            for closeable in all_closeables:
                closeable.close()
            if server is not None:
                server.should_exit = True
                time.sleep(0.2)

    print("\n" + "=" * 60)
    passed = sum(1 for _, ok in _checks if ok)
    print(f"PASS/FAIL SUMMARY: {passed}/{len(_checks)} checks passed")
    for name, ok in _checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    print("=" * 60)

    if passed != len(_checks):
        sys.exit(1)
    print("Phase 7 teacher actions, feedback delivery, and session history acceptance scenario verified end to end.")


if __name__ == "__main__":
    main()
