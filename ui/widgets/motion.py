"""ui/widgets/motion.py — Phase 12 "Subtle Motion System": restrained,
paint-free QVariantAnimation color transitions for buttons/status/values.

Architecture (§11 "smallest safe integration path"): instead of touching
every button-construction call site (Sidebar/live_graph/generic buttons are
scattered across 5+ files), ONE ``ButtonMotionFilter`` is installed ONCE on
the ``QApplication`` instance (see ``app.build_main_window()``). It observes
Enter/Leave/Press/Release/toggled for every ``QPushButton`` app-wide and, for
the small set of RECOGNIZED button roles (Sidebar nav / PrimaryButton /
variant="secondary"/"icon" — this last one already covers the graph
toolbar's checkable icon buttons, § Phase 10/11), layers a short
``QVariantAnimation`` color fade on top of Qt's existing, already-tested
:hover/:pressed/:checked QSS cascade via a PER-WIDGET instance
``setStyleSheet()`` override. The filter NEVER consumes an event (always
returns False) — it only observes.

At rest (settled on the button's own resting/normal color) the instance
override is cleared back to ``""``, handing full control back to the
app-level stylesheet — steady-state rendering is therefore byte-identical
to the pre-Phase-12 static QSS (§ geometry/visual freeze); only the brief
transition window differs, which is invisible to static screenshots and to
tests (no test in this codebase asserts on ``.styleSheet()`` content).

``MOTION_ENABLED`` (§9 "Motion Accessibility") is the single central
runtime switch — every helper here short-circuits to an immediate,
non-animated state change when it is False. Functional behavior
(``isChecked()``, click signals, focus) is completely unaffected either way,
with or without the filter installed at all.
"""

from __future__ import annotations

import time

from PySide6.QtCore import QEasingCurve, QEvent, QObject, QVariantAnimation
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QLabel, QPushButton, QWidget

from ui.themes.theme_manager import (
    ANIMATION_BUTTON_MS,
    ANIMATION_FADE_MS,
    ANIMATION_HOVER_MS,
    COLOR_ACCENT,
    COLOR_ACCENT_HOVER,
    COLOR_ACCENT_PRESSED,
    COLOR_ACCENT_SUBTLE,
    COLOR_HOVER,
    COLOR_SELECTED,
    COLOR_SURFACE,
    MOTION_VALUE_HIGHLIGHT_MS,
)

MOTION_ENABLED = True

_TRANSPARENT = QColor(0, 0, 0, 0)


class _Palette:
    __slots__ = ("normal", "hover", "pressed", "checked")

    def __init__(
        self, normal: QColor, hover: QColor, pressed: QColor, checked: QColor | None = None
    ) -> None:
        self.normal = normal
        self.hover = hover
        self.pressed = pressed
        self.checked = checked


# Sidebar nav батырмасы: §2 "Hover ~120ms / Selected ~150ms / Pressed ~80ms".
_PALETTES: dict[str, _Palette] = {
    "SidebarNavButton": _Palette(
        _TRANSPARENT, QColor(COLOR_HOVER), QColor(COLOR_SELECTED), QColor(COLOR_ACCENT)
    ),
    "PrimaryButton": _Palette(
        QColor(COLOR_ACCENT), QColor(COLOR_ACCENT_HOVER), QColor(COLOR_ACCENT_PRESSED)
    ),
}
# variant="icon" — graph toolbar-дың checkable батырмаларын да қамтиды
# (§ live_graph.py: pan/zoom/region/т.б. батырмалары ЕСКІ Phase 10/11-де
# осы variant-ты ҚОЛДАНАДЫ, бөлек интеграция ҚАЖЕТ ЕМЕС).
_VARIANT_PALETTES: dict[str, _Palette] = {
    "secondary": _Palette(QColor(COLOR_SURFACE), QColor(COLOR_HOVER), QColor(COLOR_SELECTED)),
    "icon": _Palette(_TRANSPARENT, QColor(COLOR_HOVER), QColor(COLOR_SELECTED), QColor(COLOR_SELECTED)),
}

_WATCHED_EVENTS = frozenset(
    {
        QEvent.Type.Enter,
        QEvent.Type.Leave,
        QEvent.Type.MouseButtonPress,
        QEvent.Type.MouseButtonRelease,
    }
)


