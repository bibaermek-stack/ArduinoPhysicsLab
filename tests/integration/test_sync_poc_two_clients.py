"""§21 "First Proof of Concept" — екі оқшауланған "клиент" (әрқайсысы
өз in-memory SQLite репозиторийлерімен) БІР ортақ (in-memory, оқшауланған
тест) FastAPI серверімен синхрондалады.

Machine A/Machine B параллелизмі осында ЕКІ бөлек репозиторий жиынымен
(``classroom_a``/``classroom_b`` т.б.) имитацияланады — ЕКЕУІ де БІРДЕЙ
``FastAPI`` app данасын (``fastapi.testclient.TestClient`` арқылы, нақты
socket/бөлек процесс ЖОҚ) ортақ сервер ретінде қолданады, § "use isolated
test databases, never the user's real production database" рухымен
БІРДЕЙ (тек HTTP қабаты да оқшауланған).

``TestClient`` — ``httpx.Client``-тің синхронды-үйлесімді ішкі класы
(§ ``httpx.ASGITransport`` тек async — ``handle_async_request`` ғана
іске асырады, ал ``HttpSyncApiClient``/``SyncEngine`` синхронды жұмыс
істейді, сондықтан ``TestClient`` дәл осы алшақтықты ЖАБАДЫ)."""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from domain.entities.classroom import Classroom
from domain.entities.student import Student
from domain.entities.teacher import Teacher
from domain.entities.user_role import UserRole
from domain.services.sync_engine import SyncEngine
from domain.services.teacher_pin import hash_pin
from infrastructure.storage.sqlite_classroom_repository import SqliteClassroomRepository
from infrastructure.storage.sqlite_student_repository import SqliteStudentRepository
from infrastructure.storage.sqlite_sync_outbox_repository import SqliteSyncOutboxRepository
from infrastructure.storage.sqlite_teacher_repository import SqliteTeacherRepository
from infrastructure.sync.http_sync_api_client import HttpSyncApiClient
from server.app.db.session import Base, get_db
from server.app.main import app as fastapi_app

_TEST_API_KEY = "dev-local-only-key"
_NOW = datetime.now(timezone.utc)


@pytest.fixture()
def shared_server() -> TestClient:
    """§10 "Do not require a live paid cloud database" — оқшауланған
    in-memory Postgres-ready SQLAlchemy engine, ``StaticPool`` арқылы
    бір коннекция бүкіл тест бойы бөлісіледі (server/tests/conftest.py-
    мен БІРДЕЙ паттерн)."""
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def _override_get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    fastapi_app.dependency_overrides[get_db] = _override_get_db
    with TestClient(fastapi_app) as test_client:
        yield test_client
    fastapi_app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)


_SHARED_PIN_HASH = hash_pin("482915")


def _build_client(server: TestClient, label: str):
    """§ "isolated test databases" — әр клиент ӨЗІНІҢ in-memory
    репозиторийлер жиынымен (сепаратты Python процесс/дерекқор файлы
    ЕМЕС, БІРАҚ логикалық түрде толық оқшауланған).

    § Phase 3: §7 "Multiple Devices" сценарийін имитациялайды — ЕКІ
    клиент те (Machine A/B) ДӘЛ СОЛ мұғалімнің ("t1", БІРДЕЙ pin_hash)
    ЕКІ бөлек құрылғысы (§ "the same legitimate account being used from
    more than one device"). Нақты өмірде бұл мұғалімнің ЕКІ құрылғысында
    да ӨЗ PIN-ін ЕНГІЗУІ арқылы жетеді — бұл жерде сол алдын ала
    белгілі жағдайды тікелей құрастырамыз (§ ``teacher_repo.create()``
    осы клиенттің ӨЗ жергілікті дерекқорына, sync-тен ТӘУЕЛСІЗ)."""
    outbox = SqliteSyncOutboxRepository()
    classroom_repo = SqliteClassroomRepository(sync_outbox_repository=outbox)
    student_repo = SqliteStudentRepository(sync_outbox_repository=outbox)
    teacher_repo = SqliteTeacherRepository(sync_outbox_repository=outbox)
    if teacher_repo.get("t1") is None:
        # § ``apply_remote_upsert()`` — ЕШБІР outbox жазуы ЖОҚ (§
        # established "remote apply never re-enqueues" паттерні). Бұл
        # жазба тек аутентификация credential-ін шешу үшін (§
        # ``SyncEngine._resolve_local_credential()``) — АЛДЫН АЛА
        # провизияланған сәйкестік ретінде, ЖАҢА жергілікті өзгеріс
        # ретінде ЕМЕС (§ "must not be treated as a pending local edit
        # waiting to push and overwrite the other device's assignment").
        teacher_repo.apply_remote_upsert(
            Teacher(
                id="t1", full_name="Teacher A", pin_hash=_SHARED_PIN_HASH, created_at=_NOW, updated_at=_NOW,
                sync_id="t1",
            )
        )
    api_client = HttpSyncApiClient(
        base_url="http://testserver", api_key=_TEST_API_KEY, client=server
    )
    cursors: dict[str, datetime] = {}
    token_cache: dict[str, tuple] = {}
    engine = SyncEngine(
        classroom_repo, student_repo, teacher_repo, outbox, api_client,
        get_pull_cursor=lambda entity_type: cursors.get(entity_type),
        set_pull_cursor=lambda entity_type, value: cursors.__setitem__(entity_type, value),
        get_active_role_and_sync_id=lambda: ("teacher", "t1"),
        get_cached_token=lambda: token_cache.get("token"),
        set_cached_token=lambda token, expires_at, role, sync_id: token_cache.__setitem__(
            "token", (token, expires_at, role, sync_id)
        ),
    )
    return engine, classroom_repo, student_repo, teacher_repo


