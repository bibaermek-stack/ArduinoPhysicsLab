"""§12 "Live Demo / POC" — Phase 6 (Teacher Live Classroom Monitoring
Dashboard).

Real (but ephemeral, isolated-test-database) manual demonstration,
against a REAL ``uvicorn`` server on a real socket, of the full
classroom-monitoring read model (``domain/services/teacher_
monitoring.py``) built on top of the Phase 1-5 sync architecture:

    Cloud server
    Teacher A -> Classroom 8A -> Student A (assigned)
    Teacher C -> Classroom 8C (NOT assigned to Student A)

  1.  Start the server, authenticate both clients, teacher opens the
      classroom dashboard -- student has not started yet.
  2.  Student A starts an experiment and generates measurements; a
      sync makes the batch visible.
  3.  Teacher A's classroom snapshot shows the student as ACTIVE,
      with correct measurement count.
  4.  Partial measurement updates continue -- teacher's student-detail
      read model receives the growing measurement history.
  5.  Teacher A re-syncs (simulating the Phase 5 periodic auto-refresh
      tick) -- no manual "Sync" concept needed here beyond calling the
      same ``SyncEngine.run_sync()`` the real periodic timer calls.
  6.  Student A disconnects (server unreachable) -- keeps collecting
      locally, offline-first.
  7.  Teacher A's snapshot -- still shows the OLD measurement count
      (last known data); with time advanced past the stale window
      (injected ``now``, no real sleep) it correctly reclassifies the
      session as STALE/OFFLINE ("awaiting data"), never fabricating a
      literal network-disconnect claim.
  8.  Student A reconnects and uploads the pending batches.
  9.  Teacher A automatically receives them on the next sync -- catch-up.
  10. Student A finalizes the experiment.
  11. Teacher A's snapshot shows COMPLETED, exact final reconstruction
      (count/order/values), no duplicates.
  12. Unauthorized Teacher C's classroom snapshot for "ca" is empty
      (classroom never pulled -- isolation via the existing Phase 3
      server-side authorization boundary, unchanged).

Prints a concise PASS/FAIL summary at the end. Uses only temp files/an
ephemeral port/synthetic names -- the user's real classroom data and
real database are never touched (§33 "POC data must be synthetic").

    python scripts/sync_poc_demo_phase6.py
"""

from __future__ import annotations

import os
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
from domain.entities.user_role import UserRole  # noqa: E402
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
        student_progress_repository=progress_repo,
        get_active_role_and_sync_id=lambda: (role, sync_id),
        get_cached_token=lambda: token_cache.get("token"),
        set_cached_token=lambda token, expires_at, r, s: token_cache.__setitem__("token", (token, expires_at, r, s)),
    )
    closeables = (classroom_repo, student_repo, teacher_repo, session_repo, batch_repo, progress_repo, outbox)
    return {"engine": engine, "classroom": classroom_repo, "student": student_repo, "teacher": teacher_repo,
            "session": session_repo, "batch": batch_repo, "progress": progress_repo, "outbox": outbox,
            "api_client": api_client, "closeables": closeables}


def _generate_measurements(count: int, offset: int, base_time: datetime) -> tuple[Measurement, ...]:
    return tuple(
        Measurement(timestamp=base_time - timedelta(seconds=(count - i)), values={"voltage": round(6.0 + (offset + i) * 0.01, 4)}, experiment_id="ohms-law")
        for i in range(count)
    )


