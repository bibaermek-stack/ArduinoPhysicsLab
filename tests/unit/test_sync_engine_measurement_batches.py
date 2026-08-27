"""SyncEngine ↔ measurement_batch wiring тесттері (Phase 4: Raw Arduino
Measurement Cloud Sync) — push/retry/offline/pending-count/remote-apply-
never-re-enqueues, ``test_sync_engine.py``-дегі ``FakeSyncApiClient``
паттернімен БІРДЕЙ, ЕШБІР нақты HTTP/желі."""

from datetime import datetime, timezone

import pytest

from domain.entities.measurement import Measurement
from domain.entities.sync_status import SyncStatus
from domain.interfaces.i_sync_api_client import AuthResult, ISyncApiClient, PullResult, PushItemResult
from domain.services.sync_engine import SyncEngine
from domain.services.sync_payload import ENTITY_TYPE_MEASUREMENT_BATCH, ENTITY_TYPE_SESSION, PUSH_ORDER
from infrastructure.storage.sqlite_classroom_repository import SqliteClassroomRepository
from infrastructure.storage.sqlite_measurement_batch_repository import SqliteMeasurementBatchRepository
from infrastructure.storage.sqlite_session_repository import SqliteSessionRepository
from infrastructure.storage.sqlite_student_repository import SqliteStudentRepository
from infrastructure.storage.sqlite_sync_outbox_repository import SqliteSyncOutboxRepository
from infrastructure.storage.sqlite_teacher_repository import SqliteTeacherRepository

_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


class FakeSyncApiClient(ISyncApiClient):
    def __init__(self, healthy: bool = True) -> None:
        self.healthy = healthy
        self.push_calls: list[tuple[str, list[dict]]] = []
        self.pull_calls: list[str] = []
        self._push_error_for: dict[str, Exception] = {}
        self._pull_items_for: dict[str, tuple[dict, ...]] = {}

    def set_push_error(self, entity_type: str, error: Exception) -> None:
        self._push_error_for[entity_type] = error

    def set_pull_items(self, entity_type: str, items: tuple[dict, ...]) -> None:
        self._pull_items_for[entity_type] = items

    def check_health(self) -> bool:
        return self.healthy

    def set_auth_token(self, token: str | None) -> None:
        pass

    def login_as_teacher(self, sync_id: str, pin_hash: str) -> AuthResult | None:
        return AuthResult(token="fake", expires_at=_NOW, sync_id=sync_id, role="teacher")

    def login_as_student(self, sync_id: str, student_code: str) -> AuthResult | None:
        return AuthResult(token="fake", expires_at=_NOW, sync_id=sync_id, role="student")

    def push(self, entity_type: str, payloads: list[dict]) -> list[PushItemResult]:
        self.push_calls.append((entity_type, payloads))
        if entity_type in self._push_error_for:
            raise self._push_error_for[entity_type]
        return [
            PushItemResult(sync_id=payload["sync_id"], status="upserted", server_revision=1)
            for payload in payloads
        ]

    def pull(self, entity_type: str, updated_since, limit: int) -> PullResult:
        self.pull_calls.append(entity_type)
        return PullResult(items=self._pull_items_for.get(entity_type, ()), server_time=_NOW)


@pytest.fixture()
def engine_setup(tmp_path):
    db_path = str(tmp_path / "device.db")
    outbox = SqliteSyncOutboxRepository(db_path)
    classroom_repo = SqliteClassroomRepository(db_path, sync_outbox_repository=outbox)
    student_repo = SqliteStudentRepository(db_path, sync_outbox_repository=outbox)
    teacher_repo = SqliteTeacherRepository(db_path, sync_outbox_repository=outbox)
    session_repo = SqliteSessionRepository(db_path, sync_outbox_repository=outbox)
    batch_repo = SqliteMeasurementBatchRepository(db_path, sync_outbox_repository=outbox)
    api_client = FakeSyncApiClient()
    cursors: dict[str, datetime] = {}

    engine = SyncEngine(
        classroom_repo, student_repo, teacher_repo, outbox, api_client,
        get_pull_cursor=lambda entity_type: cursors.get(entity_type),
        set_pull_cursor=lambda entity_type, value: cursors.__setitem__(entity_type, value),
        session_repository=session_repo,
        measurement_batch_repository=batch_repo,
    )
    return engine, session_repo, batch_repo, outbox, api_client


def _measurements(count: int) -> tuple[Measurement, ...]:
    return tuple(
        Measurement(timestamp=_NOW, values={"voltage": i * 0.1}, experiment_id="ohms-law") for i in range(count)
    )


def test_measurement_batch_follows_session_in_push_order() -> None:
    """§ "measurement batches depend on ExperimentSession; must never
    precede it". § Phase 7 note: ``measurement_batch`` was the LAST
    entity in ``PUSH_ORDER`` before Phase 7 appended ``teacher_note``
    after it (§ ``teacher_note`` has no ordering dependency on
    ``measurement_batch`` — only on teacher/student/classroom, § test_
    sync_payload.py::test_push_order_dependencies_precede_dependents)
    — the real, still-enforced invariant here is simply "after session",
    not "last"."""
    assert PUSH_ORDER.index(ENTITY_TYPE_SESSION) < PUSH_ORDER.index(ENTITY_TYPE_MEASUREMENT_BATCH)


