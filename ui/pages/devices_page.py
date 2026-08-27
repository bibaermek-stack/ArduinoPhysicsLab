"""DevicesPage — application-деңгейлік "Құрылғылар" беті.

Барлық Arduino Physics Lab сенсорларын бір жерден көру/анықтау/ажырату
үшін арналған. Тек ``DeviceManager``/``DeviceScanner``-дің қолданыстағы
public API-ын қолданады (жаңа abstraction жасалмады): бұл бет ешбір
serial port-тың owner-і ЕМЕС, тек ортақ (``MainWindow`` бір рет жасайтын)
``DeviceManager``-ден оқиды/сұрайды. Беттен шыққанда/бет жойылғанда ЕШБІР
байланыс жабылмайды — тек application ``aboutToQuit`` ғана
``shutdown_all()`` шақырады (``app.py``).
"""

from datetime import datetime, timezone

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from domain.entities.connected_device import ConnectedDevice
from infrastructure.serial_comm.device_manager import DeviceManager
from infrastructure.serial_comm.device_scanner import DeviceScanner, SerialDeviceInfo
from infrastructure.serial_comm.packet_parser import PacketParser
from ui.widgets.managed_device_card import STATUS_ERROR, ManagedDeviceCard

_DEFAULT_BAUD_RATE = 115200

_SENSOR_TYPE_ORDER: dict[str, int] = {
    "VOLTAGE": 0,
    "CURRENT": 1,
    "ENERGY": 2,
    "OHMMETER": 3,
    "TEMPERATURE": 4,
}
_UNKNOWN_SENSOR_ORDER = 5

_NO_VALUE_TEXT = "—"

_EMPTY_STATE_TITLE = "Қосылған құрылғылар жоқ"
_EMPTY_STATE_HINT = "USB арқылы сенсорды қосып, төмендегі COM порттан құрылғыны таңдаңыз."

_NO_PORTS_TITLE = "COM порттар табылмады."
_NO_PORTS_HINT = "USB құрылғысының қосылғанын және драйвердің орнатылғанын тексеріңіз."

_ARDUINO_HINT_TEXT = "Arduino / ESP32 құрылғысы болуы мүмкін"

# Phase 21 §14 C/D — порт деңгейінде тұрақты (persistent) сақталатын, НАҚТЫ
# сигналдан алынған сәтсіздік санаттары (transient toast-тан бөлек):
# - "handshake": порт ашылды, бірақ HELLO handshake сәтсіз/уақыты бітті
#   (§ handshake_timeout/device_identification_failed).
# - "busy": порттың ӨЗІН ашу сәтсіз болды (§ port_error — "Access is
#   denied"/"Device busy" секілді OS қатесі осы санатқа жатады).
_ISSUE_HANDSHAKE_FAILED = "handshake"
_ISSUE_BUSY = "busy"

_PORT_STATE_USED = "used"
_PORT_STATE_PENDING = "pending"
_PORT_STATE_BUSY = "busy"
_PORT_STATE_FREE = "free"

_PORT_BUTTON_TEXT: dict[str, str] = {
    _PORT_STATE_USED: "Қосылған",
    _PORT_STATE_PENDING: "Анықталуда...",
    _PORT_STATE_BUSY: "Қолжетімсіз",
    _PORT_STATE_FREE: "Қосу",
}

_HANDSHAKE_FAILED_TITLE = "Құрылғы анықталмады."
_HANDSHAKE_FAILED_HINT = "Порт табылды, бірақ Arduino Physics Lab құрылғысы ретінде расталмады."
_BUSY_ROW_TITLE = "Порт басқа бағдарламада қолданылуда."

_ERROR_PORT_OPEN_FAILED = "{port} портын ашу мүмкін болмады"
_ERROR_HANDSHAKE_TIMEOUT = "Құрылғыны анықтау уақыты аяқталды"
_ERROR_IDENTIFICATION_FAILED = "Құрылғы жауап бермеді"

# § "string-matching a localized OS error" — QSerialPort.errorString()
# құрылымдалған error CODE-ты (тек мәтін) бермейді, сондықтан "busy/
# permission" категориясы НАҚТЫ ЖАЛҒЫЗ қолжетімді сигнал — ағылшын
# тіліндегі Qt/OS әдепкі хабарламаларына сай кілт сөздер. Сәйкес келмесе
# де ЕШБІР дерек жоғалмайды — тек жалпы "port ашу мүмкін болмады"
# хабарламасы көрсетіледі (§ ``_ERROR_PORT_OPEN_FAILED``).
_BUSY_KEYWORDS: tuple[str, ...] = ("permission", "access is denied", "busy", "resource busy")

