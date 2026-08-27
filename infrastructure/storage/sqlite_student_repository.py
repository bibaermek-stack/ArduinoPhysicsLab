"""SqliteStudentRepository — ``IStudentRepository``-дің sqlite3 қолданатын
іске асыруы (Phase 39B). ``SqliteClassroomRepository``-мен БІРДЕЙ пішін.

§ Offline-First + Cloud Sync Foundation: ``SqliteClassroomRepository``-мен
БІРДЕЙ sync_id/sync_state/outbox принципі (§ сол файлдың докстрингі).
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from domain.entities.outbox_entry import OutboxOperation
from domain.entities.student import Student
from domain.entities.sync_state import SyncState
from domain.entities.user_role import UserRole
from domain.interfaces.i_student_repository import IStudentRepository
from domain.interfaces.i_sync_outbox_repository import ISyncOutboxRepository
from domain.services.student_access_control import ensure_can_manage_classroom_data
from infrastructure.storage.database import initialize_schema

_SELECT_COLUMNS = (
    "id, classroom_id, first_name, last_name, middle_name, student_code, notes, "
    "is_archived, created_at, updated_at, sync_id, sync_state, server_revision"
)
_ENTITY_TYPE = "student"


class SqliteStudentRepository(IStudentRepository):
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

    # ---- IStudentRepository ----------------------------------------------

    def create(self, student: Student, role: UserRole) -> None:
        ensure_can_manage_classroom_data(role)
        sync_id = student.sync_id or student.id
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO students
                    (id, classroom_id, first_name, last_name, middle_name, student_code,
                     notes, is_archived, created_at, updated_at, sync_id, sync_state, server_revision)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    student.id,
                    student.classroom_id,
                    student.first_name,
                    student.last_name,
                    student.middle_name,
                    student.student_code,
                    student.notes,
                    1 if student.is_archived else 0,
                    student.created_at.isoformat(),
                    student.updated_at.isoformat(),
                    sync_id,
                    SyncState.PENDING_UPLOAD.value,
                    student.server_revision,
                ),
            )
        self._enqueue(sync_id, OutboxOperation.UPSERT)

    def update(self, student: Student, role: UserRole) -> None:
        ensure_can_manage_classroom_data(role)
        sync_id = student.sync_id or student.id
        with self._connection:
            self._connection.execute(
                """
                UPDATE students
                SET classroom_id = ?, first_name = ?, last_name = ?, middle_name = ?,
                    student_code = ?, notes = ?, updated_at = ?, sync_id = ?, sync_state = ?
                WHERE id = ?
                """,
                (
                    student.classroom_id,
                    student.first_name,
                    student.last_name,
                    student.middle_name,
                    student.student_code,
                    student.notes,
                    datetime.now(timezone.utc).isoformat(),
                    sync_id,
                    SyncState.PENDING_UPLOAD.value,
                    student.id,
                ),
            )
        self._enqueue(sync_id, OutboxOperation.UPSERT)

    def archive(self, student_id: str, role: UserRole, archived: bool = True) -> None:
        ensure_can_manage_classroom_data(role)
        new_state = SyncState.PENDING_DELETE if archived else SyncState.PENDING_UPLOAD
        with self._connection:
            self._connection.execute(
                "UPDATE students SET is_archived = ?, updated_at = ?, sync_state = ? WHERE id = ?",
                (1 if archived else 0, datetime.now(timezone.utc).isoformat(), new_state.value, student_id),
            )
        existing = self.get(student_id)
        if existing is not None:
            operation = OutboxOperation.DELETE if archived else OutboxOperation.UPSERT
            self._enqueue(existing.sync_id, operation)

    def get(self, student_id: str) -> Student | None:
        row = self._connection.execute(
            f"SELECT {_SELECT_COLUMNS} FROM students WHERE id = ?", (student_id,)
        ).fetchone()
        return self._row_to_student(row) if row is not None else None

    def list_by_classroom(self, classroom_id: str, include_archived: bool = False) -> tuple[Student, ...]:
        if include_archived:
            rows = self._connection.execute(
                f"SELECT {_SELECT_COLUMNS} FROM students WHERE classroom_id = ? "
                "ORDER BY last_name, first_name",
                (classroom_id,),
            ).fetchall()
        else:
            rows = self._connection.execute(
                f"SELECT {_SELECT_COLUMNS} FROM students WHERE classroom_id = ? AND is_archived = 0 "
                "ORDER BY last_name, first_name",
                (classroom_id,),
            ).fetchall()
        return tuple(self._row_to_student(row) for row in rows)

    def search(self, classroom_id: str, query: str) -> tuple[Student, ...]:
        # Python-дың ``str.lower()``-і қолданылады (SQLite-тің құрылымдық
        # ``lower()`` функциясы Юникод/кирилл әріптерін дұрыс
        # регистрсіздендірмейді, тек ASCII) — сүзгі СОЛ себепті Python
        # деңгейінде, SQL деңгейінде ЕМЕС жасалады.
        needle = query.lower()
        candidates = self.list_by_classroom(classroom_id, include_archived=False)
        return tuple(
            student
            for student in candidates
            if needle in f"{student.first_name} {student.last_name}".lower()
            or needle in f"{student.last_name} {student.first_name}".lower()
            or needle in student.student_code.lower()
        )

    def code_exists(self, student_code: str, exclude_student_id: str | None = None) -> bool:
        if not student_code:
            return False
        row = self._connection.execute(
            "SELECT 1 FROM students WHERE student_code = ? AND is_archived = 0 AND id != ? LIMIT 1",
            (student_code, exclude_student_id or ""),
        ).fetchone()
        return row is not None

    def get_by_code(self, student_code: str) -> Student | None:
        # § "trim whitespace" — шақырушы (UI) да қырқады, бірақ репозиторий
        # деңгейінде ЕКІНШІ, тәуелсіз қорғаныс сызығы ретінде қайталанады.
        normalized = student_code.strip()
        if not normalized:
            return None
        row = self._connection.execute(
            f"SELECT {_SELECT_COLUMNS} FROM students WHERE student_code = ? AND is_archived = 0",
            (normalized,),
        ).fetchone()
        return self._row_to_student(row) if row is not None else None

    # ---- Sync foundation (Offline-First + Cloud Sync Foundation) ---------

    def _enqueue(self, sync_id: str, operation: OutboxOperation) -> None:
        if self._sync_outbox_repository is None:
            return
        self._sync_outbox_repository.enqueue(_ENTITY_TYPE, sync_id, operation)

    def apply_remote_upsert(self, student: Student) -> None:
        """§18 "Pull Sync" — ``SqliteClassroomRepository.apply_remote_
        upsert()``-пен БІРДЕЙ принцип (§ сол докстрингі)."""
        existing = self.get(student.sync_id)
        with self._connection:
            if existing is None:
                self._connection.execute(
                    """
                    INSERT INTO students
                        (id, classroom_id, first_name, last_name, middle_name, student_code,
                         notes, is_archived, created_at, updated_at, sync_id, sync_state, server_revision)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        student.sync_id, student.classroom_id, student.first_name, student.last_name,
                        student.middle_name, student.student_code, student.notes,
                        1 if student.is_archived else 0, student.created_at.isoformat(),
                        student.updated_at.isoformat(), student.sync_id, SyncState.SYNCED.value,
                        student.server_revision,
                    ),
                )
            else:
                self._connection.execute(
                    """
                    UPDATE students
                    SET classroom_id = ?, first_name = ?, last_name = ?, middle_name = ?,
                        student_code = ?, notes = ?, is_archived = ?, updated_at = ?,
                        sync_state = ?, server_revision = ?
                    WHERE sync_id = ?
                    """,
                    (
                        student.classroom_id, student.first_name, student.last_name, student.middle_name,
                        student.student_code, student.notes, 1 if student.is_archived else 0,
                        student.updated_at.isoformat(), SyncState.SYNCED.value, student.server_revision,
                        student.sync_id,
                    ),
                )

    def mark_synced(self, student_id: str, server_revision: int) -> None:
        with self._connection:
            self._connection.execute(
                "UPDATE students SET sync_state = ?, server_revision = ? WHERE id = ?",
                (SyncState.SYNCED.value, server_revision, student_id),
            )

    @staticmethod
    def _row_to_student(row: tuple) -> Student:
        (
            id_, classroom_id, first_name, last_name, middle_name, student_code,
            notes, is_archived, created_at, updated_at, sync_id, sync_state, server_revision,
        ) = row
        return Student(
            id=id_,
            classroom_id=classroom_id,
            first_name=first_name,
            last_name=last_name,
            middle_name=middle_name,
            student_code=student_code,
            notes=notes,
            is_archived=bool(is_archived),
            created_at=datetime.fromisoformat(created_at),
            updated_at=datetime.fromisoformat(updated_at),
            sync_id=sync_id,
            sync_state=SyncState(sync_state),
            server_revision=server_revision,
        )
