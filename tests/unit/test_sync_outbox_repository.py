"""infrastructure/storage/sqlite_sync_outbox_repository.py тесттері
(§6 "Local Sync Queue" / §7 "Queue Deduplication")."""

from datetime import datetime, timedelta, timezone

from domain.entities.outbox_entry import OutboxOperation
from infrastructure.storage.sqlite_sync_outbox_repository import SqliteSyncOutboxRepository


def _now() -> datetime:
    return datetime.now(timezone.utc)


def test_enqueue_then_list_all_returns_entry() -> None:
    repo = SqliteSyncOutboxRepository()
    repo.enqueue("classroom", "c1", OutboxOperation.UPSERT)

    entries = repo.list_all()

    assert len(entries) == 1
    assert entries[0].entity_type == "classroom"
    assert entries[0].entity_sync_id == "c1"
    assert entries[0].operation is OutboxOperation.UPSERT
    assert entries[0].attempt_count == 0
    assert entries[0].next_retry_at is None


def test_list_all_same_created_at_uses_rowid() -> None:
    repo = SqliteSyncOutboxRepository()
    repo.enqueue("classroom", "c1", OutboxOperation.UPSERT)
    repo.enqueue("classroom", "c2", OutboxOperation.UPSERT)
    tied = "2026-01-01T00:00:00+00:00"
    repo._connection.execute("UPDATE sync_outbox SET created_at = ?", (tied,))
    repo._connection.commit()

    entries = repo.list_all()

    assert [entry.entity_sync_id for entry in entries] == ["c1", "c2"]


def test_enqueue_same_entity_coalesces_into_single_entry() -> None:
    """§7: 5 рет offline өзгеріс -> 1 ғана тиімді UPSERT."""
    repo = SqliteSyncOutboxRepository()
    for _ in range(5):
        repo.enqueue("student", "s1", OutboxOperation.UPSERT)

    assert repo.count_pending() == 1


def test_enqueue_resets_attempt_state_on_new_intent() -> None:
    """Сәтсіз әрекеттен кейін ЖАҢА enqueue (мыс. пайдаланушы жазбаны
    тағы да өзгертті) қайталау кестесін нөлден бастайды."""
    repo = SqliteSyncOutboxRepository()
    repo.enqueue("student", "s1", OutboxOperation.UPSERT)
    entry = repo.list_all()[0]
    repo.mark_failure(entry.id, "network error", _now() + timedelta(minutes=5))

    repo.enqueue("student", "s1", OutboxOperation.UPSERT)

    refreshed = repo.list_all()[0]
    assert refreshed.attempt_count == 0
    assert refreshed.last_error == ""
    assert refreshed.next_retry_at is None


def test_enqueue_upsert_then_delete_replaces_operation() -> None:
    repo = SqliteSyncOutboxRepository()
    repo.enqueue("classroom", "c1", OutboxOperation.UPSERT)
    repo.enqueue("classroom", "c1", OutboxOperation.DELETE)

    entries = repo.list_all()

    assert len(entries) == 1
    assert entries[0].operation is OutboxOperation.DELETE


def test_mark_success_removes_entry() -> None:
    repo = SqliteSyncOutboxRepository()
    repo.enqueue("teacher", "t1", OutboxOperation.UPSERT)
    entry = repo.list_all()[0]

    repo.mark_success(entry.id)

    assert repo.count_pending() == 0


def test_mark_failure_increments_attempt_count_and_schedules_retry() -> None:
    repo = SqliteSyncOutboxRepository()
    repo.enqueue("teacher", "t1", OutboxOperation.UPSERT)
    entry = repo.list_all()[0]
    retry_at = _now() + timedelta(minutes=5)

    repo.mark_failure(entry.id, "server unreachable", retry_at)

    refreshed = repo.list_all()[0]
    assert refreshed.attempt_count == 1
    assert refreshed.last_error == "server unreachable"
    assert refreshed.next_retry_at == retry_at


def test_list_due_excludes_entries_scheduled_in_the_future() -> None:
    repo = SqliteSyncOutboxRepository()
    repo.enqueue("teacher", "t1", OutboxOperation.UPSERT)
    entry = repo.list_all()[0]
    now = _now()
    repo.mark_failure(entry.id, "err", now + timedelta(minutes=30))

    assert repo.list_due(now) == ()
    assert repo.list_due(now + timedelta(minutes=31)) != ()


def test_list_due_includes_entries_never_retried() -> None:
    repo = SqliteSyncOutboxRepository()
    repo.enqueue("classroom", "c1", OutboxOperation.UPSERT)

    due = repo.list_due(_now())

    assert len(due) == 1


def test_outbox_persists_across_repository_instances_on_same_file(tmp_path) -> None:
    """§6 "durable, survives application restart"."""
    db_path = tmp_path / "outbox_persist.db"
    repo_a = SqliteSyncOutboxRepository(db_path)
    repo_a.enqueue("classroom", "c1", OutboxOperation.UPSERT)
    repo_a.close()

    repo_b = SqliteSyncOutboxRepository(db_path)
    assert repo_b.count_pending() == 1
