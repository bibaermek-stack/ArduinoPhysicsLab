"""PlotCrosshair (Phase 33A, Scientific Graph Core) үшін юнит-тесттер:
nearest_index() таза функциясы + PlotCrosshair-тің нақты pg.PlotWidget-пен
интеграциясы (fake/интерполяцияланған дерек ЕШҚАШАН жасалмайтынын
растайды).
"""

import sys

import pyqtgraph as pg
import pytest
from PySide6.QtCore import QRectF
from PySide6.QtWidgets import QApplication

from ui.widgets.graph_crosshair import PlotCrosshair, nearest_index


@pytest.fixture(scope="module", autouse=True)
def qt_application() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


# ---- nearest_index() — таза функция -----------------------------------


def test_nearest_index_empty_list_returns_negative_one() -> None:
    assert nearest_index([], 5.0) == -1


def test_nearest_index_picks_closest_value() -> None:
    xs = [0.0, 1.0, 2.0, 3.0, 4.0]
    assert nearest_index(xs, 2.1) == 2
    assert nearest_index(xs, 1.9) == 2


def test_nearest_index_exact_match() -> None:
    xs = [0.0, 5.0, 10.0]
    assert nearest_index(xs, 5.0) == 1


def test_nearest_index_out_of_range_clamps_to_edge() -> None:
    xs = [1.0, 2.0, 3.0]
    assert nearest_index(xs, -100.0) == 0
    assert nearest_index(xs, 100.0) == 2


def test_nearest_index_works_on_unsorted_data() -> None:
    """XY/scatter деректер уақыт бойынша монотонды өспеуі мүмкін —
    nearest_index() реттелмеген тізімде де дұрыс жұмыс істеуі тиіс.
    """
    xs = [5.0, 1.0, 3.0, 0.0, 4.0]
    assert xs[nearest_index(xs, 3.2)] == 3.0


# ---- PlotCrosshair — pg.PlotWidget-пен интеграция -----------------------


def _make_plot_widget() -> pg.PlotWidget:
    widget = pg.PlotWidget()
    widget.plot([0.0, 1.0, 2.0], [10.0, 20.0, 30.0], pen=pg.mkPen("k"))
    return widget


def test_crosshair_hidden_initially() -> None:
    plot_widget = _make_plot_widget()
    crosshair = PlotCrosshair(
        plot_widget,
        get_curve_data=lambda: {"voltage": ([0.0, 1.0, 2.0], [10.0, 20.0, 30.0])},
        format_readout=lambda x, values: "test",
    )
    assert crosshair._v_line.isVisible() is False
    assert crosshair._readout.isVisible() is False


def test_show_at_x_resolves_nearest_real_sample_and_shows_items() -> None:
    plot_widget = _make_plot_widget()
    crosshair = PlotCrosshair(
        plot_widget,
        get_curve_data=lambda: {"voltage": ([0.0, 1.0, 2.0], [10.0, 20.0, 30.0])},
        format_readout=lambda x, values: f"x={x}",
    )

    crosshair.show_at_x(1.1)  # 1.0-ге ЕҢ ЖАҚЫН нақты үлгі

    assert crosshair._v_line.isVisible() is True
    assert crosshair._v_line.value() == 1.0  # интерполяция ЖОҚ — нақты x=1.0
    assert crosshair._readout.isVisible() is True


def test_show_at_x_never_fabricates_a_value_between_samples() -> None:
    """1.4 сұралса, ЕШҚАШАН y=24 (интерполяцияланған) есептелмейді —
    тек нақты (1.0, 20.0) немесе (2.0, 30.0) жұптарының бірі таңдалады.
    """
    plot_widget = _make_plot_widget()
    captured: dict[str, float] = {}

    def _format(resolved_x: float, values: dict[str, float]) -> str:
        captured.update(values)
        return "readout"

    crosshair = PlotCrosshair(
        plot_widget,
        get_curve_data=lambda: {"voltage": ([0.0, 1.0, 2.0], [10.0, 20.0, 30.0])},
        format_readout=_format,
    )

    crosshair.show_at_x(1.4)

    assert captured["voltage"] in (10.0, 20.0, 30.0)
    assert captured["voltage"] != 24.0


