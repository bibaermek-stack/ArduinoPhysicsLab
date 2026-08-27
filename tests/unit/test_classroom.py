"""Classroom domain entity — validate() контрактісі."""

from datetime import datetime, timezone

from domain.entities.classroom import Classroom

_NOW = datetime.now(timezone.utc)


def test_valid_classroom_has_no_errors() -> None:
    classroom = Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW)
    assert classroom.validate() == []


def test_empty_name_is_invalid() -> None:
    classroom = Classroom(id="c1", name="", created_at=_NOW, updated_at=_NOW)
    assert classroom.validate() != []


def test_whitespace_only_name_is_invalid() -> None:
    classroom = Classroom(id="c1", name="   ", created_at=_NOW, updated_at=_NOW)
    assert classroom.validate() != []


def test_empty_id_is_invalid() -> None:
    classroom = Classroom(id="", name="8А", created_at=_NOW, updated_at=_NOW)
    assert classroom.validate() != []


def test_optional_fields_default_empty() -> None:
    classroom = Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW)
    assert classroom.academic_year == ""
    assert classroom.description == ""
    assert classroom.is_archived is False
