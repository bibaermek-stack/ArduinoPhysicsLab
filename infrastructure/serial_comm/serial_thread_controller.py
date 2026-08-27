"""SerialThreadController — QThread өмірлік циклін UI thread ішінен
басқаратын, SerialWorker-мен тек Qt signal/slot арқылы байланысатын
сервис.

UI-мен тек Qt signal/slot арқылы байланысады, SerialWorker-ді
moveToThread() арқылы worker thread-ке орналастырады.
"""

from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot

from infrastructure.serial_comm.serial_worker import SerialWorker

_SHUTDOWN_TIMEOUT_MS = 3000


class SerialThreadController(QObject):
    """UI thread ішінде тұратын, ``SerialWorker``-ді бөлек ``QThread``
    ішінде іске қосатын және оның сигналдарын UI-ге қайта жіберетін
    контроллер.

    UI ешқашан ``QSerialPort``-пен немесе ``SerialWorker``-мен тікелей
    жұмыс істемейді — тек осы контроллердің public signal/slot-тарын
    қолданады.
    """

    connected = Signal(str)
    disconnected = Signal()
    line_received = Signal(str)
    error_occurred = Signal(str)
    state_changed = Signal(str)

    # Worker-ге бағытталған, тек ішкі қолдануға арналған ("private") сигналдар.
    _request_connect = Signal(str, int)
    _request_disconnect = Signal()
    _request_write = Signal(str)
    _request_shutdown = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._thread: QThread | None = None
        self._worker: SerialWorker | None = None

    def is_running(self) -> bool:
        """Worker thread-і қазір жұмыс істеп тұрғанын қайтарады."""
        return self._thread is not None and self._thread.isRunning()

    @Slot()
    def start(self) -> None:
        """``QThread`` пен ``SerialWorker``-ді құрып, worker-ді сол
        thread-ке көшіреді. Бірнеше рет шақырылса, thread қайта
        құрылмайды.
        """
        if self.is_running():
            return

        thread = QThread()
        worker = SerialWorker()
        worker.moveToThread(thread)

        thread.started.connect(worker.initialize)

        worker.connected.connect(self.connected)
        worker.disconnected.connect(self.disconnected)
        worker.line_received.connect(self.line_received)
        worker.error_occurred.connect(self.error_occurred)
        worker.state_changed.connect(self.state_changed)

        self._request_connect.connect(
            worker.connect_port, Qt.ConnectionType.QueuedConnection
        )
        self._request_disconnect.connect(
            worker.disconnect_port, Qt.ConnectionType.QueuedConnection
        )
        self._request_write.connect(
            worker.write_line, Qt.ConnectionType.QueuedConnection
        )
        self._request_shutdown.connect(
            worker.shutdown, Qt.ConnectionType.QueuedConnection
        )

        self._thread = thread
        self._worker = worker
        thread.start()

    @Slot(str, int)
    def connect_port(self, port_name: str, baud_rate: int) -> None:
        """Көрсетілген портпен байланыс ашуды сұрайды. Thread әлі
        іске қосылмаған болса, алдымен автоматты түрде ``start()``
        шақырылады.
        """
        if not self.is_running():
            self.start()
        self._request_connect.emit(port_name, baud_rate)

    @Slot()
    def disconnect_port(self) -> None:
        """Ашық портты жабуды сұрайды."""
        if self.is_running():
            self._request_disconnect.emit()

    @Slot(str)
    def write_line(self, line: str) -> None:
        """Бір жолды worker арқылы жіберуді сұрайды."""
        if self.is_running():
            self._request_write.emit(line)

    @Slot()
    def stop(self) -> None:
        """Worker-ге shutdown сұрап, содан кейін thread-ті таза
        тоқтатады: ``request_shutdown`` → ``thread.quit()`` →
        ``thread.wait(timeout)``. Thread белгіленген уақытта тоқтамаса,
        ``error_occurred`` шығарылады. ``terminate()`` ешқашан
        қолданылмайды.
        """
        if self._thread is None:
            return

        thread = self._thread
        worker = self._worker

        if thread.isRunning():
            self._request_shutdown.emit()
            thread.quit()
            if not thread.wait(_SHUTDOWN_TIMEOUT_MS):
                self.error_occurred.emit("Serial thread белгіленген уақытта тоқтамады")
                # Thread әлі тоқтаған жоқ: әлі белсенді QThread/SerialWorker-ді
                # deleteLater()-ге ұсынбаймыз және сілтемелерді тазаламаймыз —
                # әйтпесе dangling QObject қалады да, контроллер бұл thread-ті
                # мүлдем бақылаудан шығарып алады.
                return

        if worker is not None:
            worker.deleteLater()
        thread.deleteLater()

        self._thread = None
        self._worker = None
