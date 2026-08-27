"""infrastructure/sync/sync_worker.py тесттері (Phase 5: Connectivity-
Aware Automatic Sync) — coalescing, connectivity-triggered sync,
role-aware periodic interval, sync-disabled no-op, clean shutdown.

``SyncWorker.initialize()`` НАҚТЫ sqlite/HTTP/желі ресурстарын
құрастырады — бұл тесттер оны ЕШҚАШАН шақырмайды, орнына ``SyncWorker``
данасын ТІКЕЛЕЙ (сынақ дублерлерімен) құрастырады, § "test the
orchestration logic, not the real network/db wiring" (§ ``test_sync_
engine.py``-дегі ``FakeSyncApiClient``-пен БІРДЕЙ ұстаным).
"""

import os
import sys
import tempfile
from dataclasses import dataclass

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from domain.entities.sync_status import SyncStatus
from infrastructure.storage.app_preferences import AppPreferences
from infrastructure.sync.sync_worker import SyncWorker


@pytest.fixture(scope="module", autouse=True)
def qt_application() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture()
def temp_preferences():
    handle = tempfile.NamedTemporaryFile(suffix=".ini", delete=False)
    handle.close()
    settings = QSettings(handle.name, QSettings.Format.IniFormat)
    yield AppPreferences(settings)
    os.unlink(handle.name)


@dataclass
class _FakeSyncResult:
    status: SyncStatus
    pushed: int = 0
    pulled: int = 0
    errors: tuple = ()


class _FakeEngine:
    """§ ``run_sync()`` шақырылу санын санайды, әр шақыруда рет-ретімен
    ``results`` тізіміндегі мәнді қайтарады (соңғысы қайталанады).
    ``on_call`` (ерікті) — coalescing сынауы үшін, ӘРБІР шақыру
    ІШІНДЕ қосымша ``run_sync_now()`` сұрауын симуляциялауға мүмкіндік
    береді."""

    def __init__(self, results: list[_FakeSyncResult] | None = None, on_call=None) -> None:
        self.call_count = 0
        self._results = results or [_FakeSyncResult(status=SyncStatus.SYNCED)]
        self._on_call = on_call

    def run_sync(self):
        self.call_count += 1
        if self._on_call is not None:
            self._on_call(self.call_count)
        index = min(self.call_count - 1, len(self._results) - 1)
        return self._results[index]


class _FakeOutbox:
    def __init__(self, pending: int = 0) -> None:
        self.pending = pending

    def count_pending(self) -> int:
        return self.pending


class _FakeApiClient:
    def __init__(self, health_sequence: list[bool] | None = None) -> None:
        self._health_sequence = health_sequence or [True]
        self.check_health_call_count = 0
        self.configured_base_url: str | None = None

    def configure(self, *, base_url=None, api_key=None, request_timeout=None) -> None:
        if base_url is not None:
            self.configured_base_url = base_url

    def check_health(self) -> bool:
        index = min(self.check_health_call_count, len(self._health_sequence) - 1)
        self.check_health_call_count += 1
        return self._health_sequence[index]


class _FakeActiveContext:
    def __init__(self, identity_id: str) -> None:
        self.teacher_id = identity_id
        self.student_id = identity_id


class _FakeActiveRepo:
    def __init__(self, context: _FakeActiveContext | None = None) -> None:
        self._context = context

    def get(self):
        return self._context


def _build_worker(
    preferences: AppPreferences,
    engine=None,
    outbox=None,
    api_client=None,
    active_teacher=None,
    active_student=None,
    sync_enabled: bool = True,
) -> SyncWorker:
    # § ``_DEFAULT_SYNC_ENABLED`` False (§ app_preferences.py) — бұл
    # тесттердің КӨБІ coalescing/connectivity логикасын тексереді,
    # "sync disabled" гейтінің ӨЗІН ЕМЕС (§ ол бөлек, ``sync_enabled=
    # False`` беретін тесттерде), сондықтан әдепкі бойынша қосулы.
    preferences.set_sync_enabled(sync_enabled)
    worker = SyncWorker("unused-db-path")
    worker._preferences = preferences
    worker._engine = engine
    worker._outbox_repository = outbox or _FakeOutbox()
    worker._api_client = api_client or _FakeApiClient()
    worker._active_teacher_repository = active_teacher or _FakeActiveRepo()
    worker._active_student_repository = active_student or _FakeActiveRepo()
    return worker


