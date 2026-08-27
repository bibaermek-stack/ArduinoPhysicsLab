"""UserRole — typed enum моделінің юнит-тесттері (Phase 37A)."""

from domain.entities.user_role import UserRole


def test_two_valid_roles_exist() -> None:
    assert UserRole.STUDENT is not None
    assert UserRole.TEACHER is not None


def test_roles_are_distinct() -> None:
    assert UserRole.STUDENT != UserRole.TEACHER


def test_role_equality_is_identity_based() -> None:
    assert UserRole.STUDENT == UserRole.STUDENT
    assert UserRole.TEACHER is UserRole.TEACHER


def test_role_values_are_stable_strings() -> None:
    assert UserRole.STUDENT.value == "student"
    assert UserRole.TEACHER.value == "teacher"


def test_roles_are_hashable_and_usable_in_a_set() -> None:
    roles = {UserRole.STUDENT, UserRole.TEACHER, UserRole.STUDENT}
    assert roles == {UserRole.STUDENT, UserRole.TEACHER}


def test_roles_usable_in_frozenset_membership_check() -> None:
    allowed = frozenset({UserRole.TEACHER})
    assert UserRole.TEACHER in allowed
    assert UserRole.STUDENT not in allowed
