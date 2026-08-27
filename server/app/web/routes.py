"""HTML pages for Arduino Physics Lab on the public internet."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.status import HTTP_303_SEE_OTHER

from server.app.db.session import get_db
from server.app.models.account_models import AccountRecord
from server.app.services.account_service import (
    AccountError,
    create_account_token,
    encode_photo_base64,
    login_account,
    register_account,
    select_role,
)
from server.app.services.auth_service import get_configured_jwt_secret
from server.app.services.people_service import (
    KIND_FRIEND,
    KIND_TEACHER_STUDENT,
    accept_request,
    decline_request,
    list_requests,
    search_people,
    send_request,
)
import jwt

COOKIE = "apl_web_token"
_WEB_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(_WEB_DIR / "templates"))
router = APIRouter()


def _cookie_secure() -> bool:
    from server.app.api.accounts import _public_base_url

    return _public_base_url().startswith("https")


def _set_session(response: Response, token: str, *, secure: bool) -> None:
    response.set_cookie(
        COOKIE,
        token,
        httponly=True,
        samesite="lax",
        secure=secure,
        max_age=60 * 60,
        path="/",
    )


def get_web_account(request: Request, db: Session = Depends(get_db)) -> AccountRecord | None:
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    try:
        payload = jwt.decode(token, get_configured_jwt_secret(), algorithms=["HS256"])
    except jwt.InvalidTokenError:
        return None
    account_id = payload.get("acc") or (payload.get("sub") if payload.get("typ") == "account" else None)
    if not account_id:
        return None
    return db.get(AccountRecord, str(account_id))


def _require_account(account: AccountRecord | None) -> AccountRecord | RedirectResponse:
    if account is None:
        return RedirectResponse("/login", status_code=HTTP_303_SEE_OTHER)
    return account


@router.get("/", response_class=HTMLResponse)
def home(request: Request, account: AccountRecord | None = Depends(get_web_account)) -> HTMLResponse:
    return templates.TemplateResponse(request, "home.html", {"account": account})


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request, error: str = "") -> HTMLResponse:
    return templates.TemplateResponse(request, "login.html", {"error": error})


@router.post("/login")
def login_submit(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Form(...),
    password: str = Form(...),
) -> RedirectResponse:
    try:
        account = login_account(db, email, password)
    except AccountError as exc:
        return RedirectResponse(f"/login?error={exc}", status_code=HTTP_303_SEE_OTHER)
    token, _ = create_account_token(account)
    target = "/app" if account.role else "/role"
    response = RedirectResponse(target, status_code=HTTP_303_SEE_OTHER)
    _set_session(response, token, secure=request.url.scheme == "https")
    return response


@router.get("/register", response_class=HTMLResponse)
def register_form(request: Request, error: str = "") -> HTMLResponse:
    return templates.TemplateResponse(request, "register.html", {"error": error})


@router.post("/register")
def register_submit(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Form(...),
    password: str = Form(...),
    display_name: str = Form(""),
) -> RedirectResponse:
    try:
        account = register_account(db, email, password, display_name)
        db.commit()
        db.refresh(account)
    except AccountError as exc:
        db.rollback()
        return RedirectResponse(f"/register?error={exc}", status_code=HTTP_303_SEE_OTHER)
    token, _ = create_account_token(account)
    response = RedirectResponse("/role", status_code=HTTP_303_SEE_OTHER)
    _set_session(response, token, secure=request.url.scheme == "https")
    return response


@router.get("/google")
def google_web() -> RedirectResponse:
    return RedirectResponse("/api/v1/auth/google/start", status_code=HTTP_303_SEE_OTHER)


@router.get("/logout")
def logout() -> RedirectResponse:
    response = RedirectResponse("/", status_code=HTTP_303_SEE_OTHER)
    response.delete_cookie(COOKIE, path="/")
    return response


@router.get("/role", response_class=HTMLResponse, response_model=None)
def role_form(
    request: Request,
    db: Session = Depends(get_db),
    account: AccountRecord | None = Depends(get_web_account),
    error: str = "",
) -> Response:
    if account is None:
        return RedirectResponse("/login", status_code=HTTP_303_SEE_OTHER)
    if account.role:
        return RedirectResponse("/app", status_code=HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(request, "role.html", {"account": account, "error": error})


@router.post("/role")
def role_submit(
    request: Request,
    db: Session = Depends(get_db),
    account: AccountRecord | None = Depends(get_web_account),
    role: str = Form(...),
) -> RedirectResponse:
    if account is None:
        return RedirectResponse("/login", status_code=HTTP_303_SEE_OTHER)
    try:
        account = select_role(db, account, role)
        db.commit()
        db.refresh(account)
    except AccountError as exc:
        db.rollback()
        return RedirectResponse(f"/role?error={exc}", status_code=HTTP_303_SEE_OTHER)
    token, _ = create_account_token(account)
    response = RedirectResponse("/app", status_code=HTTP_303_SEE_OTHER)
    _set_session(response, token, secure=request.url.scheme == "https")
    return response


@router.get("/app", response_class=HTMLResponse, response_model=None)
def app_home(
    request: Request,
    db: Session = Depends(get_db),
    account: AccountRecord | None = Depends(get_web_account),
) -> Response:
    if account is None:
        return RedirectResponse("/login", status_code=HTTP_303_SEE_OTHER)
    if not account.role:
        return RedirectResponse("/role", status_code=HTTP_303_SEE_OTHER)
    incoming = list_requests(db, account)
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "account": account,
            "photo": encode_photo_base64(account.photo_bytes),
            "incoming_count": sum(1 for row, _f, _t in incoming if row.to_account_id == account.id),
        },
    )


@router.get("/profile", response_class=HTMLResponse, response_model=None)
def profile_page(
    request: Request,
    account: AccountRecord | None = Depends(get_web_account),
    saved: str = "",
    error: str = "",
) -> Response:
    if account is None:
        return RedirectResponse("/login", status_code=HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request,
        "profile.html",
        {
            "account": account,
            "photo": encode_photo_base64(account.photo_bytes),
            "saved": saved,
            "error": error,
        },
    )


@router.post("/profile")
async def profile_save(
    db: Session = Depends(get_db),
    account: AccountRecord | None = Depends(get_web_account),
    display_name: str = Form(""),
    photo: UploadFile | None = File(None),
) -> RedirectResponse:
    if account is None:
        return RedirectResponse("/login", status_code=HTTP_303_SEE_OTHER)
    name = display_name.strip()
    if name:
        account.display_name = name
    if photo is not None and photo.filename:
        data = await photo.read()
        if len(data) > 500_000:
            return RedirectResponse("/profile?error=Сурет+500+KB-тан+аспауы+керек", status_code=HTTP_303_SEE_OTHER)
        if data:
            account.photo_bytes = data
    db.commit()
    return RedirectResponse("/profile?saved=1", status_code=HTTP_303_SEE_OTHER)


@router.get("/people", response_class=HTMLResponse, response_model=None)
def people_page(
    request: Request,
    db: Session = Depends(get_db),
    account: AccountRecord | None = Depends(get_web_account),
    q: str = "",
    error: str = "",
    ok: str = "",
) -> Response:
    if account is None:
        return RedirectResponse("/login", status_code=HTTP_303_SEE_OTHER)
    results = search_people(db, q) if q else []
    incoming = list_requests(db, account)
    return templates.TemplateResponse(
        request,
        "people.html",
        {
            "account": account,
            "q": q,
            "results": results,
            "requests": incoming,
            "error": error,
            "ok": ok,
        },
    )


@router.post("/people/request")
def people_request(
    db: Session = Depends(get_db),
    account: AccountRecord | None = Depends(get_web_account),
    to_public_id: str = Form(...),
    kind: str = Form(...),
) -> RedirectResponse:
    if account is None:
        return RedirectResponse("/login", status_code=HTTP_303_SEE_OTHER)
    mapped = KIND_FRIEND if kind == "friend" else KIND_TEACHER_STUDENT
    try:
        send_request(db, account, to_public_id, mapped)
        db.commit()
    except AccountError as exc:
        db.rollback()
        return RedirectResponse(f"/people?error={exc}", status_code=HTTP_303_SEE_OTHER)
    return RedirectResponse("/people?ok=1", status_code=HTTP_303_SEE_OTHER)


@router.post("/people/accept")
def people_accept(
    db: Session = Depends(get_db),
    account: AccountRecord | None = Depends(get_web_account),
    request_id: str = Form(...),
) -> RedirectResponse:
    if account is None:
        return RedirectResponse("/login", status_code=HTTP_303_SEE_OTHER)
    try:
        accept_request(db, account, request_id)
        db.commit()
    except AccountError as exc:
        db.rollback()
        return RedirectResponse(f"/people?error={exc}", status_code=HTTP_303_SEE_OTHER)
    return RedirectResponse("/people?ok=1", status_code=HTTP_303_SEE_OTHER)


@router.post("/people/decline")
def people_decline(
    db: Session = Depends(get_db),
    account: AccountRecord | None = Depends(get_web_account),
    request_id: str = Form(...),
) -> RedirectResponse:
    if account is None:
        return RedirectResponse("/login", status_code=HTTP_303_SEE_OTHER)
    try:
        decline_request(db, account, request_id)
        db.commit()
    except AccountError as exc:
        db.rollback()
        return RedirectResponse(f"/people?error={exc}", status_code=HTTP_303_SEE_OTHER)
    return RedirectResponse("/people?ok=1", status_code=HTTP_303_SEE_OTHER)
