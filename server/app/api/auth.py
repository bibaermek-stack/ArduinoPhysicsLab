"""api.auth — Phase 3 login routes.

    POST /api/v1/auth/teacher-login
    POST /api/v1/auth/student-login

Gated by ``require_api_key()`` only (§ "this is how you GET a JWT in
the first place" — cannot also require ``get_current_user()``). Login
requests carry ``pin_hash``/``student_code`` (already-hashed/existing
local credential material), never a raw PIN (§2).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from server.app.api.deps import require_api_key
from server.app.db.session import get_db
from server.app.schemas.auth import StudentLoginRequest, TeacherLoginRequest, TokenResponse
from server.app.services import auth_service
from server.app.services.auth_service import AuthenticationError

router = APIRouter(prefix="/auth", tags=["auth"], dependencies=[Depends(require_api_key)])


@router.post("/teacher-login", response_model=TokenResponse)
def teacher_login(request: TeacherLoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    try:
        record = auth_service.authenticate_teacher(db, request)
    except AuthenticationError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(error)) from None
    db.commit()
    token, expires_at = auth_service.create_access_token(record.sync_id, auth_service.ROLE_TEACHER)
    return TokenResponse(
        access_token=token, role=auth_service.ROLE_TEACHER, sync_id=record.sync_id,
        expires_at=expires_at.isoformat(),
    )


@router.post("/student-login", response_model=TokenResponse)
def student_login(request: StudentLoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    try:
        record = auth_service.authenticate_student(db, request)
    except AuthenticationError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(error)) from None
    db.commit()
    token, expires_at = auth_service.create_access_token(record.sync_id, auth_service.ROLE_STUDENT)
    return TokenResponse(
        access_token=token, role=auth_service.ROLE_STUDENT, sync_id=record.sync_id,
        expires_at=expires_at.isoformat(),
    )
