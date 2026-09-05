"""LiveStreamWorker pure helpers — no real network, no QThread."""

from datetime import datetime, timezone
import os
import sys
import tempfile

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from domain.entities.measurement import Measurement
from infrastructure.storage.app_preferences import AppPreferences
from infrastructure.sync.live_stream_controller import LiveStreamController
from infrastructure.sync.live_stream_worker import (
    LiveStreamWorker,
    build_samples_frame,
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
