"""§28 "SERVER" тесттері: classroom sync_id-негізді upsert/pull."""

_CLASSROOM_PAYLOAD = {
    "sync_id": "c1",
    "name": "8А",
    "academic_year": "2025-2026",
    "description": "",
    "is_archived": False,
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z",
}


def test_upsert_and_pull_classroom(client, teacher_auth_headers) -> None:
    response = client.post("/api/v1/sync/classrooms", json=[_CLASSROOM_PAYLOAD], headers=teacher_auth_headers)
    assert response.status_code == 200

    pulled = client.get("/api/v1/sync/classrooms", headers=teacher_auth_headers).json()["items"]
    assert len(pulled) == 1
    assert pulled[0]["name"] == "8А"
    assert pulled[0]["server_revision"] == 1


def test_upsert_idempotent_by_sync_id(client, teacher_auth_headers) -> None:
    client.post("/api/v1/sync/classrooms", json=[_CLASSROOM_PAYLOAD], headers=teacher_auth_headers)
    client.post(
        "/api/v1/sync/classrooms",
        json=[{**_CLASSROOM_PAYLOAD, "is_archived": True}],
        headers=teacher_auth_headers,
    )

    pulled = client.get("/api/v1/sync/classrooms", headers=teacher_auth_headers).json()["items"]
    assert len(pulled) == 1
    assert pulled[0]["is_archived"] is True
    assert pulled[0]["server_revision"] == 2


def test_archive_represented_as_upsert_not_hard_delete(client, teacher_auth_headers) -> None:
    """§4/§10: soft-delete-only semantics carry through to the server —
    an archived classroom is still readable via pull, just flagged."""
    client.post("/api/v1/sync/classrooms", json=[_CLASSROOM_PAYLOAD], headers=teacher_auth_headers)
    client.post(
        "/api/v1/sync/classrooms",
        json=[{**_CLASSROOM_PAYLOAD, "is_archived": True}],
        headers=teacher_auth_headers,
    )

    pulled = client.get("/api/v1/sync/classrooms", headers=teacher_auth_headers).json()["items"]
    assert len(pulled) == 1  # record still present, not hard-deleted


def test_invalid_payload_empty_name_rejected(client, teacher_auth_headers) -> None:
    response = client.post(
        "/api/v1/sync/classrooms", json=[{**_CLASSROOM_PAYLOAD, "name": ""}], headers=teacher_auth_headers
    )
    assert response.status_code == 422
