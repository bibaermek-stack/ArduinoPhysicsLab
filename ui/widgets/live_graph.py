"""LiveGraphWidget — таңдалған тәжірибеге бейімделетін, нақты уақыттағы
график.

Бұл виджет тек көрсетуге жауап береді — ешбір физикалық шаманы
есептемейді, ``PacketParser``/``DataValidator``/``CalculationEngine``
логикасын қайталамайды. Тек ``Measurement.get_value()``-ден дайын
мәндерді алып, PyQtGraph арқылы сызады.

Екі режимді қолдайды (``configure_channels`` арқылы таңдалады):

- **Уақыттық режим** (``x_channel=None``): X = өткен уақыт (``time``
  арнасы бар болса сол, әйтпесе ``timestamp``-тен есептелген elapsed),
  Y = әр configured арна. Әрқашан сызықпен қосылады.
- **X-Y режим** (``x_channel`` берілсе): X = сол арнаның мәні, Y = әр
  ``y_channels`` арнасының мәні. X немесе Y жоқ болса, сол нүкте
  қосылмайды. Әдепкі бойынша да сызықпен қосылады (ескі мінез-құлық),
  бірақ ``connect_points=False`` берілсе (мыс. Ohm's Law) Vernier
  Graphical Analysis тәрізді scatter (pen=None, symbol='o') болады,
  дубликат нүктелер (``dedup_*_tolerance``) тек осы презентация
  қабатында сүзіледі, әрі сызықтық fit (``show_fit=True``) қосылады.

X-Y режимде қосымша **manual point capture** (``capture_mode=True``,
Ohm's Law): 10Hz raw Measurement ағыны графикке ТІКЕЛЕЙ түспейді — тек
соңғы N үлгінің rolling buffer-іне жиналады. Пайдаланушы "Нүктені
сақтау" батырмасын басқанда ғана, буфер тұрақты (spread толеранс
ішінде) болса, орташа мәннен бір нүкте графикке қосылады. Бұл transient/
шулы аралық мәндердің fit-ке кіруін болдырмайды.

Уақыттық режимде қосымша **stacked** мүмкіндігі (``stacked=True``,
мыс. "Электр тізбегін құрастыру және ток күшін өлшеу"): ЖАЛҒЫЗ ортақ Y
scale орнына, әр ``y_channels``
кілті үшін бөлек ``PlotWidget`` салынады (синхрондалған X осімен) —
әртүрлі бірлік/диапазонды шамаларды (кернеу мен ток) бір Y осьте
қыспау үшін.
"""

from collections import deque
from datetime import datetime
from functools import lru_cache

import pyqtgraph as pg
import pyqtgraph.exporters as pg_exporters
from PySide6.QtCore import QByteArray, QSize, Qt, Signal
from PySide6.QtGui import QIcon, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.resource_paths import resource_path
from domain.entities.experiment_definition import RateOfChangeConfig
from domain.entities.experiment_session import ExperimentSession
from domain.entities.measurement import Measurement
from domain.entities.sensor_channel import SensorChannel
from domain.services.graph_analysis import (
    DERIVED_ANALYSIS_POWER_ENERGY,
    DeltaResult,
    RegressionResult,
    compute_delta,
    compute_linear_regression,
    compute_region_statistics,
    compute_residuals,
    compute_trapezoidal_integral,
    indices_in_range,
    nearest_index,
)
from domain.services.region_analysis_exporter import (
    ChannelAnalysisSummary,
    RegionAnalysisExporter,
    RegionAnalysisSummary,
    format_fit_summary,
    format_region_analysis_summary,
)
from ui.widgets.graph_analysis_panel import GraphAnalysisPanel
from ui.themes.theme_manager import current_theme, theme_color
from ui.widgets.graph_crosshair import PlotCrosshair

# Жеңіл, Vernier Graphical Analysis тәрізді ғылыми тема — ашық фон, қара
# ось/мәтін. Модуль деңгейінде бір рет орнатылады, бүкіл қолданбада
# LiveGraphWidget жалғыз PlotWidget тұтынушысы болғандықтан ешбір басқа
# графикке қатысы жоқ.
# Phase 9: pure "w"/"k" орнына ThemeManager-дің ``COLOR_GRAPH_BACKGROUND``/
# ``COLOR_GRAPH_AXIS`` токендері қолданылады (мәні дәл сол — #FFFFFF/
# #111827 — тек ЕНДІ орталық токен көзінен, "сиқырлы әріп" емес).
pg.setConfigOptions(
    background=theme_color("COLOR_GRAPH_BACKGROUND"),
    foreground=theme_color("COLOR_GRAPH_AXIS"),
)

# Phase 3 (Experiment Workspace graph geometry fix): бұрын ешбір
# plot widget-те минималды биіктік болмаған — QSplitter/QVBoxLayout
# қолжетімді орынды stretch=1 бойынша "адал" бөлетін, БІРАҚ қолжетімді
# орынның ӨЗІ тым аз болса (мыс. 1366×768-де 2-plot stacked график),
# нәтиже title/os белгілері/tick label-дер бір-біріне түсетін дәрежеде
# сығылатын (эмпирикалық түрде расталды: 87px/subplot). Бұл минимум —
# pyqtgraph-тың әдепкі title+os+tick қаріптерімен title/tick қабатсыз
# оқылатын ЕҢ КІШІ биіктік (§ MeasurementWorkspace-тегі QScrollArea
# осы минимумды құрметтеп, қолжетімді орын жетіспесе scroll ұсынады —
# бірақ ЕШҚАШАН QStackedWidget-тің жалпы терезе минимумын үлкейтпейді,
# өйткені QScrollArea-ның ӨЗІНІҢ minimumSizeHint-і кішкентай болып
# қалады).
#
# Phase 5 (Graph Area Optimization): пайдаланушы 220px флоорды ЕКІ
# stacked subplot-пен бірге 1366×768-де scroll-СЫЗ сыюын НАҚТЫ талап
# етті ("Do not add vertical scrollbars"). Хром (toolbar/header/margin/
# spacing) Phase 5-те ықшамдалғаннан кейін 1366×768-де graph card-қа
# қолжетімді 443px-тен ~352px екі subplot-қа қалады (91px хром) — яғни
# әр subplot ЕҢ КӨБІ ~176px бола алады. 170px осы бюджеттен төмен
# (қауіпсіздік қоры), БІРАҚ бұрынғы бұзылған 87px-тен ӘЛІ ДЕ айтарлықтай
# үлкен — скриншот арқылы title/tick label overlap ЖОҚ екені расталды.
# Бұл ТЕК абсолютті қауіпсіздік флоор — нақты рендерленген биіктік
# (Expanding size policy арқылы) қолжетімді орынға сай ӘРҚАШАН одан
# үлкен болады (мыс. 1920×1080-де ~339px).
_MIN_STACKED_PLOT_HEIGHT = 170
_MIN_SINGLE_PLOT_HEIGHT = 240

_MAX_POINTS = 10000
_ELAPSED_TIME_LABEL = "Өткен уақыт"
_ELAPSED_TIME_UNIT = "s"
_AUTORANGE_PADDING = 0.09
_SCATTER_SYMBOL_SIZE = 8
_FIT_LINE_COLOR = (90, 90, 90)
_MIN_FIT_POINTS = 3
_CAPTURE_EPSILON = 1e-9

_FIT_PANEL_TITLE = "Сызықтық аппроксимация"
_FIT_INSUFFICIENT_TEXT = "Кемінде 3 нүкте сақтаңыз"
_FIT_WARNING_TEXT = "⚠ Физикалық модельге сәйкес келмейді"
_CAPTURE_HINT_TEXT = (
    "Өлшеуді бастаңыз және мән тұрақталған кезде «Нүктені сақтау» батырмасын басыңыз."
)
_STATUS_NO_DATA = "Деректер жоқ."
_STATUS_UNSTABLE = "Мән тұрақталған жоқ. Бірнеше секунд күтіңіз."
_STATUS_VALUE_NEAR_ZERO = "Мән нөлге тым жақын — нүкте сақталмады."
_STATUS_DUPLICATE = "Бұл нүкте алдыңғы сақталған нүктеге тым жақын — қосылмады."
_STATUS_IMAGE_EXPORT_FAILED = "Суретті сақтау сәтсіз аяқталды. Файл жолын/дискіні тексеріңіз."
_STATUS_IMAGE_EXPORT_SAVED = "Сурет сақталды."

# Phase 32.1: hardware-тәуелсіз workspace — графикте әлі бірде-бір нүкте
# жоқ кезде (0/N немесе ішінара N/M құрылғы), осьтер/тор/toolbar толық
# көрінеді, тек осы жеңіл ескерту мәтіні қосымша шығады. Manual-capture
# режимінде (Ohm's Law) өз _hint_label-і бар болғандықтан, бұл хабарлама
# ОНЫ қайталамайды (тек capture_mode=False графиктерде көрінеді).
_EMPTY_STATE_NO_DEVICES_TEXT = "Өлшеуді бастау үшін құрылғыларды қосыңыз"
# Phase 33A §14: құрылғылар дайын, бірақ тәжірибе әлі басталмаған кезде
# дәлірек хабарлама — MeasurementWorkspace.set_ready()-ден set_devices_
# ready() арқылы келеді.
_EMPTY_STATE_DEVICES_READY_TEXT = "Өлшеуді бастау үшін «Бастау» батырмасын басыңыз"

# ---- Phase 33A: Scientific Graph Core ---------------------------------
_LATEST_MARKER_SIZE = 11
_LATEST_MARKER_COLOR = (37, 99, 235)  # ThemeManager.COLOR_ACCENT
_DEFAULT_READOUT_DECIMALS = 3
_MOUSE_MODE_TOOLTIPS = {
    "pan": "Жылжыту — тышқанмен сүйреп графикті жылжытыңыз",
    "zoom": "Масштабтау — тышқанмен аймақ таңдап ұлғайтыңыз (дөңгелек — кез келген режимде масштабтайды)",
}

# ---- Phase 33B: Region/interval analysis -------------------------------
_REGION_BUTTON_TOOLTIP = "Аралықты талдау"
# Phase 34
_DELTA_BUTTON_TOOLTIP = "Екі нүктелік өлшеу (A/B, Δ)"
_RESIDUAL_BUTTON_TOOLTIP = "Қалдықтар (measured − fit)"
_IMAGE_EXPORT_TOOLTIP = "Суретке сақтау (PNG/SVG)"
_COPY_SUMMARY_TOOLTIP = "Нәтижені көшіру"
_DELTA_MARKER_COLOR_A = (16, 141, 79)  # жасыл
_DELTA_MARKER_COLOR_B = (194, 65, 12)  # қызғылт-сары
_DELTA_MARKER_SIZE = 12
_DELTA_PANEL_TITLE = "Δ өлшеу (A/B)"
_DELTA_EMPTY_TEXT = "Графикте A нүктесін таңдау үшін басыңыз."
_RESIDUAL_INSUFFICIENT_TEXT = "Fit жеткіліксіз — қалдықтар есептелмейді."
_REGION_BRUSH_COLOR = (37, 99, 235, 30)  # ThemeManager.COLOR_ACCENT, өте бозғылт
_REGION_LINE_COLOR = (37, 99, 235, 160)
# Бастапқы аймақ — көрінетін X ауқымының орталық бөлігі (§2: "select a
# reasonable central portion of the currently visible X range").
_DEFAULT_REGION_FRACTION = (0.25, 0.75)
_MIN_FIT_POINTS_TOOLTIP = "Кемінде 3 нүкте қажет"
# DERIVED_ANALYSIS_POWER_ENERGY — domain.services.graph_analysis-тен
# импортталады (домен қабатында орналасуының себебі сол модульде
# түсіндірілген): ExperimentDefinition (домен) осы мәнді
# validate_configuration()-де тексереді, ал бұл жерде тек қайта
# экспортталады (LiveGraphWidget-ті ЕСКІ import path-пен қолданатын
# кодтың бұзылмауы үшін).

# Phase 7 (Graph Toolbar Icon Integration): вендорленген Fluent SVG
# иконкалар — ДӘЛ ОСЫ Design/02_FluentIcons/svg/ жиынтығы, Phase 6-да
# Sidebar-ге қолданылған. ЕСКЕРТУ: ``ui/widgets/sidebar.py``-дегі
# `_load_nav_icon()`/`_render_svg_pixmap()`-ті ОСЫ файлдан импорттау
# ЕМЕС, әдейі бөлек, кішкентай көшірме қолданылады — Sidebar-дың
# Off/On (ақ/қараңғы) екі pixmap логикасы ТЕК SidebarNavButton-тың
# accent-көк "таңдалған" фонына арналған; graph toolbar батырмаларында
# ондай фон ЖОҚ (тексерілді — ешбір ``variant="icon"`` де,
# ``#SidebarNavButton``-ша арнайы object name де ЖОҚ, тек база
# ``QPushButton`` QSS-і), сондықтан бір ғана (қараңғы) pixmap
# жеткілікті. Екі модульді ортақ жеке функцияға тәуелді ету —
# Sidebar-ге қатысы жоқ болашақ graph toolbar өзгерісінің Sidebar-ды
# байқаусызда бұзу қаупін тудырар еді (§ пайдаланушының нұсқауы:
# "leave the Sidebar helper untouched and use the smallest safe
# alternative").
_TOOLBAR_ICON_DIR = resource_path("Design", "02_FluentIcons", "svg")
_TOOLBAR_ICON_RENDER_PX = 64
# Phase 6-дағы Sidebar-мен БІРДЕЙ эмпирикалық қорытынды: вендорленген
# 24px SVG-ті кез келген кіші өлшемге дейін рендерлеуге болады, БІРАҚ
# 8px (баспалдық sizeHint-ті дәл сақтайтын жалғыз мән) көзбен
# тексергенде анық емес шықты (§ есеп). 12px — Sidebar-де қолданылған,
# көзбен расталған, ЕҢ КІШІ анық өлшем — осында да қайта пайдаланылды
# (дәйектілік үшін), небәрі ~4px batырма ені өсіміне әкеледі (өлшенді,
# есепте көрсетілген), toolbar жолының биіктігіне/graph-тың тік
# орнына ЕШБІР әсері ЖОҚ.
_TOOLBAR_ICON_PX = 12
_TOOLBAR_ICON_FILL_DARK = b'fill="#212121"'


