"""SqliteFeedbackRepository — ``IFeedbackRepository``-дің sqlite3
қолданатын іске асыруы (Phase 39A).

``SqliteSessionRepository``-мен БІРДЕЙ пішін: ``db_path=":memory:"``
әдепкі (сынақтар/берілмеген жол — нақты пайдаланушы дерегіне ЕШҚАШАН
тимейді), нақты файл жолын тек ``app.py`` ғана береді. Raw
``measurements``/``experiment_sessions`` кестелерін ешқашан оқымайды/
жазбайды — тек ``experiment_feedback`` кестесімен жұмыс істейді.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from domain.entities.experiment_feedback_result import (
    ExperimentFeedbackResult,
    MultipleChoiceAnswer,
    OpenResponseAnswer,
    ReflectionAnswer,
    TeacherAssessment,
)
from domain.entities.outbox_entry import OutboxOperation
from domain.entities.sync_state import SyncState
from domain.entities.user_role import UserRole
from domain.interfaces.i_feedback_repository import IFeedbackRepository
from domain.interfaces.i_sync_outbox_repository import ISyncOutboxRepository
from infrastructure.storage.database import initialize_schema

_ENTITY_TYPE_FEEDBACK_RESULT = "feedback_result"
_ENTITY_TYPE_TEACHER_ASSESSMENT = "teacher_assessment"


class SqliteFeedbackRepository(IFeedbackRepository):
    """Сессия бойынша (``session_id`` PRIMARY KEY) кері байланыс
    жазбаларын sqlite файлына/жадына сақтайды.
    """

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
        """Байланысты жабады (тек тесттер/қолмен тазалау үшін)."""
        self._connection.close()

    # ---- IFeedbackRepository ------------------------------------------------

    def save_draft(self, result: ExperimentFeedbackResult) -> None:
        self._save(result, is_draft=True)

    def save_submission(self, result: ExperimentFeedbackResult) -> None:
        self._save(result, is_draft=False)

    def get_result(self, session_id: str) -> ExperimentFeedbackResult | None:
        row = self._connection.execute(
            """
            SELECT experiment_id, is_draft, level1_answers_json, level1_score,
                   level1_total, level1_percentage, level2_answers_json,
                   level3_answers_json, self_assessment, submitted_at,
                   teacher_score, teacher_comment, teacher_reviewed
            FROM experiment_feedback WHERE session_id = ?
            """,
            (session_id,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_result(session_id, row)

    def save_teacher_assessment(
        self,
        session_id: str,
        experiment_id: str,
        teacher_assessment: TeacherAssessment,
        role: UserRole,
    ) -> None:
        if role is not UserRole.TEACHER:
            raise PermissionError(
                "Мұғалім бағасын тек Мұғалім режимінде сақтауға болады"
            )
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connection:
            existing = self._connection.execute(
                "SELECT created_at FROM experiment_feedback WHERE session_id = ?",
                (session_id,),
            ).fetchone()

            if existing is None:
                # Студент әлі ешбір жоба/жіберу сақтамаған — Мұғалім
                # сонда да бағалай алуы үшін бос (толтырылмаған) жазба
                # алдын ала жасалады (§ "Teacher mode can... open the
                # same experiment feedback result" — жалған level1/2/3
                # дерек ЕШҚАШАН толтырылмайды, тек бос tuple/0). Феедбек
                # жағының sync_state ӘДЕЙІ ``pending_upload`` (§ ADD
                # COLUMN әдепкісімен БІРДЕЙ) — бос жоба студент жіберген
                # ЕМЕС, БІРАҚ жол ӨЗІ жаңа, серверге белгілі ЕМЕС.
                self._connection.execute(
                    """
                    INSERT INTO experiment_feedback
                        (session_id, experiment_id, is_draft, level1_answers_json,
                         level1_score, level1_total, level1_percentage,
                         level2_answers_json, level3_answers_json, self_assessment,
                         submitted_at, teacher_score, teacher_comment, teacher_reviewed,
                         created_at, updated_at, sync_state)
                    VALUES (?, ?, 1, '[]', 0, 0, 0.0, '[]', '[]', NULL, NULL, NULL, NULL, 0, ?, ?, ?)
                    """,
                    (session_id, experiment_id, now_iso, now_iso, SyncState.PENDING_UPLOAD.value),
                )

            self._connection.execute(
                """
                UPDATE experiment_feedback
                SET teacher_score = ?, teacher_comment = ?, teacher_reviewed = ?,
                    updated_at = ?, teacher_sync_state = ?
                WHERE session_id = ?
                """,
                (
                    teacher_assessment.score,
                    teacher_assessment.comment,
                    1 if teacher_assessment.reviewed else 0,
                    now_iso,
                    SyncState.PENDING_UPLOAD.value,
                    session_id,
                ),
            )
        self._enqueue(_ENTITY_TYPE_TEACHER_ASSESSMENT, session_id)

    # ---- Ішкі логика ---------------------------------------------------------

    def _save(self, result: ExperimentFeedbackResult, is_draft: bool) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connection:
            existing = self._connection.execute(
                "SELECT created_at, teacher_score, teacher_comment, teacher_reviewed, "
                "teacher_sync_state, teacher_server_revision, server_revision "
                "FROM experiment_feedback WHERE session_id = ?",
                (result.session_id,),
            ).fetchone()
            created_at = existing[0] if existing is not None else now_iso
            # Level1/2/3 жауаптарын қайта сақтау мұғалімнің бұрын қойған
            # бағасын (ЖӘНЕ оның sync күйін) ЕШҚАШАН жоймауы тиіс (екі
            # жазба тәуелсіз шақырылады, § сол принцип sync-те де).
            teacher_score = existing[1] if existing is not None else None
            teacher_comment = existing[2] if existing is not None else None
            teacher_reviewed = existing[3] if existing is not None else 0
            teacher_sync_state = (
                existing[4] if existing is not None else SyncState.PENDING_UPLOAD.value
            )
            teacher_server_revision = existing[5] if existing is not None else None
            # § "INSERT OR REPLACE толық жол алмастырады" — тізімде жоқ
            # баған сақталмайды, сондықтан feedback ЖАҚТЫҢ ӨЗ бұрынғы
            # ``server_revision``-ын да ЖОҒАЛТПАУ үшін нақты оқып алынады
            # (§ ``teacher_server_revision``-мен БІРДЕЙ себеп).
            feedback_server_revision = existing[6] if existing is not None else None

            submitted_at = (
                result.submitted_at.isoformat()
                if result.submitted_at is not None
                else (None if is_draft else now_iso)
            )

            self._connection.execute(
                """
                INSERT OR REPLACE INTO experiment_feedback
                    (session_id, experiment_id, is_draft, level1_answers_json,
                     level1_score, level1_total, level1_percentage,
                     level2_answers_json, level3_answers_json, self_assessment,
                     submitted_at, teacher_score, teacher_comment, teacher_reviewed,
                     created_at, updated_at, sync_state, server_revision,
                     teacher_sync_state, teacher_server_revision)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.session_id,
                    result.experiment_id,
                    1 if is_draft else 0,
                    json.dumps(
                        [
                            {"question_id": a.question_id, "selected_option_index": a.selected_option_index}
                            for a in result.level1_answers
                        ]
                    ),
                    result.level1_score,
                    result.level1_total,
                    result.level1_percentage,
                    json.dumps(
                        [{"question_id": a.question_id, "response_text": a.response_text} for a in result.level2_answers]
                    ),
                    json.dumps(
                        [{"question_id": a.question_id, "response_text": a.response_text} for a in result.level3_answers]
                    ),
                    result.self_assessment,
                    submitted_at,
                    teacher_score,
                    teacher_comment,
                    teacher_reviewed,
                    created_at,
                    now_iso,
                    SyncState.PENDING_UPLOAD.value,
                    feedback_server_revision,
                    teacher_sync_state,
                    teacher_server_revision,
                ),
            )
        self._enqueue(_ENTITY_TYPE_FEEDBACK_RESULT, result.session_id)

    # ---- Cloud Sync (Phase 2) -------------------------------------------

    def _enqueue(self, entity_type: str, session_id: str) -> None:
        if self._sync_outbox_repository is None:
            return
        self._sync_outbox_repository.enqueue(entity_type, session_id, OutboxOperation.UPSERT)

    def enqueue_feedback_for_sync(self, session_id: str) -> None:
        self._enqueue(_ENTITY_TYPE_FEEDBACK_RESULT, session_id)

    def enqueue_teacher_assessment_for_sync(self, session_id: str) -> None:
        self._enqueue(_ENTITY_TYPE_TEACHER_ASSESSMENT, session_id)

    def get_feedback_sync_payload(self, session_id: str) -> dict | None:
        row = self._connection.execute(
            """
            SELECT experiment_id, is_draft, level1_answers_json, level1_score,
                   level1_total, level1_percentage, level2_answers_json,
                   level3_answers_json, self_assessment, submitted_at,
                   created_at, updated_at, sync_state, server_revision
            FROM experiment_feedback WHERE session_id = ?
            """,
            (session_id,),
        ).fetchone()
        if row is None:
            return None
        (
            experiment_id, is_draft, level1_answers_json, level1_score, level1_total,
            level1_percentage, level2_answers_json, level3_answers_json, self_assessment,
            submitted_at, created_at, updated_at, sync_state, server_revision,
        ) = row
        return {
            "sync_id": session_id,
            "experiment_id": experiment_id,
            "is_draft": bool(is_draft),
            "level1_answers": json.loads(level1_answers_json),
            "level1_score": level1_score,
            "level1_total": level1_total,
            "level1_percentage": level1_percentage,
            "level2_answers": json.loads(level2_answers_json),
            "level3_answers": json.loads(level3_answers_json),
            "self_assessment": self_assessment,
            "submitted_at": submitted_at,
            "created_at": created_at,
            "updated_at": updated_at,
            "sync_state": sync_state,
            "server_revision": server_revision,
        }

    def apply_remote_feedback(self, payload: dict) -> None:
        """§18 "Pull Sync" — тек оқушы авторлық бағандарды жазады,
        мұғалім бағандарын (ЖӘНЕ олардың sync күйін) ЕШҚАШАН тимейді
        (§ ``_save()``-пен БІРДЕЙ read-preserve принципі). ЕШБІР outbox
        жазуы ЖАСАЛМАЙДЫ."""
        session_id = payload["sync_id"]
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connection:
            existing = self._connection.execute(
                "SELECT teacher_score, teacher_comment, teacher_reviewed, "
                "teacher_sync_state, teacher_server_revision "
                "FROM experiment_feedback WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            teacher_score = existing[0] if existing is not None else None
            teacher_comment = existing[1] if existing is not None else None
            teacher_reviewed = existing[2] if existing is not None else 0
            teacher_sync_state = (
                existing[3] if existing is not None else SyncState.PENDING_UPLOAD.value
            )
            teacher_server_revision = existing[4] if existing is not None else None

            self._connection.execute(
                """
                INSERT OR REPLACE INTO experiment_feedback
                    (session_id, experiment_id, is_draft, level1_answers_json,
                     level1_score, level1_total, level1_percentage,
                     level2_answers_json, level3_answers_json, self_assessment,
                     submitted_at, teacher_score, teacher_comment, teacher_reviewed,
                     created_at, updated_at, sync_state, server_revision,
                     teacher_sync_state, teacher_server_revision)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    payload["experiment_id"],
                    1 if payload["is_draft"] else 0,
                    json.dumps(payload["level1_answers"]),
                    payload["level1_score"],
                    payload["level1_total"],
                    payload["level1_percentage"],
                    json.dumps(payload["level2_answers"]),
                    json.dumps(payload["level3_answers"]),
                    payload.get("self_assessment"),
                    payload.get("submitted_at"),
                    teacher_score,
                    teacher_comment,
                    teacher_reviewed,
                    payload.get("created_at", now_iso),
                    payload["updated_at"],
                    SyncState.SYNCED.value,
                    payload.get("server_revision"),
                    teacher_sync_state,
                    teacher_server_revision,
                ),
            )

    def mark_feedback_synced(self, session_id: str, server_revision: int) -> None:
        with self._connection:
            self._connection.execute(
                "UPDATE experiment_feedback SET sync_state = ?, server_revision = ? WHERE session_id = ?",
                (SyncState.SYNCED.value, server_revision, session_id),
            )

    def get_teacher_assessment_sync_payload(self, session_id: str) -> dict | None:
        row = self._connection.execute(
            "SELECT teacher_score, teacher_comment, teacher_reviewed, updated_at, "
            "teacher_sync_state, teacher_server_revision "
            "FROM experiment_feedback WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            return None
        teacher_score, teacher_comment, teacher_reviewed, updated_at, sync_state, server_revision = row
        if teacher_score is None:
            return None  # § әлі бағаланбаған — синхрондауға ЕШБІР мән жоқ
        return {
            "sync_id": session_id,
            "score": teacher_score,
            "comment": teacher_comment or "",
            "reviewed": bool(teacher_reviewed),
            "updated_at": updated_at,
            "sync_state": sync_state,
            "server_revision": server_revision,
        }

    def apply_remote_teacher_assessment(self, payload: dict) -> None:
        """§18 "Pull Sync" — тек мұғалім бағандарын жазады, оқушы
        авторлық бағандарды ЕШҚАШАН тимейді (§ ``save_teacher_
        assessment()``-пен БІРДЕЙ pre-insert-empty-draft принципі,
        студент әлі ешбір жоба сақтамаған машинада да қолданылуы үшін).
        ЕШБІР outbox жазуы ЖАСАЛМАЙДЫ."""
        session_id = payload["sync_id"]
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connection:
            existing = self._connection.execute(
                "SELECT created_at FROM experiment_feedback WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if existing is None:
                # § Сирек шеткі жағдай: бұл машинада ЕШБІР feedback_result
                # әлі белгісіз, БІРАҚ teacher_assessment пайда болды (мыс.
                # PUSH_ORDER-дегі "feedback_result" осы циклде табылмады).
                # ``experiment_id`` бос қалдырылады — "feedback_result"
                # синхрондалғанда (§ ``apply_remote_feedback()``) INSERT OR
                # REPLACE арқылы дұрыс мәнге ауысады (өздігінен түзетіледі).
                self._connection.execute(
                    """
                    INSERT INTO experiment_feedback
                        (session_id, experiment_id, is_draft, level1_answers_json,
                         level1_score, level1_total, level1_percentage,
                         level2_answers_json, level3_answers_json, self_assessment,
                         submitted_at, teacher_score, teacher_comment, teacher_reviewed,
                         created_at, updated_at, sync_state)
                    VALUES (?, '', 1, '[]', 0, 0, 0.0, '[]', '[]', NULL, NULL, NULL, NULL, 0, ?, ?, ?)
                    """,
                    (session_id, now_iso, now_iso, SyncState.PENDING_UPLOAD.value),
                )

            self._connection.execute(
                """
                UPDATE experiment_feedback
                SET teacher_score = ?, teacher_comment = ?, teacher_reviewed = ?,
                    teacher_sync_state = ?, teacher_server_revision = ?
                WHERE session_id = ?
                """,
                (
                    payload["score"],
                    payload["comment"],
                    1 if payload["reviewed"] else 0,
                    SyncState.SYNCED.value,
                    payload.get("server_revision"),
                    session_id,
                ),
            )

    def mark_teacher_assessment_synced(self, session_id: str, server_revision: int) -> None:
        with self._connection:
            self._connection.execute(
                "UPDATE experiment_feedback SET teacher_sync_state = ?, teacher_server_revision = ? "
                "WHERE session_id = ?",
                (SyncState.SYNCED.value, server_revision, session_id),
            )

    @staticmethod
    def _row_to_result(session_id: str, row: tuple) -> ExperimentFeedbackResult:
        (
            experiment_id,
            is_draft,
            level1_answers_json,
            level1_score,
            level1_total,
            level1_percentage,
            level2_answers_json,
            level3_answers_json,
            self_assessment,
            submitted_at,
            teacher_score,
            teacher_comment,
            teacher_reviewed,
        ) = row

        level1_answers = tuple(
            MultipleChoiceAnswer(
                question_id=item["question_id"], selected_option_index=item["selected_option_index"]
            )
            for item in json.loads(level1_answers_json)
        )
        level2_answers = tuple(
            OpenResponseAnswer(question_id=item["question_id"], response_text=item["response_text"])
            for item in json.loads(level2_answers_json)
        )
        level3_answers = tuple(
            ReflectionAnswer(question_id=item["question_id"], response_text=item["response_text"])
            for item in json.loads(level3_answers_json)
        )

        teacher_assessment = (
            TeacherAssessment(
                score=teacher_score,
                comment=teacher_comment or "",
                reviewed=bool(teacher_reviewed),
            )
            if teacher_score is not None
            else None
        )

        return ExperimentFeedbackResult(
            experiment_id=experiment_id,
            session_id=session_id,
            level1_answers=level1_answers,
            level1_score=level1_score,
            level1_total=level1_total,
            level1_percentage=level1_percentage,
            level2_answers=level2_answers,
            level3_answers=level3_answers,
            self_assessment=self_assessment,
            is_draft=bool(is_draft),
            submitted_at=datetime.fromisoformat(submitted_at) if submitted_at is not None else None,
            teacher_assessment=teacher_assessment,
        )