def test_hide_makes_items_invisible() -> None:
    plot_widget = _make_plot_widget()
    crosshair = PlotCrosshair(
        plot_widget,
        get_curve_data=lambda: {"voltage": ([0.0, 1.0], [10.0, 20.0])},
        format_readout=lambda x, values: "readout",
    )
    crosshair.show_at_x(0.5)
    assert crosshair._v_line.isVisible() is True

    crosshair.hide()

    assert crosshair._v_line.isVisible() is False
    assert crosshair._readout.isVisible() is False


def test_show_at_x_with_no_data_stays_hidden() -> None:
    plot_widget = _make_plot_widget()
    crosshair = PlotCrosshair(
        plot_widget,
        get_curve_data=lambda: {"voltage": ([], [])},
        format_readout=lambda x, values: "readout",
    )

    crosshair.show_at_x(1.0)

    assert crosshair._v_line.isVisible() is False


def test_on_hover_callback_invoked_with_resolved_x() -> None:
    plot_widget = _make_plot_widget()
    hovered: list[float] = []
    crosshair = PlotCrosshair(
        plot_widget,
        get_curve_data=lambda: {"voltage": ([0.0, 1.0, 2.0], [10.0, 20.0, 30.0])},
        format_readout=lambda x, values: "readout",
        on_hover=hovered.append,
    )

    # show_at_x() СЫРТҚЫ синхрондау жолы — on_hover ЕШҚАШАН шақырылмауы
    # керек (шексіз циклді болдырмау үшін, § "Do not make the user
    # manually align two unrelated cursors" — синхрондау бір бағытты).
    crosshair.show_at_x(1.0)

    assert hovered == []


def test_teardown_disconnects_without_raising() -> None:
    plot_widget = _make_plot_widget()
    crosshair = PlotCrosshair(
        plot_widget,
        get_curve_data=lambda: {"voltage": ([0.0], [10.0])},
        format_readout=lambda x, values: "readout",
    )

    crosshair.teardown()  # exception шықпауы керек

    # Екінші рет шақыру да (defensive) қауіпсіз болуы керек.
    crosshair.teardown()


# ---- Phase 34.1 §1: tooltip/readout clipping fix ------------------------


def _make_ranged_plot_widget(
    x_data: list[float], y_data: list[float], x_range: tuple[float, float], y_range: tuple[float, float]
) -> pg.PlotWidget:
    widget = pg.PlotWidget()
    widget.plot(x_data, y_data, pen=pg.mkPen("k"))
    widget.setXRange(*x_range, padding=0)
    widget.setYRange(*y_range, padding=0)
    return widget


def test_tooltip_stays_inside_viewbox_near_top_edge() -> None:
    """Ohm's Law U(I)-де максимум кернеуге жақын нүкте — tooltip ЕШҚАШАН
    ViewBox-тың жоғарғы шетінен клипленбеуі (шықпауы) тиіс.
    """
    x_data = [0.0, 1.0, 2.0]
    y_data = [1.0, 9.7, 5.0]  # x=1.0-де Y=9.7, ViewBox max=10.0-ге өте жақын
    plot_widget = _make_ranged_plot_widget(x_data, y_data, (0.0, 2.0), (0.0, 10.0))
    crosshair = PlotCrosshair(
        plot_widget,
        get_curve_data=lambda: {"voltage": (x_data, y_data)},
        format_readout=lambda x, values: "readout",
    )

    crosshair.show_at_x(1.0)

    (x_min, x_max), (y_min, y_max) = plot_widget.getPlotItem().vb.viewRange()
    pos = crosshair._readout.pos()
    assert y_min <= pos.y() <= y_max
    assert x_min <= pos.x() <= x_max
    # Жоғарғы шетке жақын болғандықтан, tooltip ЕНДІ нүктенің АСТЫНДА
    # (anchor_y=0.0 — TextItem-дің ЖОҒАРҒЫ жиегі pos-та, текст төменге өседі).
    assert crosshair._readout.anchor[1] == pytest.approx(0.0)
    # Нақты дерек нүктесі (crosshair vertical line) ЕШҚАШАН жылжымайды.
    assert crosshair._v_line.value() == pytest.approx(1.0)


