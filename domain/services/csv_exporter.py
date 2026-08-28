"""csv_exporter — ExperimentSession ішіндегі Measurement тарихын CSV
файлына экспорттайтын domain сервисі.

Экспорттың жалғыз дереккөзі — ``ExperimentSession.measurements``. Бұл
сервис ``MeasurementTableWidget``-пен немесе ``LiveGraphWidget``-пен
ешбір байланысы жоқ (UI бұл екеуінен деректі оқымайды).
"""

import csv

from pathlib import Path

from domain.entities.experiment_session import ExperimentSession
from domain.interfaces.i_exporter import IExporter
from domain.services.export_io import write_export

_HEADER = ("No", "Time(s)", "Voltage(V)", "Current(A)", "Power(W)")
_TIME_DECIMALS = 2

# (Measurement ішіндегі кілт, ондық саны) — Voltage/Current/Power ретімен.
_VALUE_COLUMNS: tuple[tuple[str, int], ...] = (
    ("voltage", 3),
    ("current", 3),
    ("power", 3),
)


class CSVExporter(IExporter):
    """``ExperimentSession``-ды стандартты, Excel аша алатын CSV
    файлына жазатын сервис.
    """

    def export(self, session: ExperimentSession, output_path: str | Path) -> bool:
        """``session.measurements``-ті ``output_path`` файлына CSV
        түрінде жазады.

        Session бос болса, файл жасалмайды және ``False`` қайтарылады.
        Жазу қатесі (жол жоқ, рұқсат жоқ) ``ExportError`` ретінде шығады.
        """
        if not session.measurements:
            return False

        def _write() -> None:
            with open(output_path, mode="w", encoding="utf-8", newline="") as csv_file:
                writer = csv.writer(csv_file)
                writer.writerow(_HEADER)

                start_time = session.measurements[0].timestamp
                for index, measurement in enumerate(session.measurements, start=1):
                    elapsed = measurement.get_value("time")
                    if elapsed is None:
                        elapsed = (measurement.timestamp - start_time).total_seconds()

                    row = [str(index), f"{elapsed:.{_TIME_DECIMALS}f}"]
                    for key, decimals in _VALUE_COLUMNS:
                        value = measurement.get_value(key)
                        row.append("" if value is None else f"{value:.{decimals}f}")

                    writer.writerow(row)

        return write_export(output_path, _write)
