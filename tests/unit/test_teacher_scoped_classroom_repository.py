"""TeacherScopedClassroomRepository юнит-тесттері (Multi-Teacher
Accounts §6) — list_active()/list_all() ағымдағы мұғалімге сай
сүзіледі, ал жазу/бір жазбалық оқу әдістері ІШКІ репозиторийге
өзгеріссіз бағытталады."""

from datetime import datetime, timezone

from domain.entities.active_teacher_context import ActiveTeacherContext
from domain.entities.classroom import Classroom
from domain.entities.teacher import Teacher
from domain.entities.user_role import UserRole
from domain.services.teacher_pin import hash_pin
from infrastructure.storage.sqlite_active_teacher_repository import SqliteActiveTeacherRepository
from infrastructure.storage.sqlite_classroom_repository import SqliteClassroomRepository
from infrastructure.storage.sqlite_teacher_repository import SqliteTeacherRepository
from infrastructure.storage.teacher_scoped_classroom_repository import (
    TeacherScopedClassroomRepository,
)

_NOW = datetime.now(timezone.utc)


def _make_scoped() -> tuple[
    TeacherScopedClassroomRepository, SqliteClassroomRepository, SqliteTeacherRepository,
    SqliteActiveTeacherRepository,
]:
    classroom_repository = SqliteClassroomRepository()
    teacher_repository = SqliteTeacherRepository()
    active_teacher_repository = SqliteActiveTeacherRepository()
    scoped = TeacherScopedClassroomRepository(
        classroom_repository, teacher_repository, active_teacher_repository
    )
    return scoped, classroom_repository, teacher_repository, active_teacher_repository


def _seed_classrooms(classroom_repository: SqliteClassroomRepository) -> None:
    for classroom_id, name in (("c1", "8А"), ("c2", "8Б"), ("c3", "8В")):
        classroom_repository.create(
            Classroom(id=classroom_id, name=name, created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
        )


def test_unrestricted_without_active_teacher() -> None:
    scoped, classroom_repository, _teacher_repository, _active = _make_scoped()
    _seed_classrooms(classroom_repository)

    assert {c.id for c in scoped.list_active()} == {"c1", "c2", "c3"}
    assert {c.id for c in scoped.list_all()} == {"c1", "c2", "c3"}


def test_filtered_to_teacher_a_assignments() -> None:
    scoped, classroom_repository, teacher_repository, active_teacher_repository = _make_scoped()
    _seed_classrooms(classroom_repository)
    teacher_repository.create(
        Teacher(id="ta", full_name="Aidos", pin_hash=hash_pin("482915"), created_at=_NOW, updated_at=_NOW),
        assigned_classroom_ids=("c1", "c2"),
    )
    active_teacher_repository.set(ActiveTeacherContext(teacher_id="ta"))

    assert {c.id for c in scoped.list_active()} == {"c1", "c2"}


def test_filtered_to_teacher_b_assignments_is_disjoint_from_teacher_a() -> None:
    scoped, classroom_repository, teacher_repository, active_teacher_repository = _make_scoped()
    _seed_classrooms(classroom_repository)
    teacher_repository.create(
        Teacher(id="ta", full_name="Aidos", pin_hash=hash_pin("111111"), created_at=_NOW, updated_at=_NOW),
        assigned_classroom_ids=("c1", "c2"),
    )
    teacher_repository.create(
        Teacher(id="tb", full_name="Gulmira", pin_hash=hash_pin("222222"), created_at=_NOW, updated_at=_NOW),
        assigned_classroom_ids=("c3",),
    )
    active_teacher_repository.set(ActiveTeacherContext(teacher_id="tb"))

    result = {c.id for c in scoped.list_active()}
    assert result == {"c3"}
    assert "c1" not in result
    assert "c2" not in result


def test_switching_active_teacher_changes_visible_classrooms() -> None:
    scoped, classroom_repository, teacher_repository, active_teacher_repository = _make_scoped()
    _seed_classrooms(classroom_repository)
    teacher_repository.create(
        Teacher(id="ta", full_name="Aidos", pin_hash=hash_pin("111111"), created_at=_NOW, updated_at=_NOW),
        assigned_classroom_ids=("c1",),
    )
    teacher_repository.create(
        Teacher(id="tb", full_name="Gulmira", pin_hash=hash_pin("222222"), created_at=_NOW, updated_at=_NOW),
        assigned_classroom_ids=("c3",),
    )

    active_teacher_repository.set(ActiveTeacherContext(teacher_id="ta"))
    assert {c.id for c in scoped.list_active()} == {"c1"}

    active_teacher_repository.set(ActiveTeacherContext(teacher_id="tb"))
    assert {c.id for c in scoped.list_active()} == {"c3"}


def test_write_and_get_methods_pass_through_unrestricted() -> None:
    """§ CRUD/get() must never be teacher-filtered — only list_active()/
    list_all() are scoped (the teacher management page itself needs
    full access via the raw inner repository, and get() by id is
    always exact-match)."""
    scoped, classroom_repository, teacher_repository, active_teacher_repository = _make_scoped()
    _seed_classrooms(classroom_repository)
    teacher_repository.create(
        Teacher(id="ta", full_name="Aidos", pin_hash=hash_pin("111111"), created_at=_NOW, updated_at=_NOW),
        assigned_classroom_ids=("c1",),
    )
    active_teacher_repository.set(ActiveTeacherContext(teacher_id="ta"))

    # c3 is not assigned to "ta", but get() must still resolve it.
    fetched = scoped.get("c3")
    assert fetched is not None
    assert fetched.name == "8В"

    scoped.archive("c3", UserRole.TEACHER)
    assert classroom_repository.get("c3").is_archived is True
