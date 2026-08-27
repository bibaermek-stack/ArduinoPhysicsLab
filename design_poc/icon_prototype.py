"""Fluent Icon Proof of Concept — COMPLETELY ISOLATED, non-production script.

Demonstrates vendored Fluent System Icon SVGs (Design/02_FluentIcons/svg/) rendered
on PySide6 widgets styled with the REAL, unmodified ``ThemeManager.build_stylesheet()``
QSS (same object names/selectors that ``ui/widgets/sidebar.py`` and
``ui/widgets/live_graph.py`` already use in production: ``SidebarNavButton``,
``variant="icon"``, ``PrimaryButton``).

This script imports ONLY ``ui.themes.theme_manager`` (a dependency-free module — no
imports of its own) — it does NOT import ``app``, ``ui.main_window``, ``ui.router``,
``ui.widgets.sidebar``, ``DeviceManager``, or any repository/database module. Running
this script has no effect on the real application, its database, or its tests.

Run with:
    python design_poc/icon_prototype.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.themes.theme_manager import ICON_SIZE_MD, MIN_BUTTON_HEIGHT, ThemeManager

ICON_DIR = Path(__file__).resolve().parent.parent / "Design" / "02_FluentIcons" / "svg"


def icon(file_stem: str) -> QIcon:
    path = ICON_DIR / f"{file_stem}.svg"
    if not path.exists():
        raise FileNotFoundError(f"Vendored icon missing: {path}")
    return QIcon(str(path))


class Section(QFrame):
    """Labeled group box — presentation only, no production QSS object name."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        outer = QVBoxLayout(self)
        heading = QLabel(title, self)
        font = heading.font()
        font.setBold(True)
        heading.setFont(font)
        outer.addWidget(heading)
        self.body = QVBoxLayout()
        outer.addLayout(self.body)


def labeled(widget: QWidget, caption: str) -> QWidget:
    """Wraps a widget with a small caption below it (state-demo columns)."""
    holder = QWidget()
    layout = QVBoxLayout(holder)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(2)
    layout.addWidget(widget, 0, Qt.AlignmentFlag.AlignHCenter)
    caption_label = QLabel(caption, holder)
    caption_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
    caption_label.setProperty("role", "secondary")
    layout.addWidget(caption_label)
    return holder


