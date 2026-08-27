"""SqliteMeasurementBatchRepository + ISessionRepository.append_measurements()
тесттері (Phase 4: Raw Arduino Measurement Cloud Sync).

Барлық "device" бір физикалық файлды бөліседі (§ shared explicit
``db_path`` — ЕКІ бөлек ``:memory:`` байланысы ЕШҚАШАН БІРДЕЙ дерекқор
ЕМЕС, § ``SqliteSyncOutboxRepository``-мен БІРДЕЙ established конвенция).
"""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from domain.entities.measurement import Measurement
from infrastructure.storage.sqlite_measurement_batch_repository import SqliteMeasurementBatchRepository
from infrastructure.storage.sqlite_session_repository import SqliteSessionRepository
from infrastructure.storage.sqlite_sync_outbox_repository import SqliteSyncOutboxRepository

_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _measurements(count: int, start_voltage: float = 0.0) -> tuple[Measurement, ...]:
    return tuple(
        Measurement(
            timestamp=_NOW,
            values={"voltage": round(start_voltage + i * 0.1, 4)},
            experiment_id="ohms-law",
        )
        for i in range(count)
    )


@pytest.fixture()
def shared_db_path(tmp_path: Path) -> str:
    return str(tmp_path / "shared.db")


@pytest.fixture()
def repos(shared_db_path):
    outbox = SqliteSyncOutboxRepository(shared_db_path)
    session_repo = SqliteSessionRepository(shared_db_path, sync_outbox_repository=outbox)
    batch_repo = SqliteMeasurementBatchRepository(shared_db_path, sync_outbox_repository=outbox)
    return session_repo, batch_repo, outbox


# ---- append_measurements() (ISessionRepository) ----------------------------


def test_append_measurements_creates_in_progress_session_row(repos) -> None:
    session_repo, _, _ = repos
    count = session_repo.append_measurements("sess1", "ohms-law", _measurements(5), started_at=_NOW)

    assert count == 5
    summary = session_repo.get_session("sess1")
    assert summary is not None
    assert summary.status == "in_progress"
    assert summary.measurement_count == 5


def test_append_measurements_is_incremental_not_destructive(repos) -> None:
    session_repo, _, _ = repos
    session_repo.append_measurements("sess1", "ohms-law", _measurements(3), started_at=_NOW)
    session_repo.append_measurements("sess1", "ohms-law", _measurements(2, start_voltage=10.0), started_at=_NOW)

    measurements = session_repo.get_measurements("sess1")
    assert len(measurements) == 5
    assert [m.values["voltage"] for m in measurements] == [0.0, 0.1, 0.2, 10.0, 10.1]


def test_append_measurements_empty_tuple_is_noop(repos) -> None:
    session_repo, _, _ = repos
    count = session_repo.append_measurements("sess1", "ohms-law", (), started_at=_NOW)

    assert count == 0
    assert session_repo.get_session("sess1") is None


def test_append_measurements_then_save_session_supersedes_safely(repos) -> None:
    """§ "safely superseded by a later save_session() call" — толық
    аяқталған сессия сақталғанда, деректер жоғалмайды/қайталанбайды."""
    from domain.entities.experiment_session import ExperimentSession

    session_repo, _, _ = repos
    session_repo.append_measurements("sess1", "ohms-law", _measurements(3), started_at=_NOW)

    full_session = ExperimentSession(
        id="sess1", experiment_id="ohms-law", started_at=_NOW, ended_at=_NOW,
        measurements=list(_measurements(3)),
    )
    session_repo.save_session(full_session)

    measurements = session_repo.get_measurements("sess1")
    assert len(measurements) == 3
    summary = session_repo.get_session("sess1")
    assert summary.status == "finalized" or summary.ended_at is not None


# ---- create_pending_batches_for_session() -----------------------------------