# ---- Coalescing (§6) --------------------------------------------------------


def test_run_sync_now_executes_immediately_when_idle(temp_preferences) -> None:
    engine = _FakeEngine()
    worker = _build_worker(temp_preferences, engine=engine)

    worker.run_sync_now()

    assert engine.call_count == 1


def test_run_sync_now_coalesces_a_request_made_during_an_active_cycle(temp_preferences) -> None:
    """§6 "if useful, remember that another sync was requested and run
    one additional cycle afterward" — ағымдағы циклдың ІШІНДЕ (§ ``on_call``)
    тағы бір ``run_sync_now()`` сұрауы келсе, ДӘЛ БІР қосымша цикл
    жүреді, ЕКІНШІ емес."""
    calls_seen: list[int] = []

    def _on_call(call_number: int) -> None:
        calls_seen.append(call_number)
        if call_number == 1:
            worker.run_sync_now()  # § "another trigger arrived while syncing"
            worker.run_sync_now()  # § екінші қайталама сұрау — ЕШБІР қосымша цикл ТУДЫРМАУЫ керек

    engine = _FakeEngine(on_call=_on_call)
    worker = _build_worker(temp_preferences, engine=engine)

    worker.run_sync_now()

    assert engine.call_count == 2  # § бастапқы + ДӘЛ БІР коалесцирленген қосымша
    assert calls_seen == [1, 2]


def test_run_sync_now_never_overlaps_is_syncing(temp_preferences) -> None:
    """§ "never run multiple overlapping SyncEngine cycles" — цикл
    ІШІНДЕ ``_is_syncing`` әрқашан ``True`` болады."""
    observed_is_syncing: list[bool] = []

    def _on_call(_call_number: int) -> None:
        observed_is_syncing.append(worker._is_syncing)

    engine = _FakeEngine(on_call=_on_call)
    worker = _build_worker(temp_preferences, engine=engine)

    worker.run_sync_now()

    assert observed_is_syncing == [True]
    assert worker._is_syncing is False  # § цикл аяқталғаннан кейін тазаланады


def test_sync_disabled_prevents_coalesced_rerun(temp_preferences) -> None:
    """§ "sync disabled" күйі коалесцирленген қайта-циклда да
    құрметтелуі керек."""
    temp_preferences.set_sync_enabled(True)

    def _on_call(call_number: int) -> None:
        if call_number == 1:
            worker.run_sync_now()
            temp_preferences.set_sync_enabled(False)

    engine = _FakeEngine(on_call=_on_call)
    worker = _build_worker(temp_preferences, engine=engine)

    worker.run_sync_now()

    assert engine.call_count == 1  # § "rerun requested" болса да, sync өшірілген -> қосымша цикл ЖОҚ


def test_sync_disabled_is_a_pure_noop(temp_preferences) -> None:
    engine = _FakeEngine()
    worker = _build_worker(temp_preferences, engine=engine, sync_enabled=False)

    worker.run_sync_now()

    assert engine.call_count == 0


def test_run_sync_now_applies_updated_server_url(temp_preferences) -> None:
    temp_preferences.set_sync_api_base_url("https://lab.example.kz")
    api_client = _FakeApiClient()
    worker = _build_worker(temp_preferences, engine=_FakeEngine(), api_client=api_client)

    worker.run_sync_now()

    assert api_client.configured_base_url == "https://lab.example.kz"


def test_run_sync_now_without_engine_is_a_safe_noop(temp_preferences) -> None:
    worker = _build_worker(temp_preferences, engine=None)

    worker.run_sync_now()  # § exception шығармауы керек


# ---- Connectivity monitor wiring (§3/§4) ------------------------------------


