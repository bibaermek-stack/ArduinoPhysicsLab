"""PlotCrosshair — жалғыз ``pg.PlotWidget``-ке арналған ғылыми crosshair
+ coordinate readout helper-і (Phase 33A, Scientific Graph Core).

Бұл класс ЕШБІР физикалық есептеу жасамайды және ЕШБІР жаңа Measurement/
дерек жасамайды — тек pyqtgraph-тың ``InfiniteLine``/``TextItem``/
``SignalProxy`` компоненттері арқылы, шақырушы берген (``get_curve_data``)
НАҚТЫ деректерден ЕҢ ЖАҚЫН үлгіні тауып көрсетеді. Интерполяция/фейк
нүкте ЕШҚАШАН жасалмайды — тек нақты сақталған (x, y) жұптарының
арасынан ең жақыны таңдалады.

``LiveGraphWidget`` бір plot widget (single режим) немесе бірнеше
(stacked режим) үшін осы класстың бір-бір данасын жасайды.
Синхрондалған crosshair (stacked топтар үшін) ``on_hover``/``show_at_x``
арқылы сыртта (``LiveGraphWidget``-те) координацияланады — бұл класс
өзі басқа plot widget-тер жайлы ЕШТЕҢЕ білмейді.
"""

from __future__ import annotations

import time
from collections.abc import Callable

import pyqtgraph as pg
from PySide6.QtCore import Qt

from domain.services.graph_analysis import nearest_index
from ui.themes.theme_manager import COLOR_BORDER, COLOR_SURFACE, COLOR_TEXT_PRIMARY

_CROSSHAIR_PEN_COLOR = (0, 120, 212, 160)
_TOOLTIP_BORDER_COLOR = COLOR_BORDER
_TOOLTIP_TEXT_COLOR = COLOR_TEXT_PRIMARY
_TOOLTIP_BG_COLOR = (43, 43, 43, 235)
_MOUSE_MOVE_MIN_INTERVAL_S = 1.0 / 45.0
# Phase 34.1.1: нүкте мен tooltip жиегі арасындағы саңылау — НАҚТЫ экран
# пиксельдерінде (data-fraction ЕМЕС — Phase 34.1-дегі бастапқы түзету дәл
# осы себептен толық болмады: pg.TextItem ӘРҚАШАН тұрақты пиксель өлшемінде
# сызылады, zoom/subplot ауқымына тәуелсіз, сондықтан margin да пиксельде
# анықталуы тиіс, ViewBox.viewPixelSize() арқылы ағымдағы масштабқа
# сәйкес data-бірлікке түрлендіріледі).
_READOUT_PIXEL_MARGIN = 8.0

# ``get_curve_data()`` қайтаратын пішін: key -> (x мәндер тізімі, y мәндер
# тізімі). Тек ОҚУ үшін — LiveGraphWidget-тің меншікті deque-дерінен
# тікелей алынған snapshot, PlotCrosshair оны ЕШҚАШАН өзгертпейді.
CurveDataProvider = Callable[[], dict[str, tuple[list[float], list[float]]]]
# (resolved_x, {curve_key: y_value}) -> readout мәтіні (мыс. "t = 12.42 s\nU = 7.051 V").
ReadoutFormatter = Callable[[float, dict[str, float]], str]

# Phase 33B §1: nearest_index() ЕНДІ domain/services/graph_analysis.py-де
# (Qt-сыз, таза numpy) — региондық статистика/регрессия да ДӘЛ СОЛ
# функцияны қолданады, екінші тәуелсіз graph-analysis архитектурасы
# ЖАСАЛМАДЫ ("Do not create a second independent graph-analysis
# architecture"). Бұл жерде тек backward-compat импорт ретінде де
# қолжетімді (ескі "from ui.widgets.graph_crosshair import nearest_index"
# жолдары/тесттер бұзылмауы үшін).


