"""LiveStreamWorker pure helpers — no real network, no QThread."""

import asyncio
import json
from datetime import datetime, timezone
import os
import sys
import tempfile

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from websockets.exceptions import ConnectionClosed
from websockets.frames import Close

from domain.entities.measurement import Measurement
from infrastructure.storage.app_preferences import AppPreferences
from infrastructure.sync.live_stream_controller import LiveStreamController
from infrastructure.sync.live_stream_worker import (
    LiveStreamWorker,
    build_samples_frame,
    is_auth_failure_close,
    reconnect_delay_seconds,
    ws_url_from_http,
)


@pytest.fixture(scope="module", autouse=True)
def qt_application() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture()
def temp_preferences() -> AppPreferences:
    handle = tempfile.NamedTemporaryFile(suffix=".ini", delete=False)
    handle.close()
    settings = QSettings(handle.name, QSettings.Format.IniFormat)
    yield AppPreferences(settings)
    os.unlink(handle.name)


def _sample() -> Measurement:
    return Measurement(
        timestamp=datetime(2026, 9, 4, 12, tzinfo=timezone.utc),
        values={"voltage": 1.2},
        experiment_id="ohms-law",
        derived_values={"current": 0.01},
    )


def test_ws_url_from_http() -> None:
    assert ws_url_from_http("https://example.com") == "wss://example.com/api/v1/live/ws"
    assert ws_url_from_http("http://127.0.0.1:8000/") == "ws://127.0.0.1:8000/api/v1/live/ws"


def test_build_samples_frame_uses_all_values() -> None:
    m = Measurement(
        timestamp=datetime(2026, 9, 4, 12, tzinfo=timezone.utc),
        values={"voltage": 1.2},
        experiment_id="ohms-law",
        derived_values={"current": 0.01},
    )
    frame = build_samples_frame("ohms-law", "sess", [m])
    assert frame["type"] == "samples"
    assert frame["points"][0]["values"]["voltage"] == 1.2
    assert frame["points"][0]["values"]["current"] == 0.01


def test_enqueue_then_drain_queue_uses_all_values(temp_preferences) -> None:
    worker = LiveStreamWorker(temp_preferences)
    worker.enqueue_measurement(_sample(), "sess")
    frame = worker._drain_queue()
    assert frame is not None
    assert frame["type"] == "samples"
    assert frame["experiment_id"] == "ohms-law"
    assert frame["session_id"] == "sess"
    assert frame["points"][0]["values"]["voltage"] == 1.2
    assert frame["points"][0]["values"]["current"] == 0.01
    assert worker._drain_queue() is None


def test_constructor_does_not_open_websocket(temp_preferences) -> None:
    calls: list[str] = []

    async def fake_connect(url: str):
        calls.append(url)
        raise AssertionError("constructor must not connect")

    LiveStreamWorker(temp_preferences, connect_ws=fake_connect)
    assert calls == []


def test_enqueue_drops_when_queue_exceeds_500(temp_preferences) -> None:
    worker = LiveStreamWorker(temp_preferences)
    sample = _sample()
    for _ in range(501):
        worker.enqueue_measurement(sample, "sess")
    drained = 0
    while True:
        frame = worker._drain_queue()
        if frame is None:
            break
        drained += len(frame["points"])
    assert drained == 500


def test_flush_without_socket_keeps_queued_samples(temp_preferences) -> None:
    worker = LiveStreamWorker(temp_preferences)
    worker.enqueue_measurement(_sample(), "sess")
    worker.flush()
    frame = worker._drain_queue()
    assert frame is not None
    assert frame["points"][0]["values"]["voltage"] == 1.2


def test_reconnect_delay_seconds_caps_at_10() -> None:
    assert reconnect_delay_seconds(0) == 1
    assert reconnect_delay_seconds(1) == 2
    assert reconnect_delay_seconds(2) == 5
    assert reconnect_delay_seconds(3) == 10
    assert reconnect_delay_seconds(99) == 10


