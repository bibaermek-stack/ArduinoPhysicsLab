"""ThemeManager — Vernier/LabQuest тәрізді жеңіл, кәсіби ғылыми зертхана
дизайн-жүйесінің орталық QSS/design-token көзі.

Бұл модуль ``app.py``-де ``QApplication.setStyleSheet()`` арқылы бір
рет қолданылады — жеке виджеттерге scattered inline ``setStyleSheet()``
шақырулары орнына, object name/property селекторлары арқылы (мыс.
``QFrame#MeasurementCard``, ``QLabel[role="cardValue"]``) орталықтан
басқарылады. Виджеттер тек ``setObjectName()``/``setProperty("role",
...)`` арқылы "белгіленеді" — өз içinде ешбір түс/қаріп мәнін
қатаң (hardcode) жазбайды.

**Phase 44A — Design System Foundation:** бұл файл ЖОБАНЫҢ БІРЫҢҒАЙ
дизайн-токен көзі (spacing/radius/typography/color/status/icon-size/
animation-duration шкалалары). Бұл кезең ТЕК дизайн-жүйенің ӨЗІН
құрайды — ешбір бет/layout/dashboard/experiment workspace ҚАЙТА
ЖОБАЛАНБАЙДЫ. Жаңа property-негізді варианттар (button/card
variant-тары, status белгілері) ҚАСАҚАНА "тыныш" (dormant) — ешбір
бет.py файлы бұл property-лерді ӨЗІНЕ ЕШҚАШАН орнатпайды осы кезеңде,
тек келесі фазалар үшін дайын селектор ретінде анықталады. Барлық
БҰРЫННАН БАР object-name селекторлары (нақты беттер қолданатын) СОЛ
ҚАЛПЫ қалады — тек олардың мәндері (түс/hover/pressed/focus) токендер
арқылы нақтыланды.

**Phase 1 (premium commercial redesign brief) — token refresh:** түс/
типографика/button-height токендері "Microsoft Fluent 2 / Windows 11 /
Visual Studio 2022 / Vernier Graphical Analysis / PASCO Sparkvue"
бағытына сай ЖАҢА нақты мәндерге жаңартылды (§ Primary/Hover/Pressed
өзгеріссіз қалды, Success/Warning/Danger/Background/Borders/Text
мәндері жаңартылды, typography шәкілі Display 28/Section 20/Card
Title 16/Body 13/Caption 11/Measurement Value 42/Units 16-ға
ұлғайтылды, ``MIN_BUTTON_HEIGHT`` 32→44px). Бұл — жаңа 10-фазалық
жоспардың ТЕК 1-фазасы ("Design System"); Sidebar/Home/Experiment
Workspace/Graphs/Tables/Settings/Results/Animations беттерінің ӨЗІ
осы кезеңде ЕШҚАШАН тиілмеген — келесі фазаларда бөлек қаралады.

**Phase 2 ("Fluent 2 Laboratory Professional Edition") — compact
proportions restored, Fluent 2 polish added:** Phase 1-дің ұлғайтылған
типографикасы (Section Title 20px/Measurement Value 42px т.б.) НАҚТЫ,
скриншотпен расталған 3 clipping регрессиясын тудырған еді (§ Phase 1
есебі). Пайдаланушы Phase 1-дің нәтижесін baseline РЕТІНДЕ ЕШҚАШАН
қолданбауды, ЫҚШАМ (compact) пропорцияларды ҚАЙТА орнатуды талап етті.
Осы кезеңде: (1) typography толығымен жаңа, НАҚТЫ pixel
спецификацияға сай қайта белгіленді (Window Title 18/Page Title
24/Section Title 18/Card Title 15/Body 13/Caption 11/Measurement
Value 30 (28-32 диапазонының ортасы)/Units 13/Sidebar 13px) — барлық
өлшем бірлігі ``pt``-тен ``px``-ге ауыстырылды (нақты, DPI-тәуелсіз
логикалық пиксель); (2) ``MIN_BUTTON_HEIGHT`` 44→32px (Phase 1-ге
ДЕЙІНГІ ықшам Fluent 2 "medium control" биіктігі); (3) карточка
(card/panel) селекторларының бұрыштары ``RADIUS_MD`` (8px)-тен
``RADIUS_LG`` (12px)-ге дейін дөңгеленді (§ "Cards: 12 px radius" —
ТЕК бұрыш радиусы, карточка ені/биіктігі/padding-і ӨЗГЕРТІЛМЕДІ);
(4) Windows 11 стиліндегі жіңішке, дөңгеленген ``QScrollBar`` қосылды.
Phase 1-де ЕНІ ӨЗГЕРМЕГЕН тар контейнерлер үшін қосылған арнайы
токендер (``FONT_SIZE_SIDEBAR_BRAND``/``FONT_SIZE_LABS_SECTION_TITLE``)
енді ЖАЛПЫ токендерге қайта біріктірілді — жаңа Section Title (18px)
өлшемі бұл контейнерлерге ӨЗІ сыятыны скриншот аудитінде расталды.

**Ескерту (осы кезеңнің шеңберінен тыс қалғаны):** "Graphs" (pyqtgraph
grid/axes/legend түстері) мен "Icons" (Fluent System Icons-пен
ауыстыру) секциялары ``ui/widgets/live_graph.py``/бет .py файлдарында
Python кодымен (QSS ЕМЕС) басқарылады — бұл файлдың ӨЗІ (``ui/themes/
theme_manager.py``) ЕШҚАШАН осыны қамтамасыз ете алмайды. Пайдаланушы
құптағаннан кейін ғана, НАҚТЫ қай файл(дар) өзгеретінін алдын ала
хабарлап, бөлек қаралуы керек.
"""

# ==========================================================================
# SPACING SCALE
# ==========================================================================
# Толық 4-48 шәкілі (§ Phase 44A талабы). Ескі "T-shirt" аттар (SPACING_XS/
# SM/MD/LG/XL/XXL) осы файл ішінде бұрыннан қолданылатын жерлердің
# үзіліссіздігі үшін ЖАҢА сандық токендерге СІЛТЕМЕ ретінде сақталды.

SPACING_4 = 4
SPACING_8 = 8
SPACING_12 = 12
SPACING_16 = 16
SPACING_20 = 20
SPACING_24 = 24
SPACING_32 = 32
SPACING_40 = 40
SPACING_48 = 48

SPACING_XS = SPACING_4
SPACING_SM = SPACING_8
SPACING_MD = SPACING_8
SPACING_LG = SPACING_16
SPACING_XL = SPACING_24
SPACING_XXL = SPACING_32

# ==========================================================================
# RADIUS SCALE
# ==========================================================================

RADIUS_6 = 6
RADIUS_8 = 8
RADIUS_10 = 10
RADIUS_12 = 12
RADIUS_16 = 16

RADIUS_SM = RADIUS_6
RADIUS_MD = RADIUS_8
RADIUS_LG = RADIUS_12
RADIUS_XL = RADIUS_16

# ==========================================================================
# TYPOGRAPHY SCALE
# ==========================================================================
# Семантикалық қаріп-өлшем шкаласы (px, Qt QSS-те НАҚТЫ логикалық
# пиксель) + салмақ (weight) токендері. Нақты сан бойынша "сиқырлы мән"
# (magic number) орнына, беттер осы аттармен ЖАНАМА қолданады.
#
# Phase 2 ("Fluent 2 Laboratory Professional Edition") — Phase 1-де
# (алдыңғы "premium redesign" кезеңі) типографика айтарлықтай
# ұлғайтылған еді (Section Title 12→20pt, Measurement Value 26→42pt
# т.б.), БІРАҚ бұл нақты, ЕНІ ӨЗГЕРМЕГЕН контейнерлерде (sidebar brand,
# catalog card тақырыптары, workflow indicator) кесілу регрессиясына
# әкелген (§ Phase 1 есебіндегі 3 түзетілген регрессия). Пайдаланушы
# ЕНДІ НАҚТЫ: "Restore the original compact proportions first" деп
# талап етті — Phase 1-дің ұлғайтылған нұсқасы ЕШҚАШАН baseline
# ретінде қолданылмайды. Осы кезеңде БАРЛЫҚ мән — жаңа, НАҚТЫ pixel
# спецификацияға сай (§ "Window Title 18 / Page Title 24 / Section
# Title 18 / Card Title 15 / Body 13 / Caption 11 / Measurement Value
# 28-32 / Units 13 / Sidebar 13") — бұрынғы pt бірлігінен ``px``-ге
# ауыстырылды (нақты, DPI-тәуелсіз логикалық пиксель мәні үшін).
FONT_SIZE_WINDOW_TITLE = 18
FONT_SIZE_DISPLAY = 26
FONT_SIZE_PAGE_TITLE = 24
FONT_SIZE_SECTION_TITLE = 18
FONT_SIZE_CARD_TITLE = 15
FONT_SIZE_BODY = 13
FONT_SIZE_CAPTION = 11
FONT_SIZE_SMALL = 10
FONT_SIZE_MEASUREMENT_VALUE = 30
FONT_SIZE_MEASUREMENT_UNIT = 13
FONT_SIZE_SIDEBAR = 13

# Phase 1-де sidebar/catalog-card/workflow-indicator секілді ЕНІ
# ӨЗГЕРМЕГЕН тар контейнерлер үшін бөлек, тәуелсіз токен қажет болған
# еді (§ Phase 1 есебі). Section Title енді әлдеқайда КІШІ (18px) —
# скриншот аудитінде осы тар контейнерлердің ЖАҢА жалпы токенмен де
# (қосымша безендірусіз) кесілместен сыятыны расталды, сондықтан бұл
# арнайы токендер ЕНДІ ЖАЛПЫ ``FONT_SIZE_SIDEBAR``/``FONT_SIZE_SECTION_
# TITLE``-ге қайта біріктірілді (§ "don't over-special-case once the
# root cause — too-large a global token — is fixed").

