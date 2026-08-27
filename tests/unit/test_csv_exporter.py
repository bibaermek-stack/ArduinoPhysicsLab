"""CSVExporter үшін юнит-тесттер."""

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

from domain.entities.experiment_session import ExperimentSession
from domain.entities.measurement import Measurement
from domain.services.csv_exporter import CSVExporter


def _make_measurement(
    values: dict[str, float] | None = None,
    derived_values: dict[str, float] | None = None,
    timestamp: datetime | None = None,
) -> Measurement:
    return Measurement(
        timestamp=timestamp or datetime.now(timezone.utc),
        values=values or {},
        experiment_id="E02",
        derived_values=derived_values or {},
    )


def _make_session(started_at: datetime | None = None) -> ExperimentSession:
    return ExperimentSession(
        id="s1", experiment_id="E02", started_at=started_at or datetime.now(timezone.utc)
    )


def _read_rows(path: Path) -> list[list[str]]:
    with open(path, encoding="utf-8", newline="") as csv_file:
        return list(csv.reader(csv_file))


def test_empty_session_creates_no_file(tmp_path: Path) -> None:
    session = _make_session()
    output_path = tmp_path / "export.csv"

    result = CSVExporter().export(session, str(output_path))

    assert result is False
    assert not output_path.exists()


def test_one_measurement_is_exported(tmp_path: Path) -> None:
    session = _make_session()
    session.add_measurement(
        _make_measurement(
            values={"voltage": 5.024, "current": 0.218}, derived_values={"power": 1.095}
        )
    )
    output_path = tmp_path / "export.csv"

    result = CSVExporter().export(session, str(output_path))

    assert result is True
    rows = _read_rows(output_path)
    assert len(rows) == 2
    assert rows[1] == ["1", "0.00", "5.024", "0.218", "1.095"]


def test_many_measurements_are_exported_in_order(tmp_path: Path) -> None:
    started_at = datetime.now(timezone.utc)
    session = _make_session(started_at)
    for i in range(1, 4):
        session.add_measurement(
            _make_measurement(
                values={"voltage": float(i)},
                timestamp=started_at + timedelta(seconds=i),
            )
        )
    output_path = tmp_path / "export.csv"

    result = CSVExporter().export(session, str(output_path))

    assert result is True
    rows = _read_rows(output_path)
    assert len(rows) == 4  # header + 3
    assert [row[2] for row in rows[1:]] == ["1.000", "2.000", "3.000"]


def test_missing_values_are_written_as_empty_cells(tmp_path: Path) -> None:
    session = _make_session()
    session.add_measurement(_make_measurement(values={"voltage": 5.0}))
    output_path = tmp_path / "export.csv"

    CSVExporter().export(session, str(output_path))

    rows = _read_rows(output_path)
    assert rows[1][3] == ""  # current
    assert rows[1][4] == ""  # power


def test_time_uses_two_decimals(tmp_path: Path) -> None:
    started_at = datetime.now(timezone.utc)
    session = _make_session(started_at)
    session.add_measurement(
        _make_measurement(values={"voltage": 1.0}, timestamp=started_at)
    )
    session.add_measurement(
        _make_measurement(
            values={"voltage": 2.0},
            timestamp=started_at + timedelta(seconds=1, milliseconds=500),
        )
    )
    output_path = tmp_path / "export.csv"

    CSVExporter().export(session, str(output_path))

    rows = _read_rows(output_path)
    assert rows[1][1] == "0.00"
    assert rows[2][1] == "1.50"


def test_authoritative_elapsed_time_is_used_when_present_on_measurement(
    tmp_path: Path,
) -> None:
    """kезeng 28: Current Work/Power сияқты, ``Measurement.derived_values``
    ('немесе values') ішінде PC-owned "time" болса, CSV бұл дәл сол
    authoritative мәнді қолдануы керек — ``timestamp - session.started_at``
    fallback-і ЕМЕС (ол мән session ашылған сәттен есептеледі, ACK-gated
    running=True сәтінен емес, сондықтан екеуі сәйкес келмеуі мүмкін).
    """
    started_at = datetime.now(timezone.utc)
    session = _make_session(started_at)
    # timestamp session started_at-тан 100 секунд кейін (page ашылған соң
    # көп уақыт өткен сценарийді модельдейді), бірақ authoritative
    # elapsed-time (derived_values["time"]) тек 8.34 с — CSV ДӘЛ осыны
    # жазуы керек, 100.00-ді ЕМЕС.
    session.add_measurement(
        _make_measurement(
            values={"voltage": 5.0, "current": 0.5},
            derived_values={"time": 8.34, "power": 2.5},
            timestamp=started_at + timedelta(seconds=100),
        )
    )
    output_path = tmp_path / "export.csv"

    CSVExporter().export(session, str(output_path))

    rows = _read_rows(output_path)
    assert rows[1][1] == "8.34"


def test_numbers_use_three_decimals(tmp_path: Path) -> None:
    session = _make_session()
    session.add_measurement(
        _make_measurement(
            values={"voltage": 5.0, "current": 0.2}, derived_values={"power": 1.0}
        )
    )
    output_path = tmp_path / "export.csv"

    CSVExporter().export(session, str(output_path))

    rows = _read_rows(output_path)
    assert rows[1][2] == "5.000"
    assert rows[1][3] == "0.200"
    assert rows[1][4] == "1.000"


def test_file_is_utf8_encoded(tmp_path: Path) -> None:
    session = _make_session()
    session.add_measurement(_make_measurement(values={"voltage": 5.0}))
    output_path = tmp_path / "export.csv"

    CSVExporter().export(session, str(output_path))

    # UTF-8 ретінде оқу қатесіз өтуі керек, newline дұрыс өңделуі керек
    # (barлық жол \r\n қосымша қайталанбай).
    raw_bytes = output_path.read_bytes()
    text = raw_bytes.decode("utf-8")
    assert "\r\r" not in text


def test_header_row_matches_specification(tmp_path: Path) -> None:
    session = _make_session()
    session.add_measurement(_make_measurement(values={"voltage": 5.0}))
    output_path = tmp_path / "export.csv"

    CSVExporter().export(session, str(output_path))

    rows = _read_rows(output_path)
    assert rows[0] == ["No", "Time(s)", "Voltage(V)", "Current(A)", "Power(W)"]


def test_row_numbering_starts_at_one_and_increments(tmp_path: Path) -> None:
    session = _make_session()
    for i in range(3):
        session.add_measurement(_make_measurement(values={"voltage": float(i)}))
    output_path = tmp_path / "export.csv"

    CSVExporter().export(session, str(output_path))

    rows = _read_rows(output_path)
    assert [row[0] for row in rows[1:]] == ["1", "2", "3"]


def test_invalid_output_path_returns_false_without_crashing(tmp_path: Path) -> None:
    session = _make_session()
    session.add_measurement(_make_measurement(values={"voltage": 5.0}))
    invalid_path = tmp_path / "no_such_directory" / "export.csv"

    result = CSVExporter().export(session, str(invalid_path))

    assert result is False
