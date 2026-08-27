"""§ Phase 4 (Raw Arduino Measurement Cloud Sync) SERVER тесттері:
measurement-batch upsert idempotency ("server committed, client lost
the response, retries"), relationship validation (session ЕШҚАШАН
алдын ала белгісіз болмауы керек), authorization (тек оқушы жүктейді,
тек ӨЗ сессиясына; pull — сессия иесі оқушы НЕМЕСЕ тағайындалған
сынып мұғалімі), raw data fidelity (мән/ретті сақтау), malformed/
empty-batch rejection.
"""

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
_SESSION_PAYLOAD = {
    "sync_id": "sess1",
    "experiment_id": "ohms-law",
    "experiment_title": "Ohm's Law",
    "experiment_display_number": 3,
    "started_at": "2024-02-01T10:00:00Z",
    "ended_at": "2024-02-01T10:05:00Z",
    "status": "finalized",
    "measurement_count": 3,
    "created_at": "2024-02-01T10:00:00Z",
    "updated_at": "2024-02-01T10:05:00Z",
}
_LINK_PAYLOAD = {
    "session_sync_id": "sess1",
    "student_sync_id": "s1",
    "classroom_sync_id": "c1",
    "experiment_id": "ohms-law",
    "linked_at": "2024-02-01T09:59:00Z",
}


def _batch_payload(sync_id: str = "batch1", session_sync_id: str = "sess1") -> dict:
    return {
        "sync_id": sync_id,
        "session_sync_id": session_sync_id,
        "sequence_start": 0,
        "sequence_end": 3,
        "sample_count": 3,
        "created_at": "2024-02-01T10:01:00Z",
        "measurements": [
            {
                "sequence_no": 0,
                "timestamp": "2024-02-01T10:01:00Z",
                "values": {"voltage": 6.413, "current": 0.0078},
                "derived_values": {"power": 0.05},
                "warnings": [],
            },
            {
                "sequence_no": 1,
                "timestamp": "2024-02-01T10:01:01Z",
                "values": {"voltage": 6.5, "current": 0.008},
                "derived_values": {"power": 0.052},
                "warnings": ["low_signal"],
            },
            {
                "sequence_no": 2,
                "timestamp": "2024-02-01T10:01:02Z",
                "values": {"voltage": 6.6, "current": 0.0081},
                "derived_values": {},
                "warnings": [],
            },
        ],
    }


@pytest.fixture()
def with_student(client, teacher_auth_headers):
    client.post("/api/v1/sync/classrooms", json=[_CLASSROOM_PAYLOAD], headers=teacher_auth_headers)
    client.post("/api/v1/sync/students", json=[_STUDENT_PAYLOAD], headers=teacher_auth_headers)
    client.post(
        "/api/v1/sync/teacher-classrooms",
        json=[{"teacher_sync_id": "t1", "classroom_sync_ids": ["c1"], "updated_at": "2024-01-01T00:00:00Z"}],
        headers=teacher_auth_headers,
    )
    return client


@pytest.fixture()
def with_link_no_session(with_student, student_auth_headers):
    """§ Phase 2 "child record must not fail merely because its parent
    is still sitting earlier in the same local outbox batch": байланыс
    БАР (§ авторизация ӨТЕДІ), БІРАҚ ``sync_sessions`` жазбасы ӘЛІ ЖОҚ
    — measurement-batch upsert-тің НАҚТЫ ``RelationshipError`` жолын
    (§ ``upsert_measurement_batch()`` докстрингі) авторизациядан
    бөлек тексереді."""
    with_student.post("/api/v1/sync/session-students", json=[_LINK_PAYLOAD], headers=student_auth_headers)
    return with_student


@pytest.fixture()
def with_session_link(with_link_no_session, student_auth_headers):
    with_link_no_session.post("/api/v1/sync/sessions", json=[_SESSION_PAYLOAD], headers=student_auth_headers)
    return with_link_no_session


# ---- Relationship validation -----------------------------------------------


def test_upsert_batch_without_known_session_is_relationship_error(
    with_link_no_session, student_auth_headers
) -> None:
    response = with_link_no_session.post(
        "/api/v1/sync/measurement-batches", json=[_batch_payload()], headers=student_auth_headers
    )
    assert response.status_code == 200, response.text
    assert response.json()["results"][0]["status"] == "error"


# ---- Idempotency (HARD requirement) ----------------------------------------


def test_upsert_same_batch_sync_id_twice_is_idempotent(with_session_link, student_auth_headers) -> None:
    """§ "server committed, client lost the response, retries": екінші
    рет ЖІБЕРУ ЕШБІР дубликат жасамайды, дәл СОЛ revision қайтарады."""
    payload = _batch_payload()
    first = with_session_link.post(
        "/api/v1/sync/measurement-batches", json=[payload], headers=student_auth_headers
    )
    second = with_session_link.post(
        "/api/v1/sync/measurement-batches", json=[payload], headers=student_auth_headers
    )
    assert first.json()["results"][0]["status"] == "upserted"
    assert second.json()["results"][0]["status"] == "upserted"
    assert first.json()["results"][0]["server_revision"] == second.json()["results"][0]["server_revision"]

    pulled = with_session_link.get("/api/v1/sync/measurement-batches", headers=student_auth_headers)
    items = pulled.json()["items"]
    assert len(items) == 1
    assert len(items[0]["measurements"]) == 3


