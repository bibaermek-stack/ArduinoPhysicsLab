"""DeviceCard — Vernier стиліндегі, бір ConnectedDevice-ті көрсететін
карточка виджеті.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from domain.entities.connected_device import ConnectedDevice
from ui.themes.theme_manager import (
    COLOR_ERROR,
    COLOR_SUCCESS,
    COLOR_TEXT_SECONDARY,
    COLOR_WARNING,
)

_SENSOR_TYPE_NAMES_KK: dict[str, str] = {
    "VOLTAGE": "Кернеу датчигі",
    "CURRENT": "Ток датчигі",
    "ENERGY": "Қуат және энергия датчигі",
    "OHMMETER": "Омметр",
}
_UNKNOWN_SENSOR_TYPE_NAME_KK = "Белгісіз датчик"

STATUS_CONNECTED = "connected"
STATUS_IDENTIFYING = "identifying"
STATUS_ERROR = "error"
STATUS_DISCONNECTED = "disconnected"

_STATUS_TEXT_KK: dict[str, str] = {
    STATUS_CONNECTED: "Қосылды",
    STATUS_IDENTIFYING: "Анықталуда...",
    STATUS_ERROR: "Қате",
    STATUS_DISCONNECTED: "Байланыс үзілді",
}
_STATUS_COLOR: dict[str, str] = {
    STATUS_CONNECTED: COLOR_SUCCESS,
    STATUS_IDENTIFYING: COLOR_WARNING,
    STATUS_ERROR: COLOR_ERROR,
    STATUS_DISCONNECTED: COLOR_TEXT_SECONDARY,
}

_CARD_WIDTH = 220
_CARD_HEIGHT = 110
_NO_CHIP_TEXT = "—"


class DeviceCard(QFrame):
    """Бір ``ConnectedDevice``-ті карточка түрінде көрсететін виджет."""

    selected = Signal(object)
    identify_requested = Signal(str)

    def __init__(
        self, device: ConnectedDevice | None = None, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._device: ConnectedDevice | None = None
        self._is_selected = False

        self.setObjectName("DeviceCard")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFixedSize(_CARD_WIDTH, _CARD_HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setProperty("selected", "false")
        self.setStyleSheet(
            "#DeviceCard { border: 1px solid palette(mid); border-radius: 6px; }"
            "#DeviceCard[selected=\"true\"] { border: 2px solid palette(highlight); }"
        )

        self._title_label = QLabel(self)
        title_font = self._title_label.font()
        title_font.setBold(True)
        self._title_label.setFont(title_font)

        self._device_id_label = QLabel(self)
        # Model/Firmware/Chip негізгі карточка денесінде көрсетілмейді
        # (ықшамдау) — text/.tooltip() мазмұны сақталады, тек layout-тан
        # жасырылады. Толық ақпарат картаның өз tooltip-інде жиналады
        # (_update_card_tooltip()).
        self._model_label = QLabel(self)
        self._model_label.setVisible(False)
        self._firmware_label = QLabel(self)
        self._firmware_label.setVisible(False)
        self._chip_label = QLabel(self)
        self._chip_label.setVisible(False)
        self._port_label = QLabel(self)

        self._status_dot = QLabel(self)
        self._status_dot.setFixedSize(10, 10)
        self._status_text_label = QLabel(self)

        # Кезeng 29: нақты уақыттағы соңғы өлшем мәні (мыс. "5.333 V") —
        # ExperimentWorkspacePage measurement_ready сигналынан forward
        # етеді (set_live_value()). Бұл карточка ӨЗІ ешбір Measurement/
        # есептеу логикасын білмейді — тек берілген мәтінді көрсетеді.
        self._live_value_label = QLabel(self)
        self._live_value_label.setObjectName("DeviceCardLiveValue")
        self._live_value_label.setVisible(False)

        self._identify_button = QPushButton("⟳", self)
        self._identify_button.setFlat(True)
        self._identify_button.setFixedSize(22, 20)
        self._identify_button.setToolTip("Қайта анықтау")
        self._identify_button.clicked.connect(self._on_identify_clicked)

        status_row = QHBoxLayout()
        status_row.setContentsMargins(0, 0, 0, 0)
        status_row.addWidget(self._status_dot)
        status_row.addWidget(self._status_text_label)
        status_row.addStretch(1)
        status_row.addWidget(self._live_value_label)
        status_row.addWidget(self._identify_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self._title_label)
        layout.addWidget(self._device_id_label)
        layout.addWidget(self._model_label)
        layout.addWidget(self._firmware_label)
        layout.addWidget(self._chip_label)
        layout.addWidget(self._port_label)
        layout.addStretch(1)
        layout.addLayout(status_row)

        self._set_status(STATUS_DISCONNECTED)

        if device is not None:
            self.set_device(device)

    def set_device(self, device: ConnectedDevice) -> None:
        """Карточканың мазмұнын берілген ``ConnectedDevice``-пен толтырады."""
        self._device = device

        display_name = _SENSOR_TYPE_NAMES_KK.get(
            device.sensor_type.upper(), _UNKNOWN_SENSOR_TYPE_NAME_KK
        )
        self._set_label(self._title_label, display_name, display_name)
        self._set_label(self._device_id_label, device.device_id, device.device_id)
        self._set_label(
            self._model_label, f"Model: {device.model}", device.model
        )
        self._set_label(
            self._firmware_label,
            f"Firmware: {device.firmware_version}",
            device.firmware_version,
        )
        chip_text = device.chip or _NO_CHIP_TEXT
        self._set_label(self._chip_label, f"Chip: {chip_text}", chip_text)
        self._set_label(
            self._port_label, f"Port: {device.port_name}", device.port_name
        )
        self.setToolTip(
            f"Model: {device.model}\n"
            f"Firmware: {device.firmware_version}\n"
            f"Chip: {chip_text}"
        )

        self._set_status(STATUS_CONNECTED)
        self.set_live_value("")

    def set_live_value(self, text: str) -> None:
        """Нақты уақыттағы соңғы өлшем мәнін (мыс. "5.333 V") көрсетеді.
        Бос жол берілсе, label толық жасырылады. Бұл карточка ешбір
        Measurement/CalculationEngine логикасын қайталамайды — тек
        дайын мәтінді көрсетеді (``DevicePanel.update_measurement_value()``
        арқылы forward етіледі).
        """
        self._live_value_label.setText(text)
        self._live_value_label.setVisible(bool(text))

    def set_selected(self, selected: bool) -> None:
        """Карточканың таңдалу визуал күйін орнатады."""
        self._is_selected = selected
        self.setProperty("selected", "true" if selected else "false")
        style = self.style()
        if style is not None:
            style.unpolish(self)
            style.polish(self)

    def is_selected(self) -> bool:
        """Карточка қазір таңдалғанын қайтарады."""
        return self._is_selected

    def set_connected(self, connected: bool) -> None:
        """Байланыс күйін (Қосылды/Байланыс үзілді) орнатады."""
        self._set_status(STATUS_CONNECTED if connected else STATUS_DISCONNECTED)

    def device(self) -> ConnectedDevice | None:
        """Карточка қазір көрсетіп тұрған ``ConnectedDevice``-ті қайтарады."""
        return self._device

    def _set_status(self, status: str) -> None:
        color = _STATUS_COLOR[status]
        self._status_dot.setStyleSheet(
            f"background-color: {color}; border-radius: 5px;"
        )
        self._status_text_label.setText(_STATUS_TEXT_KK[status])

    @staticmethod
    def _set_label(label: QLabel, text: str, tooltip_source: str) -> None:
        label.setText(text)
        label.setToolTip(tooltip_source)

    def _on_identify_clicked(self) -> None:
        if self._device is not None:
            self.identify_requested.emit(self._device.port_name)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Карточканы басқанда ``selected(device)`` сигналын шығарады."""
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton and self._device is not None:
            self.selected.emit(self._device)
