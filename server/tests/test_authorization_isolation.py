"""§4 "Server-Side Authorization" (HARD requirement) — dedicated cross-
teacher / cross-student isolation tests (Phase 3 acceptance items 8-18):

TEACHER AUTHORIZATION
  8. Teacher A can read own classroom
  9. Teacher A cannot read Teacher B-only classroom
  10. Teacher A can read own students
  11. Teacher A cannot read unrelated students
  12. Teacher A can read/review authorized submission
  13. Teacher A cannot review unauthorized submission

STUDENT AUTHORIZATION
  14. Student A can read own data
  15. Student A cannot read Student B private data
  16. Student A can submit own experiment feedback
  17. Student A cannot submit as Student B
  18. Student cannot write teacher assessment fields
"""

import pytest


def _login(client, path, body):
    response = client.post(path, json=body, headers={"X-API-Key": "dev-local-only-key"})
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"X-API-Key": "dev-local-only-key", "Authorization": f"Bearer {token}"}


@pytest.fixture()
def two_teacher_two_classroom_world(client):
    """Teacher A -> Classroom 8A -> Student A. Teacher B -> Classroom
    8B -> Student B. Each teacher creates/assigns ONLY their own
    classroom (§6 "Multiple Teachers": Teacher A must not automatically
    see 8C/Teacher B's classroom)."""
    teacher_a = _login(client, "/api/v1/auth/teacher-login", {"sync_id": "ta", "pin_hash": "hash-a", "full_name": "Teacher A"})
    teacher_b = _login(client, "/api/v1/auth/teacher-login", {"sync_id": "tb", "pin_hash": "hash-b", "full_name": "Teacher B"})

    client.post(
        "/api/v1/sync/classrooms",
        json=[{
            "sync_id": "ca", "name": "8A", "academic_year": "", "description": "", "is_archived": False,
            "created_at": "2024-01-01T00:00:00Z", "updated_at": "2024-01-01T00:00:00Z",
        }],
        headers=teacher_a,
    )
    client.post(
        "/api/v1/sync/classrooms",
        json=[{
            "sync_id": "cb", "name": "8B", "academic_year": "", "description": "", "is_archived": False,
            "created_at": "2024-01-01T00:00:00Z", "updated_at": "2024-01-01T00:00:00Z",
        }],
        headers=teacher_b,
    )
    client.post(
        "/api/v1/sync/teacher-classrooms",
        json=[{"teacher_sync_id": "ta", "classroom_sync_ids": ["ca"], "updated_at": "2024-01-01T00:00:00Z"}],
        headers=teacher_a,
    )
    client.post(
        "/api/v1/sync/teacher-classrooms",
        json=[{"teacher_sync_id": "tb", "classroom_sync_ids": ["cb"], "updated_at": "2024-01-01T00:00:00Z"}],
        headers=teacher_b,
    )
    client.post(
        "/api/v1/sync/students",
        json=[{
            "sync_id": "sa", "classroom_sync_id": "ca", "first_name": "Student", "last_name": "A",
            "middle_name": "", "student_code": "111111", "notes": "", "is_archived": False,
            "created_at": "2024-01-01T00:00:00Z", "updated_at": "2024-01-01T00:00:00Z",
        }],
        headers=teacher_a,
    )
    client.post(
        "/api/v1/sync/students",
        json=[{
            "sync_id": "sb", "classroom_sync_id": "cb", "first_name": "Student", "last_name": "B",
            "middle_name": "", "student_code": "222222", "notes": "", "is_archived": False,
            "created_at": "2024-01-01T00:00:00Z", "updated_at": "2024-01-01T00:00:00Z",
        }],
        headers=teacher_b,
    )
    student_a = _login(client, "/api/v1/auth/student-login", {"sync_id": "sa", "student_code": "111111", "classroom_sync_id": "ca"})
    student_b = _login(client, "/api/v1/auth/student-login", {"sync_id": "sb", "student_code": "222222", "classroom_sync_id": "cb"})

    client.post(
        "/api/v1/sync/session-students",
        json=[{
            "session_sync_id": "sess-a", "student_sync_id": "sa", "classroom_sync_id": "ca",
            "experiment_id": "ohms-law", "linked_at": "2024-02-01T09:00:00Z",
        }],
        headers=student_a,
    )
    client.post(
        "/api/v1/sync/session-students",
        json=[{
            "session_sync_id": "sess-b", "student_sync_id": "sb", "classroom_sync_id": "cb",
            "experiment_id": "ohms-law", "linked_at": "2024-02-01T09:00:00Z",
        }],
        headers=student_b,
    )
    client.post(
        "/api/v1/sync/feedback-results",
        json=[{
            "sync_id": "sess-a", "experiment_id": "ohms-law", "is_draft": False,
            "level1_answers": [], "level1_score": 0, "level1_total": 0, "level1_percentage": 0.0,
            "level2_answers": [], "level3_answers": [{"question_id": "r1", "response_text": "A-дың құпия жауабы"}],
            "self_assessment": None, "submitted_at": "2024-02-01T09:05:00Z",
            "created_at": "2024-02-01T09:05:00Z", "updated_at": "2024-02-01T09:05:00Z",
        }],
        headers=student_a,
    )
    client.post(
        "/api/v1/sync/feedback-results",
        json=[{
            "sync_id": "sess-b", "experiment_id": "ohms-law", "is_draft": False,
            "level1_answers": [], "level1_score": 0, "level1_total": 0, "level1_percentage": 0.0,
            "level2_answers": [], "level3_answers": [{"question_id": "r1", "response_text": "B-нің құпия жауабы"}],
            "self_assessment": None, "submitted_at": "2024-02-01T09:05:00Z",
            "created_at": "2024-02-01T09:05:00Z", "updated_at": "2024-02-01T09:05:00Z",
        }],
        headers=student_b,
    )

    return {"teacher_a": teacher_a, "teacher_b": teacher_b, "student_a": student_a, "student_b": student_b}