def test_tooltip_stays_inside_viewbox_near_bottom_edge() -> None:
    x_data = [0.0, 1.0, 2.0]
    y_data = [1.0, 0.2, 5.0]  # x=1.0-де Y=0.2, ViewBox min=0.0-ге өте жақын
    plot_widget = _make_ranged_plot_widget(x_data, y_data, (0.0, 2.0), (0.0, 10.0))
    crosshair = PlotCrosshair(
        plot_widget,
        get_curve_data=lambda: {"voltage": (x_data, y_data)},
        format_readout=lambda x, values: "readout",
    )

    crosshair.show_at_x(1.0)

    (x_min, x_max), (y_min, y_max) = plot_widget.getPlotItem().vb.viewRange()
    pos = crosshair._readout.pos()
    assert y_min <= pos.y() <= y_max
    assert x_min <= pos.x() <= x_max
    assert crosshair._v_line.value() == pytest.approx(1.0)


def test_tooltip_stays_inside_viewbox_near_left_edge() -> None:
    x_data = [0.05, 1.0, 2.0]
    y_data = [5.0, 6.0, 7.0]
    plot_widget = _make_ranged_plot_widget(x_data, y_data, (0.0, 2.0), (0.0, 10.0))
    crosshair = PlotCrosshair(
        plot_widget,
        get_curve_data=lambda: {"voltage": (x_data, y_data)},
        format_readout=lambda x, values: "readout",
    )

    crosshair.show_at_x(0.05)

    (x_min, x_max), (y_min, y_max) = plot_widget.getPlotItem().vb.viewRange()
    pos = crosshair._readout.pos()
    assert x_min <= pos.x() <= x_max
    assert y_min <= pos.y() <= y_max
    assert crosshair._v_line.value() == pytest.approx(0.05)


def test_tooltip_stays_inside_viewbox_near_right_edge() -> None:
    x_data = [0.0, 1.0, 1.95]
    y_data = [5.0, 6.0, 7.0]
    plot_widget = _make_ranged_plot_widget(x_data, y_data, (0.0, 2.0), (0.0, 10.0))
    crosshair = PlotCrosshair(
        plot_widget,
        get_curve_data=lambda: {"voltage": (x_data, y_data)},
        format_readout=lambda x, values: "readout",
    )

    crosshair.show_at_x(1.95)

    (x_min, x_max), (y_min, y_max) = plot_widget.getPlotItem().vb.viewRange()
    pos = crosshair._readout.pos()
    assert x_min <= pos.x() <= x_max
    assert y_min <= pos.y() <= y_max
    # Оң жақ шетке жақын — anchor_x=1.0 (текст солға өседі), ескі мінез-құлық.
    assert crosshair._readout.anchor[0] == pytest.approx(1.0)
    assert crosshair._v_line.value() == pytest.approx(1.95)


def test_tooltip_near_top_right_corner_stays_inside_viewbox() -> None:
    """Екі шет бірден (жоғары + оң жақ) — екеуі де дұрыс өңделуі тиіс."""
    x_data = [0.0, 1.0, 1.95]
    y_data = [1.0, 5.0, 9.8]
    plot_widget = _make_ranged_plot_widget(x_data, y_data, (0.0, 2.0), (0.0, 10.0))
    crosshair = PlotCrosshair(
        plot_widget,
        get_curve_data=lambda: {"voltage": (x_data, y_data)},
        format_readout=lambda x, values: "readout",
    )

    crosshair.show_at_x(1.95)

    (x_min, x_max), (y_min, y_max) = plot_widget.getPlotItem().vb.viewRange()
    pos = crosshair._readout.pos()
    assert x_min <= pos.x() <= x_max
    assert y_min <= pos.y() <= y_max


def test_tooltip_mid_range_point_keeps_old_above_anchor_behavior() -> None:
    """Регрессия-тест: ортаңғы (шетке жақын ЕМЕС) нүктеде ескі
    мінез-құлық (tooltip нүктенің ҮСТІНДЕ, anchor_y=1.0) сақталады.
    """
    x_data = [0.0, 1.0, 2.0]
    y_data = [1.0, 5.0, 9.0]
    plot_widget = _make_ranged_plot_widget(x_data, y_data, (0.0, 2.0), (0.0, 10.0))
    crosshair = PlotCrosshair(
        plot_widget,
        get_curve_data=lambda: {"voltage": (x_data, y_data)},
        format_readout=lambda x, values: "readout",
    )

    crosshair.show_at_x(1.0)

    assert crosshair._readout.anchor[1] == pytest.approx(1.0)
    assert crosshair._readout.pos().y() > 5.0  # нүктеден ЖОҒАРЫ орналасқан


