"""SqliteSessionRepository үшін юнит-тесттер (Data Journal V1).

Барлық тест ``:memory:`` немесе ``tmp_path`` арқылы уақытша файл
қолданады — нақты пайдаланушы дерегіне ЕШҚАШАН тимейді.
"""

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from domain.entities.experiment_definition import ExperimentDefinition
from domain.entities.experiment_session import ExperimentSession
from domain.entities.measurement import Measurement
from infrastructure.storage.sqlite_session_repository import SqliteSessionRepository

_NOW = datetime.now(timezone.utc)


def _make_measurement(
    experiment_id: str = "ohms-law",
    voltage: float = 5.0,
    current: float = 0.05,
    offset_seconds: float = 0.0,
) -> Measurement:
    return Measurement(
        timestamp=_NOW + timedelta(seconds=offset_seconds),
        values={"voltage": voltage, "current": current},
        experiment_id=experiment_id,
        derived_values={"resistance": voltage / current},
        warnings=(),
    )


def _make_session(
    session_id: str = "session-1",
    experiment_id: str = "ohms-law",
    measurement_count: int = 3,
    ended: bool = True,
) -> ExperimentSession:
    session = ExperimentSession(
        id=session_id, experiment_id=experiment_id, started_at=_NOW
    )
    for i in range(measurement_count):
        session.add_measurement(
            _make_measurement(experiment_id=experiment_id, offset_seconds=i)
        )
    if ended:
        session.stop()
    return session


def _make_experiment_metadata(
    id_: str = "ohms-law",
    title: str = "Тізбек бөлігі үшін кернеудің ток күшіне тәуелділігін зерттеу",
    display_number: int = 4,
) -> ExperimentDefinition:
    return ExperimentDefinition(id=id_, title=title, description="", display_number=display_number)


@pytest.fixture
def repository() -> SqliteSessionRepository:
    return SqliteSessionRepository()  # :memory: default


def test_db_initializes_without_error(repository: SqliteSessionRepository) -> None:
    assert repository.count_sessions() == 0


def test_save_and_load_session_metadata(repository: SqliteSessionRepository) -> None:
    session = _make_session()
    metadata = _make_experiment_metadata()

    repository.save_session(session, metadata)
    summary = repository.get_session(session.id)

    assert summary is not None
    assert summary.id == session.id
    assert summary.experiment_id == "ohms-law"
    assert summary.experiment_title == "Тізбек бөлігі үшін кернеудің ток күшіне тәуелділігін зерттеу"
    assert summary.experiment_display_number == 4
    assert summary.measurement_count == 3
    assert summary.status == "finalized"


def test_load_measurements_preserves_values(repository: SqliteSessionRepository) -> None:
    session = _make_session(measurement_count=2)
    repository.save_session(session, _make_experiment_metadata())

    measurements = repository.get_measurements(session.id)

    assert len(measurements) == 2
    assert measurements[0].values == {"voltage": 5.0, "current": 0.05}


def test_load_measurements_preserves_derived_values(repository: SqliteSessionRepository) -> None:
    session = _make_session(measurement_count=1)
    repository.save_session(session, _make_experiment_metadata())

    measurements = repository.get_measurements(session.id)

    assert measurements[0].derived_values == {"resistance": 100.0}


def test_load_measurements_preserves_current_work_power_elapsed_time(
    repository: SqliteSessionRepository,
) -> None:
    """kезeng 28: Data Journal §10 — live measurement -> session -> SQLite
    round-trip PC-owned authoritative elapsed "time" (Ток жұмысы мен
    қуаты derived channel) мәнін дәл сақтауы керек, схема өзгеріссіз
    (``derived_values_json`` жалпы dict ретінде сериализацияланады).
    """
    session = ExperimentSession(
        id="work-power-session", experiment_id="current-work-power", started_at=_NOW
    )
    session.add_measurement(
        Measurement(
            timestamp=_NOW,
            values={"voltage": 5.0, "current": 0.2},
            experiment_id="current-work-power",
            derived_values={"time": 8.34, "power": 1.0, "work": 8.34},
        )
    )
    session.stop()
    repository.save_session(
        session, _make_experiment_metadata(id_="current-work-power", title="Ток жұмысы мен қуаты")
    )

    measurements = repository.get_measurements(session.id)

    assert len(measurements) == 1
    assert measurements[0].get_value("time") == pytest.approx(8.34)
    assert measurements[0].get_value("power") == pytest.approx(1.0)
    assert measurements[0].get_value("work") == pytest.approx(8.34)


