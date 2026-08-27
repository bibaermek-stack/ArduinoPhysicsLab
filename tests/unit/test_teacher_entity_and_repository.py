"""Teacher entity + SqliteTeacherRepository юнит-тесттері (Multi-Teacher
Accounts фазасы): CRUD, PIN хэш бірегейлігі, мұғалім↔сынып байланысы,
restart persistence (нақты файл dbpath арқылы)."""

import os
import tempfile
from datetime import datetime, timezone

from domain.entities.classroom import Classroom
from domain.entities.teacher import Teacher
from domain.entities.user_role import UserRole
from domain.services.teacher_pin import hash_pin
from infrastructure.storage.sqlite_classroom_repository import SqliteClassroomRepository
from infrastructure.storage.sqlite_teacher_repository import SqliteTeacherRepository

_NOW = datetime.now(timezone.utc)


def _make_teacher(teacher_id: str = "t1", full_name: str = "Aidos", pin: str = "482915") -> Teacher:
    return Teacher(id=teacher_id, full_name=full_name, pin_hash=hash_pin(pin), created_at=_NOW, updated_at=_NOW)


# ---- Teacher entity validation ---------------------------------------------


def test_teacher_validate_requires_id() -> None:
    teacher = Teacher(id="", full_name="Aidos", pin_hash=hash_pin("123456"), created_at=_NOW, updated_at=_NOW)
    assert "Teacher.id бос болмауы керек" in teacher.validate()


def test_teacher_validate_requires_full_name() -> None:
    teacher = Teacher(id="t1", full_name="  ", pin_hash=hash_pin("123456"), created_at=_NOW, updated_at=_NOW)
    assert any("аты-жөні" in error for error in teacher.validate())


def test_teacher_validate_requires_pin_hash() -> None:
    teacher = Teacher(id="t1", full_name="Aidos", pin_hash="", created_at=_NOW, updated_at=_NOW)
    assert any("pin_hash" in error for error in teacher.validate())


def test_teacher_validate_passes_for_valid_record() -> None:
    assert _make_teacher().validate() == []


def test_teacher_defaults_to_active() -> None:
    assert _make_teacher().is_active is True


# ---- SqliteTeacherRepository CRUD -------------------------------------------


def test_create_and_get_teacher() -> None:
    repository = SqliteTeacherRepository()
    teacher = _make_teacher()

    repository.create(teacher)

    fetched = repository.get("t1")
    assert fetched is not None
    assert fetched.full_name == "Aidos"
    assert fetched.pin_hash == hash_pin("482915")
    assert fetched.is_active is True


def test_get_unknown_teacher_returns_none() -> None:
    repository = SqliteTeacherRepository()
    assert repository.get("nope") is None


def test_list_all_sorted_by_name() -> None:
    repository = SqliteTeacherRepository()
    repository.create(_make_teacher("t1", "Serik", "111111"))
    repository.create(_make_teacher("t2", "Aidos", "222222"))

    names = [t.full_name for t in repository.list_all()]
    assert names == ["Aidos", "Serik"]


def test_list_all_includes_inactive() -> None:
    repository = SqliteTeacherRepository()
    teacher = _make_teacher()
    repository.create(teacher)
    repository.update(replace_active(teacher, False))

    assert len(repository.list_all()) == 1
    assert repository.list_all()[0].is_active is False


def test_list_active_excludes_inactive() -> None:
    repository = SqliteTeacherRepository()
    teacher = _make_teacher()
    repository.create(teacher)
    repository.update(replace_active(teacher, False))

    assert repository.list_active() == ()


def test_update_changes_name_and_active_status() -> None:
    repository = SqliteTeacherRepository()
    teacher = _make_teacher()
    repository.create(teacher)

    from dataclasses import replace as dc_replace

    updated = dc_replace(teacher, full_name="Aidos Nurlanuly", is_active=False)
    repository.update(updated)

    fetched = repository.get("t1")
    assert fetched.full_name == "Aidos Nurlanuly"
    assert fetched.is_active is False


def replace_active(teacher: Teacher, is_active: bool) -> Teacher:
    from dataclasses import replace as dc_replace

    return dc_replace(teacher, is_active=is_active)


# ---- PIN hash uniqueness ------------------------------------------------------


def test_pin_hash_exists_true_for_active_teacher() -> None:
    repository = SqliteTeacherRepository()
    repository.create(_make_teacher())

    assert repository.pin_hash_exists(hash_pin("482915")) is True


