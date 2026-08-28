"""CalculationEngine — R = U/I, P = U×I, A = P×t формулаларын тексеру."""

from domain.entities.experiment_definition import ExperimentDefinition
from domain.services.calculation_engine import CURRENT_EPSILON, CalculationEngine
from modules.electricity.experiments_config import (
    CURRENT_CHANNEL,
    CURRENT_WORK_POWER_EXPERIMENT,
    OHMS_LAW_EXPERIMENT,
    VOLTAGE_CHANNEL,
)


def _definition(*formula_keys: str) -> ExperimentDefinition:
    return ExperimentDefinition(
        id="calc-test",
        title="Есептеу тесті",
        description="",
        required_channels=(VOLTAGE_CHANNEL, CURRENT_CHANNEL),
        formulas={key: key for key in formula_keys},
    )


def test_resistance_is_voltage_over_current() -> None:
    result = CalculationEngine().calculate(
        {"voltage": 5.0, "current": 0.2}, _definition("resistance")
    )

    assert result.values["resistance"] == 25.0
    assert result.errors == ()
    assert result.warnings == ()


def test_ohms_law_experiment_uses_resistance_formula() -> None:
    result = CalculationEngine().calculate(
        {"voltage": 4.5, "current": 0.15}, OHMS_LAW_EXPERIMENT
    )

    assert result.values["resistance"] == 30.0
    assert "power" not in result.values


def test_power_is_voltage_times_current() -> None:
    result = CalculationEngine().calculate(
        {"voltage": 5.0, "current": 0.2}, _definition("power")
    )

    assert result.values["power"] == 1.0
    assert result.errors == ()


def test_work_is_power_times_time() -> None:
    result = CalculationEngine().calculate(
        {"power": 2.0, "time": 10.0}, _definition("work")
    )

    assert result.values["work"] == 20.0


def test_work_falls_back_to_u_i_t_when_power_missing() -> None:
    result = CalculationEngine().calculate(
        {"voltage": 5.0, "current": 0.2, "time": 10.0}, _definition("work")
    )

    assert result.values["work"] == 10.0


def test_work_uses_elapsed_seconds_when_time_channel_missing() -> None:
    result = CalculationEngine().calculate(
        {"voltage": 5.0, "current": 0.2},
        _definition("work"),
        elapsed_seconds=4.0,
    )

    assert result.values["work"] == 4.0


def test_current_work_power_experiment_computes_power_and_work() -> None:
    result = CalculationEngine().calculate(
        {"voltage": 6.0, "current": 0.5, "time": 8.0},
        CURRENT_WORK_POWER_EXPERIMENT,
    )

    assert result.values["power"] == 3.0
    assert result.values["work"] == 24.0
    assert result.errors == ()


def test_near_zero_current_does_not_compute_resistance() -> None:
    result = CalculationEngine().calculate(
        {"voltage": 5.0, "current": CURRENT_EPSILON / 2},
        _definition("resistance", "power"),
    )

    assert "resistance" not in result.values
    assert any("current нөлге тым жақын" in error for error in result.errors)
    assert result.values["power"] == 5.0 * (CURRENT_EPSILON / 2)


def test_missing_voltage_reports_error_without_raising() -> None:
    result = CalculationEngine().calculate({"current": 0.2}, _definition("power"))

    assert result.values == {}
    assert any("voltage мәні жоқ" in error for error in result.errors)


def test_unknown_formula_is_a_warning_not_an_error() -> None:
    result = CalculationEngine().calculate(
        {"voltage": 1.0, "current": 1.0}, _definition("capacitance")
    )

    assert result.values == {}
    assert result.errors == ()
    assert any("белгілі калькулятор жоқ" in warning for warning in result.warnings)


def test_negative_time_rejects_work() -> None:
    result = CalculationEngine().calculate(
        {"power": 1.0, "time": -0.1}, _definition("work")
    )

    assert "work" not in result.values
    assert any("теріс" in error for error in result.errors)


def test_one_failed_formula_does_not_block_the_others() -> None:
    result = CalculationEngine().calculate(
        {"voltage": 5.0, "current": 0.2}, _definition("capacitance", "power")
    )

    assert result.values["power"] == 1.0
    assert any("белгілі калькулятор жоқ" in warning for warning in result.warnings)
