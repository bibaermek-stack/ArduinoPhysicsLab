"""SqliteStudentRepository юнит-тесттері: CRUD/іздеу/қайталама код/рөл-
қорғаныс."""

from datetime import datetime, timezone

import pytest

from domain.entities.student import Student
from domain.entities.user_role import UserRole
from infrastructure.storage.sqlite_student_repository import SqliteStudentRepository

_NOW = datetime.now(timezone.utc)


def _make_student(id_: str = "s1", **overrides: object) -> Student:
    defaults: dict[str, object] = dict(
        id=id_, classroom_id="c1", first_name="Айдос", last_name="Серіков",
        created_at=_NOW, updated_at=_NOW,
    )
    defaults.update(overrides)
    return Student(**defaults)


def test_create_and_get() -> None:
    repository = SqliteStudentRepository()
    repository.create(_make_student(), UserRole.TEACHER)

    fetched = repository.get("s1")
    assert fetched is not None
    assert fetched.display_name == "Серіков Айдос"


def test_update_changes_fields() -> None:
    repository = SqliteStudentRepository()
    repository.create(_make_student(), UserRole.TEACHER)

    repository.update(_make_student(first_name="Бекзат"), UserRole.TEACHER)

    assert repository.get("s1").first_name == "Бекзат"


def test_archive_and_restore() -> None:
    repository = SqliteStudentRepository()
    repository.create(_make_student(), UserRole.TEACHER)

    repository.archive("s1", UserRole.TEACHER)
    assert repository.get("s1").is_archived is True
    assert repository.list_by_classroom("c1") == ()

    repository.archive("s1", UserRole.TEACHER, archived=False)
    assert repository.list_by_classroom("c1")[0].id == "s1"


def test_list_by_classroom_excludes_other_classrooms() -> None:
    repository = SqliteStudentRepository()
    repository.create(_make_student("s1", classroom_id="c1"), UserRole.TEACHER)
    repository.create(_make_student("s2", classroom_id="c2"), UserRole.TEACHER)

    assert [s.id for s in repository.list_by_classroom("c1")] == ["s1"]


def test_list_by_classroom_include_archived_flag() -> None:
    repository = SqliteStudentRepository()
    repository.create(_make_student("s1"), UserRole.TEACHER)
    repository.archive("s1", UserRole.TEACHER)

    assert repository.list_by_classroom("c1", include_archived=False) == ()
    assert len(repository.list_by_classroom("c1", include_archived=True)) == 1


def test_search_matches_display_name() -> None:
    repository = SqliteStudentRepository()
    repository.create(_make_student("s1", first_name="Айдос", last_name="Серіков"), UserRole.TEACHER)
    repository.create(_make_student("s2", first_name="Бекзат", last_name="Нұрлан"), UserRole.TEACHER)

    results = repository.search("c1", "серіков")

    assert [s.id for s in results] == ["s1"]


def test_search_matches_student_code() -> None:
    repository = SqliteStudentRepository()
    repository.create(_make_student("s1", student_code="A123"), UserRole.TEACHER)

    assert [s.id for s in repository.search("c1", "a123")] == ["s1"]


def test_search_never_returns_archived() -> None:
    repository = SqliteStudentRepository()
    repository.create(_make_student("s1", first_name="Айдос"), UserRole.TEACHER)
    repository.archive("s1", UserRole.TEACHER)

    assert repository.search("c1", "Айдос") == ()


def test_duplicate_active_code_detected() -> None:
    repository = SqliteStudentRepository()
    repository.create(_make_student("s1", student_code="A123"), UserRole.TEACHER)

    assert repository.code_exists("A123") is True
    assert repository.code_exists("B999") is False


def test_code_exists_excludes_self_when_editing() -> None:
    repository = SqliteStudentRepository()
    repository.create(_make_student("s1", student_code="A123"), UserRole.TEACHER)

    assert repository.code_exists("A123", exclude_student_id="s1") is False


def test_archived_student_code_does_not_block_reuse() -> None:
    repository = SqliteStudentRepository()
    repository.create(_make_student("s1", student_code="A123"), UserRole.TEACHER)
    repository.archive("s1", UserRole.TEACHER)

    assert repository.code_exists("A123") is False


def test_empty_code_never_conflicts() -> None:
    repository = SqliteStudentRepository()
    repository.create(_make_student("s1", student_code=""), UserRole.TEACHER)

    assert repository.code_exists("") is False


# =====================================================================
# Mode Switch + Student Access Screen Redesign: ``get_by_code()``.
# =====================================================================


def test_get_by_code_resolves_exact_match() -> None:
    repository = SqliteStudentRepository()
    repository.create(_make_student("s1", student_code="482731"), UserRole.TEACHER)

    student = repository.get_by_code("482731")

    assert student is not None
    assert student.id == "s1"


def test_get_by_code_unknown_returns_none() -> None:
    repository = SqliteStudentRepository()
    repository.create(_make_student("s1", student_code="482731"), UserRole.TEACHER)

    assert repository.get_by_code("000000") is None


def test_get_by_code_archived_student_returns_none() -> None:
    repository = SqliteStudentRepository()
    repository.create(_make_student("s1", student_code="482731"), UserRole.TEACHER)
    repository.archive("s1", UserRole.TEACHER)

    assert repository.get_by_code("482731") is None


def test_student_role_cannot_create() -> None:
    repository = SqliteStudentRepository()
    with pytest.raises(PermissionError):
        repository.create(_make_student(), UserRole.STUDENT)


def test_student_role_cannot_update() -> None:
    repository = SqliteStudentRepository()
    repository.create(_make_student(), UserRole.TEACHER)
    with pytest.raises(PermissionError):
        repository.update(_make_student(first_name="Х"), UserRole.STUDENT)


def test_student_role_cannot_archive() -> None:
    repository = SqliteStudentRepository()
    repository.create(_make_student(), UserRole.TEACHER)
    with pytest.raises(PermissionError):
        repository.archive("s1", UserRole.STUDENT)
