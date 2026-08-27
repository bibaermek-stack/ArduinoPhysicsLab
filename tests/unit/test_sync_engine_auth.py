"""domain/services/sync_engine.py — Phase 3 (Production Authentication
+ Authorization) authentication orchestration tests (acceptance items
19-24): authenticated push/pull works, 401 does not delete the local
outbox, offline write still succeeds, reconnect + authentication +
sync succeeds. Pure Python — fake ``ISyncApiClient``, no real HTTP
(§ ``tests/unit/test_sync_engine.py``-мен БІРДЕЙ принцип)."""

from datetime import datetime, timedelta, timezone

import pytest

from domain.entities.classroom import Classroom
from domain.entities.sync_status import SyncStatus
from domain.entities.teacher import Teacher
from domain.entities.user_role import UserRole
from domain.interfaces.i_sync_api_client import (
    AuthResult,
    ISyncApiClient,
    PullResult,
    PushItemResult,
    SyncAuthenticationError,
)
from domain.services.sync_engine import SyncEngine
from domain.services.teacher_pin import hash_pin
from infrastructure.storage.sqlite_classroom_repository import SqliteClassroomRepository
from infrastructure.storage.sqlite_student_repository import SqliteStudentRepository
from infrastructure.storage.sqlite_sync_outbox_repository import SqliteSyncOutboxRepository
from infrastructure.storage.sqlite_teacher_repository import SqliteTeacherRepository

_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
_PIN_HASH = hash_pin("482915")


class FakeAuthSyncApiClient(ISyncApiClient):
    """§19-24: логин/токен/401-ды толық бақылайтын fake клиент."""

    def __init__(self, healthy: bool = True) -> None:
        self.healthy = healthy
        self.auth_token: str | None = None
        self.login_calls: list[tuple[str, str]] = []
        self.push_calls: list[str] = []
        self.pull_calls: list[str] = []
        self.login_result: AuthResult | None = AuthResult(
            token="tok-1", expires_at=_NOW + timedelta(hours=1), sync_id="t1", role="teacher"
        )
        self.reject_push_until_reauth = False
        self._push_call_count = 0

    def check_health(self) -> bool:
        return self.healthy

    def set_auth_token(self, token: str | None) -> None:
        self.auth_token = token

    def login_as_teacher(self, sync_id: str, pin_hash: str) -> AuthResult | None:
        self.login_calls.append(("teacher", sync_id))
        return self.login_result

    def login_as_student(self, sync_id: str, student_code: str) -> AuthResult | None:
        self.login_calls.append(("student", sync_id))
        return self.login_result

    def push(self, entity_type: str, payloads: list[dict]) -> list[PushItemResult]:
        self.push_calls.append(entity_type)
        self._push_call_count += 1
        if self.reject_push_until_reauth and self.auth_token != "tok-refreshed":
            raise SyncAuthenticationError("token expired")
        return [
            PushItemResult(sync_id=payload["sync_id"], status="upserted", server_revision=1)
            for payload in payloads
        ]

    def pull(self, entity_type: str, updated_since: datetime | None, limit: int) -> PullResult:
        self.pull_calls.append(entity_type)
        return PullResult(items=(), server_time=_NOW)


@pytest.fixture
def engine_setup():
    outbox = SqliteSyncOutboxRepository()
    classroom_repo = SqliteClassroomRepository(sync_outbox_repository=outbox)
    student_repo = SqliteStudentRepository(sync_outbox_repository=outbox)
    teacher_repo = SqliteTeacherRepository(sync_outbox_repository=outbox)
    # § ``apply_remote_upsert()`` — ЕШБІР outbox жазуы ЖОҚ (§ established
    # "remote apply never re-enqueues" паттерні). Бұл жазба тек
    # аутентификация credential-ін шешу үшін (§ ``SyncEngine._resolve_
    # local_credential()``), ЖАҢА жергілікті өзгеріс ретінде ЕМЕС.
    teacher_repo.apply_remote_upsert(
        Teacher(id="t1", full_name="T", pin_hash=_PIN_HASH, created_at=_NOW, updated_at=_NOW, sync_id="t1")
    )
    api_client = FakeAuthSyncApiClient()
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
    return engine, classroom_repo, outbox, api_client, token_cache


# ---- 19/20. Authenticated push/pull works -----------------------------------