def build_window() -> tuple[QWidget, dict[str, QPushButton]]:
    """Builds the PoC window. Returns ``(window, buttons)`` where ``buttons`` maps
    stable keys to the exact QPushButton instances the state-demo rows use, so a
    screenshot script can force hover/pressed/checked/disabled states precisely
    without guessing at widget-tree positions.
    """
    buttons: dict[str, QPushButton] = {}

    window = QWidget()
    window.setWindowTitle("Fluent Icon PoC — isolated, not part of production app")
    window.setObjectName("PoCRoot")

    root = QHBoxLayout(window)

    # ---- Left: Sidebar-style mock (real "SidebarNavButton" object name) -----
    sidebar = QFrame(window)
    sidebar.setObjectName("Sidebar")
    sidebar.setFixedWidth(220)
    sidebar_layout = QVBoxLayout(sidebar)
    brand = QLabel("Arduino Physics Lab", sidebar)
    brand.setObjectName("SidebarBrand")
    sidebar_layout.addWidget(brand)

    nav_items = [
        ("ic_fluent_home_24_filled", "Басты бет", True, True),
        ("ic_fluent_beaker_24_regular", "Зертханалық жұмыстар", False, True),
        ("ic_fluent_clipboard_data_bar_24_regular", "Нәтижелер", False, True),
        ("ic_fluent_person_24_regular", "Оқушылар", False, True),
        ("ic_fluent_settings_24_regular", "Баптаулар", False, True),
        ("ic_fluent_question_circle_24_regular", "Анықтама", False, False),
    ]
    for file_stem, label, checked, enabled in nav_items:
        button = QPushButton(icon(file_stem), f"  {label}", sidebar)
        button.setObjectName("SidebarNavButton")
        button.setCheckable(True)
        button.setChecked(checked)
        button.setEnabled(enabled)
        button.setIconSize(QSize(ICON_SIZE_MD, ICON_SIZE_MD))
        sidebar_layout.addWidget(button)
    sidebar_layout.addStretch(1)
    root.addWidget(sidebar)

    # ---- Right column ---------------------------------------------------
    right = QVBoxLayout()
    root.addLayout(right, 1)

    note = QLabel(
        "Isolated PoC — vendored Fluent SVG icons + real ThemeManager QSS.\n"
        "Not wired into app.py / MainWindow / Router. Left panel reuses the\n"
        "production 'SidebarNavButton' object name; right panel reuses the\n"
        "production 'variant=\"icon\"' / 'PrimaryButton' object names.",
        window,
    )
    note.setWordWrap(True)
    right.addWidget(note)

    # ---- Toolbar-style row (compact icon-only buttons, matches graph toolbar) --
    toolbar_section = Section("Toolbar-style controls (compact, icon-only)", window)
    toolbar_row = QHBoxLayout()
    toolbar_icons = [
        ("ic_fluent_arrow_left_24_regular", "Back"),
        ("ic_fluent_plug_connected_24_regular", "Device"),
        ("ic_fluent_zoom_in_24_regular", "Zoom"),
        ("ic_fluent_arrow_reset_24_regular", "Reset"),
        ("ic_fluent_full_screen_maximize_24_regular", "Fullscreen"),
        ("ic_fluent_arrow_export_24_regular", "Export"),
        ("ic_fluent_settings_24_regular", "Settings"),
    ]
    for file_stem, tip in toolbar_icons:
        button = QPushButton(icon(file_stem), "", window)
        button.setProperty("variant", "icon")
        button.setToolTip(tip)
        button.setIconSize(QSize(ICON_SIZE_MD, ICON_SIZE_MD))
        toolbar_row.addWidget(button)
    toolbar_row.addStretch(1)
    toolbar_section.body.addLayout(toolbar_row)
    right.addWidget(toolbar_section)

    # ---- Action-row style (icon + text, matches Start/Stop/Clear/Export row) ---
    action_section = Section(
        "Action-row controls (icon + text, matches measurement workspace)", window
    )
    action_row = QHBoxLayout()
    start_button = QPushButton(icon("ic_fluent_play_24_filled"), " Бастау", window)
    start_button.setObjectName("PrimaryButton")
    stop_button = QPushButton(icon("ic_fluent_stop_24_regular"), " Тоқтату", window)
    stop_button.setEnabled(False)
    clear_button = QPushButton(icon("ic_fluent_delete_24_regular"), " Тазалау", window)
    export_button = QPushButton(icon("ic_fluent_arrow_export_24_regular"), " Экспорт", window)
    for b in (start_button, stop_button, clear_button, export_button):
        b.setIconSize(QSize(ICON_SIZE_MD, ICON_SIZE_MD))
        action_row.addWidget(b)
    action_row.addStretch(1)
    action_section.body.addLayout(action_row)
    right.addWidget(action_section)

    # ---- Explicit state demo: normal / hover / pressed / checked / disabled ---
    state_section = Section(
        "Button states — same icon (Zoom In), each column forced into a distinct Qt state",
        window,
    )
    state_row = QHBoxLayout()

    for key, caption, checkable in (
        ("state_normal", "Normal", False),
        ("state_hover", "Hover", False),
        ("state_pressed", "Pressed", False),
        ("state_checked", "Checked*", True),
        ("state_disabled", "Disabled", False),
    ):
        btn = QPushButton(icon("ic_fluent_zoom_in_24_regular"), "", window)
        btn.setProperty("variant", "icon")
        btn.setIconSize(QSize(ICON_SIZE_MD, ICON_SIZE_MD))
        if checkable:
            btn.setCheckable(True)
            btn.setChecked(True)
        buttons[key] = btn
        state_row.addWidget(labeled(btn, caption))
    buttons["state_disabled"].setEnabled(False)

    state_row.addStretch(1)
    state_section.body.addLayout(state_row)

    caveat = QLabel(
        "* ThemeManager currently defines :checked only for #SidebarNavButton, not for "
        'variant="icon" — this button falls back to the base QPushButton look while '
        "checked. See report 'Problems discovered'.",
        window,
    )
    caveat.setWordWrap(True)
    caveat.setProperty("role", "secondary")
    state_section.body.addWidget(caveat)
    right.addWidget(state_section)

    # ---- Sidebar-nav state demo (separate from the mock sidebar above) --------
    nav_state_section = Section("Sidebar nav button states (SidebarNavButton)", window)
    nav_state_row = QHBoxLayout()

    nav_normal = QPushButton(icon("ic_fluent_home_24_regular"), "  Normal", window)
    nav_normal.setObjectName("SidebarNavButton")
    nav_normal.setCheckable(True)
    buttons["nav_normal"] = nav_normal
    nav_state_row.addWidget(nav_normal)

    nav_hover = QPushButton(icon("ic_fluent_home_24_regular"), "  Hover", window)
    nav_hover.setObjectName("SidebarNavButton")
    nav_hover.setCheckable(True)
    buttons["nav_hover"] = nav_hover
    nav_state_row.addWidget(nav_hover)

    nav_selected = QPushButton(icon("ic_fluent_home_24_filled"), "  Selected", window)
    nav_selected.setObjectName("SidebarNavButton")
    nav_selected.setCheckable(True)
    nav_selected.setChecked(True)
    buttons["nav_selected"] = nav_selected
    nav_state_row.addWidget(nav_selected)

    nav_disabled = QPushButton(icon("ic_fluent_home_24_regular"), "  Disabled", window)
    nav_disabled.setObjectName("SidebarNavButton")
    nav_disabled.setCheckable(True)
    nav_disabled.setEnabled(False)
    buttons["nav_disabled"] = nav_disabled
    nav_state_row.addWidget(nav_disabled)

    nav_state_section.body.addLayout(nav_state_row)
    right.addWidget(nav_state_section)

    # ---- Full icon gallery: all 20 vendored icons, labeled by category --------
    gallery_section = Section("All 20 vendored icons (gallery)", window)
    gallery = QGridLayout()
    gallery_icons = [
        ("Home", "ic_fluent_home_24_regular"),
        ("Laboratory", "ic_fluent_beaker_24_regular"),
        ("Device / plug", "ic_fluent_plug_connected_24_regular"),
        ("Results / data", "ic_fluent_clipboard_data_bar_24_regular"),
        ("Graphs", "ic_fluent_chart_multiple_24_regular"),
        ("Calculations", "ic_fluent_calculator_24_regular"),
        ("Instructions", "ic_fluent_book_24_regular"),
        ("Circuit (closest match)", "ic_fluent_developer_board_24_regular"),
        ("Export", "ic_fluent_arrow_export_24_regular"),
        ("Settings", "ic_fluent_settings_24_regular"),
        ("Help", "ic_fluent_question_circle_24_regular"),
        ("Student / user", "ic_fluent_person_24_regular"),
        ("Theme / mode", "ic_fluent_dark_theme_24_regular"),
        ("Back", "ic_fluent_arrow_left_24_regular"),
        ("Start / play", "ic_fluent_play_24_regular"),
        ("Stop", "ic_fluent_stop_24_regular"),
        ("Delete / clear", "ic_fluent_delete_24_regular"),
        ("Zoom", "ic_fluent_zoom_in_24_regular"),
        ("Reset", "ic_fluent_arrow_reset_24_regular"),
        ("Fullscreen", "ic_fluent_full_screen_maximize_24_regular"),
    ]
    for index, (caption, file_stem) in enumerate(gallery_icons):
        button = QPushButton(icon(file_stem), "", window)
        button.setProperty("variant", "icon")
        button.setEnabled(False)  # gallery = display only, not interactive
        button.setIconSize(QSize(ICON_SIZE_MD, ICON_SIZE_MD))
        cell = labeled(button, caption)
        gallery.addWidget(cell, index // 5, index % 5)
    gallery_section.body.addLayout(gallery)
    right.addWidget(gallery_section)

    right.addStretch(1)

    footer = QLabel(
        f"Compact button height token in use: MIN_BUTTON_HEIGHT = {MIN_BUTTON_HEIGHT}px "
        "(same constant the production app uses — not enlarged for this PoC).",
        window,
    )
    footer.setProperty("role", "secondary")
    right.addWidget(footer)

    return window, buttons


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(ThemeManager().build_stylesheet())

    win, _buttons = build_window()
    win.resize(1180, 900)
    win.show()

    app.exec()
