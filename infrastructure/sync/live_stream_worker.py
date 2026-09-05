"""LiveStreamWorker — GUI ағынында WebSocket ашпайтын тірі өлшем
жіберушісі (QThread Worker Object, ``SyncWorker`` үлгісі).

Конструктор тек баптау мен кезекті сақтайды — ``websockets`` / ``QTimer``
/ asyncio loop ``initialize()`` ішінде ғана құрылады. Токен мен нүкте
мәндері логталмайды.
"""

from __future__ import annotations

import asyncio
import json
import queue
from datetime import datetime, timezone

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from domain.entities.measurement import Measurement
from domain.services.sync_auth import get_configured_sync_api_key
from infrastructure.storage.app_preferences import AppPreferences

_FLUSH_INTERVAL_MS = 500
_PING_INTERVAL_MS = 5000
_PUMP_INTERVAL_MS = 50
_QUEUE_MAX = 500
_MAX_POINTS_PER_FRAME = 50
_RECONNECT_DELAYS_S = (1, 2, 5, 10)
_LIVE_WS_PATH = "/api/v1/live/ws"
_CONNECT_OPEN_TIMEOUT_S = 5
_CONNECT_CLOSE_TIMEOUT_S = 2


def ws_url_from_http(base: str) -> str:
    text = (base or "").strip()
    if text.startswith("https://"):
        text = "wss://" + text[len("https://") :]
    elif text.startswith("http://"):
        text = "ws://" + text[len("http://") :]
    return text.rstrip("/") + _LIVE_WS_PATH


def _timestamp_to_zulu(timestamp: datetime) -> str:
    utc = timestamp.astimezone(timezone.utc)
    text = utc.isoformat(timespec="milliseconds")
    if text.endswith("+00:00") or text.endswith("-00:00"):
        return text[:-6] + "Z"
    return text


def build_samples_frame(
    experiment_id: str, session_id: str, measurements: list[Measurement]
) -> dict:
    points = measurements[:_MAX_POINTS_PER_FRAME]
    return {
        "type": "samples",
        "experiment_id": experiment_id,
        "session_id": session_id,
        "points": [
            {"t": _timestamp_to_zulu(item.timestamp), "values": item.all_values()}
            for item in points
        ],
    }


def reconnect_delay_seconds(attempt: int) -> int:
    if attempt < 0:
        attempt = 0
    index = min(attempt, len(_RECONNECT_DELAYS_S) - 1)
    return min(_RECONNECT_DELAYS_S[index], 10)


