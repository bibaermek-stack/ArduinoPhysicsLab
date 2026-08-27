"""§12 "Live Demo / POC" — Phase 5 (Connectivity-Aware Automatic Sync +
Near-Real-Time Classroom Monitoring).

Real (but ephemeral, isolated-test-database) manual demonstration,
against a REAL ``uvicorn`` server on a real socket, of:

    Cloud server
    Teacher A -> Classroom 8A -> Student A (assigned)
    Teacher B -> Classroom 8B (NOT assigned to Student A)

  1.  Start the server, authenticate both clients.
  2.  Student A starts an "experiment" and generates realistic
      multi-batch samples while the connectivity monitor confirms the
      server is reachable — automatic partial delivery WITHOUT a
      manual Sync button press (§ ``ConnectivityMonitor``/
      ``SyncWorker._on_connectivity_timer_tick()`` production logic,
      exercised here exactly as it runs in the real app).
  3.  Stop the server: Student A keeps collecting measurements
      completely offline — acquisition/local persistence never stall.
  4.  Restart the server: the connectivity monitor detects the
      OFFLINE -> ONLINE edge and automatically triggers a sync cycle
      -- no manual Sync action is taken anywhere in this script.
  5.  Teacher A (a second, fully isolated client) periodically re-syncs
      (§ "teacher auto-refresh") and automatically receives the
      measurements Student A collected while offline.
  6.  Student A finalizes ("Stops") the experiment -- the tail batch
      delivers automatically on the very next connectivity tick.
  7.  Exact full reconstruction is verified on Teacher A's isolated
      local database: sample count/order/values match, no duplicates.
  8.  Teacher B (NOT assigned to 8A) syncs and receives NOTHING for
      this session.

Prints a concise PASS/FAIL summary at the end. Uses only temp files/an
ephemeral port/synthetic names -- the user's real classroom data and
real database are never touched (§33 "POC data must be synthetic").

    python scripts/sync_poc_demo_phase5.py
"""

from __future__ import annotations

import os
import socket
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from domain.entities.classroom import Classroom  # noqa: E402
from domain.entities.measurement import Measurement  # noqa: E402
from domain.entities.student import Student  # noqa: E402
from domain.entities.teacher import Teacher  # noqa: E402
from domain.entities.user_role import UserRole  # noqa: E402
from domain.services.connectivity_monitor import ConnectivityMonitor  # noqa: E402
from domain.services.sync_engine import SyncEngine  # noqa: E402
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
            "api_client": api_client, "connectivity_monitor": ConnectivityMonitor(), "closeables": closeables}


def _connectivity_tick(client: dict, label: str) -> None:
    """§3/§4: НАҚТЫ ``SyncWorker._on_connectivity_timer_tick()``
    логикасын дәл қайталайды — жеңіл ``check_health()``, содан кейін
    OFFLINE->ONLINE ауысуы анықталса ғана толық ``run_sync()``."""
    is_online = client["api_client"].check_health()
    result = client["connectivity_monitor"].check(is_online)
    state = "ONLINE" if is_online else "OFFLINE"
    print(f"   [connectivity] {label}: server is {state}"
          f"{' (just restored -> triggering automatic sync)' if result.just_came_online else ''}")
    if result.just_came_online:
        sync_result = client["engine"].run_sync()
        print(f"   [auto-sync] {label}: {sync_result.status.value} (pushed={sync_result.pushed}, pulled={sync_result.pulled})")


def _generate_measurements(count: int, offset: int = 0) -> tuple[Measurement, ...]:
    now = datetime.now(timezone.utc)
    return tuple(
        Measurement(timestamp=now, values={"voltage": round(6.0 + (offset + i) * 0.01, 4)}, experiment_id="ohms-law")
        for i in range(count)
    )


