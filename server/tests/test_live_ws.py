from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from server.app.api import live
from server.app.db.session import get_db
from server.app.main import app
from server.tests.conftest import _TEST_API_KEY
from server.tests.test_accounts_people import _auth


@pytest.fixture(autouse=True)
def _reset_live_hub() -> None:
    live.hub.reset()
    live._publisher_sockets.clear()
    yield
    live.hub.reset()
    live._publisher_sockets.clear()


@contextmanager
def _cookie_free_client() -> Iterator[TestClient]:
    with TestClient(app) as extra:
        yield extra


def _assert_close(exc: BaseException, code: int) -> None:
    if getattr(exc, "code", None) is not None:
        assert exc.code == code
    assert (
        str(code) in str(exc)
        or "1008" in str(exc)
        or "401" in str(exc)
        or "403" in str(exc)
        or exc.__class__.__name__ == "WebSocketDisconnect"
    )


def test_ws_rejects_missing_auth(client) -> None:
    try:
        with client.websocket_connect("/api/v1/live/ws") as ws:
            ws.send_json({"type": "ping"})
            ws.receive_json()
        raise AssertionError("expected close")
    except Exception as exc:
        _assert_close(exc, 4401)


def test_ws_rejects_garbage_cookie(client) -> None:
    client.cookies.set("apl_web_token", "not-a-jwt")
    try:
        with client.websocket_connect("/api/v1/live/ws") as ws:
            ws.receive_json()
        raise AssertionError("expected close")
    except Exception as exc:
        _assert_close(exc, 4401)


def test_ws_rejects_desktop_garbage_jwt(client) -> None:
    try:
        with _cookie_free_client() as desktop_http:
            with desktop_http.websocket_connect("/api/v1/live/ws") as ws:
                ws.send_json({"type": "auth", "token": "not-a-jwt", "api_key": _TEST_API_KEY})
                ws.receive_json()
        raise AssertionError("expected close")
    except Exception as exc:
        _assert_close(exc, 4401)


def test_ws_rejects_empty_role_cookie(client) -> None:
    headers, _body = _auth(client, "live-norole@school.kz", "secret1", "X", None)
    token = headers["Authorization"].split(" ", 1)[1]
    client.cookies.set("apl_web_token", token)
    try:
        with client.websocket_connect("/api/v1/live/ws") as ws:
            ws.receive_json()
        raise AssertionError("expected close")
    except Exception as exc:
        _assert_close(exc, 4403)


def test_desktop_samples_reach_student_cookie_viewer(client) -> None:
    student_headers, student = _auth(client, "live-s@school.kz", "secret1", "Оқушы", "student")
    token = student_headers["Authorization"].split(" ", 1)[1]
    client.cookies.set("apl_web_token", token)
    with _cookie_free_client() as desktop_http:
        with client.websocket_connect("/api/v1/live/ws") as viewer:
            hello = viewer.receive_json()
            assert hello["type"] == "hello"
            assert hello["role"] == "student"
            with desktop_http.websocket_connect("/api/v1/live/ws") as desktop:
                desktop.send_json({"type": "auth", "token": token, "api_key": _TEST_API_KEY})
                desk_hello = desktop.receive_json()
                assert desk_hello["type"] == "hello"
                desktop.send_json({
                    "type": "samples",
                    "experiment_id": "ohms-law",
                    "session_id": "sess-1",
                    "points": [{"t": "2026-09-04T12:00:00Z", "values": {"voltage": 1.5}}],
                })
            frame = viewer.receive_json()
            while frame.get("type") == "presence":
                frame = viewer.receive_json()
            assert frame["type"] == "samples"
            assert frame["points"][0]["values"]["voltage"] == 1.5


