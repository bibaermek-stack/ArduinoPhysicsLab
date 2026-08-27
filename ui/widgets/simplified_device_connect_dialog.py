"""SimplifiedDeviceConnectDialog — Оқушы режимінде "Құрылғы қосылмаған"
күйінен ашылатын жеңілдетілген қосылым диалогы (Phase 37A).

Бұл диалог ЕШБІР жаңа scan/identify логикасын жасамайды: тек
``ExperimentWorkspacePage``-тің ӨЗІНДЕ бұрыннан бар (бірақ әдепкі бойынша
``setVisible(False)``, экранда КӨРІНБЕЙТІН) жалғыз ``DevicePanel`` данасын
ӨЗ layout-ына уақытша reparent етеді — сол арқылы coordinator/controller-
мен бұрыннан бар БАРЛЫҚ сигнал байланысы (scan_requested/identify_
requested/device_selected) өзгеріссіз жұмыс істей береді, ешбір
дубликат жасалмайды.

Калибрлеу/firmware/serial консоль сияқты күрделі мүмкіндіктер жоқ —
``DevicePanel``-дің ӨЗІНДЕ де олар ешқашан болмаған (тек скан/анықтау/
құрылғы карточкалары), сондықтан бұл диалог қолданушыға дәл сол
қарапайым, шектелген мүмкіндік жиынын көрсетеді.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ui.widgets.device_panel import DevicePanel

_TITLE_TEXT = "Құрылғыны қосу"
_CLOSE_BUTTON_TEXT = "Жабу"


class SimplifiedDeviceConnectDialog(QDialog):
    """``device_panel``-ды (ата-энесінен уақытша ажыратылған күйде)
    өз ішіне алып көрсететін, дайын болғанда автоматты жабылатын диалог.

    ``is_ready`` — ағымдағы pipeline (``ExperimentController``/
    ``MultiSensorExperimentCoordinator``) дайын ба, соны қайтаратын
    callback; диалог осыны сигнал келген сайын тексеріп, дайын болса
    ӨЗІН-ӨЗІ жабады (§7: "returns to the experiment automatically").
    """

    def __init__(
        self,
        device_panel: DevicePanel,
        is_ready: Callable[[], bool],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(_TITLE_TEXT)
        self._device_panel = device_panel
        self._is_ready = is_ready
        self._original_parent = device_panel.parent()

        device_panel.setParent(self)
        device_panel.setVisible(True)

        self._close_button = QPushButton(_CLOSE_BUTTON_TEXT, self)
        self._close_button.clicked.connect(self.close)

        footer_layout = QHBoxLayout()
        footer_layout.addStretch(1)
        footer_layout.addWidget(self._close_button)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(_TITLE_TEXT, self))
        layout.addWidget(device_panel, 1)
        layout.addLayout(footer_layout)

    def check_readiness(self) -> None:
        """Pipeline дайын болғанын тексереді — дайын болса, диалог
        автоматты жабылады (эксперимент экранына қайтарады).
        """
        if self._is_ready():
            self.close()

    def closeEvent(self, event) -> None:
        self._device_panel.setVisible(False)
        self._device_panel.setParent(self._original_parent)
        super().closeEvent(event)
