"""ManagedDeviceCard — application-деңгейлік Devices Page-те бір
``ConnectedDevice``-ті көрсететін толық ені бар dashboard карточкасы.

Эксперимент бетіндегі ``DeviceCard``-тан (кіші, тұрақты өлшемді,
click-to-select) әдейі бөлек: бұл карточканың UX мақсаты басқа — толық
ені бар қатар, "Толығырақ" арқылы ашылатын details аймағы және (бар
болса) "Ажырату" әрекеті.
"""

from datetime import datetime

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from domain.constants.sensor_types import KNOWN_SENSOR_TYPES
from domain.entities.connected_device import ConnectedDevice
from ui.themes.theme_manager import (
    COLOR_ERROR,
    COLOR_SUCCESS,
    COLOR_TEXT_SECONDARY,
    COLOR_WARNING,
)

# § domain.constants.sensor_types.KNOWN_SENSOR_TYPES-пен БІРДЕЙ 5 түр
# (VOLTAGE/CURRENT/ENERGY/OHMMETER/TEMPERATURE) — Phase 21-ге дейін бұл
# жерде TEMPERATURE ЖОҚ еді (нақты домен тұрақтысынан "артта қалған"
# регрессия, § "Prefer the project's canonical device registry").
_SENSOR_TYPE_NAMES_KK: dict[str, str] = {
    "VOLTAGE": "Кернеу датчигі",
    "CURRENT": "Ток датчигі",
    "ENERGY": "Қуат және энергия датчигі",
    "OHMMETER": "Омметр",
    "TEMPERATURE": "Температура сенсоры",
}
_UNKNOWN_SENSOR_TYPE_NAME_KK = "Белгісіз датчик"
_NO_VALUE_TEXT = "—"

STATUS_CONNECTED = "connected"
STATUS_ERROR = "error"
STATUS_DISCONNECTED = "disconnected"
# Phase 21 §5 "Unknown device: warning" — HELLO handshake СӘТТІ өтті,
# бірақ ``sensor_type`` ``KNOWN_SENSOR_TYPES``-те ЖОҚ (§ device.warnings-
# тегі "белгісіз сенсор түрі" ескертуімен БІРДЕЙ нақты негіз, тек
# карточка деңгейінде ВИЗУАЛДЫ түрде де көрсетіледі).
STATUS_UNKNOWN_DEVICE = "unknown_device"

_STATUS_TEXT_KK: dict[str, str] = {
    STATUS_CONNECTED: "Қосылды",
    STATUS_ERROR: "Қате",
    STATUS_DISCONNECTED: "Ажыратылды",
    STATUS_UNKNOWN_DEVICE: "Белгісіз құрылғы",
}


