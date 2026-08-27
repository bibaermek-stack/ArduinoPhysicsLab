"""authorization — server-side ownership/relationship rules (Phase 3
§4 "Server-Side Authorization", a HARD requirement).

Authentication (``auth_service.py``/``deps.py::get_current_user()``)
only proves WHO is calling. This module decides WHAT that identity may
read/write, re-resolved live from the DB on every call — never trusted
from the client or baked into the JWT (§3 "Do not trust role, teacher
ID, student ID, classroom ID... supplied by the client if the server
can derive them from the authenticated identity").

Mirrors the CLIENT-side ``infrastructure/storage/
teacher_scoped_classroom_repository.py`` scoping concept, server-side,
extended to sessions/links/feedback/assessments.
"""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from server.app.models.sync_models import (
    ClassroomRecord,
    SessionStudentLinkRecord,
    StudentRecord,
    TeacherClassroomLinkRecord,
)
from server.app.services.auth_service import CurrentUser


def teacher_allowed_classroom_ids(db: Session, teacher_sync_id: str) -> set[str]:
    link = db.get(TeacherClassroomLinkRecord, teacher_sync_id)
    if link is None:
        return set()
    return set(json.loads(link.classroom_sync_ids_json))


def teacher_can_access_classroom(db: Session, teacher_sync_id: str, classroom_sync_id: str) -> bool:
    return classroom_sync_id in teacher_allowed_classroom_ids(db, teacher_sync_id)


def teacher_can_access_student(db: Session, teacher_sync_id: str, student_sync_id: str) -> bool:
    student = db.get(StudentRecord, student_sync_id)
    if student is None or not student.classroom_sync_id:
        return False
    return teacher_can_access_classroom(db, teacher_sync_id, student.classroom_sync_id)


def get_session_link(db: Session, session_sync_id: str) -> SessionStudentLinkRecord | None:
    return db.get(SessionStudentLinkRecord, session_sync_id)


def teacher_can_access_session(db: Session, teacher_sync_id: str, session_sync_id: str) -> bool:
    """§ Сессия/байланыс/кері байланыс/баға — БАРЛЫҒЫ ОСЫ БІР ережеге
    сүйенеді: мұғалім тек ``session_student_link``-те көрсетілген
    сыныпқа тағайындалған болса ғана қолжетімді. Байланыс әлі ЖОҚ
    болса (§ Phase 2 дизайны — link session-нен КЕЙІН/ТӘУЕЛСІЗ пайда
    болуы мүмкін), ЕШКІМ бұл сессияны иеленбейді деп саналады —
    ``False`` (қауіпсіз әдепкі)."""
    link = get_session_link(db, session_sync_id)
    if link is None:
        return False
    return teacher_can_access_classroom(db, teacher_sync_id, link.classroom_sync_id)


def student_owns_session(db: Session, student_sync_id: str, session_sync_id: str) -> bool:
    link = get_session_link(db, session_sync_id)
    if link is None:
        return False
    return link.student_sync_id == student_sync_id


def classroom_exists(db: Session, classroom_sync_id: str) -> bool:
    return db.get(ClassroomRecord, classroom_sync_id) is not None


def classroom_is_claimed(db: Session, classroom_sync_id: str) -> bool:
    """§ Классрумда КЕМ ДЕГЕНДЕ бір мұғалім тағайындалған ба. ``PUSH_
    ORDER`` реті бойынша ``teacher_classroom`` СЕССИЯДАН/ОҚУШЫДАН КЕЙІН
    жіберіледі (§ ``sync_payload.py``) — сондықтан жаңа құрылған
    классрумға (ӘЛІ ЕШКІМ тағайындалмаған) БІРІНШІ жеткен мұғалім оны
    еркін толтыра алуы керек (§ classroom/student upsert-тегі "unclaimed"
    жол), әйтпесе дәл СОЛ құрушы мұғалімнің ӨЗ жаңа сыныбына бірінші
    оқушыны қосуы ДА тыйым салынған болар еді (§ authorization.py
    докстрингі)."""
    rows = db.query(TeacherClassroomLinkRecord).all()
    for row in rows:
        if classroom_sync_id in json.loads(row.classroom_sync_ids_json):
            return True
    return False


def teacher_can_touch_classroom(db: Session, teacher_sync_id: str, classroom_sync_id: str) -> bool:
    """§ classroom/student upsert-те қолданылатын жеңілдетілген ереже:
    тағайындалған БОЛСА мүше болу керек, ӘЛІ ЕШКІМ тағайындалмаса
    (unclaimed) кез-келген мұғалім еркін."""
    if not classroom_is_claimed(db, classroom_sync_id):
        return True
    return teacher_can_access_classroom(db, teacher_sync_id, classroom_sync_id)


def all_unclaimed_classroom_ids(db: Session, all_classroom_ids: set[str]) -> set[str]:
    claimed: set[str] = set()
    for row in db.query(TeacherClassroomLinkRecord).all():
        claimed.update(json.loads(row.classroom_sync_ids_json))
    return all_classroom_ids - claimed


def teacher_visible_classroom_ids(db: Session, teacher_sync_id: str, all_classroom_ids: set[str]) -> set[str]:
    """§ pull-сүзгіде ЖАЗУ жағымен БІРДЕЙ "unclaimed" ымыраны қайталайды
    (§ ``teacher_can_touch_classroom()`` докстрингі — жаңа құрылған,
    ӘЛІ формалды тағайындалмаған классрумды құрушы мұғалім КӨРЕ алмауы
    сол сессиядағы жеке шектеу болар еді). ``teacher_classroom``
    push-і синхрондалғаннан КЕЙІН бұл классрум "claimed" болып, тек
    НАҚТЫ мүшелерге ғана көрінеді."""
    return teacher_allowed_classroom_ids(db, teacher_sync_id) | all_unclaimed_classroom_ids(
        db, all_classroom_ids
    )


def get_student_classroom_id(db: Session, student_sync_id: str) -> str | None:
    student = db.get(StudentRecord, student_sync_id)
    return student.classroom_sync_id if student is not None else None


def current_user_can_access_session(db: Session, current_user: CurrentUser, session_sync_id: str) -> bool:
    """§ ``sessions``/``feedback-results``/``teacher-assessments`` pull
    үшін ОРТАҚ scoping ережесі — session/feedback/assessment сипаттары
    әртүрлі болса да, ИЕЛІК ЕРЕЖЕСІ БІРДЕЙ (§ ``session_student_link``
    арқылы шешіледі)."""
    if current_user.is_teacher:
        return teacher_can_access_session(db, current_user.sync_id, session_sync_id)
    return student_owns_session(db, current_user.sync_id, session_sync_id)
