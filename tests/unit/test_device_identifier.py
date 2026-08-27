"""DeviceIdentifier үшін юнит-тесттер.

Нақты QSerialPort/SerialThreadController қолданылмайды — осы файлда
анықталған ``FakeSerialThreadController`` (тест double) қолданылады.
"""

import sys

import pytest
from PySide6.QtCore import QCoreApplication, QObject, Signal
from PySide6.QtTest import QTest

from domain.entities.connected_device import ConnectedDevice
from infrastructure.serial_comm.device_identifier import DeviceIdentifier
from infrastructure.serial_comm.hello_packet_parser import HelloPacketParser


@pytest.fixture(scope="module", autouse=True)
def qt_application() -> QCoreApplication:
    """QObject/Signal/QTimer механизмдері үшін жалғыз QCoreApplication дана."""
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication(sys.argv)
    return app


def _wait_until(predicate, timeout_ms: int, step_ms: int = 5) -> bool:
    """``predicate()`` ақиқат болғанша (немесе ``timeout_ms`` таусылғанша)
    event loop-ты қысқа қадамдармен айналдырады. Бір рет фиксирленген
    ``QTest.qWait(N)``-нен айырмашылығы: system жүктемесі жоғары болса да
    (мыс. толық pytest suite астында) артық күтпей, шарт орындалысымен
    бірден қайтарады — сонымен қатар CI жүктемесіне төзімді болу үшін
    жоғарғы шекті (``timeout_ms``) кең қоюға болады."""
    elapsed = 0
    while not predicate() and elapsed < timeout_ms:
        QTest.qWait(step_ms)
        elapsed += step_ms
    return predicate()


class FakeSerialThreadController(QObject):
    """SerialThreadController-дің public сигнал/әдіс бетін қайталайтын,
    нақты Serial-мен жұмыс істемейтін тест double.
    """

    connected = Signal(str)
    disconnected = Signal()
    line_received = Signal(str)
    error_occurred = Signal(str)
    state_changed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.connect_calls: list[tuple[str, int]] = []
        self.disconnect_calls: int = 0
        self.write_calls: list[str] = []
        self._running = False

    def connect_port(self, port_name: str, baud_rate: int) -> None:
        self.connect_calls.append((port_name, baud_rate))
        self._running = True

    def disconnect_port(self) -> None:
        self.disconnect_calls += 1
        self._running = False

    def write_line(self, line: str) -> None:
        self.write_calls.append(line)

    def is_running(self) -> bool:
        return self._running


def test_identify_does_not_send_hello_immediately_on_connect() -> None:
    # Arduino Nano/Uno auto-reset settling уақыты (startup grace period)
    # аяқталмай HELLO? жіберілмеуі керек — porт ашылысымен бірден жіберу
    # reset кезінде жоғалатын байт тудырады (нақты hardware-де табылған
    # ақау, әдепкі grace 2000мс).
    fake_serial = FakeSerialThreadController()
    identifier = DeviceIdentifier(fake_serial, HelloPacketParser())

    identifier.identify("COM3", 115200)
    assert fake_serial.connect_calls == [("COM3", 115200)]
    assert fake_serial.write_calls == []  # connected әлі шықпаған

    fake_serial.connected.emit("COM3")
    assert fake_serial.write_calls == []  # grace period әлі аяқталмаған


def test_identify_sends_hello_after_grace_period_elapses() -> None:
    fake_serial = FakeSerialThreadController()
    identifier = DeviceIdentifier(
        fake_serial, HelloPacketParser(), startup_grace_ms=20, retry_interval_ms=500
    )

    identifier.identify("COM3", 115200)
    fake_serial.connected.emit("COM3")
    assert fake_serial.write_calls == []

    # Тұрақты grace timer интервалы (20ms) болғанымен, бір рет фиксирленген
    # QTest.qWait(N) орнына шартты қайталап тексеретін циклды қолданамыз:
    # толық pytest suite жүктелуінде (GC, OS scheduling) фиксирленген
    # margin жеткіліксіз болып, flaky test-ке әкелетін. _wait_until әр
    # қысқа qWait итерациясынан кейін нәтижені тексереді, сондықтан system
    # жүктемесі көбейсе де — тек grace timer нақты оталғанша күте береді
    # (жоғарғы шек 5s), ал әдейі "сынбайды".
    _wait_until(lambda: fake_serial.write_calls == ["HELLO?"], timeout_ms=5000)

    assert fake_serial.write_calls == ["HELLO?"]


