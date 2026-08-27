"""infrastructure/sync/http_sync_api_client.py тесттері — нақты желі
ЖОҚ, тек ``httpx.Client``-тің public пішінін имитациялайтын жалған
объект (§13 "Connectivity Service": қысқа timeout, ешбір exception
сыртқа шықпайды)."""

from datetime import datetime, timezone

import httpx
import pytest

from domain.interfaces.i_sync_api_client import SyncAuthenticationError, SyncAuthorizationError
from infrastructure.sync.http_sync_api_client import HttpSyncApiClient


class _FakeResponse:
    def __init__(self, status_code: int, json_body: dict | None = None) -> None:
        self.status_code = status_code
        self._json_body = json_body or {}
        self.text = str(json_body or {})

    def json(self) -> dict:
        return self._json_body

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=self)


class _FakeHttpxClient:
    """``httpx.Client``-тің ЕКІ әдісін ғана (``get``/``post``) имитациялайды —
    нақты сокет ЕШҚАШАН ашылмайды."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict]] = []
        self._get_response: _FakeResponse | Exception = _FakeResponse(200)
        self._post_response: _FakeResponse | Exception = _FakeResponse(200, {"results": []})

    def set_get_response(self, response) -> None:
        self._get_response = response

    def set_post_response(self, response) -> None:
        self._post_response = response

    def get(self, url: str, params: dict | None = None, headers: dict | None = None, timeout: float = 5.0):
        self.calls.append(("GET", url, {"params": params, "headers": headers}))
        if isinstance(self._get_response, Exception):
            raise self._get_response
        return self._get_response

    def post(self, url: str, json=None, headers: dict | None = None, timeout: float = 5.0):
        self.calls.append(("POST", url, {"json": json, "headers": headers}))
        if isinstance(self._post_response, Exception):
            raise self._post_response
        return self._post_response


def test_check_health_returns_true_on_200() -> None:
    fake_client = _FakeHttpxClient()
    client = HttpSyncApiClient(base_url="http://127.0.0.1:8000", api_key="k", client=fake_client)

    assert client.check_health() is True


def test_check_health_returns_false_when_server_unreachable() -> None:
    """§13: желі қатесі ЕШҚАШАН exception ретінде сыртқа шықпайды."""
    fake_client = _FakeHttpxClient()
    fake_client.set_get_response(httpx.ConnectError("connection refused"))
    client = HttpSyncApiClient(base_url="http://127.0.0.1:8000", api_key="k", client=fake_client)

    assert client.check_health() is False


def test_check_health_hits_versioned_health_endpoint() -> None:
    fake_client = _FakeHttpxClient()
    client = HttpSyncApiClient(base_url="http://127.0.0.1:8000", api_key="k", client=fake_client)

    client.check_health()

    method, url, _ = fake_client.calls[0]
    assert method == "GET"
    assert url == "http://127.0.0.1:8000/api/v1/health"


def test_push_sends_api_key_header_and_returns_parsed_results() -> None:
    fake_client = _FakeHttpxClient()
    fake_client.set_post_response(
        _FakeResponse(
            200,
            {"results": [{"sync_id": "c1", "status": "upserted", "server_revision": 3, "error": None}]},
        )
    )
    client = HttpSyncApiClient(base_url="http://127.0.0.1:8000", api_key="secret-key", client=fake_client)

    results = client.push("classroom", [{"sync_id": "c1", "name": "8А"}])

    assert results[0].sync_id == "c1"
    assert results[0].status == "upserted"
    assert results[0].server_revision == 3
    method, url, kwargs = fake_client.calls[0]
    assert method == "POST"
    assert url == "http://127.0.0.1:8000/api/v1/sync/classrooms"
    assert kwargs["headers"]["X-API-Key"] == "secret-key"


def test_push_uses_hyphenated_route_for_teacher_classroom() -> None:
    fake_client = _FakeHttpxClient()
    client = HttpSyncApiClient(base_url="http://127.0.0.1:8000", api_key="k", client=fake_client)

    client.push("teacher_classroom", [])

    _, url, _ = fake_client.calls[0]
    assert url == "http://127.0.0.1:8000/api/v1/sync/teacher-classrooms"


def test_push_uses_hyphenated_route_for_teacher_note() -> None:
    """§ Phase 7 — default fallback ``entity_type + "s"`` would give
    ``teacher_notes`` (underscore), not the established hyphenated
    convention used by every other multi-word entity_type; confirms
    the custom ``_CUSTOM_ROUTE_SEGMENTS`` entry is actually applied."""
    fake_client = _FakeHttpxClient()
    client = HttpSyncApiClient(base_url="http://127.0.0.1:8000", api_key="k", client=fake_client)

    client.push("teacher_note", [])

    _, url, _ = fake_client.calls[0]
    assert url == "http://127.0.0.1:8000/api/v1/sync/teacher-notes"


def test_push_raises_on_http_error_status() -> None:
    fake_client = _FakeHttpxClient()
    fake_client.set_post_response(_FakeResponse(500))
    client = HttpSyncApiClient(base_url="http://127.0.0.1:8000", api_key="k", client=fake_client)

    with pytest.raises(httpx.HTTPStatusError):
        client.push("classroom", [{"sync_id": "c1"}])


def test_pull_sends_updated_since_param_when_cursor_given() -> None:
    fake_client = _FakeHttpxClient()
    fake_client.set_get_response(
        _FakeResponse(200, {"items": [], "server_time": "2026-01-01T00:00:00+00:00"})
    )
    client = HttpSyncApiClient(base_url="http://127.0.0.1:8000", api_key="k", client=fake_client)
    cursor = datetime(2025, 12, 1, tzinfo=timezone.utc)

    result = client.pull("classroom", cursor, limit=500)

    assert result.items == ()
    assert result.server_time == datetime(2026, 1, 1, tzinfo=timezone.utc)
    _, _, kwargs = fake_client.calls[0]
    assert kwargs["params"]["updated_since"] == cursor.isoformat()


def test_pull_omits_updated_since_param_when_no_cursor() -> None:
    fake_client = _FakeHttpxClient()
    fake_client.set_get_response(
        _FakeResponse(200, {"items": [], "server_time": "2026-01-01T00:00:00+00:00"})
    )
    client = HttpSyncApiClient(base_url="http://127.0.0.1:8000", api_key="k", client=fake_client)

    client.pull("classroom", None, limit=500)

    _, _, kwargs = fake_client.calls[0]
    assert "updated_since" not in kwargs["params"]


# ---- Phase 3 (Production Authentication + Authorization) -------------------


def test_login_as_teacher_sends_pin_hash_not_raw_pin() -> None:
    """§2 "Do NOT send plaintext PINs/access codes in sync payloads"."""
    fake_client = _FakeHttpxClient()
    fake_client.set_post_response(
        _FakeResponse(
            200,
            {"access_token": "tok-123", "token_type": "bearer", "role": "teacher",
             "sync_id": "t1", "expires_at": "2026-01-01T01:00:00+00:00"},
        )
    )
    client = HttpSyncApiClient(base_url="http://127.0.0.1:8000", api_key="k", client=fake_client)

    result = client.login_as_teacher("t1", "sha256-hash-value")

    assert result is not None
    assert result.token == "tok-123"
    assert result.role == "teacher"
    assert result.sync_id == "t1"
    method, url, kwargs = fake_client.calls[0]
    assert url == "http://127.0.0.1:8000/api/v1/auth/teacher-login"
    assert kwargs["json"] == {"sync_id": "t1", "pin_hash": "sha256-hash-value"}


def test_login_as_student_returns_none_on_401() -> None:
    fake_client = _FakeHttpxClient()
    fake_client.set_post_response(_FakeResponse(401))
    client = HttpSyncApiClient(base_url="http://127.0.0.1:8000", api_key="k", client=fake_client)

    result = client.login_as_student("s1", "wrong-code")

    assert result is None


def test_set_auth_token_attaches_bearer_header_to_push() -> None:
    """§21 "token is attached by HttpSyncApiClient"."""
    fake_client = _FakeHttpxClient()
    fake_client.set_post_response(_FakeResponse(200, {"results": []}))
    client = HttpSyncApiClient(base_url="http://127.0.0.1:8000", api_key="k", client=fake_client)

    client.set_auth_token("my-jwt-token")
    client.push("classroom", [])

    _, _, kwargs = fake_client.calls[0]
    assert kwargs["headers"]["Authorization"] == "Bearer my-jwt-token"
    assert kwargs["headers"]["X-API-Key"] == "k"  # § "defense in depth" — екеуі де БІРГЕ


def test_set_auth_token_attaches_bearer_header_to_pull() -> None:
    fake_client = _FakeHttpxClient()
    fake_client.set_get_response(_FakeResponse(200, {"items": [], "server_time": "2026-01-01T00:00:00+00:00"}))
    client = HttpSyncApiClient(base_url="http://127.0.0.1:8000", api_key="k", client=fake_client)

    client.set_auth_token("my-jwt-token")
    client.pull("classroom", None, limit=500)

    _, _, kwargs = fake_client.calls[0]
    assert kwargs["headers"]["Authorization"] == "Bearer my-jwt-token"


def test_no_authorization_header_before_set_auth_token_called() -> None:
    fake_client = _FakeHttpxClient()
    fake_client.set_post_response(_FakeResponse(200, {"results": []}))
    client = HttpSyncApiClient(base_url="http://127.0.0.1:8000", api_key="k", client=fake_client)

    client.push("classroom", [])

    _, _, kwargs = fake_client.calls[0]
    assert "Authorization" not in kwargs["headers"]


def test_push_raises_authentication_error_on_401() -> None:
    """§8 "401 behavior" — ерекшеленген exception түрі (жалпы HTTP
    қатеден бөлек, § ``SyncEngine`` осыны нақты өңдейді)."""
    fake_client = _FakeHttpxClient()
    fake_client.set_post_response(_FakeResponse(401))
    client = HttpSyncApiClient(base_url="http://127.0.0.1:8000", api_key="k", client=fake_client)

    with pytest.raises(SyncAuthenticationError):
        client.push("classroom", [{"sync_id": "c1"}])


def test_push_raises_authorization_error_on_403() -> None:
    """§8 "403 behavior"."""
    fake_client = _FakeHttpxClient()
    fake_client.set_post_response(_FakeResponse(403))
    client = HttpSyncApiClient(base_url="http://127.0.0.1:8000", api_key="k", client=fake_client)

    with pytest.raises(SyncAuthorizationError):
        client.push("classroom", [{"sync_id": "c1"}])


def test_pull_raises_authentication_error_on_401() -> None:
    fake_client = _FakeHttpxClient()
    fake_client.set_get_response(_FakeResponse(401))
    client = HttpSyncApiClient(base_url="http://127.0.0.1:8000", api_key="k", client=fake_client)

    with pytest.raises(SyncAuthenticationError):
        client.pull("classroom", None, limit=500)
