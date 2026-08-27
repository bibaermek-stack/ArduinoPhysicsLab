"""sync_migration — ескі (Cloud Sync-тен бұрынғы) жазбаларға ``sync_id``
толтыратын бір реттік, идемпотентті көшу (Offline-First + Cloud Sync
Foundation фазасы, §4 "Do NOT break existing database").

``backfill_missing_student_codes()``/``backfill_default_teacher()``-мен
БІРДЕЙ принцип — ``app.py`` ЖӘНЕ ``MainWindow`` екеуі де осыны шақырады,
идемпотентті болғандықтан қайталап шақыру қауіпсіз. ``sync_id`` бос
жолдарды (§ ``database.py`` миграциясының ЖАҢА бағаны, ескі жолдарда
әдепкі ``''``) тек ЖАЗБАНЫҢ ӨЗ ``id``-мен толтырады — ЕШБІР жаңа UUID
ЖАСАЛМАЙДЫ, ЕШБІР жазба қайта құрылмайды/жойылмайды (§ "must not
regenerate identities unnecessarily").
"""

from __future__ import annotations

from dataclasses import replace

from domain.entities.user_role import UserRole
from domain.interfaces.i_classroom_repository import IClassroomRepository
from domain.interfaces.i_feedback_repository import IFeedbackRepository
from domain.interfaces.i_measurement_batch_repository import IMeasurementBatchRepository
from domain.interfaces.i_session_repository import ISessionRepository
from domain.interfaces.i_student_progress_repository import IStudentProgressRepository
from domain.interfaces.i_student_repository import IStudentRepository
from domain.interfaces.i_teacher_repository import ITeacherRepository

_SYNCED = "synced"


def backfill_sync_ids(
    classroom_repository: IClassroomRepository,
    student_repository: IStudentRepository,
    teacher_repository: ITeacherRepository,
) -> int:
    """``sync_id`` бос қалған классрум/оқушы/мұғалім жазбаларына
    ``sync_id = id`` тағайындайды. Идемпотентті — сыныпы толтырылған
    жазбалар ЕШҚАШАН қайта жазылмайды. Толтырылған жазба санын
    қайтарады."""
    updated_count = 0

    for classroom in classroom_repository.list_all():
        if classroom.sync_id:
            continue
        classroom_repository.update(replace(classroom, sync_id=classroom.id), UserRole.TEACHER)
        updated_count += 1

    for classroom in classroom_repository.list_all():
        for student in student_repository.list_by_classroom(classroom.id, include_archived=True):
            if student.sync_id:
                continue
            student_repository.update(replace(student, sync_id=student.id), UserRole.TEACHER)
            updated_count += 1

    for teacher in teacher_repository.list_all():
        if teacher.sync_id:
            continue
        teacher_repository.update(replace(teacher, sync_id=teacher.id))
        updated_count += 1

    return updated_count


def backfill_session_sync_queue(
    session_repository: ISessionRepository,
    student_progress_repository: IStudentProgressRepository,
    feedback_repository: IFeedbackRepository,
) -> int:
    """§ Phase 2 (Experiment Session + Results + Feedback Cloud Sync):
    ``session``/``session_student_link``/``feedback_result``/``teacher_
    assessment`` кестелерінің ешқайсысында жеке ``sync_id`` бағаны ЖОҚ
    (§ ``database.py``/repository докстрингтері — өз табиғи ``id``/
    ``session_id`` кілттері тікелей entity_sync_id ретінде қолданылады),
    сондықтан ``backfill_sync_ids()``-тен айырмашылығы: бұл функция
    ешбір бағанды ТОЛТЫРМАЙДЫ, тек Phase 2 кодынан БҰРЫН жазылған
    (әлі ешбір outbox жазуы жоқ) жазбаларды outbox-қа қосады.

    Идемпотентті: ``sync_state != 'synced'`` жазбалар ғана қайта
    кезекке қойылады (§ ``enqueue()``-дің ӨЗІ ``ON CONFLICT DO UPDATE``
    арқылы идемпотентті — қайта шақыру ешбір дубликат жасамайды, тек
    ҚАЛПЫНА толтырылмайды-ды кезекке ЕШҚАШАН ҚАЙТА ҚОЙЫЛМАЙДЫ).
    """
    updated_count = 0

    for summary in session_repository.get_sessions(limit=None):
        payload = session_repository.get_sync_payload(summary.id)
        if payload is not None and payload["sync_state"] != _SYNCED:
            session_repository.enqueue_for_sync(summary.id)
            updated_count += 1

    for session_id in student_progress_repository.list_all_link_session_ids():
        payload = student_progress_repository.get_link_sync_payload(session_id)
        if payload is not None and payload["sync_state"] != _SYNCED:
            student_progress_repository.enqueue_link_for_sync(session_id)
            updated_count += 1

        feedback_payload = feedback_repository.get_feedback_sync_payload(session_id)
        if feedback_payload is not None and feedback_payload["sync_state"] != _SYNCED:
            feedback_repository.enqueue_feedback_for_sync(session_id)
            updated_count += 1

        assessment_payload = feedback_repository.get_teacher_assessment_sync_payload(session_id)
        if assessment_payload is not None and assessment_payload["sync_state"] != _SYNCED:
            feedback_repository.enqueue_teacher_assessment_for_sync(session_id)
            updated_count += 1

    return updated_count


def backfill_measurement_batches(
    session_repository: ISessionRepository,
    measurement_batch_repository: IMeasurementBatchRepository,
    chunk_size: int,
) -> int:
    """§ Phase 4 "Legacy Measurement Handling": Phase 4 кодынан БҰРЫН
    жазылған (әлі ешбір ``measurement_batches`` жолы жоқ) сессиялардың
    raw measurement-дерін batch-қа бөліп, синхрондау кезегіне қояды —
    ЕСКІ пайдаланушы деректері "үнсіз еленбейді" (§ "never silently
    ignore existing user data").

    ``create_pending_batches_for_session()``-тің ӨЗІ идемпотентті/
    инкременталды (§ ``MAX(sequence_end)``-тен жалғасады) — қайта
    шақыру ЕШБІР дубликат batch жасамайды, ``backfill_sync_ids()``-пен
    БІРДЕЙ конвенция. ``finalize=True`` — бұл функция ТЕК app іске
    қосылған сәтте шақырылады (§ ``app.py``/``ui/main_window.py``),
    сол сәтте ЕШБІР сессия белсенді жиналуда БОЛА АЛМАЙДЫ (§ acquisition
    тек пайдаланушы бетте нақты Start басқаннан КЕЙІН басталады),
    сондықтан ескі сессияның "құйрығын" да дереу толық batch-қа
    жабу қауіпсіз."""
    created_count = 0
    for summary in session_repository.get_sessions(limit=None):
        created_count += measurement_batch_repository.create_pending_batches_for_session(
            summary.id, chunk_size, finalize=True
        )
    return created_count
