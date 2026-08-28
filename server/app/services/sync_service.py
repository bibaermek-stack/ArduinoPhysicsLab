"""sync_service — sync_id бойынша идемпотентті upsert + incremental
pull (§9 "API Contract", §18 "Pull Sync", §19 "Conflict Strategy").

§19 "server authoritative by version": ``server_revision`` осында, БІР
жерде, әр сәтті upsert сайын артады — клиент ешқашан бұл мәнді өзі
орната алмайды. Пайдаланушы сағатына сенбеу үшін ``updated_at``
серверде ӨЗІ де қайта жазылады (§ SQLAlchemy ``onupdate``), тек incremental
pull cursor РЕТІНДЕ ғана емес, ЖАЛПЫ "соңғы шындық" ретінде де серверлік
уақыт басым.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from server.app.models.sync_models import (
    ClassroomRecord,
    FeedbackResultRecord,
    MeasurementBatchDeletionRecord,
    MeasurementBatchRecord,
    MeasurementRecord,
    SessionRecord,
    SessionStudentLinkRecord,
    StudentRecord,
    TeacherClassroomLinkRecord,
    TeacherNoteRecord,
    TeacherRecord,
)
from server.app.schemas.sync import (
    ClassroomPayload,
    FeedbackResultPayload,
    MeasurementBatchPayload,
    SessionPayload,
    SessionStudentLinkPayload,
    StudentPayload,
    TeacherAssessmentPayload,
    TeacherClassroomPayload,
    TeacherNotePayload,
    TeacherPayload,
)


class RelationshipError(ValueError):
    """§28 "relationship validation" — сілтенген ата-ана жазба сервер
    жағында әлі жоқ (§ клиент teachers->classrooms->students->
    teacher_classrooms ретімен итеруі керек)."""


def upsert_teacher(db: Session, payload: TeacherPayload) -> TeacherRecord:
    record = db.get(TeacherRecord, payload.sync_id)
    if record is None:
        record = TeacherRecord(sync_id=payload.sync_id, server_revision=1)
        db.add(record)
    else:
        record.server_revision += 1
    record.full_name = payload.full_name
    record.pin_hash = payload.pin_hash
    record.is_active = payload.is_active
    record.created_at = payload.created_at
    record.updated_at = datetime.now(timezone.utc)
    db.flush()
    return record


def upsert_classroom(db: Session, payload: ClassroomPayload) -> ClassroomRecord:
    record = db.get(ClassroomRecord, payload.sync_id)
    if record is None:
        record = ClassroomRecord(sync_id=payload.sync_id, server_revision=1)
        db.add(record)
    else:
        record.server_revision += 1
    record.name = payload.name
    record.academic_year = payload.academic_year
    record.description = payload.description
    record.is_archived = payload.is_archived
    record.created_at = payload.created_at
    record.updated_at = datetime.now(timezone.utc)
    db.flush()
    return record


def upsert_student(db: Session, payload: StudentPayload) -> StudentRecord:
    classroom = db.get(ClassroomRecord, payload.classroom_sync_id)
    if classroom is None:
        raise RelationshipError(
            f"classroom_sync_id '{payload.classroom_sync_id}' серверде табылмады "
            "(§ алдымен сыныпты синхрондау керек)"
        )
    record = db.get(StudentRecord, payload.sync_id)
    if record is None:
        record = StudentRecord(sync_id=payload.sync_id, server_revision=1)
        db.add(record)
    else:
        record.server_revision += 1
    record.classroom_sync_id = payload.classroom_sync_id
    record.first_name = payload.first_name
    record.last_name = payload.last_name
    record.middle_name = payload.middle_name
    record.student_code = payload.student_code
    record.notes = payload.notes
    record.is_archived = payload.is_archived
    record.created_at = payload.created_at
    record.updated_at = datetime.now(timezone.utc)
    db.flush()
    return record


def upsert_teacher_classroom(db: Session, payload: TeacherClassroomPayload) -> TeacherClassroomLinkRecord:
    teacher = db.get(TeacherRecord, payload.teacher_sync_id)
    if teacher is None:
        raise RelationshipError(
            f"teacher_sync_id '{payload.teacher_sync_id}' серверде табылмады "
            "(§ алдымен мұғалімді синхрондау керек)"
        )
    for classroom_sync_id in payload.classroom_sync_ids:
        if db.get(ClassroomRecord, classroom_sync_id) is None:
            raise RelationshipError(
                f"classroom_sync_id '{classroom_sync_id}' серверде табылмады "
                "(§ алдымен сыныпты синхрондау керек)"
            )
    record = db.get(TeacherClassroomLinkRecord, payload.teacher_sync_id)
    if record is None:
        record = TeacherClassroomLinkRecord(teacher_sync_id=payload.teacher_sync_id, server_revision=1)
        db.add(record)
    else:
        record.server_revision += 1
    record.classroom_sync_ids_json = json.dumps(sorted(payload.classroom_sync_ids))
    record.updated_at = datetime.now(timezone.utc)
    db.flush()
    return record


def pull_teachers(db: Session, updated_since: datetime | None, limit: int) -> list[TeacherRecord]:
    query = db.query(TeacherRecord)
    if updated_since is not None:
        query = query.filter(TeacherRecord.updated_at > updated_since)
    return query.order_by(TeacherRecord.updated_at).limit(limit).all()


def pull_classrooms(db: Session, updated_since: datetime | None, limit: int) -> list[ClassroomRecord]:
    query = db.query(ClassroomRecord)
    if updated_since is not None:
        query = query.filter(ClassroomRecord.updated_at > updated_since)
    return query.order_by(ClassroomRecord.updated_at).limit(limit).all()


def pull_students(db: Session, updated_since: datetime | None, limit: int) -> list[StudentRecord]:
    query = db.query(StudentRecord)
    if updated_since is not None:
        query = query.filter(StudentRecord.updated_at > updated_since)
    return query.order_by(StudentRecord.updated_at).limit(limit).all()


def pull_teacher_classrooms(
    db: Session, updated_since: datetime | None, limit: int
) -> list[TeacherClassroomLinkRecord]:
    query = db.query(TeacherClassroomLinkRecord)
    if updated_since is not None:
        query = query.filter(TeacherClassroomLinkRecord.updated_at > updated_since)
    return query.order_by(TeacherClassroomLinkRecord.updated_at).limit(limit).all()


# ---- Phase 2: Experiment Session + Results + Feedback Cloud Sync ---------
#
# §11 "Dependency Ordering" / §19/§31 "Server Transaction Safety": бұл
# төрт entity-нің ешқайсысы ``session_sync_id``-ды НАҚТЫ FK ретінде
# талап ЕТПЕЙДІ (§ ``server/app/models/sync_models.py::SessionStudentLink
# Record`` докстрингі — жергілікті домен байланысты сессиясыз да заңды
# деп таниды, § "a child record must not fail merely because its parent
# is still sitting earlier in the same local outbox batch"). ``student_
# sync_id``/``classroom_sync_id`` НАҚТЫ FK-мен тексеріледі — Phase 1 push
# реті бойынша олар ӘРҚАШАН алдын ала бар.


def upsert_session(db: Session, payload: SessionPayload) -> SessionRecord:
    record = db.get(SessionRecord, payload.sync_id)
    if record is None:
        record = SessionRecord(sync_id=payload.sync_id, server_revision=1)
        db.add(record)
    else:
        record.server_revision += 1
    record.experiment_id = payload.experiment_id
    record.experiment_title = payload.experiment_title
    record.experiment_display_number = payload.experiment_display_number
    record.started_at = payload.started_at
    record.ended_at = payload.ended_at
    record.status = payload.status
    record.measurement_count = payload.measurement_count
    record.created_at = payload.created_at
    record.updated_at = datetime.now(timezone.utc)
    db.flush()
    return record


def upsert_session_student_link(
    db: Session, payload: SessionStudentLinkPayload
) -> SessionStudentLinkRecord:
    if db.get(StudentRecord, payload.student_sync_id) is None:
        raise RelationshipError(
            f"student_sync_id '{payload.student_sync_id}' серверде табылмады "
            "(§ алдымен оқушыны синхрондау керек)"
        )
    if db.get(ClassroomRecord, payload.classroom_sync_id) is None:
        raise RelationshipError(
            f"classroom_sync_id '{payload.classroom_sync_id}' серверде табылмады "
            "(§ алдымен сыныпты синхрондау керек)"
        )
    record = db.get(SessionStudentLinkRecord, payload.session_sync_id)
    if record is None:
        record = SessionStudentLinkRecord(session_sync_id=payload.session_sync_id, server_revision=1)
        db.add(record)
    else:
        record.server_revision += 1
    record.student_sync_id = payload.student_sync_id
    record.classroom_sync_id = payload.classroom_sync_id
    record.experiment_id = payload.experiment_id
    record.linked_at = payload.linked_at
    record.updated_at = datetime.now(timezone.utc)
    db.flush()
    return record


def upsert_feedback_result(db: Session, payload: FeedbackResultPayload) -> FeedbackResultRecord:
    """§5: тек оқушы авторлық бағандарды жазады, мұғалім бағандарын
    (§ ``upsert_teacher_assessment()`` иеленеді) ЕШҚАШАН тимейді —
    ``sqlite_feedback_repository.py::_save()``-пен БІРДЕЙ принцип."""
    record = db.get(FeedbackResultRecord, payload.sync_id)
    if record is None:
        record = FeedbackResultRecord(sync_id=payload.sync_id, server_revision=1)
        db.add(record)
    else:
        record.server_revision += 1
    record.experiment_id = payload.experiment_id
    record.is_draft = payload.is_draft
    record.level1_answers_json = json.dumps(payload.level1_answers)
    record.level1_score = payload.level1_score
    record.level1_total = payload.level1_total
    record.level1_percentage = payload.level1_percentage
    record.level2_answers_json = json.dumps(payload.level2_answers)
    record.level3_answers_json = json.dumps(payload.level3_answers)
    record.self_assessment = payload.self_assessment
    record.submitted_at = payload.submitted_at
    record.created_at = payload.created_at
    record.updated_at = datetime.now(timezone.utc)
    db.flush()
    return record


def upsert_teacher_assessment(db: Session, payload: TeacherAssessmentPayload) -> FeedbackResultRecord:
    """§6: тек мұғалім бағандарын жазады, оқушы авторлық бағандарды
    ЕШҚАШАН тимейді — ``sqlite_feedback_repository.py::save_teacher_
    assessment()``-пен БІРДЕЙ pre-insert-empty-shell принципі (студент
    әлі ешбір feedback_result жібермеген болса да)."""
    record = db.get(FeedbackResultRecord, payload.sync_id)
    if record is None:
        record = FeedbackResultRecord(sync_id=payload.sync_id, teacher_server_revision=1)
        db.add(record)
    else:
        record.teacher_server_revision = (record.teacher_server_revision or 0) + 1
    record.teacher_score = payload.score
    record.teacher_comment = payload.comment
    record.teacher_reviewed = payload.reviewed
    record.teacher_updated_at = datetime.now(timezone.utc)
    db.flush()
    return record


def pull_sessions(db: Session, updated_since: datetime | None, limit: int) -> list[SessionRecord]:
    query = db.query(SessionRecord)
    if updated_since is not None:
        query = query.filter(SessionRecord.updated_at > updated_since)
    return query.order_by(SessionRecord.updated_at).limit(limit).all()


def pull_session_student_links(
    db: Session, updated_since: datetime | None, limit: int
) -> list[SessionStudentLinkRecord]:
    query = db.query(SessionStudentLinkRecord)
    if updated_since is not None:
        query = query.filter(SessionStudentLinkRecord.updated_at > updated_since)
    return query.order_by(SessionStudentLinkRecord.updated_at).limit(limit).all()


def pull_feedback_results(
    db: Session, updated_since: datetime | None, limit: int
) -> list[FeedbackResultRecord]:
    query = db.query(FeedbackResultRecord)
    if updated_since is not None:
        query = query.filter(FeedbackResultRecord.updated_at > updated_since)
    return query.order_by(FeedbackResultRecord.updated_at).limit(limit).all()


def upsert_measurement_batch(db: Session, payload: MeasurementBatchPayload) -> MeasurementBatchRecord:
    """§ Phase 4 "Idempotency HARD requirement": batch мазмұны
    (``sequence_start``/``sequence_end``/measurement жолдары) құрылған
    соң ӨЗГЕРМЕЙДІ — сол себепті БАР жазба табылса, ЕШБІР қайта
    жазу/қайта insert ЖАСАЛМАЙДЫ, тек сол ҚАЛЫПТЫ жазба қайтарылады
    (§ "server committed, client lost the response, retries" — дәл
    осы жол СОЛ сценарийді дұрыс өңдейді, ``UNIQUE(session_sync_id,
    sequence_no)``-ты екінші рет бұзу қаупінсіз).
    """
    session = db.get(SessionRecord, payload.session_sync_id)
    if session is None:
        raise RelationshipError(
            f"session_sync_id '{payload.session_sync_id}' серверде табылмады "
            "(§ алдымен сессияны синхрондау керек)"
        )
    existing = db.get(MeasurementBatchRecord, payload.sync_id)
    if existing is not None:
        return existing
    record = MeasurementBatchRecord(
        sync_id=payload.sync_id,
        session_sync_id=payload.session_sync_id,
        sequence_start=payload.sequence_start,
        sequence_end=payload.sequence_end,
        sample_count=payload.sample_count,
        created_at=payload.created_at,
        server_revision=1,
    )
    db.add(record)
    for item in payload.measurements:
        db.add(
            MeasurementRecord(
                batch_sync_id=payload.sync_id,
                session_sync_id=payload.session_sync_id,
                sequence_no=item.sequence_no,
                timestamp=item.timestamp,
                values_json=json.dumps(item.values),
                derived_values_json=json.dumps(item.derived_values),
                warnings_json=json.dumps(item.warnings),
            )
        )
    try:
        db.flush()
    except IntegrityError as error:
        db.rollback()
        raise RelationshipError(
            f"batch '{payload.sync_id}': sequence_no аралығы басқа batch-пен қабаттасады ({error})"
        ) from error
    return record


def pull_measurement_batches(
    db: Session, updated_since: datetime | None, limit: int
) -> list[MeasurementBatchRecord]:
    """§18 "Pull Sync": ``updated_at`` cursor ретінде қауіпсіз — batch
    мазмұны ӨЗГЕРМЕЙТІНДІКТЕН (§ ``upsert_measurement_batch()``
    докстрингі), ``updated_at`` ЖАЛҒЫЗ РЕТ, құрылған сәтте орнатылады.
    Tombstone болған batch pull-ге кірмейді.
    """
    query = (
        db.query(MeasurementBatchRecord)
        .outerjoin(
            MeasurementBatchDeletionRecord,
            MeasurementBatchRecord.sync_id == MeasurementBatchDeletionRecord.sync_id,
        )
        .filter(MeasurementBatchDeletionRecord.sync_id.is_(None))
    )
    if updated_since is not None:
        query = query.filter(MeasurementBatchRecord.updated_at > updated_since)
    return query.order_by(MeasurementBatchRecord.updated_at).limit(limit).all()


def delete_measurement_batch(db: Session, sync_id: str, deleted_by: str) -> MeasurementBatchRecord | None:
    record = db.get(MeasurementBatchRecord, sync_id)
    if record is None:
        return None
    if db.get(MeasurementBatchDeletionRecord, sync_id) is None:
        db.add(
            MeasurementBatchDeletionRecord(sync_id=sync_id, deleted_by=deleted_by)
        )
        db.flush()
    return record


def upsert_teacher_note(db: Session, payload: TeacherNotePayload) -> TeacherNoteRecord:
    """§ Phase 7: ``TeacherNote`` мазмұны (``message``/уақыты) құрылғаннан
    кейін ӨЗГЕРМЕЙДІ (§ ``upsert_measurement_batch()``-пен БІРДЕЙ
    "immutable once created" принципі) — БАР жазба табылса, ЕШБІР қайта
    жазу ЖАСАЛМАЙДЫ, тек сол ҚАЛЫПТЫ жазба қайтарылады (§ "same
    sync_id uploaded once or twenty times must produce the same final
    server state")."""
    existing = db.get(TeacherNoteRecord, payload.sync_id)
    if existing is not None:
        return existing
    record = TeacherNoteRecord(
        sync_id=payload.sync_id,
        teacher_sync_id=payload.teacher_sync_id,
        student_sync_id=payload.student_sync_id,
        classroom_sync_id=payload.classroom_sync_id,
        experiment_id=payload.experiment_id,
        session_sync_id=payload.session_sync_id,
        message=payload.message,
        created_at=payload.created_at,
        server_revision=1,
    )
    db.add(record)
    db.flush()
    return record


def pull_teacher_notes(db: Session, updated_since: datetime | None, limit: int) -> list[TeacherNoteRecord]:
    query = db.query(TeacherNoteRecord)
    if updated_since is not None:
        query = query.filter(TeacherNoteRecord.updated_at > updated_since)
    return query.order_by(TeacherNoteRecord.updated_at).limit(limit).all()


def pull_teacher_assessments(
    db: Session, updated_since: datetime | None, limit: int
) -> list[FeedbackResultRecord]:
    """§ тек НАҚТЫ бағаланған жолдар (§ ``teacher_score IS NOT NULL``) —
    бос "pre-insert shell" жолдары ЕШҚАШАН синхрондалмайды (§ ``sqlite_
    feedback_repository.py::get_teacher_assessment_sync_payload()``-пен
    БІРДЕЙ шарт)."""
    query = db.query(FeedbackResultRecord).filter(FeedbackResultRecord.teacher_score.isnot(None))
    if updated_since is not None:
        query = query.filter(FeedbackResultRecord.teacher_updated_at > updated_since)
    return query.order_by(FeedbackResultRecord.teacher_updated_at).limit(limit).all()
