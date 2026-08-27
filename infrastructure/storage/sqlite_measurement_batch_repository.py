"""SqliteMeasurementBatchRepository — ``IMeasurementBatchRepository``-
дің sqlite3 қолданатын іске асыруы (Phase 4: Raw Arduino Measurement
Cloud Sync).

``SqliteSyncOutboxRepository``-мен БІРДЕЙ пішін: ӨЗ бетінше sqlite3
байланысы (``measurements``/``experiment_sessions`` кестелерін
``SqliteSessionRepository``-мен БІРГЕ бөліседі, СОЛ физикалық файл
арқылы). ``db_path=":memory:"`` әдепкі, нақты файл жолын тек ``app.py``
ғана береді.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from domain.entities.outbox_entry import OutboxOperation
from domain.entities.sync_state import SyncState
from domain.interfaces.i_measurement_batch_repository import IMeasurementBatchRepository
from domain.interfaces.i_sync_outbox_repository import ISyncOutboxRepository
from infrastructure.storage.database import initialize_schema

_ENTITY_TYPE_MEASUREMENT_BATCH = "measurement_batch"


class SqliteMeasurementBatchRepository(IMeasurementBatchRepository):
    def __init__(
        self,
        db_path: str | Path = ":memory:",
        sync_outbox_repository: ISyncOutboxRepository | None = None,
    ) -> None:
        self._db_path = str(db_path)
        self._connection = sqlite3.connect(self._db_path)
        initialize_schema(self._connection)
        self._sync_outbox_repository = sync_outbox_repository

    def close(self) -> None:
        self._connection.close()

    # ---- IMeasurementBatchRepository -------------------------------------

    def create_pending_batches_for_session(
        self, session_id: str, chunk_size: int, finalize: bool = False
    ) -> int:
        if chunk_size <= 0:
            raise ValueError("chunk_size оң сан болуы керек")

        covered_row = self._connection.execute(
            "SELECT MAX(sequence_end) FROM measurement_batches WHERE session_id = ?", (session_id,)
        ).fetchone()
        covered_up_to = covered_row[0] if covered_row is not None and covered_row[0] is not None else 0

        available_row = self._connection.execute(
            "SELECT COUNT(*) FROM measurements WHERE session_id = ? AND sequence_no >= ?",
            (session_id, covered_up_to),
        ).fetchone()
        available = available_row[0] if available_row is not None else 0

        ranges: list[tuple[int, int]] = []
        while available >= chunk_size:
            ranges.append((covered_up_to, covered_up_to + chunk_size))
            covered_up_to += chunk_size
            available -= chunk_size
        if finalize and available > 0:
            ranges.append((covered_up_to, covered_up_to + available))

        if not ranges:
            return 0

        now_iso = datetime.now(timezone.utc).isoformat()
        created_batch_ids: list[str] = []
        with self._connection:
            for sequence_start, sequence_end in ranges:
                batch_sync_id = str(uuid4())
                self._connection.execute(
                    """
                    INSERT INTO measurement_batches
                        (batch_sync_id, session_id, sequence_start, sequence_end,
                         sample_count, created_at, sync_state)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        batch_sync_id, session_id, sequence_start, sequence_end,
                        sequence_end - sequence_start, now_iso, SyncState.PENDING_UPLOAD.value,
                    ),
                )
                created_batch_ids.append(batch_sync_id)
        # § "database is locked" қорғанысы: outbox-қа жазу БӨЛЕК
        # sqlite3 байланысы арқылы жүреді (§ ``SqliteSyncOutboxRepository``
        # ӨЗ данасы) — ``with self._connection:`` жазу транзакциясы
        # АШЫҚ кезде екінші байланыс жаза алмайды, сондықтан enqueue
        # ӘРҚАШАН транзакция ЖАБЫЛҒАННАН КЕЙІН шақырылады (§ established
        # паттерн, ``SqliteClassroomRepository.create()``-пен БІРДЕЙ).
        for batch_sync_id in created_batch_ids:
            self._enqueue(batch_sync_id)
        return len(ranges)

    def get_batch_sync_payload(self, batch_sync_id: str) -> dict | None:
        batch_row = self._connection.execute(
            "SELECT session_id, sequence_start, sequence_end, sample_count, created_at, "
            "sync_state, server_revision FROM measurement_batches WHERE batch_sync_id = ?",
            (batch_sync_id,),
        ).fetchone()
        if batch_row is None:
            return None
        (
            session_id, sequence_start, sequence_end, sample_count, created_at,
            sync_state, server_revision,
        ) = batch_row

        measurement_rows = self._connection.execute(
            "SELECT sequence_no, timestamp, values_json, derived_values_json, warnings_json "
            "FROM measurements WHERE session_id = ? AND sequence_no >= ? AND sequence_no < ? "
            "ORDER BY sequence_no",
            (session_id, sequence_start, sequence_end),
        ).fetchall()

        return {
            "sync_id": batch_sync_id,
            "session_sync_id": session_id,
            "sequence_start": sequence_start,
            "sequence_end": sequence_end,
            "sample_count": sample_count,
            "created_at": created_at,
            "measurements": [
                {
                    "sequence_no": row[0],
                    "timestamp": row[1],
                    "values": json.loads(row[2]),
                    "derived_values": json.loads(row[3]),
                    "warnings": json.loads(row[4]),
                }
                for row in measurement_rows
            ],
            "sync_state": sync_state,
            "server_revision": server_revision,
        }

    def apply_remote_batch(self, payload: dict) -> None:
        """§18 "Pull Sync" / §21 "Remote Apply": ЕШБІР outbox жазуы
        ЖАСАЛМАЙДЫ. Measurement жолдары ``INSERT OR IGNORE`` арқылы —
        ``UNIQUE(session_id, sequence_no)`` индексі қайталама pull-ды
        қауіпсіз no-op етеді (§ идемпотентті remote apply)."""
        batch_sync_id = payload["sync_id"]
        session_id = payload["session_sync_id"]
        with self._connection:
            self._connection.execute(
                """
                INSERT OR REPLACE INTO measurement_batches
                    (batch_sync_id, session_id, sequence_start, sequence_end,
                     sample_count, created_at, sync_state, server_revision)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    batch_sync_id, session_id, payload["sequence_start"], payload["sequence_end"],
                    payload["sample_count"], payload["created_at"], SyncState.SYNCED.value,
                    payload.get("server_revision"),
                ),
            )
            self._connection.executemany(
                """
                INSERT OR IGNORE INTO measurements
                    (session_id, sequence_no, timestamp, values_json,
                     derived_values_json, warnings_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        session_id,
                        item["sequence_no"],
                        item["timestamp"],
                        json.dumps(item["values"]),
                        json.dumps(item["derived_values"]),
                        json.dumps(item["warnings"]),
                    )
                    for item in payload["measurements"]
                ],
            )
            # § "second device reconstruction" — pull арқылы алынған
            # measurement-дер ``experiment_sessions.measurement_count``-ты
            # да дұрыс көрсетуі үшін (§ ``get_measurements()`` бетбелгісіз,
            # тікелей санақ, § UI journal/results беттерінің дұрыс саны).
            total_count_row = self._connection.execute(
                "SELECT COUNT(*) FROM measurements WHERE session_id = ?", (session_id,)
            ).fetchone()
            if total_count_row is not None:
                self._connection.execute(
                    "UPDATE experiment_sessions SET measurement_count = ? WHERE id = ?",
                    (total_count_row[0], session_id),
                )

    def mark_batch_synced(self, batch_sync_id: str, server_revision: int) -> None:
        with self._connection:
            self._connection.execute(
                "UPDATE measurement_batches SET sync_state = ?, server_revision = ? WHERE batch_sync_id = ?",
                (SyncState.SYNCED.value, server_revision, batch_sync_id),
            )

    def enqueue_batch_for_sync(self, batch_sync_id: str) -> None:
        self._enqueue(batch_sync_id)

    def list_pending_batch_ids_for_session(self, session_id: str) -> tuple[str, ...]:
        rows = self._connection.execute(
            "SELECT batch_sync_id FROM measurement_batches WHERE session_id = ? ORDER BY sequence_start",
            (session_id,),
        ).fetchall()
        return tuple(row[0] for row in rows)

    # ---- Internal ----------------------------------------------------------

    def _enqueue(self, batch_sync_id: str) -> None:
        if self._sync_outbox_repository is None:
            return
        self._sync_outbox_repository.enqueue(
            _ENTITY_TYPE_MEASUREMENT_BATCH, batch_sync_id, OutboxOperation.UPSERT
        )
