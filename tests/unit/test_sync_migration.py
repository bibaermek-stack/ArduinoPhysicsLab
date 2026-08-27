"""domain/services/sync_migration.py::backfill_sync_ids() тесттері
(§4 "Migration must be idempotent" / §2 "same local id must remain,
sync_id defaults to it")."""

from datetime import datetime, timezone

from domain.entities.classroom import Classroom
from domain.entities.student import Student
from domain.entities.teacher import Teacher
from domain.entities.user_role import UserRole
from domain.services.sync_migration import backfill_sync_ids
from domain.services.teacher_pin import hash_pin
from infrastructure.storage.sqlite_classroom_repository import SqliteClassroomRepository
from infrastructure.storage.sqlite_student_repository import SqliteStudentRepository
from infrastructure.storage.sqlite_teacher_repository import SqliteTeacherRepository

_NOW = datetime.now(timezone.utc)


def _blank_sync_id(repo, table: str, record_id: str) -> None:
    """Ескі (Cloud Sync-тен бұрынғы) жазбаны имитациялайды — ``create()``
    әрдайым ``sync_id`` толтыратындықтан, тестте оны қолмен бос жолға
    қайтарамыз (§ ``database.py``-дегі ЖАҢА баған ескі жолдарда осылай
    бос басталады)."""
    with repo._connection:
        repo._connection.execute(f"UPDATE {table} SET sync_id = '' WHERE id = ?", (record_id,))


def test_backfill_fills_empty_sync_id_with_local_id() -> None:
    classroom_repo = SqliteClassroomRepository()
    student_repo = SqliteStudentRepository()
    teacher_repo = SqliteTeacherRepository()

    classroom_repo.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    student_repo.create(
        Student(id="s1", classroom_id="c1", first_name="Aidos", last_name="T", created_at=_NOW, updated_at=_NOW),
        UserRole.TEACHER,
    )
    teacher_repo.create(Teacher(id="t1", full_name="X", pin_hash=hash_pin("1234"), created_at=_NOW, updated_at=_NOW))

    _blank_sync_id(classroom_repo, "classrooms", "c1")
    _blank_sync_id(student_repo, "students", "s1")
    _blank_sync_id(teacher_repo, "teachers", "t1")

    updated_count = backfill_sync_ids(classroom_repo, student_repo, teacher_repo)

    assert updated_count == 3
    assert classroom_repo.get("c1").sync_id == "c1"
    assert student_repo.get("s1").sync_id == "s1"
    assert teacher_repo.get("t1").sync_id == "t1"


def test_backfill_is_idempotent_second_run_updates_nothing() -> None:
    classroom_repo = SqliteClassroomRepository()
    student_repo = SqliteStudentRepository()
    teacher_repo = SqliteTeacherRepository()

    classroom_repo.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    _blank_sync_id(classroom_repo, "classrooms", "c1")

    first_run = backfill_sync_ids(classroom_repo, student_repo, teacher_repo)
    second_run = backfill_sync_ids(classroom_repo, student_repo, teacher_repo)

    assert first_run == 1
    assert second_run == 0


def test_backfill_does_not_touch_records_that_already_have_sync_id() -> None:
    """Жаңа (Cloud Sync фазасынан кейін жасалған) жазбалардың ``sync_id``-і
    ``create()`` арқылы АВТОМАТТЫ толтырылған — миграция оларға тимейді."""
    classroom_repo = SqliteClassroomRepository()
    student_repo = SqliteStudentRepository()
    teacher_repo = SqliteTeacherRepository()

    classroom_repo.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )

    updated_count = backfill_sync_ids(classroom_repo, student_repo, teacher_repo)

    assert updated_count == 0
    assert classroom_repo.get("c1").sync_id == "c1"


def test_backfill_never_regenerates_local_id() -> None:
    """§2: sync_id ЕШҚАШАН жаңа UUID болмайды, тек жазбаның ӨЗ id-мен
    БІРДЕЙ мәнге ие болады."""
    classroom_repo = SqliteClassroomRepository()
    student_repo = SqliteStudentRepository()
    teacher_repo = SqliteTeacherRepository()

    classroom_repo.create(
        Classroom(id="stable-local-id", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    _blank_sync_id(classroom_repo, "classrooms", "stable-local-id")

    backfill_sync_ids(classroom_repo, student_repo, teacher_repo)

    restored = classroom_repo.get("stable-local-id")
    assert restored.id == "stable-local-id"
    assert restored.sync_id == "stable-local-id"
