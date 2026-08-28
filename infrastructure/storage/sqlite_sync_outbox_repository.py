"""SqliteSyncOutboxRepository — ``ISyncOutboxRepository``-дің sqlite3
қолданатын іске асыруы (Offline-First + Cloud Sync Foundation фазасы).

§7 "Queue Deduplication" — ``enqueue()`` ``INSERT ... ON CONFLICT
(entity_type, entity_sync_id) DO UPDATE`` арқылы іске асырылады: жаңа
UPSERT/DELETE ниеті ЕСКІ күтілетін жазбаны АЛМАСТЫРАДЫ (operation +
created_at жаңарады, ``attempt_count``/``last_error``/``next_retry_at``
НӨЛГЕ ысырылады — жаңа ниет үшін бастапқы қайталау кестесі қайта
басталуы тиіс).
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from domain.entities.outbox_entry import OutboxEntry, OutboxOperation
from domain.interfaces.i_sync_outbox_repository import ISyncOutboxRepository
from infrastructure.storage.database import initialize_schema

_SELECT_COLUMNS = (
    "id, entity_type, entity_sync_id, operation, created_at, attempt_count, last_error, next_retry_at"
)


class SqliteSyncOutboxRepository(ISyncOutboxRepository):
    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self._db_path = str(db_path)
        self._connection = sqlite3.connect(self._db_path)
        initialize_schema(self._connection)

    def close(self) -> None:
        self._connection.close()

    def enqueue(self, entity_type: str, entity_sync_id: str, operation: OutboxOperation) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO sync_outbox
                    (entity_type, entity_sync_id, operation, created_at, attempt_count, last_error, next_retry_at)
                VALUES (?, ?, ?, ?, 0, '', NULL)
                ON CONFLICT(entity_type, entity_sync_id) DO UPDATE SET
                    operation = excluded.operation,
                    created_at = excluded.created_at,
                    attempt_count = 0,
                    last_error = '',
                    next_retry_at = NULL
                """,
                (entity_type, entity_sync_id, operation.value, now_iso),
            )

    def list_due(self, now: datetime, limit: int = 100) -> tuple[OutboxEntry, ...]:
        now_iso = now.isoformat()
        rows = self._connection.execute(
            f"""
            SELECT {_SELECT_COLUMNS} FROM sync_outbox
            WHERE next_retry_at IS NULL OR next_retry_at <= ?
            ORDER BY created_at, rowid
            LIMIT ?
            """,
            (now_iso, limit),
        ).fetchall()
        return tuple(self._row_to_entry(row) for row in rows)

    def list_all(self) -> tuple[OutboxEntry, ...]:
        rows = self._connection.execute(
            f"SELECT {_SELECT_COLUMNS} FROM sync_outbox ORDER BY created_at, rowid"
        ).fetchall()
        return tuple(self._row_to_entry(row) for row in rows)

    def count_pending(self) -> int:
        row = self._connection.execute("SELECT COUNT(*) FROM sync_outbox").fetchone()
        return row[0]

    def mark_success(self, entry_id: int) -> None:
        with self._connection:
            self._connection.execute("DELETE FROM sync_outbox WHERE id = ?", (entry_id,))

    def mark_failure(self, entry_id: int, error: str, next_retry_at: datetime) -> None:
        with self._connection:
            self._connection.execute(
                """
                UPDATE sync_outbox
                SET attempt_count = attempt_count + 1, last_error = ?, next_retry_at = ?
                WHERE id = ?
                """,
                (error, next_retry_at.isoformat(), entry_id),
            )

    @staticmethod
    def _row_to_entry(row: tuple) -> OutboxEntry:
        id_, entity_type, entity_sync_id, operation, created_at, attempt_count, last_error, next_retry_at = row
        return OutboxEntry(
            id=id_,
            entity_type=entity_type,
            entity_sync_id=entity_sync_id,
            operation=OutboxOperation(operation),
            created_at=datetime.fromisoformat(created_at),
            attempt_count=attempt_count,
            last_error=last_error,
            next_retry_at=datetime.fromisoformat(next_retry_at) if next_retry_at else None,
        )