@lru_cache(maxsize=None)
def _load_toolbar_icon(svg_filename: str, theme: str = "dark") -> QIcon:
    """Вендорленген Fluent SVG-ден бір pixmap-пен ``QIcon`` құрады.

    Sidebar-дегі ``_load_nav_icon()``-нан айырмашылығы: мұнда Off/On
    (қараңғы/ақ) екі pixmap ЖОҚ — graph toolbar батырмаларының
    ешқайсысында accent-көк "таңдалған" фон жоқ (тексерілді). Қараңғы
    темада ашық fill, ашық темада қараңғы fill қолданылады.
    """
    svg_bytes = (_TOOLBAR_ICON_DIR / svg_filename).read_bytes()
    fill = b'fill="#212121"' if theme == "light" else b'fill="#DCE4EE"'
    svg_bytes = svg_bytes.replace(_TOOLBAR_ICON_FILL_DARK, fill)
    icon = QIcon()
    icon.addPixmap(_render_toolbar_svg_pixmap(svg_bytes), QIcon.Mode.Normal, QIcon.State.Off)
    return icon


def _render_toolbar_svg_pixmap(svg_bytes: bytes) -> QPixmap:
    renderer = QSvgRenderer(QByteArray(svg_bytes))
    pixmap = QPixmap(_TOOLBAR_ICON_RENDER_PX, _TOOLBAR_ICON_RENDER_PX)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(_TOOLBAR_ICON_RENDER_PX / _TOOLBAR_ICON_PX)
    return pixmap