FONT_WEIGHT_REGULAR = 400
FONT_WEIGHT_MEDIUM = 500
FONT_WEIGHT_SEMIBOLD = 600
FONT_WEIGHT_BOLD = 700

# Segoe UI Variable — Windows 11-дің жүйелік қарпі; орнатылмаған
# орталарда (CI/басқа OS) Qt үнсіз "Segoe UI"-ге, содан кейін жүйелік
# sans-serif-ке ауысады — ЕШБІР қаріп файлы жүктелмейді/бумаланбайды.
FONT_FAMILY = '"Segoe UI Variable", "Segoe UI", sans-serif'

# ==========================================================================
# COLOR TOKENS
# ==========================================================================
# Phase 1 (premium commercial redesign brief) — Fluent 2/Windows 11/
# VS2022/Vernier Graphical Analysis бағытына сай нақтыланған палитра.

# Phase 10 ("Visible Fluent 2 Refinement"): Phase 9-дағы surface/border
# токендері КӨЗБЕН көргенде дерлік ажыратылмайтыны нақты BEFORE/AFTER
# скриншот салыстыруымен расталды (§ пайдаланушының "still looks too
# visually close to the original interface" пікірі). Төмендегі мәндер
# ӘДЕЙІ айқынырақ калибрленді — background/sidebar/surface ҮШ НАҚТЫ,
# көзге көрінетін бөлек тон, border екі деңгейі шынымен байқалатын
# болуы үшін. Геометрияға (spacing/radius/padding/height) ЕШБІР тимейді
# — тек түс мәндері.
# Windows 11 Fluent 2 / mica dark — Custom QSS (кітапханасыз).
COLOR_BACKGROUND = "#1C1C1E"
COLOR_SURFACE = "#2C2C2E"
COLOR_SIDEBAR_BACKGROUND = "#141416"
COLOR_INPUT = "#3A3A3C"
COLOR_GLASS_TOP = "#3A3A42"
COLOR_GLASS_BOTTOM = "#26262A"

COLOR_BORDER = "#3F3F46"
COLOR_BORDER_SUBTLE = "#2A2A2E"

COLOR_TEXT_PRIMARY = "#F5F5F5"
COLOR_TEXT_SECONDARY = "#C8C8C8"
COLOR_TEXT_MUTED = "#8D8D8D"

COLOR_ACCENT = "#0078D4"
COLOR_ACCENT_HOVER = "#1B86D9"
COLOR_ACCENT_PRESSED = "#006CBD"
COLOR_ACCENT_TEXT = "#FFFFFF"
COLOR_ACCENT_GLOW = "#60CDFF"

COLOR_SUCCESS = "#0F7B3A"
COLOR_WARNING = "#F59E0B"
COLOR_ERROR = "#E5534B"
COLOR_ERROR_HOVER = "#C13E37"
COLOR_INFO = "#4CC2FF"

COLOR_HOVER = "#3A3A3C"
COLOR_SELECTED = "#0078D4"
COLOR_FOCUS_OUTLINE = "#60CDFF"

# Phase 9 ("Fluent 2 Laboratory Professional Edition" — visual modernization):
# сұралған семантикалық token атаулары — көбі ЖАҢА мән ЕМЕС, тек
# бұрыннан бар токендерге АТАУЛЫҚ бүркеншік (alias), сол арқылы бір
# ғана "ащы шындық" мәні сақталады (екі бөлек, сәл ажыратылатын хекс
# мән жоқ). Жаңа НАҚТЫ мән тек шынымен жетіспейтін орындарда қосылды
# (``COLOR_BORDER_STRONG``, ``COLOR_ACCENT_SUBTLE``, ``COLOR_GRAPH_*``).
COLOR_SURFACE_SECONDARY = COLOR_BACKGROUND
COLOR_SURFACE_HOVER = COLOR_HOVER
COLOR_SURFACE_SELECTED = COLOR_SELECTED
COLOR_BORDER_STRONG = "#5A5A62"
COLOR_TEXT_DISABLED = COLOR_TEXT_MUTED
# Phase 9-да ``COLOR_ACCENT_SUBTLE`` (#EFF6FF) ``COLOR_HOVER``-тен
# (сол кездегі #E8F0FE) ЖЕҢІЛІРЕК болып шыққан — нәтижесінде icon-
# батырманың "checked" күйі "hover" күйінен ӘЛСІЗІРЕК көрінген (§
# Phase 10 root cause). Түзету: checked ЕНДІ ``COLOR_SELECTED``
# қолданады (§ төмен), ол Phase 10-да hover-ден НАҚТЫ тереңірек
# болатындай қайта калибрленген — checked ӘРҚАШАН hover-ден күштірек.
COLOR_ACCENT_SUBTLE = "#1A3A52"

# Графиктің (pyqtgraph) фон/тор/ось/мәтін түстері — ``ui/widgets/
# live_graph.py``-де Python арқылы қолданылады (QSS ЕМЕС, себебі
# pyqtgraph QSS-ті мұралай алмайды, § модуль docstring-індегі ескерту).
# Мұнда тек орталық REFERENCE ретінде анықталған.
COLOR_GRAPH_BACKGROUND = COLOR_SURFACE
COLOR_GRAPH_GRID = COLOR_BORDER
COLOR_GRAPH_AXIS = COLOR_TEXT_PRIMARY
COLOR_GRAPH_TEXT = COLOR_TEXT_PRIMARY

# Laboratory Catalog — секция identity accent түстері (HomePage карточкалары,
# STEM модульдер). heat/electricity/electromagnetism/light — Phase 32-ден
# бері қолданылатын мәндер, ӨЗГЕРТІЛМЕДІ. laboratory/feedback/results/
# devices/analytics — Phase 44A-да қосымша дизайн-жүйе токені ретінде
# енгізілді (§ workspace watermark-тың ӨЗ, бөлек, 2-13% opacity-ге
# бейімделген палитрасынан — ``ui/widgets/workspace_background.py`` —
# ӘДЕЙІ тәуелсіз: бұл жерде НАҚТЫ, толық қаныққан UI accent түсі керек).
COLOR_SECTION_HEAT = "#E65100"
COLOR_SECTION_ELECTRICITY = "#2E7D32"
COLOR_SECTION_ELECTROMAGNETISM = "#2563EB"
COLOR_SECTION_LIGHT = "#6A1B9A"
COLOR_SECTION_LABORATORY = "#00897B"
COLOR_SECTION_FEEDBACK = "#AD1457"
COLOR_SECTION_RESULTS = "#00838F"
COLOR_SECTION_DEVICES = "#00ACC1"
COLOR_SECTION_ANALYTICS = "#3949AB"

# ==========================================================================
# CLASSROOM ACCENT PALETTE (Phase 13 follow-up — Teacher Dashboard Activity
# carousel, "Stable Classroom Accent Colors")
# ==========================================================================
# Fluent-үйлесімді, тұрақты (мутирленген, неон ЕМЕС) 6 түсті палитра — әр
# сынып classroom_id бойынша ДЕТЕРМИНИСТІК осы палитрадан бір түс алады
# (§ ``ui/widgets/class_activity_carousel.classroom_accent_color()``).
# Semantic status токендерімен (COLOR_SUCCESS/COLOR_WARNING/COLOR_ERROR)
# ӘДЕЙІ ешбір мән ортақ ЕМЕС (§ "Avoid using success/warning/error
# semantic colors in ways that could make a classroom look like a
# status"), қызыл да ӘДЕЙІ жоқ (§ "Avoid red... already associated with
# errors/warnings"). Тек осы палитраны, ешбір басқа UI accent-ін
# өзгертпейді.
COLOR_CLASSROOM_BLUE = "#2563EB"
COLOR_CLASSROOM_VIOLET = "#7C3AED"
COLOR_CLASSROOM_TEAL = "#0D9488"
COLOR_CLASSROOM_GREEN = "#4D7C0F"
COLOR_CLASSROOM_AMBER = "#B45309"
COLOR_CLASSROOM_MAGENTA = "#BE185D"

# ==========================================================================
# STATUS COLORS
# ==========================================================================
# Құрылғы/өлшеу lifecycle күйлеріне арналған семантикалық түс токендері
# (§ "Status Colors"). Қазір ешбір бет.py файлы бұл ``status`` property-ін
# орнатпайды — тек келесі фазаларда қолдануға дайын.

COLOR_STATUS_CONNECTED = COLOR_SUCCESS
COLOR_STATUS_DISCONNECTED = COLOR_TEXT_SECONDARY
COLOR_STATUS_MEASURING = COLOR_ACCENT
COLOR_STATUS_RECORDING = COLOR_ERROR
COLOR_STATUS_ERROR = COLOR_ERROR
COLOR_STATUS_WARNING = COLOR_WARNING
COLOR_STATUS_IDLE = COLOR_TEXT_MUTED

# ==========================================================================
# ICON STRATEGY (reserved sizing — Phase 44A-да иконка ӨЗІ қосылмайды)
# ==========================================================================

ICON_SIZE_SM = 16
ICON_SIZE_MD = 20
ICON_SIZE_LG = 24

# ==========================================================================
# ANIMATION TOKENS (тек константа — Qt QSS-те transition/animation
# қасиеті ЖОҚ; бұл мәндер келесі фазаларда Python жағында
# ``QPropertyAnimation`` арқылы қолданылады, әзірге ЕШҚАШАН анимация
# жасалмайды).
# ==========================================================================

ANIMATION_HOVER_MS = 120
ANIMATION_BUTTON_MS = 80
ANIMATION_PAGE_TRANSITION_MS = 180
ANIMATION_FADE_MS = 150
ANIMATION_CARD_LIFT_PX = 2  # тек константа — карточка hover "lift" эффектісі әзірге қолданылмайды

