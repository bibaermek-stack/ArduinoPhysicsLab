"""sync_payload — жергілікті entity ↔ сым (wire) payload түрлендіруі
(Offline-First + Cloud Sync Foundation фазасы).

§27 "Logging" ЕСКЕРТУІ: ``teacher_to_payload()``/``student_to_payload()``
``pin_hash``/``student_code``-ты ҚОСАДЫ (§12 "Offline Login" осыны
талап етеді — басқа құрылғы дәл СОЛ кодпен кіре алуы үшін), БІРАҚ
``domain/services/sync_engine.py`` бұл payload-тарды ЕШҚАШАН
логтамайды — тек ``entity_type``/``sync_id``/сан қорытындыларын
логтайды (§ ``sync_engine.py`` докстрингі).

Мұғалім↔сынып байланысы ЖЕКЕ entity ЕМЕС (§ ``sqlite_teacher_
repository.py`` докстрингі) — ``teacher_classroom_to_payload()``/
``payload_to_assignment()`` тікелей dict-пен жұмыс істейді.
"""

from __future__ import annotations

from datetime import datetime

from domain.entities.classroom import Classroom
from domain.entities.student import Student
from domain.entities.sync_state import SyncState
from domain.entities.teacher import Teacher

ENTITY_TYPE_TEACHER = "teacher"
ENTITY_TYPE_CLASSROOM = "classroom"
ENTITY_TYPE_STUDENT = "student"
ENTITY_TYPE_TEACHER_CLASSROOM = "teacher_classroom"
# § Phase 2 (Experiment Session + Results + Feedback Cloud Sync). Бұл
# төрт entity-нің ЕШҚАЙСЫСЫНДА жеке ``sync_id`` бағаны ЖОҚ — entity_
# sync_id ретінде тікелей ``ExperimentSession.id``/``session_id``
# (табиғи, ӘЛДЕҚАШАН UUID кілт) қолданылады (§ ``infrastructure/storage/
# sqlite_session_repository.py`` докстрингі). Payload dict-тері осы
# модульде ЕМЕС, тікелей repository ``get_*_sync_payload()``/``apply_
# remote_*()`` әдістерінде құрастырылады (§ ``SyncEngine`` докстрингі —
# "Cloud synchronization transports authoritative records", репозиторий
# ӨЗІ SQL схемасын білетін жалғыз орын).
ENTITY_TYPE_SESSION = "session"
ENTITY_TYPE_SESSION_STUDENT_LINK = "session_student_link"
ENTITY_TYPE_FEEDBACK_RESULT = "feedback_result"
ENTITY_TYPE_TEACHER_ASSESSMENT = "teacher_assessment"
# § Phase 4 (Raw Arduino Measurement Cloud Sync). Batch payload-ы
# ``get_batch_sync_payload()``/``apply_remote_batch()`` арқылы тікелей
# ``SqliteMeasurementBatchRepository``-де құрастырылады (§ жоғарыдағы
# session/link/feedback/assessment-мен БІРДЕЙ паттерн) — бұл модульде
# converter функциясы ЖОҚ.
ENTITY_TYPE_MEASUREMENT_BATCH = "measurement_batch"
# § Phase 7 (Teacher Actions, Feedback Delivery, and Session History).
# Мұғалімнің оқушыға жіберетін қысқа пікірі — ``experiment_feedback``-тен
# БӨЛЕК, жаңа, кіші entity (§ ``domain/entities/teacher_note.py``
# докстрингі). Payload ``get_note_sync_payload()``/``apply_remote_note()``
# арқылы тікелей ``SqliteTeacherNoteRepository``-де құрастырылады (§
# session/link/feedback/assessment/measurement_batch-пен БІРДЕЙ паттерн)
# — бұл модульде converter функциясы ЖОҚ. Бір бағытты (тек мұғалім
# авторлық) — ``experiment_feedback``-тегідей екі жартылы split ЖОҚ.
ENTITY_TYPE_TEACHER_NOTE = "teacher_note"

