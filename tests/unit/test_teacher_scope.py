"""resolve_allowed_classroom_ids() юнит-тесттері (Multi-Teacher Accounts
§6 "Data Ownership / Filtering")."""

from datetime import datetime, timezone

from domain.entities.active_teacher_context import ActiveTeacherContext
from domain.entities.teacher import Teacher
from domain.services.teacher_pin import hash_pin
from domain.services.teacher_scope import resolve_allowed_classroom_ids
from infrastructure.storage.sqlite_active_teacher_repository import SqliteActiveTeacherRepository
from infrastructure.storage.sqlite_teacher_repository import SqliteTeacherRepository

_NOW = datetime.now(timezone.utc)


def test_no_active_teacher_returns_none_unrestricted() -> None:
    teacher_repository = SqliteTeacherRepository()
    active_teacher_repository = SqliteActiveTeacherRepository()

    assert resolve_allowed_classroom_ids(teacher_repository, active_teacher_repository) is None


def test_active_teacher_returns_their_assigned_classroom_ids() -> None:
    teacher_repository = SqliteTeacherRepository()
    teacher_repository.create(
        Teacher(id="ta", full_name="Aidos", pin_hash=hash_pin("482915"), created_at=_NOW, updated_at=_NOW),
        assigned_classroom_ids=("c1", "c2"),
    )
    active_teacher_repository = SqliteActiveTeacherRepository()
    active_teacher_repository.set(ActiveTeacherContext(teacher_id="ta"))

    result = resolve_allowed_classroom_ids(teacher_repository, active_teacher_repository)

    assert result == frozenset({"c1", "c2"})


def test_teacher_with_no_assignments_returns_empty_set_not_none() -> None:
    """A newly created teacher with zero assigned classes must see
    NOTHING (strict allow-list), not fall back to unrestricted."""
    teacher_repository = SqliteTeacherRepository()
    teacher_repository.create(
        Teacher(id="ta", full_name="Aidos", pin_hash=hash_pin("482915"), created_at=_NOW, updated_at=_NOW)
    )
    active_teacher_repository = SqliteActiveTeacherRepository()
    active_teacher_repository.set(ActiveTeacherContext(teacher_id="ta"))

    result = resolve_allowed_classroom_ids(teacher_repository, active_teacher_repository)

    assert result == frozenset()


def test_dangling_active_teacher_context_returns_none() -> None:
    """If the active-teacher context references a teacher id that no
    longer resolves (should not normally happen), fail open to
    unrestricted rather than crashing or silently hiding everything."""
    teacher_repository = SqliteTeacherRepository()
    active_teacher_repository = SqliteActiveTeacherRepository()
    active_teacher_repository.set(ActiveTeacherContext(teacher_id="ghost"))

    assert resolve_allowed_classroom_ids(teacher_repository, active_teacher_repository) is None
