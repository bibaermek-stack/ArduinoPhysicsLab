"""server.app.main — FastAPI application entry point.

§8 "Remote API Foundation": сервер коды desktop клиенттен МҮЛДЕ БӨЛЕК
(``server/`` ағашы) — desktop процесіне ЕШҚАШАН қосылмайды/іске
қосылмайды (§ "Do not mix FastAPI server startup into the desktop
process").

Жергілікті іске қосу:

    uvicorn server.app.main:app --reload --port 8000

(§31 "Development Documentation"-те толық нұсқаулық, § docs/sync_
architecture.md).
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware

from server.app.api import accounts, auth, health, people, sync
from server.app.web.routes import router as web_router
from server.app.models import account_models as _account_models  # noqa: F401
from server.app.models import sync_models as _sync_models  # noqa: F401
from server.app.api.deps import _DEV_DEFAULT_API_KEY, get_configured_api_key
from server.app.services.auth_service import _DEV_DEFAULT_SECRET, get_configured_jwt_secret

_logger = logging.getLogger(__name__)


def _is_production_runtime() -> bool:
    """Railway / APL_ENV=production — dev-кілтпен іске қосуға болмайды."""
    apl_env = (os.environ.get("APL_ENV") or "").strip().lower()
    railway_env = (os.environ.get("RAILWAY_ENVIRONMENT") or "").strip().lower()
    if apl_env in {"production", "prod"}:
        return True
    if railway_env in {"production", "prod"}:
        return True
    if os.environ.get("RAILWAY_ENVIRONMENT_ID"):
        return True
    return False


def _warn_if_using_dev_default_secrets() -> None:
    """Dev-кілт жергілікті іске қосуда WARNING; production-да RuntimeError."""
    jwt_is_dev = get_configured_jwt_secret() == _DEV_DEFAULT_SECRET
    key_is_dev = get_configured_api_key() == _DEV_DEFAULT_API_KEY
    if _is_production_runtime() and (jwt_is_dev or key_is_dev):
        missing = []
        if jwt_is_dev:
            missing.append("APL_JWT_SECRET")
        if key_is_dev:
            missing.append("APL_SYNC_API_KEY")
        raise RuntimeError(
            "Production-да " + " және ".join(missing) + " міндетті. "
            "Dev-әдепкі кілтпен sync API ашық қалмайды."
        )
    if jwt_is_dev:
        _logger.warning(
            "APL_JWT_SECRET орнатылмаған — сервер dev-әдепкі (production үшін "
            "ЖАРАМСЫЗ) JWT құпиясымен жұмыс істеп тұр. Production-да міндетті "
            "түрде орта айнымалысын орнатыңыз."
        )
    if key_is_dev:
        _logger.warning(
            "APL_SYNC_API_KEY орнатылмаған — сервер dev-әдепкі (production үшін "
            "ЖАРАМСЫЗ) API кілтімен жұмыс істеп тұр. Production-да міндетті "
            "түрде орта айнымалысын орнатыңыз."
        )


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    _warn_if_using_dev_default_secrets()
    yield


app = FastAPI(title="Arduino Physics Lab Sync API", version="1", lifespan=_lifespan)


@app.get("/health")
def root_health() -> dict[str, str]:
    """Railway network healthcheck — дерекқорсыз, әрқашан 200."""
    return {"status": "ok"}

# § Phase 4 (Raw Arduino Measurement Cloud Sync) "Compression" audit:
# ``httpx`` (клиент жағы, § ``HttpSyncApiClient``) ӘДЕПКІ бойынша
# ``Accept-Encoding: gzip``-ты жібереді ЖӘНЕ жауапты ӨЗІ автоматты
# декомпрессиялайды — сервер жағында тек осы БІР жол керек (§ "if
# safe/simple, support it"). Бұл ТЕК ЖАУАПТЫ (§ "second device
# reconstruction" pull-і — потенциалды ІРІ ``measurement-batches``
# payload-ы ЕҢ КӨП пайда табатын бағыт) қысады. ӨТІНІШ (push) денесін
# қысу ӘДЕЙІ ЕНГІЗІЛМЕДІ — ол клиент жағында БӨЛЕК кодтау/декомпрессия
# middleware талап етер еді (§ "compression is secondary... do not
# destabilize the architecture for it"), ал push payload-ы ӘЛДЕҚАЙДА
# кіші (§ ``chunk_size`` әдепкісі 250 үлгі — жіберу жағында қысу
# қазір негізгі кедергі ЕМЕС).
app.add_middleware(GZipMiddleware, minimum_size=1024)

app.include_router(web_router)
app.include_router(health.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")
app.include_router(accounts.router, prefix="/api/v1")
app.include_router(accounts.me_router, prefix="/api/v1")
app.include_router(people.router, prefix="/api/v1")
app.include_router(sync.router, prefix="/api/v1")

_static_dir = Path(__file__).resolve().parent / "web" / "static"
if _static_dir.is_dir():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")
