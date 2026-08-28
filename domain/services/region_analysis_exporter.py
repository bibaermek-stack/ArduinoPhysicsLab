"""RegionAnalysisExporter — таңдалған аралық талдауының (Phase 33B)
қысқа CSV қорытындысын жазатын domain сервисі.

Бұл сервис raw Measurement экспортына (``CSVExporter``/``ExcelExporter``/
``PDFExporter`` — ``ExperimentSession.measurements``-тен оқитын, session-
негізді толық тарихты жазатын) ЕШБІР қатысы жоқ және ОЛАРДЫ АЛМАСТЫРМАЙДЫ
— тек ``GraphAnalysisPanel``-де көрсетілетін region-статистика/
регрессия/туынды нәтижелердің қосымша, факультативті қорытындысын
сақтайды (§16: "Never replace raw-data export with summary-only export").
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field

from domain.services.export_io import write_export
from domain.services.graph_analysis import RegressionResult


@dataclass(frozen=True)
class ChannelAnalysisSummary:
    display_name: str
    unit: str
    n: int
    minimum: float | None
    maximum: float | None
    average: float | None
    delta: float | None
    std_dev: float | None
    cv_percent: float | None
    # Phase 34 §4: SEM = σ/√N — таза статистикалық шама, аспаптық/
    # калибрлеу қателігінен бөлек (default=None — ескі шақырушы кодтар
    # өзгеріссіз жұмыс істейді).
    sem: float | None = None


@dataclass(frozen=True)
class RegionAnalysisSummary:
    """Бір экспорт сәтіндегі толық аралық талдау снапшоты — тек ОҚУ,
    ешбір raw Measurement/session мутацияламайды.
    """

    t1: float
    t2: float
    channels: tuple[ChannelAnalysisSummary, ...] = field(default_factory=tuple)
    regression_scope: str | None = None
    regression_slope: float | None = None
    regression_intercept: float | None = None
    regression_r_squared: float | None = None
    regression_rmse: float | None = None
    regression_n: int | None = None
    power_avg: float | None = None
    power_max: float | None = None
    energy: float | None = None


def _format_value(value: float | None) -> str:
    return "" if value is None else f"{value:.6f}"


class RegionAnalysisExporter:
    """``RegionAnalysisSummary``-ды қарапайым, Excel аша алатын CSV
    файлына жазады.
    """

    def export(self, summary: RegionAnalysisSummary, output_path: str) -> bool:
        def _write() -> None:
            with open(output_path, mode="w", encoding="utf-8", newline="") as csv_file:
                writer = csv.writer(csv_file)
                writer.writerow(["t1 (s)", f"{summary.t1:.4f}"])
                writer.writerow(["t2 (s)", f"{summary.t2:.4f}"])
                writer.writerow(["dt (s)", f"{summary.t2 - summary.t1:.4f}"])
                writer.writerow([])

                writer.writerow(
                    ["Channel", "Unit", "N", "MIN", "MAX", "AVG", "Delta", "StdDev", "CV %", "SEM"]
                )
                for channel in summary.channels:
                    writer.writerow(
                        [
                            channel.display_name,
                            channel.unit,
                            channel.n,
                            _format_value(channel.minimum),
                            _format_value(channel.maximum),
                            _format_value(channel.average),
                            _format_value(channel.delta),
                            _format_value(channel.std_dev),
                            _format_value(channel.cv_percent),
                            _format_value(channel.sem),
                        ]
                    )

                if summary.regression_slope is not None:
                    writer.writerow([])
                    writer.writerow(["Regression scope", summary.regression_scope or ""])
                    writer.writerow(["slope", _format_value(summary.regression_slope)])
                    writer.writerow(["intercept", _format_value(summary.regression_intercept)])
                    writer.writerow(["R2", _format_value(summary.regression_r_squared)])
                    writer.writerow(["RMSE", _format_value(summary.regression_rmse)])
                    writer.writerow(["N", summary.regression_n])

                if summary.energy is not None:
                    writer.writerow([])
                    writer.writerow(["P_avg (W)", _format_value(summary.power_avg)])
                    writer.writerow(["P_max (W)", _format_value(summary.power_max)])
                    writer.writerow(["Energy (J)", _format_value(summary.energy)])

        return write_export(output_path, _write)


def _format_signed(value: float) -> str:
    sign = "-" if value < 0 else "+"
    return f"{sign} {abs(value):.3f}"


def format_fit_summary(
    title: str,
    n: int,
    x_symbol: str,
    x_range: tuple[float, float] | None,
    x_unit: str,
    y_symbol: str,
    y_range: tuple[float, float] | None,
    y_unit: str,
    fit_result_prefix: str,
    fit_unit: str | None,
    result: RegressionResult,
) -> str:
    """Phase 34 §10 "Нәтижені көшіру" — region ЖОҚ кездегі (толық
    ағымдағы fit dataset-ке негізделген) жай мәтіндік қорытынды. Fit
    жарамсыз болса тек N/ауқым жолдары қайтарылады — жалған теңдеу/R
    ЕШҚАШАН көрсетілмейді (§4 конвенциясы: "prefer unavailable over
    fabricated").
    """
    lines = [title, f"N = {n}"]
    if x_range is not None:
        lines.append(f"{x_symbol}: {x_range[0]:.3f}–{x_range[1]:.3f} {x_unit}".rstrip())
    if y_range is not None:
        lines.append(f"{y_symbol}: {y_range[0]:.3f}–{y_range[1]:.3f} {y_unit}".rstrip())

    if result.valid and result.slope is not None and result.intercept is not None:
        unit_suffix = f" {fit_unit}" if fit_unit else ""
        lines.append(f"{y_symbol} = {result.slope:.3f} {x_symbol} {_format_signed(result.intercept)}")
        lines.append(f"{fit_result_prefix} = {result.slope:.3f}{unit_suffix}")
        r2_text = f"{result.r_squared:.3f}" if result.r_squared is not None else "—"
        lines.append(f"R² = {r2_text}")

    return "\n".join(lines)


def format_region_analysis_summary(
    title: str,
    summary: RegionAnalysisSummary,
    x_symbol: str | None,
    y_symbol: str | None,
    fit_result_prefix: str,
    fit_unit: str | None,
) -> str:
    """Phase 34 §10 — region таңдалған кездегі жай мәтіндік қорытынды.
    Спецификация талабы бойынша (§10: "clearly indicate that the result
    refers to the selected interval") бірінші жол "Таңдалған аралық"
    деп нақты белгіленеді.
    """
    lines = [title, "Таңдалған аралық"]
    lines.append(
        f"t₁ = {summary.t1:.3f} s   t₂ = {summary.t2:.3f} s   Δt = {summary.t2 - summary.t1:.3f} s"
    )
    for channel in summary.channels:
        if channel.n == 0:
            continue
        lines.append(
            f"{channel.display_name} (N={channel.n}): "
            f"{channel.minimum:.3f}–{channel.maximum:.3f} {channel.unit}   "
            f"AVG {channel.average:.3f} {channel.unit}".rstrip()
        )

    if summary.regression_slope is not None and summary.regression_intercept is not None:
        x_sym = x_symbol or "x"
        y_sym = y_symbol or "y"
        unit_suffix = f" {fit_unit}" if fit_unit else ""
        lines.append(
            f"{y_sym} = {summary.regression_slope:.3f} {x_sym} "
            f"{_format_signed(summary.regression_intercept)}"
        )
        lines.append(f"{fit_result_prefix} = {summary.regression_slope:.3f}{unit_suffix}")
        r2_text = (
            f"{summary.regression_r_squared:.3f}" if summary.regression_r_squared is not None else "—"
        )
        lines.append(f"R² = {r2_text}")

    return "\n".join(lines)