def test_successful_push_marks_batch_synced_and_clears_outbox(engine_setup) -> None:
    engine, session_repo, batch_repo, outbox, api_client = engine_setup
    session_repo.append_measurements("sess1", "ohms-law", _measurements(5), started_at=_NOW)
    batch_repo.create_pending_batches_for_session("sess1", chunk_size=5, finalize=False)

    result = engine.run_sync(now=_NOW)

    assert result.status is SyncStatus.SYNCED
    batch_id = batch_repo.list_pending_batch_ids_for_session("sess1")[0]
    payload = batch_repo.get_batch_sync_payload(batch_id)
    assert payload["sync_state"] == "synced"
    assert payload["server_revision"] == 1
    assert outbox.count_pending() == 0
    batch_calls = [call for call in api_client.push_calls if call[0] == ENTITY_TYPE_MEASUREMENT_BATCH]
    assert len(batch_calls) == 1
    assert batch_calls[0][1][0]["sample_count"] == 5


def test_offline_server_never_pushes_measurement_batches(engine_setup) -> None:
    """§ "sync must never block Arduino acquisition" / "internet loss is
    normal operation" — local write already happened, push simply skips."""
    engine, session_repo, batch_repo, outbox, api_client = engine_setup
    api_client.healthy = False
    session_repo.append_measurements("sess1", "ohms-law", _measurements(3), started_at=_NOW)
    batch_repo.create_pending_batches_for_session("sess1", chunk_size=3, finalize=False)

    result = engine.run_sync(now=_NOW)

    assert result.status is SyncStatus.OFFLINE
    assert api_client.push_calls == []
    # § measurement rows/batch metadata қалады, тек ЕШБІР желі әрекеті жоқ.
    assert len(session_repo.get_measurements("sess1")) == 3
    assert outbox.count_pending() >= 1


def test_push_failure_keeps_batch_pending_for_retry(engine_setup) -> None:
    engine, session_repo, batch_repo, outbox, api_client = engine_setup
    session_repo.append_measurements("sess1", "ohms-law", _measurements(4), started_at=_NOW)
    batch_repo.create_pending_batches_for_session("sess1", chunk_size=4, finalize=False)
    api_client.set_push_error(ENTITY_TYPE_MEASUREMENT_BATCH, ConnectionError("no route to host"))

    result = engine.run_sync(now=_NOW)

    assert result.status is SyncStatus.SYNC_ERROR
    batch_id = batch_repo.list_pending_batch_ids_for_session("sess1")[0]
    payload = batch_repo.get_batch_sync_payload(batch_id)
    assert payload["sync_state"] == "pending_upload"
    assert outbox.count_pending() == 1


def test_pending_batch_syncs_after_retry_succeeds(engine_setup) -> None:
    """§ "network errors = normal retry" — алдыңғы сәтсіздіктен КЕЙІН,
    келесі ``run_sync()`` шақыруы (§ желі қалпына келгенде) сәтті аяқталады."""
    engine, session_repo, batch_repo, outbox, api_client = engine_setup
    session_repo.append_measurements("sess1", "ohms-law", _measurements(2), started_at=_NOW)
    batch_repo.create_pending_batches_for_session("sess1", chunk_size=2, finalize=False)
    api_client.set_push_error(ENTITY_TYPE_MEASUREMENT_BATCH, ConnectionError("no route to host"))
    engine.run_sync(now=_NOW)

    api_client._push_error_for.clear()
    later = datetime(2026, 1, 1, 1, tzinfo=timezone.utc)
    result = engine.run_sync(now=later)

    assert result.status is SyncStatus.SYNCED
    assert outbox.count_pending() == 0


def test_pull_applies_remote_batch_without_reenqueueing(engine_setup) -> None:
    """§ established "apply_remote_* never re-enqueues" — pull-мен
    алынған batch ЕШБІР жаңа push job жасамайды (§ шексіз цикл алдын алу)."""
    engine, session_repo, batch_repo, outbox, api_client = engine_setup
    # § жаңа сессия — ЕШБІР жергілікті жазба ЖОҚ, толығымен серверден келеді.
    remote_session_payload = {
        "sync_id": "sess1", "experiment_id": "ohms-law", "experiment_title": "", "experiment_display_number": None,
        "started_at": _NOW.isoformat(), "ended_at": None, "status": "in_progress", "measurement_count": 3,
        "created_at": _NOW.isoformat(), "updated_at": _NOW.isoformat(), "server_revision": 1,
    }
    remote_batch_payload = {
        "sync_id": "remote-batch-1", "session_sync_id": "sess1", "sequence_start": 0, "sequence_end": 3,
        "sample_count": 3, "created_at": _NOW.isoformat(),
        "measurements": [
            {"sequence_no": i, "timestamp": _NOW.isoformat(), "values": {"voltage": i * 0.1}, "derived_values": {}, "warnings": []}
            for i in range(3)
        ],
        "server_revision": 1,
    }
    api_client.set_pull_items(ENTITY_TYPE_SESSION, (remote_session_payload,))
    api_client.set_pull_items(ENTITY_TYPE_MEASUREMENT_BATCH, (remote_batch_payload,))
    pending_before = outbox.count_pending()

    result = engine.run_sync(now=_NOW)

    assert result.status is SyncStatus.SYNCED
    assert len(session_repo.get_measurements("sess1")) == 3
    assert outbox.count_pending() == pending_before  # § ЕШБІР жаңа push job
