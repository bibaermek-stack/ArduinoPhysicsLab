"""Pydantic auth payload schemas (Phase 3: Production Authentication +
Authorization).

Login requests carry the ALREADY-established, ALREADY-synced SHA-256
``pin_hash``/``student_code`` (§ ``domain/services/teacher_pin.py``/
``domain/entities/student.py``) — the raw PIN/access code is NEVER
transmitted (§2 "Do NOT send plaintext PINs/access codes"). This is a
credential-equality check against data the server already has via the
existing ``/api/v1/sync/{teachers,students}`` routes, not a new
password-hashing scheme.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class TeacherLoginRequest(BaseModel):
    sync_id: str = Field(min_length=1)
    pin_hash: str = Field(min_length=1)
    # § Trust-on-first-use bootstrap (§5): тек СЕРВЕР бұл sync_id-ды
    # мүлде білмегенде қолданылады (§ ``auth_service.py`` докстрингі).
    # Кейінгі логиндерде елемейді (тек pin_hash салыстырылады).
    full_name: str = ""


class StudentLoginRequest(BaseModel):
    sync_id: str = Field(min_length=1)
    student_code: str = Field(min_length=1)
    classroom_sync_id: str = ""
    first_name: str = ""
    last_name: str = ""


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    sync_id: str
    expires_at: str  # ISO datetime
