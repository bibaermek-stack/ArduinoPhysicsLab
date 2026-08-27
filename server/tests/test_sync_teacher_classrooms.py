"""§28/§35 "SERVER" тесттері: teacher<->classroom assignment sync (§
бүкіл жиын мұғалімнің sync_id-мен синхрондалады) + Phase 3 self-
upsert-only авторизациясы (§4 "A teacher may only set their own
classroom assignment set")."""

import pytest

_CLASSROOM_A = {
    "sync_id": "c1", "name": "8А", "academic_year": "", "description": "", "is_archived": False,
    "created_at": "2024-01-01T00:00:00Z", "updated_at": "2024-01-01T00:00:00Z",
}
_CLASSROOM_B = {
    "sync_id": "c2", "name": "8Б", "academic_year": "", "description": "", "is_archived": False,
    "created_at": "2024-01-01T00:00:00Z", "updated_at": "2024-01-01T00:00:00Z",
}


@pytest.fixture()
def with_classrooms(client, teacher_auth_headers):
    client.post("/api/v1/sync/classrooms", json=[_CLASSROOM_A, _CLASSROOM_B], headers=teacher_auth_headers)
    return client


def test_cannot_assign_classrooms_to_another_teacher(client, teacher_auth_headers) -> None:
    """§4/§11 "reject entity-ID spoofing" — Phase 3-те ескі "ghost
    teacher" сценарийі мағынасыз болды (§ ``teacher_auth_headers``
    логин ӨЗІ "t1"-ды автоматты тіркейді, § TOFU bootstrap) — енді
    маңызды жағдай: ӨЗГЕ бір мұғалімнің атынан тағайындау жиынын
    орнатуға тыйым салынуы."""
    payload = {"teacher_sync_id": "another-teacher", "classroom_sync_ids": [], "updated_at": "2024-01-01T00:00:00Z"}

    response = client.post("/api/v1/sync/teacher-classrooms", json=[payload], headers=teacher_auth_headers)

    assert response.status_code == 403


def test_requires_existing_classrooms(client, teacher_auth_headers) -> None:
    payload = {
        "teacher_sync_id": "t1", "classroom_sync_ids": ["ghost-c"], "updated_at": "2024-01-01T00:00:00Z",
    }

    response = client.post("/api/v1/sync/teacher-classrooms", json=[payload], headers=teacher_auth_headers)

    assert response.json()["results"][0]["status"] == "error"


def test_upsert_and_pull_assignment_set(with_classrooms, teacher_auth_headers) -> None:
    payload = {
        "teacher_sync_id": "t1", "classroom_sync_ids": ["c1", "c2"], "updated_at": "2024-01-01T00:00:00Z",
    }

    response = with_classrooms.post(
        "/api/v1/sync/teacher-classrooms", json=[payload], headers=teacher_auth_headers
    )
    assert response.json()["results"][0]["status"] == "upserted"

    pulled = with_classrooms.get(
        "/api/v1/sync/teacher-classrooms", headers=teacher_auth_headers
    ).json()["items"]
    assert len(pulled) == 1
    assert set(pulled[0]["classroom_sync_ids"]) == {"c1", "c2"}


def test_reassignment_replaces_full_set(with_classrooms, teacher_auth_headers) -> None:
    first = {"teacher_sync_id": "t1", "classroom_sync_ids": ["c1", "c2"], "updated_at": "2024-01-01T00:00:00Z"}
    with_classrooms.post("/api/v1/sync/teacher-classrooms", json=[first], headers=teacher_auth_headers)

    second = {"teacher_sync_id": "t1", "classroom_sync_ids": ["c1"], "updated_at": "2024-01-02T00:00:00Z"}
    with_classrooms.post("/api/v1/sync/teacher-classrooms", json=[second], headers=teacher_auth_headers)

    pulled = with_classrooms.get(
        "/api/v1/sync/teacher-classrooms", headers=teacher_auth_headers
    ).json()["items"]
    assert len(pulled) == 1  # still ONE record for this teacher, not a new one
    assert pulled[0]["classroom_sync_ids"] == ["c1"]
    assert pulled[0]["server_revision"] == 2
