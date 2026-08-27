"""pdf_exporter — ExperimentSession ішіндегі Measurement тарихын
академиялық стильдегі PDF есебіне экспорттайтын domain сервисі.

Экспорттың жалғыз дереккөзі — ``ExperimentSession.measurements``. Бұл
сервис ``MeasurementTableWidget``-пен немесе ``LiveGraphWidget``-пен
ешбір байланысы жоқ (UI бұл екеуінен деректі оқымайды).
"""

import math
import os
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from domain.entities.experiment_session import ExperimentSession
from domain.entities.measurement import Measurement

_TITLE_TEXT = "Arduino Physics Lab"
_SUBTITLE_TEXT = "Өлшеу нәтижелері"
_INFO_HEADING = "Тәжірибе туралы ақпарат"
_STATS_HEADING = "Қысқаша статистика"
_TABLE_HEADING = "Өлшеулер кестесі"

_MEASUREMENT_HEADER = ("№", "Уақыт (сек)", "Кернеу (V)", "Ток (A)", "Қуат (W)")
_TIME_DECIMALS = 2
_NO_VALUE_TEXT = "—"

# (Measurement ішіндегі кілт, ондық саны) — Voltage/Current/Power ретімен.
_VALUE_COLUMNS: tuple[tuple[str, int], ...] = (
    ("voltage", 3),
    ("current", 3),
    ("power", 3),
)

# (Measurement ішіндегі кілт, статистика кестесіндегі атауы, ондық саны)
_STATS_CHANNELS: tuple[tuple[str, str, int], ...] = (
    ("voltage", "Кернеу (V)", 3),
    ("current", "Ток (A)", 3),
    ("power", "Қуат (W)", 3),
)

# ---- Unicode қаріпті іздеу және тіркеу ------------------------------------
#
# Бірде-бір қаріп файлы жобаға көшірілмейді/commit етілмейді және нақты
# бір компьютерге тән абсолютті жол hardcode етілмейді — тек стандартты
# ОЖ орта айнымалылары (WINDIR, LOCALAPPDATA) және белгілі қаріп
# атаулары арқылы қолжетімді Unicode TTF қаріп ізделеді.

_FONT_NAME = "APLUnicodeFont"
_BOLD_FONT_NAME = "APLUnicodeFont-Bold"

_CANDIDATE_FONT_FILENAMES: tuple[str, ...] = (
    "arial.ttf",
    "Arial.ttf",
    "tahoma.ttf",
    "segoeui.ttf",
    "calibri.ttf",
    "DejaVuSans.ttf",
    "NotoSans-Regular.ttf",
)

# Табылған regular қаріптің сол қалтадағы bold нұсқасының болжамды атауы.
_BOLD_FONT_FILENAME_MAP: dict[str, str] = {
    "arial.ttf": "arialbd.ttf",
    "Arial.ttf": "Arialbd.ttf",
    "tahoma.ttf": "tahomabd.ttf",
    "segoeui.ttf": "segoeuib.ttf",
    "calibri.ttf": "calibrib.ttf",
    "DejaVuSans.ttf": "DejaVuSans-Bold.ttf",
    "NotoSans-Regular.ttf": "NotoSans-Bold.ttf",
}


def _candidate_font_directories() -> list[Path]:
    """Қаріп іздеуге арналған, ОЖ орта айнымалыларынан алынған қалталар."""
    directories: list[Path] = []

    windir = os.environ.get("WINDIR")
    if windir:
        directories.append(Path(windir) / "Fonts")

    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        directories.append(Path(local_appdata) / "Microsoft" / "Windows" / "Fonts")

    directories.extend(
        Path(p)
        for p in (
            "/usr/share/fonts/truetype/dejavu",
            "/usr/share/fonts/truetype/noto",
            "/usr/share/fonts/truetype/liberation",
            "/System/Library/Fonts/Supplemental",
        )
    )
    return directories


def _find_unicode_font() -> Path | None:
    """Жүйеде кирилл таңбаларын қолдайтын қолжетімді Unicode TTF
    қаріпті іздейді (Arial, DejaVu Sans, Noto Sans, т.б.). Табылмаса
    ``None`` қайтарады.
    """
    for directory in _candidate_font_directories():
        if not directory.is_dir():
            continue
        for filename in _CANDIDATE_FONT_FILENAMES:
            candidate = directory / filename
            if candidate.is_file():
                return candidate
    return None