class LiveGraphWidget(QWidget):
    """Таңдалған тәжірибенің арналарын нақты уақытта сызатын, PyQtGraph
    негізіндегі график виджеті.
    """

    capture_status = Signal(str)
    # Phase 33A: MeasurementWorkspace-ке "графикті үлкейту/қалпына
    # келтіру" сұрауын жеткізеді — LiveGraphWidget өзі layout-ты
    # (graph/table splitter) басқармайды, тек ниетті хабарлайды.
    maximize_toggled = Signal(bool)

    def __init__(
        self, parent: QWidget | None = None, default_auto_scale: bool = True
    ) -> None:
        super().__init__(parent)
        # Phase 22 (Settings §6 "Графикті автоматты масштабтау"): тек
        # ОСЫ виджет данасының БАСТАПҚЫ checkbox күйі — белсенді
        # (жұмыс істеп тұрған) графикке ЕШҚАШАН кері әсер етпейді, тек
        # ЖАҢА дана құрылғанда оқылады (§ "never silently interrupt an
        # active experiment"). Әдепкі ``True`` — ескі, ӨЗГЕРТІЛМЕГЕН
        # мінез-құлық (§ "Do NOT silently change the existing default").
        self._default_auto_scale = default_auto_scale
        # Phase 32: график/кесте workspace-тің primary икемді аймағы —
        # LiveGraphWidget өзі екі бағытта да Expanding болуы тиіс, толбар
        # компакт қалады (QVBoxLayout-та stretch алмайды).
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._start_time: datetime | None = None
        self._x_channel: str | None = None
        self._curve_keys: tuple[str, ...] = ()
        self._channel_map: dict[str, SensorChannel] = {}
        self._x_data: dict[str, deque[float]] = {}
        self._y_data: dict[str, deque[float]] = {}
        self._seen_points: dict[str, set[tuple[float, float]]] = {}
        self._checkboxes: dict[str, QCheckBox] = {}
        self._curves: dict[str, pg.PlotDataItem] = {}
        self._fit_curves: dict[str, pg.PlotDataItem] = {}

        # Phase 33A: Scientific Graph Core — crosshair/coordinate readout
        # (бір plot widget-ке бір PlotCrosshair, single режимде кілт
        # "__single__", stacked-те curve key), latest-point маркерлері
        # (тек НАҚТЫ қосылған нүктелерге, _try_add_point() арқылы —
        # ешбір fake/интерполяцияланған дерек ЕШҚАШАН қосылмайды).
        self._crosshairs: dict[str, PlotCrosshair] = {}
        self._latest_markers: dict[str, pg.ScatterPlotItem] = {}
        self._mouse_mode = pg.ViewBox.PanMode

        # Phase 33B: аралық талдау — ``pg.LinearRegionItem`` бір plot
        # widget-ке бір дана (single режимде "__single__" кілті, stacked
        # режимде curve key — crosshair-мен БІРДЕЙ конвенция). Барлық
        # региондардың арасында БІР логикалық [t1, t2] аралығы болуы
        # тиіс (§3) — ``_syncing_region`` guard flag рекурсивті сигнал
        # циклін болдырмайды.
        self._region_items: dict[str, pg.LinearRegionItem] = {}
        self._region_enabled = False
        self._syncing_region = False
        # pg.LinearRegionItem values=(0,1) әдепкі мәнімен құрылады (нақты
        # (0,0) емес!), сондықтан "бастапқы күй ме" деген сұрақты магиялық
        # мән бойынша емес, осы жалаушамен шешеміз — алғашқы қосу кезінде
        # әрқашан көрінетін ауқымнан (§2) инициализацияланады.
        self._region_positions_initialized = False
        # Регрессия "Барлық нүктелер"/"Таңдалған аралық" scope — тек
        # GraphAnalysisPanel-дегі toggle арқылы өзгереді, әдепкі бойынша
        # ЕСКІ мінез-құлық (барлық нүктелер) сақталады.
        self._region_use_only_selection = False
        self._latest_regression_result: RegressionResult | None = None
        # §16: соңғы есептелген аралық қорытындысы — тек экспорт
        # батырмасы басылғанда файлға жазылады (ешбір автоматты
        # экспорт/side-effect ЖОҚ).
        self._last_region_summary: RegionAnalysisSummary | None = None
        # ExperimentDefinition.graph_derived_analysis-тен келеді (мыс.
        # "power_energy") — эксперимент ID-ге ЕШБІР тәуелділік ЖОҚ, тек
        # осы жалпы config мәні.
        self._derived_analysis: str = ""
        # Phase 34 §3/§6/§11: уақыттық арналардың rate-of-change (dY/dt)
        # конфигурациясы — тек region таңдалғанда есептеледі, бос tuple
        # болса ешбір жол көрсетілмейді (әдепкі, ескі мінез-құлық).
        self._rate_of_change: tuple[RateOfChangeConfig, ...] = ()
        # Devices-ready күйі (MeasurementWorkspace.set_devices_ready()
        # арқылы) — тек "деректер жоқ" хабарламасының қай нұсқасы
        # көрінетінін таңдайды (§14), ешбір дерек/есептеуге қатысы жоқ.
        self._devices_ready = False

        self._stacked = False
        self._stacked_titles: dict[str, str] = {}
        self._stacked_y_labels: dict[str, str] = {}
        self._stacked_plot_widgets: dict[str, pg.PlotWidget] = {}

        self._connect_points = True
        self._show_fit = False
        self._x_label_override: str | None = None
        self._y_label_override: str | None = None
        self._title: str | None = None
        # Phase 34 §10: "Нәтижені көшіру" қорытындысының тақырып жолы
        # (мыс. "Тізбек бөлігі үшін кернеудің ток күшіне тәуелділігін
        # зерттеу") — ExperimentDefinition.title-ден, graph_title
        # (ось сипаттамасы) МЕН БӨЛЕК ұғым.
        self._experiment_title: str | None = None
        self._dedup_x_tol = 0.0
        self._dedup_y_tol = 0.0
        self._fit_result_prefix = "slope"
        self._fit_unit: str | None = None
        self._fit_x_symbol = "X"
        self._fit_y_symbol = "Y"
        self._fit_display_name: str | None = None

        self._capture_mode = False
        self._capture_sample_count = 10
        self._capture_x_tol = 0.0
        self._capture_y_tol = 0.0
        self._capture_running = False
        self._capture_samples: deque[tuple[float, float]] = deque(
            maxlen=self._capture_sample_count
        )

        self._capture_button = QPushButton("+ Нүктені сақтау", self)
        self._capture_button.clicked.connect(self._on_capture_clicked)
        self._capture_button.setVisible(False)

        self._fit_toggle_checkbox = QCheckBox("Fit", self)
        self._fit_toggle_checkbox.setChecked(True)
        self._fit_toggle_checkbox.toggled.connect(self._on_fit_toggle_toggled)
        self._fit_toggle_checkbox.setVisible(False)

        self._clear_button = QPushButton(" Тазалау", self)
        self._clear_button.setIcon(_load_toolbar_icon("ic_fluent_delete_24_regular.svg", current_theme()))
        self._clear_button.setIconSize(QSize(_TOOLBAR_ICON_PX, _TOOLBAR_ICON_PX))
        self._clear_button.clicked.connect(self.clear)

        self._auto_scale_checkbox = QCheckBox("Автоауқым", self)
        self._auto_scale_checkbox.setChecked(self._default_auto_scale)
        self._auto_scale_checkbox.setToolTip(
            "Автомасштаб — жаңа өлшеулерге сай ауқымды автоматты жаңартады"
        )
        self._auto_scale_checkbox.toggled.connect(self._on_auto_scale_toggled)

        # Phase 33A §13: компакт ғылыми toolbar — жаңа батырмалар тек
        # icon (мәтінсіз), толық түсіндірме тек tooltip-те (§13-дегі
        # нақты мысалдар: "Автомасштаб"/"Масштабтау"/"Жылжыту"/"Көріністі
        # қалпына келтіру"/"Графикті үлкейту" — БАТЫРМА МӘТІНІ ЕМЕС,
        # tooltip мәтіні ретінде қолданылады). Толық сөзді батырма
        # мәтіні graph_card-тың минималды енін ұлғайтып, graph:table
        # splitter арақатынасын бұзатыны эмпирикалық түрде табылды
        # (pytest: 65:35 күтілген орнына 92:8 болып шықты).
        self._zoom_reset_button = QPushButton("", self)
        self._zoom_reset_button.setIcon(_load_toolbar_icon("ic_fluent_arrow_reset_24_regular.svg", current_theme()))
        self._zoom_reset_button.setIconSize(QSize(_TOOLBAR_ICON_PX, _TOOLBAR_ICON_PX))
        self._zoom_reset_button.setProperty("variant", "icon")
        self._zoom_reset_button.setToolTip("Көріністі қалпына келтіру")
        self._zoom_reset_button.clicked.connect(self._on_zoom_reset_clicked)

        # §8/§9: Zoom/Pan interaction режимі — pyqtgraph ViewBox-тың
        # НАҚТЫ RectMode/PanMode қолданады (жаңа/фрагиль custom math
        # ЖОҚ). Дөңгелек scroll екі режимде де ӘРҚАШАН масштабтайды
        # (pyqtgraph-тың кірістірілген мінез-құлқы).
        self._pan_mode_button = QPushButton("", self)
        self._pan_mode_button.setIcon(_load_toolbar_icon("ic_fluent_hand_left_24_regular.svg", current_theme()))
        self._pan_mode_button.setIconSize(QSize(_TOOLBAR_ICON_PX, _TOOLBAR_ICON_PX))
        self._pan_mode_button.setProperty("variant", "icon")
        self._pan_mode_button.setCheckable(True)
        self._pan_mode_button.setChecked(True)
        self._pan_mode_button.setToolTip(_MOUSE_MODE_TOOLTIPS["pan"])
        self._pan_mode_button.clicked.connect(self._on_pan_mode_clicked)

        self._zoom_mode_button = QPushButton("", self)
        self._zoom_mode_button.setIcon(_load_toolbar_icon("ic_fluent_zoom_in_24_regular.svg", current_theme()))
        self._zoom_mode_button.setIconSize(QSize(_TOOLBAR_ICON_PX, _TOOLBAR_ICON_PX))
        self._zoom_mode_button.setProperty("variant", "icon")
        self._zoom_mode_button.setCheckable(True)
        self._zoom_mode_button.setToolTip(_MOUSE_MODE_TOOLTIPS["zoom"])
        self._zoom_mode_button.clicked.connect(self._on_zoom_mode_clicked)

        self._mouse_mode_group = QButtonGroup(self)
        self._mouse_mode_group.setExclusive(True)
        self._mouse_mode_group.addButton(self._pan_mode_button)
        self._mouse_mode_group.addButton(self._zoom_mode_button)

        self._maximize_button = QPushButton("", self)
        self._maximize_button.setIcon(_load_toolbar_icon("ic_fluent_full_screen_maximize_24_regular.svg", current_theme()))
        self._maximize_button.setIconSize(QSize(_TOOLBAR_ICON_PX, _TOOLBAR_ICON_PX))
        self._maximize_button.setProperty("variant", "icon")
        self._maximize_button.setCheckable(True)
        self._maximize_button.setToolTip("Графикті үлкейту")
        self._maximize_button.toggled.connect(self._on_maximize_toggled)

        # Phase 33B §2: аралық талдау режимі — icon-only (§13 паттернімен
        # бірдей: компакт toolbar, толық сөз graph:table арақатынасын
        # бұзатыны Phase 33A-да эмпирикалық түрде табылған).
        # Phase 9: "Select Object" кандидаты РЕАЛ 12px toolbar
        # контекстінде (жақыннан скриншот) тексерілді — бұрыштық
        # dashed-белгілер осы өлшемде ӘЛІ ДЕ ажыратылады, "таңдауға
        # болатын шектелген аймақ" мағынасы сақталады (Phase 8-де
        # "recommended, imperfect" деп бағаланған дәл сол қорытынды
        # растады) — сондықтан интеграцияланды.
        self._region_button = QPushButton("", self)
        self._region_button.setIcon(_load_toolbar_icon("ic_fluent_select_object_24_regular.svg", current_theme()))
        self._region_button.setIconSize(QSize(_TOOLBAR_ICON_PX, _TOOLBAR_ICON_PX))
        self._region_button.setProperty("variant", "icon")
        self._region_button.setCheckable(True)
        self._region_button.setToolTip(_REGION_BUTTON_TOOLTIP)
        self._region_button.toggled.connect(self._on_region_toggled)

        # Phase 34 §1: A/B екі нүктелік Δ өлшеу құралы. Region-мен ("↔")
        # QButtonGroup-та ЕМЕС (exclusive group өз жалғыз checked мүшесін
        # қайта басқанда uncheck етпейді) — оның орнына _maximize_button
        # тәрізді тәуелсіз checkable батырма, әр toggled handler біреуін
        # өшіреді (_on_delta_toggled/_on_region_toggled).
        # Phase 9: "Arrow Between Down" кандидаты РЕАЛ 12px toolbar
        # контекстінде тексерілді (§ есеп) — жақыннан суретке түсіргенде
        # ол "сұрыптау/туралау" иконкасына оңай шатастырылатыны анықталды,
        # әрі ескі "A⟷B" мәтіні берген НАҚТЫ "A және B нүктелерінің
        # арасы" мағынасын жоғалтады (әріптер жоқ). Сондықтан ӘДЕЙІ
        # интеграцияланбай, ескі мәтін сақталды — форс-мэтч жасалмады.
        self._delta_button = QPushButton("A⟷B", self)
        self._delta_button.setCheckable(True)
        self._delta_button.setToolTip(_DELTA_BUTTON_TOOLTIP)
        self._delta_button.toggled.connect(self._on_delta_toggled)
        self._delta_button.setVisible(False)

        # Phase 34 §6: residual toggle — тек show_fit=True кезінде көрінеді.
        self._residual_toggle_button = QPushButton("Δres", self)
        self._residual_toggle_button.setCheckable(True)
        self._residual_toggle_button.setToolTip(_RESIDUAL_BUTTON_TOOLTIP)
        self._residual_toggle_button.toggled.connect(self._on_residual_toggle_toggled)
        self._residual_toggle_button.setVisible(False)

        # Phase 34 §9: snapshot экспорты (PNG/SVG).
        self._image_export_button = QPushButton("", self)
        self._image_export_button.setIcon(_load_toolbar_icon("ic_fluent_arrow_export_24_regular.svg", current_theme()))
        self._image_export_button.setIconSize(QSize(_TOOLBAR_ICON_PX, _TOOLBAR_ICON_PX))
        self._image_export_button.setProperty("variant", "icon")
        self._image_export_button.setToolTip(_IMAGE_EXPORT_TOOLTIP)
        self._image_export_button.clicked.connect(self._on_image_export_clicked)

        # Phase 34 §10: жай мәтін қорытындысын clipboard-қа көшіру.
        self._copy_summary_button = QPushButton("", self)
        self._copy_summary_button.setIcon(_load_toolbar_icon("ic_fluent_copy_24_regular.svg", current_theme()))
        self._copy_summary_button.setIconSize(QSize(_TOOLBAR_ICON_PX, _TOOLBAR_ICON_PX))
        self._copy_summary_button.setProperty("variant", "icon")
        self._copy_summary_button.setToolTip(_COPY_SUMMARY_TOOLTIP)
        self._copy_summary_button.clicked.connect(self._on_copy_summary_clicked)

        # §12: "press restore / Esc". WidgetWithChildrenShortcut — график
        # немесе оның кез келген ішкі виджеті фокуста болса іске қосылады.
        self._escape_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self._escape_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._escape_shortcut.activated.connect(self._on_escape_pressed)

        self._checkbox_layout = QHBoxLayout()

        toolbar = QHBoxLayout()
        toolbar.addWidget(self._capture_button)
        toolbar.addWidget(self._fit_toggle_checkbox)
        toolbar.addWidget(self._residual_toggle_button)
        toolbar.addLayout(self._checkbox_layout)
        toolbar.addWidget(self._clear_button)
        toolbar.addWidget(self._auto_scale_checkbox)
        toolbar.addWidget(self._pan_mode_button)
        toolbar.addWidget(self._zoom_mode_button)
        toolbar.addWidget(self._zoom_reset_button)
        toolbar.addWidget(self._region_button)
        toolbar.addWidget(self._delta_button)
        toolbar.addWidget(self._image_export_button)
        toolbar.addWidget(self._copy_summary_button)
        toolbar.addStretch(1)
        toolbar.addWidget(self._maximize_button)

        self._hint_label = QLabel(_CAPTURE_HINT_TEXT, self)
        self._hint_label.setWordWrap(True)
        self._hint_label.setVisible(False)

        # Phase 32.1: жалпы (capture_mode-нан тәуелсіз) "деректер әлі
        # жоқ" хабарламасы — hardware қосылмаған/әлі өлшеу басталмаған
        # кезде graph card толық көрінеді (осьтер/тор/toolbar), тек осы
        # жеңіл ескерту үстеледі. Бірінші нақты нүкте келгенде автоматты
        # жасырылады (_update_empty_state_visibility()).
        self._empty_state_label = QLabel(_EMPTY_STATE_NO_DEVICES_TEXT, self)
        self._empty_state_label.setWordWrap(True)
        self._empty_state_label.setProperty("role", "secondary")
        self._empty_state_label.setVisible(False)

        self._fit_panel = self._build_fit_panel()
        self._fit_panel.setVisible(False)

        # Phase 33B §5: region-режимі қосылмаған кезде мүлде орын
        # алмайды (hidden widget — Phase 32-де расталған Qt мінез-құлқы),
        # тек "↔" батырмасы қосылғанда пайда болады.
        self._analysis_panel = GraphAnalysisPanel(self)
        self._analysis_panel.setVisible(False)
        self._analysis_panel.regression_scope_changed.connect(
            self._on_regression_scope_changed
        )
        self._analysis_panel.export_requested.connect(self._on_export_analysis_clicked)

        # Phase 34 §1: A/B Δ өлшеу нәтиже панелі — _fit_panel-мен бірдей
        # персистентті lifecycle (ЕШҚАШАН _build_plot_widget()-те
        # тазаланбайды/қайта құрылмайды).
        self._delta_panel = self._build_delta_panel()
        self._delta_panel.setVisible(False)
        # A/B cursor күйі: (resolved_x, {curve_key: y_value}) немесе әлі
        # орнатылмаса None. resolved_x/values_at_x — crosshair-дегі
        # _curve_data_snapshot()/nearest_index() ЖОЛЫМЕН табылған, НАҚТЫ
        # сақталған үлгіден (ешбір интерполяция ЖОҚ).
        self._delta_cursor_a: tuple[float, dict[str, float]] | None = None
        self._delta_cursor_b: tuple[float, dict[str, float]] | None = None
        self._delta_measurement_enabled = False
        # curve_key -> {"A"/"B": marker} — жеке нүкте маркерлері.
        self._delta_markers: dict[str, dict[str, pg.ScatterPlotItem]] = {}
        # widget_key ("__single__" немесе stacked curve key) -> {"A"/"B": item}.
        self._delta_widget_vlines: dict[str, dict[str, pg.InfiniteLine]] = {}
        self._delta_widget_labels: dict[str, dict[str, pg.TextItem]] = {}
        self._delta_click_connections: list[tuple[object, object]] = []
        # Phase 34 §9: экспорт алдында уақытша жасырылған overlay-лардың
        # (region/A-B) қалпына келтіру үшін сақталған күйі.
        self._overlay_visibility_before_export: dict[str, bool] = {}

        # Phase 34 §6: residual plot — тек show_fit=True режимде мағыналы,
        # _fit_panel-мен бірдей персистентті lifecycle.
        self._residual_plot_widget = self._build_residual_plot_widget()
        self._residual_plot_widget.setVisible(False)
        self._residual_curve = self._residual_plot_widget.plot(
            [], [], pen=None, symbol="o", symbolSize=_SCATTER_SYMBOL_SIZE, symbolBrush=(90, 90, 90)
        )
        self._residual_zero_line = pg.InfiniteLine(angle=0, pos=0, pen=pg.mkPen((150, 150, 150), width=1))
        self._residual_plot_widget.addItem(self._residual_zero_line)
        self._residual_insufficient_label = QLabel(_RESIDUAL_INSUFFICIENT_TEXT, self)
        self._residual_insufficient_label.setVisible(False)

        self._plot_container_layout = QVBoxLayout()
        # Phase 5 (Graph Area Optimization): 6px әдепкі spacing екі
        # stacked subplot арасында ЖӘНЕ subplot пен empty-state
        # хабарламасы арасында ысыраптал — 1366×768-де екі графикті
        # scroll-сыз сыйдыру үшін 4px-ке дейін ықшамдалды (тек осы
        # контейнердің ІШІНДЕГІ spacing, plot widget-тердің өзіне
        # тимейді).
        self._plot_container_layout.setSpacing(4)
        self._plot_container_layout.addWidget(self._hint_label)
        self._plot_container_layout.addWidget(self._empty_state_label)
        self._plot_container_layout.addWidget(self._fit_panel)
        self._plot_container_layout.addWidget(self._delta_panel)
        self._plot_container_layout.addWidget(self._analysis_panel)
        self._plot_widget: pg.PlotWidget | None = None
        self._plot_container_layout.addWidget(self._residual_insufficient_label)
        self._plot_container_layout.addWidget(self._residual_plot_widget)

        layout = QVBoxLayout(self)
        # Phase 5 (Graph Area Optimization): бұрынғы әдепкі 9px margin/
        # 6px spacing (toolbar мен plot аймағы арасында) — тек осы
        # виджеттің ІШКІ padding-і, "Top header"/"Measurement cards"/
        # "Action buttons" секцияларына тимейді, тек графикке қосымша
        # тік орын босатады.
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        layout.addLayout(toolbar)
        layout.addLayout(self._plot_container_layout, 1)

        self._build_plot_widget()

    def refresh_theme_icons(self) -> None:
        """Тема ауысқанда toolbar иконкаларының fill түсін жаңартады."""
        theme = current_theme()
        _load_toolbar_icon.cache_clear()
        icons = (
            (self._clear_button, "ic_fluent_delete_24_regular.svg"),
            (self._zoom_reset_button, "ic_fluent_arrow_reset_24_regular.svg"),
            (self._pan_mode_button, "ic_fluent_hand_left_24_regular.svg"),
            (self._zoom_mode_button, "ic_fluent_zoom_in_24_regular.svg"),
            (self._maximize_button, "ic_fluent_full_screen_maximize_24_regular.svg"),
            (self._region_button, "ic_fluent_select_object_24_regular.svg"),
            (self._image_export_button, "ic_fluent_arrow_export_24_regular.svg"),
            (self._copy_summary_button, "ic_fluent_copy_24_regular.svg"),
        )
        for button, filename in icons:
            button.setIcon(_load_toolbar_icon(filename, theme))

    def apply_theme(self) -> None:
        """Қолданыстағы PlotWidget фон/ось түстерін ағымдағы темаға сай жаңартады."""
        background = theme_color("COLOR_GRAPH_BACKGROUND")
        foreground = theme_color("COLOR_GRAPH_AXIS")
        plots = list(self._all_plot_widgets())
        plots.append(self._residual_plot_widget)
        for plot in plots:
            plot.setBackground(background)
            for axis_name in ("bottom", "left", "right", "top"):
                axis = plot.getAxis(axis_name)
                axis.setPen(pg.mkPen(foreground))
                axis.setTextPen(foreground)
            try:
                plot.getPlotItem().titleLabel.setColor(foreground)
            except Exception:
                pass
        self.refresh_theme_icons()

    # ---- Public API -----------------------------------------------------

    def configure_channels(
        self,
        channels: tuple[SensorChannel, ...],
        x_channel: str | None = None,
        y_channels: tuple[str, ...] | None = None,
        connect_points: bool = True,
        show_fit: bool = False,
        x_label: str | None = None,
        y_label: str | None = None,
        title: str | None = None,
        dedup_x_tolerance: float = 0.0,
        dedup_y_tolerance: float = 0.0,
        fit_result_prefix: str = "slope",
        fit_unit: str | None = None,
        fit_display_name: str | None = None,
        capture_mode: bool = False,
        capture_sample_count: int = 10,
        capture_x_tolerance: float = 0.0,
        capture_y_tolerance: float = 0.0,
        fit_x_symbol: str = "X",
        fit_y_symbol: str = "Y",
        stacked: bool = False,
        stacked_titles: dict[str, str] | None = None,
        stacked_y_labels: dict[str, str] | None = None,
        derived_analysis: str = "",
        allow_delta_measurement: bool = False,
        rate_of_change: tuple[RateOfChangeConfig, ...] = (),
        experiment_title: str | None = None,
    ) -> None:
        """Графикті жаңа тәжірибеге бейімдейді.

        ``channels`` — қолжетімді арналардың label/unit metadata-сы (map
        ретінде қолданылады). ``y_channels`` берілсе, тек сол кілттер
        қисық ретінде салынады; берілмесе, ``channels``-тегі барлығы
        қисық болады. ``x_channel`` берілсе X-Y режимі, әйтпесе (``None``)
        уақыттық режим қолданылады. Ескі қисықтар/чекбокстар мен деректер
        толық тазаланып, жаңасымен ауыстырылады.

        Қалған параметрлер (әдепкісі — бұрынғы мінез-құлықты сақтайды):
        ``connect_points=False`` — нүктелерді сызықпен қоспай, scatter
        (pen=None, symbol='o') ретінде салады (X-Y режимде мағыналы).
        ``show_fit=True`` — әр қисық үшін сызықтық fit (numpy.polyfit)
        есептеп, бөлек fit panel-де ("Сызықтық аппроксимация") нәтиже
        көрсетеді. ``x_label``/``y_label`` — ось атауын
        ``channel.display_name`` орнына осымен ауыстырады (unit
        өзгеріссіз, ``channel.unit``-тен). ``title`` — plot тақырыбы.
        ``dedup_x_tolerance``/``dedup_y_tolerance`` — осы toleranstарынан
        жақын келетін X-Y нүктелерді (тек graph презентация қабатында,
        Measurement/session/table тимелместен) қайталанбас үшін сүзеді
        (0.0 — сүзу өшірулі). ``fit_result_prefix``/``fit_unit`` — fit
        slope-ынің атауы/бірлігі (мыс. "R"/"Ω"). ``fit_x_symbol``/
        ``fit_y_symbol`` — fit теңдеуіндегі айнымалы әріптер (мыс. "I"/"U").

        ``capture_mode=True`` — raw Measurement ағыны графикке ТІКЕЛЕЙ
        түспейді, тек ``capture_sample_count`` үлгілік rolling buffer-ге
        жиналады; график тек "Нүктені сақтау" батырмасы арқылы, буфер
        ``capture_x_tolerance``/``capture_y_tolerance`` ішінде тұрақты
        болғанда ғана, орташа мәннен бір нүкте алады.

        ``stacked=True`` (тек уақыттық режимде, ``show_fit``/``capture_mode``-
        сыз мағыналы) — әр ``y_channels`` кілті үшін БӨЛЕК ``PlotWidget``
        салады (синхрондалған X осімен, ``PlotItem.setXLink()`` арқылы),
        әртүрлі бірлік/диапазонды шамаларды (мыс. кернеу мен ток) бір
        Y scale-ге қыспау үшін. ``stacked_titles``/``stacked_y_labels`` —
        әр кілт үшін жеке тақырып/Y-ось мәтіні (map, key -> text).

        ``derived_analysis`` (Phase 33B, §10) — эксперимент ID-ге ЕШБІР
        тәуелділік ЖОҚ, тек жалпы config мәні (мыс.
        ``DERIVED_ANALYSIS_POWER_ENERGY``): аралық талдау панелінде
        қосымша туынды шамалар (P_орта/P_макс/Жұмыс) көрсетуді
        белгілейді. Бос жол — эксперименттің қосымша туынды талдауы жоқ.
        """
        self._channel_map = {channel.key: channel for channel in channels}
        self._curve_keys = tuple(y_channels) if y_channels else tuple(self._channel_map.keys())
        self._x_channel = x_channel
        self._connect_points = connect_points
        self._show_fit = show_fit
        self._x_label_override = x_label
        self._y_label_override = y_label
        self._title = title
        self._experiment_title = experiment_title
        self._dedup_x_tol = max(dedup_x_tolerance, 0.0)
        self._dedup_y_tol = max(dedup_y_tolerance, 0.0)
        self._fit_result_prefix = fit_result_prefix
        self._fit_unit = fit_unit
        self._fit_x_symbol = fit_x_symbol
        self._fit_y_symbol = fit_y_symbol
        self._fit_display_name = fit_display_name

        self._capture_mode = capture_mode
        self._capture_sample_count = max(int(capture_sample_count), 1)
        self._capture_x_tol = max(capture_x_tolerance, 0.0)
        self._capture_y_tol = max(capture_y_tolerance, 0.0)

        self._stacked = stacked
        self._stacked_titles = dict(stacked_titles) if stacked_titles else {}
        self._stacked_y_labels = dict(stacked_y_labels) if stacked_y_labels else {}
        self._derived_analysis = derived_analysis
        self._rate_of_change = rate_of_change

        self._delta_measurement_enabled = allow_delta_measurement
        self._delta_button.setVisible(allow_delta_measurement)

        self._clear_button.setText(" Графикті тазалау" if capture_mode else " Тазалау")
        self._capture_button.setVisible(capture_mode)
        self._fit_toggle_checkbox.setVisible(show_fit)
        self._fit_toggle_checkbox.setChecked(True)

        # Жаңа тәжірибе — ескі аралық/регрессия scope-ы мағынасыз,
        # ЖАҢА бастан басталады (region button ұстамай, тазаланған
        # __init__-тей). _build_plot_widget() region item-дерін де
        # жаңадан құрайды (_teardown_plot_widgets() ескілерін жояды).
        self._region_enabled = False
        self._region_use_only_selection = False
        self._region_positions_initialized = False
        self._region_button.setChecked(False)
        self._analysis_panel.clear()

        # Phase 34: жаңа тәжірибе — ескі A/B/residual toggle күйі де
        # мағынасыз, region-мен БІРДЕЙ "таза бастан" саясаты.
        self._delta_button.setChecked(False)
        self._delta_panel.setVisible(False)
        self._residual_toggle_button.setVisible(show_fit)
        self._residual_toggle_button.setChecked(False)
        self._residual_plot_widget.setVisible(False)
        self._residual_insufficient_label.setVisible(False)

        self._build_plot_widget()
        self._rebuild_checkboxes()
        self._reset_data()
        self._update_axis_labels()
        self._update_fit_panel_visibility()

    def set_capture_running(self, running: bool) -> None:
        """Тәжірибенің running күйіне сай "Нүктені сақтау" батырмасының
        қолжетімділігін жаңартады (``capture_mode=True`` кезінде ғана
        мағыналы — батырма running=True ЖӘНЕ буферде кем дегенде 1 raw
        үлгі болғанда ғана enabled болады).
        """
        self._capture_running = running
        self._update_capture_button_state()

    def set_devices_ready(self, ready: bool) -> None:
        """MeasurementWorkspace.set_ready()-тен келеді — "деректер жоқ"
        хабарламасының қай нұсқасы дұрыс екенін таңдайды (§14: 0/N
        кезде "құрылғыларды қосыңыз", ал N/N дайын бірақ әлі
        басталмаған кезде "«Бастау» батырмасын басыңыз"). Ешбір
        дерек/есептеуге қатысы жоқ, тек presentation.

        Phase 34.1 §3: ``ready=True`` — ЖАҢА құрылғы сессиясының
        басталуы (алғашқы Identify НЕМЕСЕ disconnect-тен кейінгі
        reconnect) дегенді білдіреді, сондықтан ескі region/A-B
        таңдауы (болған болса) толық тазаланады — ``_reset_data()``
        (Clear Data) region-ды ӘДЕЙІ САҚТАЙДЫ (бөлек тұжырымдама), бірақ
        "дайын, бірақ әлі басталмаған" таза күй region/A-B "елесінсіз"
        болуы тиіс.
        """
        self._devices_ready = ready
        self._update_empty_state_visibility()
        if ready:
            self._reset_interactive_overlays()

    def _reset_interactive_overlays(self) -> None:
        """Region селекциясы мен A/B cursor-ды ТОЛЫҚ тазалайды (позиция/
        checked күйімен қоса) — ``_reset_data()``-тан МҮЛДЕ бөлек
        (ол region-ды әдейі САҚТАЙДЫ, "Тазалау" батырмасының семантикасы
        осы). Бұл әдіс тек жаңа құрылғы сессиясы (``set_devices_ready
        (True)``) сияқты "нақты таза бастан" оқиғаларда шақырылады.
        """
        if self._region_button.isChecked():
            self._region_button.setChecked(False)
        self._region_positions_initialized = False
        if self._delta_button.isChecked():
            self._delta_button.setChecked(False)
        self._delta_cursor_a = None
        self._delta_cursor_b = None
        self._update_delta_visuals()
        self._update_delta_panel()
        for crosshair in self._crosshairs.values():
            crosshair.hide()

    def set_measurements(self, session: ExperimentSession) -> None:
        """``session`` ішіндегі барлық Measurement-терден графикті
        қайта құрады (мыс., session/құрылғы ауысқанда). Конфигурация
        (қисықтар/чекбокстар) өзгермейді — тек деректер қайта жүктеледі.
        """
        self.clear()
        for measurement in session.measurements:
            self.append_measurement(measurement)

    def append_measurement(self, measurement: Measurement) -> None:
        """Бір ``Measurement``-тен әр configured қисыққа жаңа нүкте
        қосады. Толық redraw жасалмайды — тек тиісті қисықтың деректері
        жаңартылады. X-Y режимінде X немесе Y мәні жоқ нүкте қосылмайды.

        ``capture_mode=True`` кезінде бұл әдіс графикке ЕШНӘРСЕ
        қоспайды — X/Y мәні тек ішкі rolling buffer-ге жазылады
        (``capture_point``-ке қараңыз), Measurement/session/table
        тимелмейді (олар бұл әдістен мүлде тәуелсіз жаңарады).
        Ешбір exception сыртқа шықпайды.
        """
        try:
            if self._start_time is None:
                self._start_time = measurement.timestamp

            for key in self._curve_keys:
                y_value = measurement.get_value(key)
                if y_value is None:
                    continue

                if self._x_channel is None:
                    x_value = measurement.get_value("time")
                    if x_value is None:
                        x_value = (measurement.timestamp - self._start_time).total_seconds()
                    self._try_add_point(key, x_value, y_value)
                    continue

                x_value = measurement.get_value(self._x_channel)
                if x_value is None:
                    continue

                if self._capture_mode:
                    self._capture_samples.append((x_value, y_value))
                    self._update_capture_button_state()
                    continue

                self._try_add_point(key, x_value, y_value)
        except Exception:  # қорғаныс: болжанбаған қате де UI-ды құлатпайды
            return

    def clear(self) -> None:
        """Графиктегі барлық қисықтардың деректерін тазалайды.
        Конфигурация (қисықтар/чекбокстар) сақталады. ``ExperimentSession``-ге
        тиіспейді — тек визуалды график (captured points-ты қоса) тазаланады.
        """
        self._reset_data()

    # ---- Ішкі логика -----------------------------------------------------

    def _try_add_point(self, key: str, x_value: float, y_value: float) -> bool:
        """Бір (X, Y) нүктесін ``key`` қисығына қосуға тырысады — dedup
        tolerance ішінде бұрын көрінген нүкте болса, ЕШНӘРСЕ өзгертпей
        False қайтарады. ``append_measurement()`` (automatic режим) мен
        ``_on_capture_clicked()`` (manual capture) екеуі де осы ортақ
        логиканы қолданады.
        """
        if self._dedup_x_tol > 0 or self._dedup_y_tol > 0:
            dedup_key = self._dedup_key(x_value, y_value)
            seen = self._seen_points.setdefault(key, set())
            if dedup_key in seen:
                return False
            seen.add(dedup_key)

        self._x_data[key].append(x_value)
        self._y_data[key].append(y_value)
        self._curves[key].setData(list(self._x_data[key]), list(self._y_data[key]))

        if self._show_fit:
            self._update_fit(key)

        # §7: latest-point маркері ТЕК осы жерде (нақты қосылған нүкте)
        # жаңартылады — capture_mode-дың raw буферіне (_capture_samples)
        # ЕШҚАШАН ілінбейді, себебі ол бөлек жол (append_measurement()-те
        # continue арқылы _try_add_point()-ке мүлде жетпейді).
        marker = self._latest_markers.get(key)
        if marker is not None:
            marker.setData([x_value], [y_value])

        # append_measurement() (automatic) МЕН _on_capture_clicked()
        # (manual capture) екеуі де осы жерге келеді — бірінші нақты
        # нүкте қосылған сәтте "деректер жоқ" хабарламасы автоматты
        # жоғалады. Ешбір fake нүкте жасалмайды — тек КӨРІНУ жаңарады.
        self._update_empty_state_visibility()

        return True

    def _dedup_key(self, x_value: float, y_value: float) -> tuple[float, float]:
        x_grid = round(x_value / self._dedup_x_tol) if self._dedup_x_tol > 0 else x_value
        y_grid = round(y_value / self._dedup_y_tol) if self._dedup_y_tol > 0 else y_value
        return (x_grid, y_grid)

    def _on_capture_clicked(self) -> None:
        """'Нүктені сақтау' батырмасы басылғанда: соңғы N raw үлгінің
        тұрақтылығын (spread <= tolerance) тексереді, тұрақты болса
        орташа мәнінен бір captured point қосады. Нәтиже/себеп
        ``capture_status`` сигналымен хабарланады. Ешбір exception
        сыртқа шықпайды.
        """
        try:
            if len(self._curve_keys) != 1 or not self._capture_samples:
                self.capture_status.emit(_STATUS_NO_DATA)
                return

            key = self._curve_keys[0]
            x_values = [x for x, _ in self._capture_samples]
            y_values = [y for _, y in self._capture_samples]

            x_spread = max(x_values) - min(x_values)
            y_spread = max(y_values) - min(y_values)
            if x_spread > self._capture_x_tol or y_spread > self._capture_y_tol:
                self.capture_status.emit(_STATUS_UNSTABLE)
                return

            x_avg = sum(x_values) / len(x_values)
            y_avg = sum(y_values) / len(y_values)

            if abs(x_avg) < _CAPTURE_EPSILON:
                self.capture_status.emit(_STATUS_VALUE_NEAR_ZERO)
                return

            if not self._try_add_point(key, x_avg, y_avg):
                self.capture_status.emit(_STATUS_DUPLICATE)
                return

            # Сәтті capture-дан кейін буфер тазаланады — келесі капчер
            # ескі (алдыңғы физикалық күйдің) үлгілерімен емес, пайдаланушы
            # рычагты өзгертіп, ЖАҢА тұрақты күйге жеткенде ғана рұқсат
            # етіледі (ескі+жаңа аралас буфер жалған "тұрақсыз" беруі мүмкін).
            self._capture_samples.clear()
            self._update_capture_button_state()
            self.capture_status.emit("")
            self._update_hint_visibility()
        except Exception:  # қорғаныс: болжанбаған қате де UI-ды құлатпайды
            return

    def _update_capture_button_state(self) -> None:
        self._capture_button.setEnabled(self._capture_running and bool(self._capture_samples))

    def _on_fit_toggle_toggled(self, _checked: bool) -> None:
        self._update_fit_panel_visibility()

    def _update_fit_panel_visibility(self) -> None:
        visible = self._show_fit and self._fit_toggle_checkbox.isChecked()
        self._fit_panel.setVisible(visible)
        for fit_curve in self._fit_curves.values():
            fit_curve.setVisible(visible)

    def _fit_data_for_key(self, key: str) -> tuple[list[float], list[float]]:
        """Fit-ке қолданылатын (x, y) деректерін қайтарады — әдепкі
        БАРЛЫҚ нүктелер (ескі мінез-құлық, ӨЗГЕРІССІЗ), ал region
        режимі ЖӘНЕ "Таңдалған аралық" scope-ы қосулы болса, тек
        [t1, t2] ішіндегі нүктелер (§8: "Do not silently change the
        dataset" — бұл таңдау ТЕК GraphAnalysisPanel-дегі анық radio
        button арқылы, ешқашан үнсіз емес).
        """
        x_values = list(self._x_data[key])
        y_values = list(self._y_data[key])

        if self._region_enabled and self._region_use_only_selection:
            item = self._region_items.get(key) or self._region_items.get("__single__")
            if item is not None:
                t1, t2 = item.getRegion()
                if t1 > t2:
                    t1, t2 = t2, t1
                mask = indices_in_range(x_values, t1, t2)
                x_values = [x for x, keep in zip(x_values, mask) if keep]
                y_values = [y for y, keep in zip(y_values, mask) if keep]

        return x_values, y_values

    def _update_fit(self, key: str) -> None:
        """Сызықтық fit (§7/§9: ``domain.services.graph_analysis.
        compute_linear_regression`` — бұрынғы inline ``numpy.polyfit``
        логикасының РЕФАКТОРЫ, ЕКІНШІ тәуелсіз регрессия архитектурасы
        ЕМЕС). Ескі "жеткіліксіз/деградацияланған" жағдайлардың
        БАРЛЫҒЫ (2-ден аз/бірдей X/``ss_tot<=0``) дәл ЕСКІ мінез-құлықпен
        (fit_curve тазаланады, "Кемінде 3 нүкте сақтаңыз") сақталады —
        Ohm's Law-дың нақты hardware-де тексерілген fit workflow-ы
        регресс болмайды.
        """
        fit_curve = self._fit_curves.get(key)
        if fit_curve is None:
            return

        x_values, y_values = self._fit_data_for_key(key)

        if len(x_values) < _MIN_FIT_POINTS or len(set(x_values)) < _MIN_FIT_POINTS:
            fit_curve.setData([], [])
            self._fit_body_label.setText(_FIT_INSUFFICIENT_TEXT)
            self._latest_regression_result = None
            self._update_regression_panel_if_visible()
            self._update_residual_display([], [], None)
            return

        result = compute_linear_regression(x_values, y_values)
        if not result.valid or result.r_squared is None:
            # r_squared=None (барлық Y бірдей, ss_tot<=0) — ЕСКІ кодта
            # да "жеткіліксіз" деп қаралатын, дәл сол мінез-құлық
            # сақталды (fit_curve тазаланады).
            fit_curve.setData([], [])
            self._fit_body_label.setText(_FIT_INSUFFICIENT_TEXT)
            self._latest_regression_result = None
            self._update_regression_panel_if_visible()
            self._update_residual_display([], [], None)
            return

        x_min, x_max = min(x_values), max(x_values)
        fit_curve.setData(
            [x_min, x_max],
            [result.slope * x_min + result.intercept, result.slope * x_max + result.intercept],
        )

        unit_suffix = f" {self._fit_unit}" if self._fit_unit else ""
        prefix = self._fit_result_prefix
        if self._fit_display_name:
            prefix = f"{self._fit_display_name} ({prefix})"
        lines = [
            f"{self._fit_y_symbol} = {result.slope:.3f}·{self._fit_x_symbol} + {result.intercept:.3f}",
            f"{prefix} = {result.slope:.3f}{unit_suffix}",
            f"R² = {result.r_squared:.3f}",
        ]
        if result.slope <= 0:
            lines.append(_FIT_WARNING_TEXT)
        self._fit_body_label.setText("\n".join(lines))
        self._latest_regression_result = result
        self._update_regression_panel_if_visible()
        self._update_residual_display(x_values, y_values, result)

    def _on_residual_toggle_toggled(self, _checked: bool) -> None:
        self._update_residual_visibility()

    def _update_residual_visibility(self) -> None:
        visible = self._show_fit and self._residual_toggle_button.isChecked()
        self._residual_plot_widget.setVisible(visible)
        if visible and len(self._curve_keys) == 1:
            self._update_fit(self._curve_keys[0])

    def _update_residual_display(
        self, x_values: list[float], y_values: list[float], result: RegressionResult | None
    ) -> None:
        """Phase 34 §6: fit-тің қалдықтарын (measured − fitted) ТЕК
        ``_update_fit()``-тің ӨЗІ есептеген (region-scope-ты ЕСКЕРЕТІН)
        деректерден жаңартады — жаңа recompute триггері ЖОҚ, сондықтан
        толық қымбат-есептеу тәртібін (§14 Performance) автоматты
        мұралайды.
        """
        if not self._show_fit:
            return
        if result is None or not result.valid or result.slope is None or result.intercept is None:
            self._residual_curve.setData([], [])
            self._residual_insufficient_label.setVisible(
                self._residual_toggle_button.isChecked()
            )
            return
        self._residual_insufficient_label.setVisible(False)
        residuals = compute_residuals(x_values, y_values, result.slope, result.intercept)
        self._residual_curve.setData(x_values, residuals)

    def _update_regression_panel_if_visible(self) -> None:
        """§9: аралық талдау панеліндегі регрессия секциясын (m/b/R²/
        RMSE/N) жаңартады — тек region режимі қосулы болғанда (панель
        көрінбесе, есептеу нәтижесі әлі де ``_latest_regression_result``-
        те сақталады, тек UI-ге шықпайды).
        """
        if not self._region_enabled:
            return
        result = self._latest_regression_result
        if result is None:
            result = RegressionResult(
                valid=False, slope=None, intercept=None, r_squared=None, rmse=None, n=0
            )
        self._analysis_panel.set_regression_result(
            result, self._fit_x_symbol, self._fit_y_symbol, self._fit_result_prefix, self._fit_unit
        )

    def _build_fit_panel(self) -> QFrame:
        panel = QFrame(self)
        panel.setFrameShape(QFrame.Shape.StyledPanel)

        self._fit_title_label = QLabel(_FIT_PANEL_TITLE, panel)
        title_font = self._fit_title_label.font()
        title_font.setBold(True)
        self._fit_title_label.setFont(title_font)

        self._fit_body_label = QLabel(_FIT_INSUFFICIENT_TEXT, panel)
        self._fit_body_label.setWordWrap(True)

        # kезeng 29: тек контейнер padding/spacing ықшамдалды (есептеу/
        # fit логикасына мүлде тимейді) — тар биіктікті терезелерде
        # (мыс. 1366×768) 3 жолды (U=..., R=..., R²=...) толық көрсету
        # үшін орын босату.
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(8, 4, 8, 4)
        panel_layout.setSpacing(2)
        panel_layout.addWidget(self._fit_title_label)
        panel_layout.addWidget(self._fit_body_label)
        return panel

    def _build_delta_panel(self) -> QFrame:
        panel = QFrame(self)
        panel.setFrameShape(QFrame.Shape.StyledPanel)

        title_label = QLabel(_DELTA_PANEL_TITLE, panel)
        title_font = title_label.font()
        title_font.setBold(True)
        title_label.setFont(title_font)

        self._delta_body_label = QLabel(_DELTA_EMPTY_TEXT, panel)
        self._delta_body_label.setWordWrap(True)

        self._delta_clear_button = QPushButton("✕", panel)
        self._delta_clear_button.setToolTip("A/B нүктелерін тазалау")
        self._delta_clear_button.clicked.connect(self._on_delta_clear_clicked)

        header_row = QHBoxLayout()
        header_row.addWidget(title_label)
        header_row.addStretch(1)
        header_row.addWidget(self._delta_clear_button)

        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(8, 4, 8, 4)
        panel_layout.setSpacing(2)
        panel_layout.addLayout(header_row)
        panel_layout.addWidget(self._delta_body_label)
        return panel

    def _build_residual_plot_widget(self) -> pg.PlotWidget:
        widget = pg.PlotWidget(self)
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        widget.setMaximumHeight(140)
        widget.showGrid(x=True, y=True, alpha=0.15)
        widget.getAxis("bottom").enableAutoSIPrefix(False)
        widget.getAxis("left").enableAutoSIPrefix(False)
        widget.setLabel("left", "Қалдық (measured − fit)")
        widget.setTitle("Қалдықтар (residuals)")
        return widget

    def _build_plot_widget(self) -> None:
        """Ескі plot widget(тер)ді (қажет болса) алмастырып, конфигурацияға
        сай не жалғыз ``PlotWidget`` (``_build_single_plot_widget``), не
        ``stacked=True`` кезінде бірнеше синхрондалған ``PlotWidget``
        (``_build_stacked_plot_widgets``) құрады. Ескі curve/legend
        күйінің қалдығы қалмауы үшін бүкіл виджет(тер) реконфигурация
        сайын жаңадан құрылады. ``_hint_label``/``_fit_panel`` персистентті
        виджеттер болғандықтан, жаңа plot widget(тер) әрдайым нақты
        индекске (hint үстінде, fit_panel астында) кірістіріледі.
        """
        self._teardown_plot_widgets()

        if self._stacked:
            self._build_stacked_plot_widgets()
        else:
            self._build_single_plot_widget()

    def _teardown_plot_widgets(self) -> None:
        # Phase 33A: ескі crosshair-дердің SignalProxy байланысын тазалау —
        # plot widget өзі deleteLater()-мен жойылады, бірақ proxy connection-ды
        # нақты disconnect ету дефенсивті/таза тәжірибе.
        for crosshair in self._crosshairs.values():
            crosshair.teardown()
        self._crosshairs = {}
        self._latest_markers = {}
        # Phase 33B: LinearRegionItem-дер plot widget-тің scene-іне
        # тиесілі — plot widget deleteLater() болғанда олар да жойылады,
        # тек Python-жақтағы сілтемелерді тазалаймыз.
        self._region_items = {}

        # Phase 34 §1: A/B click connection-дарды НАҚТЫ disconnect ету —
        # crosshair.teardown()-мен БІРДЕЙ себеп: жойылатын scene-ге
        # тіркелген қалдық қосылым GC/heap-corruption тәуекелін тудырады
        # (осы кодтың дәл осы себеппен crosshair-де бұрын түзетілгенін
        # қараңыз). Vline/label/marker өздері plot widget-пен бірге
        # жойылады — тек Python сілтемелерін тазалаймыз.
        for plot_widget, handler in self._delta_click_connections:
            try:
                plot_widget.scene().sigMouseClicked.disconnect(handler)
            except (RuntimeError, TypeError):
                pass
        self._delta_click_connections = []
        self._delta_markers = {}
        self._delta_widget_vlines = {}
        self._delta_widget_labels = {}

        if self._plot_widget is not None:
            self._plot_container_layout.removeWidget(self._plot_widget)
            # removeWidget() виджетті layout басқаруынан ғана алып тастайды,
            # жасырмайды — deleteLater() орындалғанша ескі виджет өз соңғы
            # geometry-сінде "елес" болып көрінеді (hide() болмаса).
            self._plot_widget.hide()
            self._plot_widget.deleteLater()
            self._plot_widget = None

        for plot_widget in self._stacked_plot_widgets.values():
            self._plot_container_layout.removeWidget(plot_widget)
            plot_widget.hide()
            plot_widget.deleteLater()
        self._stacked_plot_widgets = {}

    def _build_single_plot_widget(self) -> None:
        self._plot_widget = pg.PlotWidget(self)
        # Phase 32: нақты сызу canvas-ы (pyqtgraph PlotWidget) — екі
        # бағытта да Expanding, MIN/AVG/MAX header/toolbar-дан бөлек
        # барлық қалған GraphCard кеңістігін алу үшін НАҚТЫ көрсетілген.
        self._plot_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._plot_widget.setMinimumHeight(_MIN_SINGLE_PLOT_HEIGHT)
        # Жалғыз series болса (мыс. Ohm's Law), legend әдетте артық
        # clutter — тек 2+ қисық болғанда ҚОСЫЛАДЫ. Бірақ show_fit=True
        # кезінде (Ohm's Law) БІР curve-тің ӨЗІНДЕ екі бөлек визуалды
        # элемент бар (өлшенген нүктелер vs fit сызығы) — Phase 34 §8
        # осы жағдайда legend-ті НАҚТЫ талап етеді ("● Өлшенген деректер"
        # / "— Сызықтық fit").
        if len(self._curve_keys) > 1 or self._show_fit:
            self._plot_widget.addLegend()
        self._plot_widget.showGrid(x=True, y=True, alpha=0.15)
        self._plot_widget.enableAutoRange(enable=self._auto_scale_checkbox.isChecked())
        self._plot_widget.getViewBox().setDefaultPadding(_AUTORANGE_PADDING)
        self._plot_widget.setTitle(self._title)
        self._plot_container_layout.insertWidget(1, self._plot_widget, 1)
        self._setup_view_interactions(self._plot_widget)

        self._curves = {}
        self._fit_curves = {}
        for index, key in enumerate(self._curve_keys):
            channel = self._channel_map.get(key)
            label = channel.display_name if channel else key
            unit = channel.unit if channel else ""
            color = pg.intColor(index, hues=max(len(self._curve_keys), 1))
            # Phase 34 §8: show_fit=True + жалғыз curve (Ohm's Law) —
            # legend-де физикалық мағыналы атаулар ("Өлшенген деректер"/
            # "Сызықтық fit"), әйтпесе ескі "{label} ({unit})" атауы.
            single_fit_curve = self._show_fit and len(self._curve_keys) == 1
            name = "Өлшенген деректер" if single_fit_curve else (f"{label} ({unit})" if unit else label)

            if self._connect_points:
                pen = pg.mkPen(color=color, width=2)
                self._curves[key] = self._plot_widget.plot([], [], pen=pen, name=name)
            else:
                self._curves[key] = self._plot_widget.plot(
                    [],
                    [],
                    pen=None,
                    symbol="o",
                    symbolSize=_SCATTER_SYMBOL_SIZE,
                    symbolBrush=color,
                    symbolPen=color,
                    name=name,
                )

            if self._show_fit:
                fit_pen = pg.mkPen(color=_FIT_LINE_COLOR, width=2, style=Qt.PenStyle.DashLine)
                fit_name = "Сызықтық fit" if single_fit_curve else None
                self._fit_curves[key] = self._plot_widget.plot([], [], pen=fit_pen, name=fit_name)

            self._latest_markers[key] = self._build_latest_marker(self._plot_widget)

        # Phase 33A §4/§5/§6: барлық curve_keys БІР plot widget-те
        # (single режим) — бір ортақ PlotCrosshair, ешбір сыртқы
        # синхрондау қажет емес (тек ӨЗ curve-дерінің арасынан таңдайды).
        self._crosshairs["__single__"] = PlotCrosshair(
            self._plot_widget,
            get_curve_data=lambda: self._curve_data_snapshot(self._curve_keys),
            format_readout=self._format_readout,
        )
        self._region_items["__single__"] = self._build_region_item(
            self._plot_widget, "__single__"
        )
        self._build_delta_visuals(self._plot_widget, "__single__")
        self._connect_delta_click(self._plot_widget, "__single__")

        # Phase 34 §6: residual plot X-linking "ViewBox.linkView" weakref
        # арқылы сақталады — self._plot_widget әр configure_channels()
        # сайын deleteLater()-мен ауыстырылатындықтан, байланысты ӘР РЕТ
        # қайта орнату керек (бір реттік constructor-дегі setXLink жеткіліксіз).
        self._residual_plot_widget.getPlotItem().setXLink(self._plot_widget.getPlotItem())

    def _build_stacked_plot_widgets(self) -> None:
        """Әр ``_curve_keys`` кілті үшін бөлек ``PlotWidget`` — ортақ
        тема/autoscale padding V1/V2-мен бірдей, бірақ әрқайсысы ӨЗ Y
        scale-ін қолданады. X осьтер ``setXLink()`` арқылы синхрондалады
        (zoom/pan бірге жүреді). Fit/scatter/dedup stacked режимде
        қолданылмайды (validate_configuration()-де тыйым салынған).
        """
        self._curves = {}
        self._fit_curves = {}
        previous_plot_item = None

        for offset, key in enumerate(self._curve_keys):
            plot_widget = pg.PlotWidget(self)
            # Phase 32: әр stacked subplot та Expanding — барлық subplot
            # тең stretch=1 алады (insertWidget төменде), сондықтан
            # қолжетімді биіктік олардың арасында тең бөлінеді, ешқайсысына
            # фиксед height берілмейді.
            plot_widget.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )
            plot_widget.setMinimumHeight(_MIN_STACKED_PLOT_HEIGHT)
            plot_widget.showGrid(x=True, y=True, alpha=0.15)
            plot_widget.enableAutoRange(enable=self._auto_scale_checkbox.isChecked())
            plot_widget.getViewBox().setDefaultPadding(_AUTORANGE_PADDING)

            title = self._stacked_titles.get(key)
            if title:
                plot_widget.setTitle(title)

            color = pg.intColor(offset, hues=max(len(self._curve_keys), 1))
            pen = pg.mkPen(color=color, width=2)
            self._curves[key] = plot_widget.plot([], [], pen=pen)

            plot_item = plot_widget.getPlotItem()
            if previous_plot_item is not None:
                plot_item.setXLink(previous_plot_item)
            previous_plot_item = plot_item

            self._stacked_plot_widgets[key] = plot_widget
            self._plot_container_layout.insertWidget(1 + offset, plot_widget, 1)
            self._setup_view_interactions(plot_widget)
            self._latest_markers[key] = self._build_latest_marker(plot_widget)

            # Phase 33A §6: синхрондалған crosshair — бір subplot hover
            # етілгенде, ортақ X (setXLink() арқылы БҰРЫННАН синхрондалған
            # уақыт осіне сай) басқа subplot-тарда да ЕҢ ЖАҚЫН НАҚТЫ
            # үлгіні тауып көрсетеді (_on_stacked_crosshair_hover).
            # Эксперимент ID-ге ЕШБІР тәуелділік ЖОҚ — тек "stacked=True"
            # шартына негізделген, кез келген болашақ stacked graph тобына
            # автоматты қатысты.
            self._crosshairs[key] = PlotCrosshair(
                plot_widget,
                get_curve_data=lambda k=key: self._curve_data_snapshot((k,)),
                format_readout=self._format_readout,
                on_hover=lambda x, k=key: self._on_stacked_crosshair_hover(k, x),
            )
            # §3: әр subplot ӨЗ region item-ін алады, бірақ бір логикалық
            # [t1, t2] аралығын бөліседі — синхрондау _on_region_changed_
            # live()/_on_region_changed_finished() арқылы.
            self._region_items[key] = self._build_region_item(plot_widget, key)
            self._build_delta_visuals(plot_widget, key)
            self._connect_delta_click(plot_widget, key)

        # Residual plot тек XY show_fit режимінде мағыналы (stacked/fit
        # validate_configuration()-де бірге тыйым салынған), сондықтан
        # осында ЕШҚАШАН көрінбейді — бірақ ескі X-link өлі көрсеткішке
        # қалмас үшін нақты ажыратамыз.
        self._residual_plot_widget.getPlotItem().setXLink(None)

    def _rebuild_checkboxes(self) -> None:
        while self._checkbox_layout.count():
            item = self._checkbox_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        self._checkboxes = {}
        # Manual-capture графиктерде (жалғыз series) checkbox-тардың орнын
        # "+ Нүктені сақтау"/"Fit" toolbar-ы алмастырады — қосымша,
        # мағынасыз toggle болмасын. Stacked режимде де әр арна ӨЗ
        # subplot-ымен ажыратылады — checkbox қосымша/артық.
        if self._capture_mode or self._stacked:
            return

        for key in self._curve_keys:
            channel = self._channel_map.get(key)
            label = channel.display_name if channel else key
            checkbox = QCheckBox(label, self)
            checkbox.setChecked(True)
            checkbox.toggled.connect(
                lambda checked, channel_key=key: self._on_channel_toggled(channel_key, checked)
            )
            self._checkboxes[key] = checkbox
            self._checkbox_layout.addWidget(checkbox)

    def _reset_data(self) -> None:
        self._start_time = None
        self._x_data = {key: deque(maxlen=_MAX_POINTS) for key in self._curve_keys}
        self._y_data = {key: deque(maxlen=_MAX_POINTS) for key in self._curve_keys}
        self._seen_points = {key: set() for key in self._curve_keys}
        self._capture_samples = deque(maxlen=self._capture_sample_count)
        for curve in self._curves.values():
            curve.setData([], [])
        for fit_curve in self._fit_curves.values():
            fit_curve.setData([], [])
        for marker in self._latest_markers.values():
            marker.setData([], [])
        for crosshair in self._crosshairs.values():
            crosshair.hide()
        self._fit_body_label.setText(_FIT_INSUFFICIENT_TEXT)
        self._latest_regression_result = None
        self._update_capture_button_state()
        self._update_hint_visibility()
        self._update_empty_state_visibility()
        # Phase 34: ескі A/B cursor индекстері деректер тазаланғаннан
        # кейін мағынасыз (stale) — жаңа деректе қайта орналастырылуы
        # тиіс. Residual де толығымен бос fit-ке сай тазаланады.
        self._delta_cursor_a = None
        self._delta_cursor_b = None
        self._update_delta_visuals()
        self._update_delta_panel()
        self._residual_curve.setData([], [])
        # Clear Data region-ды ЖОЙМАЙДЫ/ӨШІРМЕЙДІ (§11: Reset View/region
        # toggle-дан бөлек тұжырымдама), тек оның статистикасы жаңа
        # (бос) деректі көрсетуі үшін қайта есептеледі.
        if self._region_enabled:
            self._recompute_region_analysis()

    def _update_hint_visibility(self) -> None:
        if not self._capture_mode or not self._curve_keys:
            self._hint_label.setVisible(False)
            return
        key = self._curve_keys[0]
        has_points = len(self._x_data.get(key, ())) > 0
        self._hint_label.setVisible(not has_points)

    def _update_empty_state_visibility(self) -> None:
        """Phase 32.1/33A: "деректер жоқ" хабарламасы — тек
        capture_mode=False графиктерде (capture_mode-да ЖОҒАРЫДАҒЫ
        ``_hint_label`` дәл осы рөлді атқарады, қосарлану болмас
        үшін). Мәтін ``_devices_ready``-ге қарай екі нұсқаның бірі
        (§14): 0/N — "құрылғыларды қосыңыз", ready бірақ басталмаған —
        "«Бастау» батырмасын басыңыз". Дерек болу-болмауы ғана
        экрандалады — hardware/readiness КҮЙІ set_devices_ready()
        арқылы сырттан беріледі, бұл жерде ЕШБІР жаңа тексеру жоқ.
        """
        if self._capture_mode or not self._curve_keys:
            self._empty_state_label.setVisible(False)
            return
        has_any_data = any(len(self._x_data.get(key, ())) > 0 for key in self._curve_keys)
        self._empty_state_label.setText(
            _EMPTY_STATE_DEVICES_READY_TEXT if self._devices_ready else _EMPTY_STATE_NO_DEVICES_TEXT
        )
        self._empty_state_label.setVisible(not has_any_data)

    def _on_channel_toggled(self, key: str, checked: bool) -> None:
        if key in self._curves:
            self._curves[key].setVisible(checked)
        if key in self._fit_curves:
            self._fit_curves[key].setVisible(checked)

    def _on_auto_scale_toggled(self, checked: bool) -> None:
        if self._plot_widget is not None:
            self._plot_widget.enableAutoRange(enable=checked)
        for plot_widget in self._stacked_plot_widgets.values():
            plot_widget.enableAutoRange(enable=checked)

    def _on_zoom_reset_clicked(self) -> None:
        """Ағымдағы деректерге сай view-ды бір рет орталықтандырады
        ("Автоауқым" checkbox күйін өзгертпейді — үздіксіз autorange
        емес, дәл қазіргі мезетте бір рет fit жасайтын әрекет). §11:
        Reset View — деректі/тәжірибе күйін ЕШҚАШАН тимейді, тек
        көрініс ауқымын қалпына келтіреді (Clear Data-дан МҮЛДЕ бөлек
        әрекет).
        """
        for plot_widget in self._all_plot_widgets():
            plot_widget.autoRange()

    # ---- Phase 33A: Zoom/Pan interaction режимі ---------------------------

    def _on_pan_mode_clicked(self) -> None:
        self._apply_mouse_mode(pg.ViewBox.PanMode)

    def _on_zoom_mode_clicked(self) -> None:
        self._apply_mouse_mode(pg.ViewBox.RectMode)

    def _apply_mouse_mode(self, mode) -> None:
        self._mouse_mode = mode
        for plot_widget in self._all_plot_widgets():
            plot_widget.getViewBox().setMouseMode(mode)

    def _all_plot_widgets(self) -> list[pg.PlotWidget]:
        if self._plot_widget is not None:
            return [self._plot_widget]
        return list(self._stacked_plot_widgets.values())

    def _setup_view_interactions(self, plot_widget: pg.PlotWidget) -> None:
        """Жаңа plot widget-ке ағымдағы mouse mode-ты қолданады және
        қолмен zoom/pan болғанда "Автоауқым"-ды автоматты өшіретін
        сигналды қосады (§8/§9/§10: "The user must never zoom in only
        for the next incoming sample to immediately reset the view").
        pyqtgraph-тың НАҚТЫ ``ViewBox.sigRangeChangedManually`` сигналы
        қолданылады — жаңа/фрагиль custom detection ЖОҚ.
        """
        view_box = plot_widget.getViewBox()
        view_box.setMouseMode(self._mouse_mode)
        view_box.sigRangeChangedManually.connect(self._on_range_changed_manually)

    def _on_range_changed_manually(self, *_args: object) -> None:
        if self._auto_scale_checkbox.isChecked():
            # setChecked(False) _on_auto_scale_toggled()-ті шақырады —
            # барлық plot widget-те enableAutoRange(False) қолданады.
            self._auto_scale_checkbox.setChecked(False)

    # ---- Phase 33A: Maximize/Restore ---------------------------------------

    def _on_maximize_toggled(self, checked: bool) -> None:
        self._maximize_button.setToolTip(
            "Қалыпты көрініске оралу (Esc)" if checked else "Графикті үлкейту"
        )
        # Layout/visibility ауыстыруы MeasurementWorkspace-тің жауапкершілігі
        # (splitter/metric cards/toolbar-ды сол иеленеді) — LiveGraphWidget
        # тек ниетті хабарлайды, дерек/zoom/crosshair күйіне ЕШБІР тиіспейді.
        self.maximize_toggled.emit(checked)

    def _on_escape_pressed(self) -> None:
        if self._maximize_button.isChecked():
            self._maximize_button.setChecked(False)

    # ---- Phase 33B: Region/interval analysis -------------------------------

    def _build_region_item(self, plot_widget: pg.PlotWidget, key: str) -> pg.LinearRegionItem:
        region = pg.LinearRegionItem(
            orientation="vertical",
            brush=pg.mkBrush(_REGION_BRUSH_COLOR),
            pen=pg.mkPen(_REGION_LINE_COLOR, width=1),
            movable=True,
        )
        region.setZValue(40)  # curves-тен ЖОҒАРЫ, бірақ crosshair(50)/marker(60)/readout(100)-тен ТӨМЕН
        region.setVisible(False)
        plot_widget.addItem(region, ignoreBounds=True)
        # sigRegionChanged — сүйреу кезінде ЖИІ (§17: тек арзан
        # синхрондау, статистика ЕСЕПТЕЛМЕЙДІ). sigRegionChangeFinished —
        # тышқан жіберілгенде БІР РЕТ (толық қымбат қайта есептеу).
        region.sigRegionChanged.connect(lambda item, k=key: self._on_region_changed_live(k, item))
        region.sigRegionChangeFinished.connect(
            lambda item, k=key: self._on_region_changed_finished(k, item)
        )
        return region

    def _on_region_toggled(self, checked: bool) -> None:
        # Phase 34 §1: Region мен A/B tool өзара EXCLUSIVE (QButtonGroup
        # ЕМЕС — сол жалғыз checked мүшесін қайта басқанда uncheck
        # етпейтіні расталды, сондықтан қолмен toggled connect).
        if checked and self._delta_button.isChecked():
            self._delta_button.setChecked(False)

        self._region_enabled = checked
        for item in self._region_items.values():
            item.setVisible(checked)

        if not checked:
            self._analysis_panel.setVisible(False)
            return

        if not self._region_items:
            return

        if not self._region_positions_initialized:
            # Алғашқы қосу — көрінетін X ауқымының орталық бөлігін
            # таңдаймыз (§2). Дерек ЕШҚАШАН ойдан шығарылмайды — тек
            # region item-дің позициясы, сызылған деректің ӨЗІ емес.
            # ЕСКЕРТУ: pg.LinearRegionItem values=(0,1) әдепкі мәнімен
            # құрылады, (0,0) ЕМЕС — сондықтан "region[0]==region[1]"
            # магиялық тексеруі әрқашан False болып, инициализация
            # ешқашан іске қосылмай қалатын (нақты bug) еді.
            self._initialize_region_from_view()
            self._region_positions_initialized = True
        self._recompute_region_analysis()

    def _initialize_region_from_view(self) -> None:
        plot_widgets = self._all_plot_widgets()
        if not plot_widgets:
            return
        (x_min, x_max), _y_range = plot_widgets[0].getViewBox().viewRange()
        span = x_max - x_min
        t1 = x_min + span * _DEFAULT_REGION_FRACTION[0]
        t2 = x_min + span * _DEFAULT_REGION_FRACTION[1]
        self._set_all_regions((t1, t2))

    def _set_all_regions(self, region: tuple[float, float]) -> None:
        self._syncing_region = True
        try:
            for item in self._region_items.values():
                item.setRegion(region)
        finally:
            self._syncing_region = False

    def _on_region_changed_live(self, source_key: str, item: pg.LinearRegionItem) -> None:
        """§3/§17: тек СИНХРОНДАУ (арзан ``setRegion()`` шақыруы) — ешбір
        статистика/регрессия осы жерде есептелмейді (сүйреу кезінде UI
        жауапты қалуы үшін). ``_syncing_region`` guard рекурсивті
        циклді болдырмайды (§3: "Avoid recursive signal loops").
        """
        if self._syncing_region or not self._region_enabled:
            return
        region = item.getRegion()
        self._syncing_region = True
        try:
            for key, other in self._region_items.items():
                if key != source_key:
                    other.setRegion(region)
        finally:
            self._syncing_region = False

    def _on_region_changed_finished(self, _source_key: str, _item: pg.LinearRegionItem) -> None:
        """Тышқан жіберілгенде БІР РЕТ шақырылады — толық (қымбат)
        статистика/регрессия/туынды талдау осы жерде қайта есептеледі
        (§17 Performance).
        """
        if self._region_enabled:
            self._recompute_region_analysis()

    def _region_bounds(self) -> tuple[float, float] | None:
        if not self._region_items:
            return None
        any_item = next(iter(self._region_items.values()))
        t1, t2 = any_item.getRegion()
        return (t1, t2) if t1 <= t2 else (t2, t1)

    def _recompute_region_analysis(self) -> None:
        bounds = self._region_bounds()
        if bounds is None:
            return
        t1, t2 = bounds

        self._analysis_panel.clear_channel_statistics()
        max_n = 0
        channel_summaries: list[ChannelAnalysisSummary] = []
        for key in self._curve_keys:
            y_values = list(self._y_data.get(key, ()))
            x_values = list(self._x_data.get(key, ()))
            mask = indices_in_range(x_values, t1, t2)
            selected_y = [value for value, keep in zip(y_values, mask) if keep]
            stats = compute_region_statistics(selected_y)
            max_n = max(max_n, stats.n)
            channel = self._channel_map.get(key) or SensorChannel(
                key=key, display_name=key, unit=""
            )
            self._analysis_panel.set_channel_statistics(channel, stats)
            channel_summaries.append(
                ChannelAnalysisSummary(
                    display_name=channel.display_name,
                    unit=channel.unit,
                    n=stats.n,
                    minimum=stats.minimum,
                    maximum=stats.maximum,
                    average=stats.average,
                    delta=stats.delta,
                    std_dev=stats.std_dev,
                    cv_percent=stats.coefficient_of_variation_percent,
                    sem=stats.standard_error_of_mean,
                )
            )

        self._analysis_panel.set_region_summary(t1, t2, f"N = {max_n}")

        can_fit = self._show_fit and len(self._curve_keys) == 1
        self._analysis_panel.set_regression_available(can_fit)
        if can_fit:
            self._update_fit(self._curve_keys[0])

        power_avg = power_max = energy = None
        if self._derived_analysis == DERIVED_ANALYSIS_POWER_ENERGY:
            power_avg, power_max, energy = self._update_power_energy_analysis(t1, t2)
        else:
            self._analysis_panel.hide_derived_section()

        self._update_rate_of_change_analysis(t1, t2)

        result = self._latest_regression_result if can_fit else None
        self._last_region_summary = RegionAnalysisSummary(
            t1=t1,
            t2=t2,
            channels=tuple(channel_summaries),
            regression_scope=(
                "Таңдалған аралық" if self._region_use_only_selection else "Барлық нүктелер"
            )
            if can_fit
            else None,
            regression_slope=result.slope if result else None,
            regression_intercept=result.intercept if result else None,
            regression_r_squared=result.r_squared if result else None,
            regression_rmse=result.rmse if result else None,
            regression_n=result.n if result else None,
            power_avg=power_avg,
            power_max=power_max,
            energy=energy,
        )

        self._analysis_panel.setVisible(True)

    def _on_export_analysis_clicked(self) -> None:
        """§16: raw Measurement экспортынан (CSVExporter/т.б., session-
        негізді) МҮЛДЕ БӨЛЕК, қосымша әрекет — тек ағымдағы region
        талдау снапшотын CSV-ге сақтайды. Раw дерек экспортын
        АЛМАСТЫРМАЙДЫ/тимейді.
        """
        if self._last_region_summary is None:
            return
        file_path, _selected_filter = QFileDialog.getSaveFileName(
            self, "Талдау қорытындысын сақтау", "region_analysis.csv", "CSV файлдары (*.csv)"
        )
        if not file_path:
            return
        RegionAnalysisExporter().export(self._last_region_summary, file_path)

    # ---- Phase 34 §9: snapshot (PNG/SVG) экспорты --------------------------

    def _on_image_export_clicked(self) -> None:
        """Ағымдағы графикті (тек plot аймағын — toolbar/fit panel/
        analysis panel ЕШҚАШАН кірмейді) PNG-ге (single/stacked) немесе
        SVG-ге (тек single-plot режимде — pyqtgraph-тың SVGExporter бір
        ``PlotItem``/scene-мен ғана жұмыс істейді, stacked-те бірнеше
        БӨЛЕК scene бар) сақтайды. Экспорт ешбір дерек/zoom/crosshair
        күйін мутацияламайды — тек A/B/region overlay-ды экспорт
        сәтінде уақытша жасырады (SVG/grab екеуі де көрінетін элементті
        scene-ге "пісіріп" қосады).
        """
        if self._plot_widget is None and not self._stacked_plot_widgets:
            return

        filters = "PNG суреттер (*.png)"
        if not self._stacked:
            filters += ";;SVG суреттер (*.svg)"
        file_path, selected_filter = QFileDialog.getSaveFileName(
            self, "Суретке сақтау", "graph.png", filters
        )
        if not file_path:
            return

        self._set_overlays_visible_for_export(False)
        try:
            if selected_filter.startswith("SVG") and not self._stacked and self._plot_widget is not None:
                exporter = pg_exporters.SVGExporter(self._plot_widget.getPlotItem())
                exporter.export(file_path)
            else:
                self._export_plot_as_png(file_path)
        except Exception:  # қорғаныс: диск/формат қатесі UI-ды құлатпайды
            self.capture_status.emit(_STATUS_IMAGE_EXPORT_FAILED)
        else:
            self.capture_status.emit(_STATUS_IMAGE_EXPORT_SAVED)
        finally:
            self._set_overlays_visible_for_export(True)

    def grab_plot_pixmap(self) -> QPixmap | None:
        """Ағымдағы графиктің (single немесе stacked) НАҚТЫ рендерленген
        суретін қайтарады — тек plot аймағы, toolbar/fit-panel/analysis-
        panel ЕШҚАШАН кірмейді. §9 image export ЖӘНЕ Phase 36 зертханалық
        есеп диалогы екеуі де осы БІР дереккөзді (grab-негізді, жаңа сызу
        логикасы ЖОҚ) пайдаланады — plot widget әлі құрылмаса (мыс.
        ``configure_channels()`` шақырылмаған) ``None`` қайтарады.
        """
        if not self._stacked:
            if self._plot_widget is None:
                return None
            return self._plot_widget.grab()

        # Stacked: pyqtgraph-тың бір scene-ге негізделген exporter-лары
        # бірнеше ТӘУЕЛСІЗ PlotWidget-ті бірге экспорттай алмайды —
        # әрқайсысын жеке grab() етіп, QPainter-мен вертикаль құрастырамыз
        # (reparent ЖОҚ, _plot_container_layout иелігіне тимейді).
        pixmaps = [widget.grab() for widget in self._stacked_plot_widgets.values()]
        if not pixmaps:
            return None
        width = max(pixmap.width() for pixmap in pixmaps)
        total_height = sum(pixmap.height() for pixmap in pixmaps)
        combined = QPixmap(width, total_height)
        combined.fill(Qt.GlobalColor.white)
        painter = QPainter(combined)
        try:
            y_offset = 0
            for pixmap in pixmaps:
                painter.drawPixmap(0, y_offset, pixmap)
                y_offset += pixmap.height()
        finally:
            painter.end()
        return combined

    def _export_plot_as_png(self, file_path: str) -> None:
        pixmap = self.grab_plot_pixmap()
        if pixmap is not None:
            pixmap.save(file_path, "PNG")

    def _set_overlays_visible_for_export(self, visible: bool) -> None:
        if not visible:
            self._overlay_visibility_before_export = {
                "region": self._region_enabled and self._region_button.isChecked(),
                "delta": self._delta_button.isChecked(),
            }
            for item in self._region_items.values():
                item.setVisible(False)
            self._update_delta_visuals_override(False)
            return

        state = self._overlay_visibility_before_export
        if state.get("region"):
            for item in self._region_items.values():
                item.setVisible(True)
        if state.get("delta"):
            self._update_delta_visuals()

    def _update_delta_visuals_override(self, _forced_hidden: bool) -> None:
        for vlines in self._delta_widget_vlines.values():
            for vline in vlines.values():
                vline.setVisible(False)
        for labels in self._delta_widget_labels.values():
            for label in labels.values():
                label.setVisible(False)
        for markers in self._delta_markers.values():
            for marker in markers.values():
                marker.setVisible(False)

    # ---- Phase 34 §10: "Нәтижені көшіру" -----------------------------------

    def _on_copy_summary_clicked(self) -> None:
        text = self._build_analysis_summary_text()
        if not text:
            return
        QApplication.clipboard().setText(text)

    def _build_analysis_summary_text(self) -> str:
        title = self._experiment_title or self._title or ""

        if self._region_enabled and self._last_region_summary is not None:
            return format_region_analysis_summary(
                title,
                self._last_region_summary,
                self._fit_x_symbol if self._show_fit else None,
                self._fit_y_symbol if self._show_fit else None,
                self._fit_result_prefix,
                self._fit_unit,
            )

        if self._show_fit and len(self._curve_keys) == 1:
            key = self._curve_keys[0]
            x_values, y_values = self._fit_data_for_key(key)
            result = self._latest_regression_result or RegressionResult(
                valid=False, slope=None, intercept=None, r_squared=None, rmse=None, n=len(x_values)
            )
            x_range = (min(x_values), max(x_values)) if x_values else None
            y_range = (min(y_values), max(y_values)) if y_values else None
            x_channel = self._channel_map.get(self._x_channel) if self._x_channel else None
            y_channel = self._channel_map.get(key)
            return format_fit_summary(
                title,
                len(x_values),
                self._fit_x_symbol,
                x_range,
                x_channel.unit if x_channel else "",
                self._fit_y_symbol,
                y_range,
                y_channel.unit if y_channel else "",
                self._fit_result_prefix,
                self._fit_unit,
                result,
            )

        return ""

    def _on_regression_scope_changed(self, use_region: bool) -> None:
        """§8: "Барлық нүктелер"/"Таңдалған аралық" — ЕШБІР жаңа
        dataset жасырын ауыстырылмайды, тек fit-ке қандай нүктелер
        кіретінін таңдайды (§8: "The UI must make it clear whether
        regression is... Do not silently change the dataset").
        """
        self._region_use_only_selection = use_region
        if self._show_fit and len(self._curve_keys) == 1:
            self._update_fit(self._curve_keys[0])

    def _update_power_energy_analysis(
        self, t1: float, t2: float
    ) -> tuple[float | None, float | None, float | None]:
        """§10/§11: P(t) — БҰРЫННАН graph_y_channels=("power",) арқылы
        сызылған нақты (t, P) жұптары (CalculationEngine есептеген,
        graph қабаты ЕШБІР жаңа P=U×I есептемейді). W=∫P dt тек осы
        НАҚТЫ сақталған үлгілердің үстінен, нақты timestamp-тармен
        (§10: "Do not invent evenly spaced timestamps"). ``(P_орта,
        P_макс, W)`` қайтарады — экспорт снапшотында да қайта
        пайдаланылады.
        """
        power_key = "power"
        x_values = list(self._x_data.get(power_key, ()))
        y_values = list(self._y_data.get(power_key, ()))

        if not x_values:
            self._analysis_panel.hide_derived_section()
            return None, None, None

        mask = indices_in_range(x_values, t1, t2)
        selected_x = [x for x, keep in zip(x_values, mask) if keep]
        selected_y = [y for y, keep in zip(y_values, mask) if keep]

        stats = compute_region_statistics(selected_y)
        energy = compute_trapezoidal_integral(selected_x, selected_y)
        self._analysis_panel.set_derived_power_energy(stats.average, stats.maximum, energy)
        return stats.average, stats.maximum, energy

    def _update_rate_of_change_analysis(self, t1: float, t2: float) -> None:
        """Phase 34 §3/§6/§11: configured уақыттық арналар үшін
        rate-of-change (dY/dt) — тек ТАҢДАЛҒАН аралықтағы сызықтық
        регрессияның slope-ынан (толық ағынды нүкте-нүктелеп
        дифференциалдамай, шу күшеймес үшін). Бос tuple болса — ешбір
        визуалды өзгеріс жоқ (analysis_panel.clear_rate_of_change()
        секцияны бос қалдырады).
        """
        self._analysis_panel.clear_rate_of_change()
        if not self._rate_of_change:
            return
        for config in self._rate_of_change:
            x_values = list(self._x_data.get(config.channel_key, ()))
            y_values = list(self._y_data.get(config.channel_key, ()))
            mask = indices_in_range(x_values, t1, t2)
            selected_x = [x for x, keep in zip(x_values, mask) if keep]
            selected_y = [y for y, keep in zip(y_values, mask) if keep]
            result = compute_linear_regression(selected_x, selected_y)
            self._analysis_panel.set_rate_of_change(
                config.symbol, config.display_name, config.unit, result
            )

    # ---- Phase 34: A/B two-point Δ measurement tool ------------------------

    def _plot_widget_for_key(self, key: str) -> pg.PlotWidget | None:
        if key == "__single__":
            return self._plot_widget
        return self._stacked_plot_widgets.get(key)

    def _build_delta_visuals(self, plot_widget: pg.PlotWidget, key: str) -> None:
        """Бір plot widget-ке (single режимде ЖАЛҒЫЗ, stacked-те әр
        subplot-қа) A/B cursor vline/label жұбын салады, ЖӘНЕ осы widget
        иеленетін curve key(тер)ге нүкте маркерін дайындайды (әзірге
        барлығы жасырын — тек _update_delta_visuals() көрсетеді).
        """
        vlines: dict[str, pg.InfiniteLine] = {}
        labels: dict[str, pg.TextItem] = {}
        for cursor_name, color in (("A", _DELTA_MARKER_COLOR_A), ("B", _DELTA_MARKER_COLOR_B)):
            vline = pg.InfiniteLine(
                angle=90,
                movable=False,
                pen=pg.mkPen(color=color, width=1, style=Qt.PenStyle.DashLine),
            )
            vline.setZValue(45)
            vline.setVisible(False)
            plot_widget.addItem(vline, ignoreBounds=True)
            vlines[cursor_name] = vline

            label = pg.TextItem(cursor_name, color=color)
            label.setZValue(65)
            label.setVisible(False)
            plot_widget.addItem(label, ignoreBounds=True)
            labels[cursor_name] = label

        self._delta_widget_vlines[key] = vlines
        self._delta_widget_labels[key] = labels

        hosted_curve_keys = self._curve_keys if key == "__single__" else (key,)
        for curve_key in hosted_curve_keys:
            markers = self._delta_markers.setdefault(curve_key, {})
            for cursor_name, color in (("A", _DELTA_MARKER_COLOR_A), ("B", _DELTA_MARKER_COLOR_B)):
                marker = pg.ScatterPlotItem(
                    size=_DELTA_MARKER_SIZE, brush=pg.mkBrush(color), pen=pg.mkPen("w", width=1.5)
                )
                marker.setZValue(62)
                marker.setVisible(False)
                plot_widget.addItem(marker)
                markers[cursor_name] = marker

    def _connect_delta_click(self, plot_widget: pg.PlotWidget, source_key: str) -> None:
        """A/B режимі белсенді кезде тышқан click-ін (hover-ден бөлек
        сигнал, ``sigMouseClicked``) НАҚТЫ сақталған үлгіге snap ету
        үшін тыңдайды. ``sigMouseMoved`` (crosshair) сияқты тікелей
        қосылады, throttling қажет емес (discrete user gesture, жиі
        firehose ЕМЕС).
        """
        handler = lambda event, k=source_key: self._on_delta_scene_clicked(event, k)
        plot_widget.scene().sigMouseClicked.connect(handler)
        self._delta_click_connections.append((plot_widget, handler))

    def _on_delta_scene_clicked(self, event, source_key: str) -> None:
        if not self._delta_measurement_enabled or not self._delta_button.isChecked():
            return
        try:
            if event.button() != Qt.MouseButton.LeftButton:
                return
        except Exception:
            pass
        plot_widget = self._plot_widget_for_key(source_key)
        if plot_widget is None:
            return
        if not plot_widget.sceneBoundingRect().contains(event.scenePos()):
            return
        view_box = plot_widget.getPlotItem().vb
        data_pos = view_box.mapSceneToView(event.scenePos())
        self._place_delta_cursor(data_pos.x())

    def _resolve_point_at_x(self, x_target: float) -> tuple[float, dict[str, float]] | None:
        """Crosshair-дегі ``_show_for_x()``-пен БІРДЕЙ логика: әр curve
        өз деректерінен ЕҢ ЖАҚЫН НАҚТЫ үлгіні (``nearest_index()``)
        табады — ешбір интерполяция ЖОҚ. Бос curve (-1 индекс) үнсіз
        өткізіп жіберіледі.
        """
        curve_data = self._curve_data_snapshot(self._curve_keys)
        values_at_x: dict[str, float] = {}
        resolved_x: float | None = None
        for key, (xs, ys) in curve_data.items():
            index = nearest_index(xs, x_target)
            if index == -1:
                continue
            values_at_x[key] = ys[index]
            if resolved_x is None:
                resolved_x = xs[index]
        if resolved_x is None:
            return None
        return resolved_x, values_at_x

    def _place_delta_cursor(self, x_target: float) -> None:
        resolved = self._resolve_point_at_x(x_target)
        if resolved is None:
            return
        if self._delta_cursor_a is None:
            self._delta_cursor_a = resolved
        elif self._delta_cursor_b is None:
            self._delta_cursor_b = resolved
        else:
            self._delta_cursor_a = resolved
            self._delta_cursor_b = None
        self._update_delta_visuals()
        self._update_delta_panel()

    def _on_delta_toggled(self, checked: bool) -> None:
        if checked and self._region_button.isChecked():
            self._region_button.setChecked(False)
        if checked:
            # Zoom (RectMode) кезінде stationary click drag-қа
            # реклассификацияланып, click мүлде ЖІБЕРІЛМЕУІ мүмкін —
            # A/B режимі әрдайым Pan mode-ты мәжбүрлейді. setChecked()
            # программалық түрде clicked сигналын ШЫҒАРМАЙДЫ, сондықтан
            # нақты mouse mode-ты да қолмен қолданамыз (тек батырманы
            # checked ету жеткіліксіз).
            self._pan_mode_button.setChecked(True)
            self._apply_mouse_mode(pg.ViewBox.PanMode)
        self._delta_panel.setVisible(checked)
        self._update_delta_visuals()

    def _on_delta_clear_clicked(self) -> None:
        self._delta_cursor_a = None
        self._delta_cursor_b = None
        self._update_delta_visuals()
        self._update_delta_panel()

    def _update_delta_visuals(self) -> None:
        tool_active = self._delta_button.isChecked()
        for widget_key, vlines in self._delta_widget_vlines.items():
            plot_widget = self._plot_widget_for_key(widget_key)
            labels = self._delta_widget_labels.get(widget_key, {})
            (_x_min, _x_max), (_y_min, y_max) = (
                plot_widget.getViewBox().viewRange() if plot_widget is not None else ((0, 1), (0, 1))
            )
            for cursor_name, cursor in (("A", self._delta_cursor_a), ("B", self._delta_cursor_b)):
                vline = vlines.get(cursor_name)
                label = labels.get(cursor_name)
                visible = tool_active and cursor is not None
                if vline is not None:
                    vline.setVisible(visible)
                if label is not None:
                    label.setVisible(visible)
                if visible and cursor is not None:
                    resolved_x, _values = cursor
                    vline.setPos(resolved_x)
                    label.setPos(resolved_x, y_max)

        for curve_key, markers in self._delta_markers.items():
            for cursor_name, cursor in (("A", self._delta_cursor_a), ("B", self._delta_cursor_b)):
                marker = markers.get(cursor_name)
                if marker is None:
                    continue
                if not tool_active or cursor is None or curve_key not in cursor[1]:
                    marker.setData([], [])
                    marker.setVisible(False)
                    continue
                resolved_x, values_at_x = cursor
                marker.setData([resolved_x], [values_at_x[curve_key]])
                marker.setVisible(True)

    def _delta_x_label_and_unit(self) -> tuple[str, str]:
        if self._x_channel is None:
            return "t", f" {_ELAPSED_TIME_UNIT}"
        if self._show_fit:
            label = self._fit_x_symbol
        else:
            channel = self._channel_map.get(self._x_channel)
            label = channel.display_name if channel else self._x_channel
        channel = self._channel_map.get(self._x_channel)
        unit = f" {channel.unit}" if channel and channel.unit else ""
        return label, unit

    def _update_delta_panel(self) -> None:
        if self._delta_cursor_a is None:
            self._delta_body_label.setText(_DELTA_EMPTY_TEXT)
            return
        if self._delta_cursor_b is None:
            resolved_x, values_at_x = self._delta_cursor_a
            lines = ["A", self._format_x_line(resolved_x)]
            lines.extend(self._format_y_line(k, v) for k, v in values_at_x.items())
            self._delta_body_label.setText("\n".join(lines))
            return
        self._delta_body_label.setText(
            self._format_delta_result(self._delta_cursor_a, self._delta_cursor_b)
        )

    def _format_delta_result(
        self,
        cursor_a: tuple[float, dict[str, float]],
        cursor_b: tuple[float, dict[str, float]],
    ) -> str:
        x_a, values_a = cursor_a
        x_b, values_b = cursor_b
        lines = ["A", self._format_x_line(x_a)]
        lines.extend(self._format_y_line(k, v) for k, v in values_a.items())
        lines.append("")
        lines.append("B")
        lines.append(self._format_x_line(x_b))
        lines.extend(self._format_y_line(k, v) for k, v in values_b.items())
        lines.append("")

        x_label, x_unit = self._delta_x_label_and_unit()
        dx_result = compute_delta(x_a, 0.0, x_b, 0.0)
        lines.append(f"Δ{x_label} = {dx_result.dx:.3f}{x_unit}")

        common_keys = [k for k in values_a if k in values_b]
        if len(self._curve_keys) == 1 and len(common_keys) == 1:
            key = common_keys[0]
            result = compute_delta(x_a, values_a[key], x_b, values_b[key])
            y_symbol = self._fit_y_symbol if self._show_fit else key
            y_channel = self._channel_map.get(key)
            y_unit = f" {y_channel.unit}" if y_channel and y_channel.unit else ""
            lines.append(f"Δ{y_symbol} = {result.dy:.3f}{y_unit}")
            if result.ratio is not None:
                ratio_unit = f" {self._fit_unit}" if self._fit_unit else ""
                lines.append(f"Δ{y_symbol}/Δ{x_label} = {result.ratio:.3f}{ratio_unit}")
        else:
            for key in common_keys:
                result = compute_delta(x_a, values_a[key], x_b, values_b[key])
                channel = self._channel_map.get(key)
                symbol = channel.display_name if channel else key
                unit = f" {channel.unit}" if channel and channel.unit else ""
                lines.append(f"Δ{symbol} = {result.dy:.3f}{unit}")

        return "\n".join(lines)

    # ---- Phase 33A: Crosshair/coordinate readout ---------------------------

    def _build_latest_marker(self, plot_widget: pg.PlotWidget) -> pg.ScatterPlotItem:
        """Тек НАҚТЫ қосылған соңғы нүктені белгілейтін маркер (§7) —
        ``_try_add_point()``-тен басқа ЕШҚАШАН жаңартылмайды, сондықтан
        continuous stream-нен келетін капчерленбеген (capture_mode)
        аралық мәндерге ЕШҚАШАН ілінбейді.
        """
        marker = pg.ScatterPlotItem(
            size=_LATEST_MARKER_SIZE,
            brush=pg.mkBrush(_LATEST_MARKER_COLOR),
            pen=pg.mkPen("w", width=1.5),
        )
        marker.setZValue(60)
        plot_widget.addItem(marker)
        return marker

    def _curve_data_snapshot(
        self, keys: tuple[str, ...]
    ) -> dict[str, tuple[list[float], list[float]]]:
        """Crosshair-ге арналған, ТЕК ОҚУ snapshot-ы — ешбір мутация
        жасалмайды, тек deque-дерден list() көшірмесі алынады.
        """
        return {
            key: (list(self._x_data.get(key, ())), list(self._y_data.get(key, ())))
            for key in keys
        }

    def _format_readout(self, resolved_x: float, values_at_x: dict[str, float]) -> str:
        """Coordinate readout мәтіні — ТЕК нақты сызылған X/Y мәндерін
        көрсетеді (§5: "Do NOT recalculate physics differently inside
        the graph layer"). Ешбір туынды шама (мыс. Ohm's Law-дағы R)
        осы жерде ЕСЕПТЕЛМЕЙДІ — бұл Phase 33B-дің статистика/анализ
        қабатына қалдырылған.
        """
        lines = [self._format_x_line(resolved_x)]
        for key, value in values_at_x.items():
            lines.append(self._format_y_line(key, value))
        return "\n".join(lines)

    def _format_x_line(self, resolved_x: float) -> str:
        if self._x_channel is None:
            return f"t = {resolved_x:.2f} {_ELAPSED_TIME_UNIT}"
        channel = self._channel_map.get(self._x_channel)
        label = self._x_label_override or (
            channel.display_name if channel else self._x_channel
        )
        unit = channel.unit if channel else ""
        decimals = channel.decimals if channel else _DEFAULT_READOUT_DECIMALS
        return f"{label} = {resolved_x:.{decimals}f} {unit}".rstrip()

    def _format_y_line(self, key: str, value: float) -> str:
        channel = self._channel_map.get(key)
        label = channel.display_name if channel else key
        unit = channel.unit if channel else ""
        decimals = channel.decimals if channel else _DEFAULT_READOUT_DECIMALS
        return f"{label} = {value:.{decimals}f} {unit}".rstrip()

    def _on_stacked_crosshair_hover(self, source_key: str, resolved_x: float) -> None:
        """Stacked топтағы бір subplot hover етілгенде, қалған
        subplot-тардың crosshair-ін ДӘЛ СОЛ X-те көрсетеді — әрқайсысы
        ӨЗ деректерінен ЕҢ ЖАҚЫН НАҚТЫ үлгіні таңдайды (PlotCrosshair.
        show_at_x()), ортақ интерполяцияланған нүкте ЖОҚ.
        """
        for key, crosshair in self._crosshairs.items():
            if key != source_key:
                crosshair.show_at_x(resolved_x)

    def _update_axis_labels(self) -> None:
        if self._stacked:
            self._update_stacked_axis_labels()
            return

        if self._plot_widget is None:
            return

        # Vernier тәрізді ғылыми график бірлікті автоматты SI-префикспен
        # (мыс. "A"->"mA") ауыстырмауы тиіс — конфигурацияланған бірлік
        # әрқашан сол қалпында көрсетіледі.
        self._plot_widget.getAxis("bottom").enableAutoSIPrefix(False)
        self._plot_widget.getAxis("left").enableAutoSIPrefix(False)

        if self._x_channel is None:
            x_label = self._x_label_override or _ELAPSED_TIME_LABEL
            self._plot_widget.setLabel("bottom", x_label, units=_ELAPSED_TIME_UNIT)
        else:
            x_channel_obj = self._channel_map.get(self._x_channel)
            x_label = self._x_label_override or (
                x_channel_obj.display_name if x_channel_obj else self._x_channel
            )
            x_unit = x_channel_obj.unit if x_channel_obj else ""
            self._plot_widget.setLabel("bottom", x_label, units=x_unit)

        if len(self._curve_keys) == 1:
            channel = self._channel_map.get(self._curve_keys[0])
            y_label = self._y_label_override or (
                channel.display_name if channel else self._curve_keys[0]
            )
            unit = channel.unit if channel else ""
            self._plot_widget.setLabel("left", y_label, units=unit)
        else:
            self._plot_widget.setLabel("left", "")

    def _update_stacked_axis_labels(self) -> None:
        """Stacked режимде әр subplot ӨЗ Y-осін (``stacked_y_labels``
        немесе ``channel.display_name`` fallback) көрсетеді, ал X-осьтің
        (уақыт) мәтіні ТЕК ЕҢ ТӨМЕНГІ subplot-та шығады — mockup-тағыдай,
        артық қайталанған "Уақыт" жазуы болмас үшін.
        """
        keys = list(self._stacked_plot_widgets.keys())
        for index, key in enumerate(keys):
            plot_widget = self._stacked_plot_widgets[key]
            plot_widget.getAxis("bottom").enableAutoSIPrefix(False)
            plot_widget.getAxis("left").enableAutoSIPrefix(False)

            if index == len(keys) - 1:
                x_label = self._x_label_override or _ELAPSED_TIME_LABEL
                plot_widget.setLabel("bottom", x_label, units=_ELAPSED_TIME_UNIT)
            else:
                plot_widget.setLabel("bottom", "")

            channel = self._channel_map.get(key)
            y_label = self._stacked_y_labels.get(key) or (
                channel.display_name if channel else key
            )
            unit = channel.unit if channel else ""
            plot_widget.setLabel("left", y_label, units=unit)
