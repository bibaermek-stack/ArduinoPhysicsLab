"""domain/services/sync_engine.py тесттері — таза Python orchestration,
нақты sqlite репозиторийлер + fake ``ISyncApiClient`` (ЕШБІР нақты
HTTP/желі, § "SyncEngine ЕШҚАШАН HTTP бөлшектерін білмейді")."""

from datetime import datetime, timezone

import pytest

from domain.entities.classroom import Classroom
from domain.entities.sync_state import SyncState
from domain.entities.student import Student
from domain.entities.sync_status import SyncStatus
from domain.entities.teacher import Teacher
from domain.entities.user_role import UserRole
from domain.interfaces.i_sync_api_client import AuthResult, ISyncApiClient, PullResult, PushItemResult
from domain.services.sync_engine import SyncEngine
from domain.services.sync_payload import ENTITY_TYPE_CLASSROOM, ENTITY_TYPE_STUDENT, ENTITY_TYPE_TEACHER
from domain.services.teacher_pin import hash_pin
from infrastructure.storage.sqlite_classroom_repository import SqliteClassroomRepository
from infrastructure.storage.sqlite_student_repository import SqliteStudentRepository
from infrastructure.storage.sqlite_sync_outbox_repository import SqliteSyncOutboxRepository
from infrastructure.storage.sqlite_teacher_repository import SqliteTeacherRepository

_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


class FakeSyncApiClient(ISyncApiClient):
    """Тестке арналған, конфигурацияланатын ``ISyncApiClient``. Шақыру
    ретін/аргументтерін жазып отырады — PUSH_ORDER-дің дұрыс сақталуын
    тексеру үшін."""

    def __init__(self, healthy: bool = True) -> None:
        self.healthy = healthy
        self.push_calls: list[tuple[str, list[dict]]] = []
        self.pull_calls: list[tuple[str, datetime | None]] = []
        self._push_result_for: dict[str, list[PushItemResult]] = {}
        self._push_error_for: dict[str, Exception] = {}
        self._pull_items_for: dict[str, tuple[dict, ...]] = {}

    def set_push_result(self, entity_type: str, results: list[PushItemResult]) -> None:
        self._push_result_for[entity_type] = results

    def set_push_error(self, entity_type: str, error: Exception) -> None:
        self._push_error_for[entity_type] = error

    def set_pull_items(self, entity_type: str, items: tuple[dict, ...]) -> None:
        self._pull_items_for[entity_type] = items

    def check_health(self) -> bool:
        return self.healthy

    # § Phase 3: бұл фейк клиент авторизация orchestration-ын
    # ЕШҚАШАН қолданбайтын ескі тесттер үшін — тек интерфейсті
    # қанағаттандыратын минимал stub-тар (§ ``SyncEngine``-нің ӨЗІ
    # ``get_active_role_and_sync_id=None`` кезінде бұларды ЕШҚАШАН
    # шақырмайды).
    def set_auth_token(self, token: str | None) -> None:
        self.auth_token = token

    def login_as_teacher(self, sync_id: str, pin_hash: str) -> AuthResult | None:
        return AuthResult(token="fake-token", expires_at=_NOW, sync_id=sync_id, role="teacher")

    def login_as_student(self, sync_id: str, student_code: str) -> AuthResult | None:
        return AuthResult(token="fake-token", expires_at=_NOW, sync_id=sync_id, role="student")

    def push(self, entity_type: str, payloads: list[dict]) -> list[PushItemResult]:
        self.push_calls.append((entity_type, payloads))
        if entity_type in self._push_error_for:
            raise self._push_error_for[entity_type]
        if entity_type in self._push_result_for:
            return self._push_result_for[entity_type]
        return [
            PushItemResult(sync_id=payload["sync_id"], status="upserted", server_revision=1)
            for payload in payloads
        ]

    def pull(self, entity_type: str, updated_since: datetime | None, limit: int) -> PullResult:
        self.pull_calls.append((entity_type, updated_since))
        items = self._pull_items_for.get(entity_type, ())
        return PullResult(items=items, server_time=_NOW)


@pytest.fixture
def engine_setup():
    outbox = SqliteSyncOutboxRepository()
    classroom_repo = SqliteClassroomRepository(sync_outbox_repository=outbox)
    student_repo = SqliteStudentRepository(sync_outbox_repository=outbox)
    teacher_repo = SqliteTeacherRepository(sync_outbox_repository=outbox)
    api_client = FakeSyncApiClient()
    cursors: dict[str, datetime] = {}

    engine = SyncEngine(
        classroom_repo, student_repo, teacher_repo, outbox, api_client,
        get_pull_cursor=lambda entity_type: cursors.get(entity_type),
        set_pull_cursor=lambda entity_type, value: cursors.__setitem__(entity_type, value),
    )
    return engine, classroom_repo, student_repo, teacher_repo, outbox, api_client, cursors


def test_offline_server_skips_push_and_pull_entirely(engine_setup) -> None:
    engine, classroom_repo, _, _, outbox, api_client, _ = engine_setup
    api_client.healthy = False
    classroom_repo.create(Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER)

    result = engine.run_sync(now=_NOW)

    assert result.status is SyncStatus.OFFLINE
    assert result.pushed == 0
    assert result.pulled == 0
    assert api_client.push_calls == []
    assert api_client.pull_calls == []
    # § "local write must never wait on server" — жазба ӘЛІ де outbox-та.
    assert outbox.count_pending() == 1


