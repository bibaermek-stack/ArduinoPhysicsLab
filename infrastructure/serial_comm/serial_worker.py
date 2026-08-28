"""SerialWorker — worker thread ішінде өмір сүретін QObject.

QSerialPort объектісін тек осы thread ішінде (``initialize()`` слотында,
``thread.started`` сигналымен шақырылғанда) құрады және тек осы thread
ішінде қолданады. UI бұл класспен ешқашан тікелей жұмыс істемейді —
барлық байланыс ``SerialThreadController`` арқылы, Qt signal/slot
негізінде жүреді.
"""

from PySide6.QtCore import QIODeviceBase, QObject, Signal, Slot
from PySide6.QtSerialPort import QSerialPort

from core.constants import SERIAL_RECEIVE_BUFFER_MAX_BYTES


class SerialWorker(QObject):
    """QSerialPort-пен нақты жұмыс істейтін, ``moveToThread()`` арқылы
    worker thread-ке көшірілетін объект (Worker Object pattern).

    QSerialPort бұл объект worker thread-ке көшірілгеннен КЕЙІН,
    ``initialize()`` слотында ғана құрылады, сондықтан ол әрдайым
    worker thread ішінде туады және сол thread ішінде ғана қолданылады.
    """

    connected = Signal(str)
    disconnected = Signal()
    line_received = Signal(str)
    error_occurred = Signal(str)
    bytes_written = Signal(int)
    state_changed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._serial: QSerialPort | None = None
        self._receive_buffer: bytearray = bytearray()

    @Slot()
    def initialize(self) -> None:
        """``QSerialPort`` объектісін worker thread ішінде құрады және
        оның сигналдарын қосады. Екінші рет шақырылса ешнәрсе жасамайды.
        """
        try:
            if self._serial is not None:
                return

            serial = QSerialPort(self)
            serial.readyRead.connect(self._on_ready_read)
            serial.errorOccurred.connect(self._on_error_occurred)
            serial.bytesWritten.connect(self._on_bytes_written)

            self._serial = serial
            self.state_changed.emit("initialized")
        except Exception as exc:  # қорғаныс: болжанбаған қате де сыртқа шықпайды
            self.error_occurred.emit(f"initialize() қатесі: {exc}")

    @Slot(str, int)
    def connect_port(self, port_name: str, baud_rate: int) -> None:
        """Көрсетілген порт атауымен, көрсетілген baudrate-пен байланыс
        ашады (8 data bits, no parity, 1 stop bit, no flow control).
        Бұрын ашық порт болса, алдымен жабылады.
        """
        try:
            if self._serial is None:
                self.error_occurred.emit("SerialWorker әлі initialize() етілмеген")
                return
            if not port_name:
                self.error_occurred.emit("port_name бос болмауы керек")
                return
            if baud_rate <= 0:
                self.error_occurred.emit("baud_rate оң сан болуы керек")
                return

            if self._serial.isOpen():
                self._close_port()

            self._serial.setPortName(port_name)
            self._serial.setBaudRate(baud_rate)
            self._serial.setDataBits(QSerialPort.DataBits.Data8)
            self._serial.setParity(QSerialPort.Parity.NoParity)
            self._serial.setStopBits(QSerialPort.StopBits.OneStop)
            self._serial.setFlowControl(QSerialPort.FlowControl.NoFlowControl)

            if not self._serial.open(QIODeviceBase.OpenModeFlag.ReadWrite):
                self.error_occurred.emit(
                    f"'{port_name}' портын ашу сәтсіз аяқталды: "
                    f"{self._serial.errorString()}"
                )
                return

            self._receive_buffer.clear()
            self.state_changed.emit("connected")
            self.connected.emit(port_name)
        except Exception as exc:
            self.error_occurred.emit(f"connect_port() қатесі: {exc}")

    @Slot()
    def disconnect_port(self) -> None:
        """Порт ашық болса, оны жабады."""
        try:
            self._close_port()
        except Exception as exc:
            self.error_occurred.emit(f"disconnect_port() қатесі: {exc}")

    @Slot(str)
    def write_line(self, line: str) -> None:
        """Бір мәтіндік жолды порт арқылы жібереді. Жол соңында newline
        болмаса, автоматты түрде ``\\n`` қосылады. Порт ашық болмаса,
        error_occurred шығарылады.
        """
        try:
            if self._serial is None or not self._serial.isOpen():
                self.error_occurred.emit("Порт ашық емес, жол жіберілмеді")
                return

            payload = line if line.endswith("\n") else line + "\n"
            self._serial.write(payload.encode("utf-8"))
        except Exception as exc:
            self.error_occurred.emit(f"write_line() қатесі: {exc}")

    @Slot()
    def shutdown(self) -> None:
        """Портты жауып, барлық ресурстарды босатады."""
        try:
            self._close_port()
            self._serial = None
            self.state_changed.emit("shutdown")
        except Exception as exc:
            self.error_occurred.emit(f"shutdown() қатесі: {exc}")

    def _close_port(self) -> None:
        """Порт ашық болса жабады және қабылдау буферін тазалайды."""
        if self._serial is not None and self._serial.isOpen():
            self._serial.close()
            self._receive_buffer.clear()
            self.state_changed.emit("disconnected")
            self.disconnected.emit()

    def _on_ready_read(self) -> None:
        """Келген байттарды буферге жинап, толық newline-мен аяқталған
        жолдарды ``line_received`` арқылы шығарады. Жартылай жол
        буферде қалады.
        """
        if self._serial is None:
            return

        chunk = bytes(self._serial.readAll())
        self._receive_buffer.extend(chunk)

        if len(self._receive_buffer) > SERIAL_RECEIVE_BUFFER_MAX_BYTES:
            self.error_occurred.emit(
                "Serial буфер шектен асты (newline табылмады), буфер тазаланды"
            )
            self._receive_buffer.clear()
            return

        while True:
            newline_index = self._receive_buffer.find(b"\n")
            if newline_index == -1:
                break

            raw_line = self._receive_buffer[:newline_index]
            del self._receive_buffer[: newline_index + 1]

            if raw_line.endswith(b"\r"):
                raw_line = raw_line[:-1]

            try:
                text_line = raw_line.decode("utf-8")
            except UnicodeDecodeError as exc:
                self.error_occurred.emit(f"UTF-8 decode қатесі: {exc}")
                continue

            self.line_received.emit(text_line)

    def _on_error_occurred(self, error: QSerialPort.SerialPortError) -> None:
        """QSerialPort қатесін ``error_occurred`` сигналына айналдырады."""
        if self._serial is None or error == QSerialPort.SerialPortError.NoError:
            return
        self.error_occurred.emit(self._serial.errorString())

    def _on_bytes_written(self, byte_count: int) -> None:
        """QSerialPort.bytesWritten сигналын ``bytes_written``-қа жеткізеді."""
        self.bytes_written.emit(int(byte_count))
