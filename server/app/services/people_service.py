"""People search and relationship requests."""

from __future__ import annotations

import json
import uuid

from sqlalchemy import or_
from sqlalchemy.orm import Session

from server.app.models.account_models import (
    AccountRecord,
    RelationshipLinkRecord,
    RelationshipRequestRecord,
)
from server.app.models.sync_models import StudentRecord, TeacherClassroomLinkRecord
from server.app.services.account_service import AccountError


KIND_TEACHER_STUDENT = "teacher_student"
KIND_FRIEND = "friend"


def _link_pair(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a < b else (b, a)


def search_people(db: Session, query: str, limit: int = 20) -> list[AccountRecord]:
    needle = query.strip()
    if len(needle) < 2:
        return []
    pattern = f"%{needle}%"
    rows = (
        db.query(AccountRecord)
        .filter(AccountRecord.public_id.isnot(None))
        .filter(
            or_(
                AccountRecord.public_id.ilike(pattern),
                AccountRecord.display_name.ilike(pattern),
                AccountRecord.email.ilike(pattern),
            )
        )
        .limit(limit)
        .all()
    )
    return rows


def search_teachers(db: Session, query: str, limit: int = 20) -> list[AccountRecord]:
    """Аты немесе T- коды бойынша тек мұғалімдер."""
    needle = query.strip()
    if len(needle) < 2:
        return []
    pattern = f"%{needle}%"
    return (
        db.query(AccountRecord)
        .filter(AccountRecord.role == "teacher")
        .filter(AccountRecord.public_id.isnot(None))
        .filter(
            or_(
                AccountRecord.public_id.ilike(pattern),
                AccountRecord.display_name.ilike(pattern),
                AccountRecord.email.ilike(pattern),
            )
        )
        .limit(limit)
        .all()
    )


def connect_to_teacher(db: Session, student: AccountRecord, teacher_code: str) -> RelationshipRequestRecord:
    """Оқушы мұғалім кодын (T-XXXXXX) енгізіп, қосылу өтінішін жібереді."""
    if student.role != "student":
        raise AccountError("Мұғалімге тек оқушы қосыла алады")
    code = teacher_code.strip().upper()
    if not code:
        raise AccountError("Мұғалім кодын енгізіңіз")
    info = student_link_status(db, student)
    if info.get("link_status") == "active":
        raise AccountError("Сіз әлдеқашан мұғалімге қосылғансыз")
    pending_teacher = info.get("teacher") if info.get("link_status") == "pending" else None
    pending_code = (getattr(pending_teacher, "public_id", None) or "").upper()
    if pending_code and pending_code != code:
        raise AccountError("Өтініш әлдеқашан жіберілген. Қабылдау күтілуде.")
    try:
        teacher = get_by_public_id(db, code)
    except AccountError as error:
        raise AccountError("Мұғалім коды табылмады") from error
    if teacher.role != "teacher":
        raise AccountError("Бұл код мұғалімге тиесілі емес")
    return send_request(db, student, teacher.public_id or code, KIND_TEACHER_STUDENT)


def student_link_status(db: Session, account: AccountRecord) -> dict:
    """Оқушы: independent / pending / active. Мұғалім: invite_code = public_id."""
    if account.role == "teacher":
        return {
            "link_status": "active",
            "teacher": None,
            "invite_code": account.public_id,
        }
    if account.role != "student":
        return {"link_status": "independent", "teacher": None, "invite_code": None}

    links = (
        db.query(RelationshipLinkRecord)
        .filter(
            RelationshipLinkRecord.kind == KIND_TEACHER_STUDENT,
            or_(
                RelationshipLinkRecord.account_a_id == account.id,
                RelationshipLinkRecord.account_b_id == account.id,
            ),
        )
        .all()
    )
    for link in links:
        other_id = link.account_b_id if link.account_a_id == account.id else link.account_a_id
        other = db.get(AccountRecord, other_id)
        if other is not None and other.role == "teacher":
            return {"link_status": "active", "teacher": other, "invite_code": None}

    pending = (
        db.query(RelationshipRequestRecord)
        .filter(
            RelationshipRequestRecord.kind == KIND_TEACHER_STUDENT,
            RelationshipRequestRecord.from_account_id == account.id,
            RelationshipRequestRecord.status == "pending",
        )
        .first()
    )
    if pending is not None:
        target = db.get(AccountRecord, pending.to_account_id)
        return {"link_status": "pending", "teacher": target, "invite_code": None}

    return {"link_status": "independent", "teacher": None, "invite_code": None}


def get_by_public_id(db: Session, public_id: str) -> AccountRecord:
    record = db.query(AccountRecord).filter(AccountRecord.public_id == public_id.strip().upper()).first()
    if record is None:
        # also try as-typed
        record = db.query(AccountRecord).filter(AccountRecord.public_id == public_id.strip()).first()
    if record is None:
        raise AccountError("Пайдаланушы табылмады")
    return record


def send_request(db: Session, sender: AccountRecord, to_public_id: str, kind: str) -> RelationshipRequestRecord:
    if not sender.role or not sender.public_id:
        raise AccountError("Алдымен рөл таңдаңыз")
    target = get_by_public_id(db, to_public_id)
    if target.id == sender.id:
        raise AccountError("Өзіңізге өтініш жібере алмайсыз")
    if not target.role:
        raise AccountError("Қарсы жақ әлі рөл таңдамаған")
    if kind == KIND_TEACHER_STUDENT:
        pair = {sender.role, target.role}
        if pair != {"teacher", "student"}:
            raise AccountError("Мұғалім мен оқушы арасында ғана өтініш жіберіледі")
    elif kind == KIND_FRIEND:
        if sender.role != "student" or target.role != "student":
            raise AccountError("Дос өтінішін тек оқушылар жібере алады")
    else:
        raise AccountError("Өтініш түрі белгісіз")

    a, b = _link_pair(sender.id, target.id)
    existing_link = (
        db.query(RelationshipLinkRecord)
        .filter(
            RelationshipLinkRecord.kind == kind,
            RelationshipLinkRecord.account_a_id == a,
            RelationshipLinkRecord.account_b_id == b,
        )
        .first()
    )
    if existing_link is not None:
        raise AccountError("Байланыс әлдеқашан бар")

    pending = (
        db.query(RelationshipRequestRecord)
        .filter(
            RelationshipRequestRecord.kind == kind,
            RelationshipRequestRecord.status == "pending",
            RelationshipRequestRecord.from_account_id == sender.id,
            RelationshipRequestRecord.to_account_id == target.id,
        )
        .first()
    )
    if pending is not None:
        return pending

    record = RelationshipRequestRecord(
        id=str(uuid.uuid4()),
        kind=kind,
        from_account_id=sender.id,
        to_account_id=target.id,
        status="pending",
    )
    db.add(record)
    db.flush()
    return record


def list_requests(db: Session, account: AccountRecord) -> list[tuple[RelationshipRequestRecord, AccountRecord, AccountRecord]]:
    rows = (
        db.query(RelationshipRequestRecord)
        .filter(
            RelationshipRequestRecord.status == "pending",
            or_(
                RelationshipRequestRecord.to_account_id == account.id,
                RelationshipRequestRecord.from_account_id == account.id,
            ),
        )
        .all()
    )
    result = []
    for row in rows:
        from_acc = db.get(AccountRecord, row.from_account_id)
        to_acc = db.get(AccountRecord, row.to_account_id)
        if from_acc and to_acc:
            result.append((row, from_acc, to_acc))
    return result


def _attach_student_to_teacher_classroom(db: Session, teacher: AccountRecord, student: AccountRecord) -> None:
    if not teacher.teacher_sync_id or not student.student_sync_id:
        return
    link = db.get(TeacherClassroomLinkRecord, teacher.teacher_sync_id)
    if link is None:
        return
    try:
        classroom_ids = json.loads(link.classroom_sync_ids_json or "[]")
    except json.JSONDecodeError:
        classroom_ids = []
    if not classroom_ids:
        return
    student_row = db.get(StudentRecord, student.student_sync_id)
    if student_row is None:
        return
    if not student_row.classroom_sync_id:
        student_row.classroom_sync_id = classroom_ids[0]


def accept_request(db: Session, account: AccountRecord, request_id: str) -> RelationshipRequestRecord:
    row = db.get(RelationshipRequestRecord, request_id)
    if row is None or row.to_account_id != account.id:
        raise AccountError("Өтініш табылмады")
    if row.status != "pending":
        raise AccountError("Өтініш әлдеқашан жабылған")
    row.status = "accepted"
    a, b = _link_pair(row.from_account_id, row.to_account_id)
    db.add(
        RelationshipLinkRecord(
            id=str(uuid.uuid4()),
            kind=row.kind,
            account_a_id=a,
            account_b_id=b,
        )
    )
    if row.kind == KIND_TEACHER_STUDENT:
        other = db.get(AccountRecord, row.from_account_id)
        if other is not None:
            teacher = account if account.role == "teacher" else other
            student = other if account.role == "teacher" else account
            _attach_student_to_teacher_classroom(db, teacher, student)
    db.flush()
    return row


def decline_request(db: Session, account: AccountRecord, request_id: str) -> RelationshipRequestRecord:
    row = db.get(RelationshipRequestRecord, request_id)
    if row is None or row.to_account_id != account.id:
        raise AccountError("Өтініш табылмады")
    if row.status != "pending":
        raise AccountError("Өтініш әлдеқашан жабылған")
    row.status = "declined"
    db.flush()
    return row
