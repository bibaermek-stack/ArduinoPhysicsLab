"""api.sync — §9 "API Contract": versioned sync routes.

    POST /api/v1/sync/teachers            (batch upsert, sync_id-негізді)
    GET  /api/v1/sync/teachers?updated_since=...&limit=...
    POST /api/v1/sync/classrooms
    GET  /api/v1/sync/classrooms?updated_since=...&limit=...
    POST /api/v1/sync/students
    GET  /api/v1/sync/students?updated_since=...&limit=...
    POST /api/v1/sync/teacher-classrooms
    GET  /api/v1/sync/teacher-classrooms?updated_since=...&limit=...
    POST /api/v1/sync/sessions                          (§ Phase 2)
    GET  /api/v1/sync/sessions?updated_since=...&limit=...
    POST /api/v1/sync/session-students
    GET  /api/v1/sync/session-students?updated_since=...&limit=...
    POST /api/v1/sync/feedback-results
    GET  /api/v1/sync/feedback-results?updated_since=...&limit=...
    POST /api/v1/sync/teacher-assessments
    GET  /api/v1/sync/teacher-assessments?updated_since=...&limit=...
    POST /api/v1/sync/measurement-batches                (§ Phase 4)
    GET  /api/v1/sync/measurement-batches?updated_since=...&limit=...
    POST /api/v1/sync/teacher-notes                      (§ Phase 7)
    GET  /api/v1/sync/teacher-notes?updated_since=...&limit=...

§4 "Server-Side Authorization" (Phase 3, HARD requirement): every route
now depends on ``get_current_user()`` (§ ``api/deps.py``) AND applies
``server/app/services/authorization.py`` rules. Two distinct
enforcement shapes, deliberately different:

- **Pull (GET)**: NEVER hard-rejects — always 200 with a query result
  FILTERED to what the caller may see (§ "return only records visible
  to the authenticated user"). This is because ``SyncEngine._pull_all()``
  pulls EVERY entity type in ``PUSH_ORDER`` unconditionally regardless
  of the local user's role (§ audit) — a student's routine sync cycle
  also calls ``GET /teachers``, and a hard 403 there would turn every
  ordinary student sync into a permanent ``SYNC_ERROR``. An empty (or
  self-only) result set is the correct "nothing relevant to you" answer.
- **Push (POST)**: hard 403 (whole request, not per-item) on ANY
  ownership violation. A legitimate client's outbox only ever contains
  entities its own role actually created (§ audit — students never
  write teacher/classroom data locally), so a real client never hits
  this; a 403 here means either an attack or a client bug, and the
  batch-partial-success semantics reserved for ``RelationshipError``
  (§ "not yet possible, might work later" — a missing parent that may
  sync in shortly) do not apply to authorization (§ "never retryable").
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from server.app.api.deps import get_current_user, require_api_key
from server.app.db.session import get_db
from server.app.models.sync_models import StudentRecord, TeacherClassroomLinkRecord
from server.app.schemas.sync import (
    ClassroomOut,
    ClassroomPayload,
    FeedbackResultOut,
    FeedbackResultPayload,
    MeasurementBatchPayload,
    PullResponse,
    SessionOut,
    SessionPayload,
    SessionStudentLinkOut,
    SessionStudentLinkPayload,
    StudentOut,
    StudentPayload,
    TeacherAssessmentOut,
    TeacherAssessmentPayload,
    TeacherClassroomOut,
    TeacherClassroomPayload,
    TeacherNoteOut,
    TeacherNotePayload,
    TeacherOut,
    TeacherPayload,
    UpsertBatchResponse,
    UpsertResult,
)
from server.app.services import authorization, sync_service
from server.app.services.auth_service import CurrentUser
from server.app.services.sync_service import RelationshipError

router = APIRouter(
    prefix="/sync", tags=["sync"], dependencies=[Depends(require_api_key)]
)

_DEFAULT_PULL_LIMIT = 500


def _forbidden(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---- Teachers --------------------------------------------------------------


@router.post("/teachers", response_model=UpsertBatchResponse)
def upsert_teachers(
    payloads: list[TeacherPayload],
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> UpsertBatchResponse:
    for payload in payloads:
        if not current_user.is_teacher or payload.sync_id != current_user.sync_id:
            raise _forbidden("A teacher may only upsert their own teacher record")
    results: list[UpsertResult] = []
    for payload in payloads:
        try:
            record = sync_service.upsert_teacher(db, payload)
            results.append(UpsertResult(sync_id=payload.sync_id, status="upserted", server_revision=record.server_revision))
        except RelationshipError as error:
            results.append(UpsertResult(sync_id=payload.sync_id, status="error", error=str(error)))
    db.commit()
    return UpsertBatchResponse(results=results)


@router.get("/teachers", response_model=PullResponse)
def pull_teachers(
    updated_since: datetime | None = Query(default=None),
    limit: int = Query(default=_DEFAULT_PULL_LIMIT, le=2000),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> PullResponse:
    records = sync_service.pull_teachers(db, updated_since, limit)
    if current_user.is_teacher:
        records = [record for record in records if record.sync_id == current_user.sync_id]
    else:
        records = []  # § student: teacher records-ке ешбір қатысы жоқ
    items = [TeacherOut.model_validate(record, from_attributes=True).model_dump(mode="json") for record in records]
    return PullResponse(server_time=_now(), items=items)


# ---- Classrooms --------------------------------------------------------------


@router.post("/classrooms", response_model=UpsertBatchResponse)
def upsert_classrooms(
    payloads: list[ClassroomPayload],
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> UpsertBatchResponse:
    if not current_user.is_teacher:
        raise _forbidden("Only teachers may upsert classrooms")
    for payload in payloads:
        if not authorization.teacher_can_touch_classroom(db, current_user.sync_id, payload.sync_id):
            raise _forbidden(f"Not assigned to classroom '{payload.sync_id}'")
    results: list[UpsertResult] = []
    for payload in payloads:
        try:
            record = sync_service.upsert_classroom(db, payload)
            results.append(UpsertResult(sync_id=payload.sync_id, status="upserted", server_revision=record.server_revision))
        except RelationshipError as error:
            results.append(UpsertResult(sync_id=payload.sync_id, status="error", error=str(error)))
    db.commit()
    return UpsertBatchResponse(results=results)


@router.get("/classrooms", response_model=PullResponse)
def pull_classrooms(
    updated_since: datetime | None = Query(default=None),
    limit: int = Query(default=_DEFAULT_PULL_LIMIT, le=2000),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> PullResponse:
    records = sync_service.pull_classrooms(db, updated_since, limit)
    if current_user.is_teacher:
        allowed = authorization.teacher_visible_classroom_ids(
            db, current_user.sync_id, {record.sync_id for record in records}
        )
        records = [record for record in records if record.sync_id in allowed]
    else:
        own_classroom_id = authorization.get_student_classroom_id(db, current_user.sync_id)
        records = [record for record in records if record.sync_id == own_classroom_id]
    items = [ClassroomOut.model_validate(record, from_attributes=True).model_dump(mode="json") for record in records]
    return PullResponse(server_time=_now(), items=items)


# ---- Students --------------------------------------------------------------


@router.post("/students", response_model=UpsertBatchResponse)
def upsert_students(
    payloads: list[StudentPayload],
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> UpsertBatchResponse:
    if not current_user.is_teacher:
        raise _forbidden("Only teachers may upsert student records")
    for payload in payloads:
        if not authorization.teacher_can_touch_classroom(db, current_user.sync_id, payload.classroom_sync_id):
            raise _forbidden(f"Not assigned to classroom '{payload.classroom_sync_id}'")
    results: list[UpsertResult] = []
    for payload in payloads:
        try:
            record = sync_service.upsert_student(db, payload)
            results.append(UpsertResult(sync_id=payload.sync_id, status="upserted", server_revision=record.server_revision))
        except RelationshipError as error:
            results.append(UpsertResult(sync_id=payload.sync_id, status="error", error=str(error)))
    db.commit()
    return UpsertBatchResponse(results=results)


@router.get("/students", response_model=PullResponse)
def pull_students(
    updated_since: datetime | None = Query(default=None),
    limit: int = Query(default=_DEFAULT_PULL_LIMIT, le=2000),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> PullResponse:
    records = sync_service.pull_students(db, updated_since, limit)
    if current_user.is_teacher:
        allowed = authorization.teacher_visible_classroom_ids(
            db, current_user.sync_id, {record.classroom_sync_id for record in records if record.classroom_sync_id}
        )
        records = [record for record in records if record.classroom_sync_id in allowed]
    else:
        records = [record for record in records if record.sync_id == current_user.sync_id]
    items = [StudentOut.model_validate(record, from_attributes=True).model_dump(mode="json") for record in records]
    return PullResponse(server_time=_now(), items=items)


# ---- Teacher <-> Classroom assignments --------------------------------------


@router.post("/teacher-classrooms", response_model=UpsertBatchResponse)
def upsert_teacher_classrooms(
    payloads: list[TeacherClassroomPayload],
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> UpsertBatchResponse:
    for payload in payloads:
        if not current_user.is_teacher or payload.teacher_sync_id != current_user.sync_id:
            raise _forbidden("A teacher may only set their own classroom assignment set")
    results: list[UpsertResult] = []
    for payload in payloads:
        try:
            record = sync_service.upsert_teacher_classroom(db, payload)
            results.append(
                UpsertResult(sync_id=payload.teacher_sync_id, status="upserted", server_revision=record.server_revision)
            )
        except RelationshipError as error:
            results.append(UpsertResult(sync_id=payload.teacher_sync_id, status="error", error=str(error)))
    db.commit()
    return UpsertBatchResponse(results=results)


@router.get("/teacher-classrooms", response_model=PullResponse)
def pull_teacher_classrooms(
    updated_since: datetime | None = Query(default=None),
    limit: int = Query(default=_DEFAULT_PULL_LIMIT, le=2000),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> PullResponse:
    records = sync_service.pull_teacher_classrooms(db, updated_since, limit)
    if current_user.is_teacher:
        records = [record for record in records if record.teacher_sync_id == current_user.sync_id]
    else:
        records = []
    items = [
        {
            "teacher_sync_id": record.teacher_sync_id,
            "classroom_sync_ids": json.loads(record.classroom_sync_ids_json),
            "updated_at": record.updated_at.isoformat(),
            "server_revision": record.server_revision,
        }
        for record in records
    ]
    return PullResponse(server_time=_now(), items=items)


# ---- Phase 2: Experiment Session + Results + Feedback Cloud Sync ---------


@router.post("/sessions", response_model=UpsertBatchResponse)
def upsert_sessions(
    payloads: list[SessionPayload],
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> UpsertBatchResponse:
    for payload in payloads:
        link = authorization.get_session_link(db, payload.sync_id)
        if link is None:
            continue  # § жаңа сессия — ЕШБІР ownership тексеруге болмайды (§ докстринг)
        if current_user.is_teacher:
            if not authorization.teacher_can_access_classroom(db, current_user.sync_id, link.classroom_sync_id):
                raise _forbidden(f"Not authorized for session '{payload.sync_id}'")
        elif link.student_sync_id != current_user.sync_id:
            raise _forbidden(f"Not authorized for session '{payload.sync_id}'")
    results: list[UpsertResult] = []
    for payload in payloads:
        try:
            record = sync_service.upsert_session(db, payload)
            results.append(UpsertResult(sync_id=payload.sync_id, status="upserted", server_revision=record.server_revision))
        except RelationshipError as error:
            results.append(UpsertResult(sync_id=payload.sync_id, status="error", error=str(error)))
    db.commit()
    return UpsertBatchResponse(results=results)


@router.get("/sessions", response_model=PullResponse)
def pull_sessions(
    updated_since: datetime | None = Query(default=None),
    limit: int = Query(default=_DEFAULT_PULL_LIMIT, le=2000),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> PullResponse:
    records = sync_service.pull_sessions(db, updated_since, limit)
    records = [
        record
        for record in records
        if authorization.current_user_can_access_session(db, current_user, record.sync_id)
    ]
    items = [SessionOut.model_validate(record, from_attributes=True).model_dump(mode="json") for record in records]
    return PullResponse(server_time=_now(), items=items)


@router.post("/session-students", response_model=UpsertBatchResponse)
def upsert_session_students(
    payloads: list[SessionStudentLinkPayload],
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> UpsertBatchResponse:
    for payload in payloads:
        if current_user.is_student:
            if payload.student_sync_id != current_user.sync_id:
                raise _forbidden("A student may only link their own sessions to themselves")
        elif current_user.is_teacher:
            if not authorization.teacher_can_access_classroom(db, current_user.sync_id, payload.classroom_sync_id):
                raise _forbidden(f"Not assigned to classroom '{payload.classroom_sync_id}'")
    results: list[UpsertResult] = []
    for payload in payloads:
        try:
            record = sync_service.upsert_session_student_link(db, payload)
            results.append(
                UpsertResult(sync_id=payload.session_sync_id, status="upserted", server_revision=record.server_revision)
            )
        except RelationshipError as error:
            results.append(UpsertResult(sync_id=payload.session_sync_id, status="error", error=str(error)))
    db.commit()
    return UpsertBatchResponse(results=results)


@router.get("/session-students", response_model=PullResponse)
def pull_session_students(
    updated_since: datetime | None = Query(default=None),
    limit: int = Query(default=_DEFAULT_PULL_LIMIT, le=2000),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> PullResponse:
    records = sync_service.pull_session_student_links(db, updated_since, limit)
    if current_user.is_teacher:
        allowed = authorization.teacher_allowed_classroom_ids(db, current_user.sync_id)
        records = [record for record in records if record.classroom_sync_id in allowed]
    else:
        records = [record for record in records if record.student_sync_id == current_user.sync_id]
    items = [
        SessionStudentLinkOut.model_validate(record, from_attributes=True).model_dump(mode="json")
        for record in records
    ]
    return PullResponse(server_time=_now(), items=items)


# ---- Feedback result (student half) -----------------------------------------


@router.post("/feedback-results", response_model=UpsertBatchResponse)
def upsert_feedback_results(
    payloads: list[FeedbackResultPayload],
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> UpsertBatchResponse:
    # § "Preserve the feedback_result/teacher_assessment split — a
    # teacher must not overwrite the student-owned half" (§4): ТЕК
    # STUDENT рөлі жаза алады.
    if not current_user.is_student:
        raise _forbidden("Only the owning student may write feedback_result content")
    for payload in payloads:
        if not authorization.student_owns_session(db, current_user.sync_id, payload.sync_id):
            raise _forbidden(f"Not authorized for session '{payload.sync_id}'")
    results: list[UpsertResult] = []
    for payload in payloads:
        try:
            record = sync_service.upsert_feedback_result(db, payload)
            results.append(UpsertResult(sync_id=payload.sync_id, status="upserted", server_revision=record.server_revision))
        except RelationshipError as error:
            results.append(UpsertResult(sync_id=payload.sync_id, status="error", error=str(error)))
    db.commit()
    return UpsertBatchResponse(results=results)


@router.get("/feedback-results", response_model=PullResponse)
def pull_feedback_results(
    updated_since: datetime | None = Query(default=None),
    limit: int = Query(default=_DEFAULT_PULL_LIMIT, le=2000),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> PullResponse:
    records = sync_service.pull_feedback_results(db, updated_since, limit)
    records = [
        record
        for record in records
        if authorization.current_user_can_access_session(db, current_user, record.sync_id)
    ]
    items = [
        {
            "sync_id": record.sync_id,
            "experiment_id": record.experiment_id,
            "is_draft": record.is_draft,
            "level1_answers": json.loads(record.level1_answers_json),
            "level1_score": record.level1_score,
            "level1_total": record.level1_total,
            "level1_percentage": record.level1_percentage,
            "level2_answers": json.loads(record.level2_answers_json),
            "level3_answers": json.loads(record.level3_answers_json),
            "self_assessment": record.self_assessment,
            "submitted_at": record.submitted_at.isoformat() if record.submitted_at else None,
            "created_at": record.created_at.isoformat(),
            "updated_at": record.updated_at.isoformat(),
            "server_revision": record.server_revision,
        }
        for record in records
    ]
    return PullResponse(server_time=_now(), items=items)


# ---- Phase 4: Raw Arduino Measurement Cloud Sync -----------------------------


def _isoformat_utc(value: datetime) -> str:
    """§ Phase 4 "Raw Data Fidelity" түзетуі: SQLite + SQLAlchemy
    ``DateTime(timezone=True)`` НАҚТЫ tzinfo-ты сақтамайды (§ белгілі
    SQLite-тың нақты TZ-aware типі жоқ шектеуі — PostgreSQL-де бұл
    мәселе жоқ). Дерекқордан оқылған соң ``tzinfo`` жоғалса, мән
    ӨЗІ әрқашан UTC (§ жобаның бүкіл конвенциясы), сондықтан жай ғана
    қайта тіркеледі — САНДЫҚ мән ЕШҚАШАН өзгермейді. Түзетусіз, клиент
    ``Measurement.__post_init__`` naive timestamp-ты ValueError-мен
    қабылдамайды, ал бұл қате ``_row_to_measurement()``-те ҮНСІЗ
    жұтылады — pull арқылы алынған БАРЛЫҚ measurement жолы жоғалады."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _measurement_batch_item(record) -> dict:
    return {
        "sync_id": record.sync_id,
        "session_sync_id": record.session_sync_id,
        "sequence_start": record.sequence_start,
        "sequence_end": record.sequence_end,
        "sample_count": record.sample_count,
        "created_at": _isoformat_utc(record.created_at),
        "measurements": [
            {
                "sequence_no": item.sequence_no,
                "timestamp": _isoformat_utc(item.timestamp),
                "values": json.loads(item.values_json),
                "derived_values": json.loads(item.derived_values_json),
                "warnings": json.loads(item.warnings_json),
            }
            for item in record.measurements
        ],
        "server_revision": record.server_revision,
    }