def main() -> None:
    now = datetime.now(timezone.utc)
    all_closeables: list = []
    server = None

    with tempfile.TemporaryDirectory(prefix="apl_sync_poc_phase6_", ignore_cleanup_errors=True) as tmp:
        try:
            tmp_dir = Path(tmp)
            port = _free_port()
            base_url = f"http://127.0.0.1:{port}"

            print(f"1. Starting FastAPI server on {base_url} (isolated temp DB)...")
            server = _start_server(tmp_dir / "server.db", port)

            print("2. Authenticating Teacher A / 8A / Student A and Teacher C / 8C (unassigned)...")
            teacher_a = _build_client(tmp_dir, "teacher_a", base_url, "teacher", "ta")
            teacher_c = _build_client(tmp_dir, "teacher_c", base_url, "teacher", "tc")
            student_a = _build_client(tmp_dir, "student_a", base_url, "student", "sa", classroom_id="ca")
            for c in (teacher_a, teacher_c, student_a):
                all_closeables.extend(c["closeables"])

            teacher_a["classroom"].create(Classroom(id="ca", name="Demo 8A", created_at=now, updated_at=now), UserRole.TEACHER)
            teacher_a["student"].create(
                Student(id="sa", classroom_id="ca", first_name="Demo", last_name="StudentA", created_at=now, updated_at=now, student_code="code-sa"),
                UserRole.TEACHER,
            )
            teacher_a["teacher"].set_assigned_classroom_ids("ta", ("ca",))
            teacher_a["engine"].run_sync()
            teacher_c["classroom"].create(Classroom(id="cc", name="Demo 8C", created_at=now, updated_at=now), UserRole.TEACHER)
            teacher_c["teacher"].set_assigned_classroom_ids("tc", ("cc",))
            teacher_c["engine"].run_sync()
            student_a["engine"].run_sync()

            print("   Teacher A opens the classroom dashboard -- student has not started...")
            snapshot = compute_classroom_monitoring(
                "ca", classroom_repository=teacher_a["classroom"], student_repository=teacher_a["student"],
                student_progress_repository=teacher_a["progress"], session_repository=teacher_a["session"], now=now,
            )
            _check(
                "Classroom visible with 1 student, NOT_STARTED before any experiment",
                snapshot is not None and snapshot.total_students == 1
                and snapshot.students[0].activity_state is MonitoringActivityState.NOT_STARTED,
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
            _check(
                "Teacher A automatically sees ACTIVE state with 10 measurements",
                snapshot.students[0].activity_state is MonitoringActivityState.ACTIVE
                and snapshot.students[0].measurement_count == 10,
            )

            print("4. Student A generates more data -- teacher's detail view grows...")
            student_a["session"].append_measurements("sess-a", "ohms-law", _generate_measurements(10, 10, now), started_at=now - timedelta(seconds=10))
            student_a["batch"].create_pending_batches_for_session("sess-a", chunk_size=_CHUNK_SIZE, finalize=False)
            student_a["engine"].run_sync()
            teacher_a["engine"].run_sync()
            detail = compute_student_monitoring_detail(
                "sa", "ohms-law", student_repository=teacher_a["student"], classroom_repository=teacher_a["classroom"],
                student_progress_repository=teacher_a["progress"], session_repository=teacher_a["session"], now=now,
            )
            _check("Partial measurement updates reach the teacher's detail view (20 samples)", len(detail.measurements) == 20)

            print("5. Student A loses connectivity -- keeps collecting locally...")
            student_a["api_client"].check_health = lambda: False
            student_a["session"].append_measurements("sess-a", "ohms-law", _generate_measurements(10, 20, now), started_at=now - timedelta(seconds=10))
            student_a["batch"].create_pending_batches_for_session("sess-a", chunk_size=_CHUNK_SIZE, finalize=False)
            offline_result = student_a["engine"].run_sync()
            _check("Offline: local collection continues, no crash", offline_result.status.value == "offline")

            print("   Teacher A retains last-known data, then reclassifies as stale after time passes...")
            snapshot_offline = compute_classroom_monitoring(
                "ca", classroom_repository=teacher_a["classroom"], student_repository=teacher_a["student"],
                student_progress_repository=teacher_a["progress"], session_repository=teacher_a["session"], now=now,
            )
            _check("Teacher retains last known count (20) while student is offline", snapshot_offline.students[0].measurement_count == 20)
            much_later = now + timedelta(minutes=5)
            snapshot_stale = compute_classroom_monitoring(
                "ca", classroom_repository=teacher_a["classroom"], student_repository=teacher_a["student"],
                student_progress_repository=teacher_a["progress"], session_repository=teacher_a["session"], now=much_later,
            )
            _check(
                "Stale classification after the activity window elapses (no fabricated disconnect)",
                snapshot_stale.students[0].activity_state is MonitoringActivityState.OFFLINE,
            )

            print("6. Student A reconnects and uploads the pending batch...")
            student_a["api_client"].check_health = lambda: True
            reconnect_result = student_a["engine"].run_sync()
            teacher_a["engine"].run_sync()
            detail_after_reconnect = compute_student_monitoring_detail(
                "sa", "ohms-law", student_repository=teacher_a["student"], classroom_repository=teacher_a["classroom"],
                student_progress_repository=teacher_a["progress"], session_repository=teacher_a["session"], now=now,
            )
            _check(
                "Teacher automatically catches up to all 30 samples after reconnect",
                reconnect_result.status.value == "synced" and len(detail_after_reconnect.measurements) == 30,
            )

            print("7. Student A finalizes the experiment (partial tail batch)...")
            student_a["session"].append_measurements("sess-a", "ohms-law", _generate_measurements(3, 30, now), started_at=now - timedelta(seconds=10))
            all_measurements = student_a["session"].get_measurements("sess-a")
            student_a["session"].save_session(
                ExperimentSession(id="sess-a", experiment_id="ohms-law", started_at=now - timedelta(seconds=40), ended_at=now, measurements=list(all_measurements))
            )
            student_a["batch"].create_pending_batches_for_session("sess-a", chunk_size=_CHUNK_SIZE, finalize=True)
            student_a["engine"].run_sync()
            teacher_a["engine"].run_sync()
            final_detail = compute_student_monitoring_detail(
                "sa", "ohms-law", student_repository=teacher_a["student"], classroom_repository=teacher_a["classroom"],
                student_progress_repository=teacher_a["progress"], session_repository=teacher_a["session"], now=now,
            )
            original_values = [m.values["voltage"] for m in all_measurements]
            final_values = [m.values["voltage"] for m in final_detail.measurements]
            _check(
                "Completion: teacher sees COMPLETED, exact reconstruction, no duplicates (33 samples)",
                final_detail.activity_state is MonitoringActivityState.COMPLETED
                and len(final_detail.measurements) == 33
                and final_values == original_values,
            )
            teacher_a["engine"].run_sync()
            detail_repeat = compute_student_monitoring_detail(
                "sa", "ohms-law", student_repository=teacher_a["student"], classroom_repository=teacher_a["classroom"],
                student_progress_repository=teacher_a["progress"], session_repository=teacher_a["session"], now=now,
            )
            _check("Repeat teacher sync creates no duplicate measurements", len(detail_repeat.measurements) == 33)

            print("8. Unauthorized Teacher C's classroom snapshot for 8A must be empty...")
            teacher_c["engine"].run_sync()
            unauthorized_snapshot = compute_classroom_monitoring(
                "ca", classroom_repository=teacher_c["classroom"], student_repository=teacher_c["student"],
                student_progress_repository=teacher_c["progress"], session_repository=teacher_c["session"], now=now,
            )
            _check("Unassigned Teacher C sees no trace of classroom 8A", unauthorized_snapshot is None)

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
    print("Phase 6 teacher live classroom monitoring dashboard acceptance scenario verified end to end.")


if __name__ == "__main__":
    main()