def _palette_for(button: QPushButton) -> _Palette | None:
    palette = _PALETTES.get(button.objectName())
    if palette is not None:
        return palette
    variant = button.property("variant")
    if isinstance(variant, str):
        return _VARIANT_PALETTES.get(variant)
    return None


class ButtonMotionFilter(QObject):
    """§11 reusable helper — БІР instance барлық танылған батырма үшін
    hover/pressed/checked ауысу анимациясын орталықтан басқарады."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._animations: dict[int, QVariantAnimation] = {}
        self._wired: set[int] = set()

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802
        if not MOTION_ENABLED:
            return False
        if event.type() not in _WATCHED_EVENTS:
            return False
        if not isinstance(obj, QPushButton):
            return False
        palette = _palette_for(obj)
        if palette is None or not obj.isEnabled():
            return False

        self._wire_toggled(obj, palette)

        et = event.type()
        if et == QEvent.Type.Enter:
            target = palette.checked if obj.isChecked() else palette.hover
            self._animate_to(obj, target, ANIMATION_HOVER_MS)
        elif et == QEvent.Type.Leave:
            target = palette.checked if obj.isChecked() else palette.normal
            self._animate_to(obj, target, ANIMATION_HOVER_MS)
        elif et == QEvent.Type.MouseButtonPress:
            self._animate_to(obj, palette.pressed, ANIMATION_BUTTON_MS)
        elif et == QEvent.Type.MouseButtonRelease:
            if obj.isChecked():
                target = palette.checked
            else:
                target = palette.hover if obj.underMouse() else palette.normal
            self._animate_to(obj, target, ANIMATION_BUTTON_MS)
        return False

    def _wire_toggled(self, obj: QPushButton, palette: _Palette) -> None:
        key = id(obj)
        if key in self._wired:
            return
        self._wired.add(key)
        if obj.isCheckable() and palette.checked is not None:
            obj.toggled.connect(lambda checked, w=obj, p=palette: self._on_toggled(w, p, checked))
        obj.destroyed.connect(lambda *_args, k=key: self._forget(k))

    def _on_toggled(self, obj: QPushButton, palette: _Palette, checked: bool) -> None:
        if not MOTION_ENABLED:
            return
        target = palette.checked if checked else (palette.hover if obj.underMouse() else palette.normal)
        self._animate_to(obj, target, ANIMATION_FADE_MS)

    def _forget(self, key: int) -> None:
        self._wired.discard(key)
        self._animations.pop(key, None)

    def _animate_to(self, obj: QPushButton, target: QColor | None, duration: int) -> None:
        if target is None:
            return
        key = id(obj)
        anim = self._animations.get(key)
        if anim is None:
            anim = QVariantAnimation(self)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            anim.valueChanged.connect(lambda value, w=obj: _apply_background(w, value))
            anim.finished.connect(lambda w=obj, t=target: _settle_background(w, t))
            self._animations[key] = anim
        current = obj.property("_motionColor")
        start = current if isinstance(current, QColor) else target
        anim.stop()
        anim.setDuration(max(1, duration))
        anim.setStartValue(start)
        anim.setEndValue(target)
        anim.start()


def _apply_background(widget: QWidget, value: QColor) -> None:
    widget.setProperty("_motionColor", value)
    widget.setStyleSheet(
        f"background-color: rgba({value.red()}, {value.green()}, {value.blue()}, {value.alpha()});"
    )


def _settle_background(widget: QWidget, target: QColor) -> None:
    current = widget.property("_motionColor")
    if isinstance(current, QColor) and current == target:
        widget.setStyleSheet("")


_button_motion_filter: ButtonMotionFilter | None = None


def install_button_motion(app: QObject) -> None:
    """``app.build_main_window()``-де шақырылады. Қайталама орнатудан
    сақтанады — ортақ ``QApplication`` бірнеше рет ``build_main_window()``
    арқылы қайта қолданылатын тесттерде де (§ pytest-qt session fixture)
    ЕКІ filter стектелмейді.
    """
    global _button_motion_filter
    if getattr(app, "_apl_motion_filter_installed", False):
        return
    _button_motion_filter = ButtonMotionFilter(app)
    app.installEventFilter(_button_motion_filter)
    app._apl_motion_filter_installed = True


# ---------------------------------------------------------------------
# Статус label color-fade (§5 "Status Transitions" — 150-200ms).
# ---------------------------------------------------------------------

_label_color_animations: dict[int, QVariantAnimation] = {}


def fade_label_color(label: QLabel, target_hex: str, duration: int = ANIMATION_FADE_MS) -> None:
    """``label``-дің ``color`` QSS қасиетін ағымдағы түстен ``target_hex``-ке
    дейін жұмсақ ауыстырады. Логикалық статус ӘРҚАШАН ДӘЛ ОСЫ шақыруда
    бірден белгіленеді (§ "the logical state must update immediately;
    animation is only visual feedback") — тек КӨРІНЕТІН түс ауысуы
    жұмсартылады, ешбір delay функционалды жаққа әсер етпейді.
    """
    target = QColor(target_hex)
    if not MOTION_ENABLED:
        label.setProperty("_motionTextColor", target)
        label.setStyleSheet(f"color: {target.name()};")
        return

    key = id(label)
    anim = _label_color_animations.get(key)
    if anim is None:
        anim = QVariantAnimation(label)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.valueChanged.connect(lambda value, w=label: _apply_text_color(w, value))
        _label_color_animations[key] = anim
        label.destroyed.connect(lambda *_args, k=key: _label_color_animations.pop(k, None))

    current = label.property("_motionTextColor")
    start = current if isinstance(current, QColor) else target
    anim.stop()
    anim.setDuration(max(1, duration))
    anim.setStartValue(start)
    anim.setEndValue(target)
    anim.start()


def _apply_text_color(label: QLabel, value: QColor) -> None:
    label.setProperty("_motionTextColor", value)
    label.setStyleSheet(f"color: {value.name()};")


# ---------------------------------------------------------------------
# Өлшем мәні жаңарғандағы қысқа highlight (§6 — суппрессияланған, ~120ms).
# ---------------------------------------------------------------------

_value_flash_animations: dict[int, QVariantAnimation] = {}
_value_flash_last: dict[int, float] = {}

_FLASH_COLOR = QColor(COLOR_ACCENT_SUBTLE)
_FLASH_TRANSPARENT = QColor(COLOR_ACCENT_SUBTLE)
_FLASH_TRANSPARENT.setAlpha(0)

_FLASH_MIN_INTERVAL_MS = 250  # § "If measurements update rapidly, suppress per-sample animation"


def flash_value_update(
    label: QLabel, duration: int = MOTION_VALUE_HIGHLIGHT_MS, min_interval_ms: int = _FLASH_MIN_INTERVAL_MS
) -> None:
    """Сан МӘНІ (``label.setText()``) ӘРҚАШАН ШАҚЫРУШЫДА бірден,
    анимациясыз жаңартылады (§ "update the number instantly") — бұл
    функция тек қосымша, THROTTLED фон-highlight эффектін қосады.
    Жоғары sample rate-те (< ``min_interval_ms``) жаңа flash БАСТАЛМАЙДЫ
    (§ "Avoid flashing at high sample rates").
    """
    if not MOTION_ENABLED:
        return
    key = id(label)
    now = time.monotonic()
    if (now - _value_flash_last.get(key, 0.0)) * 1000.0 < min_interval_ms:
        return
    _value_flash_last[key] = now

    anim = _value_flash_animations.get(key)
    if anim is None:
        anim = QVariantAnimation(label)
        anim.valueChanged.connect(lambda value, w=label: _apply_background(w, value))
        anim.finished.connect(lambda w=label: w.setStyleSheet(""))
        _value_flash_animations[key] = anim

        def _cleanup(*_args: object, k: int = key) -> None:
            _value_flash_animations.pop(k, None)
            _value_flash_last.pop(k, None)

        label.destroyed.connect(_cleanup)

    anim.stop()
    anim.setDuration(max(1, duration))
    anim.setStartValue(_FLASH_COLOR)
    anim.setEndValue(_FLASH_TRANSPARENT)
    anim.start()