class PlotCrosshair:
    """Бір ``pg.PlotWidget``-ке арналған crosshair + coordinate readout.

    ``get_curve_data`` — ағымдағы (x, y) деректерін қайтаратын callback.
    ``format_readout`` — table-мен/CalculationEngine-мен бірдей "нақты
    өлшенген мән" принципімен tooltip мәтінін құрастырады (бұл класс
    ешбір физикалық шаманы қайта есептемейді).
    """

    def __init__(
        self,
        plot_widget: pg.PlotWidget,
        get_curve_data: CurveDataProvider,
        format_readout: ReadoutFormatter,
        show_horizontal_line: bool = True,
        on_hover: Callable[[float], None] | None = None,
    ) -> None:
        self._plot_widget = plot_widget
        self._get_curve_data = get_curve_data
        self._format_readout = format_readout
        self._on_hover = on_hover

        pen = pg.mkPen(color=_CROSSHAIR_PEN_COLOR, width=1, style=Qt.PenStyle.DashLine)
        self._v_line = pg.InfiniteLine(angle=90, movable=False, pen=pen)
        self._v_line.setZValue(50)
        self._h_line: pg.InfiniteLine | None = None
        if show_horizontal_line:
            self._h_line = pg.InfiniteLine(angle=0, movable=False, pen=pen)
            self._h_line.setZValue(50)

        self._readout = pg.TextItem(
            color=_TOOLTIP_TEXT_COLOR,
            fill=pg.mkBrush(_TOOLTIP_BG_COLOR),
            border=pg.mkPen(_TOOLTIP_BORDER_COLOR),
        )
        self._readout.setZValue(100)

        plot_widget.addItem(self._v_line, ignoreBounds=True)
        if self._h_line is not None:
            plot_widget.addItem(self._h_line, ignoreBounds=True)
        plot_widget.addItem(self._readout, ignoreBounds=True)
        self._set_items_visible(False)

        # Тышқан жылжыған сайын ЕМЕС, шектелген жиілікте ғана өңдейді
        # (§18 Performance) — қолмен уақыт-негізді throttling арқылы,
        # ``pg.SignalProxy`` АРНАЙЫ ҚОЛДАНЫЛМАЙДЫ: ол өз ішінде қосымша
        # QObject/QTimer жасайды, ал бұл жобада графикті жиі reconfigure
        # ету (әр ``configure_channels()`` ескі PlotWidget-ті deleteLater()
        # арқылы алмастырады) event loop нақты pump етілместен көп рет
        # қайталанғанда — нақты heap corruption (Windows fatal exception
        # 0xc0000374) тудырғаны эмпирикалық түрде расталды (pytest толық
        # suite-те, GC PlotItem.__init__ ортасында жүргенде). Тікелей
        # ``sigMouseMoved``-ке қосылу + қолмен throttling бұл тәуекелді
        # жояды, ешбір қосымша QObject құрылмайды.
        self._last_processed_at = 0.0
        plot_widget.scene().sigMouseMoved.connect(self._on_mouse_moved)

    # ---- Public API -----------------------------------------------------

    def show_at_x(self, x_target: float) -> None:
        """Сыртқы синхрондау үшін (stacked топ): осы subplot-тың
        crosshair-ін берілген X-те (өз деректерінен ЕҢ ЖАҚЫН НАҚТЫ
        үлгіні тауып) көрсетеді. Жаңа hover event ЕМЕС — ``on_hover``
        ЕШҚАШАН шақырылмайды (шексіз циклді болдырмау үшін).
        """
        self._show_for_x(x_target, notify_hover=False)

    def hide(self) -> None:
        self._set_items_visible(False)

    def teardown(self) -> None:
        """``plot_widget`` жойылар алдында сигнал байланысын тазалайды.
        ``try/except`` — сцена ӨЗІ де деструкцияланып жатса, Qt кейде
        "signal already disconnected" ескертуін RuntimeError ретінде
        шығарады; бұл жердегі мақсат — тек мүмкін болса тазалау, ешбір
        жағдайда crash/жаңа exception тудырмау.
        """
        try:
            self._plot_widget.scene().sigMouseMoved.disconnect(self._on_mouse_moved)
        except (RuntimeError, TypeError):
            pass

    # ---- Ішкі логика -----------------------------------------------------

    def _on_mouse_moved(self, scene_pos) -> None:
        now = time.monotonic()
        if now - self._last_processed_at < _MOUSE_MOVE_MIN_INTERVAL_S:
            return
        self._last_processed_at = now

        if not self._plot_widget.sceneBoundingRect().contains(scene_pos):
            self.hide()
            return
        view_box = self._plot_widget.getPlotItem().vb
        data_pos = view_box.mapSceneToView(scene_pos)
        self._show_for_x(data_pos.x(), notify_hover=True)

    def _show_for_x(self, x_target: float, *, notify_hover: bool) -> None:
        curve_data = self._get_curve_data()
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
            self.hide()
            return

        self._v_line.setPos(resolved_x)
        if self._h_line is not None and len(values_at_x) == 1:
            self._h_line.setPos(next(iter(values_at_x.values())))

        self._readout.setText(self._format_readout(resolved_x, values_at_x))
        self._position_readout(resolved_x, values_at_x)
        self._set_items_visible(True)

        if notify_hover and self._on_hover is not None:
            self._on_hover(resolved_x)

    def _position_readout(self, x_value: float, values_at_x: dict[str, float]) -> None:
        """Readout tooltip-ты нүктені жаппай, ӘРҚАШАН көрінетін ViewBox
        ауқымының ІШІНДЕ (толық tooltip тіктөртбұрышымен) қалатындай
        орналастырады (Phase 34.1.1: "tooltip clipping" ақауының ТОЛЫҚ
        түзетуі).

        Phase 34.1-дегі бастапқы түзету жеткіліксіз болды, себебі margin/
        offset-ті ViewBox-тың DATA-ауқымының фракциясы ретінде есептеген
        (мыс. ``0.06 * y_span``) — ал ``pg.TextItem`` ӘРҚАШАН тұрақты
        ЭКРАН-ПИКСЕЛЬ өлшемінде сызылады (zoom/subplot масштабына
        тәуелсіз, ``TextItem.updateTransform()``-тің scale-cancelling
        трюгі арқылы). Тар Y-ауқымды subplot-та (мыс. stacked Ток пен
        кернеу графигінің жоғарғы Voltage subplot-ы) сол data-фракциясы
        нақты tooltip биіктігінен (пиксельде) әлдеқайда аз болады да,
        текст әлі де жоғарғы шектен шығып кетеді.

        ЖАҢА тәсіл: tooltip-тің НАҚТЫ (``boundingRect()``, пиксель-эквивалент
        бірлікте) өлшемін ``ViewBox.viewPixelSize()`` арқылы АҒЫМДАҒЫ
        масштабқа сай data-бірлікке түрлендіріп, содан кейін X/Y осьтерін
        ТӘУЕЛСІЗ тексереді: әдепкі бойынша нүктенің ҮСТІНДЕ+ОҢ жағында
        (§ "prefer above/right"), ал нақты өлшенген ені/биіктігі сол
        бағытта сыймаса — сол/төмен жаққа "аударады". Екі осьтің
        комбинациясы 4 шет + 4 бұрышты автоматты қамтиды (мыс. жоғарғы-
        оң бұрыш → төменгі-сол). Соңында pos ӘРҚАШАН [x_min,x_max]/
        [y_min,y_max] ішіне clamp етіледі (соңғы қорғаныс). Нақты
        таңдалған дерек НЕМЕСЕ ось ауқымы бұл жерде ЕШҚАШАН
        өзгертілмейді — тек tooltip text-тің anchor/pos геометриясы.
        """
        view_box = self._plot_widget.getPlotItem().vb
        (x_min, x_max), (y_min, y_max) = view_box.viewRange()
        y_ref = max(values_at_x.values()) if values_at_x else y_max

        # Tooltip-тің НАҚТЫ рендерленген өлшемі (пиксель-эквивалент,
        # setText()-тен КЕЙІН — ағымдағы мәтін ұзындығына сай) — ешбір
        # хардкодталған/фракциялық болжам ЖОҚ.
        text_rect = self._readout.boundingRect()
        px_dx, px_dy = view_box.viewPixelSize()
        text_w = text_rect.width() * px_dx
        text_h = text_rect.height() * px_dy
        margin_x = _READOUT_PIXEL_MARGIN * px_dx
        margin_y = _READOUT_PIXEL_MARGIN * px_dy

        # X: әдепкі — нүктенің ОҢ жағында (текст оңға өседі). Нақты
        # ені сыймаса — солға "аударады" (текст солға өседі).
        if x_value + margin_x + text_w <= x_max:
            anchor_x, pos_x = 0.0, x_value + margin_x
        else:
            anchor_x, pos_x = 1.0, x_value - margin_x

        # Y: әдепкі — нүктенің ҮСТІНДЕ (текст жоғары өседі, anchor_y=1.0 —
        # TextItem-дің ТӨМЕНГІ жиегі pos-та). Нақты биіктігі сыймаса —
        # АСТЫНА "аударады" (anchor_y=0.0 — ЖОҒАРҒЫ жиегі pos-та).
        if y_ref + margin_y + text_h <= y_max:
            anchor_y, pos_y = 1.0, y_ref + margin_y
        else:
            anchor_y, pos_y = 0.0, y_ref - margin_y

        # Соңғы қорғаныс — экстремалды жағдайда (tooltip бүкіл view-ден
        # де үлкен) pos ешқашан ViewBox сыртына шықпауы тиіс.
        pos_x = min(max(pos_x, x_min), x_max)
        pos_y = min(max(pos_y, y_min), y_max)

        self._readout.setAnchor((anchor_x, anchor_y))
        self._readout.setPos(pos_x, pos_y)

    def _set_items_visible(self, visible: bool) -> None:
        self._v_line.setVisible(visible)
        if self._h_line is not None:
            self._h_line.setVisible(visible)
        self._readout.setVisible(visible)
