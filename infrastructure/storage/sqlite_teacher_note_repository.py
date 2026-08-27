"""SqliteTeacherNoteRepository — ``ITeacherNoteRepository``-дің sqlite3
қолданатын іске асыруы (Phase 7).

``SqliteFeedbackRepository``-мен БІРДЕЙ пішін: ``db_path=":memory:"``
әдепкі, нақты файл жолын тек ``app.py``/``SyncWorker`` ғана береді.
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from domain.entities.outbox_entry import OutboxOperation
from domain.entities.sync_state import SyncState
from domain.entities.teacher_note import TeacherNote
from domain.entities.user_role import UserRole
from domain.interfaces.i_sync_outbox_repository import ISyncOutboxRepository
from domain.interfaces.i_teacher_note_repository import ITeacherNoteRepository
from infrastructure.storage.database import initialize_schema

_ENTITY_TYPE_TEACHER_NOTE = "teacher_note"


class SqliteTeacherNoteRepository(ITeacherNoteRepository):
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

    # ---- ITeacherNoteRepository -------------------------------------------

    def create(self, note: TeacherNote, role: UserRole) -> None:
        if role is not UserRole.TEACHER:
            raise PermissionError("Пікірді тек Мұғалім режимінде жіберуге болады")
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO teacher_notes
                    (id, teacher_id, student_id, classroom_id, experiment_id,
                     session_id, message, created_at, read_at, sync_state, server_revision)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, NULL)
                """,
                (
                    note.id,
                    note.teacher_id,
                    note.student_id,
                    note.classroom_id,
                    note.experiment_id,
                    note.session_id,
                    note.message,
                    note.created_at.isoformat(),
                    SyncState.PENDING_UPLOAD.value,
                ),
            )
        self._enqueue(note.id)

    def list_for_student(self, student_id: str) -> tuple[TeacherNote, ...]:
        rows = self._connection.execute(
            """
            SELECT id, teacher_id, student_id, classroom_id, experiment_id,
                   session_id, message, created_at, read_at, sync_state
            FROM teacher_notes WHERE student_id = ? ORDER BY created_at
            """,
            (student_id,),
        ).fetchall()
        return tuple(self._row_to_note(row) for row in rows)

    def mark_read(self, note_id: str, role: UserRole) -> None:
        if role is not UserRole.STUDENT:
            raise PermissionError("Пікірді тек Оқушы режимінде оқылды деп белгілеуге болады")
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connection:
            # § идемпотентті — әлдеқашан оқылған жазба ЕШҚАШАН қайта
            # жазылмайды (§ "repeated sync must not regress read state").
            self._connection.execute(
                "UPDATE teacher_notes SET read_at = ? WHERE id = ? AND read_at IS NULL",
                (now_iso, note_id),
            )

    # ---- Ішкі логика -------------------------------------------------------

    @staticmethod
    def _row_to_note(row: tuple) -> TeacherNote:
        (
            note_id, teacher_id, student_id, classroom_id, experiment_id,
            session_id, message, created_at, read_at, sync_state,
        ) = row
        return TeacherNote(
            id=note_id,
            teacher_id=teacher_id,
            student_id=student_id,
            classroom_id=classroom_id,
            message=message,
            created_at=datetime.fromisoformat(created_at),
            experiment_id=experiment_id,
            session_id=session_id,
            read_at=datetime.fromisoformat(read_at) if read_at is not None else None,
            sync_state=SyncState(sync_state),
        )

    # ---- Cloud Sync (Phase 7) -----------------------------------------------

    def _enqueue(self, note_id: str) -> None:
        if self._sync_outbox_repository is None:
            return
        self._sync_outbox_repository.enqueue(_ENTITY_TYPE_TEACHER_NOTE, note_id, OutboxOperation.UPSERT)

    def enqueue_note_for_sync(self, note_id: str) -> None:
        self._enqueue(note_id)

    def get_note_sync_payload(self, note_id: str) -> dict | None:
        row = self._connection.execute(
            """
            SELECT teacher_id, student_id, classroom_id, experiment_id, session_id,
                   message, created_at, sync_state, server_revision
            FROM teacher_notes WHERE id = ?
            """,
            (note_id,),
        ).fetchone()
        if row is None:
            return None
        (
            teacher_id, student_id, classroom_id, experiment_id, session_id,
            message, created_at, sync_state, server_revision,
        ) = row
        return {
            "sync_id": note_id,
            "teacher_sync_id": teacher_id,
            "student_sync_id": student_id,
            "classroom_sync_id": classroom_id,
            "experiment_id": experiment_id,
            "session_sync_id": session_id,
            "message": message,
            "created_at": created_at,
            "sync_state": sync_state,
            "server_revision": server_revision,
        }

    def apply_remote_note(self, payload: dict) -> None:
        """§18 "Pull Sync" — ЕШБІР outbox жазуы ЖАСАЛМАЙДЫ. ``read_at``
        (жергілікті-тек) ЕШҚАШАН осы payload-та ЖОҚ, сондықтан
        ЕСКІ жергілікті мәнін МІНДЕТТІ түрде сақтап қалады (§ "student's
        own local read state must never be clobbered by a pull",
        ``experiment_feedback``-тегі read-preserve паттерні)."""
        note_id = payload["sync_id"]
        existing_read_at = self._connection.execute(
            "SELECT read_at FROM teacher_notes WHERE id = ?", (note_id,)
        ).fetchone()
        read_at = existing_read_at[0] if existing_read_at is not None else None
        with self._connection:
            self._connection.execute(
                """
                INSERT OR REPLACE INTO teacher_notes
                    (id, teacher_id, student_id, classroom_id, experiment_id,
                     session_id, message, created_at, read_at, sync_state, server_revision)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    note_id,
                    payload["teacher_sync_id"],
                    payload["student_sync_id"],
                    payload["classroom_sync_id"],
                    payload.get("experiment_id"),
                    payload.get("session_sync_id"),
                    payload["message"],
                    payload["created_at"],
                    read_at,
                    SyncState.SYNCED.value,
                    payload.get("server_revision"),
                ),
            )

    def mark_note_synced(self, note_id: str, server_revision: int) -> None:
        with self._connection:
            self._connection.execute(
                "UPDATE teacher_notes SET sync_state = ?, server_revision = ? WHERE id = ?",
                (SyncState.SYNCED.value, server_revision, note_id),
            )