# Phase 12 ("Subtle Motion System"): жоғарыдағы токендер ЕНДІ НАҚТЫ
# қолданылады (§ ui/widgets/motion.py, ui/widgets/animated_atom_widget.py) —
# бұрынғы "әзірге ешқашан анимация жасалмайды" ескертуі ЕНДІ ЕСКІРГЕН.
# Атаулар сәйкестігі: ANIMATION_BUTTON_MS -> pressed/release (§ "70-90ms"),
# ANIMATION_HOVER_MS -> hover/checked toolbar (§ "100-150ms"),
# ANIMATION_FADE_MS -> Sidebar selected/status fade төменгі шегі (§ "150ms"),
# ANIMATION_PAGE_TRANSITION_MS -> status fade жоғарғы шегі (§ "150-200ms");
# бөлек, жаңа токендер тек НАҚТЫ жаңа мағыналарға (atom orbit/pulse,
# measurement value highlight) арналған.
MOTION_ATOM_ORBIT_CYCLE_MS = 16000  # орбитаның толық айналымы (§ "12-20 seconds")
MOTION_ATOM_PULSE_MS = 6000  # ядро "тыныс алу" периоды (§ "4-8 seconds")
MOTION_VALUE_HIGHLIGHT_MS = 120  # өлшем мәні жаңарғандағы қысқа highlight (§ "Maximum highlight duration: ~120ms")

# ==========================================================================
# ACCESSIBILITY
# ==========================================================================

# Phase 2 ("Fluent 2 Laboratory Professional Edition"): Phase 1-де 44px-ге
# дейін ұлғайтылған еді ("Buttons: Minimum height 44 px" деген алдыңғы
# spec-ке сай) — БІРАҚ пайдаланушы ЕНДІ НАҚТЫ "Do NOT increase height.
# Keep current dimensions" деп талап етті, яғни Phase 1-ге ДЕЙІНГІ
# ықшам (compact) Fluent 2 "medium control" биіктігіне қайтарылды.
MIN_BUTTON_HEIGHT = 32
MIN_TOUCH_TARGET = 32

# Phase 4 (Restore Compact Desktop Controls): Qt QSS box моделі ЕСКІ
# CSS content-box тәрізді — ``padding``/``border`` ЕШҚАШАН ``min-height``
# санынан алынбайды, керісінше ҮСТІНЕ қосылады. Бұрын ``min-height:
# 32px`` + ``padding: 6px 14px`` + ``border: 1px`` НАҚТЫ рендерленген
# биіктікті 46px-ге дейін ұлғайтқаны эмпирикалық түрде расталды (§
# нақты ``button.height()`` тексерісі) — сондықтан батырмалар "touch/
# tablet" тәрізді үлкен көрінген, ешбір font/spacing токені өзгермесе
# де. Төмендегі ``_CONTROL_CONTENT_MIN_HEIGHT`` — QSS-тегі ``min-height``
# үшін ГЕНЕ MIN_BUTTON_HEIGHT ЕМЕС, ЖОСПАРЛАНҒАН padding/border-ды
# алдын ала алып тастаған "ішкі мазмұн" мәні — нәтижесінде НАҚТЫ
# рендерленген биіктік дәл ``MIN_BUTTON_HEIGHT``-ке (32px) сай келеді.
_CONTROL_VERTICAL_PADDING = 4
_CONTROL_BORDER_WIDTH = 1
_CONTROL_CONTENT_MIN_HEIGHT = (
    MIN_BUTTON_HEIGHT - (2 * _CONTROL_VERTICAL_PADDING) - (2 * _CONTROL_BORDER_WIDTH)
)


