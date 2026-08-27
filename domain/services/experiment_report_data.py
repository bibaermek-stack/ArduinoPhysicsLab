"""experiment_report_data — Phase 36 зертханалық есеп үшін дайын
статистика/талдау нәтижелерін ``ExperimentSession``-нен құрастыратын,
таза (Qt-сыз) domain сервисі.

Бұл модуль ЕШБІР жаңа физикалық/статистикалық формула ойлап таппайды —
тек ``domain.services.graph_analysis``-тегі БҰРЫННАН БАР, тәуелсіз
тестелген функцияларды (``compute_region_statistics``,
``compute_linear_regression``, ``compute_trapezoidal_integral``)
``ExperimentSession.measurements``-тің ТОЛЫҚ тарихына қолданады —
``LiveGraphWidget``-тің аймақ-талдау панелі қолданатын ДӘЛ СОЛ
математика, тек кіріс дереккөзі басқа (transient graph/region UI
күйіне ЕШБІР тәуелділік жоқ, сессия — жалғыз ақиқат көзі).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from domain.entities.experiment_definition import ExperimentDefinition
from domain.entities.experiment_session import ExperimentSession
from domain.services.graph_analysis import (
    RegressionResult,
    compute_linear_regression,
    compute_region_statistics,
    compute_trapezoidal_integral,
)

_POWER_CHANNEL_KEY = "power"
_TIME_CHANNEL_KEY = "time"
_MIN_FIT_POINTS = 2


@dataclass(frozen=True)
class ChannelReportStatistics:
    """Бір арнаның толық сессия бойынша сипаттамалық статистикасы —
    "current value" (соңғы нақты мән) + N/MIN/MAX/AVG. Дерек жоқ болса
    (``n=0``) барлық өріс ``None`` — жалған 0.0 ЕШҚАШАН қайтарылмайды.
    """

    channel_key: str
    display_name: str
    unit: str
    decimals: int
    n: int
    latest: float | None
    minimum: float | None
    maximum: float | None
    average: float | None


@dataclass(frozen=True)
class ExperimentReportData:
    """Бір ``ExperimentReportDialog``-қа арналған, толық есептелген
    (Qt-сыз) дерек снапшоты. Тек ОСЫ шақыру сәтіндегі сессия күйін
    бейнелейді — "live" болу қасиеті ("report updates when reopened")
    ЖАҢА снапшот әр рет ``build_experiment_report_data()`` арқылы
    қайта құрылуынан келеді, диалог ӨЗІ ешбір auto-refresh жасамайды.
    """

    sample_count: int
    duration_seconds: float
    channel_statistics: tuple[ChannelReportStatistics, ...] = field(default_factory=tuple)
    # Fit/slope (мыс. Ohm's Law-дағы R = ΔU/ΔI) — тек graph_show_fit=True
    # ЖӘНЕ жеткілікті нүкте болғанда ғана толтырылады, әйтпесе None
    # (§ "Never fabricate fields").
    fit_result: RegressionResult | None = None
    fit_x_symbol: str = "X"
    fit_y_symbol: str = "Y"
    fit_result_prefix: str = "slope"
    fit_unit: str | None = None
    fit_display_name: str | None = None
    # Тек 'power' арнасы бар тәжірибелерде толтырылады.
    power_average: float | None = None
    # Тек 'power' арнасы БАР ЖӘНЕ уақыттық режимде (graph_x_channel=None)
    # ғана — нақты ∫P dt (трапеция интеграциясы), naive P*t ЕМЕС.
    work_energy: float | None = None


def _channel_values(session: ExperimentSession, key: str) -> list[float]:
    values: list[float] = []
    for measurement in session.measurements:
        value = measurement.get_value(key)
        if value is not None:
            values.append(value)
    return values


def _elapsed_time_values(session: ExperimentSession) -> list[float]:
    """LiveGraphWidget.append_measurement()/CSVExporter-мен БІРДЕЙ
    fallback: "time" арнасы болса сол, әйтпесе бірінші үлгіден
    бастап есептелген нақты elapsed уақыт (ойдан шығарылған
    бірқалыпты тор ЕМЕС).
    """
    if not session.measurements:
        return []
    start_time = session.measurements[0].timestamp
    elapsed: list[float] = []
    for measurement in session.measurements:
        value = measurement.get_value(_TIME_CHANNEL_KEY)
        if value is None:
            value = (measurement.timestamp - start_time).total_seconds()
        elapsed.append(value)
    return elapsed


def _build_channel_statistics(
    experiment: ExperimentDefinition, session: ExperimentSession
) -> tuple[ChannelReportStatistics, ...]:
    results = []
    for channel in experiment.get_display_channels():
        values = _channel_values(session, channel.key)
        stats = compute_region_statistics(values)
        results.append(
            ChannelReportStatistics(
                channel_key=channel.key,
                display_name=channel.display_name,
                unit=channel.unit,
                decimals=channel.decimals,
                n=stats.n,
                latest=values[-1] if values else None,
                minimum=stats.minimum,
                maximum=stats.maximum,
                average=stats.average,
            )
        )
    return tuple(results)


def _has_channel(experiment: ExperimentDefinition, key: str) -> bool:
    return any(
        channel.key == key for channel in (*experiment.required_channels, *experiment.derived_channels)
    )


def _build_fit_result(
    experiment: ExperimentDefinition, session: ExperimentSession
) -> RegressionResult | None:
    if not experiment.graph_show_fit:
        return None
    if experiment.graph_x_channel is None or len(experiment.graph_y_channels) != 1:
        return None

    x_key = experiment.graph_x_channel
    y_key = experiment.graph_y_channels[0]
    x_values: list[float] = []
    y_values: list[float] = []
    for measurement in session.measurements:
        x_value = measurement.get_value(x_key)
        y_value = measurement.get_value(y_key)
        if x_value is None or y_value is None:
            continue
        x_values.append(x_value)
        y_values.append(y_value)

    if len(x_values) < _MIN_FIT_POINTS:
        return None
    result = compute_linear_regression(x_values, y_values)
    return result if result.valid else None


def build_experiment_report_data(
    experiment: ExperimentDefinition, session: ExperimentSession
) -> ExperimentReportData:
    """``experiment``/``session``-нен ТОЛЫҚ есеп снапшотын құрастырады.
    Бос сессия (``n=0``) қауіпсіз — ешбір exception, ешбір жалған мән.
    """
    channel_statistics = _build_channel_statistics(experiment, session)
    fit_result = _build_fit_result(experiment, session)

    power_average: float | None = None
    work_energy: float | None = None
    if _has_channel(experiment, _POWER_CHANNEL_KEY):
        power_values = _channel_values(session, _POWER_CHANNEL_KEY)
        power_stats = compute_region_statistics(power_values)
        power_average = power_stats.average

        if experiment.graph_x_channel is None and power_values:
            time_values = _elapsed_time_values(session)
            # power_values тек "power" мәні бар үлгілерден жиналды, ал
            # time_values БАРЛЫҚ session.measurements-тен — сәйкес
            # индекстеу үшін ЕКЕУІН БІРГЕ, ТЕК 'power' бар жерде қайта
            # жинаймыз (ешбір интерполяция/ойдан шығарылған уақыт ЖОҚ).
            paired_time: list[float] = []
            paired_power: list[float] = []
            for measurement, elapsed in zip(session.measurements, time_values):
                value = measurement.get_value(_POWER_CHANNEL_KEY)
                if value is not None:
                    paired_time.append(elapsed)
                    paired_power.append(value)
            work_energy = compute_trapezoidal_integral(paired_time, paired_power)

    return ExperimentReportData(
        sample_count=session.measurement_count,
        duration_seconds=session.duration_seconds(),
        channel_statistics=channel_statistics,
        fit_result=fit_result,
        fit_x_symbol=experiment.graph_fit_x_symbol,
        fit_y_symbol=experiment.graph_fit_y_symbol,
        fit_result_prefix=experiment.graph_fit_result_prefix,
        fit_unit=experiment.graph_fit_unit,
        fit_display_name=experiment.graph_fit_display_name,
        power_average=power_average,
        work_energy=work_energy,
    )
