"""Account email auth, role, search, and relationship requests."""

from __future__ import annotations

from server.tests.conftest import _TEST_API_KEY


def _auth(client, email: str, password: str, name: str, role: str | None) -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "display_name": name},
        headers={"X-API-Key": _TEST_API_KEY},
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    headers = {"X-API-Key": _TEST_API_KEY, "Authorization": f"Bearer {token}"}
    if role:
        selected = client.post("/api/v1/auth/select-role", json={"role": role}, headers=headers)
        assert selected.status_code == 200, selected.text
        headers["Authorization"] = f"Bearer {selected.json()['access_token']}"
        return headers, selected.json()
    return headers, response.json()


def test_register_and_login(client) -> None:
    headers, body = _auth(client, "a@school.kz", "secret1", "Айгүл", None)
    assert body["needs_role"] is True
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "a@school.kz", "password": "secret1"},
        headers={"X-API-Key": _TEST_API_KEY},
    )
    assert login.status_code == 200
    me = client.get("/api/v1/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["email"] == "a@school.kz"


def test_duplicate_email_rejected(client) -> None:
    _auth(client, "dup@school.kz", "secret1", "A", None)
    again = client.post(
        "/api/v1/auth/register",
        json={"email": "dup@school.kz", "password": "secret1", "display_name": "B"},
        headers={"X-API-Key": _TEST_API_KEY},
    )
    assert again.status_code == 400


def test_select_role_assigns_public_id(client) -> None:
    headers, body = _auth(client, "t@school.kz", "secret1", "Мұғалім", "teacher")
    assert body["public_id"].startswith("T-")
    me = client.get("/api/v1/me", headers=headers)
    assert me.json()["role"] == "teacher"


def test_teacher_student_request_flow(client) -> None:
    teacher_headers, teacher = _auth(client, "teach@school.kz", "secret1", "Мұғалім", "teacher")
    student_headers, student = _auth(client, "stu@school.kz", "secret1", "Оқушы", "student")
    sent = client.post(
        "/api/v1/requests/teacher-student",
        json={"to_public_id": teacher["public_id"]},
        headers=student_headers,
    )
    assert sent.status_code == 200, sent.text
    incoming = client.get("/api/v1/requests/incoming", headers=teacher_headers)
    assert incoming.status_code == 200
    items = incoming.json()["items"]
    assert len(items) == 1
    accepted = client.post(
        f"/api/v1/requests/{items[0]['id']}/accept",
        headers=teacher_headers,
    )
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "accepted"


def test_student_friend_request(client) -> None:
    a_headers, a = _auth(client, "s1@school.kz", "secret1", "Али", "student")
    _b_headers, b = _auth(client, "s2@school.kz", "secret1", "Болат", "student")
    sent = client.post(
        "/api/v1/requests/friends",
        json={"to_public_id": b["public_id"]},
        headers=a_headers,
    )
    assert sent.status_code == 200, sent.text
    found = client.get("/api/v1/people/search", params={"q": "Болат"}, headers=a_headers)
    assert found.status_code == 200
    assert any(item["public_id"] == b["public_id"] for item in found.json()["results"])


def test_legacy_railway_url_rewrites_to_ab65(monkeypatch) -> None:
    from server.app.api import accounts

    live = "https://arduinophysicslab-production-ab65.up.railway.app"
    monkeypatch.delenv("APL_PUBLIC_BASE_URL", raising=False)
    monkeypatch.delenv("APL_GOOGLE_REDIRECT_URI", raising=False)
    assert accounts._public_base_url() == live
    assert accounts._google_redirect_uri() == f"{live}/api/v1/auth/google/callback"

    monkeypatch.setenv("APL_PUBLIC_BASE_URL", "https://arduinophysicslab-production.up.railway.app")
    monkeypatch.setenv(
        "APL_GOOGLE_REDIRECT_URI",
        "https://arduinophysicslab-production.up.railway.app/api/v1/auth/google/callback",
    )
    assert accounts._public_base_url() == live
    assert accounts._google_redirect_uri() == f"{live}/api/v1/auth/google/callback"


def test_wrong_password(client) -> None:
    _auth(client, "x@school.kz", "secret1", "X", None)
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "x@school.kz", "password": "nope"},
        headers={"X-API-Key": _TEST_API_KEY},
    )
    assert login.status_code == 401
