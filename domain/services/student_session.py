"""Оқушы сессиясы — email/Google кіргеннен кейін жергілікті код сұралмайды."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from domain.entities.active_student_context import ActiveStudentContext
from domain.entities.classroom import Classroom
from domain.entities.student import Student
from domain.entities.user_role import UserRole
from domain.interfaces.i_active_student_repository import IActiveStudentRepository
from domain.interfaces.i_classroom_repository import IClassroomRepository
from domain.interfaces.i_student_repository import IStudentRepository

INDEPENDENT_CLASSROOM_ID = "independent-lab"
INDEPENDENT_CLASSROOM_NAME = "Дербес зертхана"


def account_student_id(account_id: str) -> str:
    return f"acc-{account_id.strip()}"


def split_display_name(display_name: str) -> tuple[str, str]:
    cleaned = display_name.strip() or "Оқушы"
    parts = cleaned.split()
    if len(parts) >= 2:
        return parts[0], " ".join(parts[1:])
    return cleaned, ""


def _code_from_public_id(public_id: str) -> str:
    return public_id.strip().replace("-", "")[:8]


def _set_active(
    active_student_repository: IActiveStudentRepository, student: Student
) -> ActiveStudentContext:
    context = ActiveStudentContext(classroom_id=student.classroom_id, student_id=student.id)
    active_student_repository.set(context)
    return context


def _first_student(
    student_repository: IStudentRepository,
    classroom_repository: IClassroomRepository | None,
) -> Student | None:
    classroom_ids: list[str] = []
    if classroom_repository is not None:
        classroom_ids.extend(classroom.id for classroom in classroom_repository.list_all())
    if INDEPENDENT_CLASSROOM_ID not in classroom_ids:
        classroom_ids.append(INDEPENDENT_CLASSROOM_ID)
    for classroom_id in classroom_ids:
        students = student_repository.list_by_classroom(classroom_id)
        if students:
            return students[0]
    return None


def _ensure_independent_classroom(classroom_repository: IClassroomRepository | None) -> str:
    if classroom_repository is None:
        return INDEPENDENT_CLASSROOM_ID
    existing = classroom_repository.get(INDEPENDENT_CLASSROOM_ID)
    if existing is not None:
        return existing.id
    now = datetime.now(timezone.utc)
    classroom_repository.create(
        Classroom(
            id=INDEPENDENT_CLASSROOM_ID,
            name=INDEPENDENT_CLASSROOM_NAME,
            created_at=now,
            updated_at=now,
        ),
        UserRole.TEACHER,
    )
    return INDEPENDENT_CLASSROOM_ID


def ensure_active_student(
    student_repository: IStudentRepository,
    active_student_repository: IActiveStudentRepository,
    classroom_repository: IClassroomRepository | None = None,
    *,
    display_name: str = "",
    account_id: str = "",
    public_id: str = "",
) -> ActiveStudentContext:
    """Белсенді оқушыны кодсыз орнатады. Cloud аккаунт болса сол адамға
    байлайды; офлайн болса бар оқушыны қайта пайдаланады немесе дербес
    жазба құрады.
    """
    current = active_student_repository.get()
    if current is not None:
        return current

    account_id = account_id.strip()
    public_id = public_id.strip()
    if account_id:
        found = student_repository.get(account_student_id(account_id))
        if found is not None:
            return _set_active(active_student_repository, found)
    if public_id:
        found = student_repository.get_by_code(_code_from_public_id(public_id))
        if found is not None:
            return _set_active(active_student_repository, found)

    if not account_id:
        found = _first_student(student_repository, classroom_repository)
        if found is not None:
            return _set_active(active_student_repository, found)

    classroom_id = _ensure_independent_classroom(classroom_repository)
    now = datetime.now(timezone.utc)
    first_name, last_name = split_display_name(display_name)
    student_id = account_student_id(account_id) if account_id else str(uuid4())
    code = _code_from_public_id(public_id)
    if not code:
        from domain.services.student_access_code import generate_unique_student_code

        code = generate_unique_student_code(student_repository)
    student = Student(
        id=student_id,
        classroom_id=classroom_id,
        first_name=first_name,
        last_name=last_name,
        created_at=now,
        updated_at=now,
        student_code=code,
    )
    student_repository.create(student, UserRole.TEACHER)
    return _set_active(active_student_repository, student)
