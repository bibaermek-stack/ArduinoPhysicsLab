"""server tests (Phase 7: Teacher Actions, Feedback Delivery, and
Session History) — ``/api/v1/sync/teacher-notes`` push/pull
authorization, idempotency, isolation.

``test_sync_phase2.py``-мен БІРДЕЙ паттерн: жергілікті payload
константалары + ``with_student`` fixture-і (§ бөлек тест модулінің
өз оқшауланған setup-ы).
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
_OTHER_STUDENT_PAYLOAD = {
    **_STUDENT_PAYLOAD,
    "sync_id": "s2",
    "first_name": "Асем",
    "last_name": "Нурлан",
    "student_code": "222222",
}
_NOTE_PAYLOAD = {
    "sync_id": "note1",
    "teacher_sync_id": "t1",
    "student_sync_id": "s1",
    "classroom_sync_id": "c1",
    "experiment_id": "ohms-law",
    "session_sync_id": None,
    "message": "Өлшеуді қайта тексер",
    "created_at": "2024-02-01T10:00:00Z",
}


@pytest.fixture()
def with_student(client, teacher_auth_headers):
    client.post("/api/v1/sync/classrooms", json=[_CLASSROOM_PAYLOAD], headers=teacher_auth_headers)
    client.post("/api/v1/sync/students", json=[_STUDENT_PAYLOAD, _OTHER_STUDENT_PAYLOAD], headers=teacher_auth_headers)
    client.post(
        "/api/v1/sync/teacher-classrooms",
        json=[{"teacher_sync_id": "t1", "classroom_sync_ids": ["c1"], "updated_at": "2024-01-01T00:00:00Z"}],
        headers=teacher_auth_headers,
    )
    return client


def test_student_cannot_write_teacher_note(with_student, student_auth_headers) -> None:
    """§ "teacher-initiated only"."""
    response = with_student.post(
        "/api/v1/sync/teacher-notes", json=[_NOTE_PAYLOAD], headers=student_auth_headers
    )

    assert response.status_code == 403


def test_teacher_cannot_send_note_as_another_teacher(with_student, teacher_auth_headers) -> None:
    other_teacher_note = {**_NOTE_PAYLOAD, "teacher_sync_id": "t2"}

    response = with_student.post(
        "/api/v1/sync/teacher-notes", json=[other_teacher_note], headers=teacher_auth_headers
    )

    assert response.status_code == 403


def test_unassigned_teacher_cannot_send_note_to_unrelated_student(with_student, client) -> None:
    from server.tests.conftest import _bootstrap_login

    other_teacher_headers = _bootstrap_login(
        client, "/api/v1/auth/teacher-login", {"sync_id": "t2", "pin_hash": "hash-t2", "full_name": "Teacher Two"}
    )
    note_as_t2 = {**_NOTE_PAYLOAD, "teacher_sync_id": "t2"}

    response = with_student.post(
        "/api/v1/sync/teacher-notes", json=[note_as_t2], headers=other_teacher_headers
    )

    assert response.status_code == 403


def test_authorized_teacher_sends_note(with_student, teacher_auth_headers) -> None:
    response = with_student.post(
        "/api/v1/sync/teacher-notes", json=[_NOTE_PAYLOAD], headers=teacher_auth_headers
    )

    assert response.json()["results"][0]["status"] == "upserted"


def test_note_upsert_idempotent_by_sync_id(with_student, teacher_auth_headers) -> None:
    """§ "immutable once created" — қайталама push дубликат ЖАСАМАЙДЫ,
    мазмұн да ӨЗГЕРМЕЙДІ (§ ``upsert_measurement_batch()``-пен БІРДЕЙ)."""
    with_student.post("/api/v1/sync/teacher-notes", json=[_NOTE_PAYLOAD], headers=teacher_auth_headers)
    with_student.post(
        "/api/v1/sync/teacher-notes",
        json=[{**_NOTE_PAYLOAD, "message": "ӨЗГЕРТІЛГЕН мәтін"}],
        headers=teacher_auth_headers,
    )

    pulled = with_student.get("/api/v1/sync/teacher-notes", headers=teacher_auth_headers).json()["items"]
    assert len(pulled) == 1
    assert pulled[0]["message"] == "Өлшеуді қайта тексер"  # § өзгертілмеді


def test_intended_student_receives_note(with_student, teacher_auth_headers, student_auth_headers) -> None:
    with_student.post("/api/v1/sync/teacher-notes", json=[_NOTE_PAYLOAD], headers=teacher_auth_headers)

    pulled = with_student.get("/api/v1/sync/teacher-notes", headers=student_auth_headers).json()["items"]

    assert [item["sync_id"] for item in pulled] == ["note1"]
    assert pulled[0]["message"] == "Өлшеуді қайта тексер"


def test_unrelated_student_never_receives_the_note(with_student, teacher_auth_headers, client) -> None:
    """§ "another student must never receive it"."""
    from server.tests.conftest import _bootstrap_login

    other_student_headers = _bootstrap_login(
        client, "/api/v1/auth/student-login",
        {"sync_id": "s2", "student_code": "222222", "classroom_sync_id": "c1"},
    )
    with_student.post("/api/v1/sync/teacher-notes", json=[_NOTE_PAYLOAD], headers=teacher_auth_headers)

    pulled = with_student.get("/api/v1/sync/teacher-notes", headers=other_student_headers).json()["items"]

    assert pulled == []


def test_teacher_sees_own_sent_note(with_student, teacher_auth_headers) -> None:
    with_student.post("/api/v1/sync/teacher-notes", json=[_NOTE_PAYLOAD], headers=teacher_auth_headers)

    pulled = with_student.get("/api/v1/sync/teacher-notes", headers=teacher_auth_headers).json()["items"]

    assert [item["sync_id"] for item in pulled] == ["note1"]


def test_unassigned_teacher_does_not_see_others_note(with_student, teacher_auth_headers, client) -> None:
    from server.tests.conftest import _bootstrap_login

    other_teacher_headers = _bootstrap_login(
        client, "/api/v1/auth/teacher-login", {"sync_id": "t2", "pin_hash": "hash-t2", "full_name": "Teacher Two"}
    )
    with_student.post("/api/v1/sync/teacher-notes", json=[_NOTE_PAYLOAD], headers=teacher_auth_headers)

    pulled = with_student.get("/api/v1/sync/teacher-notes", headers=other_teacher_headers).json()["items"]

    assert pulled == []


def test_note_without_session_context_is_accepted(with_student, teacher_auth_headers) -> None:
    """§ ``session_sync_id``/``experiment_id`` ЕРІКТІ — ағымдағы
    тәжірибе контекстінен тыс та жіберуге болады."""
    context_free_note = {**_NOTE_PAYLOAD, "experiment_id": None, "session_sync_id": None}

    response = with_student.post(
        "/api/v1/sync/teacher-notes", json=[context_free_note], headers=teacher_auth_headers
    )

    assert response.json()["results"][0]["status"] == "upserted"


def test_missing_message_rejected_with_422(with_student, teacher_auth_headers) -> None:
    bad_payload = {k: v for k, v in _NOTE_PAYLOAD.items() if k != "message"}

    response = with_student.post("/api/v1/sync/teacher-notes", json=[bad_payload], headers=teacher_auth_headers)

    assert response.status_code == 422
