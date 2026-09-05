"""LiveStreamController — QThread өмірлік циклін UI thread ішінен
басқаратын, ``LiveStreamWorker``-мен тек Qt signal/slot арқылы
байланысатын сервис.

``SyncThreadController`` құрылымымен бірдей: ``moveToThread``, queued
connection, ``stop()`` 3000 мс күтеді. UI ешқашан WebSocket ашпайды.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot

from domain.entities.measurement import Measurement
from infrastructure.storage.app_preferences import AppPreferences
from infrastructure.sync.live_stream_worker import LiveStreamWorker

_SHUTDOWN_TIMEOUT_MS = 3000


class LiveStreamController(QObject):
    error_occurred = Signal(str)

    _request_enqueue = Signal(object, str)
    _request_set_status = Signal(str, str)
    _request_shutdown = Signal()

    def __init__(self, preferences: AppPreferences, connect_ws=None) -> None:
        super().__init__()
        self._preferences = preferences
        self._connect_ws = connect_ws
        self._thread: QThread | None = None
        self._worker: LiveStreamWorker | None = None

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.isRunning()

    @Slot()
    def start(self) -> None:
        if self.is_running():
            return

        thread = QThread()
        worker = LiveStreamWorker(self._preferences, connect_ws=self._connect_ws)
        worker.moveToThread(thread)

        thread.started.connect(worker.initialize)

        worker.error_occurred.connect(self.error_occurred)

        self._request_enqueue.connect(
            worker.enqueue_measurement, Qt.ConnectionType.QueuedConnection
        )
        self._request_set_status.connect(
            worker.set_status, Qt.ConnectionType.QueuedConnection
        )
        self._request_shutdown.connect(
            worker.shutdown, Qt.ConnectionType.QueuedConnection
        )

        self._thread = thread
        self._worker = worker
        thread.start()

    @Slot(object, str)
    def enqueue_measurement(self, measurement: Measurement, session_id: str) -> None:
        if self.is_running():
            self._request_enqueue.emit(measurement, session_id)

    @Slot(str, str)
    def set_status(self, state: str, experiment_id: str) -> None:
        if self.is_running():
            self._request_set_status.emit(state, experiment_id)

    @Slot()
    def stop(self) -> None:
        if self._thread is None:
            return

        thread = self._thread
        worker = self._worker

        if thread.isRunning():
            self._request_shutdown.emit()
            thread.quit()
            if not thread.wait(_SHUTDOWN_TIMEOUT_MS):
                self.error_occurred.emit("Live stream thread белгіленген уақытта тоқтамады")
                return

        if worker is not None:
            worker.deleteLater()
        thread.deleteLater()

        self._thread = None
        self._worker = None
