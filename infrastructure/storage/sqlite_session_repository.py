"""SqliteSessionRepository — ``ISessionRepository``-дің Python стандартты
``sqlite3`` кітапханасын қолданатын іске асыруы (Data Journal V1).

Әдепкі ``db_path=":memory:"`` — сынақтарда/ешбір нақты жол берілмегенде
пайдаланушының нақты дерегіне ЕШҚАШАН тимейді (``DeviceManager()``-дің
"әдепкі бойынша қауіпсіз" конвенциясымен бірдей). Нақты файл жолын тек
``app.py`` ғана (``get_default_database_path()`` арқылы) береді.
"""

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from domain.entities.experiment_definition import ExperimentDefinition
from domain.entities.experiment_session import ExperimentSession
from domain.entities.measurement import Measurement
from domain.entities.outbox_entry import OutboxOperation
from domain.entities.sync_state import SyncState
from domain.interfaces.i_session_repository import ISessionRepository, SessionSummary
from domain.interfaces.i_sync_outbox_repository import ISyncOutboxRepository
from infrastructure.storage.database import initialize_schema

_logger = logging.getLogger(__name__)

_STATUS_FINALIZED = "finalized"
_STATUS_IN_PROGRESS = "in_progress"
_ENTITY_TYPE_SESSION = "session"

_SUMMARY_COLUMNS = (
    "id, experiment_id, experiment_title, experiment_display_number, "
    "started_at, ended_at, status, measurement_count, created_at"
)
_SYNC_COLUMNS = (
    "id, experiment_id, experiment_title, experiment_display_number, "
    "started_at, ended_at, status, measurement_count, created_at, updated_at, "
    "sync_state, server_revision"
)