# § "Preferred first synchronized entities" — server-side foreign-key
# validation (§ ``server/app/services/sync_service.py``) талап ететін
# тәуелділік реті: teachers/classrooms алдымен, содан кейін студенттер,
# байланыстар, СОДАН КЕЙІН барып сессия/байланыс/кері байланыс/баға
# (§ Phase 2 Final Report "12. dependency ordering"). Measurement batch
# ЕҢ СОҢҒЫ — ``ExperimentSession``-ға тәуелді (§ "measurement batches
# depend on ExperimentSession; must never precede it in PUSH_ORDER").
PUSH_ORDER: tuple[str, ...] = (
    ENTITY_TYPE_TEACHER,
    ENTITY_TYPE_CLASSROOM,
    ENTITY_TYPE_STUDENT,
    ENTITY_TYPE_TEACHER_CLASSROOM,
    ENTITY_TYPE_SESSION,
    ENTITY_TYPE_SESSION_STUDENT_LINK,
    ENTITY_TYPE_FEEDBACK_RESULT,
    ENTITY_TYPE_TEACHER_ASSESSMENT,
    ENTITY_TYPE_MEASUREMENT_BATCH,
    ENTITY_TYPE_TEACHER_NOTE,
)


def teacher_to_payload(teacher: Teacher) -> dict:
    return {
        "sync_id": teacher.sync_id or teacher.id,
        "full_name": teacher.full_name,
        "pin_hash": teacher.pin_hash,
        "is_active": teacher.is_active,
        "created_at": teacher.created_at.isoformat(),
        "updated_at": teacher.updated_at.isoformat(),
    }


def payload_to_teacher(payload: dict) -> Teacher:
    return Teacher(
        id=payload["sync_id"],
        full_name=payload["full_name"],
        pin_hash=payload["pin_hash"],
        is_active=payload["is_active"],
        created_at=datetime.fromisoformat(payload["created_at"]),
        updated_at=datetime.fromisoformat(payload["updated_at"]),
        sync_id=payload["sync_id"],
        sync_state=SyncState.SYNCED,
        server_revision=payload.get("server_revision"),
    )


def classroom_to_payload(classroom: Classroom) -> dict:
    return {
        "sync_id": classroom.sync_id or classroom.id,
        "name": classroom.name,
        "academic_year": classroom.academic_year,
        "description": classroom.description,
        "is_archived": classroom.is_archived,
        "created_at": classroom.created_at.isoformat(),
        "updated_at": classroom.updated_at.isoformat(),
    }


def payload_to_classroom(payload: dict) -> Classroom:
    return Classroom(
        id=payload["sync_id"],
        name=payload["name"],
        academic_year=payload.get("academic_year", ""),
        description=payload.get("description", ""),
        is_archived=payload["is_archived"],
        created_at=datetime.fromisoformat(payload["created_at"]),
        updated_at=datetime.fromisoformat(payload["updated_at"]),
        sync_id=payload["sync_id"],
        sync_state=SyncState.SYNCED,
        server_revision=payload.get("server_revision"),
    )


def student_to_payload(student: Student) -> dict:
    return {
        "sync_id": student.sync_id or student.id,
        "classroom_sync_id": student.classroom_id,
        "first_name": student.first_name,
        "last_name": student.last_name,
        "middle_name": student.middle_name,
        "student_code": student.student_code,
        "notes": student.notes,
        "is_archived": student.is_archived,
        "created_at": student.created_at.isoformat(),
        "updated_at": student.updated_at.isoformat(),
    }


def payload_to_student(payload: dict) -> Student:
    return Student(
        id=payload["sync_id"],
        classroom_id=payload["classroom_sync_id"],
        first_name=payload["first_name"],
        last_name=payload["last_name"],
        middle_name=payload.get("middle_name", ""),
        student_code=payload.get("student_code", ""),
        notes=payload.get("notes", ""),
        is_archived=payload["is_archived"],
        created_at=datetime.fromisoformat(payload["created_at"]),
        updated_at=datetime.fromisoformat(payload["updated_at"]),
        sync_id=payload["sync_id"],
        sync_state=SyncState.SYNCED,
        server_revision=payload.get("server_revision"),
    )


def teacher_classroom_to_payload(teacher_sync_id: str, classroom_sync_ids: tuple[str, ...], updated_at: datetime) -> dict:
    return {
        "teacher_sync_id": teacher_sync_id,
        "classroom_sync_ids": list(classroom_sync_ids),
        "updated_at": updated_at.isoformat(),
    }