def test_valid_hello_creates_connected_device() -> None:
    fake_serial = FakeSerialThreadController()
    identifier = DeviceIdentifier(fake_serial, HelloPacketParser())
    devices: list[ConnectedDevice] = []
    identifier.device_identified.connect(devices.append)

    identifier.identify("COM3", 115200)
    fake_serial.connected.emit("COM3")
    fake_serial.line_received.emit(
        "TYPE=HELLO,DEV=APL-VOLTAGE-01,MODEL=V1,SENSOR=VOLTAGE,CHIP=INA226,FW=1.0"
    )

    assert len(devices) == 1
    device = devices[0]
    assert device.device_id == "APL-VOLTAGE-01"
    assert device.model == "V1"
    assert device.sensor_type == "VOLTAGE"
    assert device.port_name == "COM3"
    assert identifier.is_identifying() is False


def test_timeout_emits_handshake_timeout() -> None:
    fake_serial = FakeSerialThreadController()
    identifier = DeviceIdentifier(fake_serial, HelloPacketParser(), timeout_ms=50)
    timeouts: list[str] = []
    identifier.handshake_timeout.connect(timeouts.append)

    identifier.identify("COM3", 115200)
    fake_serial.connected.emit("COM3")

    QTest.qWait(200)

    assert timeouts == ["COM3"]
    assert identifier.is_identifying() is False


def test_measurement_packet_ignored_during_handshake() -> None:
    fake_serial = FakeSerialThreadController()
    identifier = DeviceIdentifier(fake_serial, HelloPacketParser())
    failures: list[str] = []
    devices: list[ConnectedDevice] = []
    identifier.identification_failed.connect(failures.append)
    identifier.device_identified.connect(devices.append)

    identifier.identify("COM3", 115200)
    fake_serial.connected.emit("COM3")
    fake_serial.line_received.emit("EXP=E02,U=5.0,I=0.5")

    assert failures == []
    assert devices == []
    assert identifier.is_identifying() is True


def test_invalid_hello_like_packet_emits_failure() -> None:
    fake_serial = FakeSerialThreadController()
    identifier = DeviceIdentifier(fake_serial, HelloPacketParser())
    failures: list[str] = []
    identifier.identification_failed.connect(failures.append)

    identifier.identify("COM3", 115200)
    fake_serial.connected.emit("COM3")
    fake_serial.line_received.emit("TYPE=HELLO,DEV=,SENSOR=VOLTAGE,FW=1.0")

    assert len(failures) == 1
    assert identifier.is_identifying() is False


def test_cancel_stops_identification() -> None:
    fake_serial = FakeSerialThreadController()
    identifier = DeviceIdentifier(fake_serial, HelloPacketParser(), timeout_ms=50)
    timeouts: list[str] = []
    identifier.handshake_timeout.connect(timeouts.append)

    identifier.identify("COM3", 115200)
    fake_serial.connected.emit("COM3")
    identifier.cancel()

    QTest.qWait(150)

    assert timeouts == []
    assert identifier.is_identifying() is False


def test_timeout_disconnects_port() -> None:
    # Bug C: failed identify (timeout) кезінде порт МІНДЕТТІ түрде
    # жабылуы керек — келесі қайта әрекет таза күйден басталу үшін.
    fake_serial = FakeSerialThreadController()
    identifier = DeviceIdentifier(
        fake_serial, HelloPacketParser(), timeout_ms=50, startup_grace_ms=200
    )

    identifier.identify("COM3", 115200)
    fake_serial.connected.emit("COM3")
    QTest.qWait(150)

    assert fake_serial.disconnect_calls == 1