class ThemeManager:
    """Windows 11 Fluent / mica dark — Custom QSS, толық пиксель бақылауы."""

    def build_stylesheet(self) -> str:
        """Бүкіл қолданбаға бір рет қолданылатын QSS мәтінін қайтарады."""
        return f"""
        QWidget {{
            background-color: {COLOR_BACKGROUND};
            color: {COLOR_TEXT_PRIMARY};
            font-family: {FONT_FAMILY};
        }}
        QMainWindow, QStackedWidget {{
            background-color: {COLOR_BACKGROUND};
        }}
        QSplitter::handle {{
            background-color: {COLOR_BORDER_SUBTLE};
        }}
        QSplitter::handle:horizontal {{
            width: 1px;
        }}

        /* ==================================================================
           BUTTON SYSTEM
           ================================================================== */

        QPushButton {{
            background-color: {COLOR_INPUT};
            border: {_CONTROL_BORDER_WIDTH}px solid {COLOR_BORDER};
            border-radius: {RADIUS_SM}px;
            padding: {_CONTROL_VERTICAL_PADDING}px 12px;
            min-height: {_CONTROL_CONTENT_MIN_HEIGHT}px;
        }}
        QPushButton:hover {{
            border-color: {COLOR_ACCENT};
            background-color: {COLOR_HOVER};
        }}
        QPushButton:pressed {{
            background-color: {COLOR_SELECTED};
        }}
        QPushButton:focus {{
            border: 2px solid {COLOR_FOCUS_OUTLINE};
        }}
        QPushButton:disabled {{
            color: {COLOR_TEXT_MUTED};
            background-color: {COLOR_BACKGROUND};
            border-color: {COLOR_BORDER_SUBTLE};
        }}

        /* Primary Button — Fluent градиент. */
        QPushButton#PrimaryButton {{
            background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {COLOR_ACCENT_HOVER}, stop:1 {COLOR_ACCENT});
            color: {COLOR_ACCENT_TEXT};
            border: none;
            font-weight: {FONT_WEIGHT_SEMIBOLD};
        }}
        QPushButton#PrimaryButton:hover {{
            background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {COLOR_ACCENT_GLOW}, stop:1 {COLOR_ACCENT_HOVER});
        }}
        QPushButton#PrimaryButton:pressed {{
            background-color: {COLOR_ACCENT_PRESSED};
        }}
        QPushButton#PrimaryButton:focus {{
            border: 2px solid {COLOR_ACCENT_PRESSED};
        }}
        QPushButton#PrimaryButton:disabled {{
            background-color: {COLOR_BORDER};
            color: {COLOR_TEXT_SECONDARY};
        }}

        /* Mode Switch + Student Access Screen Redesign: толық экрандық
           кіру/мод-ауыстыру беті (RoleSelectionPage) — орталық карточка
           + "үлкен" Оқушы/Мұғалім таңдау батырмалары. hover/pressed/focus
           күйлері базалық ``QPushButton``-нан мұраланады (§ objectName
           селекторы pseudo-класс ережелерін ЕШҚАШАН басып тастамайды). */
        QFrame#EntrySurfaceCard {{
            background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {COLOR_GLASS_TOP}, stop:1 {COLOR_GLASS_BOTTOM});
            border: 1px solid rgba(255, 255, 255, 42);
            border-radius: {RADIUS_LG}px;
            padding: 8px;
        }}
        QLabel#EntryTitle {{
            font-weight: {FONT_WEIGHT_BOLD};
            font-size: {FONT_SIZE_PAGE_TITLE}px;
            background-color: transparent;
        }}
        QPushButton#EntryModeButton {{
            text-align: left;
            padding: 14px 16px;
            min-height: 24px;
            font-weight: {FONT_WEIGHT_SEMIBOLD};
        }}
        QLabel#EntryErrorLabel {{
            color: {COLOR_ERROR};
            font-size: {FONT_SIZE_CAPTION}px;
            background-color: transparent;
        }}
        QWidget#EntryModeView, QWidget#EntryLoginView {{
            background-color: transparent;
        }}

        /* Дайын, БІРАҚ әзірге ешбір бет орнатпайтын variant-тар (§ "dormant
           until a later phase adopts them" — Secondary/Outline/Danger/Icon). */
        QPushButton[variant="secondary"] {{
            background-color: {COLOR_SURFACE};
            border: 1px solid {COLOR_ACCENT};
            color: {COLOR_ACCENT};
            font-weight: {FONT_WEIGHT_SEMIBOLD};
        }}
        QPushButton[variant="secondary"]:hover {{
            background-color: {COLOR_HOVER};
        }}
        QPushButton[variant="secondary"]:pressed {{
            background-color: {COLOR_SELECTED};
        }}
        QPushButton[variant="outline"] {{
            background-color: transparent;
            border: 1px solid {COLOR_BORDER};
            color: {COLOR_TEXT_PRIMARY};
        }}
        QPushButton[variant="outline"]:hover {{
            border-color: {COLOR_ACCENT};
            background-color: {COLOR_HOVER};
        }}
        QPushButton[variant="danger"] {{
            background-color: {COLOR_ERROR};
            color: {COLOR_ACCENT_TEXT};
            border: none;
            font-weight: {FONT_WEIGHT_SEMIBOLD};
        }}
        QPushButton[variant="danger"]:hover {{
            background-color: {COLOR_ERROR_HOVER};
        }}
        /* Phase 9: base ережеде ``border: none`` орнына ЕШҚАШАН
           көрінбейтін ``1px solid transparent`` қолданылады (padding
           4px→3px, дәл сол 1px-ке теңестіру үшін) — нәтижесінде
           :checked күйі НАҚТЫ accent border қосқанда РЕНДЕРЛЕНГЕН
           өлшем (32×32) БАРЛЫҚ күйде (normal/hover/pressed/checked)
           дәл бірдей қалады (тек border-СӘНІ ауысады, border-ЕНІ
           ЕШҚАШАН ЕМЕС — Qt box моделінде border-ені өзгерсе, батырма
           checked/unchecked ауысқанда 2px "секіру" тудырар еді). */
        QPushButton[variant="icon"] {{
            background-color: transparent;
            border: 1px solid transparent;
            border-radius: {RADIUS_SM}px;
            padding: 3px;
            min-height: {MIN_BUTTON_HEIGHT - 8}px;
            min-width: {MIN_BUTTON_HEIGHT - 8}px;
        }}
        QPushButton[variant="icon"]:hover {{
            background-color: {COLOR_HOVER};
        }}
        QPushButton[variant="icon"]:pressed {{
            background-color: {COLOR_SELECTED};
        }}
        /* graph toolbar-дың checkable icon-батырмалары (pan/zoom mode,
           maximize, region) бұрын ЕШБІР ``:checked`` стилін алмаған —
           checked/unchecked күй бір-бірінен визуалды ажыратылмайтын
           (§ есеп: оқшауланған тест — focus policy өшірілгенде checked
           батырма unchecked-тен АБСОЛЮТТІ ажыратылмайтыны расталды).
           Phase 10 root cause түзетуі: бастапқы нұсқа ``COLOR_ACCENT_
           SUBTLE`` қолданған, ол іс жүзінде ``COLOR_HOVER``-ден
           ЖЕҢІЛІРЕК болып шыққан — checked hover-ден ӘЛСІЗІРЕК
           көрінген. ЕНДІ ``COLOR_SELECTED`` (hover-ден НАҚТЫ
           тереңірек) қолданылады — checked ӘРҚАШАН hover-ден
           күштірек, 2px accent жиекпен қоса. */
        QPushButton[variant="icon"]:checked {{
            background-color: {COLOR_SELECTED};
            border-color: {COLOR_ACCENT};
        }}
        QPushButton[variant="icon"]:checked:hover {{
            background-color: {COLOR_SELECTED};
            border-color: {COLOR_ACCENT_HOVER};
        }}
        QPushButton[variant="icon"]:disabled {{
            color: {COLOR_TEXT_DISABLED};
        }}

        /* ==================================================================
           CARD SYSTEM
           ================================================================== */

        /* Phase 4 (Experiment Workspace layout architecture fix):
           ``min-height: 96px`` Phase 1-дің ұлғайтылған типографикасы
           (Measurement Value 42px) кезінен қалған "ЕСКІ ЛЕЙФТОВЕР" еді —
           Phase 2-де typography ықшамдалғанда (30px) бұл мән ЕШҚАШАН
           қайта қаралмаған. Нәтижесінде карточка ӨЗ шынайы мазмұн
           биіктігінен (label+value ≈ 88px) 96+border=98px-ге дейін
           жасанды ұлғайтылған (§ нақты ``card.sizeHint()`` тексерісі:
           96px min-height болмаса 88px). Бұл — ТЕК бір ғана нақты
           табылған "spacing емес, өлшем-архитектура" ысырап көзі
           (қалған барлық stretch factor/sizePolicy дұрыс екені бөлек
           тексерілді). ``min-height`` мүлде алынбады — QVBoxLayout
           карточканы ӨЗ табиғи мазмұн биіктігінен ЕШҚАШАН кішірейтпейді,
           қосымша ЖАСАНДЫ минимум қажет емес. */
        /* Phase 10/11: "instrument bezel" — өлшем карточкасының сол
           жағында accent жолақ, "ғылыми аспап readout-ы" әсерін
           күшейту үшін (§ "The card should visually read as a
           scientific readout"). Phase 11: 3px→2px — Phase 10-дағы
           нұсқа "ауыр индустриалды жолақ" сияқты тым басым көрінген
           деп бағаланды, 2px Fluent 2-ге жақынырақ, БІРАҚ карточка
           әлі де НАҚТЫ "аспап" ретінде оқылады. border-top/right/
           bottom 1px қалады — карточка БИІКТІГІНЕ (69px, frozen)
           ЕШБІР әсер етпейді. */
        QFrame#MeasurementCard {{
            background-color: {COLOR_SURFACE};
            border: 1px solid {COLOR_BORDER};
            border-left: 2px solid {COLOR_ACCENT};
            border-radius: {RADIUS_LG}px;
        }}

        /* Дайын, жалпы карточка variant-тары (§ "Card System" — Standard/
           Summary/Measurement/Status/Module). Нақты беттер (HomeSummaryCard/
           MeasurementCard/GraphCard/т.б.) өз ЕСКІ, нақты object-name
           селекторларын сақтайды — бұл жаңа property-негізді нұсқалар
           тек келесі фазаларда пайдалануға дайын, дублирление емес. */
        QFrame[cardVariant="standard"] {{
            background-color: {COLOR_SURFACE};
            border: 1px solid {COLOR_BORDER};
            border-radius: {RADIUS_LG}px;
        }}
        QFrame[cardVariant="summary"] {{
            background-color: {COLOR_SURFACE};
            border: 1px solid {COLOR_BORDER};
            border-radius: {RADIUS_LG}px;
        }}
        QFrame[cardVariant="measurement"] {{
            background-color: {COLOR_SURFACE};
            border: 1px solid {COLOR_BORDER};
            border-radius: {RADIUS_LG}px;
        }}
        QFrame[cardVariant="status"] {{
            background-color: {COLOR_SURFACE};
            border: 1px solid {COLOR_BORDER};
            border-left: 4px solid {COLOR_ACCENT};
            border-radius: {RADIUS_LG}px;
        }}
        QFrame[cardVariant="module"] {{
            background-color: {COLOR_SURFACE};
            border: 1px solid {COLOR_BORDER};
            border-top: 3px solid {COLOR_BORDER};
            border-radius: {RADIUS_LG}px;
        }}

        /* Phase 9: label ЖӘНЕ unit екеуі де ``COLOR_TEXT_SECONDARY``
           (қара-сұр) орнына ``COLOR_TEXT_MUTED`` (одан да ашығырақ)
           қолданады — cardValue-дың (30px, bold, primary) визуалды
           басымдығын күшейту үшін, өлшем/padding-ке ЕШБІР тимей (§
           "The measured numerical value should be visually dominant"). */
        QLabel[role="cardLabel"] {{
            color: {COLOR_TEXT_MUTED};
            font-size: {FONT_SIZE_BODY}px;
            font-weight: {FONT_WEIGHT_SEMIBOLD};
        }}
        QLabel[role="cardValue"] {{
            color: {COLOR_TEXT_PRIMARY};
            font-size: {FONT_SIZE_MEASUREMENT_VALUE}px;
            font-weight: {FONT_WEIGHT_BOLD};
        }}
        QLabel[role="cardTitle"] {{
            color: {COLOR_TEXT_PRIMARY};
            font-size: {FONT_SIZE_CARD_TITLE}px;
            font-weight: {FONT_WEIGHT_BOLD};
        }}
        QLabel[role="measurementUnit"] {{
            color: {COLOR_TEXT_MUTED};
            font-size: {FONT_SIZE_MEASUREMENT_UNIT}px;
            font-weight: {FONT_WEIGHT_MEDIUM};
        }}
        QLabel[role="display"] {{
            font-weight: {FONT_WEIGHT_BOLD};
            font-size: {FONT_SIZE_DISPLAY}px;
        }}
        QLabel[role="secondary"] {{
            color: {COLOR_TEXT_SECONDARY};
        }}
        QLabel[role="muted"] {{
            color: {COLOR_TEXT_MUTED};
        }}
        QLabel[role="error"] {{
            color: {COLOR_ERROR};
        }}
        QLabel[role="caption"] {{
            color: {COLOR_TEXT_SECONDARY};
            font-size: {FONT_SIZE_CAPTION}px;
        }}
        QLabel[role="small"] {{
            color: {COLOR_TEXT_MUTED};
            font-size: {FONT_SIZE_SMALL}px;
        }}
        QLabel[role="pageTitle"] {{
            font-weight: {FONT_WEIGHT_BOLD};
            font-size: {FONT_SIZE_PAGE_TITLE}px;
        }}
        QLabel[role="sectionTitle"] {{
            font-weight: {FONT_WEIGHT_BOLD};
            font-size: {FONT_SIZE_SECTION_TITLE}px;
        }}

        /* ExperimentWorkflowIndicator (§ "Нұсқаулық/Схема/Құрылғы/Өлшеу/
           Есеп/Кері байланыс" қадам жолағы) — ІШКІ label-дері ЖАЛПЫ
           "sectionTitle" role-ін тар, бір жолды қадам атаулары үшін
           қолданады (нақты БЕТ тақырыбы ЕМЕС). Жаңа, әлдеқайда үлкен
           ``FONT_SIZE_SECTION_TITLE`` (20pt) осы тар, 6 қадамды бір
           қатарға сыйдыратын жолақта кесілу/бір-біріне үстінен түсу
           регрессиясын тудыратыны скриншот аудитінде расталды —
           ExperimentWorkflowIndicator.py-дың ӨЗІ (widget hierarchy/
           объект аты) тиілместен, ТЕК осы контейнердің ІШІНДЕГІ
           "sectionTitle" мәтінін ескі, дәлелденген өлшемге қайтаратын
           неғұрлым нақты (id + descendant) селектор. */
        QWidget#ExperimentWorkflowIndicator QLabel[role="sectionTitle"] {{
            font-weight: {FONT_WEIGHT_SEMIBOLD};
            font-size: {FONT_SIZE_CAPTION}px;
        }}

        /* Status белгілері (§ "Status Colors") — дайын, БІРАҚ ешбір бет
           әзірге ``status`` property-ін орнатпайды. */
        QLabel[status="connected"] {{ color: {COLOR_STATUS_CONNECTED}; font-weight: {FONT_WEIGHT_SEMIBOLD}; }}
        QLabel[status="disconnected"] {{ color: {COLOR_STATUS_DISCONNECTED}; }}
        QLabel[status="measuring"] {{ color: {COLOR_STATUS_MEASURING}; font-weight: {FONT_WEIGHT_SEMIBOLD}; }}
        QLabel[status="recording"] {{ color: {COLOR_STATUS_RECORDING}; font-weight: {FONT_WEIGHT_SEMIBOLD}; }}
        QLabel[status="error"] {{ color: {COLOR_STATUS_ERROR}; font-weight: {FONT_WEIGHT_SEMIBOLD}; }}
        QLabel[status="warning"] {{ color: {COLOR_STATUS_WARNING}; font-weight: {FONT_WEIGHT_SEMIBOLD}; }}
        QLabel[status="idle"] {{ color: {COLOR_STATUS_IDLE}; }}

        /* Phase 11: category chip ("ЭЛЕКТР ҚҰБЫЛЫСТАРЫ") — эксперимент
           header-дің оқылу реті бойынша БІРІНШІ элемент (§ "category +
           experiment number" — 1-деңгей), сондықтан бейтарап сұр
           орнына жеңіл accent-tint "tag" көрінісі алды (padding/
           radius/font-size ӨЗГЕРМЕЙДІ — тек түс). */
        QLabel#CategoryChip {{
            background-color: {COLOR_ACCENT_SUBTLE};
            color: {COLOR_ACCENT};
            border-radius: {RADIUS_SM}px;
            padding: 2px 10px;
            font-weight: {FONT_WEIGHT_SEMIBOLD};
            font-size: {FONT_SIZE_SMALL}px;
        }}
        QLabel#ExperimentNumberBadge {{
            background-color: {COLOR_ACCENT};
            color: {COLOR_ACCENT_TEXT};
            border-radius: {RADIUS_SM}px;
            padding: 2px 8px;
            font-weight: {FONT_WEIGHT_BOLD};
            font-size: {FONT_SIZE_SMALL}px;
        }}
        QLabel#StatusDetailLabel {{
            color: {COLOR_TEXT_SECONDARY};
            font-size: {FONT_SIZE_CAPTION}px;
        }}

        QFrame#ConnectionSettingsGroup {{
            background-color: {COLOR_BACKGROUND};
            border: 1px solid {COLOR_BORDER};
            border-radius: {RADIUS_SM}px;
        }}
        QLabel#ConnectionSettingsTitle {{
            color: {COLOR_TEXT_SECONDARY};
            font-weight: {FONT_WEIGHT_SEMIBOLD};
            font-size: {FONT_SIZE_CAPTION}px;
        }}
        QLabel#DeviceCardLiveValue {{
            font-weight: {FONT_WEIGHT_BOLD};
            font-size: {FONT_SIZE_BODY}px;
        }}

        /* Phase 9/10/11: график — беттегі ЕҢ маңызды ғылыми виджет
           ("Graphs remain dominant scientific visualizations"), ЖАЙ
           карточкалардан қоюырақ ``COLOR_BORDER_STRONG`` жиекпен
           ерекшеленеді. Phase 11: Phase 10-дағы 4px accent "bezel"
           жолағы АЛЫНЫП ТАСТАЛДЫ — Fluent 2 қағидасы бойынша accent
           тек INTERACTION-ды (selected/checked/focused — § graph
           toolbar-дың checkable батырмалары) білдіруі тиіс, статикалық
           контейнерді ТҰРАҚТЫ бояп тұрмауы керек. Граф ЕНДІ бейтарап,
           бірақ қоюырақ жиекпен ("neutral surface hierarchy")
           ерекшеленеді — accent ТЕК toolbar-дың checked күйінде
           көрінеді. border ені ӨЗГЕРМЕЙДІ (1px, барлық 4 жақ) —
           БИІКТІККЕ (176/339px, frozen) ЕШБІР әсер етпейді. */
        QFrame#GraphCard {{
            background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {COLOR_GLASS_TOP}, stop:1 {COLOR_SURFACE});
            border: 1px solid rgba(255, 255, 255, 40);
            border-radius: {RADIUS_LG}px;
        }}
        QLabel#GraphCardTitle {{
            font-weight: {FONT_WEIGHT_BOLD};
            font-size: {FONT_SIZE_BODY}px;
        }}
        QLabel#GraphCardLiveBadge {{
            color: {COLOR_ERROR};
            font-weight: {FONT_WEIGHT_BOLD};
            font-size: {FONT_SIZE_SMALL}px;
        }}
        QLabel#GraphStatsLabel {{
            color: {COLOR_TEXT_SECONDARY};
            font-size: {FONT_SIZE_CAPTION}px;
        }}

        QFrame#DiagramPanel {{
            background-color: {COLOR_SURFACE};
            border: 1px solid {COLOR_BORDER};
            border-radius: {RADIUS_LG}px;
        }}

        QFrame#GuideSection {{
            background-color: {COLOR_SURFACE};
            border: 1px solid {COLOR_BORDER};
            border-radius: {RADIUS_LG}px;
        }}
        QLabel[role="formula"] {{
            font-weight: {FONT_WEIGHT_SEMIBOLD};
            font-size: {FONT_SIZE_SECTION_TITLE}px;
            padding: 2px 0;
        }}

        QFrame#DeviceCard {{
            background-color: {COLOR_SURFACE};
        }}

        QFrame#ManagedDeviceCard {{
            background-color: {COLOR_SURFACE};
            border: 1px solid {COLOR_BORDER};
            border-radius: {RADIUS_LG}px;
        }}
        QFrame#DevicePortRow {{
            background-color: {COLOR_SURFACE};
            border: 1px solid {COLOR_BORDER};
            border-radius: {RADIUS_SM}px;
        }}
        /* Phase 21: DevicesPage-тің ескі 3 жай QLabel статистикасы
           HomeSummaryCard-стильді карточкаларға ауыстырылды (§ "Use the
           already-fixed transparent card-label convention") — бұрынғы
           ``#DevicesPageSummaryLabel`` селекторының ЕНДІ ешбір
           тұтынушысы жоқ, алынып тасталды. */

        /* ==================================================================
           SIDEBAR STYLE (§ "Do NOT redesign the Sidebar. Only define the
           style system." — Sidebar.py құрылымы/layout-ы тиілмейді, тек
           бұрыннан бар object-name селекторларының мәндері нақтыланды.)
           ================================================================== */

        QWidget#Sidebar {{
            background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #101012, stop:1 {COLOR_SIDEBAR_BACKGROUND});
            border-right: 1px solid rgba(255, 255, 255, 28);
        }}
        QLabel#SidebarBrand {{
            font-weight: {FONT_WEIGHT_BOLD};
            font-size: {FONT_SIZE_SIDEBAR}px;
        }}
        QPushButton#SidebarCollapseButton {{
            border: none;
            background-color: transparent;
            padding: 2px;
            min-height: 0px;
        }}
        QPushButton#SidebarCollapseButton:hover {{
            background-color: {COLOR_HOVER};
            border-radius: {RADIUS_SM}px;
        }}

        /* "Sidebar Item" — навигация батырмасы. */
        QPushButton#SidebarNavButton {{
            text-align: left;
            border: none;
            border-radius: {RADIUS_SM}px;
            padding: 8px 10px;
            background-color: transparent;
            min-height: 0px;
        }}
        QPushButton#SidebarNavButton:hover:enabled {{
            background-color: {COLOR_HOVER};
        }}
        QPushButton#SidebarNavButton:pressed:enabled {{
            background-color: {COLOR_SELECTED};
        }}
        QPushButton#SidebarNavButton:checked {{
            background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 {COLOR_ACCENT}, stop:1 {COLOR_ACCENT_HOVER});
            color: {COLOR_ACCENT_TEXT};
            font-weight: {FONT_WEIGHT_SEMIBOLD};
        }}
        QPushButton#SidebarNavButton:disabled {{
            color: {COLOR_TEXT_MUTED};
        }}
        QPushButton#SidebarNavButton:focus {{
            border: 2px solid {COLOR_FOCUS_OUTLINE};
        }}

        /* "Role Area" / "Bottom Area" — рөл/белсенді оқушы индикаторлары. */
        QLabel#SidebarDeviceSummary {{
            color: {COLOR_TEXT_SECONDARY};
            font-size: {FONT_SIZE_CAPTION}px;
        }}
        QLabel#SidebarRoleIndicator {{
            color: {COLOR_TEXT_SECONDARY};
            font-size: {FONT_SIZE_CAPTION}px;
            font-weight: {FONT_WEIGHT_SEMIBOLD};
        }}
        QLabel#SidebarActiveStudent {{
            color: {COLOR_TEXT_SECONDARY};
            font-size: {FONT_SIZE_CAPTION}px;
            font-weight: {FONT_WEIGHT_MEDIUM};
        }}
        QLabel#SidebarActiveTeacher {{
            color: {COLOR_TEXT_SECONDARY};
            font-size: {FONT_SIZE_CAPTION}px;
            font-weight: {FONT_WEIGHT_MEDIUM};
        }}
        QPushButton#SidebarSwitchRoleButton, QPushButton#SidebarSwitchStudentButton {{
            text-align: left;
            border: none;
            border-radius: {RADIUS_SM}px;
            padding: 6px 10px;
            background-color: transparent;
            color: {COLOR_TEXT_SECONDARY};
            font-size: {FONT_SIZE_CAPTION}px;
            min-height: 0px;
        }}
        QPushButton#SidebarSwitchRoleButton:hover, QPushButton#SidebarSwitchStudentButton:hover {{
            background-color: {COLOR_HOVER};
        }}
        QPushButton#SidebarSwitchRoleButton:pressed, QPushButton#SidebarSwitchStudentButton:pressed {{
            background-color: {COLOR_SELECTED};
        }}

        QFrame#HomeHero {{
            background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 {COLOR_GLASS_TOP}, stop:1 {COLOR_GLASS_BOTTOM});
            border: 1px solid rgba(255, 255, 255, 36);
            border-radius: {RADIUS_LG}px;
        }}
        QLabel#HomeHeroTitle {{
            font-weight: {FONT_WEIGHT_BOLD};
            font-size: {FONT_SIZE_PAGE_TITLE}px;
        }}
        QLabel#HomeHeroSubtitle {{
            color: {COLOR_TEXT_SECONDARY};
            font-weight: {FONT_WEIGHT_SEMIBOLD};
            font-size: {FONT_SIZE_BODY}px;
        }}

        /* Phase 10: dashboard stat-карточкалары (Teacher/Student, §
           "HomeSummaryCard" — teacher_dashboard_page.py/home_page.py/
           student_feedback_page.py/teacher_feedback_review_page.py/
           results_page.py/analytics_page.py/question_bank_page.py/
           devices_page.py ортақ пайдаланады)
           MeasurementCard-пен БІРДЕЙ "instrument
           bezel" тілін алады — accent жолақ, дәйекті визуалды жүйе. */
        QFrame#HomeSummaryCard {{
            background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 {COLOR_GLASS_TOP}, stop:1 {COLOR_SURFACE});
            border: 1px solid rgba(255, 255, 255, 28);
            border-left: 3px solid {COLOR_ACCENT};
            border-radius: {RADIUS_LG}px;
        }}

        QFrame#HomeModuleCard {{
            background-color: {COLOR_SURFACE};
            border: 1px solid {COLOR_BORDER};
            border-top: 3px solid {COLOR_BORDER};
            border-radius: {RADIUS_LG}px;
        }}
        QFrame#HomeModuleCard[sectionAccent="heat"] {{
            border-top-color: {COLOR_SECTION_HEAT};
        }}
        QFrame#HomeModuleCard[sectionAccent="electricity"] {{
            border-top-color: {COLOR_SECTION_ELECTRICITY};
        }}
        QFrame#HomeModuleCard[sectionAccent="electromagnetism"] {{
            border-top-color: {COLOR_SECTION_ELECTROMAGNETISM};
        }}
        QFrame#HomeModuleCard[sectionAccent="light"] {{
            border-top-color: {COLOR_SECTION_LIGHT};
        }}
        QLabel#HomeModuleCardIcon {{
            background-color: transparent;
            font-size: {ICON_SIZE_MD}px;
        }}
        QLabel#HomeModuleCardTitle {{
            background-color: transparent;
            font-weight: {FONT_WEIGHT_BOLD};
        }}
        QPushButton#HomeModuleCardAction, QPushButton#HomeContinueMoreLink {{
            text-align: left;
            border: none;
            background-color: transparent;
            color: {COLOR_ACCENT};
            font-weight: {FONT_WEIGHT_SEMIBOLD};
            padding: 4px 0;
            min-height: 0px;
        }}
        QPushButton#HomeModuleCardAction:hover, QPushButton#HomeContinueMoreLink:hover {{
            text-decoration: underline;
        }}
        /* § "subtle text action" — HomeModuleCardAction-тен сәл кішірек/
           мұқым, категория "Ашу →" сілтемесімен шатастырмау үшін. */
        QPushButton#HomeContinueMoreLink {{
            color: {COLOR_TEXT_SECONDARY};
            font-weight: {FONT_WEIGHT_REGULAR};
            font-size: {FONT_SIZE_CAPTION}px;
        }}

        QFrame#HomeDevicePanel, QFrame#HomeQuickLabsPanel {{
            background-color: {COLOR_SURFACE};
            border: 1px solid {COLOR_BORDER};
            border-radius: {RADIUS_LG}px;
        }}
        /* Student Home Dashboard Redesign: "Жалғастыру" карточкасының
           populated/empty ауыстырылатын ішкі контейнерлері — PrimaryButton
           баласы бар болғандықтан instance-деңгейлік setStyleSheet() ЕМЕС
           (§ Phase 20 QuestionBankPage регрессиясы), тек осы глобал QSS. */
        QWidget#HomeContinuePopulated, QWidget#HomeContinueEmpty {{
            background-color: transparent;
        }}
        /* Student Home Dashboard Redesign: құрылғы жолы — ЖАСЫЛ
           #HomeDeviceStatusDot баласы бар болғандықтан instance-деңгейлік
           setStyleSheet() ЕМЕС (эмпирикалық түрде бұзылатыны расталды). */
        QWidget#HomeDeviceLineRow, QWidget#HomeDeviceLinesContainer,
        QWidget#HomeRecentResultsContainer, QWidget#HomeRecentResultRow {{
            background-color: transparent;
        }}
        QLabel#HomeDeviceStatusDot {{
            background-color: {COLOR_SUCCESS};
            border-radius: 5px;
        }}
        QPushButton#HomeQuickLabButton {{
            text-align: left;
            border: none;
            border-radius: {RADIUS_SM}px;
            background-color: transparent;
            padding: 6px 4px;
            min-height: 0px;
        }}
        QPushButton#HomeQuickLabButton:hover {{
            background-color: {COLOR_HOVER};
        }}

        QFrame#LabsSectionCard {{
            background-color: {COLOR_SURFACE};
            border: 1px solid {COLOR_BORDER};
            border-radius: {RADIUS_LG}px;
        }}
        QFrame#LabsSectionHeader {{
            background-color: {COLOR_BORDER};
            border-top-left-radius: {RADIUS_LG}px;
            border-top-right-radius: {RADIUS_LG}px;
            padding: {SPACING_MD}px;
        }}
        QFrame#LabsSectionHeader[sectionAccent="heat"] {{
            background-color: {COLOR_SECTION_HEAT};
        }}
        QFrame#LabsSectionHeader[sectionAccent="electricity"] {{
            background-color: {COLOR_SECTION_ELECTRICITY};
        }}
        QFrame#LabsSectionHeader[sectionAccent="electromagnetism"] {{
            background-color: {COLOR_SECTION_ELECTROMAGNETISM};
        }}
        QFrame#LabsSectionHeader[sectionAccent="light"] {{
            background-color: {COLOR_SECTION_LIGHT};
        }}
        QLabel#LabsSectionIcon {{
            background-color: transparent;
            font-size: {ICON_SIZE_MD}px;
        }}
        QLabel#LabsSectionTitle {{
            background-color: transparent;
            color: {COLOR_ACCENT_TEXT};
            font-weight: {FONT_WEIGHT_BOLD};
            font-size: {FONT_SIZE_SECTION_TITLE}px;
        }}
        QFrame#LabsExperimentRow {{
            border: none;
            border-radius: {RADIUS_SM}px;
            background-color: transparent;
            padding: 4px;
        }}
        QFrame#LabsExperimentRow:hover {{
            background-color: {COLOR_HOVER};
        }}
        QLabel#LabsExperimentRowLabel {{
            background-color: transparent;
        }}
        QFrame#LabsExperimentRow:disabled QLabel#LabsExperimentRowLabel {{
            color: {COLOR_TEXT_SECONDARY};
        }}
        QLabel#LabsPlannedBadge {{
            background-color: {COLOR_BACKGROUND};
            color: {COLOR_TEXT_SECONDARY};
            border-radius: {RADIUS_SM}px;
            padding: 1px 6px;
            font-size: {FONT_SIZE_SMALL}px;
        }}

        /* ==================================================================
           FORM SYSTEM
           ================================================================== */

        QLineEdit {{
            background-color: {COLOR_INPUT};
            border: 1px solid {COLOR_BORDER};
            border-radius: {RADIUS_SM}px;
            padding: 6px 10px;
            selection-background-color: {COLOR_ACCENT};
            selection-color: {COLOR_ACCENT_TEXT};
        }}
        QLineEdit:hover {{
            border-color: {COLOR_ACCENT};
        }}
        QLineEdit:focus {{
            border: 2px solid {COLOR_FOCUS_OUTLINE};
        }}
        QLineEdit:disabled {{
            background-color: {COLOR_BACKGROUND};
            color: {COLOR_TEXT_MUTED};
        }}
        QLineEdit[role="search"], QLineEdit[role="filter"] {{
            border-radius: {RADIUS_LG}px;
            padding: 6px 14px;
        }}

        QComboBox {{
            background-color: {COLOR_INPUT};
            border: {_CONTROL_BORDER_WIDTH}px solid {COLOR_BORDER};
            border-radius: {RADIUS_SM}px;
            padding: {_CONTROL_VERTICAL_PADDING}px 10px;
            min-height: {_CONTROL_CONTENT_MIN_HEIGHT}px;
        }}
        QComboBox:hover {{
            border-color: {COLOR_ACCENT};
        }}
        QComboBox:focus {{
            border: 2px solid {COLOR_FOCUS_OUTLINE};
        }}
        QComboBox:disabled {{
            background-color: {COLOR_BACKGROUND};
            color: {COLOR_TEXT_MUTED};
        }}
        QComboBox::drop-down {{
            border: none;
            width: 22px;
        }}
        /* QComboBox popup (QAbstractItemView) — native Windows style-тер
           (windowsvista/windows11) кейде дана item-дерді QSS ``background-
           color``-мен ЕМЕС, тікелей жүйелік (OS қараңғы режимі) palette-мен
           бояйды — тек view-деңгейлік ережеден ЖЕТКІЛІКСІЗ. Сондықтан ЖЕКЕ
           ``::item``/``::item:hover``/``::item:selected``/``::item:disabled``
           sub-control-тары да НАҚТЫ анықталады — popup-тың ӨЗІ (жақтау/фон)
           ЕМЕС, әр ЖОЛ да толық QSS бақылауында болуы үшін (§ "black popup
           background" регрессиясы). Sidebar-дың hover/selected токендерімен
           БІРДЕЙ (COLOR_HOVER/COLOR_SELECTED) — жаңа түс ойлап шығарылмайды.
           Тек попап-тың ІШКІ көрінісі — ComboBox-тың ЖАБЫҚ өлшемі/геометриясы
           бұл блокта ЕШБІР өзгермейді. */
        QComboBox QAbstractItemView {{
            background-color: {COLOR_SURFACE};
            color: {COLOR_TEXT_PRIMARY};
            border: 1px solid {COLOR_BORDER};
            outline: 0;
            selection-background-color: {COLOR_SELECTED};
            selection-color: {COLOR_TEXT_PRIMARY};
        }}
        QComboBox QAbstractItemView::item {{
            background-color: {COLOR_SURFACE};
            color: {COLOR_TEXT_PRIMARY};
            padding: 6px 10px;
        }}
        QComboBox QAbstractItemView::item:hover {{
            background-color: {COLOR_HOVER};
            color: {COLOR_TEXT_PRIMARY};
        }}
        QComboBox QAbstractItemView::item:selected {{
            background-color: {COLOR_SELECTED};
            color: {COLOR_TEXT_PRIMARY};
        }}
        QComboBox QAbstractItemView::item:disabled {{
            background-color: {COLOR_SURFACE};
            color: {COLOR_TEXT_MUTED};
        }}

        QSpinBox, QDoubleSpinBox {{
            background-color: {COLOR_SURFACE};
            border: 1px solid {COLOR_BORDER};
            border-radius: {RADIUS_SM}px;
            padding: 4px 6px;
        }}
        QSpinBox:hover, QDoubleSpinBox:hover {{
            border-color: {COLOR_ACCENT};
        }}
        QSpinBox:focus, QDoubleSpinBox:focus {{
            border: 2px solid {COLOR_FOCUS_OUTLINE};
        }}
        QSpinBox:disabled, QDoubleSpinBox:disabled {{
            background-color: {COLOR_BACKGROUND};
            color: {COLOR_TEXT_MUTED};
        }}

        QCheckBox {{
            spacing: {SPACING_8}px;
        }}
        QCheckBox::indicator {{
            width: 18px;
            height: 18px;
            border: 1px solid {COLOR_BORDER};
            border-radius: 4px;
            background-color: {COLOR_SURFACE};
        }}
        QCheckBox::indicator:hover {{
            border-color: {COLOR_ACCENT};
        }}
        QCheckBox::indicator:checked {{
            background-color: {COLOR_ACCENT};
            border-color: {COLOR_ACCENT};
        }}
        QCheckBox::indicator:disabled {{
            background-color: {COLOR_BACKGROUND};
            border-color: {COLOR_BORDER_SUBTLE};
        }}

        QRadioButton {{
            spacing: {SPACING_8}px;
        }}
        QRadioButton::indicator {{
            width: 18px;
            height: 18px;
            border: 1px solid {COLOR_BORDER};
            border-radius: 9px;
            background-color: {COLOR_SURFACE};
        }}
        QRadioButton::indicator:hover {{
            border-color: {COLOR_ACCENT};
        }}
        QRadioButton::indicator:checked {{
            background-color: {COLOR_ACCENT};
            border: 4px solid {COLOR_SURFACE};
            outline: 1px solid {COLOR_ACCENT};
        }}
        QRadioButton::indicator:disabled {{
            background-color: {COLOR_BACKGROUND};
            border-color: {COLOR_BORDER_SUBTLE};
        }}

        /* ==================================================================
           TABLE SYSTEM
           ================================================================== */

        QTableView {{
            background-color: {COLOR_SURFACE};
            gridline-color: {COLOR_BORDER};
            border: 1px solid {COLOR_BORDER};
            alternate-background-color: {COLOR_BACKGROUND};
            selection-background-color: {COLOR_ACCENT};
            selection-color: {COLOR_ACCENT_TEXT};
        }}
        QTableView::item {{
            padding: 3px 6px;
        }}
        QTableView::item:hover {{
            background-color: {COLOR_HOVER};
        }}
        QTableView::item:selected {{
            background-color: {COLOR_ACCENT};
            color: {COLOR_ACCENT_TEXT};
        }}
        /* Кестелер (мыс. тар session-нәтиже панельдері) көбінесе бірнеше
           тар бағанды бір қатарға сыйдырады — жалпы Body(13pt) өлшемі
           тақырып мәтінін кесіп тастайтыны расталды. Header-лер әрдайым
           Caption деңгейінде (§ "Comfortable spacing", БІРАҚ "No
           clipping" талабы басым). */
        /* Phase 10: header ЕНДІ ``COLOR_SIDEBAR_BACKGROUND`` (жол
           фонынан НАҚТЫ күңгірттеу — "professional data-acquisition
           software" тілі) + 2px accent асты-сызық (border-bottom 1px→
           2px, padding-top 4px→3px арқылы ДӘЛ теңестірілген — жол
           биіктігі БАЙҚАЛМАЙТЫН дәрежеде де өзгермейді: 4+4+1=9px
           ЕСКІ, 3+4+2=9px ЖАҢА). */
        QHeaderView::section {{
            background-color: {COLOR_SIDEBAR_BACKGROUND};
            border: none;
            border-bottom: 2px solid {COLOR_ACCENT};
            padding: 3px 6px 4px 6px;
            font-size: {FONT_SIZE_CAPTION}px;
            font-weight: {FONT_WEIGHT_BOLD};
            color: {COLOR_TEXT_PRIMARY};
        }}
        QHeaderView::section:hover {{
            background-color: {COLOR_HOVER};
        }}
        QTableView#MeasurementTableView {{
            alternate-background-color: {COLOR_BACKGROUND};
            border: none;
        }}
        QTableView#MeasurementTableView::item {{
            padding: 2px 6px;
        }}
        QTableView#MeasurementTableView::item:selected {{
            background-color: {COLOR_ACCENT};
            color: {COLOR_ACCENT_TEXT};
        }}

        /* Phase 2 ("Fluent 2 Laboratory Professional Edition"): Windows 11
           стиліндегі жіңішке, дөңгеленген scrollbar — кестелер/scroll
           аймақтарының геометриясына ЕШБІР ӘСЕР ЕТПЕЙДІ (тек viewport
           шеті бойындағы жіңішке жолақтың ӨЗІНІҢ безендірілуі). */
        QScrollBar:vertical {{
            background: transparent;
            width: 10px;
            margin: 2px;
        }}
        QScrollBar::handle:vertical {{
            background: {COLOR_BORDER};
            border-radius: 5px;
            min-height: 24px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {COLOR_TEXT_MUTED};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
            background: transparent;
        }}
        QScrollBar:horizontal {{
            background: transparent;
            height: 10px;
            margin: 2px;
        }}
        QScrollBar::handle:horizontal {{
            background: {COLOR_BORDER};
            border-radius: 5px;
            min-width: 24px;
        }}
        QScrollBar::handle:horizontal:hover {{
            background: {COLOR_TEXT_MUTED};
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            width: 0px;
        }}
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
            background: transparent;
        }}

        /* Phase 41: Sidebar/жұмыс кеңістігі арасындағы сүйрелетін бөлгіш —
           жіңішке бейтарап сызық, hover-де сәл күштірек. */
        QSplitter#MainWindowSplitter::handle {{
            background-color: {COLOR_BORDER};
        }}
        QSplitter#MainWindowSplitter::handle:hover {{
            background-color: {COLOR_ACCENT};
        }}

        /* Phase 41: WorkspaceBackdrop су таңбасы НАҚТЫ page мазмұнынан
           төмен қабатта көрінуі үшін — QStackedWidget-тер ӨЗДЕРІ мөлдір
           болуы керек (WorkspaceBackdrop өз paintEvent-інде COLOR_BACKGROUND
           толтыруын+су таңбаны өзі салады, сондықтан бұл жерде ешбір
           көрініс жоғалмайды — тек қабат ауыстырылады). Блэнкет ТИП
           селекторы (тек ортақ ``WorkspaceStack`` емес) — ``StudentFeedback
           Page``/``StudentResultsPage`` сияқты беттердің ӨЗ ІШКІ
           (блокталған/мазмұн күйі үшін) ``QStackedWidget``-тері де ДӘЛ
           СОЛ мәселеге ұшырайтыны скриншот тексеруінде расталды. Бұл
           ЕШҚАШАН button/label/table сияқты НАҚТЫ мазмұн виджеттеріне
           жетпейді (олар QStackedWidget данасы ЕМЕС, тек оның ІШІНДЕ
           орналасқан — § QScrollArea-мен бірдей қауіпсіздік уәжі). */
        QStackedWidget {{
            background-color: transparent;
        }}

        /* Phase 41: Router-де тіркелген БАРЛЫҚ бет класының ТҮБІР
           (root) фоны мөлдір — WorkspaceBackdrop су таңбасы ТЕК осы
           беттердің НАҚТЫ жабылмаған бос аймағында (мыс. addStretch()
           орны) көрінеді. Карточка/кесте/батырма/диалог сияқты ІШКІ
           виджеттер өз ЖЕКЕ, неғұрлым нақты (object name/property)
           селекторларымен АЛДЫН АЛА opaque — bұл ереже оларға ӘСЕР
           ЕТПЕЙДІ (QSS specificity: аттас класс селекторы жалпы QWidget
           ережесінен басым, бірақ ІШКІ object-name селекторлардан төмен). */
        HomePage, DevicesPage, ExperimentListPage, ExperimentWorkspacePage,
        DataJournalPage, SettingsPage, HelpPage, RoleSelectionPage,
        ClassManagementPage, StudentSelectionPage, StudentResultsPage,
        TeacherDashboardPage, TeacherFeedbackReviewPage, PlaceholderPage,
        StudentFeedbackPage, ResultsPage, AnalyticsPage, QuestionBankPage {{
            background-color: transparent;
        }}

        /* Phase 20: QuestionBankPage-тің "Сұрақтар әлі қосылмаған" бос
           күй контейнері — жоғарыдағы блэнкет ТИП тізіміне ЕНБЕЙДІ (ол
           тек БЕТ ТҮБІРІ класстары үшін), сондықтан жеке object-name
           селекторы қажет. instance-деңгейлік ``setStyleSheet()`` ЕМЕС —
           ол ІШІНДЕГІ #PrimaryButton (+ Сұрақ қосу) баласының ӨЗ
           background-color ережесін жоғалтатыны эмпирикалық түрде
           расталды (§ ``question_bank_page.py`` түсініктемесі). Глобал
           object-name селекторы бұл каскад мәселесін болдырмайды. */
        QWidget#QuestionBankEmptyState {{
            background-color: transparent;
        }}
        /* Phase 21: DevicesPage-тің "COM порттар табылмады" бос күйі —
           QuestionBankEmptyState-пен БІРДЕЙ себеп/түзету (§ жоғарыдағы
           түсініктеме). */
        QWidget#DevicesNoPortsEmptyState {{
            background-color: transparent;
        }}

        /* Phase 41: HomePage/DevicesPage/DevicePanel сияқты беттер
           мазмұнын QScrollArea-мен орайды — scroll area-дың ӨЗІНІҢ
           viewport-ы ЖӘНЕ setWidget()-пен берілген контейнер де жеке,
           аттас емес QWidget данлары болғандықтан, жоғарыдағы бет-класс
           селекторы ОЛАРҒА ЕШҚАШАН жетпейді (тек СЫРТҚЫ бет данасын
           мөлдір етеді). Нәтижесінде су таңба scroll ішінде мүлде
           көрінбей қалатыны скриншот тексеруінде расталды — осы ереже
           сол екі аралық opaque қабатты (viewport + setWidget()
           контейнері) алып тастайды. ТЕК ``>`` тікелей-ұрпақ
           комбинаторымен, дәл 2 деңгейге дейін ғана — эмпирикалық түрде
           тексерілді: ``QScrollArea QWidget`` (descendant, шексіз
           тереңдік) нұсқасы QPushButton сияқты ІШКІ виджеттердің ӨЗ
           ЖЕКЕ ``background-color`` ережесін speceficity бойынша
           басып тастайды (регрессия!), ал ``>`` шектеулі нұсқасы
           button/label сияқты НАҚТЫ мазмұн виджеттеріне ЕШҚАШАН жетпейді
           (олар 3+ деңгей тереңдікте). Диалогтардағы QScrollArea-ларға
           да қолданылады, БІРАҚ бұл ЕШБІР көрнекі өзгеріс тудырмайды:
           QDialog да блэнкет ``QWidget`` ережесімен ДӘЛ СОЛ
           ``COLOR_BACKGROUND``-пен боялған, сондықтан астынан дәл сол
           түс көрінеді (§ "Dialogs must remain unaffected"). ``border``
           ӘДЕЙІ өзгертілмейді — тек background-color. */
        QScrollArea {{
            background-color: transparent;
        }}
        QScrollArea > QWidget {{
            background-color: transparent;
        }}
        QScrollArea > QWidget > QWidget {{
            background-color: transparent;
        }}

        /* Phase 41: HomePage-дің ӨЗ max-width центрлеу паттернінде
           (§ HomePage.__init__: scroll -> viewport -> "centered" ->
           "content") жоғарыдағы 2-деңгейлік ереже ЖЕТКІЛІКСІЗ — нақты
           бос орын (соңғы addStretch(1)) "content" (objectName=
           "HomeContent") деңгейінде, яғни 3-деңгейде. Дәл осы белгілі,
           бұрыннан аттас ("HomeContent") контейнерге НАҚТЫ мақсатты
           селектормен қосымша ереже — генерик тереңдікті одан әрі
           арттыру (мыс. 4 деңгей) басқа беттерде НАҚТЫ мазмұн
           виджеттеріне (батырма/карточка) қате жетіп кету қаупін
           тудырар еді. */
        QWidget#HomeContent {{
            background-color: transparent;
        }}

        /* Phase 41: StudentFeedbackPage/StudentResultsPage-дің ӨЗ ІШКІ
           (блокталған оқушы таңдалмаған) күй-беттері — блэнкет
           ``QStackedWidget`` ережесі тек СТЕКТІҢ ӨЗІН мөлдір етеді,
           ІШІНДЕГІ child view (жай QWidget) әлі де жалпы ``QWidget``
           ережесімен opaque қалады. Бұл, әдетте, ЕҢ бос (тек хабарлама+
           батырма) күй болғандықтан, су таңбаны көрсетуге ЕҢ қолайлы
           орын. */
        QWidget#StudentFeedbackBlockedView, QWidget#StudentResultsBlockedView {{
            background-color: transparent;
        }}

        /* Phase 41 background regression fix: ExperimentWorkspacePage-тің
           ӨЗІ жоғарыдағы бет-класс ережесімен мөлдір болса да, оның ІШІНДЕ
           барлық қалған биіктікті алатын ``MeasurementWorkspace`` (§ Phase
           32 "жалғыз stretch=1 алушы") және оның ІШКІ ``_no_device_page``/
           ``_device_page`` контейнерлері жеке, аттас емес ``QWidget``
           данлары болғандықтан, блэнкет ``QWidget`` ережесімен әлі де
           opaque қалатын — су таңба нақты график/кесте эксперимент
           беттерінде мүлде көрінбей қалатыны скриншот тексеруінде
           расталды. Бұл ереже сол ҮШ аралық opaque қабатты алып тастайды;
           ``GraphCard``/``MeasurementTableWidget``/кесте сияқты НАҚТЫ
           мазмұн виджеттері өз ЖЕКЕ object-name/тип селекторларымен
           opaque күйінде қалады (тек контейнер жиектеріндегі layout
           margin-дер ғана мөлдір болады, дәл HomeContent-пен бірдей
           қауіпсіздік уәжі). */
        QWidget#MeasurementWorkspace, QWidget#MeasurementWorkspaceDevicePage,
        QWidget#MeasurementWorkspaceNoDevicePage {{
            background-color: transparent;
        }}

        /* Phase 41 background regression fix: DataJournalPage/
           TeacherFeedbackReviewPage/StudentFeedbackPage/StudentResultsPage —
           бәрі де ӨЗ ІШКІ (жасырын) QStackedWidget-інде БІРНЕШЕ child view
           ұстайды (мыс. "тізім" vs "бөлшек" немесе "блокталған" vs
           "мазмұн"). Бұрын ТЕК ең бос ("блокталған") view object-name
           арқылы мөлдір етілген (§ StudentFeedbackBlockedView/
           StudentResultsBlockedView) — НАҚТЫ мазмұны бар view-лер
           (тізім/кесте, мұғалім/оқушы КӨБІНЕСЕ дәл осыны көреді) әлі де
           жалпы ``QWidget`` ережесімен opaque қалып, су таңбаны толығымен
           жауып тұратыны скриншот аудитінде расталды (§ "Деректер
           журналы"/"Кері байланысты тексеру" беттерінде watermark мүлде
           көрінбейтін). Кесте/карточка/батырма өз ЖЕКЕ селекторларымен
           opaque қалады — тек айналасындағы бос контейнер ғана мөлдір
           болады. */
        QWidget#DataJournalListView, QWidget#DataJournalDetailView,
        QWidget#DataJournalResultsContainer,
        QWidget#TeacherFeedbackResultsContainer,
        QWidget#StudentFeedbackContentView, QWidget#StudentFeedbackResultsContainer,
        QWidget#StudentResultsView, QWidget#ResultsTableContainer {{
            background-color: transparent;
        }}

        /* Phase 41 background regression fix: жоғарыдағы контейнерлер
           мөлдір болса да, "деректер жоқ" бос-күй хабарламасының ЕКІ
           QLabel-і (мыс. DataJournalPage._empty_state_title_label/
           _empty_state_hint_label) кесте жасырылған кезде layout-тың
           бос жерін ТЕҢ жартыға бөліп алатыны расталды (Qt-тың stretch=0
           виджеттер арасында артық орынды тең бөлу мінез-құлқы) — екі
           QLabel НАҚТЫ мәтін өлшемінен әлдеқайда үлкен, толығымен opaque
           тіктөртбұрыш ретінде БҮКІЛ су таңбаны жауып тұрады. Мәтіннің
           ӨЗІ (түс/қаріп) ешбір жалпы ``QLabel`` ережесімен басқарылмайды
           (тек ``role``-негізді нақты селекторлар бар), сондықтан бұл тек
           фонды алып тастайды. */
        QLabel#WorkspaceEmptyStateLabel {{
            background-color: transparent;
        }}

        /* ==================================================================
           Phase 13 — Teacher Dashboard (Activity carousel / Quick Actions /
           Recent Results). Жаңа, қосымша ережелер ғана — ешбір бар селектор
           өзгертілмейді (§ "ThemeManager should NOT need redesign").
           ================================================================== */

        /* Үш жаңа панельдің ортақ "карточка" тілі — ``HomeDevicePanel``/
           ``HomeQuickLabsPanel``/``LabsSectionCard``-мен БІРДЕЙ рецепт
           (§ "Do not add arbitrary new hex colors in the page file"). */
        QFrame#DashboardPanel {{
            background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {COLOR_GLASS_TOP}, stop:1 {COLOR_SURFACE});
            border: 1px solid rgba(255, 255, 255, 32);
            border-radius: {RADIUS_LG}px;
        }}
        QFrame#ActivitySlide {{
            background-color: transparent;
            border: none;
        }}

        /* ``HomeQuickLabButton``-мен БІРДЕЙ ықшам, сол жақтауланған,
           hover-де ғана ерекшеленетін әрекет жолы тілі. */
        QPushButton#DashboardQuickActionButton {{
            text-align: left;
            border: none;
            border-radius: {RADIUS_SM}px;
            background-color: transparent;
            padding: 6px 8px;
            min-height: 0px;
        }}
        QPushButton#DashboardQuickActionButton:hover {{
            background-color: {COLOR_HOVER};
        }}

        /* Карусель prev/next — variant="icon"-мен бірге қолданылады (§
           Phase 12 ButtonMotionFilter hover/pressed анимациясын
           автоматты мұралайды), тек ені тарылтылған. */
        QPushButton#DashboardCarouselNavButton {{
            font-weight: {FONT_WEIGHT_BOLD};
        }}

        /* Индикатор нүктелері — таңдалғаны accent, қалғаны бейтарап
           (§ "The current item uses accent color. Inactive indicators
           use muted/border color"). */
        QLabel#DashboardCarouselDot {{
            font-size: 8px;
            color: {COLOR_BORDER_STRONG};
            background-color: transparent;
        }}
        QLabel#DashboardCarouselDot[active="true"] {{
            color: {COLOR_ACCENT};
        }}

        /* Жіңішке, Fluent-стильді прогресс жолағы (§ "thin and
           Fluent-style", "No animated continuous progress effects" —
           QSS-тің ӨЗІ ешбір transition/animation қоспайды). */
        QProgressBar#DashboardActivityBar {{
            border: none;
            border-radius: 4px;
            background-color: {COLOR_BORDER_SUBTLE};
        }}
        QProgressBar#DashboardActivityBar::chunk {{
            background-color: {COLOR_ACCENT};
            border-radius: 4px;
        }}
        """
