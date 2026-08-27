"""SqliteActiveTeacherRepository — ``IActiveTeacherRepository``-дің
sqlite3 қолданатын іске асыруы (Multi-Teacher Accounts фазасы).

``SqliteActiveStudentRepository``-мен БІРДЕЙ жалғыз жол кестесі өрнегі
(``active_teacher_state``, ``id=1``).
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from domain.entities.active_teacher_context import ActiveTeacherContext
from domain.interfaces.i_active_teacher_repository import IActiveTeacherRepository
from infrastructure.storage.database import initialize_schema


class SqliteActiveTeacherRepository(IActiveTeacherRepository):
    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self._db_path = str(db_path)
        self._connection = sqlite3.connect(self._db_path)
        initialize_schema(self._connection)

    def close(self) -> None:
        self._connection.close()

    def set(self, context: ActiveTeacherContext) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO active_teacher_state (id, teacher_id, updated_at)
                VALUES (1, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    teacher_id = excluded.teacher_id,
                    updated_at = excluded.updated_at
                """,
                (context.teacher_id, now_iso),
            )

    def get(self) -> ActiveTeacherContext | None:
        row = self._connection.execute(
            "SELECT teacher_id FROM active_teacher_state WHERE id = 1"
        ).fetchone()
        if row is None or row[0] is None:
            return None
        return ActiveTeacherContext(teacher_id=row[0])

    def clear(self) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO active_teacher_state (id, teacher_id, updated_at)
                VALUES (1, NULL, ?)
                ON CONFLICT(id) DO UPDATE SET
                    teacher_id = NULL, updated_at = excluded.updated_at
                """,
                (now_iso,),
            )
