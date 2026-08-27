"""SqliteActiveStudentRepository — ``IActiveStudentRepository``-дің
sqlite3 қолданатын іске асыруы (Phase 39B).

Жалғыз жол кестесі (``active_student_state``, ``id=1``) — қолданба іске
қосылған сайын соңғы таңдалған оқушыны есте сақтайды (§ "remains selected
during the current session"; қосымша артықшылық ретінде — қайта іске
қосудан кейін де сақталады, спецификация мұны тыймайды).
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from domain.entities.active_student_context import ActiveStudentContext
from domain.interfaces.i_active_student_repository import IActiveStudentRepository
from infrastructure.storage.database import initialize_schema


class SqliteActiveStudentRepository(IActiveStudentRepository):
    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self._db_path = str(db_path)
        self._connection = sqlite3.connect(self._db_path)
        initialize_schema(self._connection)

    def close(self) -> None:
        self._connection.close()

    def set(self, context: ActiveStudentContext) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO active_student_state (id, classroom_id, student_id, updated_at)
                VALUES (1, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    classroom_id = excluded.classroom_id,
                    student_id = excluded.student_id,
                    updated_at = excluded.updated_at
                """,
                (context.classroom_id, context.student_id, now_iso),
            )

    def get(self) -> ActiveStudentContext | None:
        row = self._connection.execute(
            "SELECT classroom_id, student_id FROM active_student_state WHERE id = 1"
        ).fetchone()
        if row is None or row[0] is None or row[1] is None:
            return None
        return ActiveStudentContext(classroom_id=row[0], student_id=row[1])

    def clear(self) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO active_student_state (id, classroom_id, student_id, updated_at)
                VALUES (1, NULL, NULL, ?)
                ON CONFLICT(id) DO UPDATE SET
                    classroom_id = NULL, student_id = NULL, updated_at = excluded.updated_at
                """,
                (now_iso,),
            )