def test_create_pending_batches_chunks_full_ranges_only_by_default(repos) -> None:
    session_repo, batch_repo, _ = repos
    session_repo.append_measurements("sess1", "ohms-law", _measurements(25), started_at=_NOW)

    created = batch_repo.create_pending_batches_for_session("sess1", chunk_size=10, finalize=False)

    assert created == 2  # § 25 үлгі / 10 = 2 толық batch, 5 "құйрық" әлі жоқ
    assert len(batch_repo.list_pending_batch_ids_for_session("sess1")) == 2


def test_create_pending_batches_finalize_true_captures_tail(repos) -> None:
    session_repo, batch_repo, _ = repos
    session_repo.append_measurements("sess1", "ohms-law", _measurements(25), started_at=_NOW)

    created = batch_repo.create_pending_batches_for_session("sess1", chunk_size=10, finalize=True)

    assert created == 3  # § 2 толық + 1 "құйрық" (5 үлгі)
    payloads = [
        batch_repo.get_batch_sync_payload(bid)
        for bid in batch_repo.list_pending_batch_ids_for_session("sess1")
    ]
    assert [p["sample_count"] for p in payloads] == [10, 10, 5]


def test_create_pending_batches_is_idempotent_across_repeated_calls(repos) -> None:
    session_repo, batch_repo, _ = repos
    session_repo.append_measurements("sess1", "ohms-law", _measurements(30), started_at=_NOW)

    first = batch_repo.create_pending_batches_for_session("sess1", chunk_size=10, finalize=True)
    second = batch_repo.create_pending_batches_for_session("sess1", chunk_size=10, finalize=True)

    assert first == 3
    assert second == 0
    assert len(batch_repo.list_pending_batch_ids_for_session("sess1")) == 3


def test_create_pending_batches_resumes_after_new_measurements_arrive(repos) -> None:
    """§ "Partial Session Upload": тәжірибе жүріп жатқанда мерзімді
    шақыру — әр tick алдыңғы ковербиенттен ЖАЛҒАСАДЫ."""
    session_repo, batch_repo, _ = repos
    session_repo.append_measurements("sess1", "ohms-law", _measurements(12), started_at=_NOW)
    batch_repo.create_pending_batches_for_session("sess1", chunk_size=10, finalize=False)

    session_repo.append_measurements("sess1", "ohms-law", _measurements(8, start_voltage=100.0), started_at=_NOW)
    created = batch_repo.create_pending_batches_for_session("sess1", chunk_size=10, finalize=False)

    assert created == 1  # § 2 (алғашқы tail) + 8 (жаңа) = 10 -> тағы 1 толық batch
    ids = batch_repo.list_pending_batch_ids_for_session("sess1")
    assert len(ids) == 2


def test_pending_batches_survive_repository_restart(shared_db_path) -> None:
    """§ "Restart Safety": pending batch күйі ЖАДЫДА ЕМЕС, sqlite-та
    тұрақты — ЖАҢА репозиторий данасы (§ "app restart" симуляциясы)
    дәл СОЛ ``db_path``-ты ашқанда, batch(тар) ЖӘНЕ outbox pending
    жазбалары аман қалады."""
    outbox = SqliteSyncOutboxRepository(shared_db_path)
    session_repo = SqliteSessionRepository(shared_db_path, sync_outbox_repository=outbox)
    batch_repo = SqliteMeasurementBatchRepository(shared_db_path, sync_outbox_repository=outbox)
    session_repo.append_measurements("sess1", "ohms-law", _measurements(15), started_at=_NOW)
    batch_repo.create_pending_batches_for_session("sess1", chunk_size=10, finalize=True)
    batch_ids_before = batch_repo.list_pending_batch_ids_for_session("sess1")
    pending_before = outbox.count_pending()

    # § "restart" — жаңа Python объектілері, БІРАҚ ДӘЛ СОЛ db_path.
    outbox_restarted = SqliteSyncOutboxRepository(shared_db_path)
    session_repo_restarted = SqliteSessionRepository(shared_db_path, sync_outbox_repository=outbox_restarted)
    batch_repo_restarted = SqliteMeasurementBatchRepository(shared_db_path, sync_outbox_repository=outbox_restarted)

    assert batch_repo_restarted.list_pending_batch_ids_for_session("sess1") == batch_ids_before
    assert outbox_restarted.count_pending() == pending_before
    assert len(session_repo_restarted.get_measurements("sess1")) == 15