def test_load_measurements_preserves_warnings(repository: SqliteSessionRepository) -> None:
    session = ExperimentSession(id="s-warn", experiment_id="ohms-law", started_at=_NOW)
    session.add_measurement(
        Measurement(
            timestamp=_NOW,
            values={"voltage": 1.0, "current": 0.1},
            experiment_id="ohms-law",
            warnings=("test warning",),
        )
    )
    session.stop()
    repository.save_session(session, _make_experiment_metadata())

    measurements = repository.get_measurements(session.id)

    assert measurements[0].warnings == ("test warning",)


def test_load_measurements_preserves_timestamps(repository: SqliteSessionRepository) -> None:
    session = _make_session(measurement_count=2)
    repository.save_session(session, _make_experiment_metadata())

    measurements = repository.get_measurements(session.id)

    assert measurements[0].timestamp.tzinfo is not None
    assert measurements[1].timestamp > measurements[0].timestamp


# ---- Phase 6: get_latest_measurement() (cheap, no full-history load) -------


def test_get_latest_measurement_returns_last_by_sequence_no(repository: SqliteSessionRepository) -> None:
    session = _make_session(measurement_count=5)
    repository.save_session(session, _make_experiment_metadata())

    latest = repository.get_latest_measurement(session.id)

    assert latest is not None
    all_measurements = repository.get_measurements(session.id)
    assert latest.timestamp == all_measurements[-1].timestamp
    assert latest.values == all_measurements[-1].values


def test_get_latest_measurement_unknown_session_returns_none(repository: SqliteSessionRepository) -> None:
    """§ Phase 6 "linked but no local measurements yet" — сол сессия
    ЖОҚ (§ ``link_session()``-тен кейін, бірақ бірінші ``append_
    measurements()``-тен БҰРЫН, § ``experiment_sessions`` жолы әлі
    құрылмаған) кезінде ``None`` қайтарады, ешбір exception."""
    assert repository.get_latest_measurement("does-not-exist") is None


def test_empty_session_is_not_persisted(repository: SqliteSessionRepository) -> None:
    session = ExperimentSession(id="empty-1", experiment_id="ohms-law", started_at=_NOW)

    repository.save_session(session, _make_experiment_metadata())

    assert repository.count_sessions() == 0
    assert repository.exists("empty-1") is False


def test_saving_same_session_twice_does_not_duplicate(repository: SqliteSessionRepository) -> None:
    session = _make_session(session_id="dup-1", measurement_count=2)
    metadata = _make_experiment_metadata()

    repository.save_session(session, metadata)
    repository.save_session(session, metadata)  # қайталап сақтау

    assert repository.count_sessions() == 1
    assert len(repository.get_measurements("dup-1")) == 2


def test_saving_session_again_with_more_measurements_updates_in_place(
    repository: SqliteSessionRepository,
) -> None:
    session = _make_session(session_id="grow-1", measurement_count=2)
    metadata = _make_experiment_metadata()
    repository.save_session(session, metadata)

    session.add_measurement(_make_measurement(offset_seconds=99))
    repository.save_session(session, metadata)

    assert repository.count_sessions() == 1
    summary = repository.get_session("grow-1")
    assert summary.measurement_count == 3
    assert len(repository.get_measurements("grow-1")) == 3


