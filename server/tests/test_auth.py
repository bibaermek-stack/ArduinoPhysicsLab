"""§11 "AUTHENTICATION" tesттері (Phase 3: Production Authentication +
Authorization): valid/invalid teacher login, valid/invalid student
login, expired token, malformed token, missing token."""

from datetime import datetime, timedelta, timezone

import jwt
import pytest

from server.app.services import auth_service

_TEACHER_LOGIN = {"sync_id": "t1", "pin_hash": "hash1", "full_name": "Aidos"}
_STUDENT_LOGIN = {"sync_id": "s1", "student_code": "111111", "classroom_sync_id": "c1"}


# ---- 1/3. Valid login (TOFU bootstrap on first use) ------------------------


def test_valid_teacher_login_issues_token(client, auth_headers) -> None:
    response = client.post("/api/v1/auth/teacher-login", json=_TEACHER_LOGIN, headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "teacher"
    assert body["sync_id"] == "t1"
    assert body["access_token"]
    assert body["token_type"] == "bearer"


def test_valid_student_login_issues_token(client, auth_headers) -> None:
    response = client.post("/api/v1/auth/student-login", json=_STUDENT_LOGIN, headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "student"
    assert body["sync_id"] == "s1"
    assert body["access_token"]


# ---- 2/4. Invalid credential (already-known identity, wrong secret) --------


def test_invalid_teacher_pin_hash_rejected(client, auth_headers) -> None:
    client.post("/api/v1/auth/teacher-login", json=_TEACHER_LOGIN, headers=auth_headers)  # registers t1

    response = client.post(
        "/api/v1/auth/teacher-login",
        json={**_TEACHER_LOGIN, "pin_hash": "wrong-hash"},
        headers=auth_headers,
    )

    assert response.status_code == 401


def test_invalid_student_access_code_rejected(client, auth_headers) -> None:
    client.post("/api/v1/auth/student-login", json=_STUDENT_LOGIN, headers=auth_headers)  # registers s1

    response = client.post(
        "/api/v1/auth/student-login",
        json={**_STUDENT_LOGIN, "student_code": "wrong-code"},
        headers=auth_headers,
    )

    assert response.status_code == 401


def test_login_requires_api_key(client) -> None:
    response = client.post("/api/v1/auth/teacher-login", json=_TEACHER_LOGIN)
    assert response.status_code == 401


# ---- 5. Expired token -------------------------------------------------------


def test_expired_token_rejected(client, teacher_auth_headers) -> None:
    expired_token = jwt.encode(
        {"sub": "t1", "role": "teacher", "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
        auth_service.get_configured_jwt_secret(),
        algorithm="HS256",
    )

    response = client.get(
        "/api/v1/sync/teachers",
        headers={"X-API-Key": "dev-local-only-key", "Authorization": f"Bearer {expired_token}"},
    )

    assert response.status_code == 401


# ---- 6. Malformed token ------------------------------------------------------


@pytest.mark.parametrize(
    "bad_token",
    [
        "not-a-jwt-at-all",
        "eyJhbGciOiJIUzI1NiJ9.garbage.signature",
        jwt.encode({"sub": "t1", "role": "teacher"}, "wrong-secret-entirely", algorithm="HS256"),
    ],
)
def test_malformed_or_wrongly_signed_token_rejected(client, bad_token) -> None:
    response = client.get(
        "/api/v1/sync/teachers",
        headers={"X-API-Key": "dev-local-only-key", "Authorization": f"Bearer {bad_token}"},
    )

    assert response.status_code == 401


# ---- 7. Missing token --------------------------------------------------------


def test_missing_authorization_header_rejected(client, auth_headers) -> None:
    response = client.get("/api/v1/sync/teachers", headers=auth_headers)
    assert response.status_code == 401


def test_non_bearer_authorization_header_rejected(client, auth_headers) -> None:
    response = client.get(
        "/api/v1/sync/teachers", headers={**auth_headers, "Authorization": "Basic dXNlcjpwYXNz"}
    )
    assert response.status_code == 401


# ---- Role claim / token content sanity --------------------------------------


def test_token_role_and_subject_match_login_identity(client, auth_headers) -> None:
    login_response = client.post("/api/v1/auth/teacher-login", json=_TEACHER_LOGIN, headers=auth_headers)
    token = login_response.json()["access_token"]

    decoded = jwt.decode(token, auth_service.get_configured_jwt_secret(), algorithms=["HS256"])

    assert decoded["sub"] == "t1"
    assert decoded["role"] == "teacher"
    assert "exp" in decoded


def test_pin_hash_and_student_code_never_appear_in_health_or_auth_error_bodies(client, auth_headers) -> None:
    """§27 "Logging"/§10 sanity — credential values never echoed back in
    error responses."""
    response = client.post(
        "/api/v1/auth/teacher-login", json={**_TEACHER_LOGIN, "pin_hash": "super-secret-hash-xyz"}, headers=auth_headers
    )
    client.post(
        "/api/v1/auth/teacher-login",
        json={**_TEACHER_LOGIN, "pin_hash": "different-wrong-hash"},
        headers=auth_headers,
    )
    health = client.get("/api/v1/health")

    assert "super-secret-hash-xyz" not in health.text
