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
    assert me.json()["invite_code"] == body["public_id"]


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
    assert accounts._google_redirect_uri() == live

    monkeypatch.setenv("APL_PUBLIC_BASE_URL", "https://arduinophysicslab-production.up.railway.app")
    monkeypatch.setenv(
        "APL_GOOGLE_REDIRECT_URI",
        "https://arduinophysicslab-production.up.railway.app",
    )
    assert accounts._public_base_url() == live
    assert accounts._google_redirect_uri() == live


def test_student_register_is_independent_until_teacher_accepts(client) -> None:
    registered = client.post(
        "/api/v1/auth/student/register",
        json={"email": "solo@school.kz", "password": "secret1", "display_name": "Дербес"},
        headers={"X-API-Key": _TEST_API_KEY},
    )
    assert registered.status_code == 200, registered.text
    assert registered.json()["role"] == "student"
    assert registered.json()["public_id"].startswith("S-")
    headers = {
        "X-API-Key": _TEST_API_KEY,
        "Authorization": f"Bearer {registered.json()['access_token']}",
    }
    me = client.get("/api/v1/me", headers=headers)
    assert me.json()["link_status"] == "independent"
    assert me.json()["teacher"] is None


def test_connect_teacher_by_code_then_accept(client, db_session_factory) -> None:
    import json

    from server.app.models.account_models import AccountRecord
    from server.app.models.sync_models import StudentRecord, TeacherClassroomLinkRecord

    teacher_headers, teacher = _auth(client, "lab@school.kz", "secret1", "Асқар Серікұлы", "teacher")
    student_headers, _student = _auth(client, "kid@school.kz", "secret1", "Оқушы", "student")

    found = client.get(
        "/api/v1/teachers/search",
        params={"query": "Асқар"},
        headers=student_headers,
    )
    assert found.status_code == 200
    assert any(item["public_id"] == teacher["public_id"] for item in found.json()["results"])

    sent = client.post(
        "/api/v1/student/connect-teacher",
        json={"teacher_id": teacher["public_id"]},
        headers=student_headers,
    )
    assert sent.status_code == 200, sent.text
    assert sent.json()["status"] == "pending"

    pending_me = client.get("/api/v1/me", headers=student_headers)
    assert pending_me.json()["link_status"] == "pending"

    incoming = client.get("/api/v1/requests/incoming", headers=teacher_headers)
    request_id = incoming.json()["items"][0]["id"]
    accepted = client.post(f"/api/v1/requests/{request_id}/accept", headers=teacher_headers)
    assert accepted.status_code == 200

    linked = client.get("/api/v1/me", headers=student_headers)
    assert linked.json()["link_status"] == "active"
    assert linked.json()["teacher"]["public_id"] == teacher["public_id"]
    assert linked.json()["teacher"]["display_name"] == "Асқар Серікұлы"

    db = db_session_factory()
    try:
        student_acc = db.query(AccountRecord).filter(AccountRecord.email == "kid@school.kz").one()
        teacher_acc = db.query(AccountRecord).filter(AccountRecord.email == "lab@school.kz").one()
        student_row = db.get(StudentRecord, student_acc.student_sync_id)
        rooms = json.loads(db.get(TeacherClassroomLinkRecord, teacher_acc.teacher_sync_id).classroom_sync_ids_json)
        assert student_row.classroom_sync_id == rooms[0]
    finally:
        db.close()


def test_connect_teacher_rejects_unknown_code(client) -> None:
    student_headers, _student = _auth(client, "lost@school.kz", "secret1", "Оқушы", "student")
    response = client.post(
        "/api/v1/student/connect-teacher",
        json={"teacher_code": "T-ZZZZZZ"},
        headers=student_headers,
    )
    assert response.status_code == 404
    assert "табылмады" in response.json()["detail"]


def test_wrong_password(client) -> None:
    _auth(client, "x@school.kz", "secret1", "X", None)
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "x@school.kz", "password": "nope"},
        headers={"X-API-Key": _TEST_API_KEY},
    )
    assert login.status_code == 401


def test_list_linked_students_only_accepted(client, db_session_factory) -> None:
    from server.app.models.account_models import AccountRecord
    from server.app.services.people_service import list_linked_students

    teacher_headers, teacher = _auth(client, "link-t@school.kz", "secret1", "Мұғалім", "teacher")
    student_headers, student = _auth(client, "link-s@school.kz", "secret1", "Оқушы", "student")
    lone_headers, _lone = _auth(client, "link-solo@school.kz", "secret1", "Дербес", "student")
    del lone_headers
    sent = client.post(
        "/api/v1/student/connect-teacher",
        json={"teacher_code": teacher["public_id"]},
        headers=student_headers,
    )
    assert sent.status_code == 200
    incoming = client.get("/api/v1/requests/incoming", headers=teacher_headers)
    request_id = incoming.json()["items"][0]["id"]
    client.post(f"/api/v1/requests/{request_id}/accept", headers=teacher_headers)
    db = db_session_factory()
    try:
        teacher_row = db.query(AccountRecord).filter(AccountRecord.email == "link-t@school.kz").one()
        linked = list_linked_students(db, teacher_row)
        assert [row.email for row in linked] == ["link-s@school.kz"]
    finally:
        db.close()