# Phase 21 §15: PacketParser НАҚТЫ, ӨЗГЕРТІЛМЕГЕН production компоненті
# (§ docs/serial_protocol.md) — "U"/"I"/"TEMP" мәндері firmware-дің ӨЗІНДЕ
# калибрленген (raw ADC ЕМЕС), сондықтан ЕШБІР қосымша формула/
# CalculationEngine контекстісіз тікелей көрсетуге қауіпсіз.
_PREVIEW_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("voltage", "U", "V"),
    ("current", "I", "A"),
    ("temperature", "T", "°C"),
)


def _make_background_transparent(widget: QWidget) -> None:
    """§ ``teacher_dashboard_page._make_background_transparent()``-мен
    БІРДЕЙ себеп/түзету — ``role``-негізді ``QLabel`` өз ЕНІНЕ (QVBoxLayout-
    та толық созылған) сай ``COLOR_BACKGROUND`` тіктөртбұрышын ақ
    ``HomeSummaryCard`` үстінде бояп кетеді. instance-деңгейлік
    ``setStyleSheet()`` ғана жұмыс істейді — контейнерге ЕМЕС, тек жеке
    ``QLabel``-ге қолданылады (§ Phase 20 ``QuestionBankPage`` регрессиясы:
    контейнерге қолдану ІШІНДЕГІ #PrimaryButton баласының фонын бұзады).
    """
    widget.setStyleSheet("background-color: transparent;")


def _format_preview(values: dict[str, float]) -> str | None:
    """§4/§15 — тек НАҚТЫ парсингтелген (``PacketParser``) сан өрістерін
    белгілі бірліктермен пішімдейді. Ешбір мән жоқ болса ``None``."""
    parts = [
        f"{prefix}: {values[key]:.2f} {unit}"
        for key, prefix, unit in _PREVIEW_FIELDS
        if key in values
    ]
    return ", ".join(parts) if parts else None


def _looks_busy(message: str) -> bool:
    lowered = message.lower()
    return any(keyword in lowered for keyword in _BUSY_KEYWORDS)


