"""MeasurementWorkspace — барлық болашақ датчиктерге ортақ, бір
ConnectedDevice-тің нақты уақыттағы сандық көрсеткіштерін көрсететін
V1.0 workspace виджеті.

Бұл виджет ештеңені өзі есептемейді — тек ``ConnectedDevice``/
``Measurement`` объектілерін көрсетеді және пайдаланушы әрекеттерін
(Бастау/Тоқтату/Тазалау) Qt signal ретінде шығарады. ``LiveGraphWidget``
(нақты уақыт графигі) мен ``MeasurementTableWidget`` (measurement
кестесі) екеуі де енгізілген.
"""

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from domain.entities.connected_device import ConnectedDevice
from domain.entities.experiment_definition import ExperimentDefinition
from domain.entities.measurement import Measurement
from domain.entities.sensor_channel import SensorChannel
from ui.themes.theme_manager import current_theme
from ui.widgets.live_graph import _TOOLBAR_ICON_PX, _load_toolbar_icon, LiveGraphWidget
from ui.widgets.measurement_card import MeasurementCard
from ui.widgets.measurement_table import MeasurementTableWidget
from ui.widgets.motion import flash_value_update

# ``LiveGraphWidget``-тегі toolbar иконка жүктегішінің қайта пайдаланылуы
# (§ ``MeasurementWorkspace`` бұрыннан осы модульден ``LiveGraphWidget``-ті
# импорттайды — циклдік импорт қаупі жоқ, ``live_graph.py``
# ``measurement_workspace.py``-ды ЕШҚАШАН импорттамайды).
_ACTION_ICON_PX = _TOOLBAR_ICON_PX

_SENSOR_TYPE_NAMES_KK: dict[str, str] = {
    "VOLTAGE": "Кернеу датчигі",
    "CURRENT": "Ток датчигі",
    "ENERGY": "Қуат және энергия датчигі",
    "OHMMETER": "Омметр",
}
_UNKNOWN_SENSOR_TYPE_NAME_KK = "Белгісіз датчик"

_NO_DEVICE_TEXT = "Құрылғы таңдалмаған"
_NO_VALUE_TEXT = "—"
_NO_CHIP_TEXT = "—"
_DEFAULT_DECIMALS = 3
_DEFAULT_GRAPH_CARD_TITLE = "Нақты уақыт графигі"
_LIVE_BADGE_TEXT = "● LIVE"