def _register_bold_variant(regular_path: Path) -> str | None:
    """Табылған regular қаріптің bold нұсқасын тіркеуге тырысады.
    Табылмаса/тіркелмесе ``None`` қайтарады.
    """
    bold_filename = _BOLD_FONT_FILENAME_MAP.get(regular_path.name)
    if bold_filename is None:
        return None
    bold_path = regular_path.with_name(bold_filename)
    if not bold_path.is_file():
        return None
    try:
        if _BOLD_FONT_NAME not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(_BOLD_FONT_NAME, str(bold_path)))
        return _BOLD_FONT_NAME
    except Exception:
        return None


def _register_unicode_fonts() -> tuple[str, str] | None:
    """``(regular_font_name, bold_font_name)`` қайтарады. Bold нұсқасы
    табылмаса, bold атауы да regular-мен бірдей болады. Қаріп мүлдем
    табылмаса ``None`` қайтарады.
    """
    font_path = _find_unicode_font()
    if font_path is None:
        return None
    try:
        if _FONT_NAME not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(_FONT_NAME, str(font_path)))
    except Exception:
        return None

    bold_font_name = _register_bold_variant(font_path) or _FONT_NAME
    return _FONT_NAME, bold_font_name


class _NumberedCanvas(pdfcanvas.Canvas):
    """"N / Total" пішіміндегі footer-ды әр бетке салатын Canvas.

    Total бет саны алдын ала белгісіз болғандықтан, әр бет күйі алдымен
    жадыда сақталады, содан кейін ``save()`` кезінде барлық беттің
    жалпы санымен қайта салынады (reportlab-тың стандартты тәсілі).
    """

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self._saved_page_states: list[dict[str, object]] = []

    def showPage(self) -> None:
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        total_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_page_number(total_pages)
            super().showPage()
        super().save()

    def _draw_page_number(self, total_pages: int) -> None:
        text = f"{self._pageNumber} / {total_pages}"
        self.setFont("Helvetica", 9)
        self.drawCentredString(A4[0] / 2, 1.3 * cm, text)


