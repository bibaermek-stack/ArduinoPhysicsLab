"""exporter_factory — таңдалған форматқа сай IExporter данасын қайтарады."""

from core.exceptions import ExportError
from domain.interfaces.i_exporter import IExporter
from domain.services.csv_exporter import CSVExporter
from domain.services.excel_exporter import ExcelExporter
from domain.services.pdf_exporter import PDFExporter

_EXPORTERS: dict[str, type[IExporter]] = {
    "csv": CSVExporter,
    "excel": ExcelExporter,
    "xlsx": ExcelExporter,
    "pdf": PDFExporter,
}


def create_exporter(format_name: str) -> IExporter:
    """``csv`` / ``excel``|``xlsx`` / ``pdf`` үшін нақты экспорт сервисін қайтарады."""
    key = str(format_name).strip().lower().lstrip(".")
    exporter_cls = _EXPORTERS.get(key)
    if exporter_cls is None:
        raise ExportError(f"Белгісіз экспорт форматы: {format_name}")
    return exporter_cls()
