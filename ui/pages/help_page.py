"""HelpPage — Arduino Physics Lab жүйесін пайдалану бойынша қысқаша
анықтама беті (Phase — Help/About).

Бұл бет ТЕК статикалық құжаттама — ешбір жаңа репозиторий/сервис/
дерекқор кестесі ЖОҚ (§ "keep the page lightweight"). Router route атауы
("about") және sidebar кілті ("help") ӨЗГЕРТІЛМЕЙДІ — тек ескі
placeholder-стильді ``AboutPage`` осы нақты, толық беттің класымен
ауыстырылады.
"""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from core.resource_paths import resource_path
from core.version import __version__
from ui.themes.theme_manager import COLOR_ACCENT, COLOR_ACCENT_TEXT, current_theme

# Design/02_FluentIcons/svg/ — ``ui/widgets/sidebar.py``/``ui/widgets/
# live_graph.py``-дегі SVG-тінттеу конвенциясының ЖЕКЕ көшірмесі (§ бұл
# бет графикпен/sidebar-мен ЕШБІР байланысы жоқ, жеке контекст).
_SECTION_ICON_DIR = resource_path("Design", "02_FluentIcons", "svg")
_SECTION_ICON_PX = 16
_SECTION_ICON_RENDER_PX = 64
_SECTION_ICON_FILL_DARK = b'fill="#212121"'


@lru_cache(maxsize=None)
def _load_section_icon(svg_filename: str, theme: str = "dark") -> QIcon:
    svg_bytes = (_SECTION_ICON_DIR / svg_filename).read_bytes()
    fill = b'fill="#212121"' if theme == "light" else b'fill="#DCE4EE"'
    svg_bytes = svg_bytes.replace(_SECTION_ICON_FILL_DARK, fill)
    renderer = QSvgRenderer(QByteArray(svg_bytes))
    pixmap = QPixmap(_SECTION_ICON_RENDER_PX, _SECTION_ICON_RENDER_PX)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(_SECTION_ICON_RENDER_PX / _SECTION_ICON_PX)
    icon = QIcon()
    icon.addPixmap(pixmap, QIcon.Mode.Normal, QIcon.State.Off)
    return icon

# § "chevron/arrow indicator on the right" — ``QPushButton.
# setLayoutDirection(RightToLeft)`` + ``text-align:left`` QSS комбинациясы
# арқылы қол жеткізілді (эмпирикалық тексерілді): мәтін СОЛ жақта,
# стандартты стиль strелкасы ОҢ жақта қалады, Кириллица мәтіні дұрыс
# LTR ретімен көрсетіледі (layoutDirection тек виджет chrome-ын
# ауыстырады, мәтін bidi-сін ЕМЕС).
_FAQ_HEADER_STYLE = "QPushButton { text-align: left; padding-right: 12px; }"

_FAQ_ITEMS: tuple[tuple[str, str], ...] = (
    (
        "Құрылғыны қалай қосуға болады?",
        "1. Сенсорды USB арқылы компьютерге қосыңыз.\n"
        "2. «Құрылғылар» бөліміне өтіңіз.\n"
        "3. «Жаңарту» батырмасын басыңыз.\n"
        "4. Қажетті COM портты таңдап, құрылғыны қосыңыз.",
    ),
    (
        "Зертханалық жұмысты қалай бастауға болады?",
        "1. «Зертханалық жұмыстар» бөліміне өтіңіз.\n"
        "2. Қажетті зертханалық жұмысты таңдаңыз.\n"
        "3. Қажетті сенсордың қосылғанын тексеріңіз.\n"
        "4. Жұмысты бастап, экрандағы нұсқаулықты орындаңыз.",
    ),
    (
        "Өлшеу нәтижелерін қайдан көруге болады?",
        "Зертханалық жұмыс барысында алынған өлшеулер «Деректер журналы» "
        "бөлімінде сақталады. Оқушы жұмысының қорытынды нәтижелерін "
        "«Нәтижелер» бөлімінен көруге болады.",
    ),
    (
        "Құрылғы анықталмаса не істеу керек?",
        "USB кабелінің дұрыс қосылғанын тексеріңіз. Содан кейін "
        "«Құрылғылар» бөліміне өтіп, «Жаңарту» батырмасын басыңыз. "
        "Қажетті COM порт пайда болмаса, құрылғыны қайта қосып көріңіз.",
    ),
)

