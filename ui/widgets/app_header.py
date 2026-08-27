"""AppHeader — жұмыс аймағының үстіңгі chrome жолағы.

Бет логикасын білмейді: атау мен пайдаланушы мәтінін ``MainWindow``
сырттан итереді (Sidebar-дағы dumb-display принципімен бірдей).
Зертханалық жұмыс бетінде және кіру экранында жасырылады — график
ауданы қысылмауы үшін.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QWidget

from ui.navigation.navigation_config import NAVIGATION_ITEMS
from ui.themes.theme_manager import COLOR_ACCENT

_AVATAR_SIZE = 28

_NAV_TITLES = {item.key: item.title for item in NAVIGATION_ITEMS}
_ROUTE_ALIASES = {
    "about": "help",
    "data_journal": "data_log",
    "experiment_list": "labs",
}
_EXTRA_TITLES = {
    "experiment_workspace": "Зертханалық жұмыс",
    "teacher_management": "Мұғалімдер",
    "classroom_monitoring": "Сыныпты бақылау",
    "student_monitoring": "Оқушыны бақылау",
    "role_selection": "",
}
_HEADER_HIDDEN_ROUTES = frozenset({"role_selection", "experiment_workspace"})


def title_for_route(route_name: str) -> str:
    key = _ROUTE_ALIASES.get(route_name, route_name)
    if key in _NAV_TITLES:
        return _NAV_TITLES[key]
    return _EXTRA_TITLES.get(route_name, "Arduino Physics Lab")


def header_visible_for_route(route_name: str) -> bool:
    return route_name not in _HEADER_HIDDEN_ROUTES


class AppHeader(QWidget):
    """Ағымдағы бет атауы + рөл/пайдаланушы жолағы."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("AppHeader")
        self.setFixedHeight(48)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._title_label = QLabel("Arduino Physics Lab", self)
        self._title_label.setObjectName("AppHeaderTitle")

        self._role_chip = QLabel(self)
        self._role_chip.setObjectName("AppHeaderRoleChip")
        self._role_chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._role_chip.hide()

        self._user_label = QLabel(self)
        self._user_label.setObjectName("AppHeaderUser")
        self._user_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._user_label.hide()

        self._avatar_label = QLabel(self)
        self._avatar_label.setObjectName("AppHeaderAvatar")
        self._avatar_label.setFixedSize(_AVATAR_SIZE, _AVATAR_SIZE)
        self._avatar_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._avatar_label.setStyleSheet(
            f"background-color: {COLOR_ACCENT}; color: #FFFFFF; "
            f"border-radius: {_AVATAR_SIZE // 2}px; font-weight: 600;"
        )
        self._avatar_label.hide()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(10)
        layout.addWidget(self._title_label, 1)
        layout.addWidget(self._role_chip, 0)
        layout.addWidget(self._user_label, 0)
        layout.addWidget(self._avatar_label, 0)

    def set_title(self, title: str) -> None:
        self._title_label.setText(title)

    def set_user(self, name: str | None, role_label: str | None) -> None:
        if role_label:
            self._role_chip.setText(role_label)
            self._role_chip.show()
        else:
            self._role_chip.clear()
            self._role_chip.hide()
        if name:
            self._user_label.setText(name)
            self._user_label.show()
            self._avatar_label.setText(name.strip()[:1].upper())
            self._avatar_label.show()
        else:
            self._user_label.clear()
            self._user_label.hide()
            self._avatar_label.clear()
            self._avatar_label.hide()
