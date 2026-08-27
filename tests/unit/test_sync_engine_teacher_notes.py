"""SyncEngine ↔ teacher_note wiring тесттері (Phase 7: Teacher Actions,
Feedback Delivery, and Session History) — push/pull/offline/pending-
count/remote-apply-never-re-enqueues, ``test_sync_engine_measurement_
batches.py``-дегі паттернмен БІРДЕЙ, ЕШБІР нақты HTTP/желі."""

from datetime import datetime, timezone

import pytest

from domain.entities.sync_state import SyncState
from domain.entities.sync_status import SyncStatus
from domain.entities.teacher_note import TeacherNote
from domain.entities.user_role import UserRole
from domain.interfaces.i_sync_api_client import AuthResult, ISyncApiClient, PullResult, PushItemResult
from domain.services.sync_engine import SyncEngine
from domain.services.sync_payload import ENTITY_TYPE_TEACHER_NOTE, PUSH_ORDER
from infrastructure.storage.sqlite_classroom_repository import SqliteClassroomRepository
from infrastructure.storage.sqlite_student_repository import SqliteStudentRepository
from infrastructure.storage.sqlite_sync_outbox_repository import SqliteSyncOutboxRepository
from infrastructure.storage.sqlite_teacher_note_repository import SqliteTeacherNoteRepository
from infrastructure.storage.sqlite_teacher_repository import SqliteTeacherRepository

_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


class FakeSyncApiClient(ISyncApiClient):
    def __init__(self, healthy: bool = True) -> None:
        self.healthy = healthy
        self.push_calls: list[tuple[str, list[dict]]] = []
        self.pull_calls: list[str] = []
        self._push_error_for: dict[str, Exception] = {}
        self._pull_items_for: dict[str, tuple[dict, ...]] = {}

    def set_push_error(self, entity_type: str, error: Exception) -> None:
        self._push_error_for[entity_type] = error

    def set_pull_items(self, entity_type: str, items: tuple[dict, ...]) -> None:
        self._pull_items_for[entity_type] = items

    def check_health(self) -> bool:
        return self.healthy

    def set_auth_token(self, token: str | None) -> None:
        pass

    def login_as_teacher(self, sync_id: str, pin_hash: str) -> AuthResult | None:
        return AuthResult(token="fake", expires_at=_NOW, sync_id=sync_id, role="teacher")

    def login_as_student(self, sync_id: str, student_code: str) -> AuthResult | None:
        return AuthResult(token="fake", expires_at=_NOW, sync_id=sync_id, role="student")

    def push(self, entity_type: str, payloads: list[dict]) -> list[PushItemResult]:
        self.push_calls.append((entity_type, payloads))
        if entity_type in self._push_error_for:
            raise self._push_error_for[entity_type]
        return [
            PushItemResult(sync_id=payload["sync_id"], status="upserted", server_revision=1)
            for payload in payloads
        ]

    def pull(self, entity_type: str, updated_since, limit: int) -> PullResult:
        self.pull_calls.append(entity_type)
        return PullResult(items=self._pull_items_for.get(entity_type, ()), server_time=_NOW)


@pytest.fixture()
def engine_setup(tmp_path):
    db_path = str(tmp_path / "device.db")
    outbox = SqliteSyncOutboxRepository(db_path)
    classroom_repo = SqliteClassroomRepository(db_path, sync_outbox_repository=outbox)
    student_repo = SqliteStudentRepository(db_path, sync_outbox_repository=outbox)
    teacher_repo = SqliteTeacherRepository(db_path, sync_outbox_repository=outbox)
    note_repo = SqliteTeacherNoteRepository(db_path, sync_outbox_repository=outbox)
    api_client = FakeSyncApiClient()
    cursors: dict[str, datetime] = {}

    engine = SyncEngine(
        classroom_repo, student_repo, teacher_repo, outbox, api_client,
        get_pull_cursor=lambda entity_type: cursors.get(entity_type),
        set_pull_cursor=lambda entity_type, value: cursors.__setitem__(entity_type, value),
        teacher_note_repository=note_repo,
    )
    return engine, note_repo, outbox, api_client


def test_teacher_note_is_in_push_order() -> None:
    assert ENTITY_TYPE_TEACHER_NOTE in PUSH_ORDER