def test_tooltip_reports_real_value_even_when_repositioned_near_top() -> None:
    """Tooltip қайта орналастырылса да, есептелген/интерполяцияланған
    мән ЕШҚАШАН көрсетілмейді — тек нақты сақталған Y мәні.
    """
    x_data = [0.0, 1.0, 2.0]
    y_data = [1.0, 9.9, 5.0]
    plot_widget = _make_ranged_plot_widget(x_data, y_data, (0.0, 2.0), (0.0, 10.0))
    captured: dict[str, float] = {}

    def _format(resolved_x: float, values: dict[str, float]) -> str:
        captured.update(values)
        return "readout"

    crosshair = PlotCrosshair(
        plot_widget,
        get_curve_data=lambda: {"voltage": (x_data, y_data)},
        format_readout=_format,
    )

    crosshair.show_at_x(1.02)  # 1.0-ге ЕҢ ЖАҚЫН нақты үлгі

    assert captured["voltage"] == pytest.approx(9.9)  # нақты мән, интерполяция ЖОҚ


# =====================================================================
# Phase 34.1.1: pixel-aware geometry containment (real acceptance test)
#
# Алдыңғы (Phase 34.1) tooltip-fix жеткіліксіз болды, себебі margin/
# offset ViewBox-тың DATA ауқымының фракциясы ретінде есептелген еді
# (мыс. 0.06*y_span), ал pg.TextItem ӘРҚАШАН тұрақты ЭКРАН-ПИКСЕЛЬ
# өлшемінде сызылады — тар Y-ауқымды subplot-та (stacked Ток пен
# кернеу графигі) сол data-фракциясы нақты tooltip биіктігінен
# (пиксельде) аз болды. Бұл тесттер ТЕК pos()-ты data-ауқымда
# тексерумен ШЕКТЕЛМЕЙДІ (ол әрқашан "өтеді", себебі соңғы clamp
# соны кепілдендіреді) — нақты SCENE-кеңістіктегі tooltip
# тіктөртбұрышын ViewBox-тың scene тіктөртбұрышымен салыстырады.
# =====================================================================


def _make_realistic_plot_widget(
    x_data: list[float],
    y_data: list[float],
    x_range: tuple[float, float],
    y_range: tuple[float, float],
    size: tuple[int, int] = (1000, 600),
) -> pg.PlotWidget:
    """Нақты desktop терезесіне сай өлшемді plot widget — тар/шағын
    (never-shown) виджет ЕШБІР нақты пиксель-геометрияны байқамайды
    (final clamp әрдайым "өтеді" деп көрсетеді), сондықтан геометрия
    тесттері үшін НАҚТЫ resize()+show() МІНДЕТТІ.
    """
    widget = pg.PlotWidget()
    widget.plot(x_data, y_data, pen=pg.mkPen("k"))
    widget.setXRange(*x_range, padding=0)
    widget.setYRange(*y_range, padding=0)
    widget.resize(*size)
    widget.show()
    QApplication.instance().processEvents()
    return widget


def _viewbox_scene_rect(plot_widget: pg.PlotWidget) -> QRectF:
    view_box = plot_widget.getPlotItem().vb
    (x_min, x_max), (y_min, y_max) = view_box.viewRange()
    top_left = view_box.mapViewToScene(pg.Point(x_min, y_max))
    bottom_right = view_box.mapViewToScene(pg.Point(x_max, y_min))
    return QRectF(top_left, bottom_right).normalized()


def _tooltip_scene_rect(crosshair: PlotCrosshair) -> QRectF:
    readout = crosshair._readout
    return readout.mapRectToScene(readout.boundingRect())


def _assert_tooltip_fully_contained(
    crosshair: PlotCrosshair, plot_widget: pg.PlotWidget, tolerance_px: float = 1.0
) -> None:
    """Tooltip-тің ТОЛЫҚ scene тіктөртбұрышы ViewBox-тың көрінетін scene
    ауданының ІШІНДЕ жатуы тиіс (кіші rounding tolerance-пен). Бұл —
    §7-де талап етілген "нақты acceptance" тексеруі, жай ғана pos()-ты
    data-ауқымда тексеруден МҮЛДЕ өзгеше (ол ешқашан сәтсіз бола
    алмайды, себебі соңғы clamp оны кепілдендіреді).
    """
    tooltip_rect = _tooltip_scene_rect(crosshair)
    view_rect = _viewbox_scene_rect(plot_widget)
    inflated = view_rect.adjusted(-tolerance_px, -tolerance_px, tolerance_px, tolerance_px)
    assert inflated.contains(tooltip_rect), (
        f"Tooltip scene rect {tooltip_rect} escapes ViewBox scene rect {view_rect} "
        f"(tolerance={tolerance_px}px)"
    )


