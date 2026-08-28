"""ExperimentController — жеңіл контроллер.

SerialThreadController-ден келген raw text line-ды PacketParser →
DataValidator → CalculationEngine арқылы өткізіп, Measurement объектісін
құрып ExperimentSession-ға қосады және дайын нәтижені UI-ге Qt signal
арқылы жібереді. Өлшеуді бастау/тоқтату/сессияны тазалау әрекеттерін
басқарады.
"""

import logging
from datetime import datetime, timezone
from uuid import uuid4

from PySide6.QtCore import QObject, Signal, Slot

from domain.entities.connected_device import ConnectedDevice
from domain.entities.experiment_definition import ExperimentDefinition
from domain.entities.experiment_session import ExperimentSession
from domain.entities.measurement import Measurement
from domain.services.calculation_engine import CalculationEngine
from domain.services.data_validator import DataValidator
from domain.services.device_registry import DeviceRegistry
from infrastructure.serial_comm.device_identifier import DeviceIdentifier
from infrastructure.serial_comm.hello_packet_parser import HelloPacketParser
from infrastructure.serial_comm.packet_parser import PacketParser
from infrastructure.serial_comm.serial_thread_controller import SerialThreadController

_logger = logging.getLogger(__name__)


class ExperimentController(QObject):
    """Бір зертхана жұмысына арналған pipeline-ды басқаратын контроллер.

    Pipeline: ``SerialThreadController.line_received`` → ``PacketParser``
    → ``DataValidator`` → ``CalculationEngine`` → ``Measurement`` →
    ``ExperimentSession.add_measurement`` → ``measurement_ready``.

    UI бұл объектінің public signal/slot-тарын ғана қолданады, ешқашан
    ``SerialThreadController``-мен немесе ``SerialWorker``-мен тікелей
    жұмыс істемейді.
    """

    measurement_ready = Signal(object)
    parse_error = Signal(str)
    validation_error = Signal(str)
    warning_occurred = Signal(str)
    connection_state_changed = Signal(str)

    # SerialThreadController сигналдарының тікелей форварды.
    connected = Signal(str)
    disconnected = Signal()
    error_occurred = Signal(str)
    state_changed = Signal(str)

    # DeviceIdentifier сигналдарының тікелей форварды.
    device_identified = Signal(object)
    device_identification_failed = Signal(str)
    handshake_timeout = Signal(str)

    def __init__(
        self,
        definition: ExperimentDefinition,
        serial_controller: SerialThreadController | None = None,
        packet_parser: PacketParser | None = None,
        data_validator: DataValidator | None = None,
        calculation_engine: CalculationEngine | None = None,
        session: ExperimentSession | None = None,
        hello_parser: HelloPacketParser | None = None,
        device_identifier: DeviceIdentifier | None = None,
        device_registry: DeviceRegistry | None = None,
    ) -> None:
        super().__init__()
        self._definition = definition
        self._serial_controller = serial_controller or SerialThreadController()
        self._packet_parser = packet_parser or PacketParser()
        self._data_validator = data_validator or DataValidator()
        self._calculation_engine = calculation_engine or CalculationEngine()
        self._session = session or ExperimentSession(
            id=str(uuid4()),
            experiment_id=definition.id,
            started_at=datetime.now(timezone.utc),
        )
        self._running = False

        self._hello_parser = hello_parser or HelloPacketParser()
        self._device_registry = device_registry or DeviceRegistry()
        self._device_identifier = device_identifier or DeviceIdentifier(
            serial_controller=self._serial_controller, hello_parser=self._hello_parser
        )

        self._serial_controller.connected.connect(self.connected)
        self._serial_controller.disconnected.connect(self.disconnected)
        self._serial_controller.error_occurred.connect(self.error_occurred)
        self._serial_controller.state_changed.connect(self.state_changed)
        self._serial_controller.state_changed.connect(self.connection_state_changed)
        self._serial_controller.line_received.connect(self._on_line_received)

        self._device_identifier.device_identified.connect(self._on_device_identified)
        self._device_identifier.identification_failed.connect(
            self.device_identification_failed
        )
        self._device_identifier.handshake_timeout.connect(self.handshake_timeout)

    @property
    def session(self) -> ExperimentSession:
        """Контроллер ішінде сақталатын ағымдағы ExperimentSession."""
        return self._session

    @property
    def device_registry(self) -> DeviceRegistry:
        """Контроллер ішінде сақталатын DeviceRegistry."""
        return self._device_registry

    def is_running(self) -> bool:
        """Тәжірибе қазір өлшеу қабылдап тұрғанын қайтарады."""
        return self._running

    def connect_device(self, port_name: str, baud_rate: int = 115200) -> None:
        """Serial құрылғымен байланыс ашуды сұрайды."""
        try:
            self._serial_controller.connect_port(port_name, baud_rate)
        except Exception as exc:  # қорғаныс: болжанбаған қате де сыртқа шықпайды
            self.error_occurred.emit(f"connect_device() қатесі: {exc}")

    def disconnect_device(self) -> None:
        """Serial байланысты жабуды сұрайды."""
        try:
            self._serial_controller.disconnect_port()
        except Exception as exc:
            self.error_occurred.emit(f"disconnect_device() қатесі: {exc}")

    def shutdown(self) -> None:
        """Serial thread-ті толық тоқтатады (мыс., жаңа зертхана жұмысына
        ауысу немесе терезе жабылу алдында шақырылады).
        """
        try:
            self._serial_controller.stop()
        except Exception as exc:
            self.error_occurred.emit(f"shutdown() қатесі: {exc}")

    def start_experiment(self) -> None:
        """Тәжірибені бастайды — содан кейін ғана келген пакеттер
        Measurement-ке айналады.

        Бір Arduino құрылғысы (мыс., Voltage Sensor) бірнеше тәжірибеде
        қолданылуы мүмкін болғандықтан, Arduino-ға ағымдағы
        ``definition.id``-ды ``SET_EXP=<id>`` командасымен жібереді —
        осылай Arduino өз EXP өрісін дұрыс жіберуге "үйретіледі". Arduino
        бұл команданы білмесе де (ескі firmware), елеусіз қалдырады —
        протокол артқа үйлесімді.
        """
        self._running = True
        self._calculation_engine.reset()
        try:
            self._serial_controller.write_line(f"SET_EXP={self._definition.id}")
        except Exception as exc:  # қорғаныс: болжанбаған қате де сыртқа шықпайды
            self.error_occurred.emit(f"SET_EXP жіберу қатесі: {exc}")

    def stop_experiment(self) -> None:
        """Тәжірибені тоқтатады және сессияны аяқтайды (``ended_at``
        орнатылады, бірнеше рет шақырылса өзгермейді).
        """
        try:
            self._running = False
            self._session.stop()
        except Exception as exc:
            self.error_occurred.emit(f"stop_experiment() қатесі: {exc}")

    def clear_session(self) -> None:
        """Жиналған барлық өлшемдерді сессиядан тазалайды."""
        try:
            self._session.clear()
            self._calculation_engine.reset()
        except Exception as exc:
            self.error_occurred.emit(f"clear_session() қатесі: {exc}")

    def identify_device(self, port_name: str, baud_rate: int = 115200) -> None:
        """Көрсетілген порттағы Arduino-ны HELLO handshake арқылы
        автоматты анықтауды бастайды (COM-порт атауына емес, құрылғының
        өз жауабына сүйеніп).
        """
        try:
            self._device_identifier.identify(port_name, baud_rate)
        except Exception as exc:
            self.error_occurred.emit(f"identify_device() қатесі: {exc}")

    @Slot(object)
    def _on_device_identified(self, device: ConnectedDevice) -> None:
        """DeviceIdentifier анықтаған құрылғыны DeviceRegistry-ге
        тіркеп, UI-ге жеткізеді.
        """
        try:
            self._device_registry.register(device)
        except Exception as exc:
            self.error_occurred.emit(f"DeviceRegistry тіркеу қатесі: {exc}")
        self.device_identified.emit(device)

    @Slot(str)
    def _on_line_received(self, line: str) -> None:
        """``SerialThreadController.line_received`` сигналына жазылатын
        слот. Ешбір exception сыртқа шықпайды.
        """
        _logger.debug("RX: %s", line)
        try:
            self._process_line(line)
        except Exception as exc:  # қорғаныс: болжанбаған қате де сыртқа шықпайды
            self.parse_error.emit(f"Күтпеген өңдеу қатесі: {exc}")

    def _process_line(self, line: str) -> None:
        """Бір raw Serial жолын толық pipeline арқылы өткізеді."""
        stripped = line.strip()
        if not stripped:
            return

        if stripped.upper().startswith("TYPE="):
            # HELLO handshake пакеті — measurement pipeline-ге қатысы жоқ.
            # Оны сол SerialThreadController.line_received сигналына
            # тәуелсіз жазылған DeviceIdentifier бөлек өңдейді, сондықтан
            # мұнда тек пакетті measurement parser-ға жібермей өткізіп
            # жіберу жеткілікті (parse_error шықпайды).
            return

        if stripped.upper().startswith("OK,EXP="):
            # SET_EXP командасына Arduino-дан келген растау — measurement
            # pipeline-ге қатысы жоқ, тек сәйкессіздікті тексереді.
            self._handle_set_exp_ack(stripped)
            return

        parse_result = self._packet_parser.parse_line(line)
        if not parse_result.is_valid:
            for error in parse_result.errors:
                self.parse_error.emit(error)
            return

        if parse_result.experiment_id != self._definition.id:
            self.warning_occurred.emit(
                f"Пакеттің EXP='{parse_result.experiment_id}' мәні ағымдағы "
                f"тәжірибе '{self._definition.id}'-мен сәйкес келмейді, "
                "пакет өткізіп жіберілді"
            )
            return

        if not self._running:
            # Тоқтатылған кезде де Arduino ағыны үздіксіз жалғаса береді —
            # бұл ҚАЛЫПТЫ, күтілетін жағдай, сондықтан визуалды UI
            # хабарламасы ретінде ЕМЕС, тек debug-логқа (APL_DEBUG_SERIAL=1)
            # жазылады. Пакет өзі әлі де толық өткізіп жіберіледі.
            _logger.debug(
                "_process_line: EXP='%s' сәйкес келді, бірақ running=False — "
                "пакет үнсіз өткізіп жіберілді",
                parse_result.experiment_id,
            )
            return

        for warning in parse_result.warnings:
            self.warning_occurred.emit(warning)

        validation_result = self._data_validator.validate(parse_result.values, self._definition)
        if not validation_result.is_valid:
            for error in validation_result.errors:
                self.validation_error.emit(error)
            return

        for warning in validation_result.warnings:
            self.warning_occurred.emit(warning)

        calculation_result = self._calculation_engine.calculate(
            validation_result.cleaned_values,
            self._definition,
            elapsed_seconds=self._session.duration_seconds(),
        )
        for warning in calculation_result.warnings:
            self.warning_occurred.emit(warning)
        for error in calculation_result.errors:
            self.warning_occurred.emit(error)

        combined_warnings: tuple[str, ...] = (
            *parse_result.warnings,
            *validation_result.warnings,
            *calculation_result.warnings,
        )

        measurement = Measurement(
            timestamp=datetime.now(timezone.utc),
            values=validation_result.cleaned_values,
            experiment_id=parse_result.experiment_id,
            derived_values=calculation_result.values,
            warnings=combined_warnings,
        )

        self._session.add_measurement(measurement)
        self.measurement_ready.emit(measurement)

    def _handle_set_exp_ack(self, line: str) -> None:
        """``OK,EXP=<id>`` жолын өңдейді. ``<id>`` ағымдағы
        ``definition.id``-мен сәйкес келмесе, ескерту шығарады (мыс.,
        Arduino ескі/басқа тәжірибе идентификаторын растап тұрса).
        """
        _, _, raw_id = line.partition("=")
        acknowledged_id = raw_id.strip()
        if acknowledged_id and acknowledged_id != self._definition.id:
            self.warning_occurred.emit(
                f"Arduino SET_EXP растауы '{acknowledged_id}' ағымдағы тәжірибе "
                f"'{self._definition.id}'-мен сәйкес келмейді"
            )
