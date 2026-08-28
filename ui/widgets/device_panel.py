"""DevicePanel — Vernier стиліндегі, сол жақ sidebar ретінде орналасатын
құрылғыларды іздеу/анықтау/көрсету панелі.

Бұл виджет тек көрсету және пайдаланушы әрекеттерін Qt signal ретінде
шығарумен айналысады: ``DeviceRegistry`` логикасын қайталамайды,
``SerialThreadController``/``DeviceIdentifier``-мен тікелей байланыспайды.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.constants import SERIAL_BAUD_RATE, SERIAL_BAUD_RATES
from domain.entities.connected_device import ConnectedDevice
from infrastructure.serial_comm.device_scanner import SerialDeviceInfo
from ui.widgets.device_card import DeviceCard

_BAUD_RATES = SERIAL_BAUD_RATES
_DEFAULT_BAUD_RATE = SERIAL_BAUD_RATE

_SENSOR_TYPE_ORDER: dict[str, int] = {
    "VOLTAGE": 0,
    "CURRENT": 1,
    "ENERGY": 2,
    "OHMMETER": 3,
    "TEMPERATURE": 4,
}
_UNKNOWN_SENSOR_ORDER = 5

_SENSOR_TYPE_NAMES_KK: dict[str, str] = {
    "VOLTAGE": "Кернеу датчигі",
    "CURRENT": "Ток датчигі",
    "ENERGY": "Қуат және энергия датчигі",
    "OHMMETER": "Омметр",
    "TEMPERATURE": "Температура датчигі",
}

# Кезeng 29: live-value forwarding — тек нақты сенсорлық шамамен 1:1
# сәйкес келетін кілттер ғана (туынды/есептелген шамалар ЕМЕС, олар
# сенсор карточкасына емес, MeasurementWorkspace readout-тарына тиесілі).
_CHANNEL_KEY_TO_SENSOR_TYPE: dict[str, str] = {
    "voltage": "VOLTAGE",
    "current": "CURRENT",
    "temperature": "TEMPERATURE",
}
_CHANNEL_UNIT: dict[str, str] = {
    "voltage": "V",
    "current": "A",
    "temperature": "°C",
}

_EMPTY_STATE_TEXT = "Құрылғы анықталған жоқ"
_NO_PORT_SELECTED_MESSAGE = "Алдымен COM портты таңдаңыз"
_NO_PORTS_FOUND_MESSAGE = "Қолжетімді COM порт табылмады"
_READINESS_TITLE_TEXT = "Қажетті сенсорлар"
_READINESS_ICON_READY = "✓"
_READINESS_ICON_PENDING = "○"
# Phase 32.1: hardware-тәуелсіз workspace — 0/N немесе ішінара N/M
# күйінде әр сенсордың "әлі қосылмаған" екенін мәтінмен де анық көрсету
# (тек ○ иконасына сүйенбей).
_READINESS_DISCONNECTED_SUFFIX = " — Қосылмаған"


class DevicePanel(QWidget):
    """Сол жақ sidebar: порт/baud таңдау, Жаңарту/Анықтау батырмалары
    және анықталған құрылғылардың карточкалары.
    """

    scan_requested = Signal()
    identify_requested = Signal(str, int)
    device_selected = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cards_by_port: dict[str, DeviceCard] = {}
        self._selected_port: str | None = None
        self._readiness_labels: dict[str, QLabel] = {}

        # Панель тым үлкен болмасын — негізгі назар MeasurementWorkspace-те.
        self.setMaximumWidth(260)
        # Phase 32: горизонталь бойынша компакт (Preferred + maxWidth
        # шектеуі жеткілікті — ені терезе өскен сайын ӨСПЕЙДІ), бірақ
        # вертикаль бойынша қолжетімді биіктікті НАҚТЫ пайдалана алады
        # (мазмұн scroll_area арқылы асып кетсе де, scroll қолданады).
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        title_label = QLabel("Құрылғылар", self)
        title_font = title_label.font()
        title_font.setBold(True)
        title_font.setPointSize(title_font.pointSize() + 2)
        title_label.setFont(title_font)

        self._readiness_container = QWidget(self)
        readiness_container_layout = QVBoxLayout(self._readiness_container)
        readiness_container_layout.setContentsMargins(0, 0, 0, 0)

        readiness_title_label = QLabel(_READINESS_TITLE_TEXT, self._readiness_container)
        readiness_title_font = readiness_title_label.font()
        readiness_title_font.setBold(True)
        readiness_title_label.setFont(readiness_title_font)
        readiness_container_layout.addWidget(readiness_title_label)

        self._readiness_layout = QVBoxLayout()
        readiness_container_layout.addLayout(self._readiness_layout)

        self._readiness_container.setVisible(False)

        # Кезeng 29: COM/baud/Refresh/Identify бақылау элементтері визуалды
        # бір ықшам топқа ("Қосылым параметрлері") біріктірілді — функция/
        # сигналдар МҮЛДЕ өзгермеді, тек layout қана.
        self._connection_group = QFrame(self)
        self._connection_group.setObjectName("ConnectionSettingsGroup")
        connection_group_layout = QVBoxLayout(self._connection_group)

        connection_title_label = QLabel("Қосылым параметрлері", self._connection_group)
        connection_title_label.setObjectName("ConnectionSettingsTitle")
        connection_group_layout.addWidget(connection_title_label)

        self._port_combo = QComboBox(self._connection_group)
        self._port_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )

        self._baud_combo = QComboBox(self._connection_group)
        for baud in _BAUD_RATES:
            self._baud_combo.addItem(str(baud), baud)
        self._baud_combo.setCurrentIndex(_BAUD_RATES.index(_DEFAULT_BAUD_RATE))

        self._refresh_button = QPushButton("Жаңарту", self._connection_group)
        self._identify_button = QPushButton("Анықтау", self._connection_group)

        connection_group_layout.addWidget(self._port_combo)
        connection_group_layout.addWidget(self._baud_combo)
        connection_group_layout.addWidget(self._refresh_button)
        connection_group_layout.addWidget(self._identify_button)

        self._message_label = QLabel("", self)
        self._message_label.setWordWrap(True)

        self._empty_state_label = QLabel(_EMPTY_STATE_TEXT, self)
        self._empty_state_label.setWordWrap(True)

        self._cards_container = QWidget(self)
        self._cards_layout = QVBoxLayout(self._cards_container)
        self._cards_layout.addWidget(self._empty_state_label)
        self._cards_layout.addStretch(1)

        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(self._cards_container)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        layout = QVBoxLayout(self)
        layout.addWidget(title_label)
        layout.addWidget(self._readiness_container)
        layout.addWidget(self._connection_group)
        layout.addWidget(self._message_label)
        layout.addWidget(scroll_area, 1)

        self._refresh_button.clicked.connect(self.scan_requested)
        self._identify_button.clicked.connect(self._on_identify_clicked)

    def set_required_sensor_types(self, sensor_types: tuple[str, ...]) -> None:
        """Ағымдағы тәжірибеге қажетті физикалық сенсор түрлерінің
        checklist-ін құрастырады. 0 немесе 1 түр берілсе (single-device
        тәжірибе), checklist жасырылады — панель бұрынғыдай көрінеді.
        """
        while self._readiness_layout.count():
            item = self._readiness_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._readiness_labels = {}

        if len(sensor_types) <= 1:
            self._readiness_container.setVisible(False)
            return

        for sensor_type in sensor_types:
            label = QLabel(self._readiness_text(sensor_type, False), self._readiness_container)
            self._readiness_labels[sensor_type] = label
            self._readiness_layout.addWidget(label)
        self._readiness_container.setVisible(True)

    def update_measurement_value(self, values: dict[str, float]) -> None:
        """Ағымдағы Measurement-тің шикі мәндерін ("voltage"/"current")
        сәйкес сенсор карточкасының live-value label-іне forward етеді.
        Ешбір жаңа есептеу жасамайды — тек ExperimentWorkspacePage-тен
        келген, coordinator-дың өзі есептеген мәнді көрсетеді. Белгісіз
        кілт/сәйкес карточка жоқ болса — үнсіз өткізіп жіберіледі.
        """
        for channel_key, sensor_type in _CHANNEL_KEY_TO_SENSOR_TYPE.items():
            value = values.get(channel_key)
            if value is None:
                continue
            unit = _CHANNEL_UNIT.get(channel_key, "")
            for card in self._cards_by_port.values():
                device = card.device()
                if device is not None and device.sensor_type.upper() == sensor_type:
                    card.set_live_value(f"{value:.3f} {unit}".rstrip())

    def set_sensor_readiness(self, readiness: dict[str, bool]) -> None:
        """Checklist-тегі ✓/○ белгілерін ``{sensor_type: ready}`` бойынша
        жаңартады. Checklist-те жоқ кілттер елеусіз қалады.
        """
        for sensor_type, is_ready in readiness.items():
            label = self._readiness_labels.get(sensor_type)
            if label is not None:
                label.setText(self._readiness_text(sensor_type, is_ready))

    @staticmethod
    def _readiness_text(sensor_type: str, is_ready: bool) -> str:
        display_name = _SENSOR_TYPE_NAMES_KK.get(sensor_type.upper(), sensor_type)
        icon = _READINESS_ICON_READY if is_ready else _READINESS_ICON_PENDING
        suffix = "" if is_ready else _READINESS_DISCONNECTED_SUFFIX
        return f"{icon} {display_name}{suffix}"

    def set_ports(self, ports: tuple[SerialDeviceInfo, ...]) -> None:
        """COM порттар тізімін ComboBox-қа толтырады."""
        self._port_combo.clear()
        for port in ports:
            label = f"{port.port_name} — {port.description or 'белгісіз құрылғы'}"
            if port.is_likely_arduino:
                label += " [Arduino]"
            self._port_combo.addItem(label, port.port_name)
        if not ports:
            self.show_message(_NO_PORTS_FOUND_MESSAGE)

    def add_or_update_device(self, device: ConnectedDevice) -> None:
        """Құрылғы карточкасын қосады не жаңартады (``port_name`` кілті
        бойынша). Бір ``device_id`` басқа портқа көшсе, ескі карточка
        жойылады.
        """
        for existing_port, card in list(self._cards_by_port.items()):
            existing_device = card.device()
            if (
                existing_device is not None
                and existing_device.device_id == device.device_id
                and existing_port != device.port_name
            ):
                self._remove_card(existing_port)

        card = self._cards_by_port.get(device.port_name)
        if card is None:
            card = DeviceCard(parent=self._cards_container)
            card.selected.connect(self._on_card_selected)
            card.identify_requested.connect(self._on_card_identify_requested)
            self._cards_by_port[device.port_name] = card

        card.set_device(device)
        self._rebuild_cards_layout()

    def remove_device_by_port(self, port_name: str) -> None:
        """``port_name`` бойынша карточканы жояды (бар болса)."""
        self._remove_card(port_name)
        self._rebuild_cards_layout()

    def clear_devices(self) -> None:
        """Барлық карточкаларды тазалайды."""
        for port_name in list(self._cards_by_port.keys()):
            self._remove_card(port_name)
        self._rebuild_cards_layout()

    def set_scanning(self, scanning: bool) -> None:
        """Жаңарту батырмасының белсенділігін/мәтінін өзгертеді."""
        self._refresh_button.setEnabled(not scanning)
        self._refresh_button.setText("Іздеуде..." if scanning else "Жаңарту")

    def show_message(self, text: str) -> None:
        """Панельдің хабарлама жолағына қысқа мәтін шығарады."""
        self._message_label.setText(text)
        self._message_label.setToolTip(text)

    def _on_identify_clicked(self) -> None:
        port_name = self._port_combo.currentData()
        if not port_name:
            self.show_message(_NO_PORT_SELECTED_MESSAGE)
            return
        baud_rate = self._baud_combo.currentData()
        self.identify_requested.emit(port_name, int(baud_rate))

    def _on_card_identify_requested(self, port_name: str) -> None:
        self.identify_requested.emit(port_name, _DEFAULT_BAUD_RATE)

    def _on_card_selected(self, device: ConnectedDevice) -> None:
        self._selected_port = device.port_name
        for port_name, card in self._cards_by_port.items():
            card.set_selected(port_name == device.port_name)
        self.device_selected.emit(device)

    def _remove_card(self, port_name: str) -> None:
        card = self._cards_by_port.pop(port_name, None)
        if card is not None:
            card.setParent(None)
            card.deleteLater()
            if self._selected_port == port_name:
                self._selected_port = None

    def _rebuild_cards_layout(self) -> None:
        while self._cards_layout.count():
            self._cards_layout.takeAt(0)

        if not self._cards_by_port:
            self._empty_state_label.setVisible(True)
            self._cards_layout.addWidget(self._empty_state_label)
            self._cards_layout.addStretch(1)
            return

        self._empty_state_label.setVisible(False)
        for card in sorted(self._cards_by_port.values(), key=self._card_sort_key):
            self._cards_layout.addWidget(card)
        self._cards_layout.addStretch(1)

    @staticmethod
    def _card_sort_key(card: DeviceCard) -> tuple[int, str]:
        device = card.device()
        if device is None:
            return (_UNKNOWN_SENSOR_ORDER, "")
        return (
            _SENSOR_TYPE_ORDER.get(device.sensor_type.upper(), _UNKNOWN_SENSOR_ORDER),
            device.device_id,
        )