def test_controller_construct_does_not_start_thread(temp_preferences) -> None:
    controller = LiveStreamController(temp_preferences)
    assert controller.is_running() is False


def test_flush_does_not_connect_while_reconnect_backoff_active(temp_preferences) -> None:
    temp_preferences.set_account_session(
        token="tok",
        account_id="a1",
        email="s@school.kz",
        display_name="S",
        role="student",
        public_id="S-1",
    )
    temp_preferences.set_sync_api_base_url("http://127.0.0.1:8000")
    calls: list[str] = []

    async def fake_connect(url: str):
        calls.append(url)
        raise OSError("offline")

    worker = LiveStreamWorker(temp_preferences, connect_ws=fake_connect)
    loop = asyncio.new_event_loop()
    worker._loop = loop
    try:
        worker._schedule_reconnect()
        assert worker._reconnect_timer is not None
        assert worker._reconnect_timer.isActive()
        worker.flush()
        worker._ensure_connection_state()
        worker._pump_loop()
        assert worker._reconnect_timer.isActive()
        assert worker._connecting is False
        assert calls == []
    finally:
        if worker._reconnect_timer is not None:
            worker._reconnect_timer.stop()
        worker._loop = None
        loop.close()


def _logged_in(preferences: AppPreferences) -> None:
    preferences.set_account_session(
        token="tok",
        account_id="a1",
        email="s@school.kz",
        display_name="S",
        role="student",
        public_id="S-1",
    )
    preferences.set_sync_api_base_url("http://127.0.0.1:8000")


def _closed(code: int) -> ConnectionClosed:
    return ConnectionClosed(Close(code, ""), None)


class _FakeLiveSocket:
    def __init__(self, incoming: list[object]) -> None:
        self.sent: list[str] = []
        self._incoming = list(incoming)
        self._hang: asyncio.Future | None = None

    async def send(self, data: str) -> None:
        self.sent.append(data)

    async def recv(self):
        if self._incoming:
            item = self._incoming.pop(0)
            if isinstance(item, BaseException):
                raise item
            return item
        loop = asyncio.get_running_loop()
        self._hang = loop.create_future()
        return await self._hang

    async def close(self) -> None:
        if self._hang is not None and not self._hang.done():
            self._hang.cancel()


def _run_connect(worker: LiveStreamWorker, loop: asyncio.AbstractEventLoop) -> None:
    loop.run_until_complete(worker._connect("tok", "http://127.0.0.1:8000"))


def _cleanup_worker(worker: LiveStreamWorker, loop: asyncio.AbstractEventLoop) -> None:
    worker._closing = True
    if worker._reconnect_timer is not None:
        worker._reconnect_timer.stop()

    async def _cancel() -> None:
        pending = list(worker._tasks)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

    try:
        if not loop.is_closed():
            loop.run_until_complete(_cancel())
    finally:
        worker._loop = None
        worker._ws = None
        if not loop.is_closed():
            loop.close()


def test_connect_waits_for_hello_before_resetting_reconnect(temp_preferences) -> None:
    _logged_in(temp_preferences)
    hello_gate = asyncio.Event()

    class _HelloGateSocket(_FakeLiveSocket):
        def __init__(self) -> None:
            super().__init__([])
            self._hello_sent = False

        async def recv(self):
            if not self._hello_sent:
                await hello_gate.wait()
                self._hello_sent = True
                return json.dumps({"type": "hello", "role": "student"})
            return await super().recv()

    fake = _HelloGateSocket()

    async def fake_connect(url: str):
        return fake

    worker = LiveStreamWorker(temp_preferences, connect_ws=fake_connect)
    worker._reconnect_attempt = 4
    loop = asyncio.new_event_loop()
    worker._loop = loop
    try:
        async def scenario():
            task = asyncio.create_task(worker._connect("tok", "http://127.0.0.1:8000"))
            for _ in range(30):
                await asyncio.sleep(0)
                if fake.sent:
                    break
            assert fake.sent, "auth frame should be sent before hello"
            assert json.loads(fake.sent[0])["type"] == "auth"
            assert worker._ws is None
            assert worker._reconnect_attempt == 4
            hello_gate.set()
            await task
            assert worker._ws is fake
            assert worker._reconnect_attempt == 0

        loop.run_until_complete(scenario())
    finally:
        _cleanup_worker(worker, loop)


