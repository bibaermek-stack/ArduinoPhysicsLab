"""DataValidator — SensorChannel диапазон/тип/міндетті арна тексерісі."""

from core.exceptions import AppException, SerialError, ValidationError
from domain.entities.experiment_definition import ExperimentDefinition
from domain.services.data_validator import DataValidator
from modules.electricity.experiments_config import (
    CURRENT_CHANNEL,
    CURRENT_VOLTAGE_EXPERIMENT,
    TIME_CHANNEL,
    VOLTAGE_CHANNEL,
)


def test_validation_and_serial_errors_are_app_exceptions() -> None:
    assert issubclass(ValidationError, AppException)
    assert issubclass(SerialError, AppException)
    assert str(ValidationError("кернеу диапазоннан тыс")) == "кернеу диапазоннан тыс"


def test_valid_voltage_and_current_pass() -> None:
    result = DataValidator().validate(
        {"voltage": 5.024, "current": 0.218}, CURRENT_VOLTAGE_EXPERIMENT
    )

    assert result.is_valid is True
    assert result.cleaned_values["voltage"] == 5.024
    assert result.cleaned_values["current"] == 0.218
    assert result.errors == ()


def test_voltage_above_maximum_is_invalid() -> None:
    result = DataValidator().validate(
        {"voltage": 30.1, "current": 0.2}, CURRENT_VOLTAGE_EXPERIMENT
    )

    assert result.is_valid is False
    assert "voltage" not in result.cleaned_values
    assert any("максимум" in error for error in result.errors)


def test_current_below_minimum_is_invalid() -> None:
    result = DataValidator().validate(
        {"voltage": 5.0, "current": -0.01}, CURRENT_VOLTAGE_EXPERIMENT
    )

    assert result.is_valid is False
    assert any("минимум" in error for error in result.errors)


def test_missing_required_channel_is_an_error() -> None:
    result = DataValidator().validate({"voltage": 5.0}, CURRENT_VOLTAGE_EXPERIMENT)

    assert result.is_valid is False
    assert any("current" in error and "міндетті" in error for error in result.errors)


def test_unknown_channel_is_a_warning_and_is_dropped() -> None:
    result = DataValidator().validate(
        {"voltage": 5.0, "current": 0.2, "lux": 120.0},
        CURRENT_VOLTAGE_EXPERIMENT,
    )

    assert result.is_valid is True
    assert "lux" not in result.cleaned_values
    assert any("lux" in warning and "анықталмаған" in warning for warning in result.warnings)


def test_optional_time_may_be_absent() -> None:
    definition = ExperimentDefinition(
        id="t",
        title="t",
        description="",
        required_channels=(VOLTAGE_CHANNEL, CURRENT_CHANNEL, TIME_CHANNEL),
    )

    result = DataValidator().validate({"voltage": 1.0, "current": 0.1}, definition)

    assert result.is_valid is True
    assert "time" not in result.cleaned_values


def test_boolean_is_not_accepted_as_a_number() -> None:
    result = DataValidator().validate(
        {"voltage": True, "current": 0.2}, CURRENT_VOLTAGE_EXPERIMENT  # type: ignore[dict-item]
    )

    assert result.is_valid is False
    assert any("float-қа түрлендірілмейді" in error for error in result.errors)


def test_numeric_string_is_accepted() -> None:
    result = DataValidator().validate(
        {"voltage": "5.5", "current": "0.25"},  # type: ignore[dict-item]
        CURRENT_VOLTAGE_EXPERIMENT,
    )

    assert result.is_valid is True
    assert result.cleaned_values["voltage"] == 5.5
    assert result.cleaned_values["current"] == 0.25


def test_non_numeric_string_is_rejected() -> None:
    result = DataValidator().validate(
        {"voltage": "abc", "current": 0.2},  # type: ignore[dict-item]
        CURRENT_VOLTAGE_EXPERIMENT,
    )

    assert result.is_valid is False
    assert any("voltage" in error for error in result.errors)


def test_does_not_mutate_raw_values() -> None:
    raw = {"voltage": 5.0, "current": 0.2}
    DataValidator().validate(raw, CURRENT_VOLTAGE_EXPERIMENT)
    assert raw == {"voltage": 5.0, "current": 0.2}
