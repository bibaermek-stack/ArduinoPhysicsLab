"""domain.services.graph_analysis (Phase 33B) үшін юнит-тесттер —
белгілі математикалық деректер жиынтығымен: сипаттамалық статистика,
сызықтық регрессия (соның ішінде деградацияланған жағдайлар), трапеция
интеграциясы. Ешбір Qt/pyqtgraph қажет емес — таза функциялар.
"""

import math

import numpy as np
import pytest

from domain.services.graph_analysis import (
    DeltaResult,
    RegionStatistics,
    RegressionResult,
    compute_delta,
    compute_linear_regression,
    compute_region_statistics,
    compute_residuals,
    compute_trapezoidal_integral,
    indices_in_range,
    nearest_index,
)

# ---- nearest_index() -------------------------------------------------


def test_nearest_index_empty_returns_negative_one() -> None:
    assert nearest_index([], 1.0) == -1


def test_nearest_index_picks_closest() -> None:
    assert nearest_index([0.0, 1.0, 2.0, 3.0], 2.2) == 2


# ---- indices_in_range() ------------------------------------------------


def test_indices_in_range_selects_inclusive_bounds() -> None:
    mask = indices_in_range([0.0, 1.0, 2.0, 3.0, 4.0], 1.0, 3.0)
    assert list(mask) == [False, True, True, True, False]


def test_indices_in_range_handles_reversed_bounds() -> None:
    mask = indices_in_range([0.0, 1.0, 2.0, 3.0], 3.0, 1.0)
    assert list(mask) == [False, True, True, True]


def test_indices_in_range_empty_input() -> None:
    mask = indices_in_range([], 0.0, 1.0)
    assert len(mask) == 0


# ---- compute_region_statistics() ----------------------------------------


def test_region_statistics_known_dataset() -> None:
    """MIN/MAX/AVG/Δ/σ — қолмен есептелген белгілі мәндермен тексеріледі."""
    values = [6.21, 6.87, 6.54, 6.40, 6.68]
    stats = compute_region_statistics(values)

    assert stats.n == 5
    assert stats.minimum == pytest.approx(6.21)
    assert stats.maximum == pytest.approx(6.87)
    assert stats.average == pytest.approx(sum(values) / 5)
    assert stats.delta == pytest.approx(6.87 - 6.21)
    assert stats.std_dev == pytest.approx(np.std(values, ddof=0))


def test_region_statistics_empty_returns_none_fields_not_fake_zero() -> None:
    stats = compute_region_statistics([])
    assert stats.n == 0
    assert stats.minimum is None
    assert stats.maximum is None
    assert stats.average is None
    assert stats.delta is None
    assert stats.std_dev is None


def test_region_statistics_single_value_has_zero_spread() -> None:
    stats = compute_region_statistics([5.0])
    assert stats.n == 1
    assert stats.minimum == stats.maximum == stats.average == 5.0
    assert stats.delta == 0.0
    assert stats.std_dev == 0.0


def test_coefficient_of_variation_known_value() -> None:
    # constant + tiny noise: std=0.1, avg=10 -> CV = 1%
    stats = RegionStatistics(n=3, minimum=9.9, maximum=10.1, average=10.0, delta=0.2, std_dev=0.1)
    assert stats.coefficient_of_variation_percent == pytest.approx(1.0)


def test_coefficient_of_variation_undefined_when_average_zero() -> None:
    stats = RegionStatistics(n=2, minimum=-1.0, maximum=1.0, average=0.0, delta=2.0, std_dev=1.0)
    assert stats.coefficient_of_variation_percent is None


def test_coefficient_of_variation_undefined_when_no_data() -> None:
    stats = compute_region_statistics([])
    assert stats.coefficient_of_variation_percent is None


# ---- compute_linear_regression() ----------------------------------------


def test_linear_regression_exact_line() -> None:
    """y = 2x + 3 дәл сызығы — slope/intercept/R²/RMSE дәл болуы тиіс."""
    x_values = [0.0, 1.0, 2.0, 3.0, 4.0]
    y_values = [3.0, 5.0, 7.0, 9.0, 11.0]

    result = compute_linear_regression(x_values, y_values)

    assert result.valid is True
    assert result.slope == pytest.approx(2.0)
    assert result.intercept == pytest.approx(3.0)
    assert result.r_squared == pytest.approx(1.0)
    assert result.rmse == pytest.approx(0.0, abs=1e-9)
    assert result.n == 5


