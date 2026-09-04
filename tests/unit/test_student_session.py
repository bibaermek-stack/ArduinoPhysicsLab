"""ensure_active_student — кіру кодын сұрамай оқушы сессиясын орнатады."""

from __future__ import annotations

from datetime import datetime, timezone

from domain.entities.classroom import Classroom
from domain.entities.student import Student
from domain.entities.user_role import UserRole
from domain.services.student_session import (
    INDEPENDENT_CLASSROOM_ID,
    account_student_id,
    ensure_active_student,
    split_display_name,
)
from infrastructure.storage.sqlite_active_student_repository import SqliteActiveStudentRepository
from infrastructure.storage.sqlite_classroom_repository import SqliteClassroomRepository
from infrastructure.storage.sqlite_student_repository import SqliteStudentRepository

_NOW = datetime.now(timezone.utc)


def test_split_display_name_single_token() -> None:
    assert split_display_name("Айгерім") == ("Айгерім", "")


def test_split_display_name_two_tokens() -> None:
    assert split_display_name("Асқар Серікұлы") == ("Асқар", "Серікұлы")


def test_cloud_account_creates_stable_independent_student() -> None:
    students = SqliteStudentRepository()
    active = SqliteActiveStudentRepository()
    classrooms = SqliteClassroomRepository()

    first = ensure_active_student(
        students,
        active,
        classrooms,
        display_name="Айгерім Нұр",
        account_id="acc-1",
        public_id="S-ABCDEF",
    )
    again = ensure_active_student(
        students,
        active,
        classrooms,
        display_name="Айгерім Нұр",
        account_id="acc-1",
        public_id="S-ABCDEF",
    )

    assert first == again
    student = students.get(account_student_id("acc-1"))
    assert student is not None
    assert student.classroom_id == INDEPENDENT_CLASSROOM_ID
    assert student.first_name == "Айгерім"
    assert classrooms.get(INDEPENDENT_CLASSROOM_ID) is not None


def test_offline_reuses_existing_classroom_student() -> None:
    students = SqliteStudentRepository()
    active = SqliteActiveStudentRepository()
    classrooms = SqliteClassroomRepository()
    classrooms.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW),
        UserRole.TEACHER,
    )
    students.create(
        Student(
            id="s1",
            classroom_id="c1",
            first_name="Айдос",
            last_name="Серіков",
            created_at=_NOW,
            updated_at=_NOW,
            student_code="482731",
        ),
        UserRole.TEACHER,
    )

    context = ensure_active_student(students, active, classrooms)

    assert context.student_id == "s1"
    assert context.classroom_id == "c1"
