"""§35 "SERVER" тесттері (Phase 2: Experiment Session + Results +
Feedback Cloud Sync), Phase 3 авторизациясымен: session/session-
student/feedback-result/teacher-assessment upsert idempotency,
relationship validation, incremental pull, unknown experiment_id
graceful acceptance — ЕНДІ ``teacher_auth_headers``/``student_auth_
headers`` арқылы (§4 "every protected sync operation must enforce
ownership/relationship rules on the SERVER").
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
    "experiment_id": "unknown-future-experiment-id",
    "experiment_title": "Ohm's Law",
    "experiment_display_number": 3,
    "started_at": "2024-02-01T10:00:00Z",
    "ended_at": "2024-02-01T10:05:00Z",
    "status": "finalized",
    "measurement_count": 42,
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
_FEEDBACK_PAYLOAD = {
    "sync_id": "sess1",
    "experiment_id": "ohms-law",
    "is_draft": False,
    "level1_answers": [{"question_id": "q1", "selected_option_index": 0}],
    "level1_score": 1,
    "level1_total": 1,
    "level1_percentage": 100.0,
    "level2_answers": [],
    "level3_answers": [{"question_id": "r1", "response_text": "Қорытынды мәтін"}],
    "self_assessment": 4,
    "submitted_at": "2024-02-01T10:10:00Z",
    "created_at": "2024-02-01T10:06:00Z",
    "updated_at": "2024-02-01T10:10:00Z",
}
_ASSESSMENT_PAYLOAD = {
    "sync_id": "sess1",
    "score": 9,
    "comment": "Өте жақсы жұмыс",
    "reviewed": True,
    "updated_at": "2024-02-01T11:00:00Z",
}


@pytest.fixture()
def with_student(client, teacher_auth_headers):
    """§ Мұғалім c1-ді құрады+тағайындалады, s1 оқушысын қосады."""
    client.post("/api/v1/sync/classrooms", json=[_CLASSROOM_PAYLOAD], headers=teacher_auth_headers)
    client.post("/api/v1/sync/students", json=[_STUDENT_PAYLOAD], headers=teacher_auth_headers)
    client.post(
        "/api/v1/sync/teacher-classrooms",
        json=[{"teacher_sync_id": "t1", "classroom_sync_ids": ["c1"], "updated_at": "2024-01-01T00:00:00Z"}],
        headers=teacher_auth_headers,
    )
    return client


@pytest.fixture()
def with_session_link(with_student, student_auth_headers):
    """§ Оқушы ӨЗ сессиясын байланыстырады — session/feedback/
    assessment "иелік" сынауларының негізі (§ ``session_student_link``
    жоқ болса, ешкім сессияны көре алмайды, § authorization.py)."""
    with_student.post("/api/v1/sync/session-students", json=[_LINK_PAYLOAD], headers=student_auth_headers)
    return with_student


# ---- Sessions -------------------------------------------------------------


def test_upsert_new_session_does_not_require_known_experiment_id(client, teacher_auth_headers) -> None:
    """§26 "Version Compatibility": каталогта белгісіз ``experiment_id``
    жай ғана мөлдір жол ретінде сақталады. Жаңа (байланыссыз) сессия —
    ЕШБІР ownership тексерусіз рұқсат етіледі (§ authorization.py
    докстрингі)."""
    response = client.post("/api/v1/sync/sessions", json=[_SESSION_PAYLOAD], headers=teacher_auth_headers)

    assert response.json()["results"][0]["status"] == "upserted"


def test_session_pull_requires_a_link_to_be_visible(client, teacher_auth_headers) -> None:
    """§4 "safe default": байланысы жоқ сессия ЕШКІМГЕ көрінбейді."""
    client.post("/api/v1/sync/sessions", json=[_SESSION_PAYLOAD], headers=teacher_auth_headers)

    pulled = client.get("/api/v1/sync/sessions", headers=teacher_auth_headers).json()["items"]

    assert pulled == []


def test_session_visible_to_owning_student_and_authorized_teacher(with_session_link, student_auth_headers, teacher_auth_headers) -> None:
    with_session_link.post("/api/v1/sync/sessions", json=[_SESSION_PAYLOAD], headers=teacher_auth_headers)

    student_pulled = with_session_link.get("/api/v1/sync/sessions", headers=student_auth_headers).json()["items"]
    teacher_pulled = with_session_link.get("/api/v1/sync/sessions", headers=teacher_auth_headers).json()["items"]

    assert [item["sync_id"] for item in student_pulled] == ["sess1"]
    assert [item["sync_id"] for item in teacher_pulled] == ["sess1"]


def test_session_upsert_idempotent_by_sync_id(with_session_link, teacher_auth_headers) -> None:
    with_session_link.post("/api/v1/sync/sessions", json=[_SESSION_PAYLOAD], headers=teacher_auth_headers)
    with_session_link.post(
        "/api/v1/sync/sessions",
        json=[{**_SESSION_PAYLOAD, "measurement_count": 99}],
        headers=teacher_auth_headers,
    )

    pulled = with_session_link.get("/api/v1/sync/sessions", headers=teacher_auth_headers).json()["items"]
    assert len(pulled) == 1
    assert pulled[0]["measurement_count"] == 99
    assert pulled[0]["server_revision"] == 2


def test_session_pull_incremental_by_updated_since(with_session_link, teacher_auth_headers) -> None:
    with_session_link.post("/api/v1/sync/sessions", json=[_SESSION_PAYLOAD], headers=teacher_auth_headers)
    first_pull = with_session_link.get("/api/v1/sync/sessions", headers=teacher_auth_headers).json()
    cursor = first_pull["server_time"]

    second_pull = with_session_link.get(
        "/api/v1/sync/sessions", params={"updated_since": cursor}, headers=teacher_auth_headers
    ).json()

    assert second_pull["items"] == []


# ---- Session <-> Student link ----------------------------------------------


def test_upsert_session_link_requires_existing_student(client, teacher_auth_headers) -> None:
    client.post("/api/v1/sync/classrooms", json=[_CLASSROOM_PAYLOAD], headers=teacher_auth_headers)
    client.post(
        "/api/v1/sync/teacher-classrooms",
        json=[{"teacher_sync_id": "t1", "classroom_sync_ids": ["c1"], "updated_at": "2024-01-01T00:00:00Z"}],
        headers=teacher_auth_headers,
    )

    response = client.post(
        "/api/v1/sync/session-students", json=[_LINK_PAYLOAD], headers=teacher_auth_headers
    )

    result = response.json()["results"][0]
    assert result["status"] == "error"
    assert "student_sync_id" in result["error"]


def test_student_can_link_own_session_without_a_session_row(with_student, student_auth_headers) -> None:
    """§4/§11: жергілікті домен байланысты сессиясыз да заңды деп таниды
    (§ ``derive_status(has_link=True, measurement_count=0) -> IN_
    PROGRESS``) — ``session_sync_id`` FK ретінде талап ЕТІЛМЕЙДІ."""
    response = with_student.post(
        "/api/v1/sync/session-students", json=[_LINK_PAYLOAD], headers=student_auth_headers
    )

    assert response.json()["results"][0]["status"] == "upserted"
    pulled = with_student.get("/api/v1/sync/session-students", headers=student_auth_headers).json()["items"]
    assert pulled[0]["student_sync_id"] == "s1"


def test_student_cannot_link_another_students_session(with_student, student_auth_headers) -> None:
    """§4 "Student X may submit/update only Student X's own... data"."""
    other_student_link = {**_LINK_PAYLOAD, "student_sync_id": "some-other-student"}

    response = with_student.post(
        "/api/v1/sync/session-students", json=[other_student_link], headers=student_auth_headers
    )

    assert response.status_code == 403


def test_session_link_upsert_idempotent(with_student, student_auth_headers) -> None:
    with_student.post("/api/v1/sync/session-students", json=[_LINK_PAYLOAD], headers=student_auth_headers)
    with_student.post("/api/v1/sync/session-students", json=[_LINK_PAYLOAD], headers=student_auth_headers)

    pulled = with_student.get("/api/v1/sync/session-students", headers=student_auth_headers).json()["items"]
    assert len(pulled) == 1
    assert pulled[0]["server_revision"] == 2


# ---- Feedback result --------------------------------------------------------


def test_teacher_cannot_write_feedback_result(with_session_link, teacher_auth_headers) -> None:
    """§4/§6 "must not overwrite the student-owned half"."""
    response = with_session_link.post(
        "/api/v1/sync/feedback-results", json=[_FEEDBACK_PAYLOAD], headers=teacher_auth_headers
    )

    assert response.status_code == 403


def test_student_upserts_own_feedback_result(with_session_link, student_auth_headers) -> None:
    response = with_session_link.post(
        "/api/v1/sync/feedback-results", json=[_FEEDBACK_PAYLOAD], headers=student_auth_headers
    )

    assert response.json()["results"][0]["status"] == "upserted"
    pulled = with_session_link.get("/api/v1/sync/feedback-results", headers=student_auth_headers).json()["items"]
    assert pulled[0]["level1_score"] == 1
    assert pulled[0]["level3_answers"][0]["response_text"] == "Қорытынды мәтін"


def test_feedback_result_upsert_idempotent_by_sync_id(with_session_link, student_auth_headers) -> None:
    with_session_link.post("/api/v1/sync/feedback-results", json=[_FEEDBACK_PAYLOAD], headers=student_auth_headers)
    with_session_link.post(
        "/api/v1/sync/feedback-results",
        json=[{**_FEEDBACK_PAYLOAD, "self_assessment": 5}],
        headers=student_auth_headers,
    )

    pulled = with_session_link.get("/api/v1/sync/feedback-results", headers=student_auth_headers).json()["items"]
    assert len(pulled) == 1
    assert pulled[0]["self_assessment"] == 5
    assert pulled[0]["server_revision"] == 2


def test_teacher_sees_authorized_students_feedback_result(with_session_link, student_auth_headers, teacher_auth_headers) -> None:
    with_session_link.post("/api/v1/sync/feedback-results", json=[_FEEDBACK_PAYLOAD], headers=student_auth_headers)

    pulled = with_session_link.get("/api/v1/sync/feedback-results", headers=teacher_auth_headers).json()["items"]

    assert pulled[0]["sync_id"] == "sess1"


# ---- Teacher assessment -----------------------------------------------------


def test_student_cannot_write_teacher_assessment(with_session_link, student_auth_headers) -> None:
    """§4/§11 "A student must not be able to write teacher assessment
    fields"."""
    response = with_session_link.post(
        "/api/v1/sync/teacher-assessments", json=[_ASSESSMENT_PAYLOAD], headers=student_auth_headers
    )

    assert response.status_code == 403


