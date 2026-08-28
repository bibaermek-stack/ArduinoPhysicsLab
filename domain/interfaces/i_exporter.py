"""IExporter — ExperimentSession-ды файлға жазу стратегиясының интерфейсі.

Нақты іске асырулар:
``domain.services.csv_exporter.CSVExporter``,
``domain.services.excel_exporter.ExcelExporter``,
``domain.services.pdf_exporter.PDFExporter``.
Таңдау — ``infrastructure.export.exporter_factory.create_exporter``.
"""

from abc import ABC, abstractmethod
from pathlib import Path

from domain.entities.experiment_session import ExperimentSession


class IExporter(ABC):
    """Бір ``ExperimentSession``-ды көрсетілген жолға жазатын экспорт стратегиясы."""

    @abstractmethod
    def export(self, session: ExperimentSession, output_path: str | Path) -> bool:
        """Сессияны файлға жазады.

        Бос сессияда файл жасалмайды және ``False`` қайтарылады.
        Жазу қатесі (жол жоқ, рұқсат жоқ, диск толы) ``ExportError``
        ретінде шығады — UI пайдаланушыға себебін көрсетеді.
        """
        raise NotImplementedError
