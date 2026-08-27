"""domain/services/sync_payload.py тесттері — entity <-> wire payload
round-trip конвертациясы (§9 "API Contract": payload sync_id қолданады,
жергілікті integer/UUID PK ЕМЕС)."""

from datetime import datetime, timezone

from domain.entities.classroom import Classroom
from domain.entities.student import Student
from domain.entities.sync_state import SyncState
from domain.entities.teacher import Teacher
from domain.services.sync_payload import (
    ENTITY_TYPE_CLASSROOM,
    ENTITY_TYPE_FEEDBACK_RESULT,
    ENTITY_TYPE_MEASUREMENT_BATCH,
    ENTITY_TYPE_SESSION,
    ENTITY_TYPE_SESSION_STUDENT_LINK,
    ENTITY_TYPE_STUDENT,
    ENTITY_TYPE_TEACHER,
    ENTITY_TYPE_TEACHER_ASSESSMENT,
    ENTITY_TYPE_TEACHER_CLASSROOM,
    ENTITY_TYPE_TEACHER_NOTE,
    PUSH_ORDER,
    classroom_to_payload,
    payload_to_classroom,
    payload_to_student,
    payload_to_teacher,
    student_to_payload,
    teacher_classroom_to_payload,
    teacher_to_payload,
)

_NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def test_push_order_dependencies_precede_dependents() -> None:
    """Сервер FK валидациясы теру ретіне тәуелді (§9) — teacher/classroom
    student-тен, ал teacher_classroom Phase 1 entity-лерінің БАРЛЫҒЫНАН
    бұрын жүрмеуі керек (§ Phase 2: session/link/feedback/assessment
    ЕНДІ teacher_classroom-нан КЕЙІН қосылады, § dependency ordering).
    § Phase 4: ``measurement_batch`` ``ExperimentSession``-ға (session/
    link/feedback/assessment-тің БАРЛЫҒЫНАН да) тәуелді — СОҢҒЫдан
    бұрынғы позиция (§ Phase 7: ``teacher_note`` ЕҢ СОҢҒЫ қосылды,
    себебі ол тек teacher/student/classroom-ға тәуелді, § ``domain/
    services/sync_payload.py`` PUSH_ORDER докстрингі — ретте
    measurement_batch-тан КЕЙІН/АЛДЫН болуының нақты маңызы жоқ, тек
    ӨЗ тәуелділіктерінен КЕЙІН болуы жеткілікті)."""
    assert PUSH_ORDER.index(ENTITY_TYPE_TEACHER) < PUSH_ORDER.index(ENTITY_TYPE_STUDENT)
    assert PUSH_ORDER.index(ENTITY_TYPE_CLASSROOM) < PUSH_ORDER.index(ENTITY_TYPE_STUDENT)
    assert PUSH_ORDER.index(ENTITY_TYPE_TEACHER_CLASSROOM) == 3
    assert PUSH_ORDER.index(ENTITY_TYPE_SESSION) > PUSH_ORDER.index(ENTITY_TYPE_TEACHER_CLASSROOM)
    assert PUSH_ORDER.index(ENTITY_TYPE_SESSION_STUDENT_LINK) > PUSH_ORDER.index(ENTITY_TYPE_SESSION)
    assert PUSH_ORDER.index(ENTITY_TYPE_FEEDBACK_RESULT) > PUSH_ORDER.index(ENTITY_TYPE_SESSION_STUDENT_LINK)
    assert PUSH_ORDER.index(ENTITY_TYPE_TEACHER_ASSESSMENT) > PUSH_ORDER.index(ENTITY_TYPE_FEEDBACK_RESULT)
    assert PUSH_ORDER.index(ENTITY_TYPE_MEASUREMENT_BATCH) > PUSH_ORDER.index(ENTITY_TYPE_SESSION)
    # § Phase 7: ``teacher_note`` ЕҢ СОҢҒЫ — тек ӨЗ тәуелділіктерінен
    # (мұғалім/оқушы/сынып) КЕЙІН болуы керек, § жаңа "last" элемент.
    assert PUSH_ORDER.index(ENTITY_TYPE_TEACHER_NOTE) == len(PUSH_ORDER) - 1
    assert PUSH_ORDER.index(ENTITY_TYPE_TEACHER_NOTE) > PUSH_ORDER.index(ENTITY_TYPE_TEACHER)
    assert PUSH_ORDER.index(ENTITY_TYPE_TEACHER_NOTE) > PUSH_ORDER.index(ENTITY_TYPE_STUDENT)
    assert PUSH_ORDER.index(ENTITY_TYPE_TEACHER_NOTE) > PUSH_ORDER.index(ENTITY_TYPE_CLASSROOM)


def test_teacher_payload_round_trip() -> None:
    teacher = Teacher(
        id="t1",
        full_name="Айдос Нұрланұлы",
        pin_hash="hash123",
        created_at=_NOW,
        updated_at=_NOW,
        is_active=True,
        sync_id="t1",
    )

    payload = teacher_to_payload(teacher)
    restored = payload_to_teacher(payload)

    assert payload["sync_id"] == "t1"
    assert "id" not in payload
    assert restored.id == "t1"
    assert restored.full_name == teacher.full_name
    assert restored.pin_hash == teacher.pin_hash
    assert restored.sync_state is SyncState.SYNCED


def test_classroom_payload_round_trip() -> None:
    classroom = Classroom(
        id="c1",
        name="8А",
        created_at=_NOW,
        updated_at=_NOW,
        academic_year="2025-2026",
        description="Физика",
        sync_id="c1",
    )

    payload = classroom_to_payload(classroom)
    restored = payload_to_classroom(payload)

    assert restored.name == "8А"
    assert restored.academic_year == "2025-2026"
    assert restored.sync_state is SyncState.SYNCED


def test_student_payload_round_trip_uses_classroom_sync_id() -> None:
    student = Student(
        id="s1",
        classroom_id="c1",
        first_name="Айдос",
        last_name="Смағұлов",
        created_at=_NOW,
        updated_at=_NOW,
        student_code="123456",
        sync_id="s1",
    )

    payload = student_to_payload(student)
    restored = payload_to_student(payload)

    assert payload["classroom_sync_id"] == "c1"
    assert restored.classroom_id == "c1"
    assert restored.student_code == "123456"
    assert restored.sync_state is SyncState.SYNCED


def test_payload_falls_back_to_local_id_when_sync_id_empty() -> None:
    """§2: жаңа жазба ӘЛІ ешбір sync шақыруынан өтпеген болса да (sync_id
    бос), push payload-ы ӘРҚАШАН жарамды identifier қолданады."""
    teacher = Teacher(id="t1", full_name="X", pin_hash="h", created_at=_NOW, updated_at=_NOW)

    payload = teacher_to_payload(teacher)

    assert payload["sync_id"] == "t1"


def test_teacher_classroom_payload_carries_whole_assignment_set() -> None:
    payload = teacher_classroom_to_payload("t1", ("c1", "c2"), _NOW)

    assert payload["teacher_sync_id"] == "t1"
    assert payload["classroom_sync_ids"] == ["c1", "c2"]