def test_linear_regression_known_ohms_law_dataset() -> None:
    """R = 100 Ω, b = 0.02 V — §19 мысалы бойынша дәл сол датасет."""
    resistance = 100.0
    intercept = 0.02
    currents = [0.01, 0.02, 0.03, 0.04, 0.05]
    voltages = [resistance * i + intercept for i in currents]

    result = compute_linear_regression(currents, voltages)

    assert result.valid is True
    assert result.slope == pytest.approx(resistance, rel=1e-9)
    assert result.intercept == pytest.approx(intercept, rel=1e-6, abs=1e-9)
    assert result.r_squared == pytest.approx(1.0)


def test_linear_regression_with_noise_has_reasonable_rmse() -> None:
    rng = np.random.default_rng(42)
    x_values = np.linspace(0, 10, 50)
    noise = rng.normal(0, 0.05, size=50)
    y_values = 2.0 * x_values + 1.0 + noise

    result = compute_linear_regression(x_values.tolist(), y_values.tolist())

    assert result.valid is True
    assert result.slope == pytest.approx(2.0, abs=0.05)
    assert 0 < result.rmse < 0.2
    assert result.r_squared > 0.99


def test_linear_regression_fewer_than_two_points_is_invalid() -> None:
    result = compute_linear_regression([1.0], [1.0])
    assert result.valid is False
    assert result.slope is None
    assert result.intercept is None
    assert result.r_squared is None
    assert result.rmse is None
    assert result.n == 1


def test_linear_regression_zero_points_is_invalid() -> None:
    result = compute_linear_regression([], [])
    assert result.valid is False
    assert result.n == 0


def test_linear_regression_identical_x_values_is_invalid() -> None:
    """Барлық X мәні бірдей — вертикаль сызық, slope анықталмайды."""
    result = compute_linear_regression([5.0, 5.0, 5.0], [1.0, 2.0, 3.0])
    assert result.valid is False
    assert result.slope is None


def test_linear_regression_does_not_crash_on_nan_or_inf() -> None:
    result = compute_linear_regression([1.0, float("nan"), 3.0], [1.0, 2.0, 3.0])
    assert result.valid is False

    result2 = compute_linear_regression([1.0, float("inf"), 3.0], [1.0, 2.0, 3.0])
    assert result2.valid is False


def test_linear_regression_constant_y_gives_r_squared_none_not_fake() -> None:
    """Барлық Y бірдей — ss_tot=0, R² 0/0 болмайды, None (fake 0/1 емес)."""
    result = compute_linear_regression([1.0, 2.0, 3.0], [5.0, 5.0, 5.0])
    assert result.valid is True
    assert result.slope == pytest.approx(0.0, abs=1e-9)
    assert result.r_squared is None
    assert result.rmse == pytest.approx(0.0, abs=1e-9)


def test_linear_regression_never_raises_on_degenerate_input() -> None:
    degenerate_cases = [
        ([], []),
        ([1.0], [1.0]),
        ([1.0, 1.0], [2.0, 2.0]),
        ([float("nan"), float("nan")], [1.0, 2.0]),
    ]
    for x_values, y_values in degenerate_cases:
        result = compute_linear_regression(x_values, y_values)  # exception шықпауы керек
        assert isinstance(result, RegressionResult)


# ---- compute_trapezoidal_integral() --------------------------------------


def test_trapezoidal_integral_constant_power() -> None:
    """P(t) = 2W тұрақты, t: 0..10s -> W = 2*10 = 20 J дәл."""
    t_values = [0.0, 2.0, 4.0, 6.0, 8.0, 10.0]
    p_values = [2.0] * 6

    energy = compute_trapezoidal_integral(t_values, p_values)

    assert energy == pytest.approx(20.0)


def test_trapezoidal_integral_linear_ramp_analytically_known() -> None:
    """P(t) = t, t: 0..10s -> W = ∫t dt = t²/2 |0..10 = 50 J (аналитикалық)."""
    t_values = np.linspace(0, 10, 1000).tolist()
    p_values = t_values  # P(t) = t

    energy = compute_trapezoidal_integral(t_values, p_values)

    assert energy == pytest.approx(50.0, rel=1e-3)


def test_trapezoidal_integral_uses_actual_uneven_timestamps() -> None:
    """Нақты timestamp-тар БІРКЕЛКІ ЕМЕС болса да, дұрыс есептейді —
    ешбір "ойдан шығарылған" бірқалыпты уақыт торы қолданылмайды.
    """
    t_values = [0.0, 1.0, 1.5, 4.0]  # ретсіз аралықтар
    p_values = [1.0, 1.0, 1.0, 1.0]  # тұрақты қуат

    energy = compute_trapezoidal_integral(t_values, p_values)

    assert energy == pytest.approx(4.0)  # P=1 тұрақты * толық Δt=4.0


