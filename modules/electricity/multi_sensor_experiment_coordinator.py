"""MultiSensorExperimentCoordinator — бір тәжірибе үшін бірнеше физикалық
құрылғыны (әрқайсысы жеке Arduino/COM-порт) бір мезгілде басқаратын
координатор.

Мәселе: Ohm's Law секілді тәжірибелерде Voltage Sensor мен Current
Sensor екі БӨЛЕК Arduino/COM-порт ретінде қосылады, әрқайсысы тек өз
арнасын (``U=`` немесе ``I=``) жібереді. ``ExperimentController``
құрылымы бойынша дәл БІР ``SerialThreadController``-мен жұмыс істейді,
сондықтан бұл сценарийге жарамайды (ол өзгеріссіз қалады — бір
физикалық сенсорлы сынақтарда/single-sensor тәжірибелерде қолданыла
береді).

**Persistent connection architecture:** бұл координатор ешбір
``SerialThreadController``/``DeviceIdentifier``-ді ӨЗІ ЖАСАМАЙДЫ/
ИЕЛЕНБЕЙДІ — портты нақты ашу/жабу толығымен ``DeviceManager``-дің
жауапкершілігі (application lifetime бойы өмір сүреді, эксперимент
ауысқанда ЕШҚАШАН жабылмайды). Координатор тек:
  - ``device_manager``-ден HELLO handshake сұрайды (``identify_device``),
  - ``device_manager``-дің сигналдарына жазылады (port_name/sensor_type
    бойынша сүзіп, тек ӨЗІНЕ қатысты оқиғаларды өңдейді),
  - әр порттың raw жолын өз ``PacketParser``-імен парсингтейді, партиалды
    мәндерді ``ChannelAggregator``-ге береді,
  - aggregator толық және fresh жиынтық қайтарғанда ғана — БІР ортақ
    ``DataValidator`` → ``CalculationEngine`` → ``Measurement`` →
    ``ExperimentSession`` тізбегін шақырады.

``shutdown()`` ЕНДІ тек ``device_manager``-ден жазылымнан бас тартады
(unsubscribe) — нақты serial порт ЕШҚАШАН жабылмайды. Партиалды мән
ешқашан ``DataValidator``-ге тікелей бармайды.
"""

import logging
import time
from datetime import datetime, timezone
from uuid import uuid4

from PySide6.QtCore import QObject, QTimer, Signal

from domain.entities.connected_device import ConnectedDevice
from domain.entities.experiment_definition import ExperimentDefinition
from domain.entities.experiment_session import ExperimentSession
from domain.entities.measurement import Measurement
from domain.services.calculation_engine import CalculationEngine
from domain.services.channel_aggregator import ChannelAggregator
from domain.services.data_validator import DataValidator
from infrastructure.serial_comm.device_manager import DeviceManager
from infrastructure.serial_comm.packet_parser import PacketParser

_DEFAULT_STALENESS_SECONDS = 0.5
_DEFAULT_START_ACK_TIMEOUT_MS = 3000

# Уақытша диагностикалық logging (experiment-switch/SET_EXP synchronization
# аудитінің бөлігі, DeviceIdentifier-дегі APL_DEBUG_SERIAL паттернімен
# бірдей). Әдепкі бойынша үнсіз — көру үшін APL_DEBUG_SERIAL=1.
_logger = logging.getLogger(__name__)