def test_sessions_sorted_newest_first(repository: SqliteSessionRepository) -> None:
    older = _make_session(session_id="older")
    older.started_at = _NOW - timedelta(hours=1)  # ExperimentSession frozen емес
    newer = _make_session(session_id="newer")

    repository.save_session(older, _make_experiment_metadata())
    repository.save_session(newer, _make_experiment_metadata())

    sessions = repository.get_sessions()

    assert [s.id for s in sessions] == ["newer", "older"]


def test_experiment_id_filter_works(repository: SqliteSessionRepository) -> None:
    ohms = _make_session(session_id="ohms-1", experiment_id="ohms-law")
    current_voltage = _make_session(session_id="cv-1", experiment_id="current-voltage")
    repository.save_session(ohms, _make_experiment_metadata())
    repository.save_session(
        current_voltage,
        _make_experiment_metadata(
            id_="current-voltage",
            title="Электр тізбегін құрастыру және ток күшін өлшеу",
            display_number=3,
        ),
    )

    filtered = repository.get_sessions(experiment_id="ohms-law")

    assert [s.id for s in filtered] == ["ohms-1"]


def test_corrupt_measurement_row_is_skipped_safely(tmp_path: Path) -> None:
    db_path = tmp_path / "corrupt.db"
    repository = SqliteSessionRepository(db_path=db_path)
    session = _make_session(session_id="corrupt-1", measurement_count=2)
    repository.save_session(session, _make_experiment_metadata())

    # Бір жолды қолмен бүлдіреміз (жарамсыз JSON).
    connection = sqlite3.connect(str(db_path))
    connection.execute(
        "UPDATE measurements SET values_json = ? WHERE session_id = ? AND sequence_no = 0",
        ("{not valid json", "corrupt-1"),
    )
    connection.commit()
    connection.close()

    measurements = repository.get_measurements("corrupt-1")

    # Бүлінген жол өткізіп жіберіледі, бүкіл сұрау құламайды — тек 1
    # жарамды measurement қайтарылады (2-ден).
    assert len(measurements) == 1
    repository.close()


def test_repository_isolated_from_real_user_db(tmp_path: Path) -> None:
    # Тест DB-і уақытша қалтада, нақты AppData жолында ЕМЕС.
    db_path = tmp_path / "isolated.db"
    repository = SqliteSessionRepository(db_path=db_path)

    repository.save_session(_make_session(session_id="iso-1"), _make_experiment_metadata())

    assert db_path.exists()
    assert repository.count_sessions() == 1
    repository.close()


def test_default_repository_uses_in_memory_database() -> None:
    repository = SqliteSessionRepository()
    repository.save_session(_make_session(session_id="mem-1"), _make_experiment_metadata())

    assert repository.count_sessions() == 1
    # ":memory:" -- жаңа дана қайта ашылмайды/бөлек файл жоқ, тек
    # осы объект ішінде өмір сүреді (нақты файл құрылмайды).


# ---- Stress / query-shape test (spec §34) ----------------------------------


def test_saving_many_sessions_and_loading_one_does_not_load_all_measurements(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "stress.db"
    repository = SqliteSessionRepository(db_path=db_path)
    metadata = _make_experiment_metadata()

    session_count = 100
    measurements_per_session = 500
    for i in range(session_count):
        session = _make_session(
            session_id=f"stress-{i}", measurement_count=measurements_per_session
        )
        repository.save_session(session, metadata)

    assert repository.count_sessions() == session_count

    # Тізім сұрауы — тек summary, measurement саны сол күйінде дұрыс
    # көрсетілуі тиіс, бірақ measurements кестесіне қатысы жоқ.
    summaries = repository.get_sessions()
    assert len(summaries) == session_count
    assert all(s.measurement_count == measurements_per_session for s in summaries)

    # Бір ғана сессияны ашу — тек сол сессияның 500 measurement-і жүктеледі.
    one_session_measurements = repository.get_measurements("stress-42")
    assert len(one_session_measurements) == measurements_per_session

    repository.close()