_ABOUT_INFO_ROWS: tuple[tuple[str, str], ...] = (
    # § Phase 9 (Production Deployment) Part G "Application Versioning" —
    # ЖАЛҒЫЗ канондық ``core/version.py::__version__`` көзінен, ЕШҚАШАН
    # осы жерде қатты кодталмайды (§ "Do NOT scatter version strings").
    ("Нұсқа", __version__),
    ("Платформа", "Windows"),
    ("Интерфейс тілі", "Қазақша"),
    ("Жұмыс режимі", "Мұғалім / Оқушы"),
)

# § "same icons already used by the sidebar where practical" —
# ``ui/navigation/navigation_config.py``-дегі ``NavigationItem.icon_svg``-
# бен БІРДЕЙ вендорленген Fluent SVG файлдары (жобаның бұрыннан бар кіші
# lookup кестесін файлдар арасында қасақана дублирлеу конвенциясы, §
# background_category.py докстрингі). Ескі emoji fallback ЕНДІ қолданылмайды.
_MAIN_SECTIONS: tuple[tuple[str, str, str], ...] = (
    ("ic_fluent_home_24_regular.svg", "Бақылау тақтасы", "жалпы жағдайды бақылау"),
    ("ic_fluent_person_24_regular.svg", "Сыныптар мен оқушылар", "сыныптар мен оқушыларды басқару"),
    ("ic_fluent_beaker_24_regular.svg", "Зертханалық жұмыстар", "эксперименттерді жүргізу"),
    ("ic_fluent_clipboard_data_bar_24_regular.svg", "Нәтижелер", "орындалған жұмыстардың нәтижелері"),
    ("ic_fluent_notebook_24_regular.svg", "Деректер журналы", "өлшеу деректерін қарау"),
    ("ic_fluent_comment_24_regular.svg", "Кері байланысты тексеру", "оқушы жауаптарын тексеру"),
    ("ic_fluent_chart_multiple_24_regular.svg", "Аналитика", "оқу нәтижелерін талдау"),
    ("ic_fluent_plug_connected_24_regular.svg", "Құрылғылар", "сенсорлар мен COM порттарды басқару"),
)

_WORKFLOW_STEPS: tuple[tuple[str, str, str], ...] = (
    (
        "1",
        "Құрылғыны қосу",
        "USB арқылы сенсорды қосып, «Құрылғылар» бөлімінен COM портты таңдаңыз.",
    ),
    (
        "2",
        "Зертханалық жұмысты таңдау",
        "«Зертханалық жұмыстар» бөлімінен қажетті тәжірибені ашыңыз.",
    ),
    (
        "3",
        "Өлшеуді бастау",
        "Құрылғы байланысын тексеріп, экспериментті бастаңыз.",
    ),
)

_TROUBLESHOOTING_ITEMS: tuple[tuple[str, str], ...] = (
    (
        "COM порт көрінбейді",
        "Құрылғыны USB порттан ажыратып, қайта қосыңыз және «Құрылғылар» "
        "бөлімінде «Жаңарту» батырмасын басыңыз.",
    ),
    (
        "Сенсордан дерек келмейді",
        "Құрылғының дұрыс COM портқа қосылғанын және зертханалық жұмысқа "
        "қажетті сенсор таңдалғанын тексеріңіз.",
    ),
    (
        "Құрылғы байланысы үзіліп қалды",
        "USB кабелін және құрылғының қоректенуін тексеріп, құрылғыны қайта "
        "қосыңыз.",
    ),
)

_STEP_BADGE_SIZE = 24


def _make_background_transparent(widget: QWidget) -> None:
    """§ ``devices_page._make_background_transparent()``-пен БІРДЕЙ себеп —
    instance-деңгейлік ``setStyleSheet()`` ТЕК жеке жапырақ виджетке
    (QLabel/QPushButton, интерактивті балалары ЖОҚ), ЕШҚАШАН интерактивті
    балалары бар контейнерге қолданылмайды (§ Phase 20 ``QuestionBankPage``
    регрессиясы)."""
    widget.setStyleSheet("background-color: transparent;")