class PDFExporter:
    """``ExperimentSession``-ды қарапайым академиялық стильдегі PDF
    есебіне жазатын сервис.
    """

    def export(self, session: ExperimentSession, output_path: str | Path) -> bool:
        """``session``-ды ``output_path`` файлына PDF есебі ретінде
        жазады.

        Session бос болса немесе жүйеде Unicode қаріп табылмаса, файл
        жасалмайды және ``False`` қайтарылады. Кез келген қате
        ұсталады, ешбір exception сыртқа шықпайды.
        """
        if not session.measurements:
            return False

        fonts = _register_unicode_fonts()
        if fonts is None:
            return False
        regular_font, bold_font = fonts

        try:
            path = Path(output_path)
            if path.suffix.lower() != ".pdf":
                path = path.with_suffix(".pdf")

            styles = self._build_styles(regular_font, bold_font)
            flowables = [
                Paragraph(_TITLE_TEXT, styles["title"]),
                Paragraph(_SUBTITLE_TEXT, styles["subtitle"]),
                Spacer(1, 0.6 * cm),
                Paragraph(_INFO_HEADING, styles["heading"]),
                self._build_info_table(session, regular_font, bold_font),
                Spacer(1, 0.6 * cm),
                Paragraph(_STATS_HEADING, styles["heading"]),
                self._build_statistics_table(session, regular_font, bold_font),
                Spacer(1, 0.6 * cm),
                Paragraph(_TABLE_HEADING, styles["heading"]),
                self._build_measurements_table(session, regular_font, bold_font),
            ]

            document = SimpleDocTemplate(
                str(path),
                pagesize=A4,
                topMargin=2 * cm,
                bottomMargin=2.2 * cm,
                leftMargin=2 * cm,
                rightMargin=2 * cm,
                title=_TITLE_TEXT,
            )
            document.build(flowables, canvasmaker=_NumberedCanvas)
            return True
        except Exception:  # қорғаныс: болжанбаған қате де сыртқа шықпайды
            return False

    # ---- Paragraph/Table құрастыру -------------------------------------

    @staticmethod
    def _build_styles(regular_font: str, bold_font: str) -> dict[str, ParagraphStyle]:
        return {
            "title": ParagraphStyle(
                "APLTitle", fontName=bold_font, fontSize=18, leading=22, spaceAfter=4
            ),
            "subtitle": ParagraphStyle(
                "APLSubtitle", fontName=regular_font, fontSize=13, leading=16, spaceAfter=10
            ),
            "heading": ParagraphStyle(
                "APLHeading",
                fontName=bold_font,
                fontSize=12,
                leading=15,
                spaceBefore=6,
                spaceAfter=6,
            ),
        }

    @staticmethod
    def _build_info_table(
        session: ExperimentSession, regular_font: str, bold_font: str
    ) -> Table:
        rows: list[tuple[str, str]] = [
            ("Experiment ID", session.experiment_id),
            ("Start time", session.started_at.isoformat(sep=" ", timespec="seconds")),
        ]
        if session.ended_at is not None:
            rows.append(
                ("End time", session.ended_at.isoformat(sep=" ", timespec="seconds"))
            )
        rows.append(("Duration (s)", f"{session.duration_seconds():.2f}"))
        rows.append(("Measurement count", str(session.measurement_count)))

        table = Table(rows, colWidths=[5 * cm, 9 * cm], hAlign="LEFT")
        table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), regular_font),
                    ("FONTNAME", (0, 0), (0, -1), bold_font),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        return table

    def _build_statistics_table(
        self, session: ExperimentSession, regular_font: str, bold_font: str
    ) -> Table:
        rows: list[list[str]] = [["Арна", "Min", "Max", "Орташа"]]
        for key, title, decimals in _STATS_CHANNELS:
            stats = self._compute_channel_statistics(session.measurements, key)
            if stats is None:
                rows.append([title, _NO_VALUE_TEXT, _NO_VALUE_TEXT, _NO_VALUE_TEXT])
            else:
                minimum, maximum, average = stats
                rows.append(
                    [
                        title,
                        f"{minimum:.{decimals}f}",
                        f"{maximum:.{decimals}f}",
                        f"{average:.{decimals}f}",
                    ]
                )

        table = Table(
            rows, colWidths=[4 * cm, 3.3 * cm, 3.3 * cm, 3.3 * cm], hAlign="LEFT"
        )
        table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), regular_font),
                    ("FONTNAME", (0, 0), (-1, 0), bold_font),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("ALIGN", (1, 0), (-1, -1), "CENTER"),
                    ("ALIGN", (0, 0), (0, -1), "LEFT"),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        return table

    @staticmethod
    def _compute_channel_statistics(
        measurements: list[Measurement], key: str
    ) -> tuple[float, float, float] | None:
        """Арнадағы тек ақырлы (finite) numeric мәндерден
        ``(min, max, average)`` есептейді. Жарамды мән болмаса ``None``.
        """
        values = [
            value
            for measurement in measurements
            if (value := measurement.get_value(key)) is not None and math.isfinite(value)
        ]
        if not values:
            return None
        return min(values), max(values), sum(values) / len(values)

    @staticmethod
    def _build_measurements_table(
        session: ExperimentSession, regular_font: str, bold_font: str
    ) -> Table:
        rows: list[list[str]] = [list(_MEASUREMENT_HEADER)]

        start_time = session.measurements[0].timestamp
        for index, measurement in enumerate(session.measurements, start=1):
            elapsed = measurement.get_value("time")
            if elapsed is None:
                elapsed = (measurement.timestamp - start_time).total_seconds()

            row = [str(index), f"{elapsed:.{_TIME_DECIMALS}f}"]
            for key, decimals in _VALUE_COLUMNS:
                value = measurement.get_value(key)
                row.append(_NO_VALUE_TEXT if value is None else f"{value:.{decimals}f}")
            rows.append(row)

        table = Table(
            rows,
            colWidths=[1.5 * cm, 3.3 * cm, 3.3 * cm, 3.3 * cm, 3.3 * cm],
            repeatRows=1,
            hAlign="LEFT",
        )
        table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), regular_font),
                    ("FONTNAME", (0, 0), (-1, 0), bold_font),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        return table
