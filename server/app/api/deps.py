"""api.deps — ортақ FastAPI dependency-лер.

§ Phase 1 "Authentication Design" бұл фазада ТОЛЫҚ мұғалім/оқушы токен-
негізді аутентификацияны ІСКЕ АСЫРМАДЫ — тек ортақ API кілті. Phase 3
(Production Authentication + Authorization) енді НАҚТЫ пайдаланушы-
негізді JWT қосады (``get_current_user()``), БІРАҚ ``require_api_key()``
ӘЛІ ДЕ сақталады, ЕКЕУІ БІРГЕ (§ "defense in depth", Phase 1-дің ЕШБІР
жұмыс істеп тұрған механизмі бұзылмайды) — ``X-API-Key`` "бұл заңды
клиент қолданбасы ма" деген өрескел қорғаныс, ``Authorization: Bearer``
JWT "бұл НАҚТЫ қай пайдаланушы" деген нәзік қорғаныс.

Кілт/құпия ЕШҚАШАН қатты кодталмайды (§10 "Never commit... API keys") —
``APL_SYNC_API_KEY``/``APL_JWT_SECRET`` орта айнымалыларынан оқылады,
``domain/services/teacher_pin.py::_DEFAULT_DEV_PIN``-мен БІРДЕЙ
established "opt-in env var + жергілікті әзірлеу әдепкісі" конвенциясы.
"""

from __future__ import annotations

import os

import jwt
from fastapi import Header, HTTPException, status

from server.app.services.auth_service import CurrentUser, decode_access_token

_ENV_VAR_NAME = "APL_SYNC_API_KEY"
_DEV_DEFAULT_API_KEY = "dev-local-only-key"


def get_configured_api_key() -> str:
    return os.environ.get(_ENV_VAR_NAME) or _DEV_DEFAULT_API_KEY


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    expected = get_configured_api_key()
    if x_api_key != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing X-API-Key")


def get_current_user(authorization: str | None = Header(default=None)) -> CurrentUser:
    """§ Phase 3: ``Authorization: Bearer <jwt>`` тақырыбынан
    аутентификацияланған пайдаланушыны шешеді. Жоқ/малформед/мерзімі
    өткен токен — БӘРІ 401 (§10/§11: "validate malformed tokens",
    "validate expired tokens", "missing token")."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or malformed Authorization header"
        )
    token = authorization.removeprefix("Bearer ").strip()
    try:
        sync_id, role = decode_access_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired") from None
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from None
    return CurrentUser(sync_id=sync_id, role=role)