def test_pin_hash_exists_false_for_unused_pin() -> None:
    repository = SqliteTeacherRepository()
    repository.create(_make_teacher())

    assert repository.pin_hash_exists(hash_pin("000000")) is False


def test_pin_hash_exists_excludes_given_teacher_id() -> None:
    """§ Edit Teacher's own PIN change flow — checking a teacher's PIN
    against itself must not count as a duplicate."""
    repository = SqliteTeacherRepository()
    repository.create(_make_teacher())

    assert repository.pin_hash_exists(hash_pin("482915"), exclude_teacher_id="t1") is False


def test_pin_hash_exists_false_for_disabled_teacher() -> None:
    """§ disabled teacher's old PIN becomes free to reassign (not the
    normal flow, but the uniqueness check should reflect only active
    teachers per the interface contract)."""
    repository = SqliteTeacherRepository()
    teacher = _make_teacher()
    repository.create(teacher)
    repository.update(replace_active(teacher, False))

    assert repository.pin_hash_exists(hash_pin("482915")) is False


# ---- Teacher <-> Classroom assignment (many-to-many) --------------------------


def test_set_and_list_assigned_classroom_ids() -> None:
    repository = SqliteTeacherRepository()
    repository.create(_make_teacher())

    repository.set_assigned_classroom_ids("t1", ("c1", "c2"))

    assert repository.list_assigned_classroom_ids("t1") == ("c1", "c2")


def test_set_assigned_classroom_ids_fully_replaces_previous_set() -> None:
    repository = SqliteTeacherRepository()
    repository.create(_make_teacher())
    repository.set_assigned_classroom_ids("t1", ("c1", "c2"))

    repository.set_assigned_classroom_ids("t1", ("c3",))

    assert repository.list_assigned_classroom_ids("t1") == ("c3",)


def test_create_with_assigned_classroom_ids() -> None:
    repository = SqliteTeacherRepository()
    repository.create(_make_teacher(), assigned_classroom_ids=("c1", "c2"))

    assert repository.list_assigned_classroom_ids("t1") == ("c1", "c2")


def test_classroom_may_be_shared_by_multiple_teachers() -> None:
    """§ "A class may be accessible by more than one teacher if required"."""
    repository = SqliteTeacherRepository()
    repository.create(_make_teacher("t1", "Aidos", "111111"), assigned_classroom_ids=("c1",))
    repository.create(_make_teacher("t2", "Gulmira", "222222"), assigned_classroom_ids=("c1",))

    teacher_ids = repository.list_teacher_ids_for_classroom("c1")
    assert set(teacher_ids) == {"t1", "t2"}


def test_classroom_record_is_never_duplicated_by_assignment() -> None:
    """§ "Do NOT duplicate class records" — assignment only touches the
    join table, the Classroom itself lives in its own repository."""
    classroom_repository = SqliteClassroomRepository()
    classroom_repository.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    teacher_repository = SqliteTeacherRepository()
    teacher_repository.create(_make_teacher("t1", "Aidos", "111111"), assigned_classroom_ids=("c1",))
    teacher_repository.create(_make_teacher("t2", "Gulmira", "222222"), assigned_classroom_ids=("c1",))

    assert len(classroom_repository.list_all()) == 1


# ---- Application-restart persistence (real file db_path) ----------------------


def test_teachers_and_assignments_persist_across_reconnect() -> None:
    """§21 "Restart application... confirm all teacher accounts and
    assignments persist" — simulated by closing and reopening a NEW
    repository instance against the SAME real file db_path."""
    db_path = os.path.join(tempfile.gettempdir(), "apl_test_teacher_persistence.db")
    if os.path.exists(db_path):
        os.remove(db_path)
    try:
        first_session = SqliteTeacherRepository(db_path=db_path)
        first_session.create(_make_teacher("t1", "Aidos", "482915"), assigned_classroom_ids=("c1", "c2"))
        first_session.close()

        second_session = SqliteTeacherRepository(db_path=db_path)
        teacher = second_session.get("t1")
        assert teacher is not None
        assert teacher.full_name == "Aidos"
        assert teacher.pin_hash == hash_pin("482915")
        assert second_session.list_assigned_classroom_ids("t1") == ("c1", "c2")
        second_session.close()
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)
