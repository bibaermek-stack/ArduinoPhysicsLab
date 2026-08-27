"""HttpSyncApiClient — ``ISyncApiClient``-дің ``httpx`` қолданатын
іске асыруы (Offline-First + Cloud Sync Foundation фазасы).

``httpx`` жобада ӘЛДЕҚАШАН бар тәуелділік (§ audit — ``requests`` жаңа
тәуелділік ретінде ҚОСЫЛМАДЫ, ``httpx.Client`` синхронды режимде
дәл СОЛ рөлді атқарады).

§13 "Connectivity Service": ``check_health()`` ҚЫСҚА timeout қолданады
және ЕШБІР exception сыртқа шығармайды — желі/сервер қатесі жай ғана
``False`` дегенді білдіреді.

``client`` параметрі ЕРІКТІ — берілмесе, нақты желі арқылы сұрайтын
``httpx.Client()`` қолданылады. Тесттер/§21 "First Proof of Concept"
``httpx.Client(transport=httpx.ASGITransport(app=fastapi_app))`` беруі
мүмкін — НАҚТЫ HTTP семантикасымен, БІРАҚ нақты socket/бөлек процесс
ЖОҚ (§ "Use isolated test databases, not the user's real production
DB" рухымен БІРДЕЙ, тек HTTP қабаты үшін).
"""

from __future__ import annotations

from datetime import datetime

import httpx

from domain.interfaces.i_sync_api_client import (
    AuthResult,
    ISyncApiClient,
    PullResult,
    PushItemResult,
    SyncAuthenticationError,
    SyncAuthorizationError,
)

_HEALTH_TIMEOUT_SECONDS = 2.0
_LOGIN_TIMEOUT_SECONDS = 5.0


class HttpSyncApiClient(ISyncApiClient):
    def __init__(
        self,
        base_url: str,
        api_key: str,
        request_timeout: float = 5.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._request_timeout = request_timeout
        self._client = client
        # § Phase 3: логиннен кейін орнатылады, ``push()``/``pull()``
        # шақыруларына ``Authorization: Bearer`` ретінде тіркеледі.
        self._auth_token: str | None = None

    def _http(self) -> httpx.Client:
        return self._client if self._client is not None else httpx

    def _headers(self) -> dict[str, str]:
        headers = {"X-API-Key": self._api_key}
        if self._auth_token is not None:
            headers["Authorization"] = f"Bearer {self._auth_token}"
        return headers

    def check_health(self) -> bool:
        try:
            response = self._http().get(f"{self._base_url}/api/v1/health", timeout=_HEALTH_TIMEOUT_SECONDS)
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    def set_auth_token(self, token: str | None) -> None:
        self._auth_token = token

    def login_as_teacher(self, sync_id: str, pin_hash: str) -> AuthResult | None:
        return self._login(
            "/api/v1/auth/teacher-login", {"sync_id": sync_id, "pin_hash": pin_hash}
        )

    def login_as_student(self, sync_id: str, student_code: str) -> AuthResult | None:
        return self._login(
            "/api/v1/auth/student-login", {"sync_id": sync_id, "student_code": student_code}
        )

    def _login(self, path: str, body: dict) -> AuthResult | None:
        response = self._http().post(
            f"{self._base_url}{path}",
            json=body,
            headers={"X-API-Key": self._api_key},
            timeout=_LOGIN_TIMEOUT_SECONDS,
        )
        if response.status_code == 401:
            return None
        response.raise_for_status()
        payload = response.json()
        return AuthResult(
            token=payload["access_token"],
            expires_at=datetime.fromisoformat(payload["expires_at"]),
            sync_id=payload["sync_id"],
            role=payload["role"],
        )

    def push(self, entity_type: str, payloads: list[dict]) -> list[PushItemResult]:
        endpoint = f"{self._base_url}/api/v1/sync/{_route_segment(entity_type)}"
        response = self._http().post(
            endpoint,
            json=payloads,
            headers=self._headers(),
            timeout=self._request_timeout,
        )
        _raise_for_auth_errors(response)
        response.raise_for_status()
        body = response.json()
        return [
            PushItemResult(
                sync_id=item["sync_id"],
                status=item["status"],
                server_revision=item.get("server_revision"),
                error=item.get("error") or "",
            )
            for item in body["results"]
        ]

    def pull(self, entity_type: str, updated_since: datetime | None, limit: int) -> PullResult:
        endpoint = f"{self._base_url}/api/v1/sync/{_route_segment(entity_type)}"
        params: dict[str, str | int] = {"limit": limit}
        if updated_since is not None:
            params["updated_since"] = updated_since.isoformat()
        response = self._http().get(
            endpoint,
            params=params,
            headers=self._headers(),
            timeout=self._request_timeout,
        )
        _raise_for_auth_errors(response)
        response.raise_for_status()
        body = response.json()
        return PullResult(items=tuple(body["items"]), server_time=datetime.fromisoformat(body["server_time"]))


def _raise_for_auth_errors(response: httpx.Response) -> None:
    """§8: 401/403-ты жалпы HTTP қатеден ерекшелейді (§ ``SyncEngine``
    осыларды нақты өңдейді — қалыпты желі-қатесі backoff-ымен ЕМЕС)."""
    if response.status_code == 401:
        raise SyncAuthenticationError(response.text)
    if response.status_code == 403:
        raise SyncAuthorizationError(response.text)


_CUSTOM_ROUTE_SEGMENTS: dict[str, str] = {
    "teacher_classroom": "teacher-classrooms",
    "session_student_link": "session-students",
    "feedback_result": "feedback-results",
    "teacher_assessment": "teacher-assessments",
    "measurement_batch": "measurement-batches",
    "teacher_note": "teacher-notes",
}


def _route_segment(entity_type: str) -> str:
    """§9 "API Contract": ``teacher`` -> ``teachers`` (әдепкі, ``+ "s"``),
    ал жалғыз-сөзге сыймайтын entity_type-тар үшін нақты сервер route
    атаулары (§ server/app/api/sync.py)."""
    return _CUSTOM_ROUTE_SEGMENTS.get(entity_type, entity_type + "s")
