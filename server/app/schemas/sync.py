"""Pydantic sync payload schemas (§9 "API Contract").

Барлық payload ``sync_id`` қолданады — жергілікті SQLite integer/жол
PK ЕШҚАШАН ЕМЕС (§2). Қатынастар (``classroom_sync_id``) да global
ID-ге сілтейді.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class TeacherPayload(BaseModel):
    sync_id: str = Field(min_length=1)
    full_name: str = Field(min_length=1)
    pin_hash: str = Field(min_length=1)
    is_active: bool = True
    created_at: datetime
    updated_at: datetime


class TeacherOut(TeacherPayload):
    server_revision: int


class ClassroomPayload(BaseModel):
    sync_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    academic_year: str = ""
    description: str = ""
    is_archived: bool = False
    created_at: datetime
    updated_at: datetime


class ClassroomOut(ClassroomPayload):
    server_revision: int


class StudentPayload(BaseModel):
    sync_id: str = Field(min_length=1)
    classroom_sync_id: str = Field(min_length=1)
    first_name: str = Field(min_length=1)
    last_name: str = Field(min_length=1)
    middle_name: str = ""
    student_code: str = ""
    notes: str = ""
    is_archived: bool = False
    created_at: datetime
    updated_at: datetime


class StudentOut(StudentPayload):
    server_revision: int


class TeacherClassroomPayload(BaseModel):
    teacher_sync_id: str = Field(min_length=1)
    classroom_sync_ids: list[str] = Field(default_factory=list)
    updated_at: datetime


class TeacherClassroomOut(TeacherClassroomPayload):
    server_revision: int


class SessionPayload(BaseModel):
    sync_id: str = Field(min_length=1)
    experiment_id: str = Field(min_length=1)
    experiment_title: str = ""
    experiment_display_number: int | None = None
    started_at: datetime
    ended_at: datetime | None = None
    status: str = ""
    measurement_count: int = 0
    created_at: datetime
    updated_at: datetime


class SessionOut(SessionPayload):
    server_revision: int


class SessionStudentLinkPayload(BaseModel):
    session_sync_id: str = Field(min_length=1)
    student_sync_id: str = Field(min_length=1)
    classroom_sync_id: str = Field(min_length=1)
    experiment_id: str = Field(min_length=1)
    linked_at: datetime


class SessionStudentLinkOut(SessionStudentLinkPayload):
    updated_at: datetime
    server_revision: int


class FeedbackResultPayload(BaseModel):
    sync_id: str = Field(min_length=1)
    experiment_id: str = ""
    is_draft: bool = True
    level1_answers: list[dict] = Field(default_factory=list)
    level1_score: int = 0
    level1_total: int = 0
    level1_percentage: float = 0.0
    level2_answers: list[dict] = Field(default_factory=list)
    level3_answers: list[dict] = Field(default_factory=list)
    self_assessment: int | None = None
    submitted_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class FeedbackResultOut(FeedbackResultPayload):
    server_revision: int


class TeacherAssessmentPayload(BaseModel):
    sync_id: str = Field(min_length=1)
    score: int = Field(ge=0, le=10)
    comment: str = ""
    reviewed: bool = True
    updated_at: datetime


class TeacherAssessmentOut(TeacherAssessmentPayload):
    server_revision: int


class MeasurementItemPayload(BaseModel):
    sequence_no: int = Field(ge=0)
    timestamp: datetime
    values: dict[str, float] = Field(default_factory=dict)
    derived_values: dict[str, float] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


# § Phase 4 "Payload size/limits" (§ malformed/empty-batch rejection):
# server-жақты жоғарғы шек, клиенттің әдепкі chunk_size-нен (250)
# едәуір жоғары — пайдаланушы chunk_size-ты кейін ұлғайтса да орын
# қалдырады, БІРАҚ бір HTTP payload-ты шексіз үлкейтуге жол бермейді
# (§ "avoid premature infra complexity" — қарапайым pydantic шегі
# жеткілікті, арнайы rate-limit/streaming инфрақұрылымы ЖОҚ).
MAX_MEASUREMENTS_PER_BATCH = 5000


class MeasurementBatchPayload(BaseModel):
    sync_id: str = Field(min_length=1)
    session_sync_id: str = Field(min_length=1)
    sequence_start: int = Field(ge=0)
    sequence_end: int = Field(gt=0)
    sample_count: int = Field(gt=0)
    created_at: datetime
    measurements: list[MeasurementItemPayload] = Field(
        min_length=1, max_length=MAX_MEASUREMENTS_PER_BATCH
    )


class MeasurementBatchOut(BaseModel):
    sync_id: str
    session_sync_id: str
    sequence_start: int
    sequence_end: int
    sample_count: int
    created_at: datetime
    measurements: list[MeasurementItemPayload]
    server_revision: int


class TeacherNotePayload(BaseModel):
    sync_id: str = Field(min_length=1)
    teacher_sync_id: str = Field(min_length=1)
    student_sync_id: str = Field(min_length=1)
    classroom_sync_id: str = Field(min_length=1)
    experiment_id: str | None = None
    session_sync_id: str | None = None
    message: str = Field(min_length=1)
    created_at: datetime


class TeacherNoteOut(TeacherNotePayload):
    server_revision: int


class UpsertResult(BaseModel):
    sync_id: str
    status: str  # "upserted" | "error"
    server_revision: int | None = None
    error: str | None = None


class UpsertBatchResponse(BaseModel):
    results: list[UpsertResult]


class PullResponse(BaseModel):
    server_time: datetime
    items: list[dict]