class LiveStreamWorker(QObject):
    error_occurred = Signal(str)

    def __init__(self, preferences: AppPreferences, connect_ws=None) -> None:
        super().__init__()
        self._preferences = preferences
        self._connect_ws = connect_ws
        self._queue: queue.Queue[tuple[Measurement, str]] = queue.Queue(maxsize=_QUEUE_MAX)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._ws = None
        self._flush_timer: QTimer | None = None
        self._ping_timer: QTimer | None = None
        self._pump_timer: QTimer | None = None
        self._reconnect_timer: QTimer | None = None
        self._state = "idle"
        self._experiment_id = ""
        self._reconnect_attempt = 0
        self._closing = False
        self._connecting = False
        self._tasks: set[asyncio.Task] = set()

    @Slot()
    def initialize(self) -> None:
        if self._loop is not None:
            return
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._loop = loop
            self._closing = False

            self._flush_timer = QTimer(self)
            self._flush_timer.setInterval(_FLUSH_INTERVAL_MS)
            self._flush_timer.timeout.connect(self.flush)
            self._flush_timer.start()

            self._ping_timer = QTimer(self)
            self._ping_timer.setInterval(_PING_INTERVAL_MS)
            self._ping_timer.timeout.connect(self._on_idle_tick)
            self._ping_timer.start()

            self._pump_timer = QTimer(self)
            self._pump_timer.setInterval(_PUMP_INTERVAL_MS)
            self._pump_timer.timeout.connect(self._pump_loop)
            self._pump_timer.start()

            self._try_connect()
            self._pump_loop()
        except Exception as exc:
            self.error_occurred.emit(
                f"LiveStreamWorker.initialize() қатесі: {type(exc).__name__}"
            )

    @Slot(object, str)
    def enqueue_measurement(self, measurement: Measurement, session_id: str) -> None:
        try:
            self._queue.put_nowait((measurement, session_id))
        except queue.Full:
            return

    @Slot(str, str)
    def set_status(self, state: str, experiment_id: str) -> None:
        changed = state != self._state or experiment_id != self._experiment_id
        self._state = state
        self._experiment_id = experiment_id
        if changed and self._ws is not None:
            self._submit(
                self._send_json(
                    {"type": "status", "state": state, "experiment_id": experiment_id}
                )
            )

    @Slot()
    def flush(self) -> None:
        self._pump_loop()
        self._ensure_connection_state()
        if self._ws is None:
            return
        frame = self._drain_queue()
        if frame is not None:
            self._submit(self._send_json(frame))

    def _drain_queue(self) -> dict | None:
        batch: list[tuple[Measurement, str]] = []
        while len(batch) < _MAX_POINTS_PER_FRAME:
            try:
                batch.append(self._queue.get_nowait())
            except queue.Empty:
                break
        if not batch:
            return None
        measurements = [item[0] for item in batch]
        session_id = batch[0][1]
        return build_samples_frame(measurements[0].experiment_id, session_id, measurements)

    @Slot()
    def shutdown(self) -> None:
        self._closing = True
        for timer in (
            self._flush_timer,
            self._ping_timer,
            self._pump_timer,
            self._reconnect_timer,
        ):
            if timer is not None:
                timer.stop()
        self._flush_timer = None
        self._ping_timer = None
        self._pump_timer = None
        self._reconnect_timer = None
        self._connecting = False

        loop = self._loop
        if loop is None:
            self._ws = None
            return

        async def _close_all() -> None:
            current = asyncio.current_task(loop)
            pending = [task for task in asyncio.all_tasks(loop) if task is not current]
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            ws = self._ws
            self._ws = None
            if ws is None:
                return
            close = getattr(ws, "close", None)
            if close is None:
                return
            result = close()
            if asyncio.iscoroutine(result):
                try:
                    await result
                except Exception:
                    pass

        try:
            if not loop.is_closed():
                loop.run_until_complete(_close_all())
                loop.close()
        except Exception:
            pass
        self._loop = None
        self._tasks.clear()

    @Slot()
    def _on_idle_tick(self) -> None:
        self._pump_loop()
        self._ensure_connection_state()
        if self._ws is None:
            return
        if self._state != "measuring":
            self._submit(
                self._send_json(
                    {
                        "type": "status",
                        "state": self._state or "idle",
                        "experiment_id": self._experiment_id,
                    }
                )
            )
        self._submit(self._send_json({"type": "ping"}))

    def _pump_loop(self) -> None:
        loop = self._loop
        if loop is None or loop.is_closed() or self._closing:
            return
        loop.call_soon(loop.stop)
        try:
            loop.run_forever()
        except RuntimeError:
            return

    def _ensure_connection_state(self) -> None:
        if self._closing or self._loop is None:
            return
        token = (self._preferences.get_account_token() or "").strip()
        base = (self._preferences.get_sync_api_base_url() or "").strip()
        if not token or not base:
            if self._reconnect_timer is not None:
                self._reconnect_timer.stop()
            self._reconnect_attempt = 0
            ws = self._ws
            self._ws = None
            if ws is not None:
                self._submit(self._close_connection(ws))
            return
        if self._ws is None:
            self._try_connect()

    def _try_connect(self) -> None:
        if self._closing or self._connecting or self._ws is not None or self._loop is None:
            return
        token = (self._preferences.get_account_token() or "").strip()
        base = (self._preferences.get_sync_api_base_url() or "").strip()
        if not token or not base:
            return
        self._connecting = True
        self._submit(self._connect(token, base))

    async def _connect(self, token: str, base: str) -> None:
        url = ws_url_from_http(base)
        try:
            if self._connect_ws is None:
                import websockets

                ws = await websockets.connect(
                    url,
                    open_timeout=_CONNECT_OPEN_TIMEOUT_S,
                    close_timeout=_CONNECT_CLOSE_TIMEOUT_S,
                )
            else:
                ws = await self._connect_ws(url)
            if self._closing:
                self._connecting = False
                await self._close_connection(ws)
                return
            await ws.send(
                json.dumps(
                    {
                        "type": "auth",
                        "token": token,
                        "api_key": get_configured_sync_api_key(),
                    }
                )
            )
            self._ws = ws
            self._reconnect_attempt = 0
            self._connecting = False
            if self._loop is not None:
                self._track(self._loop.create_task(self._recv_loop(ws)))
            if self._state:
                await self._send_json(
                    {
                        "type": "status",
                        "state": self._state,
                        "experiment_id": self._experiment_id,
                    }
                )
        except asyncio.CancelledError:
            self._connecting = False
            raise
        except Exception:
            self._connecting = False
            self._ws = None
            self.error_occurred.emit("Live stream қатесі: ConnectionError")
            self._schedule_reconnect()

    async def _recv_loop(self, ws) -> None:
        try:
            while True:
                incoming = await ws.recv()
                del incoming
        except asyncio.CancelledError:
            raise
        except Exception:
            if self._ws is ws:
                self._ws = None
                if not self._closing:
                    self._schedule_reconnect()

    async def _send_json(self, payload: dict) -> None:
        ws = self._ws
        if ws is None:
            return
        try:
            await ws.send(json.dumps(payload))
        except asyncio.CancelledError:
            raise
        except Exception:
            if self._ws is ws:
                self._ws = None
                if not self._closing:
                    self._schedule_reconnect()

    async def _close_connection(self, ws) -> None:
        close = getattr(ws, "close", None)
        if close is None:
            return
        result = close()
        if asyncio.iscoroutine(result):
            try:
                await result
            except Exception:
                pass

    def _schedule_reconnect(self) -> None:
        if self._closing:
            return
        delay_s = reconnect_delay_seconds(self._reconnect_attempt)
        self._reconnect_attempt += 1
        if self._reconnect_timer is None:
            self._reconnect_timer = QTimer(self)
            self._reconnect_timer.setSingleShot(True)
            self._reconnect_timer.timeout.connect(self._try_connect)
        self._reconnect_timer.start(delay_s * 1000)

    def _submit(self, coro) -> None:
        loop = self._loop
        if loop is None or loop.is_closed() or self._closing:
            if asyncio.iscoroutine(coro):
                coro.close()
            return
        self._track(loop.create_task(self._run_task(coro)))

    def _track(self, task: asyncio.Task) -> None:
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run_task(self, coro) -> None:
        try:
            await coro
        except asyncio.CancelledError:
            raise
        except Exception:
            if not self._closing:
                self.error_occurred.emit("Live stream қатесі")