# X: 0..2, Y: 0..10 — нақты Current+Voltage stacked subplot-тың тар Y-
# ауқымын бейнелейді. Мәтін екі жолды, нақты readout пішіміне сай
# (мыс. "t = 15.30 s\nКернеу = 7.376 V").
_MULTILINE_READOUT = "t = 15.30 s\nКернеу = 7.376 V"


def _make_edge_crosshair(x_data, y_data, plot_widget) -> PlotCrosshair:
    return PlotCrosshair(
        plot_widget,
        get_curve_data=lambda: {"voltage": (x_data, y_data)},
        format_readout=lambda x, values: _MULTILINE_READOUT,
    )


def test_geometry_containment_top_edge() -> None:
    x_data, y_data = [0.0, 1.0, 2.0], [5.0, 9.85, 5.0]
    plot_widget = _make_realistic_plot_widget(x_data, y_data, (0.0, 2.0), (0.0, 10.0))
    crosshair = _make_edge_crosshair(x_data, y_data, plot_widget)

    crosshair.show_at_x(1.0)

    _assert_tooltip_fully_contained(crosshair, plot_widget)
    assert crosshair._v_line.value() == pytest.approx(1.0)  # нақты нүкте жылжымады


def test_geometry_containment_bottom_edge() -> None:
    x_data, y_data = [0.0, 1.0, 2.0], [5.0, 0.15, 5.0]
    plot_widget = _make_realistic_plot_widget(x_data, y_data, (0.0, 2.0), (0.0, 10.0))
    crosshair = _make_edge_crosshair(x_data, y_data, plot_widget)

    crosshair.show_at_x(1.0)

    _assert_tooltip_fully_contained(crosshair, plot_widget)


def test_geometry_containment_left_edge() -> None:
    x_data, y_data = [0.02, 1.0, 2.0], [5.0, 6.0, 7.0]
    plot_widget = _make_realistic_plot_widget(x_data, y_data, (0.0, 2.0), (0.0, 10.0))
    crosshair = _make_edge_crosshair(x_data, y_data, plot_widget)

    crosshair.show_at_x(0.02)

    _assert_tooltip_fully_contained(crosshair, plot_widget)


def test_geometry_containment_right_edge() -> None:
    x_data, y_data = [0.0, 1.0, 1.98], [5.0, 6.0, 7.0]
    plot_widget = _make_realistic_plot_widget(x_data, y_data, (0.0, 2.0), (0.0, 10.0))
    crosshair = _make_edge_crosshair(x_data, y_data, plot_widget)

    crosshair.show_at_x(1.98)

    _assert_tooltip_fully_contained(crosshair, plot_widget)


def test_geometry_containment_top_right_corner() -> None:
    x_data, y_data = [0.0, 1.0, 1.98], [1.0, 5.0, 9.85]
    plot_widget = _make_realistic_plot_widget(x_data, y_data, (0.0, 2.0), (0.0, 10.0))
    crosshair = _make_edge_crosshair(x_data, y_data, plot_widget)

    crosshair.show_at_x(1.98)

    _assert_tooltip_fully_contained(crosshair, plot_widget)


def test_geometry_containment_top_left_corner() -> None:
    x_data, y_data = [0.02, 1.0, 2.0], [9.85, 5.0, 1.0]
    plot_widget = _make_realistic_plot_widget(x_data, y_data, (0.0, 2.0), (0.0, 10.0))
    crosshair = _make_edge_crosshair(x_data, y_data, plot_widget)

    crosshair.show_at_x(0.02)

    _assert_tooltip_fully_contained(crosshair, plot_widget)


def test_geometry_containment_bottom_right_corner() -> None:
    x_data, y_data = [0.0, 1.0, 1.98], [9.0, 5.0, 0.15]
    plot_widget = _make_realistic_plot_widget(x_data, y_data, (0.0, 2.0), (0.0, 10.0))
    crosshair = _make_edge_crosshair(x_data, y_data, plot_widget)

    crosshair.show_at_x(1.98)

    _assert_tooltip_fully_contained(crosshair, plot_widget)