# ---- Raw data fidelity + ordering ------------------------------------------


def test_pull_preserves_exact_values_and_order(with_session_link, student_auth_headers) -> None:
    with_session_link.post(
        "/api/v1/sync/measurement-batches", json=[_batch_payload()], headers=student_auth_headers
    )
    response = with_session_link.get("/api/v1/sync/measurement-batches", headers=student_auth_headers)
    item = response.json()["items"][0]
    assert [m["sequence_no"] for m in item["measurements"]] == [0, 1, 2]
    assert item["measurements"][0]["values"] == {"voltage": 6.413, "current": 0.0078}
    assert item["measurements"][0]["derived_values"] == {"power": 0.05}
    assert item["measurements"][1]["warnings"] == ["low_signal"]
    assert item["sample_count"] == 3
    assert item["sequence_start"] == 0
    assert item["sequence_end"] == 3


# ---- Authorization: push ----------------------------------------------------


def test_teacher_cannot_push_measurement_batches(with_session_link, teacher_auth_headers) -> None:
    response = with_session_link.post(
        "/api/v1/sync/measurement-batches", json=[_batch_payload()], headers=teacher_auth_headers
    )
    assert response.status_code == 403


def test_student_cannot_push_into_another_students_session(with_session_link, client) -> None:
    from server.tests.conftest import _bootstrap_login

    other_student_headers = _bootstrap_login(
        client, "/api/v1/auth/student-login",
        {"sync_id": "s2", "student_code": "222222", "classroom_sync_id": "c1"},
    )
    response = client.post(
        "/api/v1/sync/measurement-batches",
        json=[_batch_payload(sync_id="batch-intrusion", session_sync_id="sess1")],
        headers=other_student_headers,
    )
    assert response.status_code == 403


# ---- Authorization: pull ----------------------------------------------------


def test_owning_student_can_pull_own_batches(with_session_link, student_auth_headers) -> None:
    with_session_link.post(
        "/api/v1/sync/measurement-batches", json=[_batch_payload()], headers=student_auth_headers
    )
    response = with_session_link.get("/api/v1/sync/measurement-batches", headers=student_auth_headers)
    assert len(response.json()["items"]) == 1


def test_assigned_teacher_can_pull_batches(with_session_link, student_auth_headers, teacher_auth_headers) -> None:
    with_session_link.post(
        "/api/v1/sync/measurement-batches", json=[_batch_payload()], headers=student_auth_headers
    )
    response = with_session_link.get("/api/v1/sync/measurement-batches", headers=teacher_auth_headers)
    assert len(response.json()["items"]) == 1


def test_unassigned_teacher_cannot_pull_batches(with_session_link, student_auth_headers, client) -> None:
    from server.tests.conftest import _bootstrap_login

    with_session_link.post(
        "/api/v1/sync/measurement-batches", json=[_batch_payload()], headers=student_auth_headers
    )
    other_teacher_headers = _bootstrap_login(
        client, "/api/v1/auth/teacher-login",
        {"sync_id": "t2", "pin_hash": "test-pin-hash-t2", "full_name": "Other Teacher"},
    )
    response = client.get("/api/v1/sync/measurement-batches", headers=other_teacher_headers)
    assert response.status_code == 200
    assert response.json()["items"] == []


def test_other_student_cannot_pull_someone_elses_batches(with_session_link, student_auth_headers, client) -> None:
    from server.tests.conftest import _bootstrap_login

    with_session_link.post(
        "/api/v1/sync/measurement-batches", json=[_batch_payload()], headers=student_auth_headers
    )
    other_student_headers = _bootstrap_login(
        client, "/api/v1/auth/student-login",
        {"sync_id": "s2", "student_code": "222222", "classroom_sync_id": "c1"},
    )
    response = client.get("/api/v1/sync/measurement-batches", headers=other_student_headers)
    assert response.json()["items"] == []


# ---- Payload validation -----------------------------------------------------


def test_empty_batch_is_rejected(with_session_link, student_auth_headers) -> None:
    payload = _batch_payload()
    payload["measurements"] = []
    response = with_session_link.post(
        "/api/v1/sync/measurement-batches", json=[payload], headers=student_auth_headers
    )
    assert response.status_code == 422


def test_unauthenticated_push_requires_bearer_token(with_session_link, auth_headers) -> None:
    response = with_session_link.post(
        "/api/v1/sync/measurement-batches", json=[_batch_payload()], headers=auth_headers
    )
    assert response.status_code == 401
