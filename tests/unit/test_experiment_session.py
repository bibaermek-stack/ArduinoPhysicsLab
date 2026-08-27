"""ExperimentSession үшін юнит-тесттер: сеанс тіршілік циклі."""

from datetime import datetime, timedelta, timezone

import pytest

from domain.entities.experiment_session import ExperimentSession
from domain.entities.measurement import Measurement


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _measurement(experiment_id: str = "e01") -> Measurement:
    return Measurement(
        timestamp=_utc_now(), values={"voltage": 5.0}, experiment_id=experiment_id
    )


def test_session_created_successfully() -> None:
    session = ExperimentSession(id="s01", experiment_id="e01", started_at=_utc_now())
    assert session.id == "s01"
    assert session.experiment_id == "e01"
    assert session.ended_at is None
    assert session.measurement_count == 0


def test_naive_started_at_raises_value_error() -> None:
    with pytest.raises(ValueError):
        ExperimentSession(id="s01", experiment_id="e01", started_at=datetime.now())


def test_add_measurement_appends_measurement() -> None:
    session = ExperimentSession(id="s01", experiment_id="e01", started_at=_utc_now())
    session.add_measurement(_measurement("e01"))
    assert session.measurement_count == 1
    assert session.measurements[0].experiment_id == "e01"


def test_add_measurement_with_mismatched_experiment_id_raises_value_error() -> None:
    session = ExperimentSession(id="s01", experiment_id="e01", started_at=_utc_now())
    with pytest.raises(ValueError):
        session.add_measurement(_measurement("e02"))


def test_measurement_count_reflects_added_measurements() -> None:
    session = ExperimentSession(id="s01", experiment_id="e01", started_at=_utc_now())
    session.add_measurement(_measurement("e01"))
    session.add_measurement(_measurement("e01"))
    session.add_measurement(_measurement("e01"))
    assert session.measurement_count == 3


def test_stop_sets_ended_at() -> None:
    session = ExperimentSession(id="s01", experiment_id="e01", started_at=_utc_now())
    assert session.ended_at is None
    session.stop()
    assert session.ended_at is not None


def test_stop_called_twice_keeps_first_ended_at() -> None:
    session = ExperimentSession(id="s01", experiment_id="e01", started_at=_utc_now())
    session.stop()
    first_ended_at = session.ended_at
    session.stop()
    assert session.ended_at == first_ended_at


def test_clear_removes_all_measurements() -> None:
    session = ExperimentSession(id="s01", experiment_id="e01", started_at=_utc_now())
    session.add_measurement(_measurement("e01"))
    session.add_measurement(_measurement("e01"))
    session.clear()
    assert session.measurement_count == 0


def test_duration_seconds_is_correct_for_stopped_session() -> None:
    started_at = _utc_now()
    session = ExperimentSession(id="s01", experiment_id="e01", started_at=started_at)
    session.ended_at = started_at + timedelta(seconds=5)
    assert session.duration_seconds() == pytest.approx(5.0)


def test_duration_seconds_is_non_negative_for_running_session() -> None:
    session = ExperimentSession(id="s01", experiment_id="e01", started_at=_utc_now())
    assert session.duration_seconds() >= 0.0
