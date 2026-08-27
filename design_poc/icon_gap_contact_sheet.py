"""Fluent Icon Gap Closure — research contact sheet. COMPLETELY ISOLATED.

Shows every candidate icon researched in the gap-closure phase (Design/02_FluentIcons/
SOURCE.md, "Phase 8 — Gap closure candidates" section) at 12px/16px/20px, labeled with
its intended control and recommendation status. This is a visual-approval aid only —
nothing here is wired into production.

This script imports ONLY ``ui.themes.theme_manager`` (a dependency-free module) for
background/text styling — it does NOT import ``app``, ``ui.main_window``, ``ui.router``,
``ui.widgets.sidebar``, ``ui.widgets.live_graph``, or any production page/widget module.
Running this script has no effect on the real application.

Run with:
    python design_poc/icon_gap_contact_sheet.py
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
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ui.themes.theme_manager import ThemeManager

ICON_DIR = Path(__file__).resolve().parent.parent / "Design" / "02_FluentIcons" / "svg"
PREVIEW_SIZES = (12, 16, 20)

# (file_stem, control, status) — status is shown as a colored tag.
# "recommended" / "alternate" / "filled"
#
# NOTE: only VENDORED candidates (Design/02_FluentIcons/svg/) appear here, so every
# preview renders a real icon. Rejected candidates (History, Clipboard Task List,
# Hand Right, Crop) were deliberately NOT vendored per the "vendor only strong
# matches" rule — see Design/02_FluentIcons/SOURCE.md "Considered but NOT vendored"
# and the separate research grid (contact_sheet_research.png) for those side by side.
CANDIDATES: list[tuple[str, str, str]] = [
    ("ic_fluent_comment_24_regular", "feedback_student / feedback_teacher", "recommended"),
    ("ic_fluent_comment_24_filled", "feedback_student / feedback_teacher (selected)", "filled"),
    ("ic_fluent_chat_24_regular", "feedback_student / feedback_teacher", "alternate"),
    ("ic_fluent_notebook_24_regular", "data_log", "recommended"),
    ("ic_fluent_notebook_24_filled", "data_log (selected)", "filled"),
    ("ic_fluent_people_swap_24_regular", "switch_role_button", "recommended"),
    ("ic_fluent_people_swap_24_filled", "switch_role_button (future)", "filled"),
    ("ic_fluent_arrow_swap_24_regular", "switch_role_button", "alternate"),
    ("ic_fluent_usb_plug_24_regular", "device_summary_label (future)", "alternate"),
    ("ic_fluent_hand_left_24_regular", "_pan_mode_button", "recommended"),
    ("ic_fluent_drag_24_regular", "_pan_mode_button", "alternate"),
    ("ic_fluent_select_object_24_regular", "_region_button", "recommended*"),
    ("ic_fluent_arrow_between_down_24_regular", "_delta_button", "recommended"),
    ("ic_fluent_arrows_bidirectional_24_regular", "_delta_button", "alternate"),
    ("ic_fluent_copy_24_regular", "_copy_summary_button", "recommended"),
]

STATUS_COLORS = {
    "recommended": "#16A34A",
    "recommended*": "#CA8A04",
    "filled": "#2563EB",
    "alternate": "#6B7280",
    "rejected": "#DC2626",
}
STATUS_LABELS = {
    "recommended": "RECOMMENDED",
    "recommended*": "RECOMMENDED (imperfect)",
    "filled": "FILLED VARIANT",
    "alternate": "ALTERNATE",
    "rejected": "REJECTED (shown for comparison)",
}


def build_window() -> QWidget:
    window = QWidget()
    window.setWindowTitle("Fluent Icon Gap Closure — research contact sheet (isolated, not production)")

    outer = QVBoxLayout(window)
    header = QLabel(
        "Icon Gap Closure — Research Contact Sheet\n"
        "Isolated prototype. Nothing here is wired into production. See "
        "Design/02_FluentIcons/SOURCE.md “Phase 8” for full reasoning per candidate.",
        window,
    )
    header.setWordWrap(True)
    header_font = header.font()
    header_font.setBold(True)
    header.setFont(header_font)
    outer.addWidget(header)

    scroll = QScrollArea(window)
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    outer.addWidget(scroll, 1)

    body = QWidget()
    scroll.setWidget(body)
    grid = QGridLayout(body)
    grid.setHorizontalSpacing(24)
    grid.setVerticalSpacing(10)

    col_headers = ["Icon", "12px", "16px", "20px", "Intended control", "Status"]
    for col, text in enumerate(col_headers):
        label = QLabel(text, body)
        f = label.font()
        f.setBold(True)
        label.setFont(f)
        grid.addWidget(label, 0, col)

    for row, (file_stem, control, status) in enumerate(CANDIDATES, start=1):
        path = ICON_DIR / f"{file_stem}.svg"
        icon = QIcon(str(path)) if path.exists() else QIcon()

        name_label = QLabel(file_stem.replace("ic_fluent_", ""), body)
        name_label.setWordWrap(True)
        name_label.setMaximumWidth(220)
        grid.addWidget(name_label, row, 0)

        for col_offset, size in enumerate(PREVIEW_SIZES, start=1):
            pixmap = icon.pixmap(QSize(size, size))
            preview = QLabel(body)
            preview.setPixmap(pixmap)
            preview.setFixedSize(28, 28)
            preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(preview, row, col_offset)

        control_label = QLabel(control, body)
        control_label.setWordWrap(True)
        control_label.setMaximumWidth(260)
        grid.addWidget(control_label, row, 4)

        status_label = QLabel(STATUS_LABELS[status], body)
        status_label.setStyleSheet(f"color: {STATUS_COLORS[status]}; font-weight: 600;")
        grid.addWidget(status_label, row, 5)

    return window


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(ThemeManager().build_stylesheet())

    win = build_window()
    win.resize(1100, 820)
    win.show()

    app.exec()