def test_unauthorized_teacher_cannot_assess_unrelated_session(with_session_link, client) -> None:
    from server.tests.conftest import _bootstrap_login

    other_teacher_headers = _bootstrap_login(
        client, "/api/v1/auth/teacher-login", {"sync_id": "t2", "pin_hash": "hash-t2", "full_name": "Teacher Two"}
    )

    response = with_session_link.post(
        "/api/v1/sync/teacher-assessments", json=[_ASSESSMENT_PAYLOAD], headers=other_teacher_headers
    )

    assert response.status_code == 403


def test_authorized_teacher_upserts_assessment(with_session_link, teacher_auth_headers) -> None:
    response = with_session_link.post(
        "/api/v1/sync/teacher-assessments", json=[_ASSESSMENT_PAYLOAD], headers=teacher_auth_headers
    )

    assert response.json()["results"][0]["status"] == "upserted"


def test_teacher_assessment_score_out_of_range_is_rejected(with_session_link, teacher_auth_headers) -> None:
    """§6 "Do not change the existing 0-10 grading scale" — сервер де
    осы шектеуді валидациялайды."""
    response = with_session_link.post(
        "/api/v1/sync/teacher-assessments",
        json=[{**_ASSESSMENT_PAYLOAD, "score": 11}],
        headers=teacher_auth_headers,
    )

    assert response.status_code == 422  # Pydantic validation error, batch-тан бұрын