def test_multiple_sessions_batch_independently(repos) -> None:
    session_repo, batch_repo, _ = repos
    session_repo.append_measurements("sess1", "ohms-law", _measurements(10), started_at=_NOW)
    session_repo.append_measurements("sess2", "ohms-law", _measurements(15), started_at=_NOW)

    batch_repo.create_pending_batches_for_session("sess1", chunk_size=10, finalize=True)
    batch_repo.create_pending_batches_for_session("sess2", chunk_size=10, finalize=True)

    assert len(batch_repo.list_pending_batch_ids_for_session("sess1")) == 1
    assert len(batch_repo.list_pending_batch_ids_for_session("sess2")) == 2


def test_create_pending_batches_enqueues_to_outbox_after_transaction_closes(repos) -> None:
    """§ "database is locked" регрессиясы — enqueue БӨЛЕК байланыс
    арқылы жүреді, ЖАЗУ транзакциясы ашық кезде ЕМЕС."""
    session_repo, batch_repo, outbox = repos
    session_repo.append_measurements("sess1", "ohms-law", _measurements(10), started_at=_NOW)

    batch_repo.create_pending_batches_for_session("sess1", chunk_size=10, finalize=True)

    assert outbox.count_pending() >= 1


# ---- get_batch_sync_payload() -----------------------------------------------


def test_batch_sync_payload_preserves_exact_numeric_values_and_order(repos) -> None:
    session_repo, batch_repo, _ = repos
    exact_measurements = (
        Measurement(timestamp=_NOW, values={"voltage": 6.413, "current": 0.0078}, derived_values={"power": 0.0500}, experiment_id="ohms-law"),
        Measurement(timestamp=_NOW, values={"resistance": 220.0}, experiment_id="ohms-law"),
    )
    session_repo.append_measurements("sess1", "ohms-law", exact_measurements, started_at=_NOW)
    batch_repo.create_pending_batches_for_session("sess1", chunk_size=2, finalize=False)
    batch_id = batch_repo.list_pending_batch_ids_for_session("sess1")[0]

    payload = batch_repo.get_batch_sync_payload(batch_id)

    assert payload["measurements"][0]["values"] == {"voltage": 6.413, "current": 0.0078}
    assert payload["measurements"][0]["derived_values"] == {"power": 0.0500}
    assert payload["measurements"][1]["values"] == {"resistance": 220.0}
    assert [m["sequence_no"] for m in payload["measurements"]] == [0, 1]
    assert payload["session_sync_id"] == "sess1"
    assert payload["sample_count"] == 2


def test_batch_sync_payload_preserves_unicode_warnings(repos) -> None:
    session_repo, batch_repo, _ = repos
    measurement = Measurement(
        timestamp=_NOW, values={"voltage": 1.0}, warnings=["Кернеу тым жоғары"], experiment_id="ohms-law"
    )
    session_repo.append_measurements("sess1", "ohms-law", (measurement,), started_at=_NOW)
    batch_repo.create_pending_batches_for_session("sess1", chunk_size=1, finalize=False)
    batch_id = batch_repo.list_pending_batch_ids_for_session("sess1")[0]

    payload = batch_repo.get_batch_sync_payload(batch_id)

    assert payload["measurements"][0]["warnings"] == ["Кернеу тым жоғары"]


def test_batch_sync_payload_unknown_id_returns_none(repos) -> None:
    _, batch_repo, _ = repos
    assert batch_repo.get_batch_sync_payload("does-not-exist") is None


# ---- apply_remote_batch() (Pull / second device reconstruction) ------------


