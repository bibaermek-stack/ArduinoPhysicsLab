"""SqliteClassroomRepository — ``IClassroomRepository``-дің sqlite3
қолданатын іске асыруы (Phase 39B).

``SqliteFeedbackRepository``-мен БІРДЕЙ пішін: ``db_path=":memory:"``
әдепкі, нақты файл жолын тек ``app.py`` ғана береді.

§ Offline-First + Cloud Sync Foundation: жазу әдістері ЕНДІ ``sync_id``/
``sync_state`` бағандарын да жаңартады —
- ``create()``: ``sync_id`` бос болса, ``classroom.id``-мен БІРДЕЙ
  мәнге орнатылады (§ "local primary key may remain unchanged... add a
  stable sync/global identifier" — id ӘЛДЕҚАШАН UUID, § audit), ``sync_
  state`` ``PENDING_UPLOAD``.
- ``update()``: ``sync_state`` ``PENDING_UPLOAD``-қа қайта орнатылады
  (өзгертілген жазба серверге ЖАҢАДАН жіберілуі керек).
- ``archive(archived=True)``: ``sync_state`` ``PENDING_DELETE`` (soft-
  delete сигналы), ``archive(archived=False)``: қалпына келтіру —
  ``PENDING_UPLOAD``.

``sync_outbox_repository`` ЕРІКТІ параметр (§ established "optional
dependency with safe default" паттерні) — берілмесе (әдепкі, БАРЛЫҚ
қолданыстағы 500+ тест ҚОСА), мінез-құлық бұрынғыдай, ЕШБІР outbox
жазуы жасалмайды.
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from domain.entities.classroom import Classroom
from domain.entities.outbox_entry import OutboxOperation
from domain.entities.sync_state import SyncState
from domain.entities.user_role import UserRole
from domain.interfaces.i_classroom_repository import IClassroomRepository
from domain.interfaces.i_sync_outbox_repository import ISyncOutboxRepository
from domain.services.student_access_control import ensure_can_manage_classroom_data
from infrastructure.storage.database import initialize_schema

_SELECT_COLUMNS = (
    "id, name, academic_year, description, is_archived, created_at, updated_at, "
    "sync_id, sync_state, server_revision"
)
_ENTITY_TYPE = "classroom"


class SqliteClassroomRepository(IClassroomRepository):
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

    # ---- IClassroomRepository -------------------------------------------

    def create(self, classroom: Classroom, role: UserRole) -> None:
        ensure_can_manage_classroom_data(role)
        sync_id = classroom.sync_id or classroom.id
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO classrooms
                    (id, name, academic_year, description, is_archived, created_at, updated_at,
                     sync_id, sync_state, server_revision)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    classroom.id,
                    classroom.name,
                    classroom.academic_year,
                    classroom.description,
                    1 if classroom.is_archived else 0,
                    classroom.created_at.isoformat(),
                    classroom.updated_at.isoformat(),
                    sync_id,
                    SyncState.PENDING_UPLOAD.value,
                    classroom.server_revision,
                ),
            )
        self._enqueue(sync_id, OutboxOperation.UPSERT)

    def update(self, classroom: Classroom, role: UserRole) -> None:
        ensure_can_manage_classroom_data(role)
        sync_id = classroom.sync_id or classroom.id
        with self._connection:
            self._connection.execute(
                """
                UPDATE classrooms
                SET name = ?, academic_year = ?, description = ?, updated_at = ?,
                    sync_id = ?, sync_state = ?
                WHERE id = ?
                """,
                (
                    classroom.name,
                    classroom.academic_year,
                    classroom.description,
                    datetime.now(timezone.utc).isoformat(),
                    sync_id,
                    SyncState.PENDING_UPLOAD.value,
                    classroom.id,
                ),
            )
        self._enqueue(sync_id, OutboxOperation.UPSERT)

    def archive(self, classroom_id: str, role: UserRole, archived: bool = True) -> None:
        ensure_can_manage_classroom_data(role)
        new_state = SyncState.PENDING_DELETE if archived else SyncState.PENDING_UPLOAD
        with self._connection:
            self._connection.execute(
                "UPDATE classrooms SET is_archived = ?, updated_at = ?, sync_state = ? WHERE id = ?",
                (1 if archived else 0, datetime.now(timezone.utc).isoformat(), new_state.value, classroom_id),
            )
        existing = self.get(classroom_id)
        if existing is not None:
            operation = OutboxOperation.DELETE if archived else OutboxOperation.UPSERT
            self._enqueue(existing.sync_id, operation)

    def get(self, classroom_id: str) -> Classroom | None:
        row = self._connection.execute(
            f"SELECT {_SELECT_COLUMNS} FROM classrooms WHERE id = ?", (classroom_id,)
        ).fetchone()
        return self._row_to_classroom(row) if row is not None else None

    def list_active(self) -> tuple[Classroom, ...]:
        rows = self._connection.execute(
            f"SELECT {_SELECT_COLUMNS} FROM classrooms WHERE is_archived = 0 ORDER BY name"
        ).fetchall()
        return tuple(self._row_to_classroom(row) for row in rows)

    def list_all(self) -> tuple[Classroom, ...]:
        rows = self._connection.execute(
            f"SELECT {_SELECT_COLUMNS} FROM classrooms ORDER BY name"
        ).fetchall()
        return tuple(self._row_to_classroom(row) for row in rows)

    # ---- Sync foundation (Offline-First + Cloud Sync Foundation) ---------

    def _enqueue(self, sync_id: str, operation: OutboxOperation) -> None:
        if self._sync_outbox_repository is None:
            return
        self._sync_outbox_repository.enqueue(_ENTITY_TYPE, sync_id, operation)

    def apply_remote_upsert(self, classroom: Classroom) -> None:
        """§18 "Pull Sync": сервер жіберген жазбаны жергілікті
        дерекқорға жазады — ЕШБІР outbox жазуы ЖАСАЛМАЙДЫ (§ pull-дан
        алынған дерек серверге ҚАЙТА жіберілмеуі керек, әйтпесе
        шексіз push↔pull циклі болар еді). ``id`` жоқ болса ``sync_id``-мен
        БІРДЕЙ (§ "the same logical record must retain the same sync_id
        across devices")."""
        existing = self.get(classroom.sync_id)
        with self._connection:
            if existing is None:
                self._connection.execute(
                    """
                    INSERT INTO classrooms
                        (id, name, academic_year, description, is_archived, created_at, updated_at,
                         sync_id, sync_state, server_revision)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        classroom.sync_id, classroom.name, classroom.academic_year, classroom.description,
                        1 if classroom.is_archived else 0, classroom.created_at.isoformat(),
                        classroom.updated_at.isoformat(), classroom.sync_id, SyncState.SYNCED.value,
                        classroom.server_revision,
                    ),
                )
            else:
                self._connection.execute(
                    """
                    UPDATE classrooms
                    SET name = ?, academic_year = ?, description = ?, is_archived = ?, updated_at = ?,
                        sync_state = ?, server_revision = ?
                    WHERE sync_id = ?
                    """,
                    (
                        classroom.name, classroom.academic_year, classroom.description,
                        1 if classroom.is_archived else 0, classroom.updated_at.isoformat(),
                        SyncState.SYNCED.value, classroom.server_revision, classroom.sync_id,
                    ),
                )

    def mark_synced(self, classroom_id: str, server_revision: int) -> None:
        """§16 "Background Sync": push растауынан кейін жергілікті
        жазбаны ``SYNCED`` деп белгілейді (§ ЕШБІР басқа баған
        өзгертілмейді, § outbox жазуы ҚАЙТА жасалмайды)."""
        with self._connection:
            self._connection.execute(
                "UPDATE classrooms SET sync_state = ?, server_revision = ? WHERE id = ?",
                (SyncState.SYNCED.value, server_revision, classroom_id),
            )

    @staticmethod
    def _row_to_classroom(row: tuple) -> Classroom:
        (
            id_, name, academic_year, description, is_archived, created_at, updated_at,
            sync_id, sync_state, server_revision,
        ) = row
        return Classroom(
            id=id_,
            name=name,
            academic_year=academic_year,
            description=description,
            is_archived=bool(is_archived),
            created_at=datetime.fromisoformat(created_at),
            updated_at=datetime.fromisoformat(updated_at),
            sync_id=sync_id,
            sync_state=SyncState(sync_state),
            server_revision=server_revision,
        )