class MultiSensorExperimentCoordinator(QObject):
    """``ExperimentDefinition.required_sensor_types``-та көрсетілген
    бірнеше физикалық сенсорды (әрқайсысы жеке порт) бір мезгілде
    басқарып, олардың партиалды деректерін бір толық ``Measurement``-ке
    біріктіретін координатор.
    """

    measurement_ready = Signal(object)
    parse_error = Signal(str)
    validation_error = Signal(str)
    warning_occurred = Signal(str)

    device_identified = Signal(object)  # ConnectedDevice
    device_identification_failed = Signal(str)
    handshake_timeout = Signal(str)
    port_disconnected = Signal(str)  # port_name
    port_error = Signal(str, str)  # (port_name, message)
    readiness_changed = Signal(object)  # dict[str, bool] — sensor_type -> ready
    # ACK-gated start (real-hardware bug fix, kezең 15): start_experiment()
    # бірден running=True орнатпайды — SET_EXP жіберіп, БАРЛЫҚ портан
    # сәйкес "OK,EXP=<id>" ACK келгенше "starting" аралық күйінде тұрады.
    experiment_started = Signal()
    start_failed = Signal(str)

    def __init__(
        self,
        definition: ExperimentDefinition,
        device_manager: DeviceManager,
        data_validator: DataValidator | None = None,
        calculation_engine: CalculationEngine | None = None,
        session: ExperimentSession | None = None,
        staleness_seconds: float = _DEFAULT_STALENESS_SECONDS,
        start_ack_timeout_ms: int = _DEFAULT_START_ACK_TIMEOUT_MS,
    ) -> None:
        super().__init__()
        self._definition = definition
        self._device_manager = device_manager
        self._sensor_types: tuple[str, ...] = definition.required_sensor_types
        self._data_validator = data_validator or DataValidator()
        self._calculation_engine = calculation_engine or CalculationEngine()
        self._session = session or ExperimentSession(
            id=str(uuid4()),
            experiment_id=definition.id,
            started_at=datetime.now(timezone.utc),
        )

        expected_channels = frozenset(
            channel.key for channel in definition.required_channels if channel.required
        )
        self._aggregator = ChannelAggregator(
            expected_channels=expected_channels, staleness_seconds=staleness_seconds
        )

        # port_name -> sensor_type: тек ОСЫ координаторға (осы тәжірибеге)
        # қатысты порттар. device_manager сигналдары ГЛОБАЛ (барлық портқа
        # ортақ) болғандықтан, әр handler алдымен осы map арқылы сүзеді.
        self._port_to_sensor_type: dict[str, str] = {}
        self._assigned_devices: dict[str, ConnectedDevice] = {}
        # PacketParser жеңіл, тек парсинг күйін сақтайды (транспорт емес) —
        # сондықтан координатор оны өзінде сақтай береді.
        self._packet_parsers: dict[str, PacketParser] = {}

        self._running = False
        self._starting = False
        self._ports_awaiting_ack: set[str] = set()

        # Elapsed-time (Ток жұмысы мен қуаты, "УАҚЫТ"/work=P×t үшін):
        # PC-owned, ACK-gated running=True сәтінен бастап time.monotonic()
        # негізінде (wall-clock/datetime ЕМЕС — жүйелік уақыт өзгерісіне/
        # NTP түзетуіне осал болмас үшін). _check_start_complete()-те
        # орнатылады (running=True орнатылатын ЖАЛҒЫЗ жер), stop_experiment()-
        # де "мұздатылады" (Stop-тан кейін өспейді).
        self._running_started_monotonic: float | None = None
        self._frozen_elapsed_seconds: float | None = None

        self._start_timeout_timer = QTimer(self)
        self._start_timeout_timer.setSingleShot(True)
        self._start_timeout_timer.setInterval(start_ack_timeout_ms)
        self._start_timeout_timer.timeout.connect(self._on_start_timeout)

        self._device_manager.device_identified.connect(
            self._on_device_manager_device_identified
        )
        self._device_manager.line_received.connect(self._on_device_manager_line)
        self._device_manager.port_disconnected.connect(
            self._on_device_manager_port_disconnected
        )
        self._device_manager.port_error.connect(self._on_device_manager_port_error)
        self._device_manager.device_identification_failed.connect(
            self.device_identification_failed
        )
        self._device_manager.handshake_timeout.connect(self.handshake_timeout)

    @property
    def session(self) -> ExperimentSession:
        """Контроллер ішінде сақталатын ағымдағы ExperimentSession."""
        return self._session

    def is_running(self) -> bool:
        """Тәжірибе қазір өлшеу қабылдап тұрғанын қайтарады (ACK-пен
        расталған, "starting" аралық күйі бұған кірмейді).
        """
        return self._running

    def is_starting(self) -> bool:
        """Start сұралған, бірақ әлі барлық портан SET_EXP ACK келмеген
        аралық күйде екенін қайтарады (optimistic емес UI үшін).
        """
        return self._starting

    def elapsed_seconds(self) -> float:
        """Тәжірибенің ағымдағы elapsed уақыты (секунд). Authoritative,
        PC-owned мән — ACK-пен расталған ``running=True`` сәтінен бастап
        ``time.monotonic()`` негізінде есептеледі (wall-clock/``datetime``
        ЕМЕС). Әлі басталмаса ("waiting"/"starting" кезеңі) — 0.0.
        Тоқтатылған соң (``stop_experiment()``) Stop сәтінде "мұздатылған"
        соңғы мән қайтарылады — қайта сәтті Start болмайынша өспейді.
        Бір ғана дереккөз: ``_finalize_measurement()``-тегі ``work``
        есептеуі мен UI-дің readout жаңартуы (``ExperimentWorkspacePage``-
        тегі 10Hz таймер) дәл осы әдісті шақырады.
        """
        if self._frozen_elapsed_seconds is not None:
            return self._frozen_elapsed_seconds
        if self._running_started_monotonic is None:
            return 0.0
        return max(0.0, time.monotonic() - self._running_started_monotonic)

    def is_ready(self) -> bool:
        """Барлық қажетті сенсор түрі (``required_sensor_types``) identified
        болғанын қайтарады.
        """
        return all(sensor_type in self._assigned_devices for sensor_type in self._sensor_types)

    def missing_sensor_types(self) -> tuple[str, ...]:
        """Әлі identified болмаған қажетті сенсор түрлерін қайтарады."""
        return tuple(
            sensor_type
            for sensor_type in self._sensor_types
            if sensor_type not in self._assigned_devices
        )

    def identify_device(self, port_name: str, baud_rate: int = 115200) -> None:
        """Көрсетілген портты ``DeviceManager`` арқылы анықтауды сұрайды
        (порт ҚАЗІРДІҢ ӨЗІНДЕ alive болса, DeviceManager жаңа HELLO
        жібермей, тіркелген құрылғыны қайта хабарлайды — reuse).
        """
        self._device_manager.identify(port_name, baud_rate)

    def refresh_from_device_manager(self) -> None:
        """``DeviceManager``-де ҚАЗІРДІҢ ӨЗІНДЕ connected тұрған, осы
        тәжірибеге қажетті сенсорларды ЖАҢА identify-сіз бірден
        "assigned" етеді — automatic reuse (мыс. Ohm's Law-дан "Ток пен
        кернеу"-ге ауысқанда қайта Анықтау керек емес). Барлық сигнал
        байланысы орнатылғаннан КЕЙІН шақырылуы тиіс (``ExperimentWorkspacePage.
        on_enter()``-де), әйтпесе ``device_identified`` эмиссиясы
        жоғалуы мүмкін.
        """
        for sensor_type in self._sensor_types:
            device = self._device_manager.get_connected_device(sensor_type)
            if device is not None:
                self._register_assigned_device(device)
                _logger.debug(
                    "refresh_from_device_manager(): '%s' (%s) '%s' тәжірибесіне "
                    "hydrated (қайта identify жоқ)",
                    device.port_name,
                    sensor_type,
                    self._definition.id,
                )
                # UI (DevicePanel) осы сигналмен карточканы қалпына
                # келтіреді — hydration кезінде де ЖІБЕРІЛУІ міндетті,
                # әйтпесе экспериментті ауыстырғанда панель бос көрінеді.
                self.device_identified.emit(device)

    def start_experiment(self) -> None:
        """Тәжірибені бастауды сұрайды: барлық identified портқа
        ``SET_EXP=<id>`` жібереді (әр Arduino өз пакеттерінде дұрыс EXP-ті
        қолдануы үшін). ``is_ready()`` false болса ештеңе істемейді —
        нақты gating UI деңгейінде (Start батырмасы) жасалады, бұл — қосымша
        қорғаныс қабаты.

        **ACK-gated**: бұл әдіс ЕШҚАШАН бірден ``running=True`` орнатпайды.
        Оның орнына "starting" аралық күйіне өтеді — ``experiment_started``
        сигналы тек БАРЛЫҚ порттан сәйкес ``OK,EXP=<id>`` ACK келгенде
        ғана шығарылады (``_check_start_complete()``). Белгіленген уақыт
        ішінде (``_start_timeout_timer``) толық ACK жиналмаса,
        ``start_failed`` шығарылады.
        """
        if not self.is_ready():
            self.warning_occurred.emit(
                "Барлық қажетті сенсор әлі анықталған жоқ, тәжірибе басталмады"
            )
            return
        if self._running or self._starting:
            return

        self._starting = True
        self._ports_awaiting_ack = set(self._port_to_sensor_type.keys())
        self._start_timeout_timer.start()
        _logger.debug(
            "start_experiment('%s'): ACK күтілетін порттар: %s",
            self._definition.id,
            sorted(self._ports_awaiting_ack),
        )

        for port_name in list(self._port_to_sensor_type.keys()):
            try:
                _logger.debug(
                    "start_experiment('%s'): TX -> '%s' SET_EXP=%s",
                    self._definition.id,
                    port_name,
                    self._definition.id,
                )
                self._device_manager.write_to_port(
                    port_name, f"SET_EXP={self._definition.id}"
                )
            except Exception as exc:  # қорғаныс: болжанбаған қате де сыртқа шықпайды
                _logger.debug(
                    "start_experiment('%s'): '%s' write_to_port қатесі: %s",
                    self._definition.id,
                    port_name,
                    exc,
                )
                self.port_error.emit(port_name, f"SET_EXP жіберу қатесі: {exc}")
                self._ports_awaiting_ack.discard(port_name)

        self._check_start_complete()

    def stop_experiment(self) -> None:
        """Тәжірибені тоқтатады (не "starting" аралық күйінде тұрса,
        соны да тоқтатады), сессияны аяқтайды және aggregator-дың
        кэштелген мәндерін тазалайды (келесі Start ескі деректі қолданбасын).
        Serial порттарға ЕШБІР қатысы жоқ — олар ашық қалады.
        """
        try:
            if self._running_started_monotonic is not None and self._frozen_elapsed_seconds is None:
                # Stop сәтіндегі elapsed мәнін "мұздатамыз" — running=False
                # орнатылғаннан кейін де UI/дерек дәл осы мәнді көрсетуі
                # (қайта өспеуі) керек.
                self._frozen_elapsed_seconds = self.elapsed_seconds()
            self._running = False
            self._starting = False
            self._ports_awaiting_ack = set()
            self._start_timeout_timer.stop()
            self._session.stop()
            self._aggregator.reset()
        except Exception as exc:
            self.warning_occurred.emit(f"stop_experiment() қатесі: {exc}")

    def clear_session(self) -> None:
        """Жиналған барлық өлшемдерді сессиядан тазалайды. Тәжірибе
        тоқтатылған (running/starting емес) күйде болса, elapsed-time
        күйі де бастапқы "0.00 s" қалпына қайтарылады (spec §7) — белсенді
        жүріп жатқан run-ды ЕШҚАШАН тимейді (Clear UI деңгейінде тек
        тоқтатылған кезде ғана рұқсат етіледі, бұл — қосымша қорғаныс).
        """
        try:
            self._session.clear()
            self._aggregator.reset()
            if not self._running and not self._starting:
                self._running_started_monotonic = None
                self._frozen_elapsed_seconds = None
        except Exception as exc:
            self.warning_occurred.emit(f"clear_session() қатесі: {exc}")

    def shutdown(self) -> None:
        """Координаторды тоқтатады — ТЕК ``DeviceManager`` сигналдарынан
        жазылымнан бас тартады (unsubscribe) және өз ішкі бухгалтериясын
        тазалайды. **Нақты serial портты ЕШҚАШАН жаппайды** — connection
        lifecycle толығымен ``DeviceManager``-де, application lifetime
        бойы сақталады.
        """
        self._start_timeout_timer.stop()
        self._starting = False
        self._ports_awaiting_ack = set()

        for signal, slot in (
            (self._device_manager.device_identified, self._on_device_manager_device_identified),
            (self._device_manager.line_received, self._on_device_manager_line),
            (self._device_manager.port_disconnected, self._on_device_manager_port_disconnected),
            (self._device_manager.port_error, self._on_device_manager_port_error),
            (self._device_manager.device_identification_failed, self.device_identification_failed),
            (self._device_manager.handshake_timeout, self.handshake_timeout),
        ):
            try:
                signal.disconnect(slot)
            except (TypeError, RuntimeError):
                # Қате бұрын ажыратылған/ешқашан байланыспаған слот үшін
                # шығады — қорғаныс, shutdown() бірнеше рет шақырылса да
                # қауіпсіз болу үшін.
                pass

        self._port_to_sensor_type.clear()
        self._assigned_devices.clear()
        self._packet_parsers.clear()

    def _register_assigned_device(self, device: ConnectedDevice) -> None:
        sensor_type = device.sensor_type.upper()
        self._assigned_devices[sensor_type] = device
        self._port_to_sensor_type[device.port_name] = sensor_type
        self._packet_parsers.setdefault(device.port_name, PacketParser())
        self._emit_readiness()

    def _check_start_complete(self) -> None:
        if not self._starting or self._ports_awaiting_ack:
            return
        self._starting = False
        self._start_timeout_timer.stop()
        self._running = True
        # Authoritative elapsed-time anchor — дәл ОСЫ жерде (running=True
        # орнатылатын ЖАЛҒЫЗ орын), Start батырмасы басылған сәтте ЕМЕС.
        self._running_started_monotonic = time.monotonic()
        self._frozen_elapsed_seconds = None
        _logger.debug(
            "_check_start_complete('%s'): барлық ACK келді — RUNNING", self._definition.id
        )
        self.experiment_started.emit()

    def _on_start_timeout(self) -> None:
        if not self._starting:
            return
        missing_ports = tuple(sorted(self._ports_awaiting_ack))
        self._starting = False
        self._ports_awaiting_ack = set()
        self.start_failed.emit(
            "Келесі порт(тар)дан SET_EXP растауы (ACK) келмеді: "
            f"{', '.join(missing_ports)}"
        )

    def _on_device_manager_device_identified(self, device: ConnectedDevice) -> None:
        # DeviceManager сигналы ГЛОБАЛ — барлық осы сәтте тірі
        # координатор данасы бұл оқиғаны алады, сондықтан әр дана өзіне
        # қатысты сенсор түрін ғана тіркейді.
        sensor_type = device.sensor_type.upper()
        if sensor_type not in self._sensor_types:
            self.warning_occurred.emit(
                f"'{device.device_id}' ({sensor_type}) бұл тәжірибеге қажет "
                "сенсор түрлерінің арасында жоқ"
            )
            return

        self._register_assigned_device(device)
        self.device_identified.emit(device)

    def _on_device_manager_port_disconnected(self, port_name: str) -> None:
        sensor_type = self._port_to_sensor_type.pop(port_name, None)
        if sensor_type is None:
            return  # басқа эксперименттің/сенсордың порты

        self._assigned_devices.pop(sensor_type, None)
        self._packet_parsers.pop(port_name, None)

        if self._running or self._starting:
            self.stop_experiment()

        self.port_disconnected.emit(port_name)
        self._emit_readiness()

    def _on_device_manager_port_error(self, port_name: str, message: str) -> None:
        if port_name in self._port_to_sensor_type:
            self.port_error.emit(port_name, message)

    def _emit_readiness(self) -> None:
        self.readiness_changed.emit(
            {
                sensor_type: sensor_type in self._assigned_devices
                for sensor_type in self._sensor_types
            }
        )

    def _on_device_manager_line(self, port_name: str, line: str) -> None:
        if port_name not in self._port_to_sensor_type:
            return  # мына порт бұл эксперименттің қажетті сенсорына жатпайды
        parser = self._packet_parsers.get(port_name)
        if parser is None:
            return
        try:
            self._process_port_line(port_name, parser, line)
        except Exception as exc:  # қорғаныс: болжанбаған қате де сыртқа шықпайды
            self.parse_error.emit(f"[{port_name}] Күтпеген өңдеу қатесі: {exc}")

    def _process_port_line(self, port_name: str, parser: PacketParser, line: str) -> None:
        stripped = line.strip()
        if not stripped:
            return

        if stripped.upper().startswith("TYPE="):
            # HELLO handshake пакеті — DeviceManager/DeviceIdentifier бөлек өңдейді.
            return

        if stripped.upper().startswith("OK,EXP="):
            self._handle_set_exp_ack(port_name, stripped)
            return

        parse_result = parser.parse_line(line)
        if not parse_result.is_valid:
            for error in parse_result.errors:
                self.parse_error.emit(f"[{port_name}] {error}")
            return

        if parse_result.experiment_id != self._definition.id:
            # Phase 34.1 §2: бұл — протокол/пакет-роутинг диагностикасы
            # (мыс. эксперимент ауыстыру кезінде ескі Arduino ағынының
            # соңғы пакеттері келуі МҮМКІН, бұл ҚАЛЫПТЫ жағдай), студент
            # интерфейсіне ЕШҚАШАН шықпауы тиіс. Пакет өзі әлі де толық
            # ЕЛЕНБЕЙДІ/тасталады (валидация/әрекет ӨЗГЕРІССІЗ) — тек
            # көрінетін UI ескертуі алынып тасталды, диагностика
            # debug-логта (APL_DEBUG_SERIAL=1) сақталады.
            _logger.debug(
                "_process_port_line: '%s' RX EXP='%s' (күтілген '%s') — running=%s "
                "starting=%s ports_awaiting_ack=%s — пакет үнсіз тасталды",
                port_name,
                parse_result.experiment_id,
                self._definition.id,
                self._running,
                self._starting,
                sorted(self._ports_awaiting_ack),
            )
            return

        if not self._running:
            # Тоқтатылған кезде де Arduino ағыны үздіксіз жалғаса береді
            # (протокол Start/Stop командасын білмейді) — бұл ҚАЛЫПТЫ,
            # күтілетін жағдай, сондықтан визуалды UI хабарламасы ретінде
            # ЕМЕС, тек debug-логқа (APL_DEBUG_SERIAL=1) жазылады. Пакет
            # өзі әлі де толық өткізіп жіберіледі (measurement/graph/table
            # жаңармайды) — тек көрінетін ескерту алынып тасталды.
            _logger.debug(
                "_process_port_line: '%s' RX EXP='%s' сәйкес келді, бірақ "
                "running=False — пакет үнсіз өткізіп жіберілді",
                port_name,
                parse_result.experiment_id,
            )
            return

        for warning in parse_result.warnings:
            self.warning_occurred.emit(warning)

        combined: dict[str, float] | None = None
        for channel_key, value in parse_result.values.items():
            snapshot = self._aggregator.update(channel_key, value)
            if snapshot is not None:
                combined = snapshot

        if combined is not None:
            self._finalize_measurement(combined, parse_result.warnings)

    def _handle_set_exp_ack(self, port_name: str, line: str) -> None:
        """``OK,EXP=<id>`` жолын өңдейді. ``<id>`` ағымдағы
        ``definition.id``-мен сәйкес келмесе, тек debug-логқа жазылады
        (Phase 34.1 §2: протокол диагностикасы, студент UI-ге ЕШҚАШАН
        шықпайды) ЖӘНЕ бұл порт "starting" растауы ретінде ЕСЕПТЕЛМЕЙДІ
        (әлі ескі/басқа тәжірибенің ACK-і келуі мүмкін) — тек дәл сәйкес
        ACK ``_ports_awaiting_ack``-тен алып тастайды.
        """
        _, _, raw_id = line.partition("=")
        acknowledged_id = raw_id.strip()
        _logger.debug(
            "_handle_set_exp_ack: '%s' RX OK,EXP='%s' (күтілген '%s') starting=%s "
            "awaiting=%s",
            port_name,
            acknowledged_id,
            self._definition.id,
            self._starting,
            sorted(self._ports_awaiting_ack),
        )
        if acknowledged_id and acknowledged_id != self._definition.id:
            # Phase 34.1 §2: дәл жоғарыдағы себеппен (ескі/басқа
            # тәжірибенің ACK-і кешігіп келуі МҮМКІН, қалыпты жағдай) —
            # бұл да протокол диагностикасы, студент UI-ге шықпайды.
            # Порт "starting" растауы ретінде ЕСЕПТЕЛМЕЙДІ (ниет
            # ӨЗГЕРІССІЗ), тек debug-логта із қалады.
            _logger.debug(
                "_handle_set_exp_ack: '%s' RX OK,EXP='%s' ағымдағы '%s'-мен "
                "сәйкес келмейді — ACK елеусіз қалдырылды",
                port_name,
                acknowledged_id,
                self._definition.id,
            )
            return

        if self._starting and port_name in self._ports_awaiting_ack:
            self._ports_awaiting_ack.discard(port_name)
            self._check_start_complete()

    def _finalize_measurement(
        self, combined_values: dict[str, float], extra_warnings: tuple[str, ...]
    ) -> None:
        """Aggregator берген толық жиынтықты ``Measurement``-ке айналдырады.
        Партиалды мән бұл нүктеге ешқашан жетпейді — тек aggregator
        "толық" деп таныған жиынтық қана келеді.
        """
        validation_result = self._data_validator.validate(combined_values, self._definition)
        if not validation_result.is_valid:
            for error in validation_result.errors:
                self.validation_error.emit(error)
            return

        for warning in validation_result.warnings:
            self.warning_occurred.emit(warning)

        elapsed = self.elapsed_seconds()
        calculation_result = self._calculation_engine.calculate(
            validation_result.cleaned_values,
            self._definition,
            elapsed_seconds=elapsed,
        )
        for warning in calculation_result.warnings:
            self.warning_occurred.emit(warning)
        for error in calculation_result.errors:
            self.warning_occurred.emit(error)

        combined_warnings: tuple[str, ...] = (
            *extra_warnings,
            *validation_result.warnings,
            *calculation_result.warnings,
        )

        derived_values = dict(calculation_result.values)
        has_time_channel = any(
            channel.key == "time" for channel in self._definition.required_channels
        )
        if has_time_channel and "time" not in validation_result.cleaned_values:
            # PC authoritative elapsed time — нақты "T=" hardware-тен
            # келмесе (қазір ешбір firmware оны жібермейді), work
            # формуласында қолданылған ДӘЛ СОЛ мәнді measurement-тің
            # "time" арнасына да жазамыз (§8: бір ғана elapsed-time
            # дереккөзі, UI мен есептеу екі бөлек clock қолданбайды).
            derived_values["time"] = elapsed

        measurement = Measurement(
            timestamp=datetime.now(timezone.utc),
            values=validation_result.cleaned_values,
            experiment_id=self._definition.id,
            derived_values=derived_values,
            warnings=combined_warnings,
        )

        self._session.add_measurement(measurement)
        self.measurement_ready.emit(measurement)