def test_cancel_disconnects_port() -> None:
    fake_serial = FakeSerialThreadController()
    identifier = DeviceIdentifier(fake_serial, HelloPacketParser(), startup_grace_ms=200)

    identifier.identify("COM3", 115200)
    fake_serial.connected.emit("COM3")
    identifier.cancel()

    assert fake_serial.disconnect_calls == 1


def test_successful_identify_does_not_disconnect_port() -> None:
    # Сәтті identify-ден кейін порт АШЫҚ қалуы керек (measurement/Start
    # үшін қолданылады) — тек handshake-ке қатысты таймерлер тоқтайды.
    fake_serial = FakeSerialThreadController()
    identifier = DeviceIdentifier(fake_serial, HelloPacketParser())

    identifier.identify("COM3", 115200)
    fake_serial.connected.emit("COM3")
    fake_serial.line_received.emit(
        "TYPE=HELLO,DEV=APL-VOLTAGE-01,MODEL=V1,SENSOR=VOLTAGE,CHIP=INA226,FW=1.0"
    )

    assert fake_serial.disconnect_calls == 0


# ---- 1. Delayed Arduino HELLO (grace периодтан кейін, бірақ timeout-тан бұрын)


def test_delayed_hello_after_grace_period_still_succeeds() -> None:
    fake_serial = FakeSerialThreadController()
    identifier = DeviceIdentifier(
        fake_serial,
        HelloPacketParser(),
        startup_grace_ms=20,
        retry_interval_ms=500,
        timeout_ms=2000,
    )
    devices: list[ConnectedDevice] = []
    identifier.device_identified.connect(devices.append)

    identifier.identify("COM3", 115200)
    fake_serial.connected.emit("COM3")

    QTest.qWait(60)  # grace период өтті, HELLO? жіберілді
    fake_serial.line_received.emit(
        "TYPE=HELLO,DEV=APL-VOLTAGE-01,MODEL=V1,SENSOR=VOLTAGE,CHIP=INA226,FW=1.0"
    )

    assert len(devices) == 1
    assert devices[0].device_id == "APL-VOLTAGE-01"


# ---- 2. Бірінші HELLO жоғалды, екінші retry сәтті болды -------------------


def test_first_hello_lost_second_retry_succeeds() -> None:
    fake_serial = FakeSerialThreadController()
    identifier = DeviceIdentifier(
        fake_serial,
        HelloPacketParser(),
        startup_grace_ms=20,
        retry_interval_ms=30,
        timeout_ms=2000,
    )
    devices: list[ConnectedDevice] = []
    identifier.device_identified.connect(devices.append)

    identifier.identify("COM3", 115200)
    fake_serial.connected.emit("COM3")

    QTest.qWait(60)  # grace + бірінші HELLO? (жоғалды делік)
    first_hello_count = len(fake_serial.write_calls)
    assert first_hello_count >= 1

    QTest.qWait(60)  # retry_timer тағы бір HELLO? жіберді
    assert len(fake_serial.write_calls) > first_hello_count

    # Тек ЕНДІ Arduino жауап береді (екінші/кейінгі HELLO?-ге).
    fake_serial.line_received.emit(
        "TYPE=HELLO,DEV=APL-VOLTAGE-01,MODEL=V1,SENSOR=VOLTAGE,CHIP=INA226,FW=1.0"
    )

    assert len(devices) == 1


# ---- 3. Барлық retry сәтсіз — timeout шығады ------------------------------


def test_all_retries_timeout() -> None:
    fake_serial = FakeSerialThreadController()
    identifier = DeviceIdentifier(
        fake_serial,
        HelloPacketParser(),
        startup_grace_ms=10,
        retry_interval_ms=10,
        timeout_ms=80,
    )
    timeouts: list[str] = []
    devices: list[ConnectedDevice] = []
    identifier.handshake_timeout.connect(timeouts.append)
    identifier.device_identified.connect(devices.append)

    identifier.identify("COM3", 115200)
    fake_serial.connected.emit("COM3")

    QTest.qWait(200)  # Arduino ешқашан жауап бермейді

    assert timeouts == ["COM3"]
    assert devices == []
    assert len(fake_serial.write_calls) >= 2  # кем дегенде бірнеше retry болды
    assert fake_serial.disconnect_calls == 1


