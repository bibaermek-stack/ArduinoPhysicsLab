"""§28 "SERVER" тесттері: student sync_id-негізді upsert/pull +
relationship validation (§ "classroom must exist first")."""

import pytest

_CLASSROOM_PAYLOAD = {
    "sync_id": "c1",
    "name": "8А",
    "academic_year": "",
    "description": "",
    "is_archived": False,
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z",
}
_STUDENT_PAYLOAD = {
    "sync_id": "s1",
    "classroom_sync_id": "c1",
    "first_name": "Досым",
    "last_name": "Ахметов",
    "middle_name": "",
    "student_code": "111111",
    "notes": "",
    "is_archived": False,
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z",
}


@pytest.fixture()
def with_classroom(client, teacher_auth_headers):
    client.post("/api/v1/sync/classrooms", json=[_CLASSROOM_PAYLOAD], headers=teacher_auth_headers)
    return client


def test_upsert_student_requires_existing_classroom(client, teacher_auth_headers) -> None:
    """§28 "relationship validation" — no classroom pushed yet."""
    response = client.post("/api/v1/sync/students", json=[_STUDENT_PAYLOAD], headers=teacher_auth_headers)

    assert response.status_code == 200  # batch endpoint: per-item error, not a hard failure
    result = response.json()["results"][0]
    assert result["status"] == "error"
    assert "classroom_sync_id" in result["error"]


def test_upsert_student_succeeds_after_classroom_exists(with_classroom, teacher_auth_headers) -> None:
    response = with_classroom.post("/api/v1/sync/students", json=[_STUDENT_PAYLOAD], headers=teacher_auth_headers)

    assert response.json()["results"][0]["status"] == "upserted"
    pulled = with_classroom.get("/api/v1/sync/students", headers=teacher_auth_headers).json()["items"]
    assert len(pulled) == 1
    assert pulled[0]["first_name"] == "Досым"


def test_upsert_idempotent_by_sync_id(with_classroom, teacher_auth_headers) -> None:
    with_classroom.post("/api/v1/sync/students", json=[_STUDENT_PAYLOAD], headers=teacher_auth_headers)
    with_classroom.post(
        "/api/v1/sync/students",
        json=[{**_STUDENT_PAYLOAD, "first_name": "Renamed"}],
        headers=teacher_auth_headers,
    )

    pulled = with_classroom.get("/api/v1/sync/students", headers=teacher_auth_headers).json()["items"]
    assert len(pulled) == 1
    assert pulled[0]["first_name"] == "Renamed"
    assert pulled[0]["server_revision"] == 2


def test_student_code_round_trips_exactly(with_classroom, teacher_auth_headers) -> None:
    with_classroom.post("/api/v1/sync/students", json=[_STUDENT_PAYLOAD], headers=teacher_auth_headers)

    pulled = with_classroom.get("/api/v1/sync/students", headers=teacher_auth_headers).json()["items"]
    assert pulled[0]["student_code"] == "111111"


def test_mixed_batch_partial_success(with_classroom, teacher_auth_headers) -> None:
    """One valid student + one referencing a missing classroom in the
    SAME batch — the valid one still succeeds."""
    bad_student = {**_STUDENT_PAYLOAD, "sync_id": "s2", "classroom_sync_id": "ghost-classroom"}

    response = with_classroom.post(
        "/api/v1/sync/students", json=[_STUDENT_PAYLOAD, bad_student], headers=teacher_auth_headers
    )

    results = {r["sync_id"]: r["status"] for r in response.json()["results"]}
    assert results["s1"] == "upserted"
    assert results["s2"] == "error"