class HelpPage(QWidget):
    """Анықтама беті — Analytics/Devices/Settings-пен БІРДЕЙ навигация
    тәртібі (тек sidebar, "← Артқа" батырмасы ЖОҚ)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._faq_buttons: list[QPushButton] = []
        self._faq_answers: list[QLabel] = []
        self._section_icon_labels: list[tuple[QLabel, str]] = []
        self._build_ui()

    def refresh_theme_icons(self) -> None:
        """Тема ауысқанда «Негізгі бөлімдер» иконкаларының fill-ін жаңартады."""
        _load_section_icon.cache_clear()
        theme = current_theme()
        for icon_label, svg_filename in self._section_icon_labels:
            icon_label.setPixmap(
                _load_section_icon(svg_filename, theme).pixmap(QSize(_SECTION_ICON_PX, _SECTION_ICON_PX))
            )

    # ---- UI құрылысы -----------------------------------------------------

    def _build_ui(self) -> None:
        title_label = QLabel("Анықтама", self)
        title_font = title_label.font()
        title_font.setBold(True)
        title_font.setPointSize(title_font.pointSize() + 4)
        title_label.setFont(title_font)

        subtitle_label = QLabel(
            "Arduino Physics Lab жүйесін пайдалану бойынша қысқаша нұсқаулық",
            self,
        )
        subtitle_label.setProperty("role", "secondary")
        _make_background_transparent(title_label)
        _make_background_transparent(subtitle_label)

        header_layout = QVBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.addWidget(title_label)
        header_layout.addWidget(subtitle_label)

        left_column = QVBoxLayout()
        left_column.setSpacing(16)
        left_column.addWidget(self._build_faq_panel())
        left_column.addWidget(self._build_workflow_panel())
        left_column.addWidget(self._build_troubleshooting_panel())
        left_column.addStretch(1)

        right_column = QVBoxLayout()
        right_column.addWidget(self._build_about_panel())
        right_column.addWidget(self._build_sections_panel())
        right_column.addStretch(1)

        columns_row = QHBoxLayout()
        columns_row.setSpacing(16)
        columns_row.addLayout(left_column, 65)
        columns_row.addLayout(right_column, 35)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.addLayout(header_layout)
        layout.addLayout(columns_row, 1)

    def _build_panel_frame(self, title: str) -> tuple[QFrame, QVBoxLayout]:
        """§ ``analytics_page._build_panel_frame()``-пен БІРДЕЙ
        DashboardPanel/cardTitle қайта пайдалану."""
        panel = QFrame(self)
        panel.setObjectName("DashboardPanel")

        title_label = QLabel(title, panel)
        title_label.setProperty("role", "cardTitle")
        _make_background_transparent(title_label)

        layout = QVBoxLayout(panel)
        layout.addWidget(title_label)
        layout.setSpacing(12)
        return panel, layout

    # ---- ЖЫЛДАМ КӨМЕК (FAQ accordion) --------------------------------------

    def _build_faq_panel(self) -> QFrame:
        panel, layout = self._build_panel_frame("Жылдам көмек")

        for question, answer in _FAQ_ITEMS:
            layout.addLayout(self._build_faq_item(panel, question, answer))

        return panel

    def _build_faq_item(self, panel: QFrame, question: str, answer: str) -> QVBoxLayout:
        header_button = QPushButton(question, panel)
        header_button.setCheckable(True)
        header_button.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        header_button.setStyleSheet(_FAQ_HEADER_STYLE)
        header_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowDown)
        )

        answer_label = QLabel(answer, panel)
        answer_label.setProperty("role", "secondary")
        answer_label.setWordWrap(True)
        answer_label.setVisible(False)
        _make_background_transparent(answer_label)

        index = len(self._faq_buttons)
        self._faq_buttons.append(header_button)
        self._faq_answers.append(answer_label)
        header_button.toggled.connect(lambda checked, i=index: self._on_faq_toggled(i, checked))

        item_layout = QVBoxLayout()
        item_layout.setSpacing(4)
        item_layout.addWidget(header_button)
        item_layout.addWidget(answer_label)
        return item_layout

    def _on_faq_toggled(self, index: int, checked: bool) -> None:
        # § "Only one FAQ needs to be open at a time" — жаңасын ашу
        # алдыңғы ашық болғанды жабады.
        if checked:
            for other_index, other_button in enumerate(self._faq_buttons):
                if other_index == index:
                    continue
                if other_button.isChecked():
                    other_button.blockSignals(True)
                    other_button.setChecked(False)
                    other_button.blockSignals(False)
                    self._set_faq_expanded(other_index, False)
        self._set_faq_expanded(index, checked)

    def _set_faq_expanded(self, index: int, expanded: bool) -> None:
        self._faq_answers[index].setVisible(expanded)
        icon_type = (
            QStyle.StandardPixmap.SP_ArrowUp
            if expanded
            else QStyle.StandardPixmap.SP_ArrowDown
        )
        self._faq_buttons[index].setIcon(self.style().standardIcon(icon_type))

    # ---- Жұмысты бастау -----------------------------------------------------

    def _build_workflow_panel(self) -> QFrame:
        panel, layout = self._build_panel_frame("Жұмысты бастау")

        steps_row = QHBoxLayout()
        steps_row.setSpacing(12)
        for number, title, description in _WORKFLOW_STEPS:
            steps_row.addLayout(self._build_workflow_step(panel, number, title, description), 1)
        layout.addLayout(steps_row)

        return panel

    def _build_workflow_step(
        self, panel: QFrame, number: str, title: str, description: str
    ) -> QVBoxLayout:
        badge_label = QLabel(number, panel)
        badge_label.setFixedSize(_STEP_BADGE_SIZE, _STEP_BADGE_SIZE)
        badge_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge_font = badge_label.font()
        badge_font.setBold(True)
        badge_label.setFont(badge_font)
        badge_label.setStyleSheet(
            f"background-color: {COLOR_ACCENT}; color: {COLOR_ACCENT_TEXT};"
            f" border-radius: {_STEP_BADGE_SIZE // 2}px;"
        )

        title_label = QLabel(title, panel)
        title_font = title_label.font()
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setWordWrap(True)
        _make_background_transparent(title_label)

        description_label = QLabel(description, panel)
        description_label.setProperty("role", "secondary")
        description_label.setWordWrap(True)
        _make_background_transparent(description_label)

        step_layout = QVBoxLayout()
        step_layout.setSpacing(4)
        step_layout.addWidget(badge_label)
        step_layout.addWidget(title_label)
        step_layout.addWidget(description_label)
        return step_layout

    # ---- Жиі кездесетін мәселелер ---------------------------------------------

    def _build_troubleshooting_panel(self) -> QFrame:
        panel, layout = self._build_panel_frame("Жиі кездесетін мәселелер")

        for title, description in _TROUBLESHOOTING_ITEMS:
            layout.addLayout(self._build_troubleshooting_row(panel, title, description))

        return panel

    def _build_troubleshooting_row(
        self, panel: QFrame, title: str, description: str
    ) -> QVBoxLayout:
        title_label = QLabel(title, panel)
        title_font = title_label.font()
        title_font.setBold(True)
        title_label.setFont(title_font)
        _make_background_transparent(title_label)

        description_label = QLabel(description, panel)
        description_label.setProperty("role", "secondary")
        description_label.setWordWrap(True)
        _make_background_transparent(description_label)

        row_layout = QVBoxLayout()
        row_layout.setSpacing(2)
        row_layout.addWidget(title_label)
        row_layout.addWidget(description_label)
        return row_layout

    # ---- Бағдарлама туралы --------------------------------------------------

    def _build_about_panel(self) -> QFrame:
        panel, layout = self._build_panel_frame("Бағдарлама туралы")

        name_label = QLabel("Arduino Physics Lab", panel)
        name_font = name_label.font()
        name_font.setBold(True)
        name_label.setFont(name_font)
        _make_background_transparent(name_label)
        layout.addWidget(name_label)

        description_label = QLabel(
            "Arduino негізіндегі сенсорлар арқылы физикалық эксперименттер мен "
            "зертханалық жұмыстарды жүргізуге арналған desktop қолданба.",
            panel,
        )
        description_label.setProperty("role", "secondary")
        description_label.setWordWrap(True)
        _make_background_transparent(description_label)
        layout.addWidget(description_label)

        for label_text, value_text in _ABOUT_INFO_ROWS:
            layout.addLayout(self._build_info_row(panel, label_text, value_text))

        return panel

    def _build_info_row(self, panel: QFrame, label_text: str, value_text: str) -> QHBoxLayout:
        row = QHBoxLayout()
        label = QLabel(label_text, panel)
        _make_background_transparent(label)
        value = QLabel(value_text, panel)
        value.setProperty("role", "secondary")
        _make_background_transparent(value)
        row.addWidget(label)
        row.addStretch(1)
        row.addWidget(value)
        return row

    # ---- Негізгі бөлімдер ----------------------------------------------------

    def _build_sections_panel(self) -> QFrame:
        panel, layout = self._build_panel_frame("Негізгі бөлімдер")

        for svg_filename, title, description in _MAIN_SECTIONS:
            layout.addWidget(self._build_section_row(panel, svg_filename, title, description))

        return panel

    def _build_section_row(self, panel: QFrame, svg_filename: str, title: str, description: str) -> QWidget:
        icon_label = QLabel(panel)
        icon_label.setPixmap(
            _load_section_icon(svg_filename, current_theme()).pixmap(QSize(_SECTION_ICON_PX, _SECTION_ICON_PX))
        )
        _make_background_transparent(icon_label)
        self._section_icon_labels.append((icon_label, svg_filename))

        text_label = QLabel(f"<b>{title}</b> — {description}", panel)
        text_label.setProperty("role", "secondary")
        text_label.setWordWrap(True)
        _make_background_transparent(text_label)

        row = QWidget(panel)
        _make_background_transparent(row)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)
        row_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        row_layout.addWidget(icon_label)
        row_layout.addWidget(text_label, 1)
        return row
