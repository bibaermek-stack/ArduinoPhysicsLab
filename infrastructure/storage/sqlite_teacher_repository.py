"""SqliteTeacherRepository — ``ITeacherRepository``-дің sqlite3
қолданатын іске асыруы (Multi-Teacher Accounts фазасы).

``SqliteClassroomRepository``-мен БІРДЕЙ пішін: ``db_path=":memory:"``
әдепкі, нақты файл жолын тек ``app.py`` ғана береді. Сынып тағайындау
байланысы ``teacher_classroom_assignments`` кестесінде — ``set_assigned_
classroom_ids()`` толық алмастыру арқылы (ескі жолдарды жойып, жаңасын
кірістіру, бір транзакцияда).

§ Offline-First + Cloud Sync Foundation: ``SqliteClassroomRepository``-мен
БІРДЕЙ sync_id/sync_state/outbox принципі. Мұғалім↔сынып байланысы
(``teacher_classroom_assignments``) ӨЗ алдына ЖЕКЕ ``sync_id``
АЛМАЙДЫ — бүкіл жиын мұғалімнің ӨЗ ``sync_id``-мен, ``"teacher_
classroom"`` entity_type-пен синхрондалады (§ ``domain/services/
sync_payload.py`` докстрингі — "тағайындау жиыны мұғалімнің меншігі").
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from domain.entities.outbox_entry import OutboxOperation
from domain.entities.sync_state import SyncState
from domain.entities.teacher import Teacher
from domain.interfaces.i_sync_outbox_repository import ISyncOutboxRepository
from domain.interfaces.i_teacher_repository import ITeacherRepository
from infrastructure.storage.database import initialize_schema

_SELECT_COLUMNS = (
    "id, full_name, pin_hash, is_active, created_at, updated_at, sync_id, sync_state, server_revision"
)
_ENTITY_TYPE_TEACHER = "teacher"
_ENTITY_TYPE_TEACHER_CLASSROOM = "teacher_classroom"


class SqliteTeacherRepository(ITeacherRepository):
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

    # ---- ITeacherRepository ------------------------------------------------

    def create(self, teacher: Teacher, assigned_classroom_ids: tuple[str, ...] = ()) -> None:
        sync_id = teacher.sync_id or teacher.id
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO teachers
                    (id, full_name, pin_hash, is_active, created_at, updated_at,
                     sync_id, sync_state, server_revision)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    teacher.id,
                    teacher.full_name,
                    teacher.pin_hash,
                    1 if teacher.is_active else 0,
                    teacher.created_at.isoformat(),
                    teacher.updated_at.isoformat(),
                    sync_id,
                    SyncState.PENDING_UPLOAD.value,
                    teacher.server_revision,
                ),
            )
        self._enqueue(_ENTITY_TYPE_TEACHER, sync_id, OutboxOperation.UPSERT)
        self.set_assigned_classroom_ids(teacher.id, assigned_classroom_ids)

    def update(self, teacher: Teacher) -> None:
        sync_id = teacher.sync_id or teacher.id
        with self._connection:
            self._connection.execute(
                """
                UPDATE teachers
                SET full_name = ?, pin_hash = ?, is_active = ?, updated_at = ?,
                    sync_id = ?, sync_state = ?
                WHERE id = ?
                """,
                (
                    teacher.full_name,
                    teacher.pin_hash,
                    1 if teacher.is_active else 0,
                    datetime.now(timezone.utc).isoformat(),
                    sync_id,
                    SyncState.PENDING_UPLOAD.value,
                    teacher.id,
                ),
            )
        self._enqueue(_ENTITY_TYPE_TEACHER, sync_id, OutboxOperation.UPSERT)

    def get(self, teacher_id: str) -> Teacher | None:
        row = self._connection.execute(
            f"SELECT {_SELECT_COLUMNS} FROM teachers WHERE id = ?", (teacher_id,)
        ).fetchone()
        return self._row_to_teacher(row) if row is not None else None

    def list_all(self) -> tuple[Teacher, ...]:
        rows = self._connection.execute(
            f"SELECT {_SELECT_COLUMNS} FROM teachers ORDER BY full_name"
        ).fetchall()
        return tuple(self._row_to_teacher(row) for row in rows)

    def list_active(self) -> tuple[Teacher, ...]:
        rows = self._connection.execute(
            f"SELECT {_SELECT_COLUMNS} FROM teachers WHERE is_active = 1 ORDER BY full_name"
        ).fetchall()
        return tuple(self._row_to_teacher(row) for row in rows)

    def pin_hash_exists(self, pin_hash: str, exclude_teacher_id: str | None = None) -> bool:
        if exclude_teacher_id is None:
            row = self._connection.execute(
                "SELECT 1 FROM teachers WHERE pin_hash = ? AND is_active = 1", (pin_hash,)
            ).fetchone()
        else:
            row = self._connection.execute(
                "SELECT 1 FROM teachers WHERE pin_hash = ? AND is_active = 1 AND id != ?",
                (pin_hash, exclude_teacher_id),
            ).fetchone()
        return row is not None

    def set_assigned_classroom_ids(self, teacher_id: str, classroom_ids: tuple[str, ...]) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connection:
            self._connection.execute(
                "DELETE FROM teacher_classroom_assignments WHERE teacher_id = ?", (teacher_id,)
            )
            self._connection.executemany(
                "INSERT INTO teacher_classroom_assignments (teacher_id, classroom_id, updated_at) VALUES (?, ?, ?)",
                [(teacher_id, classroom_id, now_iso) for classroom_id in classroom_ids],
            )
        teacher = self.get(teacher_id)
        if teacher is not None:
            self._enqueue(
                _ENTITY_TYPE_TEACHER_CLASSROOM, teacher.sync_id or teacher.id, OutboxOperation.UPSERT
            )

    def list_assigned_classroom_ids(self, teacher_id: str) -> tuple[str, ...]:
        rows = self._connection.execute(
            "SELECT classroom_id FROM teacher_classroom_assignments WHERE teacher_id = ? ORDER BY classroom_id",
            (teacher_id,),
        ).fetchall()
        return tuple(row[0] for row in rows)

    def list_teacher_ids_for_classroom(self, classroom_id: str) -> tuple[str, ...]:
        rows = self._connection.execute(
            "SELECT teacher_id FROM teacher_classroom_assignments WHERE classroom_id = ? ORDER BY teacher_id",
            (classroom_id,),
        ).fetchall()
        return tuple(row[0] for row in rows)

    # ---- Sync foundation (Offline-First + Cloud Sync Foundation) ---------

    def _enqueue(self, entity_type: str, sync_id: str, operation: OutboxOperation) -> None:
        if self._sync_outbox_repository is None:
            return
        self._sync_outbox_repository.enqueue(entity_type, sync_id, operation)

    def apply_remote_upsert(self, teacher: Teacher) -> None:
        """§18 "Pull Sync" — ``SqliteClassroomRepository.apply_remote_
        upsert()``-пен БІРДЕЙ принцип, ЕШБІР outbox жазуы ЖОҚ."""
        existing = self.get(teacher.sync_id)
        with self._connection:
            if existing is None:
                self._connection.execute(
                    """
                    INSERT INTO teachers
                        (id, full_name, pin_hash, is_active, created_at, updated_at,
                         sync_id, sync_state, server_revision)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        teacher.sync_id, teacher.full_name, teacher.pin_hash,
                        1 if teacher.is_active else 0, teacher.created_at.isoformat(),
                        teacher.updated_at.isoformat(), teacher.sync_id, SyncState.SYNCED.value,
                        teacher.server_revision,
                    ),
                )
            else:
                self._connection.execute(
                    """
                    UPDATE teachers
                    SET full_name = ?, pin_hash = ?, is_active = ?, updated_at = ?,
                        sync_state = ?, server_revision = ?
                    WHERE sync_id = ?
                    """,
                    (
                        teacher.full_name, teacher.pin_hash, 1 if teacher.is_active else 0,
                        teacher.updated_at.isoformat(), SyncState.SYNCED.value, teacher.server_revision,
                        teacher.sync_id,
                    ),
                )

    def mark_synced(self, teacher_id: str, server_revision: int) -> None:
        with self._connection:
            self._connection.execute(
                "UPDATE teachers SET sync_state = ?, server_revision = ? WHERE id = ?",
                (SyncState.SYNCED.value, server_revision, teacher_id),
            )

    def apply_remote_assignment(self, teacher_id: str, classroom_ids: tuple[str, ...]) -> None:
        """§18 "Pull Sync" — ``set_assigned_classroom_ids()``-пен БІРДЕЙ
        толық алмастыру, БІРАҚ ЕШБІР outbox жазуы ЖАСАЛМАЙДЫ (§ pull-дан
        алынған тағайындау серверге ҚАЙТА жіберілмеуі керек)."""
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connection:
            self._connection.execute(
                "DELETE FROM teacher_classroom_assignments WHERE teacher_id = ?", (teacher_id,)
            )
            self._connection.executemany(
                "INSERT INTO teacher_classroom_assignments (teacher_id, classroom_id, updated_at) VALUES (?, ?, ?)",
                [(teacher_id, classroom_id, now_iso) for classroom_id in classroom_ids],
            )

    @staticmethod
    def _row_to_teacher(row: tuple) -> Teacher:
        id_, full_name, pin_hash, is_active, created_at, updated_at, sync_id, sync_state, server_revision = row
        return Teacher(
            id=id_,
            full_name=full_name,
            pin_hash=pin_hash,
            is_active=bool(is_active),
            created_at=datetime.fromisoformat(created_at),
            updated_at=datetime.fromisoformat(updated_at),
            sync_id=sync_id,
            sync_state=SyncState(sync_state),
            server_revision=server_revision,
        )
