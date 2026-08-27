"""build_automatic_conclusion() (Phase 38B) — таза domain функция
тестері: генерик fit/law-agreement/қуат-жұмыс/арна-орташа секциялары
ЕШБІР эксперимент ID-ге тәуелсіз, тек ``ExperimentReportData``-дан
есептеледі.
"""

from domain.services.experiment_conclusion import build_automatic_conclusion
from domain.services.experiment_report_data import (
    ChannelReportStatistics,
    ExperimentReportData,
)
from domain.services.graph_analysis import RegressionResult


def _make_stats(
    display_name: str = "Кернеу",
    unit: str = "V",
    decimals: int = 3,
    n: int = 5,
    average: float | None = 5.0,
) -> ChannelReportStatistics:
    return ChannelReportStatistics(
        channel_key="voltage",
        display_name=display_name,
        unit=unit,
        decimals=decimals,
        n=n,
        latest=average,
        minimum=average,
        maximum=average,
        average=average,
    )


def test_empty_session_returns_neutral_sentence() -> None:
    report_data = ExperimentReportData(sample_count=0, duration_seconds=0.0)

    text = build_automatic_conclusion(report_data)

    assert "әлі жоқ" in text


def test_fit_with_high_r_squared_states_law_agreement() -> None:
    fit = RegressionResult(valid=True, slope=12.3, intercept=0.1, r_squared=0.99, rmse=0.01, n=6)
    report_data = ExperimentReportData(
        sample_count=6,
        duration_seconds=10.0,
        fit_result=fit,
        fit_result_prefix="R",
        fit_unit="Ω",
        fit_display_name="Кедергі",
    )

    text = build_automatic_conclusion(report_data)

    assert "Кедергі ≈ 12.300 Ω" in text
    assert "R²=0.990" in text
    assert "сәйкес келеді" in text
    assert "толық сәйкес келмейді" not in text


def test_fit_with_low_r_squared_states_law_disagreement() -> None:
    fit = RegressionResult(valid=True, slope=1.0, intercept=0.1, r_squared=0.2, rmse=0.5, n=6)
    report_data = ExperimentReportData(
        sample_count=6,
        duration_seconds=10.0,
        fit_result=fit,
        fit_result_prefix="k",
        fit_unit="Ω/°C",
    )

    text = build_automatic_conclusion(report_data)

    assert "k ≈ 1.000 Ω/°C" in text
    assert "толық сәйкес келмейді" in text


def test_fit_without_r_squared_omits_verdict() -> None:
    fit = RegressionResult(valid=True, slope=2.0, intercept=0.0, r_squared=None, rmse=None, n=2)
    report_data = ExperimentReportData(
        sample_count=2, duration_seconds=1.0, fit_result=fit, fit_result_prefix="R"
    )

    text = build_automatic_conclusion(report_data)

    assert "R ≈ 2.000" in text
    assert "сәйкес" not in text


def test_power_and_work_present_reports_both() -> None:
    report_data = ExperimentReportData(
        sample_count=10, duration_seconds=5.0, power_average=3.14159, work_energy=18.6
    )

    text = build_automatic_conclusion(report_data)

    assert "Орташа қуат ≈ 3.142 Вт." in text
    assert "Жұмыс/энергия ≈ 18.600 Дж." in text


def test_no_fit_no_power_falls_back_to_channel_averages() -> None:
    stats = (_make_stats(display_name="Кернеу", unit="V", average=5.0),)
    report_data = ExperimentReportData(sample_count=5, duration_seconds=1.0, channel_statistics=stats)

    text = build_automatic_conclusion(report_data)

    assert "Өлшенген орташа мәндер:" in text
    assert "Кернеу ≈ 5.000 V" in text


def test_channel_fallback_skips_channels_with_no_samples() -> None:
    empty_stats = _make_stats(display_name="Ток", unit="A", n=0, average=None)
    real_stats = _make_stats(display_name="Кернеу", unit="V", n=5, average=5.0)
    report_data = ExperimentReportData(
        sample_count=5, duration_seconds=1.0, channel_statistics=(empty_stats, real_stats)
    )

    text = build_automatic_conclusion(report_data)

    assert "Ток" not in text
    assert "Кернеу ≈ 5.000 V" in text


def test_power_present_still_includes_other_channel_averages() -> None:
    # Тізбектей/Параллель қосу: power_average БАР (Қуат авто-есептелген),
    # бірақ кедергі (resistance) де channel_statistics-те бар — екеуі де
    # көрінуі тиіс, "Қуат" қайталанбауы тиіс.
    resistance_stats = ChannelReportStatistics(
        channel_key="resistance", display_name="Кедергі", unit="Ω", decimals=2,
        n=5, latest=26.0, minimum=25.0, maximum=27.0, average=26.0,
    )
    power_stats = ChannelReportStatistics(
        channel_key="power", display_name="Қуат", unit="W", decimals=3,
        n=5, latest=1.04, minimum=1.0, maximum=1.08, average=1.04,
    )
    report_data = ExperimentReportData(
        sample_count=5,
        duration_seconds=1.0,
        power_average=1.04,
        channel_statistics=(resistance_stats, power_stats),
    )

    text = build_automatic_conclusion(report_data)

    assert "Орташа қуат ≈ 1.040 Вт." in text
    assert "Кедергі ≈ 26.00 Ω" in text
    assert text.count("1.040") == 1  # қуат тек бір рет көрінеді, қайталанбайды


def test_no_usable_data_at_all_returns_no_data_sentence() -> None:
    # sample_count>0 бірақ channel_statistics бос — теориялық шеткі жағдай.
    report_data = ExperimentReportData(sample_count=3, duration_seconds=1.0)

    text = build_automatic_conclusion(report_data)

    assert "жеткілікті дерек жоқ" in text
