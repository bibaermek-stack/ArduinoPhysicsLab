"""student_access_control — рөл негізіндегі рұқсат тексерулері
(домен деңгейі, репозиторийден ТӘУЕЛСІЗ бірінші қорғаныс сызығы)."""

import pytest

from domain.entities.user_role import UserRole
from domain.services.student_access_control import (
    ensure_can_manage_classroom_data,
    ensure_can_save_teacher_assessment,
    ensure_can_view_student,
)


def test_teacher_can_manage_classroom_data() -> None:
    ensure_can_manage_classroom_data(UserRole.TEACHER)  # құламауы тиіс


def test_student_cannot_manage_classroom_data() -> None:
    with pytest.raises(PermissionError):
        ensure_can_manage_classroom_data(UserRole.STUDENT)


def test_teacher_can_save_teacher_assessment() -> None:
    ensure_can_save_teacher_assessment(UserRole.TEACHER)


def test_student_cannot_save_teacher_assessment() -> None:
    with pytest.raises(PermissionError):
        ensure_can_save_teacher_assessment(UserRole.STUDENT)


def test_teacher_can_view_any_student() -> None:
    ensure_can_view_student(UserRole.TEACHER, "other-student", "active-student")


def test_student_can_view_own_active_student() -> None:
    ensure_can_view_student(UserRole.STUDENT, "s1", "s1")


def test_student_cannot_view_other_student() -> None:
    with pytest.raises(PermissionError):
        ensure_can_view_student(UserRole.STUDENT, "other-student", "s1")


def test_student_cannot_view_when_no_active_student() -> None:
    with pytest.raises(PermissionError):
        ensure_can_view_student(UserRole.STUDENT, "s1", None)