class ManagedDeviceCard(QFrame):
    """Devices Page-тегі бір анықталған сенсордың толық ені бар карточкасы."""

    disconnect_requested = Signal(str)  # port_name

    def __init__(
        self, device: ConnectedDevice | None = None, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._device: ConnectedDevice | None = None

        self.setObjectName("ManagedDeviceCard")
        self.setFrameShape(QFrame.Shape.StyledPanel)

        self._title_label = QLabel(self)
        title_font = self._title_label.font()
        title_font.setBold(True)
        title_font.setPointSize(title_font.pointSize() + 1)
        self._title_label.setFont(title_font)

        self._status_dot = QLabel(self)
        self._status_dot.setFixedSize(10, 10)
        self._status_text_label = QLabel(self)

        header_row = QHBoxLayout()
        header_row.addWidget(self._title_label)
        header_row.addStretch(1)
        header_row.addWidget(self._status_dot)
        header_row.addWidget(self._status_text_label)

        self._device_id_label = QLabel(self)
        self._summary_label = QLabel(self)  # "COM6 • INA226"

        # Phase 21 §4/§15: соңғы НАҚТЫ (fabrication-сыз) өлшеу алдын ала
        # көрінісі — тек ``PacketParser``-мен НАҚТЫ парсингтелген
        # ``EXP=...`` пакеті келгенде ғана орнатылады (§ ``DevicesPage.
        # _on_line_received()``). Дерек әлі жоқ болса ЖАСЫРЫН қалады —
        # ешбір "0.00 V" секілді жалған бастапқы мән ЕШҚАШАН көрсетілмейді.
        self._preview_label = QLabel(self)
        preview_font = self._preview_label.font()
        preview_font.setBold(True)
        self._preview_label.setFont(preview_font)
        self._preview_label.setVisible(False)

        self._last_data_label = QLabel(self)
        self._last_data_label.setProperty("role", "secondary")
        self._last_data_label.setVisible(False)

        self._details_toggle_button = QPushButton("Толығырақ", self)
        self._details_toggle_button.setCheckable(True)
        self._details_toggle_button.toggled.connect(self._on_details_toggled)

        self._disconnect_button = QPushButton("Ажырату", self)
        self._disconnect_button.clicked.connect(self._on_disconnect_clicked)

        actions_row = QHBoxLayout()
        actions_row.addStretch(1)
        actions_row.addWidget(self._disconnect_button)
        actions_row.addWidget(self._details_toggle_button)

        self._details_frame = QFrame(self)
        self._details_layout = QVBoxLayout(self._details_frame)
        self._details_frame.setVisible(False)

        layout = QVBoxLayout(self)
        layout.addLayout(header_row)
        layout.addWidget(self._device_id_label)
        layout.addWidget(self._summary_label)
        layout.addWidget(self._preview_label)
        layout.addWidget(self._last_data_label)
        layout.addLayout(actions_row)
        layout.addWidget(self._details_frame)

        if device is not None:
            self.set_device(device)

    def set_device(self, device: ConnectedDevice) -> None:
        """Карточканың мазмұнын берілген ``ConnectedDevice``-пен толтырады."""
        self._device = device

        display_name = _SENSOR_TYPE_NAMES_KK.get(
            device.sensor_type.upper(), None
        ) or (device.sensor_type or _UNKNOWN_SENSOR_TYPE_NAME_KK)
        self._title_label.setText(display_name)
        self._device_id_label.setText(device.device_id)
        self._summary_label.setText(f"{device.port_name} • {device.chip or _NO_VALUE_TEXT}")

        # §5 "Unknown device: warning" — HELLO СӘТТІ өтті, бірақ
        # sensor_type канондық тізімде ЖОҚ (§ domain.constants.
        # sensor_types.KNOWN_SENSOR_TYPES, device.warnings-тегі "белгісіз
        # сенсор түрі" ескертуімен БІРДЕЙ негіз).
        initial_status = (
            STATUS_CONNECTED
            if device.sensor_type.upper() in KNOWN_SENSOR_TYPES
            else STATUS_UNKNOWN_DEVICE
        )
        self._set_status(initial_status)
        self._rebuild_details()

    def device(self) -> ConnectedDevice | None:
        """Карточка қазір көрсетіп тұрған ``ConnectedDevice``-ті қайтарады."""
        return self._device

    def set_status(self, status: str) -> None:
        """Байланыс күйін (Connected/Error/Disconnected/Unknown) сырттан
        орнатады."""
        self._set_status(status)

    def set_preview(self, text: str | None) -> None:
        """§4/§15: соңғы НАҚТЫ парсингтелген өлшеу мәнін көрсетеді (мыс.
        "U: 5.12 V"). ``None`` — дерек әлі жоқ, лейбл толық жасырылады
        (ешбір "0.00"-тәрізді жалған бастапқы мән көрсетілмейді)."""
        self._preview_label.setText(text or "")
        self._preview_label.setVisible(bool(text))

    def set_last_data_at(self, timestamp: datetime | None) -> None:
        """§4/§13 "last data time if available" — соңғы қабылданған
        пакеттің НАҚТЫ уақыты. ``None`` — дерек әлі жоқ, лейбл жасырын."""
        if timestamp is None:
            self._last_data_label.setVisible(False)
            return
        self._last_data_label.setText(f"Соңғы дерек: {timestamp.astimezone().strftime('%H:%M:%S')}")
        self._last_data_label.setVisible(True)

    def is_details_expanded(self) -> bool:
        return self._details_toggle_button.isChecked()

    def _set_status(self, status: str) -> None:
        color = {
            STATUS_CONNECTED: COLOR_SUCCESS,
            STATUS_ERROR: COLOR_ERROR,
            STATUS_DISCONNECTED: COLOR_TEXT_SECONDARY,
            STATUS_UNKNOWN_DEVICE: COLOR_WARNING,
        }[status]
        self._status_dot.setStyleSheet(f"background-color: {color}; border-radius: 5px;")
        self._status_text_label.setText(_STATUS_TEXT_KK[status])

    def _on_details_toggled(self, checked: bool) -> None:
        self._details_frame.setVisible(checked)
        self._details_toggle_button.setText("Жасыру" if checked else "Толығырақ")

    def _on_disconnect_clicked(self) -> None:
        if self._device is not None:
            self.disconnect_requested.emit(self._device.port_name)

    def _rebuild_details(self) -> None:
        while self._details_layout.count():
            item = self._details_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        device = self._device
        if device is None:
            return

        rows: list[tuple[str, str | None]] = [
            ("Device ID", device.device_id),
            ("Sensor type", device.sensor_type),
            ("COM port", device.port_name),
            ("Model", device.model),
            ("Firmware", device.firmware_version),
            ("Chip", device.chip),
            ("Serial number", device.serial_number),
            ("Connection time", device.connected_at.astimezone().strftime("%Y-%m-%d %H:%M:%S")),
        ]
        for label, value in rows:
            if not value:
                continue
            row_label = QLabel(f"{label}: {value}", self._details_frame)
            self._details_layout.addWidget(row_label)

        if device.warnings:
            warnings_label = QLabel(
                "Warnings: " + "; ".join(device.warnings), self._details_frame
            )
            warnings_label.setWordWrap(True)
            self._details_layout.addWidget(warnings_label)