def test_connect_does_not_reconnect_on_4401(temp_preferences) -> None:
    _logged_in(temp_preferences)
    calls: list[str] = []
    fake = _FakeLiveSocket([_closed(4401)])

    async def fake_connect(url: str):
        calls.append(url)
        return fake

    worker = LiveStreamWorker(temp_preferences, connect_ws=fake_connect)
    worker._reconnect_attempt = 2
    loop = asyncio.new_event_loop()
    worker._loop = loop
    try:
        _run_connect(worker, loop)
        assert worker._ws is None
        assert worker._closed_for_good is True
        assert worker._reconnect_attempt == 2
        assert worker._reconnect_timer is None or not worker._reconnect_timer.isActive()
        worker._ensure_connection_state()
        worker.flush()
        worker._pump_loop()
        assert calls == ["ws://127.0.0.1:8000/api/v1/live/ws"]
        assert is_auth_failure_close(_closed(4401)) is True
    finally:
        _cleanup_worker(worker, loop)


def test_connect_does_not_reconnect_on_4403(temp_preferences) -> None:
    _logged_in(temp_preferences)
    calls: list[str] = []
    fake = _FakeLiveSocket([_closed(4403)])

    async def fake_connect(url: str):
        calls.append(url)
        return fake

    worker = LiveStreamWorker(temp_preferences, connect_ws=fake_connect)
    loop = asyncio.new_event_loop()
    worker._loop = loop
    try:
        _run_connect(worker, loop)
        assert worker._ws is None
        assert worker._closed_for_good is True
        worker._ensure_connection_state()
        worker._pump_loop()
        assert len(calls) == 1
        assert is_auth_failure_close(_closed(4403)) is True
    finally:
        _cleanup_worker(worker, loop)


def test_recv_loop_does_not_reconnect_on_4401_after_hello(temp_preferences) -> None:
    _logged_in(temp_preferences)
    fake = _FakeLiveSocket(
        [
            json.dumps({"type": "hello", "role": "student"}),
            _closed(4401),
        ]
    )

    async def fake_connect(url: str):
        return fake

    worker = LiveStreamWorker(temp_preferences, connect_ws=fake_connect)
    worker._state = ""
    worker._reconnect_attempt = 3
    loop = asyncio.new_event_loop()
    worker._loop = loop
    try:
        _run_connect(worker, loop)
        worker._pump_loop()
        assert worker._reconnect_attempt == 0
        assert worker._ws is None
        assert worker._closed_for_good is True
        assert worker._reconnect_timer is None or not worker._reconnect_timer.isActive()
    finally:
        _cleanup_worker(worker, loop)


def test_connect_still_reconnects_on_non_auth_close(temp_preferences) -> None:
    _logged_in(temp_preferences)
    fake = _FakeLiveSocket([_closed(1006)])

    async def fake_connect(url: str):
        return fake

    worker = LiveStreamWorker(temp_preferences, connect_ws=fake_connect)
    loop = asyncio.new_event_loop()
    worker._loop = loop
    try:
        _run_connect(worker, loop)
        assert worker._ws is None
        assert worker._closed_for_good is False
        assert worker._reconnect_timer is not None
        assert worker._reconnect_timer.isActive()
        assert is_auth_failure_close(_closed(1006)) is False
    finally:
        _cleanup_worker(worker, loop)