@router.post("/measurement-batches", response_model=UpsertBatchResponse)
def upsert_measurement_batches(
    payloads: list[MeasurementBatchPayload],
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> UpsertBatchResponse:
    # § "Student: may upload... only for their own sessions" — raw
    # measurement-ды ТЕК студент жүктейді (§ мұғалім өлшеу жасамайды,
    # тек оқиды, ``feedback-results`` push-імен БІРДЕЙ рөл шектеуі).
    if not current_user.is_student:
        raise _forbidden("Only the owning student may upload measurement batches")
    for payload in payloads:
        if not authorization.student_owns_session(db, current_user.sync_id, payload.session_sync_id):
            raise _forbidden(f"Not authorized for session '{payload.session_sync_id}'")
    results: list[UpsertResult] = []
    for payload in payloads:
        try:
            record = sync_service.upsert_measurement_batch(db, payload)
            results.append(
                UpsertResult(sync_id=payload.sync_id, status="upserted", server_revision=record.server_revision)
            )
        except RelationshipError as error:
            results.append(UpsertResult(sync_id=payload.sync_id, status="error", error=str(error)))
    db.commit()
    return UpsertBatchResponse(results=results)


@router.get("/measurement-batches", response_model=PullResponse)
def pull_measurement_batches(
    updated_since: datetime | None = Query(default=None),
    limit: int = Query(default=_DEFAULT_PULL_LIMIT, le=2000),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> PullResponse:
    records = sync_service.pull_measurement_batches(db, updated_since, limit)
    records = [
        record
        for record in records
        if authorization.current_user_can_access_session(db, current_user, record.session_sync_id)
    ]
    items = [_measurement_batch_item(record) for record in records]
    return PullResponse(server_time=_now(), items=items)


# ---- Teacher assessment (teacher half) --------------------------------------


@router.post("/teacher-assessments", response_model=UpsertBatchResponse)
def upsert_teacher_assessments(
    payloads: list[TeacherAssessmentPayload],
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> UpsertBatchResponse:
    # § "A student must not be able to write teacher assessment fields" (§4).
    if not current_user.is_teacher:
        raise _forbidden("Only a teacher may write teacher_assessment content")
    for payload in payloads:
        if not authorization.teacher_can_access_session(db, current_user.sync_id, payload.sync_id):
            raise _forbidden(f"Not authorized for session '{payload.sync_id}'")
    results: list[UpsertResult] = []
    for payload in payloads:
        try:
            record = sync_service.upsert_teacher_assessment(db, payload)
            results.append(
                UpsertResult(sync_id=payload.sync_id, status="upserted", server_revision=record.teacher_server_revision)
            )
        except RelationshipError as error:
            results.append(UpsertResult(sync_id=payload.sync_id, status="error", error=str(error)))
    db.commit()
    return UpsertBatchResponse(results=results)


@router.get("/teacher-assessments", response_model=PullResponse)
def pull_teacher_assessments(
    updated_since: datetime | None = Query(default=None),
    limit: int = Query(default=_DEFAULT_PULL_LIMIT, le=2000),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> PullResponse:
    records = sync_service.pull_teacher_assessments(db, updated_since, limit)
    records = [
        record
        for record in records
        if authorization.current_user_can_access_session(db, current_user, record.sync_id)
    ]
    items = [
        {
            "sync_id": record.sync_id,
            "score": record.teacher_score,
            "comment": record.teacher_comment,
            "reviewed": record.teacher_reviewed,
            "updated_at": record.teacher_updated_at.isoformat(),
            "server_revision": record.teacher_server_revision,
        }
        for record in records
    ]
    return PullResponse(server_time=_now(), items=items)


# ---- Phase 7: Teacher Actions, Feedback Delivery, and Session History -------


@router.post("/teacher-notes", response_model=UpsertBatchResponse)
def upsert_teacher_notes(
    payloads: list[TeacherNotePayload],
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> UpsertBatchResponse:
    # § "teacher-initiated only" — тек мұғалім жаза алады, тек ӨЗ
    # sync_id-мен (§ ``upsert_teachers()``-пен БІРДЕЙ "may only act as
    # themselves" ережесі), ТЕК ӨЗІ қатынайтын оқушыға (§ ``teacher_can_
    # access_student()`` — ``measurement-batches``/``feedback-results``-
    # пен БІРДЕЙ ортақ авторизация примитиві, жаңа ереже ЖОҚ).
    if not current_user.is_teacher:
        raise _forbidden("Only a teacher may write teacher_note content")
    for payload in payloads:
        if payload.teacher_sync_id != current_user.sync_id:
            raise _forbidden("A teacher may only send notes as themselves")
        if not authorization.teacher_can_access_student(db, current_user.sync_id, payload.student_sync_id):
            raise _forbidden(f"Not authorized for student '{payload.student_sync_id}'")
    results: list[UpsertResult] = []
    for payload in payloads:
        try:
            record = sync_service.upsert_teacher_note(db, payload)
            results.append(
                UpsertResult(sync_id=payload.sync_id, status="upserted", server_revision=record.server_revision)
            )
        except RelationshipError as error:
            results.append(UpsertResult(sync_id=payload.sync_id, status="error", error=str(error)))
    db.commit()
    return UpsertBatchResponse(results=results)


@router.get("/teacher-notes", response_model=PullResponse)
def pull_teacher_notes(
    updated_since: datetime | None = Query(default=None),
    limit: int = Query(default=_DEFAULT_PULL_LIMIT, le=2000),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> PullResponse:
    # § pull scoping: мұғалім ТЕК ӨЗІ жіберген пікірлерді алады (§
    # "own sent notes", басқа мұғалімнің жеке пікірі ортақ емес);
    # оқушы ТЕК ӨЗІНЕ жіберілген пікірлерді алады.
    records = sync_service.pull_teacher_notes(db, updated_since, limit)
    if current_user.is_teacher:
        records = [record for record in records if record.teacher_sync_id == current_user.sync_id]
    else:
        records = [record for record in records if record.student_sync_id == current_user.sync_id]
    items = [
        TeacherNoteOut.model_validate(record, from_attributes=True).model_dump(mode="json")
        for record in records
    ]
    return PullResponse(server_time=_now(), items=items)
