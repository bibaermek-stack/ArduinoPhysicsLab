"""HTTP client for account / people APIs."""

from __future__ import annotations

from typing import Any

import httpx

from domain.services.sync_auth import get_configured_sync_api_key
from infrastructure.storage.app_preferences import AppPreferences


class AccountApiError(RuntimeError):
    def __init__(self, message: str, status_code: int = 0) -> None:
        super().__init__(message)
        self.status_code = status_code


class AccountApiClient:
    def __init__(self, preferences: AppPreferences | None = None) -> None:
        self._preferences = preferences or AppPreferences()

    def _base(self) -> str:
        return self._preferences.get_sync_api_base_url().rstrip("/")

    def _headers(self, with_bearer: bool = True) -> dict[str, str]:
        headers = {"X-API-Key": get_configured_sync_api_key()}
        token = self._preferences.get_account_token()
        if with_bearer and token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _request(self, method: str, path: str, **kwargs: Any) -> dict:
        url = f"{self._base()}{path}"
        try:
            response = httpx.request(method, url, timeout=15.0, **kwargs)
        except httpx.HTTPError as exc:
            raise AccountApiError("Серверге қосылу мүмкін болмады") from exc
        if response.status_code >= 400:
            detail = ""
            try:
                detail = str(response.json().get("detail") or response.text)
            except Exception:
                detail = response.text
            raise AccountApiError(detail or f"Қате {response.status_code}", response.status_code)
        if not response.content:
            return {}
        return response.json()

    def register(self, email: str, password: str, display_name: str) -> dict:
        return self._request(
            "POST",
            "/api/v1/auth/register",
            headers=self._headers(with_bearer=False),
            json={"email": email, "password": password, "display_name": display_name},
        )

    def login(self, email: str, password: str) -> dict:
        return self._request(
            "POST",
            "/api/v1/auth/login",
            headers=self._headers(with_bearer=False),
            json={"email": email, "password": password},
        )

    def select_role(self, role: str) -> dict:
        return self._request(
            "POST",
            "/api/v1/auth/select-role",
            headers=self._headers(),
            json={"role": role},
        )

    def me(self) -> dict:
        return self._request("GET", "/api/v1/me", headers=self._headers())

    def update_me(self, display_name: str | None = None, photo_base64: str | None = None) -> dict:
        body: dict[str, Any] = {}
        if display_name is not None:
            body["display_name"] = display_name
        if photo_base64 is not None:
            body["photo_base64"] = photo_base64
        return self._request("PATCH", "/api/v1/me", headers=self._headers(), json=body)

    def search(self, query: str) -> list[dict]:
        payload = self._request("GET", "/api/v1/people/search", headers=self._headers(), params={"q": query})
        return list(payload.get("results") or [])

    def search_teachers(self, query: str) -> list[dict]:
        payload = self._request(
            "GET", "/api/v1/teachers/search", headers=self._headers(), params={"query": query}
        )
        return list(payload.get("results") or [])

    def connect_teacher(self, teacher_code: str) -> dict:
        return self._request(
            "POST",
            "/api/v1/student/connect-teacher",
            headers=self._headers(),
            json={"teacher_code": teacher_code},
        )

    def send_teacher_student(self, public_id: str) -> dict:
        return self._request(
            "POST",
            "/api/v1/requests/teacher-student",
            headers=self._headers(),
            json={"to_public_id": public_id},
        )

    def send_friend(self, public_id: str) -> dict:
        return self._request(
            "POST",
            "/api/v1/requests/friends",
            headers=self._headers(),
            json={"to_public_id": public_id},
        )

    def incoming(self) -> list[dict]:
        payload = self._request("GET", "/api/v1/requests/incoming", headers=self._headers())
        return list(payload.get("items") or [])

    def accept(self, request_id: str) -> dict:
        return self._request("POST", f"/api/v1/requests/{request_id}/accept", headers=self._headers())

    def decline(self, request_id: str) -> dict:
        return self._request("POST", f"/api/v1/requests/{request_id}/decline", headers=self._headers())

    def google_start_url(self, desktop_port: int) -> str:
        return f"{self._base()}/api/v1/auth/google/start?desktop_port={desktop_port}"

    def store_session(self, payload: dict, email: str = "") -> None:
        self._preferences.set_account_session(
            token=str(payload.get("access_token") or ""),
            account_id=str(payload.get("account_id") or ""),
            email=email,
            display_name=str(payload.get("display_name") or ""),
            role=str(payload.get("role") or ""),
            public_id=str(payload.get("public_id") or ""),
        )
