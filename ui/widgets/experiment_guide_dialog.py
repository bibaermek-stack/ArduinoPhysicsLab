"""ExperimentGuideDialog — таңдалған зертхана жұмысының толық
нұсқаулығын (мақсаты, жабдық, теория, формулалар, орындау тәртібі,
қауіпсіздік, бақылау сұрақтары) көрсететін диалог (Phase 35).

Бұл диалог ЕШБІР физикалық есептеу/дерек жасамайды және
``LiveGraphWidget``/``MeasurementWorkspace``/coordinator-ге ЕШБІР
сілтемесі жоқ — тек ``ExperimentDefinition.guide`` (``ExperimentGuide``)
мазмұнын оқиды. Дәл осы бөліну арқасында диалогты ашу/жабу
өлшеу/график/A-B cursor/region/zoom-pan күйіне ЕШҚАШАН тимейді (§15) —
қорғаныс коды емес, архитектуралық кепілдік.

``.show()`` арқылы (ЕШҚАШАН ``.exec()`` ЕМЕС) көрсетіледі — модальды
event loop ЖОҚ, сондықтан астыңғы терезенің таймерлері/serial
сигналдары бөгелместен жұмыс істей береді (өлшеу жалғаса береді).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from domain.entities.experiment_definition import ExperimentGuide

_SUBTITLE_TEXT = "Зертханалық жұмысқа нұсқаулық"
_CLOSE_BUTTON_TEXT = "Жабу"
_DEFAULT_SIZE = (760, 820)

_SECTION_TITLE_OBJECTIVE = "Жұмыстың мақсаты"
_SECTION_TITLE_EQUIPMENT = "Қажетті құрал-жабдықтар"
_SECTION_TITLE_THEORY = "Теориялық мәлімет"
_SECTION_TITLE_FORMULAS = "Негізгі формулалар"
_SECTION_TITLE_PROCEDURE = "Жұмысты орындау тәртібі"
_SECTION_TITLE_SAFETY = "Қауіпсіздік ережелері"
_SECTION_TITLE_CONTROL_QUESTIONS = "Бақылау сұрақтары"


class ExperimentGuideDialog(QDialog):
    """Бір ``ExperimentGuide``-ге арналған, скролленетін диалог терезесі.

    Тек НАҚТЫ мазмұны бар секциялар ғана салынады (§6) — бос
    ``tuple()``/``""`` секциясы ЕШҚАШАН бос карточка ретінде
    көрсетілмейді.
    """

    def __init__(
        self, experiment_title: str, guide: ExperimentGuide, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Нұсқаулық — {experiment_title}")
        self.resize(*_DEFAULT_SIZE)

        title_label = QLabel(experiment_title, self)
        title_font = title_label.font()
        title_font.setBold(True)
        title_font.setPointSize(title_font.pointSize() + 4)
        title_label.setFont(title_font)

        subtitle_label = QLabel(_SUBTITLE_TEXT, self)
        subtitle_label.setProperty("role", "secondary")

        header_layout = QVBoxLayout()
        header_layout.addWidget(title_label)
        header_layout.addWidget(subtitle_label)

        self._sections_layout = QVBoxLayout()
        self._sections_layout.addStretch(1)
        self._populate_sections(guide)

        content_widget = QWidget(self)
        content_widget.setLayout(self._sections_layout)

        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setWidget(content_widget)

        self._close_button = QPushButton(_CLOSE_BUTTON_TEXT, self)
        self._close_button.clicked.connect(self.close)

        footer_layout = QHBoxLayout()
        footer_layout.addStretch(1)
        footer_layout.addWidget(self._close_button)

        layout = QVBoxLayout(self)
        layout.addLayout(header_layout)
        layout.addWidget(scroll_area, 1)
        layout.addLayout(footer_layout)

    # ---- Ішкі логика -----------------------------------------------------

    def _populate_sections(self, guide: ExperimentGuide) -> None:
        insert_index = self._sections_layout.count() - 1  # addStretch(1)-ден бұрын

        def add_section(section: QFrame | None) -> None:
            nonlocal insert_index
            if section is None:
                return
            self._sections_layout.insertWidget(insert_index, section)
            insert_index += 1

        add_section(self._build_bullet_section(_SECTION_TITLE_OBJECTIVE, guide.objective))
        add_section(self._build_bullet_section(_SECTION_TITLE_EQUIPMENT, guide.equipment))
        add_section(self._build_text_section(_SECTION_TITLE_THEORY, guide.theory))
        add_section(self._build_formula_section(_SECTION_TITLE_FORMULAS, guide.formulas))
        add_section(self._build_numbered_section(_SECTION_TITLE_PROCEDURE, guide.procedure))
        add_section(self._build_bullet_section(_SECTION_TITLE_SAFETY, guide.safety))
        add_section(
            self._build_numbered_section(_SECTION_TITLE_CONTROL_QUESTIONS, guide.control_questions)
        )

    def _build_section_frame(self, title: str) -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame(self)
        frame.setObjectName("GuideSection")
        frame.setFrameShape(QFrame.Shape.StyledPanel)

        title_label = QLabel(title, frame)
        title_label.setProperty("role", "sectionTitle")

        layout = QVBoxLayout(frame)
        layout.addWidget(title_label)
        return frame, layout

    def _build_text_section(self, title: str, text: str) -> QFrame | None:
        if not text:
            return None
        frame, layout = self._build_section_frame(title)
        body_label = QLabel(text, frame)
        body_label.setWordWrap(True)
        layout.addWidget(body_label)
        return frame

    def _build_bullet_section(self, title: str, items: tuple[str, ...]) -> QFrame | None:
        if not items:
            return None
        frame, layout = self._build_section_frame(title)
        for item in items:
            item_label = QLabel(f"•  {item}", frame)
            item_label.setWordWrap(True)
            layout.addWidget(item_label)
        return frame

    def _build_numbered_section(self, title: str, items: tuple[str, ...]) -> QFrame | None:
        if not items:
            return None
        frame, layout = self._build_section_frame(title)
        for index, item in enumerate(items):
            item_label = QLabel(f"{index + 1}. {item}", frame)
            item_label.setWordWrap(True)
            layout.addWidget(item_label)
        return frame

    def _build_formula_section(self, title: str, formulas: tuple[str, ...]) -> QFrame | None:
        if not formulas:
            return None
        frame, layout = self._build_section_frame(title)
        for formula in formulas:
            formula_label = QLabel(formula, frame)
            formula_label.setProperty("role", "formula")
            formula_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
            layout.addWidget(formula_label)
        return frame
