"""WorkspaceBackdrop — жұмыс кеңістігінің секцияға тәуелді су таңбасы
(watermark) фоны (Phase 41; Phase 42A: paint-only визуалды редизайн).

``MainWindow`` бұл виджетті ``self._stack`` (QStackedWidget) айналасына
БІР РЕТ орайды — беттердің ӨЗІ ешбір фон логикасын білмейді/қайталамайды
(§ "The background must not be recreated every time a filter changes").
Секция ``set_category()`` арқылы СЫРТТАН итеріледі (``Router.route_changed``
хабарламасына жауап ретінде, ``ui.navigation.background_category``
көмегімен есептеледі) — дәл сол "dumb display widget" принципі
``Sidebar.set_active_student_text()``-те қолданылған.

Су таңба ӘРҚАШАН НАҚТЫ page мазмұнынан ТӨМЕН қабатта қалады: беттердің
ӨЗІ (``ui.pages.*``) мен ортақ ``QStackedWidget#WorkspaceStack``
``ThemeManager``-де ЖЕКЕ, тар бейнеленген селектормен мөлдір етіледі —
тек СОЛ беттердің НАҚТЫ жабылмаған бос аймағында (мыс. ``addStretch()``
орны) көрінеді, карточка/кесте/график үстінде ЕШҚАШАН емес (олар өз
айқын ``background-color`` ережелерін сақтайды).

Су таңбалар ЖЕКЕ прогромматикалық ``QPainter`` сызбалары (растрлық
файлдар/интернеттен жүктелген суреттер ЕМЕС) — категория бойынша БІР РЕТ
``QPixmap``-қа кэштеліп, әр ``paintEvent``-те тек масштабталып/
позицияланып салынады (қымбат сызу логикасы resize/repaint кезінде
ҚАЙТА ЕСЕПТЕЛМЕЙДІ).

**Phase 42A (paint-only redesign):** әр категория енді БІР оқшау сызық
емес, БІРНЕШЕ қабатты композиция — негізгі мотив + 2-3 қосымша пішін +
бөлшектер/түйіндер, әр қабаттың ӨЗ (rect-тегі pixmap-қа "күйдірілген")
alpha деңгейі бар (``_PRIMARY_ALPHA``/``_SECONDARY_ALPHA``/
``_ACCENT_FILL_ALPHA``), ал сыртқы composite opacity
(``_MAIN_COMPOSITE_OPACITY``) осы қабаттарды түпкілікті 2-12% перцептивті
диапазонға түсіреді. Акцент нүкте (соңғы регрессия сақтандыру белгісі —
ЕҢ тар видимая жиекте де көрінетін кепілдік) БӨЛЕК, кэштелмеген
composite өтуімен (``_ACCENT_DOT_OPACITY`` ≈ 13%) салынады — сол арқылы
ол қалған сызықтардан сәл ЖАРҚЫН болып, "highlight" ретінде оқылады.
Виджеттің public API-і (класс аты, ``set_category()``/``current_category()``/
``paintEvent()``, категория кілттері, кэштеу, corner-anchoring) МҮЛДЕ
өзгеріссіз қалады — тек ІШКІ сызу логикасы байытылды.
"""

from __future__ import annotations

import math
import time

from PySide6.QtCore import QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from ui.navigation.background_category import (
    ALL_CATEGORIES,
    CATEGORY_DEFAULT,
    CATEGORY_HOME,
    CATEGORY_LABORATORY,
)
from ui.themes.theme_manager import (
    COLOR_SECTION_ELECTRICITY,
    theme_color,
    COLOR_SECTION_ELECTROMAGNETISM,
    COLOR_SECTION_HEAT,
    COLOR_SECTION_LIGHT,
    COLOR_TEXT_SECONDARY,
)
from ui.widgets import motion
from ui.widgets.animated_atom_widget import paint_atom

# Phase 12 ("Subtle Motion System"): "home" санаты ЕНДІ ЖИВ анимацияланған
# атом (§ AnimatedAtomWidget.paint_atom()) — ЕСКІ статикалық baked-pixmap
# жолы ("_draw_home") ЕНДІ paintEvent-те "home" үшін мүлде шақырылмайды
# (функцияның өзі, тестке/анықтамаға арналған дайын drawer ретінде,
# файлда өзгеріссіз қалады — ешбір нақты жол оны ЕНДІ пайдаланбайды).
# Интеграция ӘДЕЙІ AnimatedAtomWidget-ті child ретінде ЕМЕС (§ grab()/
# hit-testing risk-ті болдырмау үшін), ТЕК paint_atom() функциясын осы
# файлдың ӨЗ paintEvent-інде тікелей шақыру арқылы — дәл СОЛ, әлдеқашан
# тексерілген композиция тетігі (§ модуль docstring-і), тек "home" үшін
# cached pixmap орнына live paint. Басқа 10 санат МҮЛДЕ өзгеріссіз.
_ATOM_UPDATE_INTERVAL_MS = 40  # ~25 FPS, AnimatedAtomWidget-пен БІРДЕЙ

_PIXMAP_SIZE = 320
# Phase 41 background regression fix: 24 -> 8. ExperimentWorkspacePage
# (heat/electricity/electromagnetism/light) графигі/кестесі WorkspaceBackdrop-тың
# іс жүзінде БАРЛЫҚ ауданын жабады — тек шеттегі layout margin-нің ЖІҢІШКЕ
# жолағы (эмпирикалық түрде ~10-20px) ғана нақты бос қалады. Су таңба ӘРҚАШАН
# СОЛ жолақтың ІШІНДЕ, backdrop-тың НАҚТЫ бұрышына мейлінше жақын басталуы
# тиіс — үлкен margin кезінде су таңбаның өзі сол жіңішке жолаққа мүлде
# жетпей, толығымен астыртын мазмұнмен жабылып қалады (§ скриншот аудиті).
_MARGIN = 8
_MIN_DRAW_SIZE = 72
_MAX_DRAW_SIZE = 260

