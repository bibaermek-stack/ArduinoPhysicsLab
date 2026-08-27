"""§12 "Live Demo / POC" — Phase 3 (Production Authentication +
Authorization).

Real (but ephemeral, isolated-test-database) manual demonstration,
against a REAL ``uvicorn`` server on a real socket, of:

    Cloud server
    Teacher A -> Classroom 8A -> Student A
    Teacher B -> Classroom 8B -> Student B

  1. Student A logs in (JWT), submits a synthetic result, syncs.
  2. Teacher A logs in on another client, receives Student A's result,
     grades it, syncs.
  3. Student A receives Teacher A's assessment.
  4. Teacher B must NOT receive Student A's private experiment data.
  5. Stop the server: Student A performs a local action, succeeds
     offline, outbox retains the pending operation.
  6. Restart the server: authentication is restored, sync completes.

Prints a concise PASS/FAIL summary at the end. Uses only temp files/an
ephemeral port/synthetic names — the user's real classroom data and
real database are never touched (§33 "POC data must be synthetic").

    python scripts/sync_poc_demo_phase3.py
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
from domain.entities.experiment_feedback_result import (  # noqa: E402
    ExperimentFeedbackResult,
    ReflectionAnswer,
    TeacherAssessment,
)
from domain.entities.experiment_session import ExperimentSession  # noqa: E402
from domain.entities.measurement import Measurement  # noqa: E402
from domain.entities.student import Student  # noqa: E402
from domain.entities.teacher import Teacher  # noqa: E402
from domain.entities.user_role import UserRole  # noqa: E402
from domain.services.sync_engine import SyncEngine  # noqa: E402
from domain.services.teacher_pin import hash_pin  # noqa: E402
from infrastructure.storage.sqlite_classroom_repository import SqliteClassroomRepository  # noqa: E402
from infrastructure.storage.sqlite_feedback_repository import SqliteFeedbackRepository  # noqa: E402
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
    outbox = SqliteSyncOutboxRepository(db_dir / f"outbox_{label}.db")
    classroom_repo = SqliteClassroomRepository(db_dir / f"data_{label}.db", sync_outbox_repository=outbox)
    student_repo = SqliteStudentRepository(db_dir / f"data_{label}.db", sync_outbox_repository=outbox)
    teacher_repo = SqliteTeacherRepository(db_dir / f"data_{label}.db", sync_outbox_repository=outbox)
    session_repo = SqliteSessionRepository(db_dir / f"data_{label}.db", sync_outbox_repository=outbox)
    feedback_repo = SqliteFeedbackRepository(db_dir / f"data_{label}.db", sync_outbox_repository=outbox)
    progress_repo = SqliteStudentProgressRepository(
        db_dir / f"data_{label}.db", session_repository=session_repo, feedback_repository=feedback_repo,
        classroom_repository=classroom_repo, student_repository=student_repo, sync_outbox_repository=outbox,
    )
    # § "AS IF the human had already entered their PIN/access code
    # locally" — ЖЕРГІЛІКТІ credential алдын ала белгілі, apply_remote_
    # upsert() арқылы ЕШБІР outbox жазуынсыз (§ TOFU bootstrap-қа сай).
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
        session_repository=session_repo, student_progress_repository=progress_repo,
        feedback_repository=feedback_repo,
        get_active_role_and_sync_id=lambda: (role, sync_id),
        get_cached_token=lambda: token_cache.get("token"),
        set_cached_token=lambda token, expires_at, r, s: token_cache.__setitem__("token", (token, expires_at, r, s)),
    )
    closeables = (classroom_repo, student_repo, teacher_repo, session_repo, feedback_repo, progress_repo, outbox)
    return {"engine": engine, "classroom": classroom_repo, "student": student_repo, "teacher": teacher_repo,
            "session": session_repo, "feedback": feedback_repo, "progress": progress_repo, "outbox": outbox,
            "closeables": closeables}


def main() -> None:
    now = datetime.now(timezone.utc)
    all_closeables: list = []
    server = None

    with tempfile.TemporaryDirectory(prefix="apl_sync_poc_phase3_", ignore_cleanup_errors=True) as tmp:
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
            _check("Teacher A seeds+syncs 8A/Student A (authenticated)", result_a_seed.status.value == "synced")

            teacher_b["classroom"].create(Classroom(id="cb", name="Demo 8B", created_at=now, updated_at=now), UserRole.TEACHER)
            teacher_b["student"].create(
                Student(id="sb", classroom_id="cb", first_name="Demo", last_name="StudentB", created_at=now, updated_at=now, student_code="code-sb"),
                UserRole.TEACHER,
            )
            teacher_b["teacher"].set_assigned_classroom_ids("tb", ("cb",))
            teacher_b["engine"].run_sync()

            student_a["engine"].run_sync()
            student_b["engine"].run_sync()

            print("3. Student A logs in, submits a synthetic experiment result, syncs...")
            student_a["progress"].link_session("sess-a", "sa", "ca", "ohms-law")
            student_a["session"].save_session(
                ExperimentSession(id="sess-a", experiment_id="ohms-law", started_at=now, ended_at=now,
                                   measurements=[Measurement(timestamp=now, values={"voltage": 3.3}, experiment_id="ohms-law")])
            )
            student_a["feedback"].save_submission(
                ExperimentFeedbackResult(experiment_id="ohms-law", session_id="sess-a",
                                          level3_answers=(ReflectionAnswer(question_id="r1", response_text="Синтетикалық қорытынды"),),
                                          submitted_at=now)
            )
            result_submit = student_a["engine"].run_sync()
            _check("Student A submission synced (authenticated push)", result_submit.status.value == "synced")

            print("4. Teacher A (another client) pulls, sees the submission, grades it, syncs...")
            result_teacher_pull = teacher_a["engine"].run_sync()
            progress = teacher_a["progress"].get_progress("sa", "ohms-law")
            _check(
                "Teacher A discovers submission via existing repos",
                result_teacher_pull.status.value == "synced" and progress.status.name == "FEEDBACK_SUBMITTED",
            )
            teacher_a["feedback"].save_teacher_assessment(
                "sess-a", "ohms-law", TeacherAssessment(score=9, comment="Өте жақсы орындалған жұмыс"), UserRole.TEACHER
            )
            result_grade = teacher_a["engine"].run_sync()
            _check("Teacher A grade synced", result_grade.status.value == "synced")

            print("5. Student A pulls, receives Teacher A's assessment...")
            result_student_pull = student_a["engine"].run_sync()
            final = student_a["feedback"].get_result("sess-a")
            _check(
                "Student A sees Reviewed / 9 / comment",
                result_student_pull.status.value == "synced"
                and final.teacher_assessment is not None
                and final.teacher_assessment.score == 9,
            )

            print("6. Teacher B syncs -- must NOT receive Student A's private data...")
            result_teacher_b = teacher_b["engine"].run_sync()
            _check(
                "Teacher B receives NO trace of Student A's session/feedback/classroom",
                result_teacher_b.status.value == "synced"
                and not teacher_b["session"].exists("sess-a")
                and teacher_b["feedback"].get_result("sess-a") is None
                and teacher_b["student"].get("sa") is None
                and teacher_b["classroom"].get("ca") is None,
            )

            print("7. Stopping the server...")
            server.should_exit = True
            time.sleep(0.5)

            print("8. Student A performs another local action while the server is down...")
            student_a["progress"].link_session("sess-a2", "sa", "ca", "ohms-law")
            student_a["session"].save_session(
                ExperimentSession(id="sess-a2", experiment_id="ohms-law", started_at=now, ended_at=now,
                                   measurements=[Measurement(timestamp=now, values={"voltage": 4.0}, experiment_id="ohms-law")])
            )
            offline_result = student_a["engine"].run_sync()
            _check(
                "Offline local write succeeds, outbox retains pending operation",
                offline_result.status.value == "offline" and student_a["outbox"].count_pending() > 0,
            )

            print("9. Restarting the server -- authentication restored, sync completes...")
            server = _start_server(tmp_dir / "server.db", port)
            result_reconnect = student_a["engine"].run_sync()
            _check(
                "Reconnect: authentication restored, pending sync completes",
                result_reconnect.status.value == "synced" and student_a["outbox"].count_pending() == 0,
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
    print("Phase 3 authentication + authorization acceptance scenario verified end to end.")


if __name__ == "__main__":
    main()
