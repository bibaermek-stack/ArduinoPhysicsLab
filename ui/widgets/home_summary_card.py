"""HomeSummaryCard — жинақы сан + қалып (caption) көрсететін карточка.

``results_page.py``, ``student_feedback_page.py``, ``teacher_dashboard_page.py``,
``teacher_feedback_review_page.py`` төртеуінде де айна-қатесіз қайталанған
``_build_summary_card()``/``_make_background_transparent()`` осы жалғыз
виджет класына бірегейленді. ``TeacherDashboardPage`` ғана қосымша
accent-tinted icon badge қолданады (``icon_pixmap``/``icon_accent``) —
қалған үшеуі жай мән+қалып ғана.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ui.themes.theme_manager import SPACING_LG, SPACING_MD, SPACING_XS


def make_background_transparent(widget: QWidget) -> None:
    """``role``-негізді ``QLabel`` өз еніне (толық созылған layout-та) сай
    ``COLOR_BACKGROUND`` тіктөртбұрышын ақ карточка/панель үстінде бояп
    кетеді. instance-деңгейлік ``setStyleSheet()`` ғана жұмыс істейді
    (эмпирикалық тексерілді, ``WA_StyledBackground`` бұл жағдайда ЕШБІР
    әсер етпейді)."""
    widget.setStyleSheet("background-color: transparent;")


class HomeSummaryCard(QFrame):
    """Жинақы сан (мыс. "12") + қалып мәтіні (мыс. "Барлық жұмыстар")
    көрсететін карточка. ``value_label`` шақырушыда ашық қалады, сан
    жаңарғанда ``value_label.setText(...)`` тікелей шақырылады.
    """

    def __init__(
        self,
        label: str,
        *,
        icon_pixmap: QPixmap | None = None,
        icon_accent: str | None = None,
        icon_badge_px: int = 36,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("HomeSummaryCard")

        self.value_label = QLabel("0", self)
        self.value_label.setProperty("role", "cardValue")
        make_background_transparent(self.value_label)

        caption_label = QLabel(label, self)
        caption_label.setProperty("role", "cardLabel")
        make_background_transparent(caption_label)

        text_column = QVBoxLayout()
        text_column.setSpacing(SPACING_XS)
        text_column.addWidget(self.value_label)
        text_column.addWidget(caption_label)

        if icon_pixmap is not None and icon_accent is not None:
            icon_badge = QLabel(self)
            icon_badge.setFixedSize(icon_badge_px, icon_badge_px)
            icon_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon_badge.setPixmap(icon_pixmap)
            icon_badge.setStyleSheet(
                f"background-color: {icon_accent}; border-radius: {icon_badge_px // 2}px;"
            )

            card_layout = QHBoxLayout(self)
            card_layout.setContentsMargins(SPACING_LG, SPACING_MD, SPACING_LG, SPACING_MD)
            card_layout.setSpacing(SPACING_MD)
            card_layout.addLayout(text_column, 1)
            card_layout.addWidget(icon_badge, 0, Qt.AlignmentFlag.AlignVCenter)
        else:
            card_layout = QVBoxLayout(self)
            card_layout.setContentsMargins(SPACING_LG, SPACING_MD, SPACING_LG, SPACING_MD)
            card_layout.setSpacing(SPACING_XS)
            card_layout.addLayout(text_column)
