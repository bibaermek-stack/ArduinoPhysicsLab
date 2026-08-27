"""device_identifier — HELLO handshake арқылы Arduino негізіндегі
датчиктің түрін COM-порт атауына емес, құрылғының өзі жіберетін HELLO
пакетіне қарап автоматты анықтайтын сервис.

Нақты Arduino Nano/Uno құрылғылары USB Serial порты ашылғанда (DTR
арқылы) автоматты reset болады — bootloader мен ``setup()``/``loop()``
қайта жүктелуі шамамен 1.5-2.5 секунд алады. Осы "startup grace period"
ішінде PC жіберген кез келген байт (соның ішінде ``HELLO?``) жай
жоғалады, себебі Arduino оны әлі оқи алмайды. Сондықтан:

- порт ашылғаннан кейін ``HELLO?`` бірден емес, invalid grace период
  (``startup_grace_ms``) өткен соң ғана жіберіледі;
- содан кейін жауап келгенше ``HELLO?`` бірнеше рет қайталанады
  (``retry_interval_ms`` сайын), жалпы handshake ``timeout_ms`` ішінде;
- сәтсіз (timeout/invalid HELLO/cancel) аяқталған identify порттты
  міндетті түрде жабады — келесі қайта әрекет таза күйден басталады.
"""

import logging
from datetime import datetime, timezone

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from domain.constants.sensor_types import KNOWN_SENSOR_TYPES
from domain.entities.connected_device import ConnectedDevice
from infrastructure.serial_comm.hello_packet_parser import HelloPacketParser
from infrastructure.serial_comm.serial_thread_controller import SerialThreadController

_DEFAULT_HANDSHAKE_TIMEOUT_MS = 4500
_DEFAULT_STARTUP_GRACE_MS = 2000
_DEFAULT_HELLO_RETRY_INTERVAL_MS = 500
_HELLO_REQUEST = "HELLO?"

# Уақытша диагностикалық logging (COM/HELLO lifecycle аудитінің бөлігі).
# Әдепкі бойынша ешбір хендлер орнатылмағандықтан үнсіз қалады — көру
# үшін APL_DEBUG_SERIAL=1 ортасында app.py DEBUG деңгейін қосады.
_logger = logging.getLogger(__name__)


