"""SqliteQuestionRepository юнит-тесттері (Phase 20): CRUD, мұрағаттау
(soft-delete), деңгей бойынша JSON өрістер (1-деңгей options/correct_
option_index), тұрақты сұрыптау, рұқсат гейті.
"""

from datetime import datetime, timezone

import pytest

from domain.entities.experiment_assessment import (
    MultipleChoiceQuestion,
    OpenResponseQuestion,
    ReflectionQuestion,
)
from domain.entities.question_record import QuestionRecord
from domain.entities.user_role import UserRole
from infrastructure.storage.sqlite_question_repository import SqliteQuestionRepository

_NOW = datetime.now(timezone.utc)


def _mc_record(question_id="q1", experiment_id="ohms-law", created_at=_NOW) -> QuestionRecord:
    return QuestionRecord(
        id=question_id, experiment_id=experiment_id, level=1,
        question=MultipleChoiceQuestion(
            id=question_id, prompt="Ток күшінің өлшем бірлігі қандай?",
            options=("Ампер", "Вольт", "Ом"), correct_option_index=0, points=1,
        ),
        is_active=True, created_at=created_at,
    )


def _open_record(question_id="q2", experiment_id="ohms-law", created_at=_NOW) -> QuestionRecord:
    return QuestionRecord(
        id=question_id, experiment_id=experiment_id, level=2,
        question=OpenResponseQuestion(id=question_id, prompt="Графиктен не байқадыңыз?"),
        is_active=True, created_at=created_at,
    )


def _reflection_record(question_id="q3", experiment_id="ohms-law", created_at=_NOW) -> QuestionRecord:
    return QuestionRecord(
        id=question_id, experiment_id=experiment_id, level=3,
        question=ReflectionQuestion(id=question_id, prompt="Не үйрендіңіз?"),
        is_active=True, created_at=created_at,
    )


def test_create_and_get_multiple_choice_question_round_trips_options() -> None:
    repository = SqliteQuestionRepository()
    record = _mc_record()

    repository.create(record, UserRole.TEACHER)
    fetched = repository.get("q1")

    assert fetched is not None
    assert fetched.question == record.question
    assert fetched.experiment_id == "ohms-law"
    assert fetched.level == 1
    assert fetched.is_active is True


def test_create_open_response_and_reflection_questions() -> None:
    repository = SqliteQuestionRepository()
    repository.create(_open_record(), UserRole.TEACHER)
    repository.create(_reflection_record(), UserRole.TEACHER)

    open_q = repository.get("q2")
    reflection_q = repository.get("q3")

    assert isinstance(open_q.question, OpenResponseQuestion)
    assert isinstance(reflection_q.question, ReflectionQuestion)


def test_get_returns_none_for_unknown_id() -> None:
    repository = SqliteQuestionRepository()
    assert repository.get("missing") is None


def test_update_changes_prompt_and_level() -> None:
    repository = SqliteQuestionRepository()
    repository.create(_mc_record(), UserRole.TEACHER)

    updated_question = MultipleChoiceQuestion(
        id="q1", prompt="Жаңартылған сұрақ", options=("A", "B"), correct_option_index=1, points=2,
    )
    repository.update(
        QuestionRecord(
            id="q1", experiment_id="ohms-law", level=1, question=updated_question,
            is_active=True, created_at=_NOW,
        ),
        UserRole.TEACHER,
    )

    fetched = repository.get("q1")
    assert fetched.question.prompt == "Жаңартылған сұрақ"
    assert fetched.question.correct_option_index == 1


def test_archive_sets_inactive_and_restore_sets_active_again() -> None:
    repository = SqliteQuestionRepository()
    repository.create(_mc_record(), UserRole.TEACHER)

    repository.archive("q1", UserRole.TEACHER, archived=True)
    assert repository.get("q1").is_active is False

    repository.archive("q1", UserRole.TEACHER, archived=False)
    assert repository.get("q1").is_active is True


def test_archive_never_hard_deletes_the_row() -> None:
    """§ "DO NOT hard-delete. Use... archive/disable/soft-delete" —
    мұрағатталған жол ``include_archived=True``-мен ӘЛІ де табылады."""
    repository = SqliteQuestionRepository()
    repository.create(_mc_record(), UserRole.TEACHER)
    repository.archive("q1", UserRole.TEACHER, archived=True)

    assert repository.get("q1") is not None
    assert len(repository.list_all(include_archived=True)) == 1
    assert len(repository.list_all(include_archived=False)) == 0


def test_list_all_excludes_archived_by_default() -> None:
    repository = SqliteQuestionRepository()
    repository.create(_mc_record(), UserRole.TEACHER)
    repository.create(_open_record(), UserRole.TEACHER)
    repository.archive("q1", UserRole.TEACHER, archived=True)

    active_only = repository.list_all()
    assert [r.id for r in active_only] == ["q2"]


def test_list_for_experiment_isolates_other_experiments() -> None:
    """§16 "editing a question does not alter unrelated experiments"."""
    repository = SqliteQuestionRepository()
    repository.create(_mc_record(experiment_id="ohms-law"), UserRole.TEACHER)
    repository.create(_open_record(experiment_id="current-voltage"), UserRole.TEACHER)

    ohms_questions = repository.list_for_experiment("ohms-law")

    assert len(ohms_questions) == 1
    assert ohms_questions[0].experiment_id == "ohms-law"


def test_list_for_experiment_stable_order_by_level_then_created_at() -> None:
    repository = SqliteQuestionRepository()
    t1 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    t2 = datetime(2026, 1, 2, tzinfo=timezone.utc)
    repository.create(_reflection_record(question_id="r1", created_at=t2), UserRole.TEACHER)
    repository.create(_mc_record(question_id="m1", created_at=t1), UserRole.TEACHER)
    repository.create(_open_record(question_id="o1", created_at=t2), UserRole.TEACHER)
    repository.create(_mc_record(question_id="m2", created_at=t2), UserRole.TEACHER)

    ordered = repository.list_for_experiment("ohms-law")

    assert [r.id for r in ordered] == ["m1", "m2", "o1", "r1"]


def test_empty_repository_returns_empty_tuples() -> None:
    repository = SqliteQuestionRepository()
    assert repository.list_all() == ()
    assert repository.list_for_experiment("ohms-law") == ()


def test_create_rejects_student_role() -> None:
    repository = SqliteQuestionRepository()
    with pytest.raises(PermissionError):
        repository.create(_mc_record(), UserRole.STUDENT)


def test_update_rejects_student_role() -> None:
    repository = SqliteQuestionRepository()
    repository.create(_mc_record(), UserRole.TEACHER)
    with pytest.raises(PermissionError):
        repository.update(_mc_record(), UserRole.STUDENT)


def test_archive_rejects_student_role() -> None:
    repository = SqliteQuestionRepository()
    repository.create(_mc_record(), UserRole.TEACHER)
    with pytest.raises(PermissionError):
        repository.archive("q1", UserRole.STUDENT)