# Phase 41 background regression fix: heat/electricity/electromagnetism/light
# категориялары ТЕК ExperimentWorkspacePage-те (§ resolve_experiment_category)
# көрінеді — сол бет графигі/кестесі толық ауданды алатындықтан, су таңбаның
# ТЕК backdrop-тың нақты бұрышына ЕҢ ЖАҚЫН бөлігі ғана нақты көрінеді. Осы 4
# категорияның сызбасы сондықтан rect-тің толық ауданына ЕМЕС, оның бұрышқа
# анкерленген кіші ішкі аймағына салынады (§ _anchor_bottom_right) — сызу
# логикасының ӨЗІ (пішін геометриясы) өзгермейді, тек оның позициясы/масштабы.
_CORNER_ANCHORED_CATEGORIES = frozenset(
    {"heat", "electricity", "electromagnetism", "light"}
)
_CORNER_ANCHOR_SCALE = 0.62

# Phase 42A: композицияның қабатты "перцептивті күш" диапазоны (§ талап
# етілген approximately 8-12% / 4-8% / 2-5% / 10-16%). ``_PRIMARY_ALPHA``/
# ``_SECONDARY_ALPHA``/``_ACCENT_FILL_ALPHA`` — pixmap-қа "күйдірілетін"
# (0-255) alpha, ал ``_MAIN_COMPOSITE_OPACITY`` — сол кэштелген pixmap
# БҮКІЛІ үшін ортақ, paint-уақытындағы сыртқы composite көбейткіш.
# Түпкілікті перцептивті alpha = (baked_alpha/255) * _MAIN_COMPOSITE_OPACITY.
_MAIN_COMPOSITE_OPACITY = 0.10
_PRIMARY_ALPHA = 255  # -> ~10.0% (талап: негізгі контур 8-12%)
_SECONDARY_ALPHA = 190  # -> ~7.5% (талап: қосалқы геометрия 4-8%)
_ACCENT_FILL_ALPHA = 100  # -> ~3.9% (талап: акцент толтыру 2-5%)

# Phase 41 background regression fix: кез келген санат үшін, ХАТТА ең жіңішке
# (бірнеше пиксельдік) видимая жолақта да, категорияны АЖЫРАТАТЫН БІР
# кепілдендірілген белгі болуы үшін — pixmap-тың НАҚТЫ бұрышында толық
# бояумен (contour емес) кіші дөңгелек "акцент нүкте" салынады. Бас сызба
# (термометр/зигзаг/т.б.) кең орында әдемі көрінеді, ал бұл нүкте ЕҢ тар
# орында да категорияның ӨЗ түсімен әрдайым көрінетін соңғы кепілдік.
# Phase 42A: highlight ретінде оқылуы үшін — енді кэштелген pixmap-тың
# ІШІНДЕ ЕМЕС, paintEvent-те БӨЛЕК (жоғарырақ ``_ACCENT_DOT_OPACITY``
# composite-мен) салынады (§ модуль docstring-і).
_ACCENT_DOT_RADIUS = 9.0
_ACCENT_DOT_INSET = 13.0
_ACCENT_DOT_OPACITY = 0.13  # талап: 10-16%

_NEUTRAL_COLOR = COLOR_TEXT_SECONDARY

# Phase 41 background regression fix: бұрын тек 4 модуль категориясының
# (heat/electricity/electromagnetism/light) өз түсі болатын, ал қалған 8
# категория (соның ішінде "laboratory" — каталог беті, ең жиі көрінетін)
# бәрі бірдей ``_NEUTRAL_COLOR`` (сұр) түспен салынатын — 4% opacity-де
# нәтижесінде әр түрлі пішіндер де бір-біріне ұқсас "күңгірт дақ" болып
# көрінетін (§ пайдаланушының "always shows the same faint trapezoid"
# сипаттамасы). Әр категорияға ӨЗ, БІР-БІРІНЕН НАҚТЫ АЖЫРАТЫЛАТЫН түс
# беру — тек осы файлдағы decorative watermark константасы, ThemeManager-дің
# нақты UI түс жүйесін өзгертпейді/кеңейтпейді. Phase 42A: осы мәндер
# ӨЗГЕРТІЛМЕЙДІ (§ "Use the project's existing color constants where
# possible. Do not introduce a new global color system.").
_CATEGORY_STROKE_COLOR: dict[str, str] = {
    "heat": COLOR_SECTION_HEAT,
    "electricity": COLOR_SECTION_ELECTRICITY,
    "electromagnetism": COLOR_SECTION_ELECTROMAGNETISM,
    "light": COLOR_SECTION_LIGHT,
    "home": "#37474F",
    "laboratory": "#F9A825",
    "results": "#00838F",
    "feedback": "#AD1457",
    "devices": "#5D4037",
    "analytics": "#3949AB",
    "help": "#8D6E63",
}


