"""SqliteTeacherNoteRepository юнит-тесттері (Phase 7: Teacher Actions,
Feedback Delivery, and Session History)."""

from datetime import datetime, timezone

import pytest

from domain.entities.sync_state import SyncState
from domain.entities.teacher_note import TeacherNote
from domain.entities.user_role import UserRole
from infrastructure.storage.sqlite_sync_outbox_repository import SqliteSyncOutboxRepository
from infrastructure.storage.sqlite_teacher_note_repository import SqliteTeacherNoteRepository

_NOW = datetime.now(timezone.utc)


def _make_note(note_id: str = "note-1", **overrides) -> TeacherNote:
    fields = {
        "id": note_id,
        "teacher_id": "t1",
        "student_id": "s1",
        "classroom_id": "c1",
        "message": "Өлшеуді қайта тексер",
        "created_at": _NOW,
    }
    fields.update(overrides)
    return TeacherNote(**fields)


def test_create_requires_teacher_role() -> None:
    repo = SqliteTeacherNoteRepository()

    with pytest.raises(PermissionError):
        repo.create(_make_note(), UserRole.STUDENT)


def test_create_and_list_for_student() -> None:
    repo = SqliteTeacherNoteRepository()

    repo.create(_make_note(), UserRole.TEACHER)

    notes = repo.list_for_student("s1")
    assert len(notes) == 1
    assert notes[0].message == "Өлшеуді қайта тексер"
    assert notes[0].sync_state == SyncState.PENDING_UPLOAD
    assert notes[0].read_at is None


def test_list_for_student_only_returns_that_students_notes() -> None:
    repo = SqliteTeacherNoteRepository()
    repo.create(_make_note("note-1", student_id="s1"), UserRole.TEACHER)
    repo.create(_make_note("note-2", student_id="s2"), UserRole.TEACHER)

    notes_s1 = repo.list_for_student("s1")
    notes_s2 = repo.list_for_student("s2")

    assert [n.id for n in notes_s1] == ["note-1"]
    assert [n.id for n in notes_s2] == ["note-2"]


def test_list_for_student_orders_by_created_at() -> None:
    repo = SqliteTeacherNoteRepository()
    from datetime import timedelta

    repo.create(_make_note("later", created_at=_NOW), UserRole.TEACHER)
    repo.create(_make_note("earlier", created_at=_NOW - timedelta(minutes=5)), UserRole.TEACHER)

    notes = repo.list_for_student("s1")

    assert [n.id for n in notes] == ["earlier", "later"]


def test_list_for_student_same_created_at_uses_rowid() -> None:
    repo = SqliteTeacherNoteRepository()
    repo.create(_make_note("n1", created_at=_NOW), UserRole.TEACHER)
    repo.create(_make_note("n2", created_at=_NOW), UserRole.TEACHER)

    notes = repo.list_for_student("s1")

    assert [n.id for n in notes] == ["n1", "n2"]


def test_mark_read_requires_student_role() -> None:
    repo = SqliteTeacherNoteRepository()
    repo.create(_make_note(), UserRole.TEACHER)

    with pytest.raises(PermissionError):
        repo.mark_read("note-1", UserRole.TEACHER)


def test_mark_read_sets_read_at() -> None:
    repo = SqliteTeacherNoteRepository()
    repo.create(_make_note(), UserRole.TEACHER)

    repo.mark_read("note-1", UserRole.STUDENT)

    notes = repo.list_for_student("s1")
    assert notes[0].read_at is not None


def test_mark_read_is_idempotent_does_not_regress() -> None:
    """§ "repeated sync must not regress read state" — екінші рет
    шақыру бастапқы read_at-ты ЕШҚАШАН ауыстырмайды."""
    repo = SqliteTeacherNoteRepository()
    repo.create(_make_note(), UserRole.TEACHER)

    repo.mark_read("note-1", UserRole.STUDENT)
    first_read_at = repo.list_for_student("s1")[0].read_at

    repo.mark_read("note-1", UserRole.STUDENT)
    second_read_at = repo.list_for_student("s1")[0].read_at

    assert first_read_at == second_read_at


def test_create_enqueues_for_sync() -> None:
    outbox = SqliteSyncOutboxRepository(":memory:")
    repo = SqliteTeacherNoteRepository(sync_outbox_repository=outbox)

    repo.create(_make_note(), UserRole.TEACHER)

    assert outbox.count_pending() == 1


