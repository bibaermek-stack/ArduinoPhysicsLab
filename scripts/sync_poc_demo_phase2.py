"""§37 "Live Local-Server Demo" / §41 "Final Acceptance Scenario" —
Phase 2 (Experiment Session + Results + Feedback Cloud Sync).

Real (but ephemeral, isolated-test-database) manual demonstration,
against a REAL ``uvicorn`` server on a real socket, of:

  A. initial teacher/class/student sync
  B. Student client creates/submits a synthetic experiment session/result
  C. Teacher client pulls and sees the submission (via EXISTING
     IStudentProgressRepository/IFeedbackRepository abstractions)
  D. Teacher reviews with score + Kazakh comment
  E. Student pulls and sees the teacher assessment
  F. stop server
  G. Student submits another result offline
  H. app remains fully functional offline
  I. restart server
  J. pending record syncs
  K. teacher receives it

Prints a concise PASS/FAIL summary at the end. Uses only temp files/an
ephemeral port/synthetic names — the user's real classroom data and
real database are never touched (§33 "POC data must be synthetic").

    python scripts/sync_poc_demo_phase2.py
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

_checks: list[tuple[str, bool, str]] = []


def _check(name: str, condition: bool, detail: str = "") -> None:
    _checks.append((name, condition, detail))
    mark = "PASS" if condition else "FAIL"
    print(f"   [{mark}] {name}" + (f" ({detail})" if detail else ""))


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _start_server(db_path: Path, port: int) -> uvicorn.Server:
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    config = uvicorn.Config(fastapi_app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    return server


def _build_client(db_dir: Path, label: str, base_url: str) -> dict:
    outbox = SqliteSyncOutboxRepository(db_dir / f"outbox_{label}.db")
    classroom_repo = SqliteClassroomRepository(db_dir / f"data_{label}.db", sync_outbox_repository=outbox)
    student_repo = SqliteStudentRepository(db_dir / f"data_{label}.db", sync_outbox_repository=outbox)
    teacher_repo = SqliteTeacherRepository(db_dir / f"data_{label}.db", sync_outbox_repository=outbox)
    session_repo = SqliteSessionRepository(db_dir / f"data_{label}.db", sync_outbox_repository=outbox)
    feedback_repo = SqliteFeedbackRepository(db_dir / f"data_{label}.db", sync_outbox_repository=outbox)
    progress_repo = SqliteStudentProgressRepository(
        db_dir / f"data_{label}.db",
        session_repository=session_repo,
        feedback_repository=feedback_repo,
        classroom_repository=classroom_repo,
        student_repository=student_repo,
        sync_outbox_repository=outbox,
    )
    api_client = HttpSyncApiClient(base_url=base_url, api_key=_API_KEY)
    cursors: dict[str, datetime] = {}
    engine = SyncEngine(
        classroom_repo, student_repo, teacher_repo, outbox, api_client,
        get_pull_cursor=lambda entity_type: cursors.get(entity_type),
        set_pull_cursor=lambda entity_type, value: cursors.__setitem__(entity_type, value),
        session_repository=session_repo,
        student_progress_repository=progress_repo,
        feedback_repository=feedback_repo,
    )
    return {
        "engine": engine, "classroom": classroom_repo, "student": student_repo, "teacher": teacher_repo,
        "session": session_repo, "feedback": feedback_repo, "progress": progress_repo, "outbox": outbox,
        "api_client": api_client,
        "closeables": (classroom_repo, student_repo, teacher_repo, session_repo, feedback_repo, progress_repo, outbox),
    }


def main() -> None:
    now = datetime.now(timezone.utc)
    all_closeables: list = []
    server = None

    with tempfile.TemporaryDirectory(prefix="apl_sync_poc_phase2_", ignore_cleanup_errors=True) as tmp:
        try:
            tmp_dir = Path(tmp)
            port = _free_port()
            base_url = f"http://127.0.0.1:{port}"

            print(f"1. Starting FastAPI server on {base_url} (isolated temp DB)...")
            server = _start_server(tmp_dir / "server.db", port)

            print("A. Seeding + syncing shared Teacher/Classroom/Student...")
            student_pc = _build_client(tmp_dir, "student", base_url)
            teacher_pc = _build_client(tmp_dir, "teacher", base_url)
            all_closeables.extend(student_pc["closeables"])
            all_closeables.extend(teacher_pc["closeables"])

            student_pc["classroom"].create(
                Classroom(id="demo-c1", name="Demo 8A", created_at=now, updated_at=now), UserRole.TEACHER
            )
            student_pc["student"].create(
                Student(
                    id="demo-s1", classroom_id="demo-c1", first_name="Demo", last_name="Student",
                    created_at=now, updated_at=now, student_code="000001",
                ),
                UserRole.TEACHER,
            )
            student_pc["teacher"].create(
                Teacher(id="demo-t1", full_name="Demo Teacher", pin_hash=hash_pin("135790"), created_at=now, updated_at=now),
                assigned_classroom_ids=("demo-c1",),
            )
            student_pc["engine"].run_sync()
            teacher_pc["engine"].run_sync()
            _check(
                "A. shared roster synced to teacher PC",
                teacher_pc["student"].get("demo-s1") is not None,
            )

            print("B. Student client: submitting a synthetic experiment result...")
            student_pc["progress"].link_session("demo-sess1", "demo-s1", "demo-c1", "ohms-law")
            student_pc["session"].save_session(
                ExperimentSession(
                    id="demo-sess1", experiment_id="ohms-law", started_at=now, ended_at=now,
                    measurements=[Measurement(timestamp=now, values={"voltage": 3.3}, experiment_id="ohms-law")],
                )
            )
            student_pc["feedback"].save_submission(
                ExperimentFeedbackResult(
                    experiment_id="ohms-law", session_id="demo-sess1",
                    level3_answers=(ReflectionAnswer(question_id="r1", response_text="Синтетикалық қорытынды"),),
                    submitted_at=now,
                )
            )
            result_b = student_pc["engine"].run_sync()
            _check("B. student submission synced", result_b.status.value == "synced" and result_b.pushed == 3)

            print("C. Teacher client: pulling and discovering the submission via existing repos...")
            result_c = teacher_pc["engine"].run_sync()
            progress = teacher_pc["progress"].get_progress("demo-s1", "ohms-law")
            _check(
                "C. teacher discovers FEEDBACK_SUBMITTED via IStudentProgressRepository",
                result_c.status.value == "synced" and progress.status.name == "FEEDBACK_SUBMITTED",
            )

            print("D. Teacher: reviewing with score 9/10 + Kazakh comment...")
            teacher_pc["feedback"].save_teacher_assessment(
                "demo-sess1", "ohms-law",
                TeacherAssessment(score=9, comment="Өте жақсы орындалған жұмыс"),
                UserRole.TEACHER,
            )
            result_d = teacher_pc["engine"].run_sync()
            _check("D. teacher assessment synced", result_d.status.value == "synced" and result_d.pushed == 1)

            print("E. Student client: pulling and seeing the reviewed result...")
            result_e = student_pc["engine"].run_sync()
            final_result = student_pc["feedback"].get_result("demo-sess1")
            final_progress = student_pc["progress"].get_progress("demo-s1", "ohms-law")
            _check(
                "E. student sees Reviewed / 9 / comment",
                result_e.status.value == "synced"
                and final_result.teacher_assessment is not None
                and final_result.teacher_assessment.score == 9
                and final_progress.status.name == "REVIEWED",
            )

            print("F. Stopping the server...")
            server.should_exit = True
            time.sleep(0.5)

            print("G. Student submits ANOTHER result while the server is down...")
            student_pc["progress"].link_session("demo-sess2", "demo-s1", "demo-c1", "ohms-law")
            student_pc["session"].save_session(
                ExperimentSession(
                    id="demo-sess2", experiment_id="ohms-law", started_at=now, ended_at=now,
                    measurements=[Measurement(timestamp=now, values={"voltage": 4.1}, experiment_id="ohms-law")],
                )
            )
            student_pc["feedback"].save_submission(
                ExperimentFeedbackResult(experiment_id="ohms-law", session_id="demo-sess2", submitted_at=now)
            )
            offline_result = student_pc["engine"].run_sync()
            _check(
                "H. app remains fully functional offline (local save + offline status)",
                offline_result.status.value == "offline" and student_pc["session"].exists("demo-sess2"),
            )

            print("I. Restarting the server...")
            server = _start_server(tmp_dir / "server.db", port)

            print("J. Student re-syncs the pending record...")
            result_j = student_pc["engine"].run_sync()
            _check("J. pending session/link/feedback synced", result_j.status.value == "synced" and result_j.pushed == 3)

            print("K. Teacher receives the second submission...")
            teacher_pc["engine"].run_sync()
            second_progress = teacher_pc["progress"].get_progress("demo-s1", "ohms-law")
            second_result = teacher_pc["session"].get_session("demo-sess2")
            _check("K. teacher pulls the second session", second_result is not None)

            server.should_exit = True
            time.sleep(0.3)
        finally:
            for closeable in all_closeables:
                closeable.close()
            if server is not None:
                server.should_exit = True
                time.sleep(0.2)

    print("\n" + "=" * 60)
    passed = sum(1 for _, ok, _ in _checks if ok)
    print(f"PASS/FAIL SUMMARY: {passed}/{len(_checks)} checks passed")
    for name, ok, detail in _checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    print("=" * 60)

    if passed != len(_checks):
        sys.exit(1)
    print("Phase 2 acceptance scenario verified end to end.")


if __name__ == "__main__":
    main()
