"""PlaceholderPage — болашақ модульдерге арналған қайта пайдаланылатын
заглушка бет (Phase 37A).

``SettingsPage``-тегі бұрыннан бар заглушка пішінін (тақырып + бір
сөйлемдік сипаттама + "Артқа" батырмасы) жалпылайды — әр жаңа route
(``Бақылау тақтасы``, ``Сыныптар мен оқушылар`` т.б.) осы БІР класстың
өз тақырып/сипаттама мәтіні бар данасын алады. Ешбір өтірік
статистика/нәтиже/дерек көрсетілмейді — тек НАҚТЫ "әлі жоқ" күйі.
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

_STATUS_TEXT = "Келесі кезеңде іске асырылады"


class PlaceholderPage(QWidget):
    """Бір секция/route үшін заглушка мазмұны бар бет."""

    back_requested = Signal()

    def __init__(
        self,
        title: str,
        description: str,
        parent: QWidget | None = None,
        *,
        show_back_button: bool = True,
    ) -> None:
        super().__init__(parent)

        title_label = QLabel(title, self)
        title_font = title_label.font()
        title_font.setBold(True)
        title_font.setPointSize(title_font.pointSize() + 4)
        title_label.setFont(title_font)

        description_label = QLabel(description, self)
        description_label.setWordWrap(True)

        status_label = QLabel(_STATUS_TEXT, self)
        status_label.setProperty("role", "secondary")

        layout = QVBoxLayout(self)
        if show_back_button:
            back_button = QPushButton("← Артқа", self)
            back_button.clicked.connect(self.back_requested)
            layout.addWidget(back_button)
        layout.addWidget(title_label)
        layout.addWidget(description_label)
        layout.addWidget(status_label)
        layout.addStretch(1)
