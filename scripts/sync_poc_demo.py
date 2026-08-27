"""§30 "Manual Demo" — Offline-First + Cloud Sync Foundation Phase 1.

Real (but ephemeral, isolated-test-database) manual demonstration of the
two-client sync round trip, using a REAL ``uvicorn`` server on a real
socket (unlike ``tests/integration/test_sync_poc_two_clients.py``, which
uses an in-process ``TestClient`` for speed). Run directly:

    python scripts/sync_poc_demo.py

Everything here uses temp files/an ephemeral port — the user's real
classroom data and real database are never touched (§ "Do not use the
user's real classroom data for this demo").

Steps performed (matching §30 exactly):
  1. Start local FastAPI server (isolated temp SQLite file).
  2. Start "Client A" (separate temp SQLite file), create a test
     classroom + student, sync.
  3. Start "Client B" (separate temp SQLite file), sync, confirm the
     same data arrived.
  4. Stop the server, edit local data on Client A, confirm the app
     (i.e. the local repository) still works fully offline.
  5. Restart the server, sync Client A then Client B again, confirm the
     pending change reaches the server and then Client B.
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
from domain.entities.student import Student  # noqa: E402
from domain.entities.user_role import UserRole  # noqa: E402
from domain.services.sync_engine import SyncEngine  # noqa: E402
from infrastructure.storage.sqlite_classroom_repository import SqliteClassroomRepository  # noqa: E402
from infrastructure.storage.sqlite_student_repository import SqliteStudentRepository  # noqa: E402
from infrastructure.storage.sqlite_sync_outbox_repository import SqliteSyncOutboxRepository  # noqa: E402
from infrastructure.storage.sqlite_teacher_repository import SqliteTeacherRepository  # noqa: E402
from infrastructure.sync.http_sync_api_client import HttpSyncApiClient  # noqa: E402
from server.app.main import app as fastapi_app  # noqa: E402

_API_KEY = "dev-local-only-key"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _start_server(db_path: Path, port: int) -> uvicorn.Server:
    # § db/session.py::get_session_factory() lazily creates + caches ONE
    # engine per process on first use (Base.metadata.create_all() runs
    # inside create_session_factory() itself) — setting DATABASE_URL
    # before the FIRST request is all that's needed; stopping/restarting
    # the uvicorn.Server object below (same process, same DATABASE_URL)
    # safely reuses that same cached engine/db file.
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"

    config = uvicorn.Config(fastapi_app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    return server


def _build_client(db_dir: Path, label: str, base_url: str):
    outbox = SqliteSyncOutboxRepository(db_dir / f"outbox_{label}.db")
    classroom_repo = SqliteClassroomRepository(db_dir / f"data_{label}.db", sync_outbox_repository=outbox)
    student_repo = SqliteStudentRepository(db_dir / f"data_{label}.db", sync_outbox_repository=outbox)
    teacher_repo = SqliteTeacherRepository(db_dir / f"data_{label}.db", sync_outbox_repository=outbox)
    api_client = HttpSyncApiClient(base_url=base_url, api_key=_API_KEY)
    cursors: dict[str, datetime] = {}
    engine = SyncEngine(
        classroom_repo, student_repo, teacher_repo, outbox, api_client,
        get_pull_cursor=lambda entity_type: cursors.get(entity_type),
        set_pull_cursor=lambda entity_type, value: cursors.__setitem__(entity_type, value),
    )
    closeables = (classroom_repo, student_repo, teacher_repo, outbox)
    return engine, classroom_repo, student_repo, teacher_repo, closeables


def main() -> None:
    now = datetime.now(timezone.utc)
    all_closeables: list = []
    server = None

    # ``ignore_cleanup_errors=True`` — Windows may keep a brief file lock
    # on the server-side SQLite file via the process-wide cached SQLAlchemy
    # engine (server/app/db/session.py) even after the uvicorn server
    # thread stops; this has no bearing on the sync round trip itself,
    # which has already been fully verified by the asserts above.
    with tempfile.TemporaryDirectory(prefix="apl_sync_poc_", ignore_cleanup_errors=True) as tmp:
        try:
            tmp_dir = Path(tmp)
            port = _free_port()
            base_url = f"http://127.0.0.1:{port}"

            print(f"1. Starting FastAPI server on {base_url} (isolated temp DB)...")
            server = _start_server(tmp_dir / "server.db", port)

            print("2. Client A: creating a test classroom + student...")
            engine_a, classroom_a, student_a, _, closeables_a = _build_client(tmp_dir, "A", base_url)
            all_closeables.extend(closeables_a)
            classroom_a.create(
                Classroom(id="demo-c1", name="Demo 8A", created_at=now, updated_at=now), UserRole.TEACHER
            )
            student_a.create(
                Student(
                    id="demo-s1", classroom_id="demo-c1", first_name="Demo", last_name="Student",
                    created_at=now, updated_at=now, student_code="000001",
                ),
                UserRole.TEACHER,
            )
            result_a = engine_a.run_sync()
            print(f"   Client A sync: {result_a.status.value}, pushed={result_a.pushed}")

            print("3. Client B: syncing, expecting the same records to arrive...")
            engine_b, classroom_b, _, _, closeables_b = _build_client(tmp_dir, "B", base_url)
            all_closeables.extend(closeables_b)
            result_b = engine_b.run_sync()
            pulled_classroom = classroom_b.get("demo-c1")
            print(f"   Client B sync: {result_b.status.value}, pulled={result_b.pulled}")
            print(f"   Client B sees classroom: {pulled_classroom.name if pulled_classroom else 'MISSING'}")
            assert pulled_classroom is not None and pulled_classroom.name == "Demo 8A"

            print("4. Stopping the server...")
            server.should_exit = True
            time.sleep(0.5)

            print("   Editing data on Client A while the server is down (must succeed locally)...")
            classroom_a.update(
                Classroom(
                    id="demo-c1", name="Demo 8A (offline edit)", created_at=now, updated_at=now, sync_id="demo-c1",
                ),
                UserRole.TEACHER,
            )
            assert classroom_a.get("demo-c1").name == "Demo 8A (offline edit)"
            print("   OK -- local write succeeded with the server down.")

            offline_result = engine_a.run_sync()
            print(f"   Client A sync while server is down: {offline_result.status.value} (expected: offline)")
            assert offline_result.status.value == "offline"

            print("5. Restarting the server and re-syncing both clients...")
            server = _start_server(tmp_dir / "server.db", port)
            result_a2 = engine_a.run_sync()
            print(f"   Client A sync: {result_a2.status.value}, pushed={result_a2.pushed}")
            result_b2 = engine_b.run_sync()
            print(f"   Client B sync: {result_b2.status.value}, pulled={result_b2.pulled}")
            final_classroom = classroom_b.get("demo-c1")
            print(f"   Client B now sees: {final_classroom.name}")
            assert final_classroom.name == "Demo 8A (offline edit)"

            server.should_exit = True
            time.sleep(0.3)

            print("\nDemo complete -- offline-first + cloud sync round trip verified end to end.")
        finally:
            for closeable in all_closeables:
                closeable.close()
            if server is not None:
                server.should_exit = True
                time.sleep(0.2)


if __name__ == "__main__":
    main()