# ---- 4. Cleanup-тан кейінгі қайта identify сәтті болады -------------------


def test_failed_identify_can_retry_successfully_after_cleanup() -> None:
    fake_serial = FakeSerialThreadController()
    identifier = DeviceIdentifier(
        fake_serial,
        HelloPacketParser(),
        startup_grace_ms=10,
        retry_interval_ms=10,
        timeout_ms=50,
    )
    timeouts: list[str] = []
    devices: list[ConnectedDevice] = []
    identifier.handshake_timeout.connect(timeouts.append)
    identifier.device_identified.connect(devices.append)

    # Бірінші әрекет — сәтсіз (Arduino жауап бермейді).
    identifier.identify("COM3", 115200)
    fake_serial.connected.emit("COM3")
    QTest.qWait(120)

    assert timeouts == ["COM3"]
    assert fake_serial.disconnect_calls == 1

    # Екінші әрекет — дәл сол порт, дәл сол identifier, енді сәтті.
    identifier.identify("COM3", 115200)
    fake_serial.connected.emit("COM3")
    QTest.qWait(30)
    fake_serial.line_received.emit(
        "TYPE=HELLO,DEV=APL-VOLTAGE-01,MODEL=V1,SENSOR=VOLTAGE,CHIP=INA226,FW=1.0"
    )

    assert len(devices) == 1
    assert identifier.is_identifying() is False


# ---- 5/6/8/9. Екі порт тәуелсіз/параллель, бір-бірінің timeout-ына әсер етпейді


def test_two_ports_identify_independently() -> None:
    fake_com7 = FakeSerialThreadController()
    fake_com11 = FakeSerialThreadController()
    identifier_com7 = DeviceIdentifier(fake_com7, HelloPacketParser(), startup_grace_ms=10)
    identifier_com11 = DeviceIdentifier(fake_com11, HelloPacketParser(), startup_grace_ms=10)
    devices_com7: list[ConnectedDevice] = []
    devices_com11: list[ConnectedDevice] = []
    identifier_com7.device_identified.connect(devices_com7.append)
    identifier_com11.device_identified.connect(devices_com11.append)

    identifier_com7.identify("COM7", 115200)
    identifier_com11.identify("COM11", 115200)
    fake_com7.connected.emit("COM7")
    fake_com11.connected.emit("COM11")

    QTest.qWait(30)
    fake_com7.line_received.emit(
        "TYPE=HELLO,DEV=APL-VOLTAGE-01,MODEL=V1,SENSOR=VOLTAGE,CHIP=INA226,FW=1.0"
    )
    fake_com11.line_received.emit(
        "TYPE=HELLO,DEV=APL-CURRENT-01,MODEL=V1,SENSOR=CURRENT,CHIP=INA226,FW=1.0"
    )

    assert len(devices_com7) == 1 and devices_com7[0].port_name == "COM7"
    assert len(devices_com11) == 1 and devices_com11[0].port_name == "COM11"


