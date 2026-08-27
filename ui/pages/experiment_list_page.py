"""ExperimentListPage — таңдалған модульдің зертхана жұмыстарының тізімін,
немесе (module берілмесе) БАРЛЫҚ тіркелген модульдің толық каталогын
секция тақырыптарымен көрсететін бет.

Екі режим бір кодта: ``on_enter(module=...)`` ЕСКІ single-module мінез-
құлқын өзгеріссіз сақтайды (HomePage-тен келетін барлық шақыру осылай);
``on_enter()`` (параметрсіз, sidebar-дың "Зертханалық жұмыстар" пунктінен)
``module_registry``-дегі БАРЛЫҚ модульді секция тақырыптарымен тізеді.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from domain.entities.experiment_definition import ExperimentDefinition
from domain.interfaces.i_physics_module import IPhysicsModule
from modules.module_registry import ModuleRegistry

_EMPTY_STATE_TEXT = "Бұл модульде зертхана жұмысы жоқ"
_CATALOG_TITLE_TEXT = "Зертханалық жұмыстар"
_PLANNED_BADGE_TEXT = "Жоспарланған"
_LABS_CARD_MIN_WIDTH = 220

# Секция атауы -> QSS accent кілті ("theme_manager.py"-дегі
# QFrame#LabsSectionHeader[sectionAccent=...] селекторымен сәйкес).
# home_page.py-дегі _SECTION_ACCENT_BY_NAME-мен бірдей мағына, бірақ
# бөлек презентациялық қажеттілік (сол дублирование конвенциясы
# _SENSOR_TYPE_NAMES_KK-де device_card.py/device_panel.py арасында
# бұрыннан бар).
_SECTION_ACCENT_BY_NAME: dict[str, str] = {
    "Жылу құбылыстары": "heat",
    "Электр құбылыстары": "electricity",
    "Электромагниттік құбылыстар": "electromagnetism",
    "Жарық құбылыстары": "light",
}


class _LabsExperimentRow(QFrame):
    """Labs каталог картасындағы бір тәжірибе жолы.

    ``QPushButton`` орнына ЖАСАЛДЫ — Qt-тың ``QPushButton``-ы ұзын
    атауларды (мыс. "Металдардың меншікті жылу сыйымдылығын анықтау")
    бір жолда кесіп тастайды (word-wrap қолдамайды), ал ықшам карточка
    бағанында бұл clipping-ке әкеледі. ``QLabel(wordWrap=True)`` көп
    жолды атауды дұрыс сыйдырады, ал басу оқиғасы ``DeviceCard``-та
    (``ui/widgets/device_card.py``) бұрыннан қолданылатын
    ``mousePressEvent`` паттернімен бірдей түрде ұсталады.
    """

    clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("LabsExperimentRow")

    def mousePressEvent(self, event: QMouseEvent) -> None:
        super().mousePressEvent(event)
        if self.isEnabled() and event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()


class ExperimentListPage(QWidget):
    """``on_enter(module=...)`` арқылы келген модульдің зертхана
    жұмыстарын, немесе ``on_enter()`` (module=None) арқылы БАРЛЫҚ
    тіркелген модульдің толық каталогын карточка түрінде көрсетіп,
    таңдалғанын ``experiment_selected`` сигналымен шығаратын бет.
    """

    experiment_selected = Signal(object)
    back_requested = Signal()

    def __init__(
        self,
        module_registry: ModuleRegistry | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._module_registry = module_registry or ModuleRegistry()
        self._module: IPhysicsModule | None = None
        self._showing_all = False

        self._back_button = QPushButton("← Модульдерге оралу", self)
        self._back_button.clicked.connect(self.back_requested)

        self._title_label = QLabel(self)
        title_font = self._title_label.font()
        title_font.setBold(True)
        title_font.setPointSize(title_font.pointSize() + 4)
        self._title_label.setFont(title_font)

        self._cards_layout = QVBoxLayout()

        layout = QVBoxLayout(self)
        layout.addWidget(self._back_button)
        layout.addWidget(self._title_label)
        layout.addLayout(self._cards_layout)
        layout.addStretch(1)

    def on_enter(self, module: IPhysicsModule | None = None) -> None:
        """``module`` берілсе, тек сол модульдің жұмыстарын көрсетеді
        (ескі мінез-құлық). Берілмесе, тіркелген БАРЛЫҚ модульдің толық
        каталогын секция тақырыптарымен көрсетеді.
        """
        self._module = module
        self._showing_all = module is None
        # "← Модульдерге оралу" тек single-module режимінде мағыналы (ол
        # HomePage-тен келеді). Толық Labs каталогында бұл батырма артық —
        # sidebar навигацияны толық қамтамасыз етеді, бөлек "модульге
        # оралу" тұжырымдамасы жоқ (setVisible(False) layout-та орын
        # қалдырмайды, қосымша spacer керек емес).
        self._back_button.setVisible(not self._showing_all)
        self._title_label.setText(module.get_name() if module is not None else _CATALOG_TITLE_TEXT)
        self._rebuild_cards()

    def _rebuild_cards(self) -> None:
        while self._cards_layout.count():
            item = self._cards_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        if self._showing_all:
            self._rebuild_all_sections()
            return

        experiments = self._module.get_experiments() if self._module is not None else ()
        if not experiments:
            self._cards_layout.addWidget(QLabel(_EMPTY_STATE_TEXT, self))
            return

        for experiment in experiments:
            self._cards_layout.addWidget(self._build_card(experiment))

    def _rebuild_all_sections(self) -> None:
        modules = self._module_registry.get_all()
        if not modules:
            self._cards_layout.addWidget(QLabel(_EMPTY_STATE_TEXT, self))
            return

        # QWidget контейнерге оралған (тек addLayout() емес) — сол арқылы
        # _rebuild_cards()-тегі ЕСКІ тазалау циклі (``item.widget()``)
        # келесі on_enter()-де бұл қатарды да дұрыс жояды (widget leak жоқ).
        row_container = QWidget(self)
        row_layout = QHBoxLayout(row_container)
        row_layout.setContentsMargins(0, 0, 0, 0)
        for module in modules:
            row_layout.addWidget(self._build_section_card(module), 1)
        self._cards_layout.addWidget(row_container)

    def _build_section_card(self, module: IPhysicsModule) -> QWidget:
        card = QFrame(self)
        card.setObjectName("LabsSectionCard")
        card.setMinimumWidth(_LABS_CARD_MIN_WIDTH)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        header = QFrame(card)
        header.setObjectName("LabsSectionHeader")
        accent = _SECTION_ACCENT_BY_NAME.get(module.get_name())
        if accent is not None:
            header.setProperty("sectionAccent", accent)

        icon_label = QLabel(module.get_icon() or "", header)
        icon_label.setObjectName("LabsSectionIcon")

        title_label = QLabel(module.get_name(), header)
        title_label.setObjectName("LabsSectionTitle")
        title_label.setWordWrap(True)

        header_layout = QVBoxLayout(header)
        header_layout.addWidget(icon_label)
        header_layout.addWidget(title_label)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)
        card_layout.addWidget(header)

        experiments = module.get_experiments()
        if not experiments:
            body_layout = QVBoxLayout()
            body_layout.addWidget(QLabel(_EMPTY_STATE_TEXT, card))
            card_layout.addLayout(body_layout)
        else:
            for experiment in experiments:
                card_layout.addWidget(self._build_labs_row(experiment, card))
        card_layout.addStretch(1)

        return card

    def _build_labs_row(self, experiment: ExperimentDefinition, parent: QWidget) -> QWidget:
        row = _LabsExperimentRow(parent)
        row.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        row.setEnabled(experiment.is_implemented)
        row.setCursor(
            Qt.CursorShape.PointingHandCursor
            if experiment.is_implemented
            else Qt.CursorShape.ArrowCursor
        )

        text = (
            f"{experiment.display_number}. {experiment.title}"
            if experiment.display_number is not None
            else experiment.title
        )
        title_label = QLabel(text, row)
        title_label.setObjectName("LabsExperimentRowLabel")
        title_label.setWordWrap(True)

        row_layout = QVBoxLayout(row)
        row_layout.addWidget(title_label)

        if not experiment.is_implemented:
            badge_label = QLabel(_PLANNED_BADGE_TEXT, row)
            badge_label.setObjectName("LabsPlannedBadge")
            row_layout.addWidget(badge_label)

        if experiment.is_implemented:
            row.clicked.connect(lambda e=experiment: self._on_card_selected(e))

        return row

    def _build_card(self, experiment: ExperimentDefinition) -> QWidget:
        card = QWidget(self)
        layout = QVBoxLayout(card)

        title_text = (
            f"{experiment.display_number}. {experiment.title}"
            if experiment.display_number is not None
            else experiment.title
        )
        title_label = QLabel(title_text, card)
        title_font = title_label.font()
        title_font.setBold(True)
        title_label.setFont(title_font)

        description_label = QLabel(experiment.description, card)
        description_label.setWordWrap(True)

        layout.addWidget(title_label)
        layout.addWidget(description_label)

        if experiment.is_implemented:
            select_button = QPushButton("Таңдау", card)
            select_button.clicked.connect(
                lambda _checked=False, e=experiment: self._on_card_selected(e)
            )
            layout.addWidget(select_button)
        else:
            planned_row = QPushButton("Таңдау", card)
            planned_row.setEnabled(False)
            badge_label = QLabel(_PLANNED_BADGE_TEXT, card)
            badge_label.setProperty("role", "secondary")
            layout.addWidget(planned_row)
            layout.addWidget(badge_label)

        return card

    def _on_card_selected(self, experiment: ExperimentDefinition) -> None:
        self.experiment_selected.emit(experiment)