def test_client_a_creates_data_client_b_pulls_same_records(shared_server: TestClient) -> None:
    engine_a, classroom_a, student_a, teacher_a = _build_client(shared_server, "A")
    engine_b, classroom_b, student_b, teacher_b = _build_client(shared_server, "B")

    classroom_a.create(
        Classroom(id="c1", name="8А-POC", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    student_a.create(
        Student(
            id="s1", classroom_id="c1", first_name="Aidos", last_name="Test",
            created_at=_NOW, updated_at=_NOW, student_code="999999",
        ),
        UserRole.TEACHER,
    )
    # § "t1" ({_build_client()} арқылы алдын ала провизияланған, §
    # Phase 3 "Multiple Devices" bootstrap ескертуі) — тек тағайындау
    # жиынын орнату қажет.
    teacher_a.set_assigned_classroom_ids("t1", ("c1",))

    result_a = engine_a.run_sync()
    assert result_a.status.value == "synced"
    # § Phase 3: "teacher" ЖЕКЕ push етілмейді — сервер оны ЛОГИН
    # кезіндегі TOFU bootstrap-та ӘЛДЕҚАШАН тіркеді (§ ``auth_service.
    # py::authenticate_teacher()``). Тек ЖАҢА жергілікті әрекеттер
    # push етіледі: teacher_classroom + classroom + student.
    assert result_a.pushed == 3

    result_b = engine_b.run_sync()
    assert result_b.status.value == "synced"
    # teacher (§ A-ның логин TOFU bootstrap-ынан) + classroom + student
    # + teacher_classroom.
    assert result_b.pulled == 4

    pulled_classroom = classroom_b.get("c1")
    pulled_student = student_b.get("s1")
    pulled_teacher = teacher_b.get("t1")
    assert pulled_classroom is not None and pulled_classroom.sync_id == "c1"
    assert pulled_student is not None and pulled_student.sync_id == "s1"
    assert pulled_teacher is not None and pulled_teacher.sync_id == "t1"
    assert pulled_teacher.pin_hash == hash_pin("482915")
    assert teacher_b.list_assigned_classroom_ids("t1") == ("c1",)


def test_edit_on_b_propagates_back_to_a_after_both_sync(shared_server: TestClient) -> None:
    engine_a, classroom_a, _, _ = _build_client(shared_server, "A")
    engine_b, classroom_b, _, _ = _build_client(shared_server, "B")

    classroom_a.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    engine_a.run_sync()
    engine_b.run_sync()

    classroom_b.update(
        Classroom(id="c1", name="8А (өзгертілген B-де)", created_at=_NOW, updated_at=_NOW, sync_id="c1"),
        UserRole.TEACHER,
    )
    result_b_push = engine_b.run_sync()
    assert result_b_push.pushed == 1

    result_a_pull = engine_a.run_sync()
    assert result_a_pull.pulled == 1
    assert classroom_a.get("c1").name == "8А (өзгертілген B-де)"


def test_second_sync_with_no_local_changes_pushes_and_pulls_nothing_new(shared_server: TestClient) -> None:
    """§18 "Incremental pull": cursor сақталғаннан кейін бос синхрондау
    ешбір қайталама push/pull тудырмайды."""
    engine_a, classroom_a, _, _ = _build_client(shared_server, "A")
    classroom_a.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    engine_a.run_sync()

    result = engine_a.run_sync()

    assert result.pushed == 0
    assert result.pulled == 0
    assert result.status.value == "synced"


def test_server_returning_error_status_keeps_app_functional(shared_server: TestClient, monkeypatch) -> None:
    """§29 acceptance requirement: "the existing local application must
    remain functional even if the server is not running" — бұл тест
    HTTP денгейінде сервер қолжетімсіз болған жағдайды имитациялайды
    (``check_health`` False қайтарады), жергілікті жазу/оқу ӘСЕР
    етпейді."""
    engine_a, classroom_a, _, _ = _build_client(shared_server, "A")
    monkeypatch.setattr(engine_a._api_client, "check_health", lambda: False)

    classroom_a.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    result = engine_a.run_sync()

    assert result.status.value == "offline"
    # Жергілікті дерек толық қолжетімді қалады.
    assert classroom_a.get("c1") is not None
    assert classroom_a.get("c1").name == "8А"
