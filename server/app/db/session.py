"""db.session — SQLAlchemy engine/session factory.

§10 "Server Database": production мәні ``DATABASE_URL`` орта
айнымалысынан келеді (§ "should come from environment configuration,
not hardcoded credentials"), ешбір нақты құпия сөз бұл файлда
ЖОҚ. Орнатылмаса, жергілікті әзірлеу үшін файл-негізді SQLite-ке
құлайды (§ "Do not require a live paid cloud database for core
automated tests").

Postgres-ке дайын болу үшін: ``DATABASE_URL=postgresql+psycopg2://
user:pass@host:5432/dbname`` (``psycopg2-binary`` ``server/requirements.
txt``-те құжатталған, бірақ бұл фазада МІНДЕТТІ түрде орнатылмайды —
§ "do not require a live paid cloud database").
"""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

_DEFAULT_SQLITE_PATH = Path(__file__).resolve().parents[2] / "arduino_physics_lab_server.db"
_ENV_VAR_NAME = "DATABASE_URL"
_PUBLIC_PG_HOST_MARKERS = ("rlwy.net", "railway.app")


class Base(DeclarativeBase):
    pass


def _with_public_railway_ssl(url: str) -> str:
    """Railway public proxy (``*.rlwy.net``) TLS талап етеді; ішкі
    ``*.railway.internal`` хостқа sslmode қосылмайды."""
    if "sslmode=" in url:
        return url
    if any(marker in url for marker in _PUBLIC_PG_HOST_MARKERS):
        separator = "&" if "?" in url else "?"
        return f"{url}{separator}sslmode=require"
    return url


def get_database_url() -> str:
    """§25 "Configuration": ешбір localhost-қа ғана бекітілмеген —
    ``DATABASE_URL`` орнатылса, соны қолданады (Postgres production
    үшін), әйтпесе жергілікті файл-негізді SQLite-ке құлайды.

    Railway ``postgres://`` схемасын береді; SQLAlchemy + psycopg2
    ``postgresql+psycopg2://`` күтеді."""
    url = os.environ.get(_ENV_VAR_NAME) or f"sqlite:///{_DEFAULT_SQLITE_PATH}"
    if url.startswith("postgres://"):
        url = "postgresql+psycopg2://" + url[len("postgres://") :]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url[len("postgresql://") :]
    if url.startswith("postgresql"):
        url = _with_public_railway_ssl(url)
    return url


def create_session_factory(database_url: str | None = None) -> sessionmaker[Session]:
    url = database_url or get_database_url()
    engine_kwargs: dict = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        engine_kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_engine(url, **engine_kwargs)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


_default_session_factory: sessionmaker[Session] | None = None


def get_session_factory() -> sessionmaker[Session]:
    global _default_session_factory
    if _default_session_factory is None:
        _default_session_factory = create_session_factory()
    return _default_session_factory


def get_db():
    """FastAPI dependency — сұрау аяқталғанда сессияны ЖАБАДЫ."""
    session_factory = get_session_factory()
    db = session_factory()
    try:
        yield db
    finally:
        db.close()
