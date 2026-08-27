"""SqliteClassroomRepository юнит-тесттері: CRUD/мұрағаттау/рөл-қорғаныс,
аддитивті схема (ескі дерекқор ашылады)."""

import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from domain.entities.classroom import Classroom
from domain.entities.user_role import UserRole
from infrastructure.storage.database import _SCHEMA_STATEMENTS
from infrastructure.storage.sqlite_classroom_repository import SqliteClassroomRepository

_NOW = datetime.now(timezone.utc)


def _make_classroom(id_: str = "c1", name: str = "8А", **overrides: object) -> Classroom:
    defaults: dict[str, object] = dict(id=id_, name=name, created_at=_NOW, updated_at=_NOW)
    defaults.update(overrides)
    return Classroom(**defaults)


def test_create_and_get() -> None:
    repository = SqliteClassroomRepository()
    repository.create(_make_classroom(), UserRole.TEACHER)

    fetched = repository.get("c1")

    assert fetched is not None
    assert fetched.name == "8А"
    assert fetched.is_archived is False


def test_get_missing_returns_none() -> None:
    repository = SqliteClassroomRepository()
    assert repository.get("missing") is None


def test_update_changes_fields() -> None:
    repository = SqliteClassroomRepository()
    repository.create(_make_classroom(), UserRole.TEACHER)

    updated = _make_classroom(name="8Ә", academic_year="2025-2026")
    repository.update(updated, UserRole.TEACHER)

    fetched = repository.get("c1")
    assert fetched.name == "8Ә"
    assert fetched.academic_year == "2025-2026"


def test_archive_and_restore() -> None:
    repository = SqliteClassroomRepository()
    repository.create(_make_classroom(), UserRole.TEACHER)

    repository.archive("c1", UserRole.TEACHER)
    assert repository.get("c1").is_archived is True
    assert repository.get("c1") not in repository.list_active()

    repository.archive("c1", UserRole.TEACHER, archived=False)
    assert repository.get("c1").is_archived is False


def test_list_active_excludes_archived() -> None:
    repository = SqliteClassroomRepository()
    repository.create(_make_classroom("c1", "8А"), UserRole.TEACHER)
    repository.create(_make_classroom("c2", "8Ә"), UserRole.TEACHER)
    repository.archive("c2", UserRole.TEACHER)

    active = repository.list_active()

    assert [c.id for c in active] == ["c1"]


def test_list_all_includes_archived() -> None:
    repository = SqliteClassroomRepository()
    repository.create(_make_classroom("c1", "8А"), UserRole.TEACHER)
    repository.create(_make_classroom("c2", "8Ә"), UserRole.TEACHER)
    repository.archive("c2", UserRole.TEACHER)

    all_classrooms = repository.list_all()

    assert {c.id for c in all_classrooms} == {"c1", "c2"}


def test_student_role_cannot_create() -> None:
    repository = SqliteClassroomRepository()
    with pytest.raises(PermissionError):
        repository.create(_make_classroom(), UserRole.STUDENT)


def test_student_role_cannot_update() -> None:
    repository = SqliteClassroomRepository()
    repository.create(_make_classroom(), UserRole.TEACHER)
    with pytest.raises(PermissionError):
        repository.update(_make_classroom(name="Өзгертілген"), UserRole.STUDENT)


def test_student_role_cannot_archive() -> None:
    repository = SqliteClassroomRepository()
    repository.create(_make_classroom(), UserRole.TEACHER)
    with pytest.raises(PermissionError):
        repository.archive("c1", UserRole.STUDENT)


def test_old_database_file_opens_successfully(tmp_path: Path) -> None:
    """Ескі (Phase 39B-ге дейінгі) кестелермен дерекқор файлы жаңа
    ``classrooms`` кестесі жоқ болса да қалыпты ашылуы тиіс.
    """
    db_path = tmp_path / "legacy.db"
    legacy_connection = sqlite3.connect(str(db_path))
    # Тек ескі кестелерді (classrooms-сыз) қолмен жасаймыз.
    for statement in _SCHEMA_STATEMENTS[:2]:
        legacy_connection.execute(statement)
    legacy_connection.commit()
    legacy_connection.close()

    repository = SqliteClassroomRepository(db_path=db_path)
    repository.create(_make_classroom(), UserRole.TEACHER)

    assert repository.get("c1") is not None