def test_trapezoidal_integral_insufficient_points_returns_none() -> None:
    assert compute_trapezoidal_integral([1.0], [1.0]) is None
    assert compute_trapezoidal_integral([], []) is None


def test_trapezoidal_integral_never_raises_on_nan() -> None:
    assert compute_trapezoidal_integral([0.0, float("nan")], [1.0, 1.0]) is None


def test_trapezoidal_integral_large_dataset_matches_analytic() -> None:
    """§17 Performance: 5000 нүктелі dataset те дәл, жылдам есептеледі."""
    t_values = np.linspace(0, 100, 5000)
    p_values = np.full(5000, 3.0)  # тұрақты 3W

    energy = compute_trapezoidal_integral(t_values.tolist(), p_values.tolist())

    assert energy == pytest.approx(300.0, rel=1e-6)  # 3W * 100s = 300J


# ---- Phase 34: standard_error_of_mean (SEM) ------------------------------


def test_sem_known_value() -> None:
    # std=0.1, n=4 -> SEM = 0.1/2 = 0.05
    stats = RegionStatistics(n=4, minimum=9.9, maximum=10.1, average=10.0, delta=0.2, std_dev=0.1)
    assert stats.standard_error_of_mean == pytest.approx(0.05)


def test_sem_undefined_for_single_sample() -> None:
    stats = RegionStatistics(n=1, minimum=5.0, maximum=5.0, average=5.0, delta=0.0, std_dev=0.0)
    assert stats.standard_error_of_mean is None


def test_sem_undefined_for_empty_data() -> None:
    stats = compute_region_statistics([])
    assert stats.standard_error_of_mean is None


def test_sem_matches_manual_formula_for_real_dataset() -> None:
    values = [6.21, 6.87, 6.54, 6.40, 6.68]
    stats = compute_region_statistics(values)
    expected = stats.std_dev / math.sqrt(len(values))
    assert stats.standard_error_of_mean == pytest.approx(expected)


# ---- Phase 34: compute_delta() -------------------------------------------


def test_compute_delta_normal_case() -> None:
    result = compute_delta(0.020, 1.75, 0.081, 7.01)
    assert isinstance(result, DeltaResult)
    assert result.dx == pytest.approx(0.061)
    assert result.dy == pytest.approx(5.26)
    assert result.ratio == pytest.approx(5.26 / 0.061)


def test_compute_delta_zero_dx_gives_none_ratio() -> None:
    result = compute_delta(2.0, 1.0, 2.0, 5.0)
    assert result.dx == 0.0
    assert result.dy == pytest.approx(4.0)
    assert result.ratio is None


def test_compute_delta_preserves_negative_sign_not_abs() -> None:
    """B алдында А орналассын (кері ретте таңдалса) — таңба сақталуы
    тиіс, физикалық мағыналы теріс градиент (мыс. салқындау) жасырылмайды.
    """
    result = compute_delta(10.0, 100.0, 5.0, 50.0)
    assert result.dx == pytest.approx(-5.0)
    assert result.dy == pytest.approx(-50.0)
    assert result.ratio == pytest.approx(10.0)


# ---- Phase 34: compute_residuals() ---------------------------------------


def test_compute_residuals_matches_manual_calculation() -> None:
    x_values = [0.0, 1.0, 2.0, 3.0]
    y_values = [3.1, 4.9, 7.2, 8.8]  # y ~= 2x + 3, бірнеше шу
    slope, intercept = 2.0, 3.0

    residuals = compute_residuals(x_values, y_values, slope, intercept)

    expected = [y - (slope * x + intercept) for x, y in zip(x_values, y_values)]
    assert residuals == pytest.approx(expected)


def test_compute_residuals_exact_fit_is_all_zero() -> None:
    x_values = [0.0, 1.0, 2.0, 3.0]
    y_values = [3.0, 5.0, 7.0, 9.0]  # дәл y = 2x + 3

    residuals = compute_residuals(x_values, y_values, 2.0, 3.0)

    assert residuals == pytest.approx([0.0, 0.0, 0.0, 0.0], abs=1e-9)


def test_compute_residuals_empty_input_returns_empty_list() -> None:
    assert compute_residuals([], [], 1.0, 0.0) == []


def test_compute_residuals_mismatched_length_returns_empty_list() -> None:
    assert compute_residuals([1.0, 2.0], [1.0], 1.0, 0.0) == []