def test_other_student_does_not_receive_samples(client) -> None:
    a_headers, _a = _auth(client, "live-a@school.kz", "secret1", "A", "student")
    b_headers, _b = _auth(client, "live-b@school.kz", "secret1", "B", "student")
    token_a = a_headers["Authorization"].split(" ", 1)[1]
    token_b = b_headers["Authorization"].split(" ", 1)[1]
    client.cookies.set("apl_web_token", token_b)
    with _cookie_free_client() as desktop_http:
        with client.websocket_connect("/api/v1/live/ws") as viewer_b:
            viewer_b.receive_json()  # hello
            with desktop_http.websocket_connect("/api/v1/live/ws") as desktop_a:
                desktop_a.send_json({"type": "auth", "token": token_a, "api_key": _TEST_API_KEY})
                desktop_a.receive_json()
                desktop_a.send_json({
                    "type": "samples",
                    "experiment_id": "ohms-law",
                    "session_id": "sess-1",
                    "points": [{"t": "2026-09-04T12:00:00Z", "values": {"voltage": 9.9}}],
                })
            viewer_b.send_json({"type": "ping"})
            pong = viewer_b.receive_json()
            assert pong["type"] == "pong"


def test_cookie_viewer_ignores_auth_and_does_not_publish(client) -> None:
    headers, body = _auth(client, "live-view@school.kz", "secret1", "Оқушы", "student")
    token = headers["Authorization"].split(" ", 1)[1]
    account_id = body["account_id"]
    client.cookies.set("apl_web_token", token)
    with client.websocket_connect("/api/v1/live/ws") as viewer:
        hello = viewer.receive_json()
        assert hello["type"] == "hello"
        viewer.send_json({"type": "auth", "token": token, "api_key": _TEST_API_KEY})
        viewer.send_json({
            "type": "samples",
            "experiment_id": "ohms-law",
            "session_id": "sess-1",
            "points": [{"t": "2026-09-04T12:00:00Z", "values": {"voltage": 1.5}}],
        })
        viewer.send_json({"type": "ping"})
        pong = viewer.receive_json()
        assert pong["type"] == "pong"
        assert live.hub.publisher_state(account_id) == "offline"


def test_ws_closes_db_session_after_handshake(client, db_session_factory) -> None:
    headers, _body = _auth(client, "live-db@school.kz", "secret1", "Оқушы", "student")
    token = headers["Authorization"].split(" ", 1)[1]
    closed_at: list[str] = []

    def _override_get_db():
        db = db_session_factory()
        original_close = db.close

        def tracking_close() -> None:
            closed_at.append("closed")
            original_close()

        db.close = tracking_close  # type: ignore[method-assign]
        try:
            yield db
        finally:
            original_close()

    app.dependency_overrides[get_db] = _override_get_db
    closed_at.clear()
    with _cookie_free_client() as desktop_http:
        with desktop_http.websocket_connect("/api/v1/live/ws") as desktop:
            desktop.send_json({"type": "auth", "token": token, "api_key": _TEST_API_KEY})
            hello = desktop.receive_json()
            assert hello["type"] == "hello"
            assert closed_at, "db session must be closed before the receive loop"
            desktop.send_json({"type": "ping"})
            assert desktop.receive_json()["type"] == "pong"


def test_new_desktop_publisher_disconnects_previous(client) -> None:
    headers, body = _auth(client, "live-dup@school.kz", "secret1", "Оқушы", "student")
    token = headers["Authorization"].split(" ", 1)[1]
    account_id = body["account_id"]
    with _cookie_free_client() as desktop_http:
        with desktop_http.websocket_connect("/api/v1/live/ws") as old:
            old.send_json({"type": "auth", "token": token, "api_key": _TEST_API_KEY})
            assert old.receive_json()["type"] == "hello"
            with desktop_http.websocket_connect("/api/v1/live/ws") as new:
                new.send_json({"type": "auth", "token": token, "api_key": _TEST_API_KEY})
                assert new.receive_json()["type"] == "hello"
                try:
                    old.receive_json()
                    raise AssertionError("expected previous desktop websocket to close")
                except Exception as exc:
                    assert exc.__class__.__name__ != "AssertionError"
                new.send_json({"type": "status", "state": "measuring", "experiment_id": "ohms-law"})
                new.send_json({"type": "ping"})
                assert new.receive_json()["type"] == "pong"
                assert live.hub.publisher_state(account_id) == "measuring"
