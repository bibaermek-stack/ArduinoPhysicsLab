"""auth_service — JWT issuance/validation + teacher/student login
(Phase 3: Production Authentication + Authorization).

§ Token model: short-lived (60 min) HS256 JWT, payload carries ONLY
``sub`` (the authenticated Teacher/Student ``sync_id``) and ``role`` —
NEVER classroom/student lists (§4 "Do not trust ... if the server can
derive them from the authenticated identity" — every authorization
check in ``authorization.py`` re-resolves current assignments live from
the DB on every request, so a revoked classroom assignment takes effect
immediately without waiting for token expiry).

§ Secret: ``APL_JWT_SECRET`` env var, dev fallback — SAME "opt-in env
var + local dev default" convention as ``APL_TEACHER_PIN``/
``APL_SYNC_API_KEY`` (``domain/services/teacher_pin.py``/
``server/app/api/deps.py``). Never commit a real secret.

§ Bootstrap (§5 "Bootstrap / First Login"): a login request for a
``sync_id`` the server has NEVER seen creates a minimal record right
then (trust-on-first-use) using the pin_hash/student_code supplied in
THAT request — deterministic, idempotent (subsequent logins for the
same sync_id just compare against the now-stored hash), no destructive
migration, no admin step required. This mirrors SSH host-key TOFU: the
first device to authenticate as a given identity establishes it.
"""

from __future__ import annotations

import hmac
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from sqlalchemy.orm import Session

from server.app.models.sync_models import StudentRecord, TeacherRecord
from server.app.schemas.auth import StudentLoginRequest, TeacherLoginRequest

_ENV_VAR_NAME = "APL_JWT_SECRET"
# § >=32 байт (RFC 7518 §3.2 HS256 ұсынымы) — жай "dev-local-only-key"
# (Phase 1 API кілтімен БІРДЕЙ форма) тым қысқа болар еді.
_DEV_DEFAULT_SECRET = "dev-local-only-jwt-secret-not-for-production-use"
_ALGORITHM = "HS256"
_TOKEN_TTL_MINUTES = 60

ROLE_TEACHER = "teacher"
ROLE_STUDENT = "student"


@dataclass(frozen=True)
class CurrentUser:
    sync_id: str
    role: str

    @property
    def is_teacher(self) -> bool:
        return self.role == ROLE_TEACHER

    @property
    def is_student(self) -> bool:
        return self.role == ROLE_STUDENT


class AuthenticationError(ValueError):
    """§ Incorrect pin_hash/student_code for an already-known sync_id."""


def get_configured_jwt_secret() -> str:
    return os.environ.get(_ENV_VAR_NAME) or _DEV_DEFAULT_SECRET


def create_access_token(sync_id: str, role: str) -> tuple[str, datetime]:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=_TOKEN_TTL_MINUTES)
    payload = {"sub": sync_id, "role": role, "exp": expires_at}
    token = jwt.encode(payload, get_configured_jwt_secret(), algorithm=_ALGORITHM)
    return token, expires_at


def decode_access_token(token: str) -> tuple[str, str]:
    """``(sync_id, role)`` қайтарады. ``jwt.ExpiredSignatureError``/
    ``jwt.InvalidTokenError`` (малформед/қолтаңба сәйкессіз/т.б.)
    шақырушыға таралады — ``server/app/api/deps.py`` осыны 401-ге
    аударады."""
    payload = jwt.decode(token, get_configured_jwt_secret(), algorithms=[_ALGORITHM])
    return payload["sub"], payload["role"]


def authenticate_teacher(db: Session, request: TeacherLoginRequest) -> TeacherRecord:
    record = db.get(TeacherRecord, request.sync_id)
    if record is None:
        # § Trust-on-first-use bootstrap.
        record = TeacherRecord(
            sync_id=request.sync_id,
            full_name=request.full_name or request.sync_id,
            pin_hash=request.pin_hash,
            is_active=True,
            server_revision=1,
        )
        db.add(record)
        db.flush()
        return record
    if not hmac.compare_digest(record.pin_hash, request.pin_hash):
        raise AuthenticationError("PIN хэші сәйкес келмейді")
    return record


def authenticate_student(db: Session, request: StudentLoginRequest) -> StudentRecord:
    record = db.get(StudentRecord, request.sync_id)
    if record is None:
        # § Trust-on-first-use bootstrap. classroom_sync_id БОС қалса да
        # қауіпсіз — тек ownership тексерулерінде сол сынып бос жол болып
        # қалады, кейін қалыпты ``/api/v1/sync/students`` push-і арқылы
        # НАҚТЫ classroom_sync_id-мен ауыстырылады (INSERT OR REPLACE
        # семантикасы жоқ SQLAlchemy update жолымен).
        record = StudentRecord(
            sync_id=request.sync_id,
            classroom_sync_id=request.classroom_sync_id,
            first_name=request.first_name or request.sync_id,
            last_name=request.last_name,
            student_code=request.student_code,
            is_archived=False,
            server_revision=1,
        )
        db.add(record)
        db.flush()
        return record
    if not hmac.compare_digest(record.student_code, request.student_code):
        raise AuthenticationError("Оқушы коды сәйкес келмейді")
    return record
