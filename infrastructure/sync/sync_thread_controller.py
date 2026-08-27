"""SyncThreadController — QThread өмірлік циклін UI thread ішінен
басқаратын, ``SyncWorker``-мен тек Qt signal/slot арқылы байланысатын
сервис.

``infrastructure/serial_comm/serial_thread_controller.py``-мен ДӘЛ
БІРДЕЙ форма (§16 "Background Sync": "use the existing worker/thread
pattern already established in this codebase if one exists"). UI
ешқашан ``SyncEngine``/``HttpSyncApiClient``-пен тікелей жұмыс
істемейді — тек осы контроллердің public signal/slot-тарын қолданады.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot

from infrastructure.sync.sync_worker import SyncWorker

_SHUTDOWN_TIMEOUT_MS = 3000


class SyncThreadController(QObject):
    sync_started = Signal()
    sync_finished = Signal(str, int, int, str, int)
    error_occurred = Signal(str)
    # § Phase 5 (Connectivity-Aware Automatic Sync): ``SyncWorker.
    # connectivity_changed``-ты ТІКЕЛЕЙ жеткізеді — is_online(bool),
    # pending_count(int).
    connectivity_changed = Signal(bool, int)

    _request_run_sync = Signal()
    _request_shutdown = Signal()

    def __init__(self, db_path: str) -> None:
        super().__init__()
        self._db_path = db_path
        self._thread: QThread | None = None
        self._worker: SyncWorker | None = None

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.isRunning()

    @Slot()
    def start(self) -> None:
        """``QThread`` пен ``SyncWorker``-ді құрып, worker-ді сол
        thread-ке көшіреді. Бірнеше рет шақырылса, thread қайта
        құрылмайды."""
        if self.is_running():
            return

        thread = QThread()
        worker = SyncWorker(self._db_path)
        worker.moveToThread(thread)

        thread.started.connect(worker.initialize)

        worker.sync_started.connect(self.sync_started)
        worker.sync_finished.connect(self.sync_finished)
        worker.error_occurred.connect(self.error_occurred)
        worker.connectivity_changed.connect(self.connectivity_changed)

        self._request_run_sync.connect(
            worker.run_sync_now, Qt.ConnectionType.QueuedConnection
        )
        self._request_shutdown.connect(
            worker.shutdown, Qt.ConnectionType.QueuedConnection
        )

        self._thread = thread
        self._worker = worker
        thread.start()

    @Slot()
    def run_sync_now(self) -> None:
        """§15 "Manual Sync" / §16 startup-after-UI-and-periodic
        триггерлерінің ортақ кіру нүктесі. Thread әлі іске қосылмаған
        болса, алдымен автоматты түрде ``start()`` шақырылады."""
        if not self.is_running():
            self.start()
        self._request_run_sync.emit()

    @Slot()
    def stop(self) -> None:
        """Worker-ге shutdown сұрап, содан кейін thread-ті таза
        тоқтатады — ``SerialThreadController.stop()``-пен БІРДЕЙ
        ``terminate()``-сіз graceful shutdown."""
        if self._thread is None:
            return

        thread = self._thread
        worker = self._worker

        if thread.isRunning():
            self._request_shutdown.emit()
            thread.quit()
            if not thread.wait(_SHUTDOWN_TIMEOUT_MS):
                self.error_occurred.emit("Sync thread белгіленген уақытта тоқтамады")
                return

        if worker is not None:
            worker.deleteLater()
        thread.deleteLater()

        self._thread = None
        self._worker = None
