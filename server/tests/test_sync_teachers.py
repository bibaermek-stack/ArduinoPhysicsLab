"""§28/§35 "SERVER" тесттері: teacher sync_id-негізді upsert/pull +
Phase 3 self-upsert-only авторизациясы (§4 "A teacher may only upsert
their own teacher record")."""

_TEACHER_PAYLOAD = {
    "sync_id": "t1",
    "full_name": "Aidos Nurlanuly",
    "pin_hash": "hash1",
    "is_active": True,
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z",
}


def test_requires_api_key(client) -> None:
    response = client.post("/api/v1/sync/teachers", json=[_TEACHER_PAYLOAD])
    assert response.status_code == 401


def test_requires_bearer_token(client, auth_headers) -> None:
    """§4/§11: X-API-Key ЖЕТКІЛІКСІЗ — payload-негізді авторизация
    ЖОҚ болса да, ``Authorization: Bearer`` МІНДЕТТІ."""
    response = client.post("/api/v1/sync/teachers", json=[_TEACHER_PAYLOAD], headers=auth_headers)
    assert response.status_code == 401


def test_upsert_creates_new_teacher(client, teacher_auth_headers) -> None:
    response = client.post("/api/v1/sync/teachers", json=[_TEACHER_PAYLOAD], headers=teacher_auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["results"] == [{"sync_id": "t1", "status": "upserted", "server_revision": 2, "error": None}]


def test_pull_returns_created_teacher(client, teacher_auth_headers) -> None:
    client.post("/api/v1/sync/teachers", json=[_TEACHER_PAYLOAD], headers=teacher_auth_headers)

    response = client.get("/api/v1/sync/teachers", headers=teacher_auth_headers)

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["sync_id"] == "t1"
    assert items[0]["full_name"] == "Aidos Nurlanuly"


def test_upsert_by_same_sync_id_is_idempotent_and_increments_revision(client, teacher_auth_headers) -> None:
    """§28 "idempotent upsert by sync_id" — re-upserting the SAME
    sync_id updates the existing row in place (never duplicates)."""
    client.post("/api/v1/sync/teachers", json=[_TEACHER_PAYLOAD], headers=teacher_auth_headers)
    updated_payload = {**_TEACHER_PAYLOAD, "full_name": "Aidos Renamed"}

    client.post("/api/v1/sync/teachers", json=[updated_payload], headers=teacher_auth_headers)

    pulled = client.get("/api/v1/sync/teachers", headers=teacher_auth_headers).json()["items"]
    assert len(pulled) == 1
    assert pulled[0]["full_name"] == "Aidos Renamed"


def test_invalid_payload_missing_required_field_rejected(client, teacher_auth_headers) -> None:
    invalid_payload = {"sync_id": "t1"}  # missing full_name/pin_hash/timestamps

    response = client.post("/api/v1/sync/teachers", json=[invalid_payload], headers=teacher_auth_headers)

    assert response.status_code == 422


def test_invalid_payload_empty_full_name_rejected(client, teacher_auth_headers) -> None:
    invalid_payload = {**_TEACHER_PAYLOAD, "full_name": ""}

    response = client.post("/api/v1/sync/teachers", json=[invalid_payload], headers=teacher_auth_headers)

    assert response.status_code == 422


def test_pull_incremental_via_updated_since(client, teacher_auth_headers) -> None:
    client.post("/api/v1/sync/teachers", json=[_TEACHER_PAYLOAD], headers=teacher_auth_headers)
    first_pull = client.get("/api/v1/sync/teachers", headers=teacher_auth_headers).json()
    cursor = first_pull["server_time"]

    # No new changes since the cursor -> empty incremental pull.
    second_pull = client.get(
        "/api/v1/sync/teachers", params={"updated_since": cursor}, headers=teacher_auth_headers
    ).json()
    assert second_pull["items"] == []

    client.post(
        "/api/v1/sync/teachers", json=[{**_TEACHER_PAYLOAD, "full_name": "Renamed"}], headers=teacher_auth_headers
    )

    third_pull = client.get(
        "/api/v1/sync/teachers", params={"updated_since": cursor}, headers=teacher_auth_headers
    ).json()
    assert [item["sync_id"] for item in third_pull["items"]] == ["t1"]


def test_teacher_cannot_upsert_another_teachers_record(client, teacher_auth_headers) -> None:
    """§4/§11 "reject entity-ID spoofing": t1 identity may not push a
    payload claiming to BE t2."""
    other_teacher_payload = {**_TEACHER_PAYLOAD, "sync_id": "t2", "full_name": "Gulmira"}

    response = client.post("/api/v1/sync/teachers", json=[other_teacher_payload], headers=teacher_auth_headers)

    assert response.status_code == 403


def test_two_teachers_each_self_upsert_and_only_see_their_own_record(client) -> None:
    """§6/§25 "Multi-teacher isolation": Teacher A and Teacher B each
    authenticate independently and each may only self-upsert/self-pull."""
    from server.tests.conftest import _bootstrap_login

    teacher_a_headers = _bootstrap_login(
        client, "/api/v1/auth/teacher-login", {"sync_id": "ta", "pin_hash": "hash-a", "full_name": "Teacher A"}
    )
    teacher_b_headers = _bootstrap_login(
        client, "/api/v1/auth/teacher-login", {"sync_id": "tb", "pin_hash": "hash-b", "full_name": "Teacher B"}
    )

    client.post(
        "/api/v1/sync/teachers",
        json=[{**_TEACHER_PAYLOAD, "sync_id": "ta", "full_name": "Teacher A"}],
        headers=teacher_a_headers,
    )
    client.post(
        "/api/v1/sync/teachers",
        json=[{**_TEACHER_PAYLOAD, "sync_id": "tb", "full_name": "Teacher B"}],
        headers=teacher_b_headers,
    )

    a_sees = client.get("/api/v1/sync/teachers", headers=teacher_a_headers).json()["items"]
    b_sees = client.get("/api/v1/sync/teachers", headers=teacher_b_headers).json()["items"]

    assert [item["sync_id"] for item in a_sees] == ["ta"]
    assert [item["sync_id"] for item in b_sees] == ["tb"]


def test_pin_hash_never_appears_in_health_endpoint(client) -> None:
    """§27 "Logging"/§12 sanity: unrelated endpoints never leak sync
    payload content."""
    response = client.get("/api/v1/health")
    assert "hash1" not in response.text
