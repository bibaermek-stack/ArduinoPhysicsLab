"""Account register/login, Google OAuth, profile."""

from __future__ import annotations

import os
import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from server.app.api.deps import get_current_account, require_api_key
from server.app.db.session import get_db
from server.app.models.account_models import AccountRecord
from server.app.schemas.account import (
    AccountProfileResponse,
    AccountTokenResponse,
    LoginRequest,
    ProfileUpdateRequest,
    RegisterRequest,
    SelectRoleRequest,
)
from server.app.services.account_service import (
    AccountError,
    create_account_token,
    decode_photo_base64,
    encode_photo_base64,
    get_google_oauth_config,
    login_account,
    register_account,
    select_role,
    upsert_google_account,
)

router = APIRouter(prefix="/auth", tags=["accounts"])
me_router = APIRouter(prefix="/me", tags=["accounts"])

_google_states: dict[str, dict] = {}


def _token_response(account: AccountRecord) -> AccountTokenResponse:
    token, expires_at = create_account_token(account)
    return AccountTokenResponse(
        access_token=token,
        role=account.role,
        account_id=account.id,
        public_id=account.public_id,
        display_name=account.display_name,
        expires_at=expires_at.isoformat(),
        needs_role=account.role is None,
    )


def _profile(account: AccountRecord) -> AccountProfileResponse:
    return AccountProfileResponse(
        account_id=account.id,
        email=account.email,
        display_name=account.display_name,
        role=account.role,
        public_id=account.public_id,
        photo_base64=encode_photo_base64(account.photo_bytes),
        needs_role=account.role is None,
    )


@router.post("/register", response_model=AccountTokenResponse, dependencies=[Depends(require_api_key)])
def register(body: RegisterRequest, db: Session = Depends(get_db)) -> AccountTokenResponse:
    try:
        account = register_account(db, body.email, body.password, body.display_name)
    except AccountError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from None
    db.commit()
    db.refresh(account)
    return _token_response(account)


@router.post("/login", response_model=AccountTokenResponse, dependencies=[Depends(require_api_key)])
def login(body: LoginRequest, db: Session = Depends(get_db)) -> AccountTokenResponse:
    try:
        account = login_account(db, body.email, body.password)
    except AccountError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(error)) from None
    return _token_response(account)


@router.post("/select-role", response_model=AccountTokenResponse, dependencies=[Depends(require_api_key)])
def select_account_role(
    body: SelectRoleRequest,
    db: Session = Depends(get_db),
    account: AccountRecord = Depends(get_current_account),
) -> AccountTokenResponse:
    try:
        account = select_role(db, account, body.role)
    except AccountError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from None
    db.commit()
    db.refresh(account)
    return _token_response(account)


_DEFAULT_PUBLIC_BASE = "https://arduinophysicslab-production-ab65.up.railway.app"


def _public_base_url() -> str:
    return os.environ.get("APL_PUBLIC_BASE_URL", _DEFAULT_PUBLIC_BASE).rstrip("/")


def _google_redirect_uri(_request: Request | None = None) -> str:
    """Google Console-дағы URI-мен БІРДЕЙ болуы керек — request host-қа тәуелді емес."""
    return os.environ.get(
        "APL_GOOGLE_REDIRECT_URI",
        f"{_public_base_url()}/api/v1/auth/google/callback",
    ).strip()


@router.get("/google/start")
def google_start(request: Request, desktop_port: int = Query(default=0)) -> RedirectResponse:
    client_id, client_secret = get_google_oauth_config()
    if not client_id or not client_secret:
        raise HTTPException(status_code=503, detail="Google кіру бапталмаған")
    state = secrets.token_urlsafe(16)
    redirect_uri = _google_redirect_uri(request)
    _google_states[state] = {"desktop_port": desktop_port, "redirect_uri": redirect_uri}
    params = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "access_type": "online",
            "prompt": "select_account",
        }
    )
    return RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{params}")


@router.get("/google/callback")
def google_callback(
    request: Request,
    db: Session = Depends(get_db),
    code: str = "",
    state: str = "",
) -> RedirectResponse:
    client_id, client_secret = get_google_oauth_config()
    if not client_id or not client_secret:
        raise HTTPException(status_code=503, detail="Google кіру бапталмаған")
    stored = _google_states.pop(state, {})
    if isinstance(stored, int):
        stored = {"desktop_port": stored, "redirect_uri": _google_redirect_uri(request)}
    desktop_port = int(stored.get("desktop_port") or 0)
    redirect_uri = str(stored.get("redirect_uri") or _google_redirect_uri(request))
    token_response = httpx.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=15.0,
    )
    if token_response.status_code != 200:
        raise HTTPException(status_code=401, detail="Google кіру сәтсіз")
    access = token_response.json().get("access_token")
    userinfo = httpx.get(
        "https://openidconnect.googleapis.com/v1/userinfo",
        headers={"Authorization": f"Bearer {access}"},
        timeout=15.0,
    )
    if userinfo.status_code != 200:
        raise HTTPException(status_code=401, detail="Google профилі оқылмады")
    info = userinfo.json()
    account = upsert_google_account(
        db,
        google_sub=str(info.get("sub") or ""),
        email=info.get("email"),
        display_name=str(info.get("name") or ""),
    )
    db.commit()
    db.refresh(account)
    token, _expires = create_account_token(account)
    if desktop_port:
        return RedirectResponse(
            f"http://127.0.0.1:{desktop_port}/?token={token}&needs_role={'1' if account.role is None else '0'}"
        )
    target = "/role" if account.role is None else "/app"
    response = RedirectResponse(target)
    response.set_cookie(
        "apl_web_token",
        token,
        httponly=True,
        samesite="lax",
        secure=_public_base_url().startswith("https"),
        max_age=60 * 60,
        path="/",
    )
    return response


@me_router.get("", response_model=AccountProfileResponse, dependencies=[Depends(require_api_key)])
def read_me(account: AccountRecord = Depends(get_current_account)) -> AccountProfileResponse:
    return _profile(account)


@me_router.patch("", response_model=AccountProfileResponse, dependencies=[Depends(require_api_key)])
def update_me(
    body: ProfileUpdateRequest,
    db: Session = Depends(get_db),
    account: AccountRecord = Depends(get_current_account),
) -> AccountProfileResponse:
    if body.display_name is not None:
        name = body.display_name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Аты бос болмауы керек")
        account.display_name = name
    if body.photo_base64 is not None:
        if body.photo_base64 == "":
            account.photo_bytes = None
        else:
            try:
                account.photo_bytes = decode_photo_base64(body.photo_base64)
            except AccountError as error:
                raise HTTPException(status_code=400, detail=str(error)) from None
    db.commit()
    db.refresh(account)
    return _profile(account)
