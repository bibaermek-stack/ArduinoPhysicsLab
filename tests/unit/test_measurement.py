"""Measurement үшін юнит-тесттер: негізгі құрылыс, мән алу және шеткі жағдайлар."""

from datetime import datetime, timezone

import pytest

from domain.entities.measurement import Measurement


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def test_accepts_timezone_aware_timestamp() -> None:
    measurement = Measurement(
        timestamp=_utc_now(),
        values={"voltage": 5.0},
        experiment_id="e01",
    )
    assert measurement.experiment_id == "e01"


def test_naive_timestamp_raises_value_error() -> None:
    with pytest.raises(ValueError):
        Measurement(
            timestamp=datetime.now(),  # naive, tzinfo жоқ
            values={"voltage": 5.0},
            experiment_id="e01",
        )


def test_empty_experiment_id_raises_value_error() -> None:
    with pytest.raises(ValueError):
        Measurement(
            timestamp=_utc_now(),
            values={"voltage": 5.0},
            experiment_id="",
        )


def test_get_value_returns_raw_value() -> None:
    measurement = Measurement(
        timestamp=_utc_now(),
        values={"voltage": 5.0},
        experiment_id="e01",
    )
    assert measurement.get_value("voltage") == 5.0


def test_get_value_returns_derived_value() -> None:
    measurement = Measurement(
        timestamp=_utc_now(),
        values={"voltage": 5.0},
        experiment_id="e01",
        derived_values={"resistance": 25.0},
    )
    assert measurement.get_value("resistance") == 25.0


def test_get_value_returns_none_for_missing_key() -> None:
    measurement = Measurement(
        timestamp=_utc_now(),
        values={"voltage": 5.0},
        experiment_id="e01",
    )
    assert measurement.get_value("unknown") is None


def test_all_values_merges_raw_and_derived() -> None:
    measurement = Measurement(
        timestamp=_utc_now(),
        values={"voltage": 5.0, "current": 0.2},
        experiment_id="e01",
        derived_values={"resistance": 25.0},
    )
    assert measurement.all_values() == {
        "voltage": 5.0,
        "current": 0.2,
        "resistance": 25.0,
    }


def test_mutating_original_values_dict_does_not_affect_measurement() -> None:
    """Measurement — өзгермейтін (immutable) тарихи жазба болуы тиіс:
    оны құрғаннан кейін сыртта пайдаланылған dict өзгерсе, объект
    ішіндегі мән өзгермеуі керек.

    ЕСКЕРТУ: бұл тест ағымдағы production кодында ҚҰЛАЙДЫ. Себебі
    ``@dataclass(frozen=True)`` тек атрибутты ҚАЙТА ТАҒАЙЫНДАУҒА
    (`measurement.values = ...`) тыйым салады, бірақ __post_init__
    берілген ``values``/``derived_values`` dict-теріне қорғаныш
    көшірме (defensive copy) жасамайды — сол СІЛТЕМЕНІҢ (reference)
    өзі сақталады. Сондықтан сыртта dict мутацияланса, Measurement
    ішіндегі мән де бірге өзгереді. Бұл production кодтағы белгілі
    олқылық, тапсырма бойынша дереу түзетілмейді.
    """
    values = {"voltage": 5.0}
    measurement = Measurement(
        timestamp=_utc_now(),
        values=values,
        experiment_id="e01",
    )
    values["voltage"] = 999.0
    assert measurement.values["voltage"] == 5.0