class WorkspaceBackdrop(QWidget):
    """Жұмыс кеңістігі ``QStackedWidget``-ін орайтын, секцияға тәуелді
    жеңіл су таңба фонын салатын контейнер.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("WorkspaceBackdrop")
        # Меншікті paintEvent толық бақылауда болу үшін — Qt-тың QSS-
        # негізді автоматты фон бояуы бұл виджетке ЕШҚАШАН араласпайды.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        # ЕСКЕРТУ (Phase 41 кейінгі инцидент): ``WA_TransparentForMouseEvents``
        # БҰРЫН осында орнатылған еді ("су таңба тінтуір оқиғасын
        # ұстамауы керек" деген ниетпен), БІРАҚ бұл КАТАСТРОФАЛЫҚ регрессия
        # тудырды — Qt-тың нақты (screen-coordinate негізді) hit-testing
        # алгоритмі бұл атрибуты бар виджеттің ТҮГЕЛ ішкі ағашын (яғни
        # ``self._stack`` және ОНЫҢ ІШІНДЕГІ БАРЛЫҚ бет/батырма) аталық
        # деңгейден (``QSplitter``) іздегенде толығымен ЕШКІМГЕ жеткізбей
        # аттап кетеді — тіпті НАҚТЫ көрінетін, дұрыс орналасқан батырмалар
        # да СЫРТТАН еш click алмай қалды (тек виджетке ТІКЕЛЕЙ бағытталған
        # синтетикалық ``QTest.mouseClick(widget, ...)`` бұл tekserуден
        # аттап өтеді, сондықтан автоматтандырылған тестерде БАЙҚАЛМАДЫ).
        # WorkspaceBackdrop ``self._stack``-тың АТАЛЫҒЫ (parent), ҮСТІНЕ
        # салынған sibling ЕМЕС — Qt-та бала виджеттер өз аймағында
        # аталықтан бұрын оқиғаны алады, сондықтан бұл атрибут ЕШҚАШАН
        # қажет болмаған (§ "non-interactive" талабы parent-тің өз
        # paintEvent-і тек фон салатынымен, ешбір mouse handler
        # анықтамайтынымен ӘЛДЕҚАШАН қамтамасыз етілген). Phase 42A:
        # осы шешім ӨЗГЕРТІЛМЕЙДІ — тек paint-only редизайн.
        self._category = CATEGORY_DEFAULT
        self._pixmap_cache: dict[str, QPixmap] = {}
        # Phase 12: "home" санатының тірі атом анимациясы — тек СОЛ санат
        # белсенді ЖӘНЕ виджет көрінгенде жұмыс істейді (§ "pause or stop
        # its timer if practical").
        self._atom_start_time = time.monotonic()
        self._atom_timer = QTimer(self)
        self._atom_timer.setInterval(_ATOM_UPDATE_INTERVAL_MS)
        self._atom_timer.timeout.connect(self.update)

    def current_category(self) -> str:
        return self._category

    def set_category(self, category: str) -> None:
        """Ағымдағы секцияны ауыстырады. Белгісіз кілт қауіпсіз түрде
        ``CATEGORY_DEFAULT``-қа сай келеді. Санат НАҚТЫ ӨЗГЕРМЕСЕ —
        ЕШБІР ``update()`` шақырылмайды (§ "reuse the same background
        across pages within the same major section" / "must not trigger
        unnecessary background repaints" — Phase 41 approval).
        """
        resolved = category if category in ALL_CATEGORIES else CATEGORY_DEFAULT
        if resolved == self._category:
            return
        self._category = resolved
        self._sync_atom_timer()
        self.update()

    def showEvent(self, event) -> None:  # noqa: N802 (Qt override name)
        super().showEvent(event)
        self._sync_atom_timer()

    def hideEvent(self, event) -> None:  # noqa: N802 (Qt override name)
        super().hideEvent(event)
        self._atom_timer.stop()

    def _sync_atom_timer(self) -> None:
        # Phase 15: "laboratory" (флакон/колба су таңбасы) ЕНДІ "home"
        # атомымен БІРДЕЙ, ортақ таймерді пайдаланады (§ "reuse the
        # existing single shared timer where possible" — екі санаттың
        # БІРІ ғана бір мезгілде белсенді бола алады, сондықтан екінші
        # таймер қажет емес).
        should_run = (
            self._category in (CATEGORY_HOME, CATEGORY_LABORATORY)
            and self.isVisible()
            and motion.MOTION_ENABLED
        )
        if should_run and not self._atom_timer.isActive():
            self._atom_timer.start()
        elif not should_run and self._atom_timer.isActive():
            self._atom_timer.stop()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override name)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor(theme_color("COLOR_BACKGROUND")))
        if self._category == CATEGORY_HOME:
            self._paint_atom(painter)
        elif self._category == CATEGORY_LABORATORY:
            self._paint_flask(painter)
        else:
            self._paint_watermark(painter)
        painter.end()

    # ---- Су таңбаны позициялау/масштабтау -----------------------------

    def _compute_target_rect(self) -> QRect | None:
        available_size = min(self.width(), self.height())
        if available_size <= 0:
            return None
        draw_size = max(_MIN_DRAW_SIZE, min(_MAX_DRAW_SIZE, int(available_size * 0.4)))
        if draw_size + _MARGIN > self.width() or draw_size + _MARGIN > self.height():
            draw_size = max(1, min(self.width(), self.height()) - _MARGIN)
        if draw_size <= 0:
            return None
        return QRect(
            self.width() - draw_size - _MARGIN,
            self.height() - draw_size - _MARGIN,
            draw_size,
            draw_size,
        )

    def _paint_atom(self, painter: QPainter) -> None:
        target = self._compute_target_rect()
        if target is None:
            return
        elapsed_ms = (time.monotonic() - self._atom_start_time) * 1000.0
        paint_atom(
            painter,
            QRectF(target),
            elapsed_ms,
            opacity=_MAIN_COMPOSITE_OPACITY,
            animated=self._atom_timer.isActive(),
        )

    def _paint_flask(self, painter: QPainter) -> None:
        target = self._compute_target_rect()
        if target is None:
            return
        elapsed_ms = (time.monotonic() - self._atom_start_time) * 1000.0
        # Ескі baked-pixmap жолы (§ _render_category_pixmap) флакон
        # геометриясын 320px canvas ІШІНДЕГІ 20px жиекпен (¬ 6.25%) сызатын
        # — НАҚТЫ СОЛ пропорцияны сақтау үшін (§ "EXACT same position/
        # size/geometry" талабы) осы қатынасты ӘДЕЙІ қайта қолданамыз,
        # тек ТІКЕЛЕЙ target үстіне (кэшсіз, paint_atom-мен БІРДЕЙ тәсіл).
        inset = target.width() * (20.0 / _PIXMAP_SIZE)
        drawing_rect = QRectF(target).adjusted(inset, inset, -inset, -inset)
        color = QColor(_CATEGORY_STROKE_COLOR.get(self._category, _NEUTRAL_COLOR))
        paint_flask(
            painter,
            drawing_rect,
            elapsed_ms,
            color=color,
            opacity=_MAIN_COMPOSITE_OPACITY,
            animated=self._atom_timer.isActive(),
        )
        self._paint_accent_dot(painter, target)

    def _paint_watermark(self, painter: QPainter) -> None:
        target = self._compute_target_rect()
        if target is None:
            return

        pixmap = self._pixmap_for_category(self._category)
        painter.save()
        painter.setOpacity(_MAIN_COMPOSITE_OPACITY)
        painter.drawPixmap(target, pixmap, pixmap.rect())
        painter.restore()

        self._paint_accent_dot(painter, target)

    def _paint_accent_dot(self, painter: QPainter, target: QRect) -> None:
        """Кэштелген сахна pixmap-ынан БӨЛЕК, жоғарырақ composite-пен
        салынатын кіші "highlight" нүкте (§ модуль docstring-і, Phase
        42A). Геометриясы арзан (бір ``drawEllipse``), сондықтан кэштеу
        қажет емес — ``_MAIN_COMPOSITE_OPACITY``-мен салынатын негізгі
        сахнаның қымбат бөлігі (сызу логикасы) әлі де толық кэштеледі.
        """
        if target.width() <= 0:
            return
        scale = target.width() / _PIXMAP_SIZE
        inset = _ACCENT_DOT_INSET * scale
        radius = max(1.0, _ACCENT_DOT_RADIUS * scale)
        center = QPointF(target.right() - inset, target.bottom() - inset)
        color = QColor(_CATEGORY_STROKE_COLOR.get(self._category, _NEUTRAL_COLOR))

        painter.save()
        painter.setOpacity(_ACCENT_DOT_OPACITY)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(center, radius, radius)
        painter.restore()

    def _pixmap_for_category(self, category: str) -> QPixmap:
        cached = self._pixmap_cache.get(category)
        if cached is not None:
            return cached
        pixmap = _render_category_pixmap(category)
        self._pixmap_cache[category] = pixmap
        return pixmap


# ---- Ортақ сызу көмекшілері (Phase 42A) ------------------------------
#
# Барлық drawer-лер осы кіші, қайта пайдаланылатын көмекшілер арқылы
# қабатты alpha-ны ("primary"/"secondary"/"accent fill") pixmap-қа
# күйдіреді — сыртқы composite opacity (``_MAIN_COMPOSITE_OPACITY``)
# кейін осыны БІРЫҢҒАЙ көбейтеді (§ модуль docstring-і).


def _tinted(color: QColor, alpha: int) -> QColor:
    tinted = QColor(color)
    tinted.setAlpha(alpha)
    return tinted


def _pen(color: QColor, alpha: int, width: float) -> QPen:
    pen = QPen(_tinted(color, alpha))
    pen.setWidthF(width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def _set_outline(painter: QPainter, color: QColor, alpha: int, width: float = 5.0) -> None:
    """Painter-ды "негізгі контур" күйіне келтіреді: белгілі alpha-дағы
    pen, бояусыз brush."""
    painter.setPen(_pen(color, alpha, width))
    painter.setBrush(Qt.BrushStyle.NoBrush)


def _fill_circle(
    painter: QPainter, center: QPointF, radius: float, color: QColor, alpha: int
) -> None:
    """Бөлшек/түйін/көпіршік сияқты кіші толтырылған дөңгелектер үшін
    ортақ көмекші."""
    painter.save()
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(_tinted(color, alpha)))
    painter.drawEllipse(center, radius, radius)
    painter.restore()


def _fill_path(painter: QPainter, path: QPainterPath, color: QColor, alpha: int) -> None:
    """Сұйықтық деңгейі/жұмсақ аймақ сияқты жартылай мөлдір толтыру
    пішіндері үшін ортақ көмекші."""
    painter.save()
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(_tinted(color, alpha)))
    painter.drawPath(path)
    painter.restore()


def _draw_cross_sparkle(
    painter: QPainter, center: QPointF, size: float, color: QColor, alpha: int
) -> None:
    """Кіші "жарқылдақ" акцент белгісі (help категориясы үшін) — плюс
    тәрізді екі қысқа сызық."""
    painter.save()
    painter.setPen(_pen(color, alpha, max(1.5, size * 0.5)))
    painter.drawLine(QPointF(center.x() - size, center.y()), QPointF(center.x() + size, center.y()))
    painter.drawLine(QPointF(center.x(), center.y() - size), QPointF(center.x(), center.y() + size))
    painter.restore()


# ---- Категория сызу-графикасы -----------------------------------------


def _render_category_pixmap(category: str) -> QPixmap:
    pixmap = QPixmap(_PIXMAP_SIZE, _PIXMAP_SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    color = QColor(_CATEGORY_STROKE_COLOR.get(category, _NEUTRAL_COLOR))

    rect = QRectF(20, 20, _PIXMAP_SIZE - 40, _PIXMAP_SIZE - 40)
    if category in _CORNER_ANCHORED_CATEGORIES:
        rect = _anchor_bottom_right(rect, _CORNER_ANCHOR_SCALE)
    drawer = _CATEGORY_DRAWERS.get(category, _draw_default)
    drawer(painter, rect, color)

    painter.end()
    return pixmap


def _anchor_bottom_right(rect: QRectF, scale: float) -> QRectF:
    """``rect``-тің бұрышқа анкерленген, кішірейтілген ішкі аймағын
    қайтарады — сызу логикасының ӨЗІ (drawer функциясы) өзгермейді, тек
    оның қай аймаққа салынатыны.
    """
    width = rect.width() * scale
    height = rect.height() * scale
    return QRectF(rect.right() - width, rect.bottom() - height, width, height)


def _draw_home(painter: QPainter, rect: QRectF, color: QColor) -> None:
    """Атом орбитасы: 3 айналдырылған сақина + орталық ядро + бірнеше
    "электрон" бөлшегі (§ "balanced composition, not just one large
    atom symbol")."""
    center = rect.center()
    radius = rect.width() / 2

    _set_outline(painter, color, _PRIMARY_ALPHA, 4.5)
    painter.translate(center)
    for angle in (0, 60, 120):
        painter.save()
        painter.rotate(angle)
        painter.drawEllipse(QRectF(-radius, -radius * 0.4, radius * 2, radius * 0.8))
        painter.restore()
    painter.translate(-center)

    _fill_circle(painter, center, radius * 0.12, color, _PRIMARY_ALPHA)

    for angle_deg, orbit_scale in ((25.0, 1.0), (150.0, 0.82), (255.0, 1.0)):
        rad = math.radians(angle_deg)
        point = QPointF(
            center.x() + radius * orbit_scale * math.cos(rad),
            center.y() + radius * 0.4 * orbit_scale * math.sin(rad),
        )
        _fill_circle(painter, point, radius * 0.06, color, _SECONDARY_ALPHA)


def _draw_laboratory(painter: QPainter, rect: QRectF, color: QColor) -> None:
    """Erlenmeyer колбасы: мойын + денесі + сұйықтық деңгейі + өлшеу
    белгілері + көпіршіктер."""
    neck_width = rect.width() * 0.2
    neck_top = rect.top()
    cx = rect.center().x()
    body_left = QPointF(cx - rect.width() * 0.4, rect.bottom())
    body_right = QPointF(cx + rect.width() * 0.4, rect.bottom())
    neck_left = QPointF(cx - neck_width / 2, neck_top)
    neck_right = QPointF(cx + neck_width / 2, neck_top)

    outline = QPainterPath()
    outline.moveTo(neck_left)
    outline.lineTo(body_left)
    outline.lineTo(body_right)
    outline.lineTo(neck_right)
    outline.closeSubpath()
    _set_outline(painter, color, _PRIMARY_ALPHA, 4.5)
    painter.drawPath(outline)

    liquid_y = rect.bottom() - rect.height() * 0.28
    liquid = QPainterPath()
    liquid.moveTo(QPointF(cx - rect.width() * 0.32, liquid_y))
    liquid.lineTo(QPointF(cx + rect.width() * 0.32, liquid_y))
    liquid.lineTo(body_right)
    liquid.lineTo(body_left)
    liquid.closeSubpath()
    _fill_path(painter, liquid, color, _ACCENT_FILL_ALPHA)

    painter.setPen(_pen(color, _SECONDARY_ALPHA, 3.5))
    painter.drawLine(
        QPointF(cx - rect.width() * 0.32, liquid_y), QPointF(cx + rect.width() * 0.32, liquid_y)
    )

    tick_x = cx + neck_width * 0.9
    for fraction in (0.15, 0.32, 0.49):
        y = neck_top + rect.height() * fraction
        painter.drawLine(QPointF(tick_x, y), QPointF(tick_x + rect.width() * 0.08, y))

    for dx, dy, r in ((-0.1, 0.1, 0.032), (0.08, 0.16, 0.04), (-0.02, 0.05, 0.026)):
        bubble_center = QPointF(cx + rect.width() * dx, rect.bottom() - rect.height() * dy)
        _fill_circle(painter, bubble_center, rect.width() * r, color, _SECONDARY_ALPHA)


# Phase 15 ("Flask Background Animation ONLY"): "laboratory" санатының ЖИВ
# нұсқасы — ``paint_atom()``-мен БІРДЕЙ келісім бойынша ("home" санаты
# үшін, § animated_atom_widget.py): контур/мойын/белгі сызықтары
# ``_draw_laboratory``-мен пиксель ДӘЛ БІРДЕЙ (өзгермейді, көшірілген,
# ЕМЕС қайта есептелген геометрия), тек сұйықтық беті мен көпіршіктер
# ЖҰМСАҚ анимацияланады. ``animated=False`` кезінде (§ MOTION_ENABLED
# сөндірулі) толқын амплитудасы 0-ге тең және көпіршіктер ӨЗ бастапқы
# (dx, dy) позициясында қалады — сондықтан статикалық сурет ескі
# baked-pixmap-пен ДӘЛ БІРДЕЙ болып қалады (§ "static illustration"
# талабы).
_FLASK_LIQUID_CYCLE_MS = 6500.0  # 5-8с диапазонының ортасы
_FLASK_LIQUID_WAVE_FRACTION = 0.015  # rect биіктігінен — "бірнеше пиксель" ғана
_FLASK_BUBBLE_MIN_DY = 0.02
_FLASK_BUBBLE_MAX_DY = 0.26
# (dx, бастапқы dy, r, цикл_ms) — dx/r ЕСКІ статикалық үш көпіршікпен
# БІРДЕЙ, циклдер сәл ӘРТҮРЛІ жылдамдық/фаза үшін (§ "slightly different
# speeds/phases").
_FLASK_BUBBLES = (
    (-0.10, 0.10, 0.032, 4600.0),
    (0.08, 0.16, 0.040, 5200.0),
    (-0.02, 0.05, 0.026, 4900.0),
)


def paint_flask(
    painter: QPainter,
    rect: QRectF,
    elapsed_ms: float,
    *,
    color: QColor,
    opacity: float,
    animated: bool,
) -> None:
    """Erlenmeyer колбасының ЖИВ нұсқасы: контур/мойын/белгілер
    ``_draw_laboratory``-мен ДӘЛ БІРДЕЙ, тек сұйықтық беті/көпіршіктер
    анимацияланады."""
    painter.save()
    painter.setOpacity(opacity)

    neck_width = rect.width() * 0.2
    neck_top = rect.top()
    cx = rect.center().x()
    body_left = QPointF(cx - rect.width() * 0.4, rect.bottom())
    body_right = QPointF(cx + rect.width() * 0.4, rect.bottom())
    neck_left = QPointF(cx - neck_width / 2, neck_top)
    neck_right = QPointF(cx + neck_width / 2, neck_top)

    outline = QPainterPath()
    outline.moveTo(neck_left)
    outline.lineTo(body_left)
    outline.lineTo(body_right)
    outline.lineTo(neck_right)
    outline.closeSubpath()
    _set_outline(painter, color, _PRIMARY_ALPHA, 4.5)
    painter.drawPath(outline)

    wave_offset = 0.0
    if animated:
        phase = (elapsed_ms / _FLASK_LIQUID_CYCLE_MS) * 2.0 * math.pi
        wave_offset = math.sin(phase) * rect.height() * _FLASK_LIQUID_WAVE_FRACTION

    liquid_y = rect.bottom() - rect.height() * 0.28 + wave_offset
    liquid = QPainterPath()
    liquid.moveTo(QPointF(cx - rect.width() * 0.32, liquid_y))
    liquid.lineTo(QPointF(cx + rect.width() * 0.32, liquid_y))
    liquid.lineTo(body_right)
    liquid.lineTo(body_left)
    liquid.closeSubpath()
    _fill_path(painter, liquid, color, _ACCENT_FILL_ALPHA)

    painter.setPen(_pen(color, _SECONDARY_ALPHA, 3.5))
    painter.drawLine(
        QPointF(cx - rect.width() * 0.32, liquid_y), QPointF(cx + rect.width() * 0.32, liquid_y)
    )

    tick_x = cx + neck_width * 0.9
    for fraction in (0.15, 0.32, 0.49):
        y = neck_top + rect.height() * fraction
        painter.drawLine(QPointF(tick_x, y), QPointF(tick_x + rect.width() * 0.08, y))

    span = _FLASK_BUBBLE_MAX_DY - _FLASK_BUBBLE_MIN_DY
    for dx, base_dy, r, cycle_ms in _FLASK_BUBBLES:
        if animated:
            phase0 = (base_dy - _FLASK_BUBBLE_MIN_DY) / span
            t = (elapsed_ms / cycle_ms + phase0) % 1.0
            dy = _FLASK_BUBBLE_MIN_DY + span * t
            fade = 1.0
            if t < 0.06:
                fade = t / 0.06
            elif t > 0.94:
                fade = (1.0 - t) / 0.06
        else:
            dy = base_dy
            fade = 1.0
        bubble_center = QPointF(cx + rect.width() * dx, rect.bottom() - rect.height() * dy)
        bubble_alpha = max(0, int(_SECONDARY_ALPHA * fade))
        if bubble_alpha > 0:
            _fill_circle(painter, bubble_center, rect.width() * r, color, bubble_alpha)

    painter.restore()


def _draw_heat(painter: QPainter, rect: QRectF, color: QColor) -> None:
    """Термометр (діңгек + шар) + үш жұмсақ көтерілу толқыны + кіші
    температура бөлшектері."""
    stem_width = rect.width() * 0.22
    stem_top = rect.top()
    stem_bottom = rect.bottom() - rect.width() * 0.3
    stem_left = rect.center().x() - stem_width / 2

    _set_outline(painter, color, _PRIMARY_ALPHA, 5.5)
    painter.drawRoundedRect(
        QRectF(stem_left, stem_top, stem_width, stem_bottom - stem_top), stem_width / 2, stem_width / 2
    )
    bulb_radius = rect.width() * 0.28
    bulb_center = QPointF(rect.center().x(), rect.bottom() - bulb_radius)
    painter.drawEllipse(bulb_center, bulb_radius, bulb_radius)
    _fill_circle(painter, bulb_center, bulb_radius * 0.62, color, _ACCENT_FILL_ALPHA)

    painter.setPen(_pen(color, _SECONDARY_ALPHA, 3.0))
    wave_x = rect.left() + rect.width() * 0.08
    for index, amplitude in enumerate((0.07, 0.06, 0.05)):
        y0 = rect.top() + rect.height() * (0.12 + index * 0.14)
        path = QPainterPath()
        path.moveTo(wave_x, y0)
        path.cubicTo(
            QPointF(wave_x + rect.width() * amplitude, y0 - rect.height() * 0.05),
            QPointF(wave_x - rect.width() * amplitude, y0 + rect.height() * 0.05),
            QPointF(wave_x, y0 + rect.height() * 0.12),
        )
        painter.drawPath(path)

    for dx, dy, r in ((0.3, -0.08, 0.03), (0.38, 0.06, 0.024)):
        center = QPointF(rect.center().x() + rect.width() * dx, rect.top() + rect.height() * (0.28 + dy))
        _fill_circle(painter, center, rect.width() * r, color, _SECONDARY_ALPHA)


def _draw_electricity(painter: QPainter, rect: QRectF, color: QColor) -> None:
    """Тізбек жолы: сым + резистор зигзагы + екі түйін + найзағай
    акценті (§ "avoid a plain zigzag-only symbol")."""
    mid_y = rect.center().y()
    zig_left = rect.left() + rect.width() * 0.16
    zig_right = rect.right() - rect.width() * 0.16

    path = QPainterPath()
    path.moveTo(rect.left(), mid_y)
    path.lineTo(zig_left, mid_y)
    segments = 5
    step = (zig_right - zig_left) / segments
    amplitude = rect.height() * 0.24
    for index in range(1, segments + 1):
        x = zig_left + step * index
        y = mid_y + (amplitude if index % 2 == 1 else -amplitude) if index < segments else mid_y
        path.lineTo(x, y)
    path.lineTo(rect.right(), mid_y)

    _set_outline(painter, color, _PRIMARY_ALPHA, 5.0)
    painter.drawPath(path)

    _fill_circle(painter, QPointF(rect.left(), mid_y), rect.width() * 0.035, color, _SECONDARY_ALPHA)
    _fill_circle(painter, QPointF(rect.right(), mid_y), rect.width() * 0.035, color, _SECONDARY_ALPHA)

    bolt = QPainterPath()
    bx = rect.left() + rect.width() * 0.18
    by = rect.top()
    bolt.moveTo(bx, by)
    bolt.lineTo(bx - rect.width() * 0.06, by + rect.height() * 0.24)
    bolt.lineTo(bx + rect.width() * 0.02, by + rect.height() * 0.22)
    bolt.lineTo(bx - rect.width() * 0.07, by + rect.height() * 0.46)
    painter.setPen(_pen(color, _SECONDARY_ALPHA, 2.5))
    painter.drawPath(bolt)


def _draw_electromagnetism(painter: QPainter, rect: QRectF, color: QColor) -> None:
    """U-тәрізді таяқша магнит + өріс доғалары + кіші бағыттық
    бөлшектер (§ electricity-ден визуалды ажыратылған)."""
    bar_width = rect.width() * 0.22
    top = rect.top()
    bottom = rect.bottom() - rect.height() * 0.25

    _set_outline(painter, color, _PRIMARY_ALPHA, 5.5)
    painter.drawLine(QPointF(rect.left() + bar_width / 2, top), QPointF(rect.left() + bar_width / 2, bottom))
    painter.drawLine(QPointF(rect.right() - bar_width / 2, top), QPointF(rect.right() - bar_width / 2, bottom))
    bridge = QPainterPath()
    bridge.moveTo(rect.left() + bar_width / 2, bottom)
    bridge.quadTo(rect.center().x(), rect.bottom(), rect.right() - bar_width / 2, bottom)
    painter.drawPath(bridge)

    painter.setPen(_pen(color, _SECONDARY_ALPHA, 3.0))
    for offset in (0.12, 0.26):
        arc_rect = rect.adjusted(
            -rect.width() * offset, -rect.height() * offset, rect.width() * offset, rect.height() * offset
        )
        painter.drawArc(arc_rect, 30 * 16, 120 * 16)

    for dx, dy in ((-0.26, -0.16), (0.0, -0.26), (0.26, -0.16)):
        center = QPointF(rect.center().x() + rect.width() * dx, rect.center().y() + rect.height() * dy)
        _fill_circle(painter, center, rect.width() * 0.024, color, _SECONDARY_ALPHA)


def _draw_light(painter: QPainter, rect: QRectF, color: QColor) -> None:
    """Дөңес линза (vesica пішіні) + сынатын сәулелер + фокус нүктесі +
    жарық көзі шеңбері."""
    cx = rect.center().x()
    top = QPointF(cx, rect.top())
    bottom = QPointF(cx, rect.bottom())
    bulge = rect.width() * 0.2

    lens = QPainterPath()
    lens.moveTo(top)
    lens.quadTo(QPointF(cx + bulge, rect.center().y()), bottom)
    lens.quadTo(QPointF(cx - bulge, rect.center().y()), top)
    _fill_path(painter, lens, color, _ACCENT_FILL_ALPHA)
    _set_outline(painter, color, _PRIMARY_ALPHA, 4.5)
    painter.drawPath(lens)

    focal = QPointF(rect.right(), rect.center().y())
    source = QPointF(rect.left(), rect.center().y())
    painter.setPen(_pen(color, _SECONDARY_ALPHA, 2.5))
    for dy in (-0.28, 0.28):
        entry = QPointF(rect.left(), rect.center().y() + rect.height() * dy)
        lens_point = QPointF(cx, rect.center().y() + rect.height() * dy * 0.4)
        painter.drawLine(entry, lens_point)
        painter.drawLine(lens_point, focal)
    painter.drawLine(source, focal)

    _fill_circle(painter, focal, rect.width() * 0.035, color, _SECONDARY_ALPHA)
    _fill_circle(painter, source, rect.width() * 0.05, color, _SECONDARY_ALPHA)


def _draw_results(painter: QPainter, rect: QRectF, color: QColor) -> None:
    """Баған диаграмма + үрдіс сызығы + деректер нүктелері + жұмсақ
    ось белгісі."""
    bar_count = 4
    bar_width = rect.width() / (bar_count * 2)
    heights = (0.4, 0.7, 0.5, 0.9)
    tops: list[QPointF] = []

    _set_outline(painter, color, _PRIMARY_ALPHA, 3.5)
    for index, height_fraction in enumerate(heights):
        x = rect.left() + index * (bar_width * 2) + bar_width * 0.5
        bar_height = rect.height() * height_fraction
        bar_rect = QRectF(x, rect.bottom() - bar_height, bar_width, bar_height)
        painter.drawRoundedRect(bar_rect, bar_width * 0.15, bar_width * 0.15)
        tops.append(QPointF(x + bar_width / 2, rect.bottom() - bar_height))

    painter.setPen(_pen(color, _SECONDARY_ALPHA, 2.5))
    trend = QPainterPath()
    trend.moveTo(tops[0])
    for point in tops[1:]:
        trend.lineTo(point)
    painter.drawPath(trend)
    for point in tops:
        _fill_circle(painter, point, rect.width() * 0.02, color, _SECONDARY_ALPHA)

    painter.setPen(_pen(color, _ACCENT_FILL_ALPHA, 2.0))
    painter.drawLine(QPointF(rect.left(), rect.bottom()), QPointF(rect.right(), rect.bottom()))


def _draw_feedback(painter: QPainter, rect: QRectF, color: QColor) -> None:
    """Сөйлеу көпіршігі + белгі (check mark) + кіші жауап көпіршігі +
    қысқа абстрактілі мәтін жолдары."""
    bubble_rect = QRectF(rect.left(), rect.top(), rect.width() * 0.78, rect.height() * 0.62)
    _set_outline(painter, color, _PRIMARY_ALPHA, 4.5)
    painter.drawRoundedRect(bubble_rect, bubble_rect.width() * 0.16, bubble_rect.width() * 0.16)

    tail = QPainterPath()
    tail.moveTo(bubble_rect.left() + bubble_rect.width() * 0.25, bubble_rect.bottom())
    tail.lineTo(bubble_rect.left() + bubble_rect.width() * 0.15, bubble_rect.bottom() + rect.height() * 0.12)
    tail.lineTo(bubble_rect.left() + bubble_rect.width() * 0.4, bubble_rect.bottom())
    painter.drawPath(tail)

    check = QPainterPath()
    cx, cy = bubble_rect.center().x(), bubble_rect.center().y()
    check.moveTo(cx - bubble_rect.width() * 0.18, cy)
    check.lineTo(cx - bubble_rect.width() * 0.04, cy + bubble_rect.height() * 0.22)
    check.lineTo(cx + bubble_rect.width() * 0.24, cy - bubble_rect.height() * 0.22)
    painter.drawPath(check)

    small_rect = QRectF(
        rect.right() - rect.width() * 0.42,
        rect.bottom() - rect.height() * 0.34,
        rect.width() * 0.42,
        rect.height() * 0.3,
    )
    painter.setPen(_pen(color, _SECONDARY_ALPHA, 2.5))
    painter.drawRoundedRect(small_rect, small_rect.height() * 0.3, small_rect.height() * 0.3)
    for fraction in (0.36, 0.64):
        y = small_rect.top() + small_rect.height() * fraction
        painter.drawLine(
            QPointF(small_rect.left() + small_rect.width() * 0.16, y),
            QPointF(small_rect.right() - small_rect.width() * 0.16, y),
        )


def _draw_devices(painter: QPainter, rect: QRectF, color: QColor) -> None:
    """USB коннекторы (корпус + екі шпилька) + кіші тізбек-тақта ізі +
    екі күй-индикаторы."""
    body = QRectF(rect.left(), rect.center().y() - rect.height() * 0.15, rect.width() * 0.72, rect.height() * 0.3)
    _set_outline(painter, color, _PRIMARY_ALPHA, 4.5)
    painter.drawRoundedRect(body, body.height() * 0.3, body.height() * 0.3)
    prong_top = body.top() - rect.height() * 0.2
    painter.drawLine(
        QPointF(body.left() + body.width() * 0.3, body.top()), QPointF(body.left() + body.width() * 0.3, prong_top)
    )
    painter.drawLine(
        QPointF(body.left() + body.width() * 0.6, body.top()), QPointF(body.left() + body.width() * 0.6, prong_top)
    )

    trace = QPainterPath()
    trace.moveTo(body.right(), body.center().y())
    trace.lineTo(body.right() + rect.width() * 0.1, body.center().y())
    trace.lineTo(body.right() + rect.width() * 0.1, body.center().y() + rect.height() * 0.2)
    trace.lineTo(rect.right(), body.center().y() + rect.height() * 0.2)
    painter.setPen(_pen(color, _SECONDARY_ALPHA, 2.5))
    painter.drawPath(trace)

    _fill_circle(
        painter,
        QPointF(body.right() + rect.width() * 0.1, body.center().y() + rect.height() * 0.2),
        rect.width() * 0.022,
        color,
        _SECONDARY_ALPHA,
    )
    _fill_circle(
        painter,
        QPointF(rect.right(), body.center().y() + rect.height() * 0.2),
        rect.width() * 0.022,
        color,
        _SECONDARY_ALPHA,
    )


def _draw_analytics(painter: QPainter, rect: QRectF, color: QColor) -> None:
    """Сызықтық график + шашыранды нүктелер + жұмсақ тор + үрдіс
    көрсеткіші."""
    painter.setPen(_pen(color, _ACCENT_FILL_ALPHA, 1.5))
    for fraction in (0.25, 0.5, 0.75):
        y = rect.top() + rect.height() * fraction
        painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))

    points = [
        QPointF(rect.left(), rect.bottom() - rect.height() * 0.2),
        QPointF(rect.left() + rect.width() * 0.3, rect.bottom() - rect.height() * 0.5),
        QPointF(rect.left() + rect.width() * 0.6, rect.bottom() - rect.height() * 0.35),
        QPointF(rect.right() - rect.width() * 0.08, rect.top() + rect.height() * 0.15),
    ]
    _set_outline(painter, color, _PRIMARY_ALPHA, 3.0)
    trend = QPainterPath()
    trend.moveTo(points[0])
    for point in points[1:]:
        trend.lineTo(point)
    painter.drawPath(trend)
    for point in points:
        _fill_circle(painter, point, rect.width() * 0.022, color, _SECONDARY_ALPHA)

    tip = points[-1]
    previous = points[-2]
    direction = QPointF(tip.x() - previous.x(), tip.y() - previous.y())
    length = math.hypot(direction.x(), direction.y()) or 1.0
    ux, uy = direction.x() / length, direction.y() / length
    arrow = rect.width() * 0.05
    left_wing = QPointF(tip.x() - ux * arrow - uy * arrow * 0.6, tip.y() - uy * arrow + ux * arrow * 0.6)
    right_wing = QPointF(tip.x() - ux * arrow + uy * arrow * 0.6, tip.y() - uy * arrow - ux * arrow * 0.6)
    painter.setPen(_pen(color, _SECONDARY_ALPHA, 2.2))
    painter.drawLine(tip, left_wing)
    painter.drawLine(tip, right_wing)