def test_successful_push_marks_local_record_synced_and_clears_outbox(engine_setup) -> None:
    engine, classroom_repo, _, _, outbox, _, _ = engine_setup
    classroom_repo.create(Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER)

    result = engine.run_sync(now=_NOW)

    assert result.status is SyncStatus.SYNCED
    assert result.pushed == 1
    assert outbox.count_pending() == 0
    updated = classroom_repo.get("c1")
    assert updated.sync_state is SyncState.SYNCED
    assert updated.server_revision == 1


def test_push_order_respects_teacher_before_student_dependency(engine_setup) -> None:
    engine, classroom_repo, student_repo, teacher_repo, _, api_client, _ = engine_setup
    classroom_repo.create(Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER)
    student_repo.create(
        Student(id="s1", classroom_id="c1", first_name="A", last_name="B", created_at=_NOW, updated_at=_NOW),
        UserRole.TEACHER,
    )
    teacher_repo.create(
        Teacher(id="t1", full_name="X", pin_hash=hash_pin("1234"), created_at=_NOW, updated_at=_NOW),
        assigned_classroom_ids=("c1",),
    )

    engine.run_sync(now=_NOW)

    pushed_entity_types = [entity_type for entity_type, _ in api_client.push_calls]
    assert pushed_entity_types.index(ENTITY_TYPE_TEACHER) < pushed_entity_types.index(ENTITY_TYPE_STUDENT)
    assert pushed_entity_types.index(ENTITY_TYPE_CLASSROOM) < pushed_entity_types.index(ENTITY_TYPE_STUDENT)


def test_push_item_error_schedules_retry_and_leaves_outbox_entry(engine_setup) -> None:
    engine, classroom_repo, _, _, outbox, api_client, _ = engine_setup
    classroom_repo.create(Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER)
    api_client.set_push_result(
        ENTITY_TYPE_CLASSROOM, [PushItemResult(sync_id="c1", status="error", error="validation failed")]
    )

    result = engine.run_sync(now=_NOW)

    assert result.status is SyncStatus.SYNC_ERROR
    assert result.pushed == 0
    assert any("validation failed" in error for error in result.errors)
    entries = outbox.list_all()
    assert len(entries) == 1
    assert entries[0].attempt_count == 1
    assert entries[0].next_retry_at is not None
    # Жергілікті жазба ӘЛІ де PENDING_UPLOAD — ЕШБІР "SYNCED" деп жалған белгіленбеді.
    assert classroom_repo.get("c1").sync_state is SyncState.PENDING_UPLOAD


def test_push_transport_exception_marks_all_entries_failed(engine_setup) -> None:
    engine, classroom_repo, _, _, outbox, api_client, _ = engine_setup
    classroom_repo.create(Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER)
    api_client.set_push_error(ENTITY_TYPE_CLASSROOM, ConnectionError("server unreachable"))

    result = engine.run_sync(now=_NOW)

    assert result.status is SyncStatus.SYNC_ERROR
    entries = outbox.list_all()
    assert entries[0].attempt_count == 1
    assert "server unreachable" in entries[0].last_error


def test_pull_applies_remote_classroom_without_enqueueing_outbox(engine_setup) -> None:
    engine, classroom_repo, _, _, outbox, api_client, cursors = engine_setup
    api_client.set_pull_items(
        ENTITY_TYPE_CLASSROOM,
        (
            {
                "sync_id": "remote-c1",
                "name": "Remote 8Б",
                "academic_year": "",
                "description": "",
                "is_archived": False,
                "created_at": _NOW.isoformat(),
                "updated_at": _NOW.isoformat(),
                "server_revision": 5,
            },
        ),
    )

    result = engine.run_sync(now=_NOW)

    assert result.status is SyncStatus.SYNCED
    assert result.pulled == 1
    assert outbox.count_pending() == 0
    pulled_classroom = classroom_repo.get("remote-c1")
    assert pulled_classroom is not None
    assert pulled_classroom.name == "Remote 8Б"
    assert pulled_classroom.sync_state is SyncState.SYNCED
    assert cursors[ENTITY_TYPE_CLASSROOM] == _NOW


def test_pull_uses_persisted_cursor_for_incremental_fetch(engine_setup) -> None:
    engine, _, _, _, _, api_client, cursors = engine_setup
    cursors[ENTITY_TYPE_CLASSROOM] = datetime(2025, 6, 1, tzinfo=timezone.utc)

    engine.run_sync(now=_NOW)

    classroom_pull_call = next(call for call in api_client.pull_calls if call[0] == ENTITY_TYPE_CLASSROOM)
    assert classroom_pull_call[1] == datetime(2025, 6, 1, tzinfo=timezone.utc)


def test_full_round_trip_reports_synced_with_zero_errors_when_nothing_pending(engine_setup) -> None:
    engine, *_ = engine_setup

    result = engine.run_sync(now=_NOW)

    assert result.status is SyncStatus.SYNCED
    assert result.pushed == 0
    assert result.pulled == 0
    assert result.errors == ()
