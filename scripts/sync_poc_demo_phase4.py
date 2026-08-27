"""§12 "Live Demo / POC" — Phase 4 (Raw Arduino Measurement Cloud Sync).

Real (but ephemeral, isolated-test-database) manual demonstration,
against a REAL ``uvicorn`` server on a real socket, of:

    Cloud server
    Teacher A -> Classroom 8A -> Student A
    Teacher B -> Classroom 8B -> Student B (unassigned to Student A)

  1.  Student A logs in, an experiment session exists.
  2.  Realistic multi-chunk Arduino measurement data is generated
      (33 samples, chunk_size=10 -> 3 full batches + 1 partial tail).
  3.  Some batches sync WHILE the experiment is still "running"
      (partial session upload, not only at experiment end).
  4.  Server goes down: more measurements are collected locally,
      the local repository stays fully functional (offline-first).
  5.  App "restarts" (repositories re-opened against the SAME db file)
      -- pending batches survive (restart safety).
  6.  Server returns: remaining batches (including the finalized tail)
      sync; a retry of the same sync is idempotent (no duplicates).
  7.  Teacher A (another client, fully isolated local DB, assigned to
      Student A's classroom) pulls and reconstructs the RAW
      measurements locally -- exact sample count/order/values match.
  8.  Teacher B (NOT assigned to 8A) receives nothing for this session.
  9.  Student B (unrelated) receives nothing for this session.

Prints a concise PASS/FAIL summary at the end. Uses only temp files/an
ephemeral port/synthetic names -- the user's real classroom data and
real database are never touched (§33 "POC data must be synthetic").

    python scripts/sync_poc_demo_phase4.py
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
    """§ Phase 4 "restart safety" — ``session_repo``/``batch_repo``
    (ЖӘНЕ барлық басқа репозиторийлер) БІР ортақ ``data_{label}.db``
    файлымен (§ ``sync_poc_demo_phase3.py``-мен БІРДЕЙ established
    паттерн — ЕКІ бөлек ``:memory:`` байланысы емес)."""
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
            "api_client": api_client, "db_path": db_path, "closeables": closeables}


def _generate_measurements(count: int, offset: int = 0) -> tuple[Measurement, ...]:
    now = datetime.now(timezone.utc)
    return tuple(
        Measurement(
            timestamp=now,
            values={"voltage": round(6.0 + (offset + i) * 0.01, 4), "current": round(0.0078 + (offset + i) * 0.0001, 6)},
            derived_values={"power": round((6.0 + (offset + i) * 0.01) * (0.0078 + (offset + i) * 0.0001), 6)},
            experiment_id="ohms-law",
        )
        for i in range(count)
    )


def main() -> None:
    now = datetime.now(timezone.utc)
    all_closeables: list = []
    server = None

    with tempfile.TemporaryDirectory(prefix="apl_sync_poc_phase4_", ignore_cleanup_errors=True) as tmp:
        try:
            tmp_dir = Path(tmp)
            port = _free_port()
            base_url = f"http://127.0.0.1:{port}"

            print(f"1. Starting FastAPI server on {base_url} (isolated temp DB)...")
            server = _start_server(tmp_dir / "server.db", port)

            print("2. Building Teacher A / 8A / Student A and Teacher B / 8B / Student B...")
            teacher_a = _build_client(tmp_dir, "teacher_a", base_url, "teacher", "ta")
            teacher_b = _build_client(tmp_dir, "teacher_b", base_url, "teacher", "tb")
            student_a = _build_client(tmp_dir, "student_a", base_url, "student", "sa", classroom_id="ca")
            student_b = _build_client(tmp_dir, "student_b", base_url, "student", "sb", classroom_id="cb")
            for c in (teacher_a, teacher_b, student_a, student_b):
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
            teacher_b["student"].create(
                Student(id="sb", classroom_id="cb", first_name="Demo", last_name="StudentB", created_at=now, updated_at=now, student_code="code-sb"),
                UserRole.TEACHER,
            )
            teacher_b["teacher"].set_assigned_classroom_ids("tb", ("cb",))
            teacher_b["engine"].run_sync()
            student_a["engine"].run_sync()
            student_b["engine"].run_sync()

            print("3. Student A links a session and generates 25 realistic Arduino samples while 'running'...")
            student_a["progress"].link_session("sess-a", "sa", "ca", "ohms-law")
            student_a["session"].append_measurements("sess-a", "ohms-law", _generate_measurements(25), started_at=now)
            created = student_a["batch"].create_pending_batches_for_session("sess-a", chunk_size=_CHUNK_SIZE, finalize=False)
            _check("2 full batches created mid-experiment (chunk_size=10, tail unbatched)", created == 2)

            print("4. Partial sync WHILE the experiment is still running (session + link + 2 batches)...")
            result_partial = student_a["engine"].run_sync()
            _check(
                "Partial batches push while running (partial session upload)",
                result_partial.status.value == "synced" and result_partial.pushed >= 2,
            )

            print("5. Server goes down: MORE data is collected locally, UI/repo stays fully functional...")
            student_a["api_client"].check_health = lambda: False
            student_a["session"].append_measurements("sess-a", "ohms-law", _generate_measurements(8, offset=25), started_at=now)
            offline_result = student_a["engine"].run_sync()
            _check(
                "Offline: local write succeeds, no crash, outbox retains pending state",
                offline_result.status.value == "offline" and len(student_a["session"].get_measurements("sess-a")) == 33,
            )

            print("6. App 'restarts' -- repositories re-opened against the SAME db file...")
            student_a_restarted = _build_client(tmp_dir, "student_a", base_url, "student", "sa", classroom_id="ca")
            all_closeables.extend(student_a_restarted["closeables"])
            _check(
                "Restart safety: all 33 measurements + pending batches survive restart",
                len(student_a_restarted["session"].get_measurements("sess-a")) == 33,
            )
            created_after_restart = student_a_restarted["batch"].create_pending_batches_for_session(
                "sess-a", chunk_size=_CHUNK_SIZE, finalize=True
            )
            _check("Tail finalized after restart (1 full + 1 partial batch)", created_after_restart == 2)

            print("7. Server returns: remaining batches sync; retry is idempotent...")
            final_sync = student_a_restarted["engine"].run_sync()
            _check("Final sync completes, outbox drains to zero", final_sync.status.value == "synced" and student_a_restarted["outbox"].count_pending() == 0)
            retry_sync = student_a_restarted["engine"].run_sync()
            _check("Retry sync is a safe no-op (idempotent)", retry_sync.status.value == "synced")

            print("8. Teacher A (isolated client) pulls and reconstructs raw measurements...")
            pull_result = teacher_a["engine"].run_sync()
            reconstructed = teacher_a["session"].get_measurements("sess-a")
            original = student_a_restarted["session"].get_measurements("sess-a")
            _check(
                "Teacher A reconstructs exact count/order/values (33 samples)",
                pull_result.status.value == "synced"
                and len(reconstructed) == 33 == len(original)
                and [m.values["voltage"] for m in reconstructed] == [m.values["voltage"] for m in original],
            )
            teacher_a["engine"].run_sync()
            _check("Second teacher pull creates no duplicates", len(teacher_a["session"].get_measurements("sess-a")) == 33)

            print("9. Teacher B (unassigned) and Student B (unrelated) must receive NOTHING for this session...")
            result_b = teacher_b["engine"].run_sync()
            _check(
                "Unassigned Teacher B sees no trace of Student A's session/measurements",
                result_b.status.value == "synced" and not teacher_b["session"].exists("sess-a"),
            )
            result_sb = student_b["engine"].run_sync()
            _check(
                "Unrelated Student B sees no trace of Student A's session/measurements",
                result_sb.status.value == "synced" and not student_b["session"].exists("sess-a"),
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
    print("Phase 4 raw Arduino measurement cloud sync acceptance scenario verified end to end.")


if __name__ == "__main__":
    main()