class MeasurementWorkspace(QWidget):
    """Таңдалған құрылғының ақпараты мен нақты уақыт өлшемдерін
    көрсететін workspace.
    """

    start_requested = Signal()
    stop_requested = Signal()
    clear_requested = Signal()
    export_requested = Signal(str)  # "csv" немесе "excel"
    connect_device_requested = Signal()

    def __init__(
        self, parent: QWidget | None = None, default_auto_scale: bool = True
    ) -> None:
        super().__init__(parent)
        # Phase 22: ``LiveGraphWidget``-ке ӘРІ ҚАРАЙ жеткізілетін бастапқы
        # "Автоауқым" checkbox күйі (§ ``live_graph.py``-дегі БІРДЕЙ
        # түсініктеме).
        self._default_auto_scale = default_auto_scale
        # Phase 41 background regression fix: object name — ThemeManager-де
        # осы атпен нақты мөлдірлік ережесі бар (§ WorkspaceBackdrop су
        # таңбасы experiment workspace бетінде де көрінуі үшін).
        self.setObjectName("MeasurementWorkspace")
        # Phase 32: shared workspace architecture fix — MeasurementWorkspace
        # is the primary flexible region of ExperimentWorkspacePage and must
        # claim all remaining width/height (previously relied on it being
        # the sole/last stretched item, which worked implicitly but wasn't
        # architecturally explicit or testable).
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._device: ConnectedDevice | None = None
        self._is_running = False
        self._is_starting = False
        self._ready = False
        self._connect_action_role_enabled = False
        self._value_labels: dict[str, QLabel] = {}
        self._channel_map: dict[str, SensorChannel] = {}
        self._optional_channels: tuple[SensorChannel, ...] = ()
        self._optional_readout_widgets: dict[str, QWidget] = {}
        self._optional_visible = False
        self._optional_show_label = ""
        self._optional_hide_label = ""

        # Кезeng 29: graph card MIN/AVG/MAX статистикасы — "негізгі"
        # сызылатын шама (definition.graph_y_channels[0]) үшін, GRAPH-ты
        # ҚОРЕКТЕНДІРЕТІН дәл сол Measurement ағынынан жиналған running
        # aggregate (параллель дерек қоймасы ЖОҚ).
        self._primary_stat_channel_key: str | None = None
        self._primary_stat_unit: str = ""
        self._primary_stat_decimals: int = _DEFAULT_DECIMALS
        self._primary_stat_label: str = ""
        self._primary_stat_min: float | None = None
        self._primary_stat_max: float | None = None
        self._primary_stat_sum: float = 0.0
        self._primary_stat_count: int = 0

        # Phase 32.2: ExperimentWorkspacePage-тің ӨЗ header-інде
        # (``_title_label``) дәл СОЛ ``experiment.title`` бұрыннан
        # көрсетіледі — бұл екінші көшірме тек жасырын атрибут ретінде
        # сақталады (ескі тесттер/интеграциялар ``.text()`` арқылы оқи
        # алады), бірақ ЕШҚАШАН экранға шығарылмайды (hidden widget —
        # Qt layout-та орын алмайды, metric cards ДӘЛ осы орыннан
        # басталады).
        self._experiment_title_label = QLabel(self)
        experiment_title_font = self._experiment_title_label.font()
        experiment_title_font.setBold(True)
        experiment_title_font.setPointSize(experiment_title_font.pointSize() + 3)
        self._experiment_title_label.setFont(experiment_title_font)
        self._experiment_title_label.setVisible(False)

        self._stack = QStackedWidget(self)
        self._no_device_page = self._build_no_device_page()
        self._device_page = self._build_device_page()
        self._stack.addWidget(self._no_device_page)
        self._stack.addWidget(self._device_page)
        # Phase 32.1: ``_no_device_page`` тек ОСЫ bootstrap сәтке —
        # ``configure_for_experiment()`` ЕШҚАШАН шақырылмаған кезге —
        # тиесілі (ExperimentWorkspacePage.on_enter() әрдайым Router
        # арқылы бетті экранда көрсетпес БҰРЫН шақырады, сондықтан
        # пайдаланушы бұл placeholder-ды нақты ЕШҚАШАН көрмейді).
        # ``configure_for_experiment()`` шақырылғаннан КЕЙІН бет
        # ЕШҚАШАН бұл параққа қайтарылмайды — hardware readiness (0/N,
        # ішінара N/M, толық N/N) тек Start/Тоқтату/Тазалау батырмалар
        # мен readiness индикаторларын басқарады, workspace-тің ӨЗІН ЕМЕС.
        self._stack.setCurrentWidget(self._no_device_page)

        self._status_message_label = QLabel("", self)
        self._status_message_label.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addWidget(self._experiment_title_label)
        layout.addWidget(self._stack)
        layout.addWidget(self._status_message_label)

        self._update_button_states()

    # ---- Public API ---------------------------------------------------

    def configure_for_experiment(self, definition: ExperimentDefinition) -> None:
        """Workspace-ты жаңа тәжірибеге бейімдейді: тәжірибе атауын
        көрсетеді, readout карточкаларын ``definition.get_display_channels()``
        бойынша қайта құрады (бұрынғы мәндер «—» күйіне қайтады),
        ``LiveGraphWidget``/``MeasurementTableWidget``-ті конфигурациялайды.
        ``definition.get_optional_display_channels()`` (мыс. Қуат) болса,
        readout/table-де ӘДЕПКІ ЖАСЫРЫН қосымша баған/карточка ретінде
        қосылады (toggle батырмасы арқылы, backend есептеуге қатысы жоқ).
        Ешбір физикалық есеп жасамайды.
        """
        self._experiment_title_label.setText(definition.title)

        display_channels = definition.get_display_channels()
        optional_channels = definition.get_optional_display_channels()
        self._optional_channels = optional_channels
        self._channel_map = {
            channel.key: channel for channel in (*display_channels, *optional_channels)
        }
        self._rebuild_readouts(display_channels, optional_channels)

        self._live_graph.configure_channels(
            display_channels,
            x_channel=definition.graph_x_channel,
            y_channels=definition.graph_y_channels or None,
            connect_points=definition.graph_connect_points,
            show_fit=definition.graph_show_fit,
            x_label=definition.graph_x_label,
            y_label=definition.graph_y_label,
            title=definition.graph_title,
            dedup_x_tolerance=definition.graph_dedup_x_tolerance,
            dedup_y_tolerance=definition.graph_dedup_y_tolerance,
            fit_result_prefix=definition.graph_fit_result_prefix,
            fit_unit=definition.graph_fit_unit,
            capture_mode=definition.graph_capture_mode == "manual",
            capture_sample_count=definition.graph_capture_sample_count,
            capture_x_tolerance=definition.graph_capture_x_tolerance,
            capture_y_tolerance=definition.graph_capture_y_tolerance,
            fit_x_symbol=definition.graph_fit_x_symbol,
            fit_y_symbol=definition.graph_fit_y_symbol,
            stacked=definition.graph_stacked,
            stacked_titles=definition.graph_stacked_titles,
            stacked_y_labels=definition.graph_stacked_y_labels,
            derived_analysis=definition.graph_derived_analysis,
            fit_display_name=definition.graph_fit_display_name,
            allow_delta_measurement=definition.graph_allow_delta_measurement,
            rate_of_change=definition.graph_rate_of_change,
            experiment_title=definition.title,
        )
        self._measurement_table.configure_channels((*display_channels, *optional_channels))

        # Phase 32.1: жаңа тәжірибе конфигурацияланған сәттен бастап,
        # ЕШБІР сенсор оқиғасын күтпей-ақ, толық workspace (metric cards/
        # toolbar/graph/table) көрінеді — ары қарай тек readiness/
        # button-күйі өзгереді, бет ЕШҚАШАН _no_device_page-ге қайтарылмайды
        # (§ set_ready()/clear_device()). Root cause: бұрын бұл жерде
        # ешбір stack ауысуы болмайтын, сондықтан 0 құрылғымен ашылған
        # тәжірибе беті ЕШҚАШАН _device_page-ге жетпейтін (readiness_changed
        # сигналы coordinator-нан ешқашан келмейтін, себебі DeviceManager-де
        # тіркелген құрылғы жоқ).
        self._stack.setCurrentWidget(self._device_page)

        self._graph_card_title_label.setText(
            definition.graph_title or _DEFAULT_GRAPH_CARD_TITLE
        )
        y_channels = definition.graph_y_channels
        primary_key = y_channels[0] if y_channels else None
        self._primary_stat_channel_key = primary_key
        primary_channel = self._channel_map.get(primary_key) if primary_key else None
        self._primary_stat_unit = primary_channel.unit if primary_channel else ""
        self._primary_stat_decimals = (
            primary_channel.decimals if primary_channel else _DEFAULT_DECIMALS
        )
        # Phase 33A §17: MIN/AVG/MAX қай айнымалыға қатысты екенін НАҚТЫ
        # көрсету (тек presentation — жаңа статистика архитектурасы ЕМЕС).
        # Көп арналы графиктерде (мыс. stacked current-voltage) statistics
        # тек graph_y_channels[0]-ге қатысты болғандықтан, бұрын мұны
        # тек "MIN x AVG x MAX x" деп көрсету екі арнаның да статистикасы
        # секілді көрінетін.
        self._primary_stat_label = (
            primary_channel.display_name if primary_channel else (primary_key or "")
        )
        self._reset_primary_stats()
        self._graph_stats_label.setVisible(primary_key is not None)

        self._optional_show_label = f"⚡ {definition.optional_display_show_label}"
        self._optional_hide_label = f"⚡ {definition.optional_display_hide_label}"
        self._optional_visible = False
        self._optional_toggle_button.setVisible(bool(optional_channels))
        self._optional_toggle_button.setText(self._optional_show_label)
        for channel in optional_channels:
            self._measurement_table.set_column_visible(channel.key, False)

    def set_ready(self, ready: bool) -> None:
        """Multi-device тәжірибелерде (бір ``ConnectedDevice`` жоқ, бірнеше
        физикалық сенсор қажет) Start/Clear батырмаларының қолжетімділігін
        басқарады.

        ``set_device()``-тен өзгеше — жеке құрылғы ақпаратын (title/id/
        firmware/chip) көрсетпейді, себебі multi-device режимінде "жалғыз
        құрылғы" деген түсінік жоқ (``DevicePanel``-дегі readiness
        checklist соны алмастырады).

        Phase 32.1: бұрын бұл әдіс ``_stack``-ты ``_device_page``/
        ``_no_device_page`` арасында ауыстыратын — сондықтан ready=False
        (0/N немесе ішінара N/M) кезінде БҮКІЛ workspace (metric cards/
        graph/table) экраннан жоғалатын. Ендi бет ``configure_for_
        experiment()``-тен бастап ТҰРАҚТЫ көрінеді — бұл әдіс тек
        readiness-ке байланысты Start/Тоқтату/Тазалау батырмаларының
        қолжетімділігін (``_update_button_states()`` арқылы) басқарады.
        """
        self._ready = ready
        self._live_graph.set_devices_ready(ready)
        if ready:
            self._clear_measurement_history()
        self._update_button_states()
        self._update_connect_action_visibility()

    def set_device(self, device: ConnectedDevice) -> None:
        """Таңдалған құрылғының ақпаратын көрсетіп, workspace-ты
        "құрылғы бар" күйіне ауыстырады. Ескі өлшем көрсеткіштері
        тазаланады, тәжірибе idle (running емес) күйінен басталады.
        Ешбір exception сыртқа шықпайды.
        """
        try:
            self._device = device

            display_name = _SENSOR_TYPE_NAMES_KK.get(
                device.sensor_type.upper(), _UNKNOWN_SENSOR_TYPE_NAME_KK
            )
            self._title_label.setText(display_name)
            self._device_id_label.setText(device.device_id)
            self._firmware_label.setText(f"Firmware: {device.firmware_version}")
            self._model_label.setText(f"Model: {device.model}")
            self._chip_label.setText(f"Chip: {device.chip or _NO_CHIP_TEXT}")
            self._status_label.setText("Status: Қосылды")
            self._device_info_section.setVisible(True)
            self._live_graph.set_devices_ready(True)

            self._clear_measurement_history()
            self._is_running = False
            self._stack.setCurrentWidget(self._device_page)
            self._update_button_states()
        except Exception:  # қорғаныс: болжанбаған қате де UI-ды құлатпайды
            self.clear_device()

    def clear_device(self) -> None:
        """Таңдалған құрылғы ақпаратын (single-device жол) тазалайды.
        Құрылғы ақпараты да, өлшем тарихы да толық тазаланады.

        Phase 32.1: бет ``_no_device_page``-ге ЕНДІ ҚАЙТАРЫЛМАЙДЫ (§11:
        "device disconnects while stopped — the workspace remains
        visible and returns to waiting/not-ready state") — тек device
        info section жасырылады (``_reset_device_info_labels()``),
        readouts/graph/table "—" placeholder күйіне қайтады.
        """
        self._device = None
        self._is_running = False
        self._reset_device_info_labels()
        self._live_graph.set_devices_ready(False)
        self._clear_measurement_history()
        self._update_button_states()

    def set_measurement(self, measurement: Measurement) -> None:
        """Келген ``Measurement`` бойынша configure_for_experiment()
        арқылы белгіленген әр арнаның көрсеткішін жаңартады
        (``measurement.get_value(key)``). Мән жоқ болса "—" болып
        қалады. Ешбір exception сыртқа шықпайды.
        """
        try:
            for key, label in self._value_labels.items():
                value = measurement.get_value(key)
                if value is None:
                    label.setText(_NO_VALUE_TEXT)
                    continue
                channel = self._channel_map.get(key)
                unit = channel.unit if channel else ""
                decimals = channel.decimals if channel else _DEFAULT_DECIMALS
                # Phase 12 (§6): сан МӘНІ ӘРҚАШАН осында бірден, анимациясыз
                # жаңартылады — ``flash_value_update()`` тек қосымша,
                # THROTTLED (жоғары sample rate-те суппрессияланатын) фон-
                # highlight эффектін қосады, мәтіннің ӨЗІНЕ ешбір delay
                # әкелмейді.
                label.setText(f"{value:.{decimals}f} {unit}".rstrip())
                flash_value_update(label)
            self._live_graph.append_measurement(measurement)
            self._measurement_table.append_measurement(measurement)
            if self._primary_stat_channel_key is not None:
                value = measurement.get_value(self._primary_stat_channel_key)
                if value is not None:
                    self._update_primary_stats(value)
        except Exception:  # қорғаныс: болжанбаған қате де UI-ды құлатпайды
            self._reset_readouts()

    def update_elapsed_time(self, elapsed_seconds: float) -> None:
        """"time" арнасы конфигурацияланған болса ғана (қазір тек "Ток
        жұмысы мен қуаты"), оның readout label-ін берілген elapsed
        уақытпен жаңартады. "time" арнасы жоқ тәжірибелерде — no-op
        (басқа readout-тарға, graph/table-ге мүлде тимейді).

        Бұл ExperimentWorkspacePage-тегі 10Hz UI refresh таймерінен
        шақырылады — authoritative elapsed уақыттың дереккөзі ЕМЕС, тек
        сол мәнді (pipeline.elapsed_seconds()) экранға шығаратын
        presentation-only жаңарту.
        """
        label = self._value_labels.get("time")
        if label is None:
            return
        channel = self._channel_map.get("time")
        unit = channel.unit if channel else ""
        decimals = channel.decimals if channel else _DEFAULT_DECIMALS
        label.setText(f"{elapsed_seconds:.{decimals}f} {unit}".rstrip())

    def set_experiment_running(self, running: bool) -> None:
        """Тәжірибенің running күйін орнатып, батырмалардың
        (Бастау/Тоқтату/Тазалау) қолжетімділігін сол күйге сай жаңартады.
        Manual point capture графиктерінде (Ohm's Law) "Нүктені сақтау"
        батырмасының қолжетімділігін де осы күймен синхрондайды.
        """
        self._is_running = running
        self._live_graph.set_capture_running(running)
        self._graph_card_live_badge.setVisible(running)
        self._update_button_states()

    def set_experiment_starting(self, starting: bool) -> None:
        """Multi-sensor coordinator SET_EXP ACK-ын күткен аралық
        ("Іске қосылуда...") кезеңінде Start/Тоқтату/Тазалау батырмаларының
        қолжетімділігін басқарады. Бұл optimistic ЕМЕС: ACK келгенше
        ``set_experiment_running(True)`` шақырылмайды (нақты hardware
        Start lifecycle bug түзетуі).
        """
        self._is_starting = starting
        self._update_button_states()

    def clear_measurements(self) -> None:
        """Оқылым, график және кесте деректерін тазалайды. Таңдалған
        құрылғының ақпараты (device info) сақталады.
        """
        self._clear_measurement_history()

    def show_status(self, text: str) -> None:
        """Workspace-тің статус жолағына қысқа хабарлама шығарады."""
        self._status_message_label.setText(text)

    # ---- UI құрастыру ---------------------------------------------------

    def _build_no_device_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("MeasurementWorkspaceNoDevicePage")
        layout = QVBoxLayout(page)

        label = QLabel(_NO_DEVICE_TEXT, page)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = label.font()
        font.setPointSize(font.pointSize() + 2)
        label.setFont(font)

        layout.addStretch(1)
        layout.addWidget(label)
        layout.addStretch(1)
        return page

    def set_connect_action_visible(self, visible: bool) -> None:
        """"🔌 Құрылғыны қосу" әрекетінің Оқушы режиміне тиесілі екенін
        белгілейді (Phase 37A: Мұғалім режимінде толық ``DevicesPage``
        қолданылады, бұл батырма ЕШҚАШАН көрінбейді). Нақты көріну
        readiness-ке де тәуелді (``_update_connect_action_visibility()``)
        — батырма ТЕК әлі дайын болмағанда керек, дайын болған соң
        (студент құрылғыны қосқаннан кейін) автоматты жасырылады.
        """
        self._connect_action_role_enabled = visible
        self._update_connect_action_visibility()

    def _update_connect_action_visibility(self) -> None:
        self._connect_device_button.setVisible(
            self._connect_action_role_enabled and not self._ready
        )

    def _build_device_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("MeasurementWorkspaceDevicePage")
        layout = QVBoxLayout(page)
        # Phase 4 (Workspace Layout Optimization): бұрынғы default
        # margin/spacing (~9px/6px) metrics/toolbar-дан кейінгі graph/
        # table scroll area-ға берілетін орынды ысырап ететін — "барлық
        # босатылған тік орын graph аймағына баруы керек" талабына сай
        # ықшамдалды.
        layout.setSpacing(4)
        layout.setContentsMargins(6, 4, 6, 4)

        layout.addWidget(self._build_device_info_section())
        self._readouts_layout = QHBoxLayout()
        layout.addLayout(self._readouts_layout)
        layout.addLayout(self._build_controls_section())

        # Phase 3 (Experiment Workspace graph geometry fix): graph/table
        # splitter ЕНДІ QScrollArea ІШІНДЕ. Себебі: ``LiveGraphWidget``
        # (stacked режимде, мыс. 2 subplot) ЕНДІ нақты минималды биіктік
        # талап етеді (§ ``_MIN_STACKED_PLOT_HEIGHT``), ал бұл бет
        # ``QStackedWidget#WorkspaceStack``-тың ІШІНДЕ көрсетіледі —
        # QStackedWidget әрбір парақты ӨЗ ағымдағы өлшеміне (терезе
        # өлшеміне) МӘЖБҮРЛЕП қиыстырады (setGeometry() арқылы, layout
        # negotiation-ды айналып өтіп), сондықтан жай ғана setMinimumHeight()
        # қоюдың ӨЗІ жеткіліксіз (тіпті ҚАУІПТІ: QStackedWidget өз
        # minimumSizeHint-ін БАРЛЫҚ тіркелген парақтардың ішінен ЕҢ
        # үлкенін алады, яғни бұл беттің минимумы БҮКІЛ терезенің
        # минимал өлшемін де үлкейтіп жіберер еді — HomePage/DevicesPage
        # сияқты басқа беттерге де ӘСЕР ЕТЕДІ). ``QScrollArea``-ның ӨЗІНІҢ
        # ``minimumSizeHint()`` кішкентай (scrollbar ені ғана) болатындықтан,
        # бұл тәуекел ЖОҚ — ал іште, splitter/plot-тар ӨЗ шынайы минимал
        # биіктігін алады, қолжетімді орын жетіспесе тік scrollbar
        # автоматты пайда болады (§ "prefer correct stretch behavior,
        # scrolling only if the page genuinely cannot fit").
        splitter = self._build_placeholders_section()
        scroll_area = QScrollArea(page)
        scroll_area.setObjectName("GraphTableScrollArea")
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        scroll_area.setWidget(splitter)
        self._graph_table_scroll_area = scroll_area
        layout.addWidget(scroll_area, 1)

        # Тестілеу үшін ашық: metrics/toolbar компакт (stretch=0), ал
        # graph/table scroll area primary stretch=1 алатынын pixel-perfect
        # емес, layout-контракт арқылы тексеруге мүмкіндік береді.
        self._device_page_layout = layout
        return page

    def _build_device_info_section(self) -> QWidget:
        """Жалғыз ``ConnectedDevice``-тің ақпаратын (title/id/firmware/
        model/chip/status) көрсететін секция — тек ЕСКІ single-device
        ``ExperimentController`` жолында (``set_device()``) мағыналы.

        Phase 32 layout архитектурасы түзетуі: бұл контейнер ӘДЕПКІ
        ЖАСЫРЫН (``setVisible(False)``). Барлық production электр
        тәжірибесі ``MultiSensorExperimentCoordinator`` (2+ сенсор)
        қолданатындықтан, ``set_device()`` ЕШҚАШАН шақырылмайды —
        бұрын бұл секция сол кезде де 6 БОС ``QLabel`` ретінде ~125px
        вертикаль орынды metric cards-тың ҮСТІНДЕ бекітіп қоятын (нақты
        hardware/pytest-те өлшенген root cause). Енді контейнер жасырын
        болғанда QVBoxLayout оған ЕШБІР орын бөлмейді (Qt: hidden widget
        item-дер layout есебінде size=0 болып қаралады) — сондықтан
        metric cards ДӘЛ секцияның үстінен, тікелей readouts_layout-тың
        орнында басталады. ``set_device()`` секцияны көрсетеді,
        ``clear_device()``/``_reset_device_info_labels()`` жасырады —
        бұл эксперимент ID-ге ЕШБІР тәуелділік ЖОҚ, тек "нақты бір
        құрылғы таңдалды ма" деген жалпы шартқа негізделген.
        """
        section = QWidget(self)
        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(0, 0, 0, 0)

        self._title_label = QLabel(self)
        title_font = self._title_label.font()
        title_font.setBold(True)
        title_font.setPointSize(title_font.pointSize() + 3)
        self._title_label.setFont(title_font)

        self._device_id_label = QLabel(self)
        self._firmware_label = QLabel(self)
        self._model_label = QLabel(self)
        self._chip_label = QLabel(self)
        self._status_label = QLabel(self)

        for label in (
            self._title_label,
            self._device_id_label,
            self._firmware_label,
            self._model_label,
            self._chip_label,
            self._status_label,
        ):
            section_layout.addWidget(label)

        self._device_info_section = section
        self._device_info_section.setVisible(False)
        return section

    def _rebuild_readouts(
        self,
        channels: tuple[SensorChannel, ...],
        optional_channels: tuple[SensorChannel, ...] = (),
    ) -> None:
        while self._readouts_layout.count():
            item = self._readouts_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        self._value_labels = {}
        self._optional_readout_widgets = {}
        for channel in channels:
            readout_widget, value_label = self._make_readout(channel.display_name)
            self._value_labels[channel.key] = value_label
            self._readouts_layout.addWidget(readout_widget, 1)

        for channel in optional_channels:
            readout_widget, value_label = self._make_readout(channel.display_name)
            # Бір ортақ _value_labels dict-те — set_measurement() hidden
            # readout-ты да шартсыз жаңартады (backend есептеу presentation
            # toggle-ға тәуелсіз жүре береді).
            self._value_labels[channel.key] = value_label
            readout_widget.setVisible(False)
            self._optional_readout_widgets[channel.key] = readout_widget
            self._readouts_layout.addWidget(readout_widget, 1)

        # "time" арнасы болса, MeasurementCard-тың әдепкі "—"-ін бірден
        # "0.00 s" ready-күйіне ауыстырамыз (§7) — басқа арналар өзгеріссіз.
        self._reset_readouts()

    def _make_readout(self, title: str) -> tuple[QWidget, QLabel]:
        """Vernier/LabQuest тәрізді үлкен readout карточкасы. ``MeasurementCard``
        ``value_label`` public атрибутын ашады — қайтарылатын tuple пішіні
        ескі (container, value QLabel) контрактісімен бірдей, сондықтан
        ``_value_labels``/тәуелді тесттер өзгеріссіз жұмыс істейді.
        """
        card = MeasurementCard(title, self)
        return card, card.value_label

    def refresh_theme_icons(self) -> None:
        """Тема ауысқанда Бастау/Тоқтату/Тазалау/Экспорт/Құрылғыны қосу
        батырмаларының иконка fill-ін жаңартады.
        """
        theme = current_theme()
        _load_toolbar_icon.cache_clear()
        for button, filename in self._action_buttons_with_icons:
            icon = _load_toolbar_icon(filename, theme)
            button.setIcon(icon)
            button.setIconSize(QSize(_ACTION_ICON_PX, _ACTION_ICON_PX))

    def _build_controls_section(self) -> QHBoxLayout:
        row = QHBoxLayout()

        self._start_button = QPushButton("Бастау", self)
        self._start_button.setObjectName("PrimaryButton")
        self._stop_button = QPushButton("Тоқтату", self)
        self._clear_button = QPushButton("Тазалау", self)
        self._optional_toggle_button = QPushButton("", self)
        self._optional_toggle_button.setVisible(False)
        self._export_button = QPushButton("Экспорт", self)
        # Phase 37A: Оқушы режимінде, тек әлі дайын болмаған кезде ғана
        # көрінетін жеңілдетілген "Құрылғыны қосу" әрекеті
        # (``set_connect_action_visible()``/``_update_connect_action_
        # visibility()`` арқылы басқарылады — рөл ЖӘНЕ readiness екеуіне
        # тәуелді). Әдепкі бойынша ЖАСЫРЫН, сондықтан бұрыннан бар барлық
        # тест ӨЗГЕРІССІЗ өтеді.
        self._connect_device_button = QPushButton("Құрылғыны қосу", self)
        self._connect_device_button.setVisible(False)

        self._action_buttons_with_icons = (
            (self._start_button, "ic_fluent_play_24_regular.svg"),
            (self._stop_button, "ic_fluent_stop_24_regular.svg"),
            (self._clear_button, "ic_fluent_delete_24_regular.svg"),
            (self._export_button, "ic_fluent_arrow_export_24_regular.svg"),
            (self._connect_device_button, "ic_fluent_plug_connected_24_regular.svg"),
        )
        self.refresh_theme_icons()

        self._start_button.clicked.connect(self.start_requested)
        self._stop_button.clicked.connect(self.stop_requested)
        self._clear_button.clicked.connect(self.clear_requested)
        self._optional_toggle_button.clicked.connect(self._on_optional_toggle_clicked)
        self._connect_device_button.clicked.connect(self.connect_device_requested)

        self._export_menu = QMenu(self._export_button)
        self._csv_export_action = self._export_menu.addAction("CSV экспорт")
        self._excel_export_action = self._export_menu.addAction("Excel экспорт")
        self._pdf_export_action = self._export_menu.addAction("PDF экспорт")
        self._csv_export_action.triggered.connect(lambda: self.export_requested.emit("csv"))
        self._excel_export_action.triggered.connect(
            lambda: self.export_requested.emit("excel")
        )
        self._pdf_export_action.triggered.connect(lambda: self.export_requested.emit("pdf"))
        self._export_button.setMenu(self._export_menu)

        row.addWidget(self._start_button)
        row.addWidget(self._stop_button)
        row.addWidget(self._clear_button)
        row.addWidget(self._optional_toggle_button)
        row.addWidget(self._export_button)
        row.addWidget(self._connect_device_button)
        return row

    def _build_placeholders_section(self) -> QSplitter:
        self._live_graph = LiveGraphWidget(self, default_auto_scale=self._default_auto_scale)
        self._live_graph.capture_status.connect(self.show_status)
        self._live_graph.maximize_toggled.connect(self._on_graph_maximize_toggled)
        self._measurement_table = MeasurementTableWidget(self)

        graph_card = self._build_graph_card(self._live_graph)

        # QSplitter — график Vernier тәрізді scientific graph ретінде
        # оқылымды визуалды басым болуы тиіс (~65:35), бірақ пайдаланушы
        # графикті/кестені өзінше өзгерте алады.
        self._graph_table_splitter = QSplitter(Qt.Orientation.Horizontal, self)
        # Phase 32: график/кесте workspace-тің БІРІНШІ КЕЗЕКТІ (primary)
        # икемді аймағы — екі бағытта да Expanding, терезе өскен сайын
        # артық биіктік/ен ДӘЛ осы жерге ағуы тиіс.
        self._graph_table_splitter.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._graph_table_splitter.addWidget(graph_card)
        self._graph_table_splitter.addWidget(self._measurement_table)
        self._graph_table_splitter.setStretchFactor(0, 13)
        self._graph_table_splitter.setStretchFactor(1, 7)
        self._graph_table_splitter.setSizes([650, 350])
        return self._graph_table_splitter

    def _build_graph_card(self, graph: LiveGraphWidget) -> QFrame:
        """``LiveGraphWidget``-ті (toolbar + plot, ӨЗГЕРТУСІЗ) визуалды
        карточкаға орайды: тақырып + "● LIVE" индикаторы (running-мен
        синхрондалған) + MIN/AVG/MAX статистика жолағы (тек ``graph_
        y_channels``-тегі негізгі арна үшін, graph-ты қоректендіретін
        ДӘЛ СОЛ Measurement ағынынан). Графиктің ішкі сызу логикасына
        мүлде тимейді.
        """
        card = QFrame(self)
        card.setObjectName("GraphCard")
        # Phase 32: GraphCard wrapper-і LiveGraph-тың кеңеюіне кедергі
        # жасамауы тиіс — MIN/AVG/MAX header компакт, ал график өзі
        # барлық қалған кеңістікті алады (layout.addWidget(graph, 1)).
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._graph_card_title_label = QLabel(_DEFAULT_GRAPH_CARD_TITLE, card)
        self._graph_card_title_label.setObjectName("GraphCardTitle")

        # kезeng 29: MIN/AVG/MAX бір жолда, тақырыппен қатар — тар
        # биіктікті терезелерде (мыс. 1366×768-де "Тізбек бөлігі үшін
        # кернеудің ток күшіне тәуелділігін зерттеу" fit панелі) артық
        # вертикал орын алмас үшін.
        self._graph_stats_label = QLabel("", card)
        self._graph_stats_label.setObjectName("GraphStatsLabel")
        self._graph_stats_label.setVisible(False)

        self._graph_card_live_badge = QLabel(_LIVE_BADGE_TEXT, card)
        self._graph_card_live_badge.setObjectName("GraphCardLiveBadge")
        self._graph_card_live_badge.setVisible(False)

        header_row = QHBoxLayout()
        header_row.addWidget(self._graph_card_title_label)
        header_row.addStretch(1)
        header_row.addWidget(self._graph_stats_label)
        header_row.addSpacing(12)
        header_row.addWidget(self._graph_card_live_badge)

        layout = QVBoxLayout(card)
        # Phase 5 (Graph Area Optimization): бұрынғы әдепкі 9px margin/
        # 6px spacing тек GraphCard-тың ӨЗ ІШКІ padding-і — тек графикке
        # қосымша тік орын босату үшін ықшамдалды, карточкадан тыс
        # ешбір секцияға (measurement cards/toolbar/table) тимейді.
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        layout.addLayout(header_row)
        layout.addWidget(graph, 1)
        return card

    def _reset_primary_stats(self) -> None:
        self._primary_stat_min = None
        self._primary_stat_max = None
        self._primary_stat_sum = 0.0
        self._primary_stat_count = 0
        self._graph_stats_label.setText("")

    def _update_primary_stats(self, value: float) -> None:
        self._primary_stat_min = value if self._primary_stat_min is None else min(
            self._primary_stat_min, value
        )
        self._primary_stat_max = value if self._primary_stat_max is None else max(
            self._primary_stat_max, value
        )
        self._primary_stat_sum += value
        self._primary_stat_count += 1
        avg = self._primary_stat_sum / self._primary_stat_count
        decimals = self._primary_stat_decimals
        unit = self._primary_stat_unit
        label = f"{self._primary_stat_label}: " if self._primary_stat_label else ""
        self._graph_stats_label.setText(
            f"{label}MIN {self._primary_stat_min:.{decimals}f} {unit}   "
            f"AVG {avg:.{decimals}f} {unit}   "
            f"MAX {self._primary_stat_max:.{decimals}f} {unit}".rstrip()
        )

    def _on_optional_toggle_clicked(self) -> None:
        """Қосымша (әдепкі жасырын) арналардың readout/table бағанын
        көрсету/жасыру. Тек presentation — running/session/Measurement/
        graph-ға ешбір қатысы жоқ, тоқтатпайды/тазаламайды.
        """
        self._optional_visible = not self._optional_visible
        self._optional_toggle_button.setText(
            self._optional_hide_label if self._optional_visible else self._optional_show_label
        )
        for channel in self._optional_channels:
            widget = self._optional_readout_widgets.get(channel.key)
            if widget is not None:
                widget.setVisible(self._optional_visible)
            self._measurement_table.set_column_visible(channel.key, self._optional_visible)

    def _on_graph_maximize_toggled(self, maximized: bool) -> None:
        """``LiveGraphWidget.maximize_toggled``-ге жазылады (Phase 33A
        §12): графикке "барлыққа жуық" орын босату үшін metric cards
        пен measurement table-ды уақытша жасырады — ``QSplitter``
        жасырын виджетке орын бермейді (Phase 32-де расталған Qt
        мінез-құлқы), сондықтан graph_card автоматты splitter-дің
        толық енін алады.

        Start/Тоқтату/Тазалау/Export батырмалары (``_build_controls_
        section()``) ӘРҚАШАН көрінеді — классрумда демонстрация
        кезінде тәжірибені тоқтату мүмкіндігі ЕШҚАШАН жоғалмауы тиіс.
        Дерек/zoom/crosshair/experiment/session күйіне мүлде тимейді —
        тек presentation, ешбір Measurement/session/firmware қатысы жоқ.
        """
        optional_widgets = set(self._optional_readout_widgets.values())
        for index in range(self._readouts_layout.count()):
            widget = self._readouts_layout.itemAt(index).widget()
            if widget is None:
                continue
            if maximized:
                widget.setVisible(False)
            elif widget in optional_widgets:
                # Қосымша (Қуат т.б.) карточка тек toggle батырмасы
                # арқылы көрінеді — restore ЕШҚАШАН оны мәжбүрлеп
                # қайта көрсетпейді, ескі _optional_visible күйі сақталады.
                widget.setVisible(self._optional_visible)
            else:
                widget.setVisible(True)
        self._measurement_table.setVisible(not maximized)

    def _reset_readouts(self) -> None:
        for key, label in self._value_labels.items():
            if key == "time":
                # Уақыт — PC-generated, әрдайым белгілі шама (§7): басқа
                # арналардай "—" емес, "0.00 s" бастапқы/ready күйі.
                self.update_elapsed_time(0.0)
                continue
            label.setText(_NO_VALUE_TEXT)

    def _reset_device_info_labels(self) -> None:
        for label in (
            self._title_label,
            self._device_id_label,
            self._firmware_label,
            self._model_label,
            self._chip_label,
            self._status_label,
        ):
            label.setText("")
        self._device_info_section.setVisible(False)

    def _clear_measurement_history(self) -> None:
        self._reset_readouts()
        self._live_graph.clear()
        self._measurement_table.clear()
        self._reset_primary_stats()

    def _update_button_states(self) -> None:
        has_device = self._device is not None or self._ready
        busy = self._is_running or self._is_starting
        self._start_button.setEnabled(has_device and not busy)
        self._stop_button.setEnabled(has_device and busy)
        self._clear_button.setEnabled(has_device and not busy)
        self._export_button.setEnabled(has_device)
