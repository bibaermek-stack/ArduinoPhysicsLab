"""MeasurementSummaryCard — өлшеу тоқтатылғаннан кейін көрсетілетін
қысқа қорытынды карточкасы (Phase 38A).

Бұл виджет ЕШБІР жаңа статистика есептемейді — тек шақырушы
(``ExperimentWorkspacePage``) ``domain.services.experiment_report_data.
build_experiment_report_data()`` (Phase 36, бұрыннан бар, тәуелсіз
тестелген) арқылы дайын есептеп берген ``ChannelReportStatistics``-ті
көрсетеді. "Есепті ашу" батырмасы ЖАҢА есеп терезесін жасамайды — тек
сигнал шығарады, нақты ашу ``ExperimentWorkspacePage``-тің бұрыннан бар
``_on_report_button_clicked()``-іне қайта бағытталады.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from domain.services.experiment_report_data import ChannelReportStatistics

_TITLE_TEXT = "Өлшеу аяқталды"
_NO_VALUE_TEXT = "—"
_OPEN_REPORT_BUTTON_TEXT = "Есепті ашу"
_REMEASURE_BUTTON_TEXT = "Қайта өлшеу"
_START_FEEDBACK_BUTTON_TEXT = "Кері байланысты бастау"


class MeasurementSummaryCard(QFrame):
    """Өлшеу тоқтатылған сәттегі N/орташа/min/max мәнін көрсететін,
    "Есепті ашу"/"Қайта өлшеу" батырмалары бар карточка. Әдепкі бойынша
    жасырын.
    """

    open_report_requested = Signal()
    remeasure_requested = Signal()
    feedback_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("GuideSection")
        self.setFrameShape(QFrame.Shape.StyledPanel)

        self._title_label = QLabel(_TITLE_TEXT, self)
        self._title_label.setProperty("role", "sectionTitle")

        self._count_label = QLabel(self)
        self._average_label = QLabel(self)
        self._minimum_label = QLabel(self)
        self._maximum_label = QLabel(self)

        self._open_report_button = QPushButton(_OPEN_REPORT_BUTTON_TEXT, self)
        self._open_report_button.setObjectName("PrimaryButton")
        self._open_report_button.clicked.connect(self.open_report_requested)

        self._remeasure_button = QPushButton(_REMEASURE_BUTTON_TEXT, self)
        self._remeasure_button.clicked.connect(self.remeasure_requested)

        # Phase 39A: тек assessment конфигурацияланған тәжірибелерде
        # көрінеді (Guide/Diagram/Report батырмаларымен БІРДЕЙ "is not
        # None" gating), және есеп КЕМІНДЕ бір рет ашылғанша өшірулі
        # тұрады (§ "The button must be disabled... until... the report
        # has been opened").
        self._start_feedback_button = QPushButton(_START_FEEDBACK_BUTTON_TEXT, self)
        self._start_feedback_button.clicked.connect(self.feedback_requested)
        self._start_feedback_button.setEnabled(False)
        self._start_feedback_button.setVisible(False)

        button_row = QHBoxLayout()
        button_row.addWidget(self._open_report_button)
        button_row.addWidget(self._remeasure_button)
        button_row.addWidget(self._start_feedback_button)
        button_row.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addWidget(self._title_label)
        layout.addWidget(self._count_label)
        layout.addWidget(self._average_label)
        layout.addWidget(self._minimum_label)
        layout.addWidget(self._maximum_label)
        layout.addLayout(button_row)

        self.setVisible(False)

    def show_summary(self, stats: ChannelReportStatistics) -> None:
        """Берілген (алдын ала есептелген) статистиканы көрсетіп,
        карточканы көрінетін етеді.
        """
        self._count_label.setText(f"Өлшеу саны: {stats.n}")
        self._average_label.setText(
            f"Орташа мән: {self._format_value(stats.average, stats.unit, stats.decimals)}"
        )
        self._minimum_label.setText(
            f"Минимум: {self._format_value(stats.minimum, stats.unit, stats.decimals)}"
        )
        self._maximum_label.setText(
            f"Максимум: {self._format_value(stats.maximum, stats.unit, stats.decimals)}"
        )
        self.setVisible(True)

    def hide_summary(self) -> None:
        self.setVisible(False)

    def set_feedback_available(self, available: bool) -> None:
        """Тек ``experiment.assessment is not None`` болғанда
        шақырылады — assessment конфигурацияланбаған тәжірибеде батырма
        мүлде көрінбейді (Guide/Diagram/Report батырмаларымен БІРДЕЙ
        конвенция).
        """
        self._start_feedback_button.setVisible(available)

    def set_feedback_button_enabled(self, enabled: bool) -> None:
        """Кемінде 1 өлшеу БАР және есеп кемінде бір рет ашылғаннан
        кейін ғана ``True`` етіп шақырылады — жалған "аяқталу" ешқашан
        көрсетілмейді.
        """
        self._start_feedback_button.setEnabled(enabled)

    @staticmethod
    def _format_value(value: float | None, unit: str, decimals: int) -> str:
        if value is None:
            return _NO_VALUE_TEXT
        return f"{value:.{decimals}f} {unit}".rstrip()
