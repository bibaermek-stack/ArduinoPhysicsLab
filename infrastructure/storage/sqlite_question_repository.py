"""SqliteQuestionRepository — ``IQuestionRepository``-дің sqlite3
қолданатын іске асыруы (Phase 20).

``SqliteFeedbackRepository``-мен БІРДЕЙ пішін: ``db_path=":memory:"``
әдепкі (сынақтар/берілмеген жол — нақты пайдаланушы дерегіне ЕШҚАШАН
тимейді), нақты файл жолын тек ``app.py`` ғана береді. Level 1 (тест)
сұрағының ``options``/``correct_option_index`` өрістері JSON/INTEGER
бағаны ретінде сақталады — 2/3-деңгейде NULL.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from domain.entities.experiment_assessment import (
    MultipleChoiceQuestion,
    OpenResponseQuestion,
    ReflectionQuestion,
)
from domain.entities.question_record import QuestionContent, QuestionRecord
from domain.entities.user_role import UserRole
from domain.interfaces.i_question_repository import IQuestionRepository
from domain.services.student_access_control import ensure_can_manage_questions
from infrastructure.storage.database import initialize_schema

_SELECT_COLUMNS = (
    "id, experiment_id, level, prompt, options_json, correct_option_index, "
    "points, is_active, created_at"
)


class SqliteQuestionRepository(IQuestionRepository):
    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self._db_path = str(db_path)
        self._connection = sqlite3.connect(self._db_path)
        initialize_schema(self._connection)

    def close(self) -> None:
        self._connection.close()

    # ---- IQuestionRepository ------------------------------------------------

    def create(self, record: QuestionRecord, role: UserRole) -> None:
        ensure_can_manage_questions(role)
        now_iso = datetime.now(timezone.utc).isoformat()
        options_json, correct_option_index, points = self._level1_fields(record.question)
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO questions
                    (id, experiment_id, level, prompt, options_json, correct_option_index,
                     points, is_active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id, record.experiment_id, record.level, record.question.prompt,
                    options_json, correct_option_index, points,
                    1 if record.is_active else 0, record.created_at.isoformat(), now_iso,
                ),
            )

    def update(self, record: QuestionRecord, role: UserRole) -> None:
        ensure_can_manage_questions(role)
        now_iso = datetime.now(timezone.utc).isoformat()
        options_json, correct_option_index, points = self._level1_fields(record.question)
        with self._connection:
            self._connection.execute(
                """
                UPDATE questions
                SET experiment_id = ?, level = ?, prompt = ?, options_json = ?,
                    correct_option_index = ?, points = ?, is_active = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    record.experiment_id, record.level, record.question.prompt,
                    options_json, correct_option_index, points,
                    1 if record.is_active else 0, now_iso, record.id,
                ),
            )

    def archive(self, question_id: str, role: UserRole, archived: bool = True) -> None:
        ensure_can_manage_questions(role)
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connection:
            self._connection.execute(
                "UPDATE questions SET is_active = ?, updated_at = ? WHERE id = ?",
                (0 if archived else 1, now_iso, question_id),
            )

    def get(self, question_id: str) -> QuestionRecord | None:
        row = self._connection.execute(
            f"SELECT {_SELECT_COLUMNS} FROM questions WHERE id = ?", (question_id,)
        ).fetchone()
        return self._row_to_record(row) if row is not None else None

    def list_all(self, include_archived: bool = False) -> tuple[QuestionRecord, ...]:
        query = f"SELECT {_SELECT_COLUMNS} FROM questions"
        if not include_archived:
            query += " WHERE is_active = 1"
        query += " ORDER BY experiment_id, level, created_at, rowid"
        rows = self._connection.execute(query).fetchall()
        return tuple(self._row_to_record(row) for row in rows)

    def list_for_experiment(
        self, experiment_id: str, include_archived: bool = False
    ) -> tuple[QuestionRecord, ...]:
        query = f"SELECT {_SELECT_COLUMNS} FROM questions WHERE experiment_id = ?"
        if not include_archived:
            query += " AND is_active = 1"
        query += " ORDER BY level, created_at, rowid"
        rows = self._connection.execute(query, (experiment_id,)).fetchall()
        return tuple(self._row_to_record(row) for row in rows)

    # ---- Ішкі логика ---------------------------------------------------------

    @staticmethod
    def _level1_fields(question: QuestionContent) -> tuple[str | None, int | None, int]:
        if isinstance(question, MultipleChoiceQuestion):
            return json.dumps(list(question.options)), question.correct_option_index, question.points
        return None, None, 1

    @staticmethod
    def _row_to_record(row: tuple) -> QuestionRecord:
        (
            question_id, experiment_id, level, prompt, options_json,
            correct_option_index, points, is_active, created_at,
        ) = row

        question: QuestionContent
        if level == 1:
            options = tuple(json.loads(options_json)) if options_json is not None else ()
            question = MultipleChoiceQuestion(
                id=question_id, prompt=prompt, options=options,
                correct_option_index=correct_option_index or 0, points=points,
            )
        elif level == 2:
            question = OpenResponseQuestion(id=question_id, prompt=prompt)
        else:
            question = ReflectionQuestion(id=question_id, prompt=prompt)

        return QuestionRecord(
            id=question_id,
            experiment_id=experiment_id,
            level=level,
            question=question,
            is_active=bool(is_active),
            created_at=datetime.fromisoformat(created_at),
        )
