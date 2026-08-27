"""SqliteStudentProgressRepository — ``IStudentProgressRepository``-дің
sqlite3 қолданатын іске асыруы (Phase 39B).

Бұл репозиторий тек ``session_student_link`` кестесін иеленеді (жаңа
raw measurement/feedback кестесі ЖОҚ) — прогресс/дашборд сандарын
есептеу үшін бар ``ISessionRepository``/``IFeedbackRepository``/
``IClassroomRepository``/``IStudentRepository``-ді композиция арқылы
шақырады. ``StudentExperimentProgress`` ЕШҚАШАН материалдандырылмайды —
әр шақыруда НАҚТЫ жазбалардан қайта есептеледі (§ "status must be
derived from real persisted records").
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from domain.entities.classroom_activity_snapshot import ClassroomActivitySnapshot
from domain.entities.outbox_entry import OutboxOperation
from domain.entities.student_experiment_progress import (
    ProgressStatus,
    StudentExperimentProgress,
    derive_status,
)
from domain.entities.sync_state import SyncState
from domain.interfaces.i_classroom_repository import IClassroomRepository
from domain.interfaces.i_feedback_repository import IFeedbackRepository
from domain.interfaces.i_session_repository import ISessionRepository
from domain.interfaces.i_student_progress_repository import IStudentProgressRepository
from domain.interfaces.i_student_repository import IStudentRepository
from domain.interfaces.i_sync_outbox_repository import ISyncOutboxRepository
from infrastructure.storage.database import initialize_schema
from infrastructure.storage.sqlite_classroom_repository import SqliteClassroomRepository
from infrastructure.storage.sqlite_feedback_repository import SqliteFeedbackRepository
from infrastructure.storage.sqlite_session_repository import SqliteSessionRepository
from infrastructure.storage.sqlite_student_repository import SqliteStudentRepository

_ENTITY_TYPE_SESSION_STUDENT_LINK = "session_student_link"


class SqliteStudentProgressRepository(IStudentProgressRepository):
    def __init__(
        self,
        db_path: str | Path = ":memory:",
        session_repository: ISessionRepository | None = None,
        feedback_repository: IFeedbackRepository | None = None,
        classroom_repository: IClassroomRepository | None = None,
        student_repository: IStudentRepository | None = None,
        sync_outbox_repository: ISyncOutboxRepository | None = None,
    ) -> None:
        self._db_path = str(db_path)
        self._connection = sqlite3.connect(self._db_path)
        initialize_schema(self._connection)
        self._session_repository = session_repository or SqliteSessionRepository(db_path=db_path)
        self._feedback_repository = feedback_repository or SqliteFeedbackRepository(db_path=db_path)
        self._classroom_repository = classroom_repository or SqliteClassroomRepository(db_path=db_path)
        self._student_repository = student_repository or SqliteStudentRepository(db_path=db_path)
        self._sync_outbox_repository = sync_outbox_repository

    def close(self) -> None:
        self._connection.close()

    # ---- IStudentProgressRepository --------------------------------------

    def link_session(
        self, session_id: str, student_id: str, classroom_id: str, experiment_id: str
    ) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connection:
            self._connection.execute(
                """
                INSERT OR REPLACE INTO session_student_link
                    (session_id, student_id, classroom_id, experiment_id, linked_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, student_id, classroom_id, experiment_id, now_iso),
            )
        self._enqueue_link(session_id)

    def get_student_for_session(self, session_id: str) -> str | None:
        row = self._connection.execute(
            "SELECT student_id FROM session_student_link WHERE session_id = ?", (session_id,)
        ).fetchone()
        return row[0] if row is not None else None

    # ---- Cloud Sync (Phase 2) -------------------------------------------

    def _enqueue_link(self, session_id: str) -> None:
        if self._sync_outbox_repository is None:
            return
        self._sync_outbox_repository.enqueue(
            _ENTITY_TYPE_SESSION_STUDENT_LINK, session_id, OutboxOperation.UPSERT
        )

    def enqueue_link_for_sync(self, session_id: str) -> None:
        self._enqueue_link(session_id)

    def list_all_link_session_ids(self) -> tuple[str, ...]:
        rows = self._connection.execute("SELECT session_id FROM session_student_link").fetchall()
        return tuple(row[0] for row in rows)

    def get_link_sync_payload(self, session_id: str) -> dict | None:
        row = self._connection.execute(
            "SELECT student_id, classroom_id, experiment_id, linked_at, sync_state, server_revision "
            "FROM session_student_link WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            return None
        student_id, classroom_id, experiment_id, linked_at, sync_state, server_revision = row
        student = self._student_repository.get(student_id)
        classroom = self._classroom_repository.get(classroom_id)
        return {
            "session_sync_id": session_id,
            "student_sync_id": (student.sync_id or student.id) if student is not None else student_id,
            "classroom_sync_id": (classroom.sync_id or classroom.id) if classroom is not None else classroom_id,
            "experiment_id": experiment_id,
            "linked_at": linked_at,
            "sync_state": sync_state,
            "server_revision": server_revision,
        }

    def apply_remote_link(self, payload: dict) -> None:
        """§18 "Pull Sync" — ЕШБІР outbox жазуы ЖАСАЛМАЙДЫ. Global
        student_sync_id/classroom_sync_id-ды ЖЕРГІЛІКТІ id ретінде
        тікелей қолданады (§ established Phase 1 конвенциясы: pull
        арқылы алынған жазба ӘРҚАШАН ``id = sync_id``-мен жазылады,
        сондықтан кез-келген машинада ``id == sync_id`` инварианты
        сақталады)."""
        session_id = payload["session_sync_id"]
        with self._connection:
            self._connection.execute(
                """
                INSERT OR REPLACE INTO session_student_link
                    (session_id, student_id, classroom_id, experiment_id, linked_at,
                     sync_state, server_revision)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    payload["student_sync_id"],
                    payload["classroom_sync_id"],
                    payload["experiment_id"],
                    payload["linked_at"],
                    SyncState.SYNCED.value,
                    payload.get("server_revision"),
                ),
            )

    def mark_link_synced(self, session_id: str, server_revision: int) -> None:
        with self._connection:
            self._connection.execute(
                "UPDATE session_student_link SET sync_state = ?, server_revision = ? WHERE session_id = ?",
                (SyncState.SYNCED.value, server_revision, session_id),
            )

    def get_progress(self, student_id: str, experiment_id: str) -> StudentExperimentProgress:
        row = self._connection.execute(
            """
            SELECT session_id FROM session_student_link
            WHERE student_id = ? AND experiment_id = ?
            ORDER BY linked_at DESC, rowid DESC LIMIT 1
            """,
            (student_id, experiment_id),
        ).fetchone()
        if row is None:
            return StudentExperimentProgress(
                student_id=student_id, experiment_id=experiment_id, status=ProgressStatus.NOT_STARTED
            )
        session_id = row[0]

        summary = self._session_repository.get_session(session_id)
        measurement_count = summary.measurement_count if summary is not None else 0
        last_activity_at = summary.ended_at if summary is not None and summary.ended_at is not None else (
            summary.started_at if summary is not None else None
        )

        feedback_result = self._feedback_repository.get_result(session_id)
        status = derive_status(
            has_link=True, measurement_count=measurement_count, feedback_result=feedback_result
        )

        teacher_score = (
            feedback_result.teacher_assessment.score
            if feedback_result is not None and feedback_result.teacher_assessment is not None
            else None
        )
        teacher_reviewed = (
            feedback_result.teacher_assessment is not None
            if feedback_result is not None
            else False
        )

        return StudentExperimentProgress(
            student_id=student_id,
            experiment_id=experiment_id,
            status=status,
            latest_session_id=session_id,
            measurement_count=measurement_count,
            report_opened=feedback_result is not None,
            level1_score=feedback_result.level1_score if feedback_result is not None else None,
            level1_total=feedback_result.level1_total if feedback_result is not None else None,
            level1_percentage=feedback_result.level1_percentage if feedback_result is not None else None,
            self_assessment=feedback_result.self_assessment if feedback_result is not None else None,
            teacher_score=teacher_score,
            teacher_reviewed=teacher_reviewed,
            last_activity_at=last_activity_at,
            submitted_at=feedback_result.submitted_at if feedback_result is not None else None,
        )

    def list_progress_for_student(
        self, student_id: str, experiment_ids: tuple[str, ...]
    ) -> tuple[StudentExperimentProgress, ...]:
        return tuple(
            self.get_progress(student_id, experiment_id) for experiment_id in experiment_ids
        )

    def _select_pairs(self, allowed_classroom_ids: frozenset[str] | None = None) -> list[tuple]:
        """§ Multi-Teacher Accounts: ``session_student_link`` кестесінің
        ӨЗІНДЕ ``classroom_id`` бағаны бар болғандықтан (§ database.py
        схемасы), сынып бойынша сүзу үшін ЕШБІР қосымша JOIN қажет емес.
        ``allowed_classroom_ids=None`` — шектеусіз (ескі мінез-құлықпен
        бит-бітіне сәйкес, § backward compatibility)."""
        if allowed_classroom_ids is None:
            return self._connection.execute(
                "SELECT DISTINCT student_id, experiment_id FROM session_student_link"
            ).fetchall()
        if not allowed_classroom_ids:
            return []
        placeholders = ",".join("?" for _ in allowed_classroom_ids)
        return self._connection.execute(
            f"""
            SELECT DISTINCT student_id, experiment_id FROM session_student_link
            WHERE classroom_id IN ({placeholders})
            """,
            tuple(allowed_classroom_ids),
        ).fetchall()

    def compute_dashboard_counts(
        self, allowed_classroom_ids: frozenset[str] | None = None
    ) -> dict[str, int]:
        pairs = self._select_pairs(allowed_classroom_ids)

        completed = 0
        awaiting_review = 0
        for student_id, experiment_id in pairs:
            progress = self.get_progress(student_id, experiment_id)
            if progress.status in (
                ProgressStatus.MEASUREMENT_COMPLETED,
                ProgressStatus.REPORT_COMPLETED,
                ProgressStatus.FEEDBACK_SUBMITTED,
                ProgressStatus.REVIEWED,
            ):
                completed += 1
            if progress.status is ProgressStatus.FEEDBACK_SUBMITTED:
                awaiting_review += 1

        classrooms = [
            classroom
            for classroom in self._classroom_repository.list_active()
            if allowed_classroom_ids is None or classroom.id in allowed_classroom_ids
        ]
        return {
            "classrooms": len(classrooms),
            "students": sum(
                len(self._student_repository.list_by_classroom(classroom.id))
                for classroom in classrooms
            ),
            "completed": completed,
            "awaiting_review": awaiting_review,
        }

    def list_submitted_progress(
        self, allowed_classroom_ids: frozenset[str] | None = None
    ) -> tuple[StudentExperimentProgress, ...]:
        pairs = self._select_pairs(allowed_classroom_ids)

        results: list[StudentExperimentProgress] = []
        for student_id, experiment_id in pairs:
            progress = self.get_progress(student_id, experiment_id)
            if progress.status in (ProgressStatus.FEEDBACK_SUBMITTED, ProgressStatus.REVIEWED):
                results.append(progress)
        return tuple(results)

    def list_all_progress(
        self, allowed_classroom_ids: frozenset[str] | None = None
    ) -> tuple[StudentExperimentProgress, ...]:
        pairs = self._select_pairs(allowed_classroom_ids)
        return tuple(
            self.get_progress(student_id, experiment_id) for student_id, experiment_id in pairs
        )

    def compute_classroom_activity(
        self, allowed_classroom_ids: frozenset[str] | None = None
    ) -> tuple[ClassroomActivitySnapshot, ...]:
        snapshots: list[ClassroomActivitySnapshot] = []
        for classroom in self._classroom_repository.list_active():
            if allowed_classroom_ids is not None and classroom.id not in allowed_classroom_ids:
                continue
            # § "linked_at" секундтан кіші дәлдікте жазылады (§ Race
            # condition түзетуі) — екі сессия БІРДЕЙ миллисекундта
            # құрылса, ``ORDER BY latest DESC`` жалғыз өзі реттеуді
            # КЕПІЛДЕМЕЙДІ (SQLite тең мәндерде анықталмаған ретпен
            # қайтарады). ``MAX(rowid)`` (кірістіру реті бойынша
            # монотонды өсетін implicit баған) екінші тиек-бұзушы
            # ретінде қосылды.
            row = self._connection.execute(
                """
                SELECT experiment_id, MAX(linked_at) AS latest, MAX(rowid) AS latest_rowid
                FROM session_student_link
                WHERE classroom_id = ?
                GROUP BY experiment_id
                ORDER BY latest DESC, latest_rowid DESC
                LIMIT 1
                """,
                (classroom.id,),
            ).fetchone()
            if row is None:
                continue  # § "DO NOT fabricate activity" — белсенділігі жоқ сынып мүлде қосылмайды
            experiment_id, latest_iso, _latest_rowid = row
            last_activity_at = datetime.fromisoformat(latest_iso) if latest_iso else None

            students = self._student_repository.list_by_classroom(classroom.id)
            completed = in_progress = not_started = 0
            for student in students:
                status = self.get_progress(student.id, experiment_id).status
                if status is ProgressStatus.NOT_STARTED:
                    not_started += 1
                elif status is ProgressStatus.IN_PROGRESS:
                    in_progress += 1
                else:
                    completed += 1

            snapshots.append(
                ClassroomActivitySnapshot(
                    classroom_id=classroom.id,
                    classroom_name=classroom.name,
                    experiment_id=experiment_id,
                    student_count=len(students),
                    completed_count=completed,
                    in_progress_count=in_progress,
                    not_started_count=not_started,
                    last_activity_at=last_activity_at,
                )
            )
        return tuple(snapshots)
