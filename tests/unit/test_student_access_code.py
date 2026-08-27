"""student_access_code юнит-тесттері (Phase — Mode Switch + Student Access
Screen Redesign): генерация бірегейлігі, backfill идемпотенттілігі,
``get_by_code()`` дәл сәйкестендіру."""

from datetime import datetime, timezone

from domain.entities.classroom import Classroom
from domain.entities.student import Student
from domain.entities.user_role import UserRole
from domain.services.student_access_code import (
    backfill_missing_student_codes,
    generate_unique_student_code,
)
from infrastructure.storage.sqlite_classroom_repository import SqliteClassroomRepository
from infrastructure.storage.sqlite_student_repository import SqliteStudentRepository

_NOW = datetime.now(timezone.utc)


def _make_repos() -> tuple[SqliteClassroomRepository, SqliteStudentRepository]:
    return SqliteClassroomRepository(), SqliteStudentRepository()


def _make_student(student_id: str, classroom_id: str = "c1", code: str = "") -> Student:
    return Student(
        id=student_id, classroom_id=classroom_id, first_name="Аты", last_name="Тегі",
        created_at=_NOW, updated_at=_NOW, student_code=code,
    )


def test_generated_code_is_six_digits() -> None:
    _classrooms, students = _make_repos()

    code = generate_unique_student_code(students)

    assert len(code) == 6
    assert code.isdigit()


def test_generated_codes_are_unique_across_many_students() -> None:
    classrooms, students = _make_repos()
    classrooms.create(Classroom(id="c1", name="8Б", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER)

    codes = set()
    for i in range(50):
        code = generate_unique_student_code(students)
        students.create(_make_student(f"s{i}", code=code), UserRole.TEACHER)
        codes.add(code)

    assert len(codes) == 50


def test_generated_code_is_not_student_id_or_sequential() -> None:
    _classrooms, students = _make_repos()

    code = generate_unique_student_code(students)

    assert code not in ("000001", "000000", "1", "s1")


def test_backfill_assigns_code_to_students_missing_one() -> None:
    classrooms, students = _make_repos()
    classrooms.create(Classroom(id="c1", name="8Б", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER)
    students.create(_make_student("s1"), UserRole.TEACHER)

    updated = backfill_missing_student_codes(classrooms, students)

    assert updated == 1
    student = students.get("s1")
    assert student.student_code != ""
    assert len(student.student_code) == 6


def test_backfill_does_not_touch_students_with_existing_code() -> None:
    classrooms, students = _make_repos()
    classrooms.create(Classroom(id="c1", name="8Б", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER)
    students.create(_make_student("s1", code="123456"), UserRole.TEACHER)

    backfill_missing_student_codes(classrooms, students)

    assert students.get("s1").student_code == "123456"


def test_backfill_is_idempotent() -> None:
    classrooms, students = _make_repos()
    classrooms.create(Classroom(id="c1", name="8Б", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER)
    students.create(_make_student("s1"), UserRole.TEACHER)

    first_count = backfill_missing_student_codes(classrooms, students)
    first_code = students.get("s1").student_code
    second_count = backfill_missing_student_codes(classrooms, students)
    second_code = students.get("s1").student_code

    assert first_count == 1
    assert second_count == 0
    assert first_code == second_code


def test_backfill_never_deletes_or_recreates_student_records() -> None:
    classrooms, students = _make_repos()
    classrooms.create(Classroom(id="c1", name="8Б", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER)
    students.create(_make_student("s1"), UserRole.TEACHER)
    before = students.get("s1")

    backfill_missing_student_codes(classrooms, students)

    after = students.get("s1")
    assert after.id == before.id
    assert after.first_name == before.first_name
    assert after.created_at == before.created_at


def test_backfill_covers_archived_students_too() -> None:
    classrooms, students = _make_repos()
    classrooms.create(Classroom(id="c1", name="8Б", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER)
    students.create(_make_student("s1"), UserRole.TEACHER)
    students.archive("s1", UserRole.TEACHER, archived=True)

    updated = backfill_missing_student_codes(classrooms, students)

    assert updated == 1


def test_get_by_code_resolves_correct_student() -> None:
    classrooms, students = _make_repos()
    classrooms.create(Classroom(id="c1", name="8Б", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER)
    students.create(_make_student("s1", code="482731"), UserRole.TEACHER)
    students.create(_make_student("s2", code="111222"), UserRole.TEACHER)

    found = students.get_by_code("482731")

    assert found is not None
    assert found.id == "s1"


def test_get_by_code_trims_whitespace() -> None:
    _classrooms, students = _make_repos()
    students.create(_make_student("s1", code="482731"), UserRole.TEACHER)

    found = students.get_by_code("  482731  ")

    assert found is not None
    assert found.id == "s1"


def test_get_by_code_returns_none_for_unknown_code() -> None:
    _classrooms, students = _make_repos()
    students.create(_make_student("s1", code="482731"), UserRole.TEACHER)

    assert students.get_by_code("000000") is None


def test_get_by_code_returns_none_for_empty_code() -> None:
    _classrooms, students = _make_repos()

    assert students.get_by_code("") is None
    assert students.get_by_code("   ") is None


def test_get_by_code_ignores_archived_students() -> None:
    _classrooms, students = _make_repos()
    students.create(_make_student("s1", code="482731"), UserRole.TEACHER)
    students.archive("s1", UserRole.TEACHER, archived=True)

    assert students.get_by_code("482731") is None
