"""HomePage — Оқушының фокустелген "Басты бет" дашборды (Phase — Student
Home Dashboard Redesign).

Үш сұраққа дереу жауап беруге бағытталған: Мен кіммін? (сәлемдесу),
Не істеуім керек? ("Жалғастыру" карточкасы), Менің прогресім қандай? (4
KPI карточка + физика бөлімдері). Толық 12 жұмыс каталогын
``ExperimentListPage`` көрсетеді — бұл бет оны ҚАЙТАЛАМАЙДЫ.

``HomePage`` ешбір progress/session/active-student репозиторийін тікелей
СҰРАМАЙДЫ (§ zero-repository-access design, бұрыннан бар): барлық
студентке-тәуелді сан/таңдау ``MainWindow`` арқылы, ``domain.services.
student_home_summary.compute_student_home_summary()``-мен есептеліп,
``set_student_context()`` арқылы дайын күйде беріледі. ``DeviceManager``
ерекшелік — тек оқу/тыңдау үшін тікелей беріледі (``get_connected_
devices()``), ешқашан ``shutdown_all()``/``disconnect_port()``/``stop()``
шақырылмайды (persistent connection architecture, өзгеріссіз).
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from domain.entities.connected_device import ConnectedDevice
from domain.entities.experiment_definition import ExperimentDefinition
from domain.interfaces.i_physics_module import IPhysicsModule
from domain.services.student_home_summary import RecentResult, StudentHomeSummary
from infrastructure.serial_comm.device_manager import DeviceManager
from modules.module_registry import ModuleRegistry
from ui.themes.theme_manager import (
    COLOR_BORDER_SUBTLE,
    COLOR_SECTION_ELECTRICITY,
    COLOR_SECTION_ELECTROMAGNETISM,
    COLOR_SECTION_HEAT,
    COLOR_SECTION_LIGHT,
    FONT_SIZE_MEASUREMENT_VALUE,
)

_EMPTY_MODULES_TEXT = "Қолжетімді модуль жоқ"

# § "Reduce the visual size of KPI numeric values ... approximately
# 10-15%" — ТЕК Student Home-тегі KPI карточкаларына арналған instance-
# деңгейлік font-size (глобал ``[role="cardValue"]`` ережесі, басқа
# көптеген беттерде (Devices/Analytics/Results/...) қолданылатын БІРДЕЙ
# 30px мәні, ЕШҚАШАН өзгертілмейді).
_KPI_VALUE_FONT_SIZE = round(FONT_SIZE_MEASUREMENT_VALUE * 0.87)

# Кезeng 29: терезе енді showMaximized() арқылы ашылады, сондықтан
# max-width көбейтілді — 1920/1600-де контент әлдеқайда көп орын алады,
# бірақ 2560px-те де әлі де sensible cap болып қалады.
_CONTENT_MAX_WIDTH = 1800
# Phase 32.2: centered_layout-тағы [addStretch(1), content, addStretch(1)]
# өрнегінде content-ке ЕДӘУІР басым stretch керек (тек QSizePolicy.
# Expanding жеткіліксіз, эмпирикалық түрде расталды — Qt екі жақтағы
# addStretch(1) spacer-ларына БАРЛЫҚ артық орынды береді, content
# stretch=0 болса, hPolicy Expanding болса да ешқашан sizeHint-тен
# өспейді). Бұл мән spacer-лардың stretch-інен (1) ЕДӘУІР үлкен болуы
# керек — content maximumWidth-ке жеткенше барлық артық енді жұтады,
# содан кейін ғана қалған орын spacer-ларға (центрлеу үшін) қайтады.
_CONTENT_STRETCH = 100

_NEUTRAL_GREETING = "Сәлем!"
_DEFAULT_SUBTITLE = "Бүгінгі зертханалық жұмыстар"

_CONTINUE_EMPTY_TITLE = "Жаңа зертханалық жұмысты бастаңыз"
_CONTINUE_EMPTY_DESCRIPTION = "Қажетті физика бөлімін таңдап, жаңа зертханалық жұмысты бастаңыз."

_RECENT_RESULTS_EMPTY_TITLE = "Әзірге бағаланған нәтиже жоқ."
_RECENT_RESULTS_EMPTY_HINT = (
    "Орындалған зертханалық жұмыстардың нәтижелері осы жерде көрсетіледі."
)
_NO_SCORE_TEXT = "—"

_DEVICE_EMPTY_TITLE = "Құрылғы қосылмаған"
_DEVICE_EMPTY_HINT = "Өлшеуді бастау үшін Arduino сенсорын USB арқылы қосыңыз."
_DEVICE_READY_STATUS_TEXT = "Дайын"
_OPEN_IMPLEMENTED_TEXT = "Ашу →"
_OPEN_PLANNED_TEXT = "Жоспарланған"

# home_page.py/experiment_list_page.py арасында бұрыннан бар дублирование
# конвенциясы (device_card.py/device_panel.py-дегі _SENSOR_TYPE_NAMES_KK
# паттернімен бірдей) — секция атауы бойынша Labs Page-пен ортақ accent.
_SECTION_ACCENT_BY_NAME: dict[str, str] = {
    "Жылу құбылыстары": "heat",
    "Электр құбылыстары": "electricity",
    "Электромагниттік құбылыстар": "electromagnetism",
    "Жарық құбылыстары": "light",
}

# § "use the existing category accent color" — QSS-тегі
# ``QFrame#HomeModuleCard[sectionAccent=...]``-мен БІРДЕЙ түс жиынтығы
# (§ ThemeManager), progress bar chunk-і үшін Python деңгейінде де қажет.
_SECTION_ACCENT_COLOR: dict[str, str] = {
    "heat": COLOR_SECTION_HEAT,
    "electricity": COLOR_SECTION_ELECTRICITY,
    "electromagnetism": COLOR_SECTION_ELECTROMAGNETISM,
    "light": COLOR_SECTION_LIGHT,
}

# Dashboard карточкасына арналған қысқа бір сөйлемдік сипаттама — Labs
# Page-дегі толық тізімді қайталамайды, каталогта сақталмайтын таза
# cosmetic мета.
_MODULE_DESCRIPTION_BY_NAME: dict[str, str] = {
    "Жылу құбылыстары": "Температура және жылулық процестер",
    "Электр құбылыстары": "Ток, кернеу, кедергі және қуат",
    "Электромагниттік құбылыстар": "Магнит өрісі және электромагниттік әсерлер",
    "Жарық құбылыстары": "Жарық құбылыстары мен оптика",
}

# managed_device_card.py/device_card.py/device_panel.py-дегі established
# дублирование конвенциясы — тек қысқа дисплей атауы.
_SENSOR_TYPE_NAMES_KK: dict[str, str] = {
    "VOLTAGE": "Кернеу датчигі",
    "CURRENT": "Ток датчигі",
    "ENERGY": "Қуат және энергия датчигі",
    "OHMMETER": "Омметр",
}
_UNKNOWN_SENSOR_TYPE_NAME_KK = "Белгісіз датчик"


def _make_background_transparent(widget: QWidget) -> None:
    """§ ``teacher_dashboard_page._make_background_transparent()``-мен
    БІРДЕЙ себеп/түзету — ``role``-негізді ``QLabel`` өз ЕНІНЕ (QVBoxLayout-
    та толық созылған) сай ``COLOR_BACKGROUND`` тіктөртбұрышын ақ
    ``HomeSummaryCard`` үстінде бояп кетеді. instance-деңгейлік
    ``setStyleSheet()`` ғана жұмыс істейді."""
    widget.setStyleSheet("background-color: transparent;")


class HomePage(QWidget):
    """Оқушының фокустелген "Басты бет" дашборды: сәлемдесу + негізгі CTA,
    4 KPI карточка, "Жалғастыру" карточкасы, 4 физика бөлімі карточкасы,
    Соңғы нәтижелер + Құрылғы күйі.
    """

    module_selected = Signal(object)  # IPhysicsModule — категория карточкасы
    experiment_selected = Signal(object)  # ExperimentDefinition — Жалғастыру
    devices_requested = Signal()
    labs_requested = Signal()
    results_requested = Signal()  # "Барлық нәтижелер →"

    def __init__(
        self,
        module_registry: ModuleRegistry,
        device_manager: DeviceManager | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._module_registry = module_registry
        self._device_manager = device_manager

        self._kpi_value_labels: dict[str, QLabel] = {}
        self._category_progress_labels: dict[str, QLabel] = {}
        self._category_progress_bars: dict[str, QProgressBar] = {}
        self._continue_resumable_experiment: ExperimentDefinition | None = None

        content = QWidget(self)
        content.setObjectName("HomeContent")
        content.setMaximumWidth(_CONTENT_MAX_WIDTH)
        content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(16)
        content_layout.addWidget(self._build_greeting_header())
        content_layout.addWidget(self._build_kpi_row())
        content_layout.addWidget(self._build_continue_card())
        content_layout.addWidget(self._build_category_row())
        content_layout.addWidget(self._build_bottom_row())
        content_layout.addStretch(1)

        centered = QWidget(self)
        centered_layout = QHBoxLayout(centered)
        centered_layout.setContentsMargins(0, 0, 0, 0)
        centered_layout.addStretch(1)
        centered_layout.addWidget(content, _CONTENT_STRETCH)
        centered_layout.addStretch(1)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setWidget(centered)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(scroll)

        self._render_student_context(None, None, None)
        self._connect_device_manager()
        self._refresh_device_state()

    # ---- Router интерфейсі ------------------------------------------------

    def on_enter(self) -> None:
        """Бет көрсетілер алдында құрылғы күйін қайта рендерлейді (COM
        сканирование ЖОҚ — тек ағымдағы ``DeviceManager`` күйін оқиды).
        """
        self._refresh_device_state()

    def set_devices_action_visible(self, visible: bool) -> None:
        """Phase 37A: "Құрылғыларды тексеру" әрекетін көрсету/жасыру.
        Оқушы режимінде ``devices`` route Router-де рұқсат етілмегендіктен,
        батырма көрінбесе — басқанда үнсіз ешнәрсе болмайтын "өлі"
        батырма көрінбейді (§ "do not add an invalid button").
        """
        self._manage_devices_button.setVisible(visible)

    def set_student_context(
        self,
        student_display_name: str | None,
        classroom_name: str | None,
        summary: StudentHomeSummary | None,
    ) -> None:
        """``MainWindow``-дан НАҚТЫ есептелген ``StudentHomeSummary``-ды
        (§ ``domain.services.student_home_summary``) алады. ``HomePage``
        өзі ЕШБІР репозиторий сұрамайды (§ zero-repository-access
        дизайны). ``summary=None`` — белсенді оқушы жоқ немесе Мұғалім
        режимі: барлық студентке-тәуелді карточка бос/нөлдік күйге
        оралады, ешбір мән ойдан шығарылмайды.
        """
        self._render_student_context(student_display_name, classroom_name, summary)

    # ---- Сәлемдесу header ---------------------------------------------------

    def _build_greeting_header(self) -> QWidget:
        header = QWidget(self)

        self._greeting_label = QLabel(_NEUTRAL_GREETING, header)
        greeting_font = self._greeting_label.font()
        greeting_font.setBold(True)
        greeting_font.setPointSize(greeting_font.pointSize() + 4)
        self._greeting_label.setFont(greeting_font)

        self._greeting_subtitle_label = QLabel(_DEFAULT_SUBTITLE, header)
        self._greeting_subtitle_label.setProperty("role", "secondary")
        _make_background_transparent(self._greeting_label)
        _make_background_transparent(self._greeting_subtitle_label)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.addWidget(self._greeting_label)
        text_layout.addWidget(self._greeting_subtitle_label)

        self._labs_action_button = QPushButton("Зертханалық жұмысты бастау →", header)
        self._labs_action_button.setObjectName("PrimaryButton")
        self._labs_action_button.clicked.connect(self.labs_requested)

        layout = QHBoxLayout(header)
        layout.addLayout(text_layout, 1)
        layout.addWidget(self._labs_action_button, 0, Qt.AlignmentFlag.AlignVCenter)
        return header

    # ---- 4 KPI карточка -----------------------------------------------------

    def _build_kpi_row(self) -> QWidget:
        row = QWidget(self)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)

        cards = (
            ("in_progress", "Орындалып жатыр"),
            ("completed", "Аяқталған"),
            ("awaiting_review", "Тексеруді күтуде"),
            ("devices", "Қосылған құрылғы"),
        )
        for key, label in cards:
            layout.addWidget(self._build_kpi_card(key, label), 1)
        return row

    def _build_kpi_card(self, key: str, label: str) -> QWidget:
        card = QFrame(self)
        card.setObjectName("HomeSummaryCard")

        value_label = QLabel("0", card)
        value_label.setProperty("role", "cardValue")
        # § "Reduce KPI value size ... do not change card dimensions/
        # captions/spacing/accent border" — тек ЖЕКЕ бұл виджеттің font-
        # size-і instance-деңгейде азайтылады (§ leaf QLabel, қауіпсіз).
        value_label.setStyleSheet(
            f"background-color: transparent; font-size: {_KPI_VALUE_FONT_SIZE}px;"
        )
        self._kpi_value_labels[key] = value_label

        caption_label = QLabel(label, card)
        caption_label.setProperty("role", "cardLabel")
        _make_background_transparent(caption_label)

        layout = QVBoxLayout(card)
        layout.addWidget(value_label)
        layout.addWidget(caption_label)
        return card

    # ---- "Жалғастыру" карточкасы ---------------------------------------------

    def _build_continue_card(self) -> QFrame:
        card = QFrame(self)
        card.setObjectName("HomeHero")
        card_layout = QVBoxLayout(card)
        # § "Reduce its height/padding by approximately 20-25%" — тек осы
        # карточкаға арналған ықшам margin/spacing (әдепкі Qt мәні ~9px
        # margin / 6px spacing еді), глобал QSS/басқа карточкаларға
        # ЕШБІР қатысы жоқ.
        card_layout.setContentsMargins(16, 10, 16, 10)
        card_layout.setSpacing(0)

        # § "never apply instance-level setStyleSheet to a container with
        # interactive children" (§ Phase 20 QuestionBankPage регрессиясы) —
        # бұл контейнерде PrimaryButton бар, сондықтан ГЛОБАЛ QSS object-
        # name селекторы қолданылады (§ ThemeManager.build_stylesheet()).
        self._continue_populated_container = QWidget(card)
        self._continue_populated_container.setObjectName("HomeContinuePopulated")
        populated_layout = QVBoxLayout(self._continue_populated_container)
        populated_layout.setContentsMargins(0, 0, 0, 0)
        populated_layout.setSpacing(3)

        continue_title_label = QLabel("Жалғастыру", self._continue_populated_container)
        continue_title_label.setObjectName("HomeHeroTitle")
        _make_background_transparent(continue_title_label)

        self._continue_experiment_label = QLabel(self._continue_populated_container)
        experiment_font = self._continue_experiment_label.font()
        experiment_font.setBold(True)
        self._continue_experiment_label.setFont(experiment_font)
        self._continue_experiment_label.setWordWrap(True)
        _make_background_transparent(self._continue_experiment_label)

        self._continue_category_label = QLabel(self._continue_populated_container)
        self._continue_category_label.setProperty("role", "secondary")
        _make_background_transparent(self._continue_category_label)

        self._continue_sensors_label = QLabel(self._continue_populated_container)
        self._continue_sensors_label.setProperty("role", "secondary")
        _make_background_transparent(self._continue_sensors_label)

        self._continue_button = QPushButton(
            "Жұмысты жалғастыру →", self._continue_populated_container
        )
        self._continue_button.setObjectName("PrimaryButton")
        self._continue_button.clicked.connect(self._on_continue_clicked)

        # § "In-progress secondary indicator" — тек in_progress_count > 1
        # болғанда ғана көрінеді, ешбір екінші carousel/list жасалмайды.
        self._continue_more_in_progress_button = QPushButton(
            "", self._continue_populated_container
        )
        self._continue_more_in_progress_button.setObjectName("HomeContinueMoreLink")
        self._continue_more_in_progress_button.clicked.connect(self.labs_requested)
        self._continue_more_in_progress_button.setVisible(False)

        populated_layout.addWidget(continue_title_label)
        populated_layout.addWidget(self._continue_experiment_label)
        populated_layout.addWidget(self._continue_category_label)
        populated_layout.addWidget(self._continue_sensors_label)
        populated_layout.addWidget(self._continue_button, 0, Qt.AlignmentFlag.AlignLeft)
        populated_layout.addWidget(
            self._continue_more_in_progress_button, 0, Qt.AlignmentFlag.AlignLeft
        )

        self._continue_empty_container = QWidget(card)
        self._continue_empty_container.setObjectName("HomeContinueEmpty")
        empty_layout = QVBoxLayout(self._continue_empty_container)
        empty_layout.setContentsMargins(0, 0, 0, 0)
        empty_layout.setSpacing(3)

        empty_title_label = QLabel(_CONTINUE_EMPTY_TITLE, self._continue_empty_container)
        empty_title_label.setObjectName("HomeHeroTitle")
        _make_background_transparent(empty_title_label)

        empty_description_label = QLabel(
            _CONTINUE_EMPTY_DESCRIPTION, self._continue_empty_container
        )
        empty_description_label.setProperty("role", "secondary")
        empty_description_label.setWordWrap(True)
        _make_background_transparent(empty_description_label)

        self._continue_empty_button = QPushButton(
            "Зертханалық жұмыстарды ашу →", self._continue_empty_container
        )
        self._continue_empty_button.setObjectName("PrimaryButton")
        self._continue_empty_button.clicked.connect(self.labs_requested)

        empty_layout.addWidget(empty_title_label)
        empty_layout.addWidget(empty_description_label)
        empty_layout.addWidget(self._continue_empty_button, 0, Qt.AlignmentFlag.AlignLeft)

        card_layout.addWidget(self._continue_populated_container)
        card_layout.addWidget(self._continue_empty_container)
        return card

    def _on_continue_clicked(self) -> None:
        if self._continue_resumable_experiment is not None:
            self.experiment_selected.emit(self._continue_resumable_experiment)

    # ---- Физика бөлімдері (категория карточкалары) -----------------------------

    def _build_category_row(self) -> QWidget:
        row = QWidget(self)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)

        modules = self._module_registry.get_all()
        if not modules:
            layout.addWidget(QLabel(_EMPTY_MODULES_TEXT, row))
            return row

        for module in modules:
            layout.addWidget(self._build_category_card(module), 1)
        return row

    def _build_category_card(self, module: IPhysicsModule) -> QWidget:
        card = QFrame(self)
        card.setObjectName("HomeModuleCard")
        accent = _SECTION_ACCENT_BY_NAME.get(module.get_name())
        if accent is not None:
            card.setProperty("sectionAccent", accent)

        icon_label = QLabel(module.get_icon() or "", card)
        icon_label.setObjectName("HomeModuleCardIcon")

        title_label = QLabel(module.get_name(), card)
        title_label.setObjectName("HomeModuleCardTitle")
        title_label.setWordWrap(True)

        header_row = QHBoxLayout()
        header_row.addWidget(icon_label)
        header_row.addWidget(title_label, 1)

        description_label = QLabel(
            _MODULE_DESCRIPTION_BY_NAME.get(module.get_name(), ""), card
        )
        description_label.setWordWrap(True)
        description_label.setProperty("role", "secondary")
        _make_background_transparent(description_label)

        progress_label = QLabel(card)
        progress_label.setProperty("role", "secondary")
        _make_background_transparent(progress_label)
        self._category_progress_labels[module.get_name()] = progress_label

        # § "Category progress indicator" — жіңішке (3-4px) progress bar,
        # ``class_activity_carousel.py``-дегі ``DashboardActivityBar``-мен
        # БІРДЕЙ рецепт (instance-деңгейлік QSS, chunk=категория accent-і,
        # трек=COLOR_BORDER_SUBTLE), тек бөлек object-name (ортақ глобал
        # ережеге ЕШБІР қатысы жоқ, әр категория ӨЗ accent түсін алады).
        progress_bar = QProgressBar(card)
        progress_bar.setObjectName("HomeCategoryProgressBar")
        progress_bar.setRange(0, 100)
        progress_bar.setTextVisible(False)
        progress_bar.setFixedHeight(4)
        chunk_color = _SECTION_ACCENT_COLOR.get(accent or "", COLOR_BORDER_SUBTLE)
        progress_bar.setStyleSheet(
            f"QProgressBar#HomeCategoryProgressBar {{ border: none; border-radius: 2px;"
            f" background-color: {COLOR_BORDER_SUBTLE}; }}"
            f"QProgressBar#HomeCategoryProgressBar::chunk {{ background-color: {chunk_color};"
            f" border-radius: 2px; }}"
        )
        self._category_progress_bars[module.get_name()] = progress_bar
        self._set_category_progress(module, completed=0)

        has_implemented = any(experiment.is_implemented for experiment in module.get_experiments())
        action_button = QPushButton(
            _OPEN_IMPLEMENTED_TEXT if has_implemented else _OPEN_PLANNED_TEXT, card
        )
        action_button.setObjectName("HomeModuleCardAction")
        action_button.clicked.connect(
            lambda _checked=False, m=module: self.module_selected.emit(m)
        )

        layout = QVBoxLayout(card)
        layout.addLayout(header_row)
        layout.addWidget(description_label)
        layout.addWidget(progress_label)
        layout.addWidget(progress_bar)
        layout.addStretch(1)
        layout.addWidget(action_button)
        return card

    def _set_category_progress(self, module: IPhysicsModule, completed: int) -> None:
        label = self._category_progress_labels.get(module.get_name())
        bar = self._category_progress_bars.get(module.get_name())
        total = len(module.get_experiments())
        if label is not None:
            label.setText(f"{completed} / {total} орындалды")
        if bar is not None:
            # § "if Y == 0, render 0 safely" — 0 бөлуге ЕШҚАШАН жол
            # берілмейді, бос каталог/бөлім болса бар жай 0% көрсетеді.
            percentage = round((completed / total) * 100) if total > 0 else 0
            bar.setValue(max(0, min(100, percentage)))

    # ---- Төменгі екі баған: Соңғы нәтижелер + Құрылғы күйі -----------------------

    def _build_bottom_row(self) -> QWidget:
        row = QWidget(self)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._build_recent_results_panel(), 1)
        layout.addWidget(self._build_device_status_panel(), 1)
        return row

    def _build_recent_results_panel(self) -> QWidget:
        panel = QFrame(self)
        panel.setObjectName("HomeDevicePanel")

        title_label = QLabel("Соңғы нәтижелер", panel)
        title_font = title_label.font()
        title_font.setBold(True)
        title_label.setFont(title_font)
        _make_background_transparent(title_label)

        self._recent_results_empty_title_label = QLabel(_RECENT_RESULTS_EMPTY_TITLE, panel)
        self._recent_results_empty_hint_label = QLabel(_RECENT_RESULTS_EMPTY_HINT, panel)
        self._recent_results_empty_hint_label.setProperty("role", "secondary")
        self._recent_results_empty_hint_label.setWordWrap(True)
        _make_background_transparent(self._recent_results_empty_title_label)
        _make_background_transparent(self._recent_results_empty_hint_label)

        self._recent_results_container = QWidget(panel)
        self._recent_results_container.setObjectName("HomeRecentResultsContainer")
        self._recent_results_layout = QVBoxLayout(self._recent_results_container)
        self._recent_results_layout.setContentsMargins(0, 0, 0, 0)

        view_all_button = QPushButton("Барлық нәтижелер →", panel)
        view_all_button.setObjectName("HomeModuleCardAction")
        view_all_button.clicked.connect(self.results_requested)

        layout = QVBoxLayout(panel)
        layout.addWidget(title_label)
        layout.addWidget(self._recent_results_empty_title_label)
        layout.addWidget(self._recent_results_empty_hint_label)
        layout.addWidget(self._recent_results_container)
        layout.addStretch(1)
        layout.addWidget(view_all_button, 0, Qt.AlignmentFlag.AlignLeft)
        return panel

    def _build_recent_result_row(self, result: RecentResult) -> QWidget:
        row = QWidget(self)
        row.setObjectName("HomeRecentResultRow")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)

        experiment = result.experiment
        title_line = (
            f"№{experiment.display_number}   {experiment.title}"
            if experiment.display_number is not None
            else experiment.title
        )
        title_label = QLabel(title_line, row)
        title_label.setWordWrap(True)
        _make_background_transparent(title_label)

        score_text = (
            f"{result.teacher_score} / 10" if result.teacher_score is not None else _NO_SCORE_TEXT
        )
        score_label = QLabel(score_text, row)
        score_label.setProperty("role", "secondary")
        _make_background_transparent(score_label)

        layout.addWidget(title_label, 1)
        layout.addWidget(score_label, 0, Qt.AlignmentFlag.AlignRight)
        return row

    def _build_device_status_panel(self) -> QWidget:
        panel = QFrame(self)
        panel.setObjectName("HomeDevicePanel")

        title_label = QLabel("Құрылғы күйі", panel)
        title_font = title_label.font()
        title_font.setBold(True)
        title_label.setFont(title_font)
        _make_background_transparent(title_label)

        self._device_summary_label = QLabel(panel)
        self._device_summary_label.setProperty("role", "secondary")
        _make_background_transparent(self._device_summary_label)

        self._device_empty_title_label = QLabel(_DEVICE_EMPTY_TITLE, panel)
        self._device_empty_hint_label = QLabel(_DEVICE_EMPTY_HINT, panel)
        self._device_empty_hint_label.setProperty("role", "secondary")
        self._device_empty_hint_label.setWordWrap(True)
        _make_background_transparent(self._device_empty_title_label)
        _make_background_transparent(self._device_empty_hint_label)

        # § "an ancestor's instance-level stylesheet can interfere with a
        # specially-styled descendant even when not the direct parent"
        # (эмпирикалық түрде расталды — #HomeDeviceStatusDot түсі осы
        # контейнер арқылы бұзылды) — ГЛОБАЛ QSS object-name селекторы.
        self._device_lines_container = QWidget(panel)
        self._device_lines_container.setObjectName("HomeDeviceLinesContainer")
        self._device_lines_layout = QVBoxLayout(self._device_lines_container)
        self._device_lines_layout.setContentsMargins(0, 0, 0, 0)

        self._manage_devices_button = QPushButton("Құрылғыларды тексеру", panel)
        self._manage_devices_button.clicked.connect(self.devices_requested)

        layout = QVBoxLayout(panel)
        layout.addWidget(title_label)
        layout.addWidget(self._device_summary_label)
        layout.addWidget(self._device_empty_title_label)
        layout.addWidget(self._device_empty_hint_label)
        layout.addWidget(self._device_lines_container)
        layout.addStretch(1)
        layout.addWidget(self._manage_devices_button, 0, Qt.AlignmentFlag.AlignLeft)
        return panel

    def _build_device_line(self, device: ConnectedDevice) -> QWidget:
        # § "never apply instance-level setStyleSheet to a container with
        # a specially-styled child" — ``status_dot`` (#HomeDeviceStatusDot)
        # ЖАСЫЛ түсі instance-деңгейлік fix арқылы бұзылатыны эмпирикалық
        # түрде расталды (screenshot тексерілді), сондықтан ГЛОБАЛ QSS
        # object-name селекторы қолданылады.
        row = QWidget(self)
        row.setObjectName("HomeDeviceLineRow")
        layout = QVBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        display_name = _SENSOR_TYPE_NAMES_KK.get(
            device.sensor_type.upper(), None
        ) or (device.sensor_type or _UNKNOWN_SENSOR_TYPE_NAME_KK)

        name_label = QLabel(display_name, row)
        name_font = name_label.font()
        name_font.setBold(True)
        name_label.setFont(name_font)
        _make_background_transparent(name_label)

        port_label = QLabel(device.port_name, row)
        port_label.setProperty("role", "secondary")
        _make_background_transparent(port_label)

        status_row = QHBoxLayout()
        status_row.setContentsMargins(0, 0, 0, 0)
        status_dot = QLabel(row)
        status_dot.setObjectName("HomeDeviceStatusDot")
        status_dot.setFixedSize(10, 10)
        status_label = QLabel(_DEVICE_READY_STATUS_TEXT, row)
        _make_background_transparent(status_label)
        status_row.addWidget(status_dot)
        status_row.addWidget(status_label)
        status_row.addStretch(1)

        layout.addWidget(name_label)
        layout.addWidget(port_label)
        layout.addLayout(status_row)
        return row

    # ---- Рендеринг: студент контексі -----------------------------------------

    def _render_student_context(
        self,
        student_display_name: str | None,
        classroom_name: str | None,
        summary: StudentHomeSummary | None,
    ) -> None:
        self._render_greeting(student_display_name, classroom_name)
        self._render_kpis(summary)
        self._render_continue_card(summary)
        self._render_category_cards(summary)
        self._render_recent_results(summary)

    def _render_greeting(self, student_display_name: str | None, classroom_name: str | None) -> None:
        if student_display_name is None:
            # § "If no active student is resolved, use a safe neutral
            # title rather than fabricated identity data."
            self._greeting_label.setText(_NEUTRAL_GREETING)
            self._greeting_subtitle_label.setText(_DEFAULT_SUBTITLE)
            return

        self._greeting_label.setText(f"Сәлем, {student_display_name}!")
        if classroom_name is not None:
            self._greeting_subtitle_label.setText(f"{classroom_name} сыныбы · {_DEFAULT_SUBTITLE}")
        else:
            self._greeting_subtitle_label.setText(_DEFAULT_SUBTITLE)

    def _render_kpis(self, summary: StudentHomeSummary | None) -> None:
        in_progress = summary.in_progress_count if summary is not None else 0
        completed = summary.completed_count if summary is not None else 0
        awaiting_review = summary.awaiting_review_count if summary is not None else 0
        self._kpi_value_labels["in_progress"].setText(str(in_progress))
        self._kpi_value_labels["completed"].setText(str(completed))
        self._kpi_value_labels["awaiting_review"].setText(str(awaiting_review))

    def _render_continue_card(self, summary: StudentHomeSummary | None) -> None:
        resumable = summary.resumable if summary is not None else None
        populated = resumable is not None
        self._continue_populated_container.setVisible(populated)
        self._continue_empty_container.setVisible(not populated)

        if not populated:
            self._continue_resumable_experiment = None
            return

        experiment = resumable.experiment
        self._continue_resumable_experiment = experiment

        title_line = (
            f"№{experiment.display_number}   {experiment.title}"
            if experiment.display_number is not None
            else experiment.title
        )
        self._continue_experiment_label.setText(title_line)

        icon = resumable.module.get_icon() or ""
        category_text = f"{icon} {resumable.module.get_name()}".strip()
        self._continue_category_label.setText(category_text)

        sensor_names = [
            _SENSOR_TYPE_NAMES_KK.get(sensor_type.upper(), sensor_type)
            for sensor_type in experiment.required_sensor_types
        ]
        self._continue_sensors_label.setText(" + ".join(sensor_names))
        self._continue_sensors_label.setVisible(bool(sensor_names))

        remaining_in_progress = summary.in_progress_count - 1
        if remaining_in_progress > 0:
            self._continue_more_in_progress_button.setText(
                f"Тағы {remaining_in_progress} орындалып жатқан жұмыс"
            )
            self._continue_more_in_progress_button.setVisible(True)
        else:
            self._continue_more_in_progress_button.setVisible(False)

    def _render_category_cards(self, summary: StudentHomeSummary | None) -> None:
        completed_by_module_name: dict[str, int] = {}
        if summary is not None:
            completed_by_module_name = {
                category.module.get_name(): category.completed
                for category in summary.category_progress
            }
        for module in self._module_registry.get_all():
            completed = completed_by_module_name.get(module.get_name(), 0)
            self._set_category_progress(module, completed)

    def _render_recent_results(self, summary: StudentHomeSummary | None) -> None:
        results = summary.recent_results if summary is not None else ()

        while self._recent_results_layout.count():
            item = self._recent_results_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        has_results = bool(results)
        self._recent_results_empty_title_label.setVisible(not has_results)
        self._recent_results_empty_hint_label.setVisible(not has_results)
        self._recent_results_container.setVisible(has_results)
        for result in results:
            self._recent_results_layout.addWidget(self._build_recent_result_row(result))

    # ---- DeviceManager (тек оқу/тыңдау — ешқашан ажырату/тоқтату жоқ) --------

    def _connect_device_manager(self) -> None:
        if self._device_manager is None:
            return
        self._device_manager.device_identified.connect(self._on_device_manager_changed)
        self._device_manager.port_disconnected.connect(self._on_device_manager_changed)

    def _on_device_manager_changed(self, *_args: object) -> None:
        self._refresh_device_state()

    def _refresh_device_state(self) -> None:
        devices: tuple[ConnectedDevice, ...] = ()
        if self._device_manager is not None:
            devices = self._device_manager.get_connected_devices()

        self._kpi_value_labels["devices"].setText(str(len(devices)))

        while self._device_lines_layout.count():
            item = self._device_lines_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        has_devices = bool(devices)
        self._device_empty_title_label.setVisible(not has_devices)
        self._device_empty_hint_label.setVisible(not has_devices)
        self._device_summary_label.setVisible(has_devices)
        self._device_lines_container.setVisible(has_devices)

        if not has_devices:
            return

        self._device_summary_label.setText(f"{len(devices)} құрылғы қосылған")
        for device in devices:
            self._device_lines_layout.addWidget(self._build_device_line(device))