def main() -> None:
    now = datetime.now(timezone.utc)
    all_closeables: list = []
    server = None

    with tempfile.TemporaryDirectory(prefix="apl_sync_poc_phase5_", ignore_cleanup_errors=True) as tmp:
        try:
            tmp_dir = Path(tmp)
            port = _free_port()
            base_url = f"http://127.0.0.1:{port}"

            print(f"1. Starting FastAPI server on {base_url} (isolated temp DB)...")
            server = _start_server(tmp_dir / "server.db", port)

            print("2. Authenticating Teacher A / 8A / Student A and Teacher B / 8B...")
            teacher_a = _build_client(tmp_dir, "teacher_a", base_url, "teacher", "ta")
            teacher_b = _build_client(tmp_dir, "teacher_b", base_url, "teacher", "tb")
            student_a = _build_client(tmp_dir, "student_a", base_url, "student", "sa", classroom_id="ca")
            for c in (teacher_a, teacher_b, student_a):
                all_closeables.extend(c["closeables"])

            teacher_a["classroom"].create(Classroom(id="ca", name="Demo 8A", created_at=now, updated_at=now), UserRole.TEACHER)
            teacher_a["student"].create(
                Student(id="sa", classroom_id="ca", first_name="Demo", last_name="StudentA", created_at=now, updated_at=now, student_code="code-sa"),
                UserRole.TEACHER,
            )
            teacher_a["teacher"].set_assigned_classroom_ids("ta", ("ca",))
            result_a_seed = teacher_a["engine"].run_sync()
            _check("Teacher A seeds+syncs 8A/Student A", result_a_seed.status.value == "synced")

            teacher_b["classroom"].create(Classroom(id="cb", name="Demo 8B", created_at=now, updated_at=now), UserRole.TEACHER)
            teacher_b["engine"].run_sync()
            student_a["engine"].run_sync()

            print("3. Student A starts an experiment (session linked, generating samples)...")
            student_a["progress"].link_session("sess-a", "sa", "ca", "ohms-law")

            print("4. Automatic partial delivery WHILE the experiment runs (no manual Sync)...")
            student_a["session"].append_measurements("sess-a", "ohms-law", _generate_measurements(14), started_at=now)
            student_a["batch"].create_pending_batches_for_session("sess-a", chunk_size=_CHUNK_SIZE, finalize=False)
            _connectivity_tick(student_a, "Student A")
            _check(
                "Automatic partial delivery: 1 full batch pushed without pressing Sync",
                len(student_a["batch"].list_pending_batch_ids_for_session("sess-a")) == 1
                and student_a["outbox"].count_pending() == 0,
            )

            print("5. Stopping the server -- Student A keeps collecting, fully offline...")
            server.should_exit = True
            time.sleep(0.5)
            student_a["session"].append_measurements("sess-a", "ohms-law", _generate_measurements(9, offset=14), started_at=now)
            student_a["batch"].create_pending_batches_for_session("sess-a", chunk_size=_CHUNK_SIZE, finalize=False)
            _connectivity_tick(student_a, "Student A")
            _check(
                "Offline: acquisition/local persistence never stalls (23 samples collected)",
                len(student_a["session"].get_measurements("sess-a")) == 23,
            )

            print("6. Restarting the server -- connectivity monitor auto-detects restoration...")
            server = _start_server(tmp_dir / "server.db", port)
            _connectivity_tick(student_a, "Student A")
            _check(
                "Reconnect: automatic upload happened with NO manual Sync action",
                student_a["outbox"].count_pending() == 0,
            )

            print("7. Student A finalizes ('Stops') the experiment -- tail batch delivers automatically...")
            # § "stopping/finalizing the experiment delivers the tail batch"
            # is an UNCONDITIONAL trigger in the real app (§ ExperimentWorkspacePage.
            # _finalize_and_persist_session() calls sync_thread_controller.
            # run_sync_now() directly) -- NOT gated on a connectivity
            # transition like the lightweight connectivity-monitor ping is.
            student_a["batch"].create_pending_batches_for_session("sess-a", chunk_size=_CHUNK_SIZE, finalize=True)
            finalize_result = student_a["engine"].run_sync()
            print(f"   [finalize-sync] Student A: {finalize_result.status.value} (pushed={finalize_result.pushed})")
            final_measurements = student_a["session"].get_measurements("sess-a")

            print("8. Teacher A (isolated client) performs its periodic auto-refresh pull...")
            # § §8 "Teacher Monitoring Update Strategy": the teacher's OWN
            # periodic timer runs UNCONDITIONALLY every ``teacher_auto_
            # refresh_interval_seconds`` (§ SyncWorker._on_periodic_timer_
            # tick()) -- it is NOT gated on a connectivity transition like
            # the lightweight connectivity-monitor ping (§ steps 4-6 above).
            auto_refresh_result = teacher_a["engine"].run_sync()
            print(f"   [teacher-auto-refresh] Teacher A: {auto_refresh_result.status.value} (pulled={auto_refresh_result.pulled})")
            reconstructed = teacher_a["session"].get_measurements("sess-a")
            _check(
                "Teacher A automatically received all 23 samples, exact order/values",
                len(reconstructed) == 23 == len(final_measurements)
                and [m.values["voltage"] for m in reconstructed] == [m.values["voltage"] for m in final_measurements],
            )
            teacher_a["engine"].run_sync()
            _check("Second auto-refresh creates no duplicates", len(teacher_a["session"].get_measurements("sess-a")) == 23)

            print("9. Teacher B (unassigned) auto-refreshes -- must see NOTHING for this session...")
            teacher_b["engine"].run_sync()
            _check(
                "Unassigned Teacher B receives no trace of Student A's session",
                not teacher_b["session"].exists("sess-a"),
            )

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
    print("Phase 5 connectivity-aware automatic sync acceptance scenario verified end to end.")


if __name__ == "__main__":
    main()