# ---- Teacher authorization (8-13) -------------------------------------------


def test_teacher_a_can_read_own_classroom(client, two_teacher_two_classroom_world) -> None:
    headers = two_teacher_two_classroom_world["teacher_a"]
    pulled = client.get("/api/v1/sync/classrooms", headers=headers).json()["items"]
    assert "ca" in {item["sync_id"] for item in pulled}


def test_teacher_a_cannot_read_teacher_b_only_classroom(client, two_teacher_two_classroom_world) -> None:
    headers = two_teacher_two_classroom_world["teacher_a"]
    pulled = client.get("/api/v1/sync/classrooms", headers=headers).json()["items"]
    assert "cb" not in {item["sync_id"] for item in pulled}


def test_teacher_a_can_read_own_students(client, two_teacher_two_classroom_world) -> None:
    headers = two_teacher_two_classroom_world["teacher_a"]
    pulled = client.get("/api/v1/sync/students", headers=headers).json()["items"]
    assert "sa" in {item["sync_id"] for item in pulled}


def test_teacher_a_cannot_read_unrelated_students(client, two_teacher_two_classroom_world) -> None:
    headers = two_teacher_two_classroom_world["teacher_a"]
    pulled = client.get("/api/v1/sync/students", headers=headers).json()["items"]
    assert "sb" not in {item["sync_id"] for item in pulled}


def test_teacher_a_can_read_and_review_authorized_submission(client, two_teacher_two_classroom_world) -> None:
    headers = two_teacher_two_classroom_world["teacher_a"]

    pulled_feedback = client.get("/api/v1/sync/feedback-results", headers=headers).json()["items"]
    assert any(item["sync_id"] == "sess-a" for item in pulled_feedback)

    response = client.post(
        "/api/v1/sync/teacher-assessments",
        json=[{"sync_id": "sess-a", "score": 8, "comment": "Жақсы", "reviewed": True, "updated_at": "2024-02-01T10:00:00Z"}],
        headers=headers,
    )
    assert response.json()["results"][0]["status"] == "upserted"


def test_teacher_a_cannot_review_unauthorized_submission(client, two_teacher_two_classroom_world) -> None:
    headers = two_teacher_two_classroom_world["teacher_a"]

    pulled_feedback = client.get("/api/v1/sync/feedback-results", headers=headers).json()["items"]
    assert not any(item["sync_id"] == "sess-b" for item in pulled_feedback)

    response = client.post(
        "/api/v1/sync/teacher-assessments",
        json=[{"sync_id": "sess-b", "score": 5, "comment": "unauthorized", "reviewed": True, "updated_at": "2024-02-01T10:00:00Z"}],
        headers=headers,
    )
    assert response.status_code == 403


# ---- Student authorization (14-18) ------------------------------------------


def test_student_a_can_read_own_data(client, two_teacher_two_classroom_world) -> None:
    headers = two_teacher_two_classroom_world["student_a"]

    sessions = client.get("/api/v1/sync/sessions", headers=headers).json()  # ok even if empty, no session row pushed
    feedback = client.get("/api/v1/sync/feedback-results", headers=headers).json()["items"]
    assert any(item["sync_id"] == "sess-a" for item in feedback)


def test_student_a_cannot_read_student_b_private_data(client, two_teacher_two_classroom_world) -> None:
    headers = two_teacher_two_classroom_world["student_a"]

    feedback = client.get("/api/v1/sync/feedback-results", headers=headers).json()["items"]
    assert not any(item["sync_id"] == "sess-b" for item in feedback)

    students = client.get("/api/v1/sync/students", headers=headers).json()["items"]
    assert {item["sync_id"] for item in students} == {"sa"}

    classrooms = client.get("/api/v1/sync/classrooms", headers=headers).json()["items"]
    assert {item["sync_id"] for item in classrooms} == {"ca"}


def test_student_a_can_submit_own_experiment_feedback(client, two_teacher_two_classroom_world) -> None:
    headers = two_teacher_two_classroom_world["student_a"]

    response = client.post(
        "/api/v1/sync/feedback-results",
        json=[{
            "sync_id": "sess-a", "experiment_id": "ohms-law", "is_draft": False,
            "level1_answers": [], "level1_score": 1, "level1_total": 1, "level1_percentage": 100.0,
            "level2_answers": [], "level3_answers": [], "self_assessment": 5,
            "submitted_at": "2024-02-01T09:10:00Z", "created_at": "2024-02-01T09:05:00Z",
            "updated_at": "2024-02-01T09:10:00Z",
        }],
        headers=headers,
    )

    assert response.json()["results"][0]["status"] == "upserted"


def test_student_a_cannot_submit_as_student_b(client, two_teacher_two_classroom_world) -> None:
    headers = two_teacher_two_classroom_world["student_a"]

    response = client.post(
        "/api/v1/sync/session-students",
        json=[{
            "session_sync_id": "sess-fraud", "student_sync_id": "sb", "classroom_sync_id": "cb",
            "experiment_id": "ohms-law", "linked_at": "2024-02-01T09:00:00Z",
        }],
        headers=headers,
    )

    assert response.status_code == 403


def test_student_cannot_write_teacher_assessment_fields(client, two_teacher_two_classroom_world) -> None:
    headers = two_teacher_two_classroom_world["student_a"]

    response = client.post(
        "/api/v1/sync/teacher-assessments",
        json=[{"sync_id": "sess-a", "score": 10, "comment": "self-graded", "reviewed": True, "updated_at": "2024-02-01T09:30:00Z"}],
        headers=headers,
    )

    assert response.status_code == 403