def test_teacher_assessment_upsert_idempotent(with_session_link, teacher_auth_headers) -> None:
    with_session_link.post("/api/v1/sync/teacher-assessments", json=[_ASSESSMENT_PAYLOAD], headers=teacher_auth_headers)
    with_session_link.post(
        "/api/v1/sync/teacher-assessments",
        json=[{**_ASSESSMENT_PAYLOAD, "comment": "Түзетілген пікір"}],
        headers=teacher_auth_headers,
    )

    pulled = with_session_link.get("/api/v1/sync/teacher-assessments", headers=teacher_auth_headers).json()["items"]
    assert len(pulled) == 1
    assert pulled[0]["comment"] == "Түзетілген пікір"
    assert pulled[0]["server_revision"] == 2


def test_teacher_assessment_and_feedback_result_do_not_clobber_each_other(
    with_session_link, student_auth_headers, teacher_auth_headers
) -> None:
    """§6/§7: екі тәуелсіз push (студент content + мұғалім бағасы) БІР
    серверлік жолда қатар өмір сүре алуы керек, бірінің упсерты
    екіншісінің бағандарын жоймайды (§ ``FeedbackResultRecord``
    докстрингі)."""
    with_session_link.post("/api/v1/sync/feedback-results", json=[_FEEDBACK_PAYLOAD], headers=student_auth_headers)
    with_session_link.post("/api/v1/sync/teacher-assessments", json=[_ASSESSMENT_PAYLOAD], headers=teacher_auth_headers)

    feedback_pulled = with_session_link.get(
        "/api/v1/sync/feedback-results", headers=student_auth_headers
    ).json()["items"]
    assessment_pulled = with_session_link.get(
        "/api/v1/sync/teacher-assessments", headers=teacher_auth_headers
    ).json()["items"]

    assert feedback_pulled[0]["level1_score"] == 1  # § мұғалім упсерты студент дерегін ЖОЙМАДЫ
    assert assessment_pulled[0]["score"] == 9


def test_teacher_assessment_pull_excludes_unscored_placeholder_rows(with_session_link, student_auth_headers, teacher_auth_headers) -> None:
    """§ пре-инсерт бос shell жолы (§ ``upsert_teacher_assessment()``
    докстрингі) ешқашан teacher-assessments pull-ында ШЫҚПАУЫ керек —
    тек НАҚТЫ бағаланған жолдар."""
    with_session_link.post("/api/v1/sync/feedback-results", json=[_FEEDBACK_PAYLOAD], headers=student_auth_headers)

    pulled = with_session_link.get("/api/v1/sync/teacher-assessments", headers=teacher_auth_headers).json()["items"]

    assert pulled == []


# ---- Malformed payload -------------------------------------------------------


def test_missing_required_field_rejected_with_422(client, teacher_auth_headers) -> None:
    bad_payload = {k: v for k, v in _SESSION_PAYLOAD.items() if k != "started_at"}

    response = client.post("/api/v1/sync/sessions", json=[bad_payload], headers=teacher_auth_headers)

    assert response.status_code == 422
