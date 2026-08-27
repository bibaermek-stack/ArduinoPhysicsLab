"""ui/widgets/animated_atom_widget.py — Phase 12 "Subtle Motion System":
lightweight, paint-only animated atom illustration (nucleus + 3 elliptical
orbits + moving electron dots), replacing the previously-static "home"
category watermark motif (``_draw_home`` in ``workspace_background.py``).

``QPainter``/``QTimer`` only (§ "Do NOT use GIF/WebView/video/QML"). The
actual drawing math lives in the module-level ``paint_atom()`` function so
it can be shared: ``AnimatedAtomWidget`` (this class, a genuine standalone
reusable widget — usable in any layout on its own) calls it from its own
``paintEvent()``, and ``WorkspaceBackdrop`` calls it directly too (§ that
file's integration comment) instead of embedding this widget as an
overlapping child — avoiding any new child-widget hit-testing/grab()
visibility risk in that already heavily-tested file, with zero drawing
logic duplicated between the two call sites.
"""

from __future__ import annotations

import math
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ui.themes.theme_manager import MOTION_ATOM_ORBIT_CYCLE_MS, MOTION_ATOM_PULSE_MS
from ui.widgets import motion

_UPDATE_INTERVAL_MS = 40  # ~25 FPS (§ "Preferred update rate: 20-30 FPS maximum")
ORBIT_CYCLE_MS = float(MOTION_ATOM_ORBIT_CYCLE_MS)  # 12-20s range (central token, § ThemeManager)
PULSE_CYCLE_MS = float(MOTION_ATOM_PULSE_MS)  # 4-8s range (central token, § ThemeManager)
_PULSE_AMPLITUDE = 0.12  # ядро радиусының жұмсақ "тыныс алу" ауытқуы
NUCLEUS_COLOR = "#37474F"  # workspace_background._CATEGORY_STROKE_COLOR["home"]-мен БІРДЕЙ
DEFAULT_OPACITY = 0.10  # § "approximately 0.06-0.12"

# (бастапқы бұрыш°, орбита scale, жылдамдық көбейткіші) — бұрынғы статикалық
# _draw_home-дегі 3 электронмен ГЕОМЕТРИЯЛЫҚ БІРДЕЙ бастапқы позиция,
# әрқайсысына сәл ӘРТҮРЛІ жылдамдық қосылған (§ "Different electron speeds").
_ELECTRONS = (
    (25.0, 1.0, 1.0),
    (150.0, 0.82, 0.82),
    (255.0, 1.0, 1.24),
)
_ORBIT_TILT_DEG = (0.0, 60.0, 120.0)


def paint_atom(
    painter: QPainter,
    rect: QRectF,
    elapsed_ms: float,
    *,
    color: str = NUCLEUS_COLOR,
    opacity: float = DEFAULT_OPACITY,
    animated: bool = True,
) -> None:
    """Ядро + 3 орбита + электрондарды берілген ``rect`` ішіне,
    ``elapsed_ms``-ке сай фазамен салады. ``rect``-қа қатысты барлық
    координаталар (widget-relative) — HiDPI/resize кезінде де анық
    қалады (§ "Do not use fixed bitmap dimensions").
    """
    side = min(rect.width(), rect.height())
    if side <= 0:
        return
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setOpacity(opacity)

    qcolor = QColor(color)
    center = rect.center()
    radius = side / 2

    pen = QPen(qcolor)
    pen.setWidthF(max(1.0, side * 0.014))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.translate(center)
    for tilt in _ORBIT_TILT_DEG:
        painter.save()
        painter.rotate(tilt)
        painter.drawEllipse(QRectF(-radius, -radius * 0.4, radius * 2, radius * 0.8))
        painter.restore()
    painter.translate(-center)

    if animated:
        pulse_phase = (elapsed_ms % PULSE_CYCLE_MS) / PULSE_CYCLE_MS
        pulse = 1.0 + _PULSE_AMPLITUDE * math.sin(pulse_phase * 2.0 * math.pi)
    else:
        pulse = 1.0
    nucleus_radius = radius * 0.12 * pulse
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(qcolor)
    painter.drawEllipse(center, nucleus_radius, nucleus_radius)

    for start_deg, orbit_scale, speed in _ELECTRONS:
        travel_deg = (elapsed_ms * speed / ORBIT_CYCLE_MS) * 360.0 if animated else 0.0
        rad = math.radians(start_deg + travel_deg)
        point = QPointF(
            center.x() + radius * orbit_scale * math.cos(rad),
            center.y() + radius * 0.4 * orbit_scale * math.sin(rad),
        )
        painter.drawEllipse(point, radius * 0.06, radius * 0.06)

    painter.restore()


class AnimatedAtomWidget(QWidget):
    """Дербес, толық жұмыс істейтін қайта пайдаланылатын виджет (§ "Create
    a reusable widget such as AnimatedAtomWidget"). Тек СӘНДІК фон элементі
    — ешбір mouse/focus/keyboard оқиғасын ұстамайды
    (``WA_TransparentForMouseEvents`` осы ЖАПЫРАҚ виджеттің өзінде, ешбір
    ұрпағы жоқ — бұрынғы WorkspaceBackdrop hit-testing инцидентінен
    (§ сол файлдың docstring-і) ПРИНЦИПТІ түрде өзгеше: сол инцидент бұл
    атрибутты ІШІНДЕ интерактивті ағашы бар АТА-ТЕК виджетке қойғаннан
    туындаған, мұнда декенденті жоқ жапырақ виджет үшін бұл ЕШБІР тәуекел
    тудырмайды).

    Тек көрінгенде жаңарады (``showEvent``/``hideEvent`` — § "pause or
    stop its timer if practical").
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._start_time = time.monotonic()
        self._timer = QTimer(self)
        self._timer.setInterval(_UPDATE_INTERVAL_MS)
        self._timer.timeout.connect(self.update)

    def showEvent(self, event) -> None:  # noqa: N802 (Qt override name)
        super().showEvent(event)
        if motion.MOTION_ENABLED:
            self._timer.start()

    def hideEvent(self, event) -> None:  # noqa: N802 (Qt override name)
        super().hideEvent(event)
        self._timer.stop()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override name)
        painter = QPainter(self)
        elapsed_ms = (time.monotonic() - self._start_time) * 1000.0
        paint_atom(painter, QRectF(self.rect()), elapsed_ms, animated=motion.MOTION_ENABLED)
        painter.end()