def test_successful_push_marks_note_synced_and_clears_outbox(engine_setup) -> None:
    engine, note_repo, outbox, api_client = engine_setup
    note_repo.create(
        TeacherNote(id="note1", teacher_id="t1", student_id="s1", classroom_id="c1",
                    message="Өлшеуді қайта тексер", created_at=_NOW),
        UserRole.TEACHER,
    )

    result = engine.run_sync(now=_NOW)

    assert result.status is SyncStatus.SYNCED
    notes = note_repo.list_for_student("s1")
    assert notes[0].sync_state == SyncState.SYNCED
    assert outbox.count_pending() == 0
    note_calls = [call for call in api_client.push_calls if call[0] == ENTITY_TYPE_TEACHER_NOTE]
    assert len(note_calls) == 1
    assert note_calls[0][1][0]["message"] == "Өлшеуді қайта тексер"


def test_offline_server_never_pushes_notes(engine_setup) -> None:
    engine, note_repo, outbox, api_client = engine_setup
    api_client.healthy = False
    note_repo.create(
        TeacherNote(id="note1", teacher_id="t1", student_id="s1", classroom_id="c1",
                    message="Хабарлама", created_at=_NOW),
        UserRole.TEACHER,
    )

    result = engine.run_sync(now=_NOW)

    assert result.status is SyncStatus.OFFLINE
    assert api_client.push_calls == []
    assert len(note_repo.list_for_student("s1")) == 1  # § жергілікті жазба сақталды
    assert outbox.count_pending() == 1


def test_push_failure_keeps_note_pending_for_retry(engine_setup) -> None:
    engine, note_repo, outbox, api_client = engine_setup
    note_repo.create(
        TeacherNote(id="note1", teacher_id="t1", student_id="s1", classroom_id="c1",
                    message="Хабарлама", created_at=_NOW),
        UserRole.TEACHER,
    )
    api_client.set_push_error(ENTITY_TYPE_TEACHER_NOTE, ConnectionError("no route to host"))

    result = engine.run_sync(now=_NOW)

    assert result.status is SyncStatus.SYNC_ERROR
    notes = note_repo.list_for_student("s1")
    assert notes[0].sync_state == SyncState.PENDING_UPLOAD
    assert outbox.count_pending() == 1


def test_pending_note_syncs_after_retry_succeeds(engine_setup) -> None:
    engine, note_repo, outbox, api_client = engine_setup
    note_repo.create(
        TeacherNote(id="note1", teacher_id="t1", student_id="s1", classroom_id="c1",
                    message="Хабарлама", created_at=_NOW),
        UserRole.TEACHER,
    )
    api_client.set_push_error(ENTITY_TYPE_TEACHER_NOTE, ConnectionError("no route to host"))
    engine.run_sync(now=_NOW)

    api_client._push_error_for.clear()
    later = datetime(2026, 1, 1, 1, tzinfo=timezone.utc)
    result = engine.run_sync(now=later)

    assert result.status is SyncStatus.SYNCED
    assert outbox.count_pending() == 0


def test_pull_applies_remote_note_without_reenqueueing(engine_setup) -> None:
    engine, note_repo, outbox, api_client = engine_setup
    remote_note_payload = {
        "sync_id": "remote-note-1", "teacher_sync_id": "t1", "student_sync_id": "s1",
        "classroom_sync_id": "c1", "experiment_id": "ohms-law", "session_sync_id": None,
        "message": "Кернеу мәніне назар аудар", "created_at": _NOW.isoformat(), "server_revision": 1,
    }
    api_client.set_pull_items(ENTITY_TYPE_TEACHER_NOTE, (remote_note_payload,))
    pending_before = outbox.count_pending()

    result = engine.run_sync(now=_NOW)

    assert result.status is SyncStatus.SYNCED
    notes = note_repo.list_for_student("s1")
    assert len(notes) == 1
    assert notes[0].message == "Кернеу мәніне назар аудар"
    assert notes[0].sync_state == SyncState.SYNCED
    assert outbox.count_pending() == pending_before  # § ЕШБІР жаңа push job


def test_repeated_pull_does_not_duplicate_notes(engine_setup) -> None:
    engine, note_repo, outbox, api_client = engine_setup
    remote_note_payload = {
        "sync_id": "remote-note-1", "teacher_sync_id": "t1", "student_sync_id": "s1",
        "classroom_sync_id": "c1", "experiment_id": None, "session_sync_id": None,
        "message": "Хабарлама", "created_at": _NOW.isoformat(), "server_revision": 1,
    }
    api_client.set_pull_items(ENTITY_TYPE_TEACHER_NOTE, (remote_note_payload,))

    engine.run_sync(now=_NOW)
    engine.run_sync(now=_NOW)

    assert len(note_repo.list_for_student("s1")) == 1