def test_apply_remote_batch_reconstructs_measurements_on_second_device(shared_db_path, tmp_path) -> None:
    # § device 1
    outbox1 = SqliteSyncOutboxRepository(shared_db_path)
    session_repo1 = SqliteSessionRepository(shared_db_path, sync_outbox_repository=outbox1)
    batch_repo1 = SqliteMeasurementBatchRepository(shared_db_path, sync_outbox_repository=outbox1)
    measurements = _measurements(23)
    session_repo1.append_measurements("sess1", "ohms-law", measurements, started_at=_NOW)
    batch_repo1.create_pending_batches_for_session("sess1", chunk_size=10, finalize=True)
    batch_ids = batch_repo1.list_pending_batch_ids_for_session("sess1")
    session_payload = session_repo1.get_sync_payload("sess1")
    session_payload["server_revision"] = 1

    # § device 2 — ӨЗ БӨЛЕК, БІРАҚ ортақ db_path
    device2_db_path = str(tmp_path / "device2.db")
    outbox2 = SqliteSyncOutboxRepository(device2_db_path)
    session_repo2 = SqliteSessionRepository(device2_db_path, sync_outbox_repository=outbox2)
    batch_repo2 = SqliteMeasurementBatchRepository(device2_db_path, sync_outbox_repository=outbox2)

    session_repo2.apply_remote_session(session_payload)
    for batch_id in batch_ids:
        payload = batch_repo1.get_batch_sync_payload(batch_id)
        payload["server_revision"] = 1
        batch_repo2.apply_remote_batch(payload)

    reconstructed = session_repo2.get_measurements("sess1")
    assert len(reconstructed) == 23
    assert [m.values["voltage"] for m in reconstructed] == [m.values["voltage"] for m in measurements]
    assert outbox2.count_pending() == 0  # § apply_remote_* ЕШҚАШАН қайта enqueue жасамайды


def test_apply_remote_batch_is_idempotent_on_duplicate_apply(shared_db_path, tmp_path) -> None:
    outbox1 = SqliteSyncOutboxRepository(shared_db_path)
    session_repo1 = SqliteSessionRepository(shared_db_path, sync_outbox_repository=outbox1)
    batch_repo1 = SqliteMeasurementBatchRepository(shared_db_path, sync_outbox_repository=outbox1)
    session_repo1.append_measurements("sess1", "ohms-law", _measurements(5), started_at=_NOW)
    batch_repo1.create_pending_batches_for_session("sess1", chunk_size=5, finalize=False)
    batch_id = batch_repo1.list_pending_batch_ids_for_session("sess1")[0]
    payload = batch_repo1.get_batch_sync_payload(batch_id)
    payload["server_revision"] = 1

    device2_db_path = str(tmp_path / "device2.db")
    outbox2 = SqliteSyncOutboxRepository(device2_db_path)
    session_repo2 = SqliteSessionRepository(device2_db_path, sync_outbox_repository=outbox2)
    batch_repo2 = SqliteMeasurementBatchRepository(device2_db_path, sync_outbox_repository=outbox2)
    session_repo2.apply_remote_session(session_repo1.get_sync_payload("sess1") | {"server_revision": 1})

    batch_repo2.apply_remote_batch(payload)
    batch_repo2.apply_remote_batch(payload)  # § "server committed, client lost response, retries"

    assert len(session_repo2.get_measurements("sess1")) == 5


def test_mark_batch_synced_updates_state(repos) -> None:
    session_repo, batch_repo, _ = repos
    session_repo.append_measurements("sess1", "ohms-law", _measurements(3), started_at=_NOW)
    batch_repo.create_pending_batches_for_session("sess1", chunk_size=3, finalize=False)
    batch_id = batch_repo.list_pending_batch_ids_for_session("sess1")[0]

    batch_repo.mark_batch_synced(batch_id, server_revision=7)

    payload = batch_repo.get_batch_sync_payload(batch_id)
    assert payload["sync_state"] == "synced"
    assert payload["server_revision"] == 7