def test_geometry_containment_bottom_left_corner() -> None:
    x_data, y_data = [0.02, 1.0, 2.0], [0.15, 5.0, 9.0]
    plot_widget = _make_realistic_plot_widget(x_data, y_data, (0.0, 2.0), (0.0, 10.0))
    crosshair = _make_edge_crosshair(x_data, y_data, plot_widget)

    crosshair.show_at_x(0.02)

    _assert_tooltip_fully_contained(crosshair, plot_widget)


def test_geometry_containment_narrow_stacked_subplot_reproduces_reported_bug() -> None:
    """Нақты хабарланған bug-ты дәл қайталайды: Электр тізбегін
    құрастыру және ток күшін өлшеу stacked
    графигінің Voltage subplot-ы тар Y-ауқыммен (мыс. 4-9В) және
    шектеулі subplot биіктігімен (stacked-те бір ғана subplot толық
    графиктің биіктігін емес, жартысын алады). Ескі (Phase 34.1)
    data-фракция негізді margin осында НАҚТЫ жеткіліксіз болатын.
    """
    x_data, y_data = [0.0, 10.0, 20.0], [5.0, 7.0, 8.95]
    # Stacked subplot биіктігі толық графиктен әлдеқайда аз (~300px).
    plot_widget = _make_realistic_plot_widget(
        x_data, y_data, (0.0, 20.0), (4.0, 9.0), size=(1400, 280)
    )
    crosshair = _make_edge_crosshair(x_data, y_data, plot_widget)

    crosshair.show_at_x(20.0)

    _assert_tooltip_fully_contained(crosshair, plot_widget)


def test_geometry_containment_survives_zoom() -> None:
    """Қолмен zoom жасалғаннан кейін де (ViewBox ауқымы тарылғаннан
    кейін) tooltip contain болуы тиіс — ``viewPixelSize()`` әрбір
    шақыруда АҒЫМДАҒЫ масштабты қайта оқиды.
    """
    x_data, y_data = [0.0, 1.0, 2.0], [5.0, 9.85, 5.0]
    plot_widget = _make_realistic_plot_widget(x_data, y_data, (0.0, 2.0), (0.0, 10.0))
    crosshair = _make_edge_crosshair(x_data, y_data, plot_widget)

    # Қолмен зумдау — ауқым тарылады (жаңа, кішірек Y-span).
    plot_widget.setYRange(8.0, 10.0, padding=0)
    QApplication.instance().processEvents()

    crosshair.show_at_x(1.0)

    _assert_tooltip_fully_contained(crosshair, plot_widget)


def test_geometry_containment_survives_window_resize() -> None:
    x_data, y_data = [0.0, 1.0, 2.0], [5.0, 9.85, 5.0]
    plot_widget = _make_realistic_plot_widget(x_data, y_data, (0.0, 2.0), (0.0, 10.0))
    crosshair = _make_edge_crosshair(x_data, y_data, plot_widget)

    plot_widget.resize(500, 300)
    QApplication.instance().processEvents()

    crosshair.show_at_x(1.0)

    _assert_tooltip_fully_contained(crosshair, plot_widget)


def test_geometry_containment_does_not_mutate_data_or_view_range() -> None:
    """Критикалық integrity тест: tooltip орналастыру (edge-flip-мен
    қоса) деректі НЕМЕСЕ ось ауқымын ЕШҚАШАН өзгертпейді.
    """
    x_data, y_data = [0.0, 1.0, 2.0], [5.0, 9.85, 5.0]
    plot_widget = _make_realistic_plot_widget(x_data, y_data, (0.0, 2.0), (0.0, 10.0))
    crosshair = _make_edge_crosshair(x_data, y_data, plot_widget)
    before_range = plot_widget.getPlotItem().vb.viewRange()

    crosshair.show_at_x(1.0)

    after_range = plot_widget.getPlotItem().vb.viewRange()
    (before_x, before_y), (after_x, after_y) = before_range, after_range
    assert before_x == pytest.approx(after_x)
    assert before_y == pytest.approx(after_y)
    assert list(x_data) == [0.0, 1.0, 2.0]
    assert list(y_data) == [5.0, 9.85, 5.0]
