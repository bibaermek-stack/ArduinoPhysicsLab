"""Student domain entity — validate()/display_name контрактісі."""

from datetime import datetime, timezone

from domain.entities.student import Student

_NOW = datetime.now(timezone.utc)


def _make_student(**overrides: object) -> Student:
    defaults: dict[str, object] = dict(
        id="s1", classroom_id="c1", first_name="Айдос", last_name="Серіков",
        created_at=_NOW, updated_at=_NOW,
    )
    defaults.update(overrides)
    return Student(**defaults)


def test_valid_student_has_no_errors() -> None:
    assert _make_student().validate() == []


def test_empty_first_name_is_invalid() -> None:
    assert _make_student(first_name="").validate() != []


def test_empty_last_name_is_invalid() -> None:
    assert _make_student(last_name="").validate() != []


def test_empty_classroom_id_is_invalid() -> None:
    assert _make_student(classroom_id="").validate() != []


def test_display_name_is_lastname_firstname() -> None:
    student = _make_student(first_name="Айдос", last_name="Серіков")
    assert student.display_name == "Серіков Айдос"


def test_optional_fields_default_empty() -> None:
    student = _make_student()
    assert student.middle_name == ""
    assert student.student_code == ""
    assert student.notes == ""
    assert student.is_archived is False