def test_connectivity_tick_triggers_sync_on_offline_to_online_transition(temp_preferences) -> None:
    engine = _FakeEngine()
    api_client = _FakeApiClient(health_sequence=[False, True])
    worker = _build_worker(temp_preferences, engine=engine, api_client=api_client)

    worker._on_connectivity_timer_tick()  # § False -> "change", БІРАҚ "just_came_online" ЕМЕС
    assert engine.call_count == 0

    worker._on_connectivity_timer_tick()  # § False -> True: "connectivity restored"
    assert engine.call_count == 1


def test_connectivity_tick_emits_signal_only_on_change(temp_preferences, qtbot=None) -> None:
    engine = _FakeEngine()
    api_client = _FakeApiClient(health_sequence=[True, True, True])
    worker = _build_worker(temp_preferences, engine=engine, api_client=api_client)
    received: list[tuple[bool, int]] = []
    worker.connectivity_changed.connect(lambda online, pending: received.append((online, pending)))

    worker._on_connectivity_timer_tick()  # § None -> True: change
    worker._on_connectivity_timer_tick()  # § True -> True: NO change
    worker._on_connectivity_timer_tick()  # § True -> True: NO change

    assert received == [(True, 0)]
    assert engine.call_count == 1  # § "just came online" ТЕК БІРІНШІ tick-те (алдыңғы белгісіз -> True)


def test_connectivity_tick_skips_health_check_while_sync_in_progress(temp_preferences) -> None:
    api_client = _FakeApiClient(health_sequence=[True])
    worker = _build_worker(temp_preferences, engine=_FakeEngine(), api_client=api_client)
    worker._is_syncing = True

    worker._on_connectivity_timer_tick()

    assert api_client.check_health_call_count == 0  # § "avoid excessive server requests"


def test_full_cycle_result_updates_connectivity_state_without_extra_ping(temp_preferences) -> None:
    """§ ``_run_sync_cycle()`` СОҢЫНДА connectivity-монитор ӨЗ нәтижесімен
    жаңартылады — арнайы ``check_health()`` шақыруынсыз."""
    engine = _FakeEngine(results=[_FakeSyncResult(status=SyncStatus.OFFLINE)])
    api_client = _FakeApiClient(health_sequence=[True])
    worker = _build_worker(temp_preferences, engine=engine, api_client=api_client)
    received: list[tuple[bool, int]] = []
    worker.connectivity_changed.connect(lambda online, pending: received.append((online, pending)))

    worker.run_sync_now()

    assert api_client.check_health_call_count == 0
    assert received == [(False, 0)]


# ---- Role-aware periodic interval (§8) --------------------------------------


def test_periodic_interval_is_short_when_teacher_active(temp_preferences) -> None:
    temp_preferences.set_teacher_auto_refresh_interval_seconds(7)
    worker = _build_worker(
        temp_preferences, active_teacher=_FakeActiveRepo(_FakeActiveContext("t1"))
    )

    assert worker._periodic_interval_ms() == 7000


def test_periodic_interval_is_long_default_when_student_active(temp_preferences) -> None:
    worker = _build_worker(
        temp_preferences,
        active_teacher=_FakeActiveRepo(None),
        active_student=_FakeActiveRepo(_FakeActiveContext("s1")),
    )

    assert worker._periodic_interval_ms() == 15 * 60 * 1000


def test_periodic_interval_is_long_default_when_no_active_identity(temp_preferences) -> None:
    worker = _build_worker(temp_preferences)

    assert worker._periodic_interval_ms() == 15 * 60 * 1000


# ---- Clean shutdown (§18) ----------------------------------------------------


def test_shutdown_without_initialize_does_not_raise(temp_preferences) -> None:
    worker = SyncWorker("unused-db-path")
    worker.shutdown()  # § ешбір таймер құрылмаған, exception шығармауы керек


def test_shutdown_stops_and_clears_timers(tmp_path) -> None:
    worker = SyncWorker(str(tmp_path / "worker_shutdown_test.db"))
    worker.initialize()
    try:
        assert worker._periodic_timer is not None
        assert worker._connectivity_timer is not None

        worker.shutdown()

        assert worker._periodic_timer is None
        assert worker._connectivity_timer is None
        assert worker._engine is None
    finally:
        worker.shutdown()
