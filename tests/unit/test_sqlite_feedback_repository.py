"""SqliteFeedbackRepository (Phase 39A) юнит-тесттері: draft/submit/
teacher жазу-оқу, аддитивті схема (ескі дерекқор ашылады), raw
measurements-ке тимейтіні.
"""

import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from domain.entities.experiment_feedback_result import (
    ExperimentFeedbackResult,
    MultipleChoiceAnswer,
    OpenResponseAnswer,
    ReflectionAnswer,
    TeacherAssessment,
)
from domain.entities.experiment_session import ExperimentSession
from domain.entities.measurement import Measurement
from domain.entities.user_role import UserRole
from infrastructure.storage.database import _SCHEMA_STATEMENTS
from infrastructure.storage.sqlite_feedback_repository import SqliteFeedbackRepository
from infrastructure.storage.sqlite_session_repository import SqliteSessionRepository

_NOW = datetime.now(timezone.utc)


def _draft_result(session_id: str = "s1") -> ExperimentFeedbackResult:
    return ExperimentFeedbackResult(
        experiment_id="ohms-law",
        session_id=session_id,
        level2_answers=(OpenResponseAnswer("l2-1", "partial"),),
    )


def _submitted_result(session_id: str = "s1") -> ExperimentFeedbackResult:
    return ExperimentFeedbackResult(
        experiment_id="ohms-law",
        session_id=session_id,
        level1_answers=(MultipleChoiceAnswer("l1-1", 0),),
        level1_score=4,
        level1_total=5,
        level1_percentage=80.0,
        level2_answers=(OpenResponseAnswer("l2-1", "final analysis"),),
        level3_answers=(ReflectionAnswer("l3-1", "reflection"),),
        self_assessment=4,
        is_draft=False,
        submitted_at=_NOW,
    )


def test_get_result_returns_none_when_absent() -> None:
    repo = SqliteFeedbackRepository()
    assert repo.get_result("missing") is None


def test_save_draft_then_get_result_roundtrip() -> None:
    repo = SqliteFeedbackRepository()
    repo.save_draft(_draft_result())

    loaded = repo.get_result("s1")

    assert loaded is not None
    assert loaded.is_draft is True
    assert loaded.level2_answers[0].response_text == "partial"
    assert loaded.teacher_assessment is None


def test_save_submission_marks_not_draft_with_score() -> None:
    repo = SqliteFeedbackRepository()
    repo.save_submission(_submitted_result())

    loaded = repo.get_result("s1")

    assert loaded.is_draft is False
    assert loaded.level1_score == 4
    assert loaded.level1_total == 5
    assert loaded.level1_percentage == 80.0
    assert loaded.submitted_at is not None
    assert loaded.self_assessment == 4


def test_draft_then_submission_overwrites_same_session_idempotently() -> None:
    repo = SqliteFeedbackRepository()
    repo.save_draft(_draft_result())
    repo.save_submission(_submitted_result())

    loaded = repo.get_result("s1")
    assert loaded.is_draft is False
    assert loaded.level2_answers[0].response_text == "final analysis"


def test_save_teacher_assessment_persists_and_does_not_erase_level_answers() -> None:
    repo = SqliteFeedbackRepository()
    repo.save_submission(_submitted_result())

    repo.save_teacher_assessment(
        "s1", "ohms-law", TeacherAssessment(score=9, comment="Great"), UserRole.TEACHER
    )

    loaded = repo.get_result("s1")
    assert loaded.teacher_assessment.score == 9
    assert loaded.teacher_assessment.comment == "Great"
    assert loaded.level1_score == 4  # untouched by teacher save
    assert loaded.level2_answers[0].response_text == "final analysis"


def test_save_teacher_assessment_rejects_student_role() -> None:
    repo = SqliteFeedbackRepository()
    repo.save_submission(_submitted_result())

    with pytest.raises(PermissionError):
        repo.save_teacher_assessment("s1", "ohms-law", TeacherAssessment(score=5), UserRole.STUDENT)

    # Confirm nothing was persisted from the rejected attempt.
    loaded = repo.get_result("s1")
    assert loaded.teacher_assessment is None


def test_re_saving_answers_preserves_previously_saved_teacher_assessment() -> None:
    repo = SqliteFeedbackRepository()
    repo.save_submission(_submitted_result())
    repo.save_teacher_assessment("s1", "ohms-law", TeacherAssessment(score=7), UserRole.TEACHER)

    # Student edits and re-submits (e.g. before the teacher score existed
    # in their view) — teacher's earlier score must survive.
    repo.save_submission(_submitted_result())

    loaded = repo.get_result("s1")
    assert loaded.teacher_assessment.score == 7


def test_teacher_can_save_assessment_before_any_student_draft_exists() -> None:
    """Мұғалім студент жоба/жіберу сақтамай тұрып та бағалай алуы тиіс
    (§ "Teacher mode can... open the same experiment feedback result") —
    бос жазба алдын ала жасалады, жалған level1/2/3 дерек ЕШҚАШАН
    толтырылмайды.
    """
    repo = SqliteFeedbackRepository()

    repo.save_teacher_assessment(
        "s1", "ohms-law", TeacherAssessment(score=6, comment="Early review"), UserRole.TEACHER
    )

    loaded = repo.get_result("s1")
    assert loaded is not None
    assert loaded.teacher_assessment.score == 6
    assert loaded.level1_answers == ()
    assert loaded.level1_total == 0
    assert loaded.is_draft is True


def test_one_row_per_session_id() -> None:
    repo = SqliteFeedbackRepository()
    repo.save_draft(_draft_result("s1"))
    repo.save_draft(_draft_result("s2"))

    assert repo.get_result("s1").session_id == "s1"
    assert repo.get_result("s2").session_id == "s2"


def test_additive_schema_creation_is_idempotent() -> None:
    repo1 = SqliteFeedbackRepository()
    # Constructing a second repository against the same (fresh) in-memory
    # semantics elsewhere is covered by file-based tests below; here we
    # just confirm re-initializing schema on the same connection is safe.
    from infrastructure.storage.database import initialize_schema

    initialize_schema(repo1._connection)
    initialize_schema(repo1._connection)
    repo1.save_draft(_draft_result())
    assert repo1.get_result("s1") is not None


def test_old_database_without_feedback_table_opens_successfully(tmp_path: Path) -> None:
    db_path = tmp_path / "old.db"
    connection = sqlite3.connect(str(db_path))
    with connection:
        for statement in _SCHEMA_STATEMENTS[:3]:  # pre-Phase-39A subset only
            connection.execute(statement)
    connection.close()

    repo = SqliteFeedbackRepository(db_path=db_path)
    assert repo.get_result("anything") is None
    repo.save_draft(_draft_result())
    assert repo.get_result("s1") is not None
    repo.close()


def test_feedback_repository_never_touches_raw_measurements(tmp_path: Path) -> None:
    db_path = tmp_path / "shared.db"

    session_repo = SqliteSessionRepository(db_path=db_path)
    session = ExperimentSession(id="s1", experiment_id="ohms-law", started_at=_NOW)
    session.add_measurement(
        Measurement(timestamp=_NOW, values={"voltage": 5.0, "current": 0.2}, experiment_id="ohms-law")
    )
    session_repo.save_session(session)

    feedback_repo = SqliteFeedbackRepository(db_path=db_path)
    feedback_repo.save_submission(_submitted_result("s1"))

    measurements = session_repo.get_measurements("s1")
    assert len(measurements) == 1
    assert measurements[0].values == {"voltage": 5.0, "current": 0.2}

    session_repo.close()
    feedback_repo.close()