class SqliteSessionRepository(ISessionRepository):
    """Аяқталған ``ExperimentSession``-дарды sqlite файлына/жадына сақтайды."""

    def __init__(
        self,
        db_path: str | Path = ":memory:",
        sync_outbox_repository: ISyncOutboxRepository | None = None,
    ) -> None:
        self._db_path = str(db_path)
        self._connection = sqlite3.connect(self._db_path)
        self._connection.execute("PRAGMA foreign_keys = ON")
        initialize_schema(self._connection)
        self._sync_outbox_repository = sync_outbox_repository

    def close(self) -> None:
        """Байланысты жабады (тек тесттер/қолмен тазалау үшін — интерфейс
        бөлігі ЕМЕС, себебі әр іске асыру өз ресурс түрін білуі мүмкін).
        """
        self._connection.close()

    # ---- ISessionRepository -------------------------------------------------

    def save_session(
        self,
        session: ExperimentSession,
        experiment_metadata: ExperimentDefinition | None = None,
    ) -> None:
        if not session.measurements:
            # Бос сессия журналда сақталмайды (§8) — жалғыз, орталықтандырылған
            # guard, барлық шақырушы нүкте (Stop/Back/switch/quit) осыдан
            # автоматты дұрыс болады.
            return

        title = experiment_metadata.title if experiment_metadata is not None else session.experiment_id
        display_number = (
            experiment_metadata.display_number if experiment_metadata is not None else None
        )
        status = _STATUS_FINALIZED if session.ended_at is not None else _STATUS_IN_PROGRESS
        now_iso = datetime.now(timezone.utc).isoformat()

        with self._connection:
            existing = self._connection.execute(
                "SELECT created_at FROM experiment_sessions WHERE id = ?", (session.id,)
            ).fetchone()
            created_at = existing[0] if existing is not None else now_iso

            self._connection.execute(
                """
                INSERT OR REPLACE INTO experiment_sessions
                    (id, experiment_id, experiment_display_number, experiment_title,
                     started_at, ended_at, status, measurement_count, created_at,
                     updated_at, sync_state)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session.id,
                    session.experiment_id,
                    display_number,
                    title,
                    session.started_at.isoformat(),
                    session.ended_at.isoformat() if session.ended_at is not None else None,
                    status,
                    session.measurement_count,
                    created_at,
                    now_iso,
                    SyncState.PENDING_UPLOAD.value,
                ),
            )

            # Идемпотенттілік: қайта сақтағанда ескі жолдар алынып,
            # ағымдағы толық тізім қайта жазылады — session.id тұрақты
            # болғандықтан дубликат жол ешқашан құрылмайды.
            self._connection.execute(
                "DELETE FROM measurements WHERE session_id = ?", (session.id,)
            )
            self._connection.executemany(
                """
                INSERT INTO measurements
                    (session_id, sequence_no, timestamp, values_json,
                     derived_values_json, warnings_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        session.id,
                        index,
                        measurement.timestamp.isoformat(),
                        json.dumps(measurement.values),
                        json.dumps(measurement.derived_values),
                        json.dumps(list(measurement.warnings)),
                    )
                    for index, measurement in enumerate(session.measurements)
                ],
            )
        self._enqueue(session.id)

    def get_sessions(
        self, limit: int | None = None, experiment_id: str | None = None
    ) -> tuple[SessionSummary, ...]:
        query = f"SELECT {_SUMMARY_COLUMNS} FROM experiment_sessions"
        params: list[object] = []
        if experiment_id is not None:
            query += " WHERE experiment_id = ?"
            params.append(experiment_id)
        query += " ORDER BY started_at DESC, rowid DESC"
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)

        rows = self._connection.execute(query, params).fetchall()
        return tuple(self._row_to_summary(row) for row in rows)

    def get_session(self, session_id: str) -> SessionSummary | None:
        row = self._connection.execute(
            f"SELECT {_SUMMARY_COLUMNS} FROM experiment_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        return self._row_to_summary(row) if row is not None else None

    def get_measurements(self, session_id: str) -> tuple[Measurement, ...]:
        session_row = self._connection.execute(
            "SELECT experiment_id FROM experiment_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if session_row is None:
            return ()
        experiment_id = session_row[0]

        rows = self._connection.execute(
            "SELECT timestamp, values_json, derived_values_json, warnings_json "
            "FROM measurements WHERE session_id = ? ORDER BY sequence_no",
            (session_id,),
        ).fetchall()

        measurements: list[Measurement] = []
        for row in rows:
            measurement = self._row_to_measurement(experiment_id, row)
            if measurement is not None:
                measurements.append(measurement)
        return tuple(measurements)

    def get_latest_measurement(self, session_id: str) -> Measurement | None:
        session_row = self._connection.execute(
            "SELECT experiment_id FROM experiment_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if session_row is None:
            return None
        experiment_id = session_row[0]

        row = self._connection.execute(
            "SELECT timestamp, values_json, derived_values_json, warnings_json "
            "FROM measurements WHERE session_id = ? ORDER BY sequence_no DESC LIMIT 1",
            (session_id,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_measurement(experiment_id, row)

    def count_sessions(self) -> int:
        row = self._connection.execute("SELECT COUNT(*) FROM experiment_sessions").fetchone()
        return int(row[0])

    def exists(self, session_id: str) -> bool:
        row = self._connection.execute(
            "SELECT 1 FROM experiment_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        return row is not None

    # ---- Cloud Sync (Phase 2) -------------------------------------------

    def _enqueue(self, session_id: str) -> None:
        if self._sync_outbox_repository is None:
            return
        self._sync_outbox_repository.enqueue(_ENTITY_TYPE_SESSION, session_id, OutboxOperation.UPSERT)

    def enqueue_for_sync(self, session_id: str) -> None:
        self._enqueue(session_id)

    def append_measurements(
        self,
        session_id: str,
        experiment_id: str,
        new_measurements: tuple[Measurement, ...],
        experiment_metadata: ExperimentDefinition | None = None,
        started_at: datetime | None = None,
    ) -> int:
        if not new_measurements:
            return 0

        now_iso = datetime.now(timezone.utc).isoformat()
        title = experiment_metadata.title if experiment_metadata is not None else experiment_id
        display_number = (
            experiment_metadata.display_number if experiment_metadata is not None else None
        )

        with self._connection:
            existing = self._connection.execute(
                "SELECT created_at FROM experiment_sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if existing is None:
                # § Тәжірибе ӘЛІ ЖҮРІП ЖАТЫР — жол алдын ала "in_progress"
                # күймен жасалады (§ ``save_session()`` кейінірек, соңғы
                # аяқталған күймен, ҚАУІПСІЗ АЛМАСТЫРАДЫ).
                self._connection.execute(
                    """
                    INSERT INTO experiment_sessions
                        (id, experiment_id, experiment_display_number, experiment_title,
                         started_at, ended_at, status, measurement_count, created_at,
                         updated_at, sync_state)
                    VALUES (?, ?, ?, ?, ?, NULL, ?, 0, ?, ?, ?)
                    """,
                    (
                        session_id, experiment_id, display_number, title,
                        (started_at or datetime.now(timezone.utc)).isoformat(),
                        _STATUS_IN_PROGRESS, now_iso, now_iso, SyncState.PENDING_UPLOAD.value,
                    ),
                )

            max_row = self._connection.execute(
                "SELECT MAX(sequence_no) FROM measurements WHERE session_id = ?", (session_id,)
            ).fetchone()
            next_sequence_no = (max_row[0] + 1) if max_row is not None and max_row[0] is not None else 0

            self._connection.executemany(
                """
                INSERT INTO measurements
                    (session_id, sequence_no, timestamp, values_json,
                     derived_values_json, warnings_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        session_id,
                        next_sequence_no + offset,
                        measurement.timestamp.isoformat(),
                        json.dumps(measurement.values),
                        json.dumps(measurement.derived_values),
                        json.dumps(list(measurement.warnings)),
                    )
                    for offset, measurement in enumerate(new_measurements)
                ],
            )

            total_count_row = self._connection.execute(
                "SELECT COUNT(*) FROM measurements WHERE session_id = ?", (session_id,)
            ).fetchone()
            self._connection.execute(
                """
                UPDATE experiment_sessions
                SET measurement_count = ?, updated_at = ?, sync_state = ?
                WHERE id = ?
                """,
                (total_count_row[0], now_iso, SyncState.PENDING_UPLOAD.value, session_id),
            )
        self._enqueue(session_id)
        return len(new_measurements)

    def get_sync_payload(self, session_id: str) -> dict | None:
        row = self._connection.execute(
            f"SELECT {_SYNC_COLUMNS} FROM experiment_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if row is None:
            return None
        (
            id_, experiment_id, experiment_title, experiment_display_number,
            started_at, ended_at, status, measurement_count, created_at, updated_at,
            sync_state, server_revision,
        ) = row
        return {
            "sync_id": id_,
            "experiment_id": experiment_id,
            "experiment_title": experiment_title,
            "experiment_display_number": experiment_display_number,
            "started_at": started_at,
            "ended_at": ended_at,
            "status": status,
            "measurement_count": measurement_count,
            "created_at": created_at,
            "updated_at": updated_at or created_at,
            "sync_state": sync_state,
            "server_revision": server_revision,
        }

    def apply_remote_session(self, payload: dict) -> None:
        """§18 "Pull Sync": ЕШБІР outbox жазуы ЖАСАЛМАЙДЫ (§ established
        "apply_remote_* never re-enqueues" паттерні). Raw measurement-дер
        Phase 2-де синхрондалмайды (§27) — бұл жазба тек сессия
        метадатасын (title/display_number/status/counts) жаңартады,
        ``measurements`` кестесіне ЕШҚАШАН тимейді."""
        sync_id = payload["sync_id"]
        with self._connection:
            existing = self._connection.execute(
                "SELECT created_at FROM experiment_sessions WHERE id = ?", (sync_id,)
            ).fetchone()
            created_at = existing[0] if existing is not None else payload["created_at"]
            self._connection.execute(
                """
                INSERT OR REPLACE INTO experiment_sessions
                    (id, experiment_id, experiment_display_number, experiment_title,
                     started_at, ended_at, status, measurement_count, created_at,
                     updated_at, sync_state, server_revision)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sync_id,
                    payload["experiment_id"],
                    payload.get("experiment_display_number"),
                    payload["experiment_title"],
                    payload["started_at"],
                    payload.get("ended_at"),
                    payload["status"],
                    payload["measurement_count"],
                    created_at,
                    payload["updated_at"],
                    SyncState.SYNCED.value,
                    payload.get("server_revision"),
                ),
            )

    def mark_session_synced(self, session_id: str, server_revision: int) -> None:
        with self._connection:
            self._connection.execute(
                "UPDATE experiment_sessions SET sync_state = ?, server_revision = ? WHERE id = ?",
                (SyncState.SYNCED.value, server_revision, session_id),
            )

    # ---- Row -> domain/DTO конверсиясы --------------------------------------

    @staticmethod
    def _row_to_summary(row: tuple) -> SessionSummary:
        (
            id_,
            experiment_id,
            experiment_title,
            experiment_display_number,
            started_at,
            ended_at,
            status,
            measurement_count,
            created_at,
        ) = row
        return SessionSummary(
            id=id_,
            experiment_id=experiment_id,
            experiment_title=experiment_title,
            experiment_display_number=experiment_display_number,
            started_at=datetime.fromisoformat(started_at),
            ended_at=datetime.fromisoformat(ended_at) if ended_at is not None else None,
            status=status,
            measurement_count=measurement_count,
            created_at=datetime.fromisoformat(created_at),
        )

    @staticmethod
    def _row_to_measurement(experiment_id: str, row: tuple) -> Measurement | None:
        timestamp_str, values_json, derived_values_json, warnings_json = row
        try:
            values = json.loads(values_json)
            derived_values = json.loads(derived_values_json)
            warnings = json.loads(warnings_json)
            if not isinstance(values, dict) or not isinstance(derived_values, dict):
                raise ValueError("values/derived_values JSON dict болуы керек")
            if not isinstance(warnings, list):
                raise ValueError("warnings JSON list болуы керек")
            return Measurement(
                timestamp=datetime.fromisoformat(timestamp_str),
                values=values,
                experiment_id=experiment_id,
                derived_values=derived_values,
                warnings=tuple(warnings),
            )
        except Exception as exc:  # қорғаныс: бүлінген жол бүкіл сұрауды құлатпайды
            _logger.debug(
                "get_measurements(): бүлінген measurement жолы өткізіп жіберілді: %s", exc
            )
            return None