def _draw_help(painter: QPainter, rect: QRectF, color: QColor) -> None:
    """Сұрақ белгісі бар жұмсақ шеңбер + кіші кітап/ақпарат-карта
    контуры + жарқылдақ белгілер."""
    circle_rect = QRectF(rect.left(), rect.top(), rect.width() * 0.7, rect.height() * 0.7)
    _set_outline(painter, color, _PRIMARY_ALPHA, 4.5)
    painter.drawEllipse(circle_rect)

    font = painter.font()
    font.setPointSizeF(max(6.0, circle_rect.height() * 0.4))
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(_pen(color, _PRIMARY_ALPHA, 1.0))
    painter.drawText(circle_rect, Qt.AlignmentFlag.AlignCenter, "?")

    book_rect = QRectF(
        rect.right() - rect.width() * 0.4, rect.bottom() - rect.height() * 0.3, rect.width() * 0.4, rect.height() * 0.22
    )
    painter.setPen(_pen(color, _SECONDARY_ALPHA, 2.5))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(book_rect, book_rect.height() * 0.15, book_rect.height() * 0.15)
    painter.drawLine(QPointF(book_rect.center().x(), book_rect.top()), QPointF(book_rect.center().x(), book_rect.bottom()))

    for dx, dy, size in ((0.06, -0.1, 0.03), (0.18, -0.02, 0.02)):
        center = QPointF(circle_rect.right() + rect.width() * dx, circle_rect.top() + rect.height() * dy)
        _draw_cross_sparkle(painter, center, rect.width() * size, color, _SECONDARY_ALPHA)