class DevicesPage(QWidget):
    """Application-lifetime ``DeviceManager``-ге негізделген сенсор
    басқару беті: анықталған құрылғылар + қолжетімді COM порттар.
    """

    def __init__(
        self,
        device_manager: DeviceManager | None = None,
        device_scanner: DeviceScanner | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._device_manager = device_manager or DeviceManager()
        self._device_scanner = device_scanner or DeviceScanner()
        self._packet_parser = PacketParser()

        self._pending_ports: set[str] = set()
        # Phase 21 §3/§14: ескі мotonic-өспелі ``_error_count``-тың орнына —
        # ҚАЗІРГІ, НАҚТЫ бар сәтсіздік күйлерін бетпе-бет сақтайды (port_name
        # -> "busy"/"handshake"), § "Do not fabricate historical error
        # counts" — сан ӘРҚАШАН ``len(self._port_issues)``-тен есептеледі.
        self._port_issues: dict[str, str] = {}
        self._connected_cards: dict[str, ManagedDeviceCard] = {}
        self._port_buttons: dict[str, QPushButton] = {}
        self._latest_ports: tuple[SerialDeviceInfo, ...] = ()
        self._value_labels: dict[str, QLabel] = {}

        self._build_ui()
        self._connect_device_manager()

    # ---- UI құрылысы ---------------------------------------------------

    def _build_ui(self) -> None:
        title_label = QLabel("Құрылғылар", self)
        title_font = title_label.font()
        title_font.setBold(True)
        title_font.setPointSize(title_font.pointSize() + 4)
        title_label.setFont(title_font)

        subtitle_label = QLabel(
            "Arduino Physics Lab жүйесіне қосылған сенсорларды басқару", self
        )
        subtitle_label.setProperty("role", "secondary")

        header_text_layout = QVBoxLayout()
        header_text_layout.setContentsMargins(0, 0, 0, 0)
        header_text_layout.addWidget(title_label)
        header_text_layout.addWidget(subtitle_label)

        self._refresh_button = QPushButton("↻ Жаңарту", self)
        self._refresh_button.clicked.connect(self._on_refresh_clicked)

        header_row = QHBoxLayout()
        header_row.addLayout(header_text_layout)
        header_row.addStretch(1)
        header_row.addWidget(self._refresh_button, 0, Qt.AlignmentFlag.AlignTop)

        summary_row = QHBoxLayout()
        summary_row.addWidget(self._build_kpi_card("connected", "Қосылған құрылғылар"), 1)
        summary_row.addWidget(self._build_kpi_card("available", "Қолжетімді порттар"), 1)
        summary_row.addWidget(self._build_kpi_card("errors", "Қате"), 1)

        self._message_label = QLabel("", self)
        self._message_label.setWordWrap(True)
        self._message_label.setProperty("role", "secondary")

        connected_title = QLabel("ҚОСЫЛҒАН ҚҰРЫЛҒЫЛАР", self)
        connected_title_font = connected_title.font()
        connected_title_font.setBold(True)
        connected_title.setFont(connected_title_font)

        self._empty_state_title_label = QLabel(_EMPTY_STATE_TITLE, self)
        self._empty_state_title_label.setObjectName("WorkspaceEmptyStateLabel")
        empty_title_font = self._empty_state_title_label.font()
        empty_title_font.setBold(True)
        self._empty_state_title_label.setFont(empty_title_font)
        self._empty_state_hint_label = QLabel(_EMPTY_STATE_HINT, self)
        self._empty_state_hint_label.setObjectName("WorkspaceEmptyStateLabel")
        self._empty_state_hint_label.setWordWrap(True)

        self._connected_container = QWidget(self)
        self._connected_layout = QVBoxLayout(self._connected_container)
        self._connected_layout.setContentsMargins(0, 0, 0, 0)

        ports_title = QLabel("ҚОЛЖЕТІМДІ COM ПОРТТАР", self)
        ports_title_font = ports_title.font()
        ports_title_font.setBold(True)
        ports_title.setFont(ports_title_font)

        self._ports_container = QWidget(self)
        self._ports_layout = QVBoxLayout(self._ports_container)
        self._ports_layout.setContentsMargins(0, 0, 0, 0)

        ports_scroll = QScrollArea(self)
        ports_scroll.setWidgetResizable(True)
        ports_scroll.setWidget(self._ports_container)
        ports_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        ports_scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # §14 A "No ports found" — ескі коды тек бос scroll аймағын
        # көрсететін (ЕШБІР хабарламасыз); ЕНДІ results_page.py-дегі ДӘЛ
        # СОЛ QStackedWidget(empty/content) конвенциясы (§ "phantom gap"
        # bag-ынан аулақ болу).
        self._no_ports_title_label = QLabel(_NO_PORTS_TITLE, self)
        self._no_ports_title_label.setObjectName("WorkspaceEmptyStateLabel")
        no_ports_title_font = self._no_ports_title_label.font()
        no_ports_title_font.setBold(True)
        self._no_ports_title_label.setFont(no_ports_title_font)
        self._no_ports_hint_label = QLabel(_NO_PORTS_HINT, self)
        self._no_ports_hint_label.setObjectName("WorkspaceEmptyStateLabel")
        self._no_ports_hint_label.setWordWrap(True)

        # § "Do not accidentally create an opaque root QWidget that hides
        # the watermark" — бұл контейнер ``_ports_stack``-тың (жалғыз
        # stretch=1 элементі, § су таңбаға арналған негізгі бос аймақ)
        # БІР беті, сондықтан QuestionBankEmptyState-пен БІРДЕЙ ГЛОБАЛ
        # object-name селекторы қажет (instance ``setStyleSheet()`` ЕМЕС
        # — § Phase 20 регрессиясы, ІШІНДЕГІ button баласының фонын
        # бұзар еді).
        no_ports_widget = QWidget(self)
        no_ports_widget.setObjectName("DevicesNoPortsEmptyState")
        no_ports_layout = QVBoxLayout(no_ports_widget)
        no_ports_layout.setContentsMargins(0, 0, 0, 0)
        no_ports_layout.addWidget(self._no_ports_title_label)
        no_ports_layout.addWidget(self._no_ports_hint_label)
        no_ports_layout.addStretch(1)

        self._ports_stack = QStackedWidget(self)
        self._ports_stack.addWidget(no_ports_widget)
        self._ports_stack.addWidget(ports_scroll)

        separator = QFrame(self)
        separator.setFrameShape(QFrame.Shape.HLine)

        layout = QVBoxLayout(self)
        layout.addLayout(header_row)
        layout.addLayout(summary_row)
        layout.addWidget(self._message_label)
        layout.addWidget(connected_title)
        layout.addWidget(self._connected_container)
        layout.addWidget(separator)
        layout.addWidget(ports_title)
        layout.addWidget(self._ports_stack, 1)

        self._render()

    def _build_kpi_card(self, key: str, label: str) -> QWidget:
        card = QFrame(self)
        card.setObjectName("HomeSummaryCard")

        value_label = QLabel(_NO_VALUE_TEXT, card)
        value_label.setProperty("role", "cardValue")
        _make_background_transparent(value_label)
        self._value_labels[key] = value_label

        caption_label = QLabel(label, card)
        caption_label.setProperty("role", "cardLabel")
        _make_background_transparent(caption_label)

        card_layout = QVBoxLayout(card)
        card_layout.addWidget(value_label)
        card_layout.addWidget(caption_label)
        return card

    def _connect_device_manager(self) -> None:
        self._device_manager.device_identified.connect(self._on_device_identified)
        self._device_manager.port_disconnected.connect(self._on_port_disconnected)
        self._device_manager.port_error.connect(self._on_port_error)
        self._device_manager.handshake_timeout.connect(self._on_handshake_timeout)
        self._device_manager.device_identification_failed.connect(
            self._on_identification_failed
        )
        # Phase 21 §15: белсенді карточкаларға арналған НАҚТЫ (fabrication-
        # сыз) соңғы өлшеу алдын ала көрінісі.
        self._device_manager.line_received.connect(self._on_line_received)

    # ---- Router интерфейсі ----------------------------------------------

    def on_enter(self) -> None:
        """Бет көрсетілер алдында COM порттарды қайта сканерлейді."""
        self._refresh()

    # ---- Пайдаланушы әрекеттері ------------------------------------------

    def _on_refresh_clicked(self) -> None:
        self._refresh()

    def _refresh(self) -> None:
        self._message_label.setText("")
        self._latest_ports = self._device_scanner.scan()
        # §7 "remove ports that physically disappeared" — сканерден
        # кейін ЖОҚ порттарға қатысты ескі pending/issue күйі тазаланады
        # (§ "preserve healthy active connections" — байланысқан
        # құрылғылар DeviceManager-дің ӨЗ данасында сақталады, бұл жерге
        # ЕШБІР қатысы жоқ).
        current_port_names = {port.port_name for port in self._latest_ports}
        self._pending_ports &= current_port_names
        self._port_issues = {
            port: reason for port, reason in self._port_issues.items()
            if port in current_port_names
        }
        self._render()

    def _on_identify_clicked(self, port_name: str) -> None:
        self._pending_ports.add(port_name)
        self._port_issues.pop(port_name, None)
        self._device_manager.identify(port_name, _DEFAULT_BAUD_RATE)
        self._render()

    def _on_disconnect_clicked(self, port_name: str) -> None:
        self._device_manager.disconnect_port(port_name)
        self._render()

    # ---- DeviceManager сигналдары -----------------------------------------

    def _on_device_identified(self, device: ConnectedDevice) -> None:
        self._pending_ports.discard(device.port_name)
        self._port_issues.pop(device.port_name, None)
        self._render()

    def _on_port_disconnected(self, port_name: str) -> None:
        # §12 (hot-plug): физикалық ажырау — ескі pending/issue күйі осы
        # портқа қатысты мағынасын жоғалтады, әрі порттың ӨЗІ жүйеден
        # мүлде жоғалуы мүмкін (§7-мен БІРДЕЙ "re-scan on known change"
        # принципі), сондықтан толық ``_refresh()`` шақырылады.
        self._pending_ports.discard(port_name)
        self._port_issues.pop(port_name, None)
        card = self._connected_cards.get(port_name)
        if card is not None:
            card.set_preview(None)
            card.set_last_data_at(None)
        self._refresh()

    def _on_port_error(self, port_name: str, message: str) -> None:
        # §14 D "Port busy" — портты АШУ сәтсіз болды (HELLO handshake
        # басталмай тұрып). Тек хабарлама шынымен "busy/permission"
        # кілт сөзіне сай келгенде ғана НАҚТЫ "Порт басқа бағдарламада
        # қолданылуда" деп белгіленеді (§ "Do not fabricate" — сай
        # келмесе, себебі белгісіз, тек transient toast көрсетіледі,
        # тұрақты жол-деңгейлік болжам жасалмайды).
        self._pending_ports.discard(port_name)
        if _looks_busy(message):
            self._port_issues[port_name] = _ISSUE_BUSY
        else:
            self._port_issues.pop(port_name, None)

        self._show_error(_ERROR_PORT_OPEN_FAILED.format(port=port_name))

        # §5 "Error: red semantic status" — қате БЕЛСЕНДІ (identified)
        # құрылғының портында пайда болса (мыс. уақытша serial үзіліс,
        # ЕШБІР толық "disconnected" оқиғасынсыз), карточка ӨЗІ ҚЫЗЫЛ
        # түске ауысады. ``_show_error()`` (демек ``_render()``) ӘЛДЕҚАШАН
        # аяқталғаннан КЕЙІН шақырылады — ``_render_connected_section()``-
        # тегі ``card.set_device(device)`` статусты СТАТИК каталог
        # мәніне қайта орнатып жібермеуі үшін (§ реттілік bag-ы).
        card = self._connected_cards.get(port_name)
        if card is not None:
            card.set_status(STATUS_ERROR)

    def _on_handshake_timeout(self, port_name: str) -> None:
        # §14 C "Handshake fails" — порт ашылды, бірақ HELLO жауап
        # бермеді.
        self._pending_ports.discard(port_name)
        self._port_issues[port_name] = _ISSUE_HANDSHAKE_FAILED
        self._show_error(_ERROR_HANDSHAKE_TIMEOUT)

    def _on_identification_failed(self, _message: str) -> None:
        # device_identification_failed мына port-қа қатысты екені әрдайым
        # анық емес (DeviceIdentifier мессажында port атауы кепілденбейді).
        # Қауіпсіз fallback: қазір "Анықталуда..." деп белгіленген барлық
        # порттарды §14 C (handshake сәтсіз) күйіне ауыстырамыз (әдетте
        # біреу ғана болады).
        for port_name in self._pending_ports:
            self._port_issues[port_name] = _ISSUE_HANDSHAKE_FAILED
        self._pending_ports.clear()
        self._show_error(_ERROR_IDENTIFICATION_FAILED)

    def _on_line_received(self, port_name: str, line: str) -> None:
        """§4/§15: белсенді карточкаға НАҚТЫ соңғы өлшеу алдын ала
        көрінісін қосады. ``PacketParser`` (ӨЗГЕРТІЛМЕГЕН, production
        компоненті) арқылы жарамсыз/қатысы жоқ жолдар үнсіз өткізіп
        жіберіледі — ешбір жалған мән ЕШҚАШАН көрсетілмейді."""
        card = self._connected_cards.get(port_name)
        if card is None:
            return
        result = self._packet_parser.parse_line(line)
        if not result.is_valid:
            return
        preview_text = _format_preview(result.values)
        if preview_text is None:
            return
        card.set_preview(preview_text)
        card.set_last_data_at(datetime.now(timezone.utc))

    def _show_error(self, text: str) -> None:
        self._message_label.setText(text)
        self._render()

    # ---- Рендеринг ------------------------------------------------------

    def _render(self) -> None:
        self._render_summary()
        self._render_connected_section()
        self._render_ports_section()

    def _render_summary(self) -> None:
        connected_count = len(self._device_manager.get_connected_devices())
        self._value_labels["connected"].setText(str(connected_count))
        self._value_labels["available"].setText(str(len(self._latest_ports)))
        self._value_labels["errors"].setText(str(len(self._port_issues)))

    def _render_connected_section(self) -> None:
        devices = self._device_manager.get_connected_devices()
        current_ports = {device.port_name for device in devices}

        for port_name in list(self._connected_cards.keys()):
            if port_name not in current_ports:
                card = self._connected_cards.pop(port_name)
                card.setParent(None)
                card.deleteLater()

        for device in devices:
            card = self._connected_cards.get(device.port_name)
            if card is None:
                card = ManagedDeviceCard(parent=self._connected_container)
                card.disconnect_requested.connect(self._on_disconnect_clicked)
                self._connected_cards[device.port_name] = card
            card.set_device(device)

        while self._connected_layout.count():
            self._connected_layout.takeAt(0)

        if not devices:
            self._connected_layout.addWidget(self._empty_state_title_label)
            self._connected_layout.addWidget(self._empty_state_hint_label)
            self._empty_state_title_label.setVisible(True)
            self._empty_state_hint_label.setVisible(True)
            return

        self._empty_state_title_label.setVisible(False)
        self._empty_state_hint_label.setVisible(False)
        for device in sorted(devices, key=self._device_sort_key):
            self._connected_layout.addWidget(self._connected_cards[device.port_name])

    @staticmethod
    def _device_sort_key(device: ConnectedDevice) -> tuple[int, str]:
        return (
            _SENSOR_TYPE_ORDER.get(device.sensor_type.upper(), _UNKNOWN_SENSOR_ORDER),
            device.device_id,
        )

    def _render_ports_section(self) -> None:
        while self._ports_layout.count():
            item = self._ports_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._port_buttons = {}

        if not self._latest_ports:
            self._ports_stack.setCurrentIndex(0)
            return
        self._ports_stack.setCurrentIndex(1)

        for port in self._latest_ports:
            self._ports_layout.addWidget(self._build_port_row(port))
        self._ports_layout.addStretch(1)

    def _build_port_row(self, port: SerialDeviceInfo) -> QWidget:
        row = QFrame(self._ports_container)
        row.setObjectName("DevicePortRow")

        name_label = QLabel(port.port_name, row)
        name_font = name_label.font()
        name_font.setBold(True)
        name_label.setFont(name_font)

        state = self._port_state(port.port_name)
        button = QPushButton(_PORT_BUTTON_TEXT[state], row)
        button.setEnabled(state in (_PORT_STATE_FREE, _PORT_STATE_BUSY))
        if state in (_PORT_STATE_FREE, _PORT_STATE_BUSY):
            button.clicked.connect(
                lambda _checked=False, p=port.port_name: self._on_identify_clicked(p)
            )
        self._port_buttons[port.port_name] = button

        top_row = QHBoxLayout()
        top_row.addWidget(name_label)
        top_row.addStretch(1)
        top_row.addWidget(button)

        # §6 "serial description, manufacturer, VID/PID, detected/
        # recognized device type" — ``SerialDeviceInfo``-дың БАРЛЫҚ
        # бұрыннан бар өрістері (§ DeviceScanner audit-і, ЕШБІР жаңа
        # metadata ойдан шығарылмайды).
        detail_parts = [port.description or _NO_VALUE_TEXT]
        if port.manufacturer:
            detail_parts.append(port.manufacturer)
        if port.vendor_id is not None and port.product_id is not None:
            detail_parts.append(f"VID:{port.vendor_id:04X} PID:{port.product_id:04X}")
        detail_label = QLabel(" • ".join(detail_parts), row)
        detail_label.setProperty("role", "secondary")

        row_layout = QVBoxLayout(row)
        row_layout.addLayout(top_row)
        row_layout.addWidget(detail_label)

        if port.is_likely_arduino:
            arduino_hint_label = QLabel(_ARDUINO_HINT_TEXT, row)
            arduino_hint_label.setProperty("role", "secondary")
            row_layout.addWidget(arduino_hint_label)

        # §14 C/D — тұрақты (ағымдағы Refresh/қайталау дейін сақталатын)
        # сәтсіздік хабары, тек НАҚТЫ шыққан сигналдан (§ _port_issues).
        issue = self._port_issues.get(port.port_name)
        if issue == _ISSUE_HANDSHAKE_FAILED:
            issue_title_label = QLabel(_HANDSHAKE_FAILED_TITLE, row)
            issue_title_label.setProperty("role", "error")
            issue_hint_label = QLabel(_HANDSHAKE_FAILED_HINT, row)
            issue_hint_label.setProperty("role", "secondary")
            issue_hint_label.setWordWrap(True)
            row_layout.addWidget(issue_title_label)
            row_layout.addWidget(issue_hint_label)
        elif issue == _ISSUE_BUSY:
            issue_title_label = QLabel(_BUSY_ROW_TITLE, row)
            issue_title_label.setProperty("role", "error")
            row_layout.addWidget(issue_title_label)

        return row

    def _port_state(self, port_name: str) -> str:
        if self._device_manager.is_port_connected(port_name):
            return _PORT_STATE_USED
        if port_name in self._pending_ports:
            return _PORT_STATE_PENDING
        if self._port_issues.get(port_name) == _ISSUE_BUSY:
            return _PORT_STATE_BUSY
        return _PORT_STATE_FREE
