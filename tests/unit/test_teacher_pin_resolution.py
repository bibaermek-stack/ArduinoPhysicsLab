"""resolve_teacher_by_pin() юнит-тесттері (Multi-Teacher Accounts) —
бірнеше мұғалім арасында PIN бойынша дұрыс сәйкестендіру, қате PIN,
белсенді емес мұғалімнің қабылданбауы."""

from datetime import datetime, timezone

from domain.entities.teacher import Teacher
from domain.services.teacher_pin import hash_pin, resolve_teacher_by_pin
from infrastructure.storage.sqlite_teacher_repository import SqliteTeacherRepository

_NOW = datetime.now(timezone.utc)


def _make_repository_with_two_teachers() -> SqliteTeacherRepository:
    repository = SqliteTeacherRepository()
    repository.create(
        Teacher(id="ta", full_name="Aidos Nurlanuly", pin_hash=hash_pin("482915"), created_at=_NOW, updated_at=_NOW)
    )
    repository.create(
        Teacher(id="tb", full_name="Gulmira Serikkyzy", pin_hash=hash_pin("731426"), created_at=_NOW, updated_at=_NOW)
    )
    return repository


def test_resolves_teacher_a_by_correct_pin() -> None:
    repository = _make_repository_with_two_teachers()

    resolved = resolve_teacher_by_pin("482915", repository)

    assert resolved is not None
    assert resolved.id == "ta"
    assert resolved.full_name == "Aidos Nurlanuly"


def test_resolves_teacher_b_by_correct_pin() -> None:
    repository = _make_repository_with_two_teachers()

    resolved = resolve_teacher_by_pin("731426", repository)

    assert resolved is not None
    assert resolved.id == "tb"
    assert resolved.full_name == "Gulmira Serikkyzy"


def test_wrong_pin_resolves_to_none() -> None:
    repository = _make_repository_with_two_teachers()

    assert resolve_teacher_by_pin("000000", repository) is None


def test_empty_teacher_repository_never_resolves() -> None:
    repository = SqliteTeacherRepository()

    assert resolve_teacher_by_pin("482915", repository) is None


def test_inactive_teacher_pin_is_rejected() -> None:
    """§10/§12: "Disabled teacher PIN must no longer allow login"."""
    from dataclasses import replace

    repository = _make_repository_with_two_teachers()
    teacher = repository.get("ta")
    repository.update(replace(teacher, is_active=False))

    assert resolve_teacher_by_pin("482915", repository) is None


def test_reactivating_teacher_restores_login() -> None:
    from dataclasses import replace

    repository = _make_repository_with_two_teachers()
    teacher = repository.get("ta")
    repository.update(replace(teacher, is_active=False))
    repository.update(replace(teacher, is_active=True))

    resolved = resolve_teacher_by_pin("482915", repository)
    assert resolved is not None
    assert resolved.id == "ta"


def test_one_teachers_pin_never_resolves_another_teacher() -> None:
    """Cross-contamination guard: Teacher A's PIN must never resolve to
    Teacher B even though both records coexist in the same repository."""
    repository = _make_repository_with_two_teachers()

    resolved = resolve_teacher_by_pin("482915", repository)

    assert resolved.id != "tb"
