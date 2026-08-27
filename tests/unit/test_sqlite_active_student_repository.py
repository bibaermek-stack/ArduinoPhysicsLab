"""SqliteActiveStudentRepository юнит-тесттері: set/get/clear, жалғыз
жол (``id=1``) семантикасы, persistence бір қосылым ішінде."""

from pathlib import Path

from domain.entities.active_student_context import ActiveStudentContext
from infrastructure.storage.sqlite_active_student_repository import SqliteActiveStudentRepository


def test_get_returns_none_when_never_set() -> None:
    repository = SqliteActiveStudentRepository()
    assert repository.get() is None


def test_set_then_get_returns_context() -> None:
    repository = SqliteActiveStudentRepository()
    repository.set(ActiveStudentContext(classroom_id="c1", student_id="s1"))

    assert repository.get() == ActiveStudentContext(classroom_id="c1", student_id="s1")


def test_set_overwrites_previous_context() -> None:
    repository = SqliteActiveStudentRepository()
    repository.set(ActiveStudentContext(classroom_id="c1", student_id="s1"))
    repository.set(ActiveStudentContext(classroom_id="c2", student_id="s2"))

    assert repository.get() == ActiveStudentContext(classroom_id="c2", student_id="s2")


def test_clear_removes_context() -> None:
    repository = SqliteActiveStudentRepository()
    repository.set(ActiveStudentContext(classroom_id="c1", student_id="s1"))

    repository.clear()

    assert repository.get() is None


def test_clear_when_never_set_is_safe() -> None:
    repository = SqliteActiveStudentRepository()
    repository.clear()  # құламауы тиіс
    assert repository.get() is None


def test_persists_across_repository_instances_sharing_file(tmp_path: Path) -> None:
    db_path = tmp_path / "shared.db"
    first = SqliteActiveStudentRepository(db_path=db_path)
    first.set(ActiveStudentContext(classroom_id="c1", student_id="s1"))
    first.close()

    second = SqliteActiveStudentRepository(db_path=db_path)
    assert second.get() == ActiveStudentContext(classroom_id="c1", student_id="s1")