def _draw_default(painter: QPainter, rect: QRectF, color: QColor) -> None:
    """Бейтарап абстрактілі геометрия: орталық түйін + байланыс
    сызықтары + кіші түйіндер (§ "must not look identical to another
    category")."""
    center_node = (QPointF(rect.center().x(), rect.center().y()), rect.width() * 0.16)
    satellites = (
        (QPointF(rect.left() + rect.width() * 0.15, rect.top() + rect.height() * 0.2), rect.width() * 0.08),
        (QPointF(rect.right() - rect.width() * 0.1, rect.top() + rect.height() * 0.35), rect.width() * 0.07),
        (QPointF(rect.left() + rect.width() * 0.2, rect.bottom() - rect.height() * 0.15), rect.width() * 0.06),
    )

    painter.setPen(_pen(color, _SECONDARY_ALPHA, 2.2))
    for center, _radius in satellites:
        painter.drawLine(center_node[0], center)

    _set_outline(painter, color, _PRIMARY_ALPHA, 3.5)
    painter.drawEllipse(center_node[0], center_node[1], center_node[1])
    for center, radius in satellites:
        _fill_circle(painter, center, radius, color, _SECONDARY_ALPHA)


_CATEGORY_DRAWERS = {
    "home": _draw_home,
    "heat": _draw_heat,
    "electricity": _draw_electricity,
    "electromagnetism": _draw_electromagnetism,
    "light": _draw_light,
    "laboratory": _draw_laboratory,
    "results": _draw_results,
    "feedback": _draw_feedback,
    "devices": _draw_devices,
    "analytics": _draw_analytics,
    "help": _draw_help,
    "default": _draw_default,
}
