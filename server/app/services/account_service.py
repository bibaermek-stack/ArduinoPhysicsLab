"""Account register/login, password hashing, public IDs, role bootstrap."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt

import json

from sqlalchemy.orm import Session

from server.app.models.account_models import AccountRecord
from server.app.models.sync_models import ClassroomRecord, TeacherClassroomLinkRecord, TeacherRecord, StudentRecord
from server.app.services.auth_service import _ALGORITHM, _TOKEN_TTL_MINUTES, get_configured_jwt_secret

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_ID_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_MAX_PHOTO_BYTES = 500_000
_PBKDF2_ROUNDS = 120_000


class AccountError(ValueError):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), _PBKDF2_ROUNDS
    ).hex()
    return f"pbkdf2${_PBKDF2_ROUNDS}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, rounds_s, salt, digest = stored.split("$", 3)
    except ValueError:
        return False
    if scheme != "pbkdf2":
        return False
    check = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), int(rounds_s)
    ).hex()
    return hmac.compare_digest(check, digest)


def allocate_public_id(db: Session, role: str) -> str:
    prefix = "T" if role == "teacher" else "S"
    for _ in range(32):
        body = "".join(secrets.choice(_ID_ALPHABET) for _ in range(6))
        public_id = f"{prefix}-{body}"
        exists = db.query(AccountRecord).filter(AccountRecord.public_id == public_id).first()
        if exists is None:
            return public_id
    raise AccountError("ID генерациясы сәтсіз")


def create_account_token(account: AccountRecord) -> tuple[str, datetime]:
    expires_at = _utcnow() + timedelta(minutes=_TOKEN_TTL_MINUTES)
    role = account.role or "account"
    sub = account.teacher_sync_id or account.student_sync_id or account.id
    payload = {
        "sub": sub,
        "role": role,
        "acc": account.id,
        "typ": "account",
        "exp": expires_at,
    }
    token = jwt.encode(payload, get_configured_jwt_secret(), algorithm=_ALGORITHM)
    return token, expires_at


def register_account(db: Session, email: str, password: str, display_name: str) -> AccountRecord:
    normalized = normalize_email(email)
    if not _EMAIL_RE.match(normalized):
        raise AccountError("Email пішімі дұрыс емес")
    if db.query(AccountRecord).filter(AccountRecord.email == normalized).first() is not None:
        raise AccountError("Бұл email әлдеқашан тіркелген")
    name = display_name.strip() or normalized.split("@")[0]
    record = AccountRecord(
        id=str(uuid.uuid4()),
        email=normalized,
        password_hash=hash_password(password),
        display_name=name,
    )
    db.add(record)
    db.flush()
    return record


def login_account(db: Session, email: str, password: str) -> AccountRecord:
    normalized = normalize_email(email)
    record = db.query(AccountRecord).filter(AccountRecord.email == normalized).first()
    if record is None or not record.password_hash:
        raise AccountError("Email немесе құпия сөз қате")
    if not verify_password(password, record.password_hash):
        raise AccountError("Email немесе құпия сөз қате")
    return record


def upsert_google_account(db: Session, google_sub: str, email: str | None, display_name: str) -> AccountRecord:
    record = db.query(AccountRecord).filter(AccountRecord.google_sub == google_sub).first()
    if record is not None:
        return record
    normalized = normalize_email(email) if email else None
    if normalized:
        by_email = db.query(AccountRecord).filter(AccountRecord.email == normalized).first()
        if by_email is not None:
            by_email.google_sub = google_sub
            db.flush()
            return by_email
    record = AccountRecord(
        id=str(uuid.uuid4()),
        email=normalized,
        google_sub=google_sub,
        display_name=display_name.strip() or (normalized.split("@")[0] if normalized else "Пайдаланушы"),
    )
    db.add(record)
    db.flush()
    return record


def select_role(db: Session, account: AccountRecord, role: str) -> AccountRecord:
    if role not in ("student", "teacher"):
        raise AccountError("Рөл student немесе teacher болуы керек")
    if account.role and account.role != role:
        raise AccountError("Рөл әлдеқашан таңдалған")
    if account.role == role:
        return account
    account.role = role
    account.public_id = allocate_public_id(db, role)
    now = _utcnow()
    if role == "teacher":
        sync_id = str(uuid.uuid4())
        teacher = TeacherRecord(
            sync_id=sync_id,
            full_name=account.display_name,
            pin_hash=hashlib.sha256(account.id.encode("utf-8")).hexdigest(),
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        db.add(teacher)
        classroom_id = str(uuid.uuid4())
        db.add(
            ClassroomRecord(
                sync_id=classroom_id,
                name="Менің сыныбым",
                academic_year="",
                description="",
                created_at=now,
                updated_at=now,
            )
        )
        # Postgres FK: sync_teacher_classrooms.teacher_sync_id → sync_teachers
        db.flush()
        db.add(
            TeacherClassroomLinkRecord(
                teacher_sync_id=sync_id,
                classroom_sync_ids_json=json.dumps([classroom_id]),
                updated_at=now,
            )
        )
        account.teacher_sync_id = sync_id
    else:
        sync_id = str(uuid.uuid4())
        db.add(
            StudentRecord(
                sync_id=sync_id,
                classroom_sync_id=None,
                first_name=account.display_name,
                last_name="",
                student_code=account.public_id.replace("-", "")[:8],
                created_at=now,
                updated_at=now,
            )
        )
        account.student_sync_id = sync_id
    db.flush()
    return account


def decode_photo_base64(raw: str) -> bytes:
    payload = raw.strip()
    if "," in payload and payload.lower().startswith("data:"):
        payload = payload.split(",", 1)[1]
    try:
        data = base64.b64decode(payload, validate=True)
    except Exception as exc:
        raise AccountError("Сурет пішімі дұрыс емес") from exc
    if len(data) > _MAX_PHOTO_BYTES:
        raise AccountError("Сурет 500 KB-тан аспауы керек")
    if not data:
        raise AccountError("Сурет бос")
    return data


def encode_photo_base64(data: bytes | None) -> str | None:
    if not data:
        return None
    return base64.b64encode(data).decode("ascii")


def get_google_oauth_config() -> tuple[str, str]:
    client_id = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
    return client_id, client_secret