def test_mark_read_does_not_enqueue_for_sync() -> None:
    """§ ХАЛАЛ (honest) шектеу — ``read_at`` ЕШҚАШАН синхрондалмайды
    (§ ``domain/entities/teacher_note.py`` докстрингі)."""
    outbox = SqliteSyncOutboxRepository(":memory:")
    repo = SqliteTeacherNoteRepository(sync_outbox_repository=outbox)
    repo.create(_make_note(), UserRole.TEACHER)
    outbox_count_after_create = outbox.count_pending()

    repo.mark_read("note-1", UserRole.STUDENT)

    assert outbox.count_pending() == outbox_count_after_create


def test_get_note_sync_payload_shape() -> None:
    repo = SqliteTeacherNoteRepository()
    repo.create(_make_note(experiment_id="ohms-law", session_id="sess-1"), UserRole.TEACHER)

    payload = repo.get_note_sync_payload("note-1")

    assert payload["sync_id"] == "note-1"
    assert payload["teacher_sync_id"] == "t1"
    assert payload["student_sync_id"] == "s1"
    assert payload["classroom_sync_id"] == "c1"
    assert payload["experiment_id"] == "ohms-law"
    assert payload["session_sync_id"] == "sess-1"
    assert payload["message"] == "Өлшеуді қайта тексер"
    assert "read_at" not in payload  # § ешқашан push payload-та жоқ


def test_get_note_sync_payload_missing_returns_none() -> None:
    repo = SqliteTeacherNoteRepository()

    assert repo.get_note_sync_payload("missing") is None


def test_apply_remote_note_creates_local_row() -> None:
    repo = SqliteTeacherNoteRepository()
    payload = {
        "sync_id": "remote-note-1",
        "teacher_sync_id": "t1",
        "student_sync_id": "s1",
        "classroom_sync_id": "c1",
        "experiment_id": "ohms-law",
        "session_sync_id": None,
        "message": "Кернеу мәніне назар аудар",
        "created_at": _NOW.isoformat(),
        "server_revision": 1,
    }

    repo.apply_remote_note(payload)

    notes = repo.list_for_student("s1")
    assert len(notes) == 1
    assert notes[0].message == "Кернеу мәніне назар аудар"
    assert notes[0].sync_state == SyncState.SYNCED


def test_apply_remote_note_never_clobbers_local_read_state() -> None:
    """§ "student's own local read state must never be clobbered by a
    pull" — read-preserve паттерні (§ ``experiment_feedback``-пен
    БІРДЕЙ)."""
    repo = SqliteTeacherNoteRepository()
    repo.create(_make_note(), UserRole.TEACHER)
    repo.mark_read("note-1", UserRole.STUDENT)
    read_at_before = repo.list_for_student("s1")[0].read_at

    payload = repo.get_note_sync_payload("note-1")
    payload["message"] = "жаңартылған мәтін (сервер жауабы)"
    repo.apply_remote_note(payload)

    notes_after = repo.list_for_student("s1")
    assert notes_after[0].read_at == read_at_before


def test_apply_remote_note_does_not_enqueue() -> None:
    outbox = SqliteSyncOutboxRepository(":memory:")
    repo = SqliteTeacherNoteRepository(sync_outbox_repository=outbox)
    payload = {
        "sync_id": "remote-note-1",
        "teacher_sync_id": "t1",
        "student_sync_id": "s1",
        "classroom_sync_id": "c1",
        "experiment_id": None,
        "session_sync_id": None,
        "message": "Хабарлама",
        "created_at": _NOW.isoformat(),
        "server_revision": 1,
    }

    repo.apply_remote_note(payload)

    assert outbox.count_pending() == 0


def test_mark_note_synced_updates_state() -> None:
    repo = SqliteTeacherNoteRepository()
    repo.create(_make_note(), UserRole.TEACHER)

    repo.mark_note_synced("note-1", 5)

    notes = repo.list_for_student("s1")
    assert notes[0].sync_state == SyncState.SYNCED


def test_repeated_apply_remote_note_does_not_duplicate() -> None:
    repo = SqliteTeacherNoteRepository()
    payload = {
        "sync_id": "remote-note-1",
        "teacher_sync_id": "t1",
        "student_sync_id": "s1",
        "classroom_sync_id": "c1",
        "experiment_id": None,
        "session_sync_id": None,
        "message": "Хабарлама",
        "created_at": _NOW.isoformat(),
        "server_revision": 1,
    }

    repo.apply_remote_note(payload)
    repo.apply_remote_note(payload)

    assert len(repo.list_for_student("s1")) == 1