class DeviceIdentifier(QObject):
    """``SerialThreadController`` арқылы қосылған Arduino-ға ``HELLO?``
    жіберіп, жауап ретінде келген HELLO пакетінен ``ConnectedDevice``
    жасайтын сервис.

    Тек ``SerialThreadController`` public API-ын қолданады, ``SerialWorker``-
    мен немесе ``QSerialPort``-пен ешқашан тікелей жұмыс істемейді.
    """

    device_identified = Signal(object)
    identification_failed = Signal(str)
    handshake_started = Signal(str)
    handshake_timeout = Signal(str)

    def __init__(
        self,
        serial_controller: SerialThreadController,
        hello_parser: HelloPacketParser | None = None,
        timeout_ms: int = _DEFAULT_HANDSHAKE_TIMEOUT_MS,
        startup_grace_ms: int = _DEFAULT_STARTUP_GRACE_MS,
        retry_interval_ms: int = _DEFAULT_HELLO_RETRY_INTERVAL_MS,
    ) -> None:
        super().__init__()
        self._serial_controller = serial_controller
        self._hello_parser = hello_parser or HelloPacketParser()

        self._identifying = False
        self._port_name: str | None = None
        self._hello_attempt_count = 0  # тек диагностика/логтау үшін

        # Жалпы handshake дедлайны (қосылу сәтінен басталады).
        self._timeout_timer = QTimer(self)
        self._timeout_timer.setSingleShot(True)
        self._timeout_timer.setInterval(timeout_ms)
        self._timeout_timer.timeout.connect(self._on_timeout)

        # Arduino auto-reset settling уақыты — осыдан кейін ғана HELLO?
        # жіберіледі (бірінші рет).
        self._grace_timer = QTimer(self)
        self._grace_timer.setSingleShot(True)
        self._grace_timer.setInterval(startup_grace_ms)
        self._grace_timer.timeout.connect(self._on_grace_period_elapsed)

        # Grace период өткен соң, жауап келгенше HELLO?-ды қайталап
        # отыратын таймер (жалпы timeout ішінде).
        self._retry_timer = QTimer(self)
        self._retry_timer.setInterval(retry_interval_ms)
        self._retry_timer.timeout.connect(self._send_hello_request)

        self._serial_controller.connected.connect(self._on_connected)
        self._serial_controller.line_received.connect(self._on_line_received)
        # Тек диагностика: порт ашу қатесі (мыс. "access denied", "port
        # табылмады") осы арқылы да көрінеді — identify() әйтпесе үнсіз
        # handshake_timeout-қа дейін күте береді.
        self._serial_controller.error_occurred.connect(self._on_serial_error)

    def is_identifying(self) -> bool:
        """Handshake процесі қазір жүріп жатқанын қайтарады."""
        return self._identifying

    def identify(self, port_name: str, baud_rate: int = 115200) -> None:
        """Көрсетілген портпен қосылып, HELLO handshake бастайды.

        Бұрынғы identify процесі жүріп жатса, алдымен ол ``cancel()``
        етіледі (ескі порт жабылады). Ешбір exception сыртқа шықпайды.
        """
        try:
            if self._identifying:
                _logger.debug(
                    "identify('%s'): алдыңғы '%s' attempt-і cancel етілуде",
                    port_name,
                    self._port_name,
                )
                self.cancel()

            self._identifying = True
            self._port_name = port_name
            self._hello_attempt_count = 0
            _logger.debug(
                "identify('%s', baud=%d): connect_port() сұралуда", port_name, baud_rate
            )
            self._serial_controller.connect_port(port_name, baud_rate)
            self.handshake_started.emit(port_name)
        except Exception as exc:  # қорғаныс: болжанбаған қате де сыртқа шықпайды
            self._identifying = False
            self._port_name = None
            _logger.debug("identify('%s') қатесі: %s", port_name, exc)
            self.identification_failed.emit(f"identify() қатесі: {exc}")

    def cancel(self) -> None:
        """Ағымдағы handshake процесін тоқтатады (``handshake_timeout``
        шығармайды) және ашық болса, портты жабады — келесі identify
        таза күйден басталады.
        """
        was_identifying = self._identifying
        port_name = self._port_name
        self._stop_handshake()
        if was_identifying:
            _logger.debug("cancel('%s'): port disconnect_port() сұралуда", port_name)
            self._serial_controller.disconnect_port()

    def _on_connected(self, port_name: str) -> None:
        if not self._identifying or port_name != self._port_name:
            return
        _logger.debug(
            "'%s': port ашылды (connected сигналы келді) — grace timer (%dмс) басталды",
            port_name,
            self._grace_timer.interval(),
        )
        # HELLO? бірден жіберілмейді — Arduino auto-reset settling уақыты
        # (grace period) күтіледі, тек жалпы дедлайн осы сәттен басталады.
        self._timeout_timer.start()
        self._grace_timer.start()

    def _on_serial_error(self, message: str) -> None:
        # Тек диагностика — бұл сигнал ағымдағы identify-ге қатысты
        # болмауы да мүмкін, бірақ handshake кезінде пайда болса, "port
        # open" сәтсіздігінің нақты себебін көрсетеді.
        if self._identifying:
            _logger.debug(
                "'%s': serial error identify кезінде: %s", self._port_name, message
            )

    def _on_grace_period_elapsed(self) -> None:
        if not self._identifying:
            return
        _logger.debug(
            "'%s': grace period бітті, бірінші HELLO? жіберілуде", self._port_name
        )
        self._send_hello_request()
        self._retry_timer.start()

    def _send_hello_request(self) -> None:
        if not self._identifying:
            self._retry_timer.stop()
            return
        self._hello_attempt_count += 1
        _logger.debug(
            "'%s': HELLO? жіберілуде (attempt #%d)",
            self._port_name,
            self._hello_attempt_count,
        )
        self._serial_controller.write_line(_HELLO_REQUEST)

    @Slot(str)
    def _on_line_received(self, line: str) -> None:
        try:
            self._handle_line(line)
        except Exception as exc:  # қорғаныс: болжанбаған қате де сыртқа шықпайды
            self.identification_failed.emit(f"Күтпеген identification қатесі: {exc}")

    def _handle_line(self, line: str) -> None:
        if not self._identifying:
            return

        _logger.debug("'%s': RX raw line: %r", self._port_name, line)

        stripped = line.strip()
        if not stripped or not stripped.upper().startswith("TYPE="):
            # HELLO-ге қатысы жоқ жол (мыс., измерение пакеті) — елену,
            # handshake әлі жалғасады.
            _logger.debug(
                "'%s': жол HELLO-ге қатысы жоқ ('TYPE=' басталмайды), елеусіз",
                self._port_name,
            )
            return

        result = self._hello_parser.parse(stripped)
        if not result.success:
            port_name = self._port_name or ""
            _logger.debug(
                "'%s': HELLO parse СӘТСІЗ: %s", port_name, "; ".join(result.errors)
            )
            self._stop_handshake()
            self._serial_controller.disconnect_port()
            message = "; ".join(result.errors) or "HELLO пакеті жарамсыз"
            self.identification_failed.emit(f"'{port_name}': {message}")
            return

        warnings = result.warnings
        sensor_type = result.sensor_type or ""
        if sensor_type.upper() not in KNOWN_SENSOR_TYPES:
            warnings = (*warnings, f"'{sensor_type}' белгісіз сенсор түрі")

        _logger.debug(
            "'%s': HELLO parse СӘТТІ — SENSOR=%s DEV=%s",
            self._port_name,
            sensor_type,
            result.device_id,
        )

        device = ConnectedDevice(
            device_id=result.device_id or "",
            model=result.model or "",
            sensor_type=sensor_type,
            firmware_version=result.firmware_version or "",
            chip=result.chip,
            serial_number=result.serial_number,
            hardware_version=result.hardware_version,
            port_name=self._port_name or "",
            connected_at=datetime.now(timezone.utc),
            warnings=warnings,
        )
        # Сәтті identify — порт ӘДЕЙІ ашық қалады (measurement/Start үшін
        # қолданылады), тек handshake таймерлері тоқтатылады.
        self._stop_handshake()
        self.device_identified.emit(device)

    def _on_timeout(self) -> None:
        if not self._identifying:
            return
        port_name = self._port_name or ""
        _logger.debug(
            "'%s': handshake TIMEOUT (%d HELLO? attempt жасалды), порт disconnect етілуде",
            port_name,
            self._hello_attempt_count,
        )
        self._stop_handshake()
        self._serial_controller.disconnect_port()
        self.handshake_timeout.emit(port_name)

    def _stop_handshake(self) -> None:
        _logger.debug("'%s': handshake таймерлері тоқтатылуда (cleanup)", self._port_name)
        self._grace_timer.stop()
        self._retry_timer.stop()
        self._timeout_timer.stop()
        self._identifying = False
        self._port_name = None
