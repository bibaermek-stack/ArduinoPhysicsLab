"""navigation_config — рөлге тәуелді ортақ навигация кестесінің юнит-
тесттері (Phase 37A).
"""

from domain.entities.user_role import UserRole
from ui.navigation.navigation_config import (
    NAVIGATION_ITEMS,
    default_landing_route,
    is_route_allowed_for_role,
    items_for_role,
)

_STUDENT_KEYS = {"home", "labs", "my_results", "feedback_student", "help"}
_TEACHER_KEYS = {
    "dashboard",
    "classes",
    "labs",
    "results",
    "data_log",
    "feedback_teacher",
    "analytics",
    "question_bank",
    "devices",
    "settings",
    "help",
}
_TEACHER_ONLY_KEYS = _TEACHER_KEYS - _STUDENT_KEYS
_STUDENT_ONLY_KEYS = _STUDENT_KEYS - _TEACHER_KEYS


def test_student_subset_matches_spec() -> None:
    keys = {item.key for item in items_for_role(UserRole.STUDENT)}
    assert keys == _STUDENT_KEYS


def test_teacher_subset_matches_spec() -> None:
    keys = {item.key for item in items_for_role(UserRole.TEACHER)}
    assert keys == _TEACHER_KEYS


def test_shared_items_present_in_both_roles() -> None:
    student_keys = {item.key for item in items_for_role(UserRole.STUDENT)}
    teacher_keys = {item.key for item in items_for_role(UserRole.TEACHER)}
    for shared_key in ("labs", "help"):
        assert shared_key in student_keys
        assert shared_key in teacher_keys


def test_teacher_only_items_absent_from_student_list() -> None:
    student_keys = {item.key for item in items_for_role(UserRole.STUDENT)}
    for forbidden_key in _TEACHER_ONLY_KEYS:
        assert forbidden_key not in student_keys


def test_student_only_items_absent_from_teacher_list() -> None:
    teacher_keys = {item.key for item in items_for_role(UserRole.TEACHER)}
    for student_only_key in _STUDENT_ONLY_KEYS:
        assert student_only_key not in teacher_keys


def test_items_for_role_preserves_table_order() -> None:
    student_items = items_for_role(UserRole.STUDENT)
    table_order = [item.key for item in NAVIGATION_ITEMS if item.key in _STUDENT_KEYS]
    assert [item.key for item in student_items] == table_order


def test_navigation_item_has_no_duplicate_keys() -> None:
    keys = [item.key for item in NAVIGATION_ITEMS]
    assert len(keys) == len(set(keys))


def test_is_route_allowed_for_role_student_restricted() -> None:
    assert is_route_allowed_for_role("home", UserRole.STUDENT) is True
    assert is_route_allowed_for_role("devices", UserRole.STUDENT) is False
    assert is_route_allowed_for_role("settings", UserRole.STUDENT) is False


def test_is_route_allowed_for_role_teacher_unrestricted() -> None:
    for item in NAVIGATION_ITEMS:
        assert is_route_allowed_for_role(item.key, UserRole.TEACHER) is True


def test_is_route_allowed_for_role_unregistered_route_always_allowed() -> None:
    """Drill-down/қызметтік route-тар (мыс. ``experiment_workspace``,
    ``role_selection``) кестеде жоқ — рөлге қарамастан әрдайым рұқсат.
    """
    assert is_route_allowed_for_role("experiment_workspace", UserRole.STUDENT) is True
    assert is_route_allowed_for_role("experiment_list", UserRole.STUDENT) is True
    assert is_route_allowed_for_role("role_selection", UserRole.STUDENT) is True


def test_default_landing_route_per_role() -> None:
    assert default_landing_route(UserRole.STUDENT) == "home"
    assert default_landing_route(UserRole.TEACHER) == "dashboard"


def test_teacher_only_drilldown_routes_blocked_for_student() -> None:
    """§ Phase 6 (``classroom_monitoring``/``student_monitoring``) + Phase 7
    (``data_journal``, § audit found this ROUTER key had no matching
    ``NAVIGATION_ITEMS`` entry — only "data_log" did — so it silently
    defaulted to allowed-for-everyone before this fix)."""
    for route_key in ("classroom_monitoring", "student_monitoring", "data_journal"):
        assert is_route_allowed_for_role(route_key, UserRole.STUDENT) is False
        assert is_route_allowed_for_role(route_key, UserRole.TEACHER) is True