def test_authenticated_push_works(engine_setup) -> None:
    engine, classroom_repo, outbox, api_client, _ = engine_setup
    classroom_repo.create(Classroom(id="c1", name="8A", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER)

    result = engine.run_sync(now=_NOW)

    assert result.status is SyncStatus.SYNCED
    assert api_client.login_calls == [("teacher", "t1")]
    assert api_client.auth_token == "tok-1"
    assert "classroom" in api_client.push_calls


def test_authenticated_pull_works(engine_setup) -> None:
    engine, _, _, api_client, _ = engine_setup

    result = engine.run_sync(now=_NOW)

    assert result.status is SyncStatus.SYNCED
    assert api_client.auth_token == "tok-1"
    assert len(api_client.pull_calls) > 0


def test_cached_valid_token_skips_re_login(engine_setup) -> None:
    engine, classroom_repo, outbox, api_client, token_cache = engine_setup
    token_cache["token"] = ("cached-tok", _NOW + timedelta(hours=1), "teacher", "t1")

    engine.run_sync(now=_NOW)

    assert api_client.login_calls == []  # § жарамды кэш болғандықтан ЕШБІР жаңа логин
    assert api_client.auth_token == "cached-tok"


def test_expired_cached_token_triggers_fresh_login(engine_setup) -> None:
    engine, _, _, api_client, token_cache = engine_setup
    token_cache["token"] = ("stale-tok", _NOW - timedelta(minutes=1), "teacher", "t1")

    engine.run_sync(now=_NOW)

    assert api_client.login_calls == [("teacher", "t1")]
    assert api_client.auth_token == "tok-1"


def test_cached_token_for_different_identity_is_not_reused(engine_setup) -> None:
    """§ logout/switch-user: ЕСКІ (басқа sync_id-ге шығарылған) токен
    ЖАҢА пайдаланушы атынан ЕШҚАШАН қате қолданылмайды."""
    engine, _, _, api_client, token_cache = engine_setup
    token_cache["token"] = ("someone-elses-tok", _NOW + timedelta(hours=1), "teacher", "t2")

    engine.run_sync(now=_NOW)

    assert api_client.login_calls == [("teacher", "t1")]


# ---- 22. 401 does not delete the local outbox -------------------------------


def test_401_does_not_delete_local_outbox_when_reauth_also_fails(engine_setup) -> None:
    engine, classroom_repo, outbox, api_client, _ = engine_setup
    classroom_repo.create(Classroom(id="c1", name="8A", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER)
    api_client.reject_push_until_reauth = True
    api_client.login_result = None  # § re-login де сәтсіз (қате credential)

    result = engine.run_sync(now=_NOW)

    assert result.status is SyncStatus.AUTH_REQUIRED
    assert outbox.count_pending() == 1  # § жазба ЕШҚАШАН жоғалмайды/жойылмайды
    assert classroom_repo.get("c1") is not None  # § жергілікті дерек те сақталады


def test_reconnect_authentication_and_sync_succeeds(engine_setup) -> None:
    """§24 "reconnect + authentication + sync succeeds" — 401 бір рет
    кездеседі, БІРАҚ бірден қайта логин арқылы ТОЛЫҚ қалпына келеді."""
    engine, classroom_repo, outbox, api_client, _ = engine_setup
    classroom_repo.create(Classroom(id="c1", name="8A", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER)
    api_client.reject_push_until_reauth = True
    # § "safe token refresh" — қайта логиннен кейін ЖАҢА (жарамды) токен.
    api_client.login_result = AuthResult(
        token="tok-refreshed", expires_at=_NOW + timedelta(hours=1), sync_id="t1", role="teacher"
    )

    result = engine.run_sync(now=_NOW)

    assert result.status is SyncStatus.SYNCED
    assert result.pushed == 1
    assert outbox.count_pending() == 0
    assert len(api_client.login_calls) >= 1


# ---- 23. Offline write still succeeds (auth never even attempted) ----------


def test_offline_write_still_succeeds_without_any_login_attempt(engine_setup) -> None:
    engine, classroom_repo, outbox, api_client, _ = engine_setup
    api_client.healthy = False

    classroom_repo.create(Classroom(id="c1", name="8A", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER)
    result = engine.run_sync(now=_NOW)

    assert result.status is SyncStatus.OFFLINE
    assert api_client.login_calls == []  # § сервер қолжетімсіз кезде логин де СҰРАЛМАЙДЫ
    assert classroom_repo.get("c1") is not None
    assert outbox.count_pending() == 1


# ---- Auth-orchestration-disabled backward compatibility --------------------


def test_auth_orchestration_disabled_when_callables_not_supplied() -> None:
    """§ established "optional dependency with safe default" паттерні —
    ескі шақырушылар (§ ``get_active_role_and_sync_id`` берілмесе)
    ЕШБІР жаңа мінез-құлыққа тап болмайды."""
    outbox = SqliteSyncOutboxRepository()
    classroom_repo = SqliteClassroomRepository(sync_outbox_repository=outbox)
    student_repo = SqliteStudentRepository(sync_outbox_repository=outbox)
    teacher_repo = SqliteTeacherRepository(sync_outbox_repository=outbox)
    api_client = FakeAuthSyncApiClient()
    engine = SyncEngine(
        classroom_repo, student_repo, teacher_repo, outbox, api_client,
        get_pull_cursor=lambda entity_type: None,
        set_pull_cursor=lambda entity_type, value: None,
    )

    result = engine.run_sync(now=_NOW)

    assert result.status is SyncStatus.SYNCED
    assert api_client.login_calls == []
