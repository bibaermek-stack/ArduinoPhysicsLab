"""GraphAnalysisPanel — таңдалған аралық үшін ғылыми статистика/регрессия/
туынды талдау көрсететін компакт панель (Phase 33B).

Бұл виджет ЕШБІР статистика/регрессия/интеграл есептемейді — тек
``domain.services.graph_analysis``-тан келген дайын нәтижелерді (``RegionStatistics``/
``RegressionResult``/float) көрсетеді. Каналдар/бірліктер ЕШҚАШАН
hardcoded емес — тек ``set_channel_statistics()``-ке берілген
``SensorChannel`` metadata-сынан құрылады, сондықтан кез келген
болашақ (Жылу/Магнетизм/Оптика) тәжірибесінде де өзгеріссіз қайта
пайдаланылады.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from domain.entities.sensor_channel import SensorChannel
from domain.services.graph_analysis import RegionStatistics, RegressionResult

_TITLE_TEXT = "Таңдалған аралық"
_REGRESSION_TITLE_TEXT = "Регрессия"
_ALL_POINTS_LABEL = "Барлық нүктелер"
_REGION_ONLY_LABEL = "Таңдалған аралық"
_NO_VALUE_TEXT = "—"
_STABILITY_LABEL = "Тұрақтылық"
# Phase 34 §4: SEM (стандартты қате) — калибрлеу/аспаптық қателіктен
# МҮЛДЕ бөлек статистикалық шама екенін нақты көрсету үшін тұрақты
# ескерту мәтіні (per-line емес, секцияның астында БІР рет).
_SEM_CAPTION_TEXT = (
    "SEM — тек статистикалық стандартты қате (осы N үлгінің орташа "
    "мәнін бағалау сенімділігі). Бұл аспап/калибрлеу қателігі ЕМЕС."
)


class GraphAnalysisPanel(QFrame):
    """Аралық статистика/регрессия/туынды талдау панелі — graph_card-тың
    ішінде, тек region-режимі қосулы кезде көрінеді (§5).
    """

    # Пайдаланушы "Барлық нүктелер"/"Таңдалған аралық" ауыстырғанда
    # (тек show_fit=True графиктерде мағыналы) — LiveGraphWidget осыған
    # жазылып, fit-ті сәйкес деректер жиынымен қайта есептейді.
    regression_scope_changed = Signal(bool)  # True = тек таңдалған аралық
    # §16: аралық талдау қорытындысын (raw Measurement экспортынан
    # МҮЛДЕ бөлек, қосымша) сақтау сұрауы.
    export_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("GraphAnalysisPanel")
        self.setFrameShape(QFrame.Shape.StyledPanel)

        title_label = QLabel(_TITLE_TEXT, self)
        title_font = title_label.font()
        title_font.setBold(True)
        title_label.setFont(title_font)

        self._region_summary_label = QLabel(self)
        self._region_summary_label.setWordWrap(True)

        self._export_button = QPushButton("📤", self)
        self._export_button.setToolTip("Талдау қорытындысын сақтау (CSV)")
        self._export_button.clicked.connect(self.export_requested)

        header_row = QHBoxLayout()
        header_row.addWidget(title_label)
        header_row.addSpacing(12)
        header_row.addWidget(self._region_summary_label, 1)
        header_row.addWidget(self._export_button)

        self._channels_layout = QVBoxLayout()
        self._channel_rows: dict[str, QLabel] = {}

        # Phase 34 §4: SEM түсіндірме жазуы — тек кем дегенде бір арнада
        # SEM көрсетілгенде ғана көрінеді (channel_rows жаңарған сайын
        # қайта есептеледі, _update_sem_caption_visibility()).
        self._sem_caption_label = QLabel(_SEM_CAPTION_TEXT, self)
        self._sem_caption_label.setWordWrap(True)
        self._sem_caption_label.setProperty("role", "secondary")
        self._sem_caption_label.setVisible(False)

        # Phase 34 §3/§6: rate-of-change (dY/dt) секциясы — тек
        # ExperimentDefinition.graph_rate_of_change конфигурацияланған
        # тәжірибелерде, region таңдалғанда ғана көрінеді.
        self._rate_of_change_layout = QVBoxLayout()
        self._rate_of_change_rows: dict[str, QLabel] = {}

        self._regression_title_label = QLabel(_REGRESSION_TITLE_TEXT, self)
        regression_title_font = self._regression_title_label.font()
        regression_title_font.setBold(True)
        self._regression_title_label.setFont(regression_title_font)

        self._all_points_radio = QRadioButton(_ALL_POINTS_LABEL, self)
        self._region_only_radio = QRadioButton(_REGION_ONLY_LABEL, self)
        self._all_points_radio.setChecked(True)
        self._regression_scope_group = QButtonGroup(self)
        self._regression_scope_group.setExclusive(True)
        self._regression_scope_group.addButton(self._all_points_radio)
        self._regression_scope_group.addButton(self._region_only_radio)
        self._all_points_radio.toggled.connect(self._on_scope_toggled)

        scope_row = QHBoxLayout()
        scope_row.addWidget(self._regression_title_label)
        scope_row.addSpacing(12)
        scope_row.addWidget(self._all_points_radio)
        scope_row.addWidget(self._region_only_radio)
        scope_row.addStretch(1)

        self._regression_equation_label = QLabel(self)
        self._regression_result_label = QLabel(self)

        self._regression_section = QWidget(self)
        regression_section_layout = QVBoxLayout(self._regression_section)
        regression_section_layout.setContentsMargins(0, 4, 0, 0)
        regression_section_layout.addLayout(scope_row)
        regression_section_layout.addWidget(self._regression_equation_label)
        regression_section_layout.addWidget(self._regression_result_label)
        self._regression_section.setVisible(False)

        self._derived_title_label = QLabel("Қуат / Жұмыс", self)
        derived_title_font = self._derived_title_label.font()
        derived_title_font.setBold(True)
        self._derived_title_label.setFont(derived_title_font)
        self._derived_value_label = QLabel(self)
        self._derived_section = QWidget(self)
        derived_section_layout = QVBoxLayout(self._derived_section)
        derived_section_layout.setContentsMargins(0, 4, 0, 0)
        derived_section_layout.addWidget(self._derived_title_label)
        derived_section_layout.addWidget(self._derived_value_label)
        self._derived_section.setVisible(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)
        layout.addLayout(header_row)
        layout.addLayout(self._channels_layout)
        layout.addWidget(self._sem_caption_label)
        layout.addLayout(self._rate_of_change_layout)
        layout.addWidget(self._regression_section)
        layout.addWidget(self._derived_section)

    # ---- Public API -----------------------------------------------------

    def set_region_summary(self, t1: float, t2: float, n_label: str, decimals: int = 2) -> None:
        """Аралық басы/соңы/ұзақтығын көрсетеді. ``n_label`` шақырушыда
        дайындалады (мыс. "N = 126") — бірнеше арнада N әртүрлі болуы
        мүмкін болғандықтан, бұл жалпы емес, канал жолдарында да
        қайталанады.
        """
        delta = t2 - t1
        self._region_summary_label.setText(
            f"t₁ = {t1:.{decimals}f} s      t₂ = {t2:.{decimals}f} s      "
            f"Δt = {delta:.{decimals}f} s      {n_label}"
        )

    def set_channel_statistics(self, channel: SensorChannel, stats: RegionStatistics) -> None:
        """Бір арнаның статистика жолын қосады/жаңартады. Бос статистика
        (``n=0``) үшін "—" көрсетеді (жалған 0.000 мән ЕШҚАШАН
        көрсетілмейді).
        """
        if channel.key not in self._channel_rows:
            row_label = QLabel(self)
            row_label.setWordWrap(True)
            self._channel_rows[channel.key] = row_label
            self._channels_layout.addWidget(row_label)

        label = self._channel_rows[channel.key]
        label.setText(self._format_channel_line(channel, stats))
        self._update_sem_caption_visibility(stats)

    def _format_channel_line(self, channel: SensorChannel, stats: RegionStatistics) -> str:
        decimals = channel.decimals
        unit = channel.unit
        if stats.n == 0:
            return f"{channel.display_name}: {_NO_VALUE_TEXT}"

        cv = stats.coefficient_of_variation_percent
        cv_text = f"{cv:.1f} %" if cv is not None else _NO_VALUE_TEXT
        sem = stats.standard_error_of_mean
        sem_segment = f"   AVG ± SEM {stats.average:.{decimals}f} ± {sem:.{decimals}f} {unit}" if sem is not None else ""
        return (
            f"{channel.display_name} (N={stats.n})   "
            f"MIN {stats.minimum:.{decimals}f} {unit}   "
            f"MAX {stats.maximum:.{decimals}f} {unit}   "
            f"AVG {stats.average:.{decimals}f} {unit}   "
            f"Δ {stats.delta:.{decimals}f} {unit}   "
            f"σ {stats.std_dev:.{decimals}f} {unit}   "
            f"{_STABILITY_LABEL}: CV {cv_text}"
            f"{sem_segment}"
        ).rstrip()

    def _update_sem_caption_visibility(self, stats: RegionStatistics) -> None:
        if stats.standard_error_of_mean is not None:
            self._sem_caption_label.setVisible(True)

    def clear_channel_statistics(self) -> None:
        while self._channels_layout.count():
            item = self._channels_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._channel_rows = {}
        self._sem_caption_label.setVisible(False)

    def set_regression_available(self, available: bool) -> None:
        """Ohm's Law секілді fit-ті қолдайтын графиктерде ғана
        регрессия секциясы көрінеді (§5: тек мағыналы графиктерде).
        """
        self._regression_section.setVisible(available)

    def is_region_only_regression(self) -> bool:
        return self._region_only_radio.isChecked()

    def set_regression_result(
        self,
        result: RegressionResult,
        x_symbol: str,
        y_symbol: str,
        result_prefix: str,
        unit: str | None,
    ) -> None:
        if not result.valid:
            self._regression_equation_label.setText(_NO_VALUE_TEXT)
            self._regression_result_label.setText("Кемінде 2 нүкте қажет")
            return

        unit_suffix = f" {unit}" if unit else ""
        self._regression_equation_label.setText(
            f"{y_symbol} = {result.slope:.3f}·{x_symbol} + {result.intercept:.3f}"
        )
        r_squared_text = f"{result.r_squared:.3f}" if result.r_squared is not None else _NO_VALUE_TEXT
        rmse_unit = f" {unit_suffix.strip()}" if unit else ""
        self._regression_result_label.setText(
            f"{result_prefix} = {result.slope:.3f}{unit_suffix}   "
            f"R² = {r_squared_text}   "
            f"RMSE = {result.rmse:.4f}{rmse_unit}   "
            f"N = {result.n}"
        )

    def set_derived_power_energy(
        self, p_avg: float | None, p_max: float | None, work: float | None
    ) -> None:
        """§11: Ток жұмысы мен қуаты тәжірибесіне арналған туынды
        мәндер. ``None`` мән — жеткіліксіз дерек (fake 0.000 ЕМЕС).
        """
        self._derived_section.setVisible(True)
        p_avg_text = f"{p_avg:.3f} W" if p_avg is not None else _NO_VALUE_TEXT
        p_max_text = f"{p_max:.3f} W" if p_max is not None else _NO_VALUE_TEXT
        work_text = f"{work:.3f} J" if work is not None else _NO_VALUE_TEXT
        self._derived_value_label.setText(
            f"P_орта = {p_avg_text}      P_макс = {p_max_text}      Жұмыс = {work_text}"
        )

    def hide_derived_section(self) -> None:
        self._derived_section.setVisible(False)

    def set_rate_of_change(self, symbol: str, display_name: str, unit: str, result: RegressionResult) -> None:
        """Phase 34 §3/§6: уақыттық арнаның таңдалған аралықтағы физикалық
        rate-of-change мәнін (dY/dt) көрсетеді — сызықтық регрессияның
        slope-ынан (толық ағынды нүкте-нүктелеп дифференциалдамай).
        ``result.valid=False`` болса (жеткіліксіз/деградацияланған
        дерек), жол "—" болып қалады (жалған 0.0 ЕШҚАШАН көрсетілмейді).
        """
        if symbol not in self._rate_of_change_rows:
            row_label = QLabel(self)
            row_label.setWordWrap(True)
            self._rate_of_change_rows[symbol] = row_label
            self._rate_of_change_layout.addWidget(row_label)

        label = self._rate_of_change_rows[symbol]
        if not result.valid or result.slope is None:
            label.setText(f"{display_name} ({symbol}): {_NO_VALUE_TEXT}")
            return
        label.setText(f"{display_name} ({symbol}) = {result.slope:.3f} {unit}")

    def clear_rate_of_change(self) -> None:
        while self._rate_of_change_layout.count():
            item = self._rate_of_change_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._rate_of_change_rows = {}

    def clear(self) -> None:
        self._region_summary_label.setText("")
        self.clear_channel_statistics()
        self.clear_rate_of_change()
        self._regression_section.setVisible(False)
        self._derived_section.setVisible(False)

    # ---- Ішкі логика -----------------------------------------------------

    def _on_scope_toggled(self, _checked: bool) -> None:
        self.regression_scope_changed.emit(self._region_only_radio.isChecked())
