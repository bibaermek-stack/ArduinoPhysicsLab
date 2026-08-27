"""DeviceManager — application-lifetime, persistent құрылғы қосылымдарын
басқаратын сервис.

Device connection lifecycle-ды experiment lifecycle-дан толық ажырату
үшін жасалған: бір рет identified/connected болған сенсор
(``SerialThreadController`` + ``DeviceIdentifier`` жұбы) application
жабылғанша, немесе құрылғы физикалық ажыратылғанша ашық қалады.
``ExperimentWorkspacePage``/``MultiSensorExperimentCoordinator`` бұл
байланыстардың owner-ы ЕМЕС — тек осы менеджерден port "тыңдауын"
сұрайды (``identify``/сигналдарға жазылу), эксперимент ауысқанда порт
ЕШҚАШАН жабылмайды.

``DeviceManager`` MainWindow-мен бірге БІР рет жасалады және бүкіл
қолданба өмірі бойы (application lifetime) өмір сүреді — тек нақты
``shutdown_all()`` шақырылғанда (application жабылу) немесе физикалық
USB ажыратылғанда порт жабылады.
"""

import logging
from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal

from domain.entities.connected_device import ConnectedDevice
from infrastructure.serial_comm.device_identifier import DeviceIdentifier
from infrastructure.serial_comm.serial_thread_controller import SerialThreadController

# Уақытша диагностикалық logging (DeviceIdentifier-дегі APL_DEBUG_SERIAL
# паттернімен бірдей) — write_to_port() нақты жазуды сұрағанын/портты
# таппағанын/thread тірі емес екенін көрсету үшін.
_logger = logging.getLogger(__name__)


@dataclass
class _ManagedPort:
    """Бір COM-порттың persistent күйі (менеджердің ішкі бухгалтериясы —
    публикалық API емес).
    """

    port_name: str
    serial_controller: SerialThreadController
    device_identifier: DeviceIdentifier
    device: ConnectedDevice | None = None


