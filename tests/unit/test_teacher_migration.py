"""backfill_default_teacher() юнит-тесттері (§11 "First Teacher /
Backward Compatibility") — идемпотентті бір реттік көшу, ескі жалғыз-PIN
конфигурациясынан дефолт мұғалім жазбасына."""

from datetime import datetime, timezone

from domain.entities.classroom import Classroom
from domain.entities.teacher import Teacher
from domain.entities.user_role import UserRole
from domain.services.teacher_migration import backfill_default_teacher
from domain.services.teacher_pin import get_configured_pin_hash, hash_pin
from infrastructure.storage.sqlite_classroom_repository import SqliteClassroomRepository
from infrastructure.storage.sqlite_teacher_repository import SqliteTeacherRepository

_NOW = datetime.now(timezone.utc)


def test_creates_default_teacher_when_none_exist() -> None:
    teacher_repository = SqliteTeacherRepository()
    classroom_repository = SqliteClassroomRepository()

    created = backfill_default_teacher(teacher_repository, classroom_repository)

    assert created is not None
    assert len(teacher_repository.list_all()) == 1


def test_default_teacher_uses_legacy_pin_hash() -> None:
    """§ "Do not lose access to Teacher Mode after the migration" — the
    same PIN that used to work (APL_TEACHER_PIN / dev default) must
    resolve the migrated teacher."""
    teacher_repository = SqliteTeacherRepository()
    classroom_repository = SqliteClassroomRepository()

    created = backfill_default_teacher(teacher_repository, classroom_repository)

    assert created.pin_hash == get_configured_pin_hash()


def test_default_teacher_is_active() -> None:
    teacher_repository = SqliteTeacherRepository()
    classroom_repository = SqliteClassroomRepository()

    created = backfill_default_teacher(teacher_repository, classroom_repository)

    assert created.is_active is True


def test_default_teacher_assigned_all_existing_classrooms() -> None:
    """§ "Preserve backward compatibility with the current data" — the
    migrated teacher must retain full access, matching the pre-migration
    unrestricted behaviour."""
    classroom_repository = SqliteClassroomRepository()
    classroom_repository.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    classroom_repository.create(
        Classroom(id="c2", name="8Б", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    teacher_repository = SqliteTeacherRepository()

    created = backfill_default_teacher(teacher_repository, classroom_repository)

    assigned = set(teacher_repository.list_assigned_classroom_ids(created.id))
    assert assigned == {"c1", "c2"}


def test_migration_is_idempotent_on_repeated_calls() -> None:
    """§19 "Migration must be idempotent... starting the application
    multiple times must NOT duplicate teachers"."""
    teacher_repository = SqliteTeacherRepository()
    classroom_repository = SqliteClassroomRepository()

    backfill_default_teacher(teacher_repository, classroom_repository)
    second_call_result = backfill_default_teacher(teacher_repository, classroom_repository)
    third_call_result = backfill_default_teacher(teacher_repository, classroom_repository)

    assert second_call_result is None
    assert third_call_result is None
    assert len(teacher_repository.list_all()) == 1


def test_migration_does_nothing_when_teachers_already_exist() -> None:
    """§ Do NOT run if a real multi-teacher setup already exists —
    a pre-existing teacher (not the migrated default) must be left
    completely alone."""
    teacher_repository = SqliteTeacherRepository()
    classroom_repository = SqliteClassroomRepository()
    existing = Teacher(
        id="t1", full_name="Aidos", pin_hash=hash_pin("482915"), created_at=_NOW, updated_at=_NOW
    )
    teacher_repository.create(existing)

    result = backfill_default_teacher(teacher_repository, classroom_repository)

    assert result is None
    # § Offline-First + Cloud Sync Foundation: create() ЕНДІ ``sync_id``-ті
    # автоматты түрде ``id``-мен толтырады (§ audit — id ӘЛДЕҚАШАН UUID),
    # сондықтан fetched жазба тек осы БІР жаңа өріспен ерекшеленеді.
    from dataclasses import replace

    assert teacher_repository.list_all() == (replace(existing, sync_id="t1"),)
