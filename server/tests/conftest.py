"""server/tests/conftest.py — оқшауланған in-memory SQLite тест дерекқоры
(§10 "Do not require a live paid cloud database for core automated
tests"). Әр тест ЖАҢА, БОС дерекқормен басталады — ``StaticPool``
арқылы бір ғана коннекция бүкіл тест бойы бөлісіледі (SQLite
``:memory:`` дефолты коннекция сайын БӨЛЕК дерекқор жасайды, ол
FastAPI ``TestClient``/dependency override арасында сәйкессіздік
тудырар еді).
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from server.app.db.session import Base, get_db
from server.app.main import app

_TEST_API_KEY = "dev-local-only-key"


@pytest.fixture()
def db_session_factory():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    yield factory
    Base.metadata.drop_all(engine)


@pytest.fixture()
def client(db_session_factory) -> TestClient:
    def _override_get_db():
        db = db_session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def auth_headers() -> dict[str, str]:
    return {"X-API-Key": _TEST_API_KEY}


def _bootstrap_login(client: TestClient, path: str, body: dict) -> dict[str, str]:
    """§ Phase 3: TOFU bootstrap login (``auth_service.py`` докстрингі)
    — тест дерекқоры бос болғандықтан, БІРІНШІ логин автоматты түрде
    сол sync_id/credential-ды тіркейді. ``X-API-Key`` ЖӘНЕ ``Authorization:
    Bearer`` екеуін де қайтарады (§ "defense in depth", екеуі де ӘРБІР
    /sync/* маршрутында талап етіледі)."""
    response = client.post(path, json=body, headers={"X-API-Key": _TEST_API_KEY})
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"X-API-Key": _TEST_API_KEY, "Authorization": f"Bearer {token}"}


@pytest.fixture()
def teacher_auth_headers(client: TestClient) -> dict[str, str]:
    """§ Барлық ескі (Phase 1/2) тесттер "t1" sync_id-мен мұғалім
    ретінде әрекет етеді (§ established конвенция — payload-тар
    ``_TEACHER_PAYLOAD``/``teacher_sync_id`` барлық жерде "t1")."""
    return _bootstrap_login(
        client, "/api/v1/auth/teacher-login",
        {"sync_id": "t1", "pin_hash": "test-pin-hash-t1", "full_name": "Test Teacher"},
    )


@pytest.fixture()
def student_auth_headers(client: TestClient) -> dict[str, str]:
    """§ Барлық ескі (Phase 1/2) тесттер "s1" sync_id-мен оқушы
    ретінде әрекет етеді. ``student_code`` осы файлдардағы ортақ
    ``_STUDENT_PAYLOAD["student_code"]``-мен БІРДЕЙ ("111111") — кейбір
    тесттерде мұғалім ЖӘНЕ осы fixture ЕКЕУІ де "s1" жазбасын
    құрастыруы мүмкін (тәуелділік ретіне қарай), сол себепті екеуі
    ЕШҚАШАН қайшы келмеуі керек."""
    return _bootstrap_login(
        client, "/api/v1/auth/student-login",
        {"sync_id": "s1", "student_code": "111111", "classroom_sync_id": "c1"},
    )