def test_com7_timeout_does_not_block_com11_success() -> None:
    fake_com7 = FakeSerialThreadController()
    fake_com11 = FakeSerialThreadController()
    identifier_com7 = DeviceIdentifier(
        fake_com7, HelloPacketParser(), startup_grace_ms=10, retry_interval_ms=10, timeout_ms=50
    )
    identifier_com11 = DeviceIdentifier(
        fake_com11, HelloPacketParser(), startup_grace_ms=10, retry_interval_ms=500, timeout_ms=2000
    )
    timeouts_com7: list[str] = []
    devices_com11: list[ConnectedDevice] = []
    identifier_com7.handshake_timeout.connect(timeouts_com7.append)
    identifier_com11.device_identified.connect(devices_com11.append)

    # COM7 ешқашан жауап бермейді — timeout-қа ұшырайды.
    identifier_com7.identify("COM7", 115200)
    fake_com7.connected.emit("COM7")

    # COM11 сол уақытта тәуелсіз сәтті identify болады.
    identifier_com11.identify("COM11", 115200)
    fake_com11.connected.emit("COM11")
    QTest.qWait(30)
    fake_com11.line_received.emit(
        "TYPE=HELLO,DEV=APL-CURRENT-01,MODEL=V1,SENSOR=CURRENT,CHIP=INA226,FW=1.0"
    )

    assert len(devices_com11) == 1  # COM7-нің болашақ timeout-ы кедергі жасамады

    QTest.qWait(80)  # COM7-нің timeout-ы енді шығады

    assert timeouts_com7 == ["COM7"]
    # COM11 сәтті identified күйінде қалады — COM7 timeout-ы оған әсер етпеді.
    assert len(devices_com11) == 1


# ---- 7. Дәл сол портты қайта қосу (reconnect) -----------------------------


def test_reconnect_same_port_after_success() -> None:
    fake_serial = FakeSerialThreadController()
    identifier = DeviceIdentifier(fake_serial, HelloPacketParser(), startup_grace_ms=10)
    devices: list[ConnectedDevice] = []
    identifier.device_identified.connect(devices.append)

    identifier.identify("COM3", 115200)
    fake_serial.connected.emit("COM3")
    fake_serial.line_received.emit(
        "TYPE=HELLO,DEV=APL-VOLTAGE-01,MODEL=V1,SENSOR=VOLTAGE,CHIP=INA226,FW=1.0"
    )
    assert len(devices) == 1

    # Құрылғы ажыратылып (мыс. USB суырылды), пайдаланушы қайта Identify басады.
    fake_serial.disconnected.emit()
    identifier.identify("COM3", 115200)
    fake_serial.connected.emit("COM3")
    QTest.qWait(30)
    fake_serial.line_received.emit(
        "TYPE=HELLO,DEV=APL-VOLTAGE-01,MODEL=V1,SENSOR=VOLTAGE,CHIP=INA226,FW=1.0"
    )

    assert len(devices) == 2
    assert devices[1].port_name == "COM3"


# ---- 9. Ескі (stale) таймер жаңа әрекетке әсер етпейді ---------------------


def test_stale_timer_from_previous_attempt_does_not_fire_into_new_attempt() -> None:
    fake_serial = FakeSerialThreadController()
    identifier = DeviceIdentifier(
        fake_serial,
        HelloPacketParser(),
        startup_grace_ms=10,
        retry_interval_ms=10,
        timeout_ms=40,
    )
    timeouts: list[str] = []
    devices: list[ConnectedDevice] = []
    identifier.handshake_timeout.connect(timeouts.append)
    identifier.device_identified.connect(devices.append)

    # Бірінші әрекет басталады (COM3), бірақ hasty пайдаланушы бірден
    # екінші портқа (COM5) ауысады — cancel() ескі таймерлерді тоқтатуы керек.
    identifier.identify("COM3", 115200)
    fake_serial.connected.emit("COM3")
    QTest.qWait(15)  # grace аяз, бірінші HELLO? жіберілген болуы мүмкін

    identifier.identify("COM5", 115200)  # ескі (COM3) әрекетті cancel етеді
    fake_serial.connected.emit("COM5")
    fake_serial.line_received.emit(
        "TYPE=HELLO,DEV=APL-VOLTAGE-01,MODEL=V1,SENSOR=VOLTAGE,CHIP=INA226,FW=1.0"
    )

    assert len(devices) == 1
    assert devices[0].port_name == "COM5"

    # COM3-тің ескі timeout/retry таймерлері енді іске қосылмауы керек —
    # ешбір қосымша HELLO?/timeout COM3-ке қатысты пайда болмайды.
    QTest.qWait(80)

    assert timeouts == []  # COM3-тің stale timeout-ы ешқашан оталмады