class DeviceManager(QObject):
    """Барлық COM-порт қосылымдарын application lifetime бойы иеленетін
    жалғыз объект.

    ``ExperimentWorkspacePage`` (тұрақты, MainWindow-да бір рет жасалатын
    бет) осы менеджердің БІР данасын конструктор арқылы алады да, әр
    ``on_enter()``-де жаңа ``MultiSensorExperimentCoordinator`` жасалса да,
    сол БІР ``DeviceManager`` данасы сақталып қалады.
    """

    device_identified = Signal(object)  # ConnectedDevice
    device_identification_failed = Signal(str)
    handshake_timeout = Signal(str)
    port_disconnected = Signal(str)  # port_name (физикалық ажырау)
    port_error = Signal(str, str)  # (port_name, message)
    line_received = Signal(str, str)  # (port_name, line)

    def __init__(self) -> None:
        super().__init__()
        self._ports: dict[str, _ManagedPort] = {}

    def identify(self, port_name: str, baud_rate: int = 115200) -> None:
        """Көрсетілген портты анықтауды сұрайды.

        Портта ҚАЗІРДІҢ ӨЗІНДЕ alive байланыс болса (бұрын identified),
        ЖАҢА HELLO handshake жасалмайды — тек соңғы белгілі
        ``ConnectedDevice`` (бар болса) қайта ``device_identified``
        арқылы хабарланады (reuse). Әйтпесе жаңа ``SerialThreadController``
        + ``DeviceIdentifier`` жұбы ашылып, нақты HELLO handshake
        басталады (``DeviceIdentifier``-дің grace/retry/timeout логикасы
        өзгеріссіз).
        """
        managed = self._ports.get(port_name)
        if managed is not None and managed.serial_controller.is_running():
            if managed.device is not None:
                self.device_identified.emit(managed.device)
            return

        if managed is None:
            managed = self._create_managed_port(port_name)
            self._ports[port_name] = managed
        managed.device_identifier.identify(port_name, baud_rate)

    def get_connected_device(self, sensor_type: str) -> ConnectedDevice | None:
        """Берілген сенсор түрі бойынша ҚАЗІРГІ identified құрылғыны
        қайтарады (жоқ болса ``None``).
        """
        sensor_type_upper = sensor_type.upper()
        for managed in self._ports.values():
            if managed.device is not None and managed.device.sensor_type.upper() == sensor_type_upper:
                return managed.device
        return None

    def get_connected_devices(self) -> tuple[ConnectedDevice, ...]:
        """Қазір identified барлық құрылғыны қайтарады."""
        return tuple(
            managed.device for managed in self._ports.values() if managed.device is not None
        )

    def is_port_connected(self, port_name: str) -> bool:
        """Порт ашық және worker thread жұмыс істеп тұрғанын қайтарады."""
        managed = self._ports.get(port_name)
        return managed is not None and managed.serial_controller.is_running()

    def write_to_port(self, port_name: str, line: str) -> None:
        """Бір жолды (мыс. ``SET_EXP=<id>``) көрсетілген портқа жібереді.
        Порт белгісіз болса, үнсіз ешнәрсе істемейді.
        """
        managed = self._ports.get(port_name)
        if managed is None:
            _logger.debug(
                "write_to_port('%s', %r): порт белгісіз, жазу жіберілмеді", port_name, line
            )
            return
        is_running = managed.serial_controller.is_running()
        _logger.debug(
            "write_to_port('%s', %r): serial_controller.is_running()=%s",
            port_name,
            line,
            is_running,
        )
        managed.serial_controller.write_line(line)

    def disconnect_port(self, port_name: str) -> None:
        """Пайдаланушы ӘДЕЙІ (explicit) ажыратуды сұрағанда шақырылады —
        физикалық ажыратудан ("_on_port_disconnected") өзгеше, бұл PC-side
        бастамашылық.
        """
        managed = self._ports.pop(port_name, None)
        if managed is not None:
            managed.serial_controller.stop()

    def shutdown_all(self) -> None:
        """Барлық басқарылатын порттың serial thread-ін толық тоқтатады.
        ТЕК application шынымен жабылғанда шақырылуы тиіс (мыс.
        ``QApplication.aboutToQuit``) — эксперимент ауысу/навигация
        кезінде ЕШҚАШАН шақырылмайды.
        """
        for managed in self._ports.values():
            try:
                managed.serial_controller.stop()
            except Exception:  # қорғаныс: application жабылу кезінде де құламау керек
                pass
        self._ports.clear()

    def _create_managed_port(self, port_name: str) -> _ManagedPort:
        serial_controller = SerialThreadController()
        device_identifier = DeviceIdentifier(serial_controller=serial_controller)
        managed = _ManagedPort(
            port_name=port_name,
            serial_controller=serial_controller,
            device_identifier=device_identifier,
        )

        serial_controller.disconnected.connect(
            lambda: self._on_port_disconnected(port_name)
        )
        serial_controller.error_occurred.connect(
            lambda message: self.port_error.emit(port_name, message)
        )
        serial_controller.line_received.connect(
            lambda line: self.line_received.emit(port_name, line)
        )

        device_identifier.device_identified.connect(
            lambda device: self._on_device_identified(port_name, device)
        )
        device_identifier.identification_failed.connect(
            self.device_identification_failed
        )
        device_identifier.handshake_timeout.connect(self.handshake_timeout)

        return managed

    def _on_device_identified(self, port_name: str, device: ConnectedDevice) -> None:
        managed = self._ports.get(port_name)
        if managed is not None:
            managed.device = device
        self.device_identified.emit(device)

    def _on_port_disconnected(self, port_name: str) -> None:
        """Физикалық USB ажырау (немесе serial error) — портты толық
        тіркеуден шығарады, келесі ``identify()`` таза күйден басталады.
        """
        self._ports.pop(port_name, None)
        self.port_disconnected.emit(port_name)
