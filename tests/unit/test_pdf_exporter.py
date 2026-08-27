"""PDFExporter үшін юнит-тесттер.

PDF мазмұнын тексеру үшін ``pypdf`` қолданылады — бұл тек тестке
арналған құрал, ол ``requirements.txt``-ке (production тәуелділігіне)
қосылмайды, себебі PDFExporter-дің өзі оны қолданбайды.
"""

import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pypdf import PdfReader

import domain.services.pdf_exporter as pdf_exporter_module
from domain.entities.experiment_session import ExperimentSession
from domain.entities.measurement import Measurement
from domain.services.pdf_exporter import PDFExporter


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


def _extract_text(path: Path) -> str:
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() for page in reader.pages)


def test_empty_session_returns_false_and_creates_no_file(tmp_path: Path) -> None:
    session = _make_session()
    output_path = tmp_path / "report.pdf"

    result = PDFExporter().export(session, str(output_path))

    assert result is False
    assert not output_path.exists()


def test_pdf_file_is_created(tmp_path: Path) -> None:
    session = _make_session()
    session.add_measurement(_make_measurement(values={"voltage": 5.0}))
    output_path = tmp_path / "report.pdf"

    result = PDFExporter().export(session, str(output_path))

    assert result is True
    assert output_path.exists()


def test_pdf_extension_is_added_automatically(tmp_path: Path) -> None:
    session = _make_session()
    session.add_measurement(_make_measurement(values={"voltage": 5.0}))
    output_path_without_extension = tmp_path / "report"

    result = PDFExporter().export(session, str(output_path_without_extension))

    assert result is True
    assert (tmp_path / "report.pdf").exists()


def test_invalid_path_returns_false(tmp_path: Path) -> None:
    session = _make_session()
    session.add_measurement(_make_measurement(values={"voltage": 5.0}))
    invalid_path = tmp_path / "no_such_directory" / "report.pdf"

    result = PDFExporter().export(session, str(invalid_path))

    assert result is False


def test_one_measurement_is_included(tmp_path: Path) -> None:
    session = _make_session()
    session.add_measurement(
        _make_measurement(
            values={"voltage": 5.024, "current": 0.218}, derived_values={"power": 1.095}
        )
    )
    output_path = tmp_path / "report.pdf"

    PDFExporter().export(session, str(output_path))

    text = _extract_text(output_path)
    assert "5.024" in text
    assert "0.218" in text
    assert "1.095" in text


def test_many_measurements_are_included(tmp_path: Path) -> None:
    started_at = datetime.now(timezone.utc)
    session = _make_session(started_at)
    for i in range(1, 6):
        session.add_measurement(
            _make_measurement(
                values={"voltage": float(i)},
                timestamp=started_at + timedelta(seconds=i),
            )
        )
    output_path = tmp_path / "report.pdf"

    PDFExporter().export(session, str(output_path))

    text = _extract_text(output_path)
    for i in range(1, 6):
        assert f"{float(i):.3f}" in text


def test_missing_values_show_dash(tmp_path: Path) -> None:
    session = _make_session()
    session.add_measurement(_make_measurement(values={"voltage": 5.0}))
    output_path = tmp_path / "report.pdf"

    PDFExporter().export(session, str(output_path))

    text = _extract_text(output_path)
    assert "—" in text


def test_elapsed_time_computed_from_timestamp(tmp_path: Path) -> None:
    started_at = datetime.now(timezone.utc)
    session = _make_session(started_at)
    session.add_measurement(
        _make_measurement(values={"voltage": 1.0}, timestamp=started_at)
    )
    session.add_measurement(
        _make_measurement(
            values={"voltage": 2.0}, timestamp=started_at + timedelta(seconds=2, milliseconds=500)
        )
    )
    output_path = tmp_path / "report.pdf"

    PDFExporter().export(session, str(output_path))

    text = _extract_text(output_path)
    assert "0.00" in text
    assert "2.50" in text


def test_explicit_time_value_is_used(tmp_path: Path) -> None:
    session = _make_session()
    session.add_measurement(
        _make_measurement(values={"voltage": 1.0, "time": 42.5})
    )
    output_path = tmp_path / "report.pdf"

    PDFExporter().export(session, str(output_path))

    text = _extract_text(output_path)
    assert "42.50" in text


def test_voltage_statistics_are_computed(tmp_path: Path) -> None:
    session = _make_session()
    for value in (1.0, 2.0, 3.0):
        session.add_measurement(_make_measurement(values={"voltage": value}))
    output_path = tmp_path / "report.pdf"

    PDFExporter().export(session, str(output_path))

    text = _extract_text(output_path)
    assert "1.000" in text  # min
    assert "3.000" in text  # max
    assert "2.000" in text  # average


def test_current_statistics_are_computed(tmp_path: Path) -> None:
    session = _make_session()
    for value in (0.1, 0.2, 0.3):
        session.add_measurement(_make_measurement(values={"current": value}))
    output_path = tmp_path / "report.pdf"

    PDFExporter().export(session, str(output_path))

    text = _extract_text(output_path)
    assert "0.100" in text  # min
    assert "0.300" in text  # max
    assert "0.200" in text  # average


def test_power_statistics_are_computed(tmp_path: Path) -> None:
    session = _make_session()
    for value in (1.0, 3.0, 5.0):
        session.add_measurement(_make_measurement(derived_values={"power": value}))
    output_path = tmp_path / "report.pdf"

    PDFExporter().export(session, str(output_path))

    text = _extract_text(output_path)
    assert "1.000" in text  # min
    assert "5.000" in text  # max
    assert "3.000" in text  # average


def test_non_finite_values_excluded_from_statistics(tmp_path: Path) -> None:
    session = _make_session()
    session.add_measurement(_make_measurement(values={"voltage": math.nan}))
    session.add_measurement(_make_measurement(values={"voltage": math.inf}))
    output_path = tmp_path / "report.pdf"

    PDFExporter().export(session, str(output_path))

    # Ешбір ақырлы (finite) voltage мәні жоқ, сондықтан статистика жолы "—".
    stats = PDFExporter()._compute_channel_statistics(session.measurements, "voltage")
    assert stats is None


def test_multi_page_pdf_for_many_measurements(tmp_path: Path) -> None:
    started_at = datetime.now(timezone.utc)
    session = _make_session(started_at)
    for i in range(80):
        session.add_measurement(
            _make_measurement(
                values={"voltage": float(i)},
                timestamp=started_at + timedelta(seconds=i),
            )
        )
    output_path = tmp_path / "report.pdf"

    PDFExporter().export(session, str(output_path))

    reader = PdfReader(str(output_path))
    assert len(reader.pages) > 1


def test_kazakh_unicode_text_is_present(tmp_path: Path) -> None:
    session = _make_session()
    session.add_measurement(_make_measurement(values={"voltage": 5.0}))
    output_path = tmp_path / "report.pdf"

    PDFExporter().export(session, str(output_path))

    text = _extract_text(output_path)
    assert "Өлшеу нәтижелері" in text
    assert "Тәжірибе туралы ақпарат" in text
    assert "Қысқаша статистика" in text
    assert "Өлшеулер кестесі" in text


def test_missing_font_returns_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pdf_exporter_module, "_find_unicode_font", lambda: None)
    session = _make_session()
    session.add_measurement(_make_measurement(values={"voltage": 5.0}))
    output_path = tmp_path / "report.pdf"

    result = PDFExporter().export(session, str(output_path))

    assert result is False
    assert not output_path.exists()


def test_existing_file_is_overwritten(tmp_path: Path) -> None:
    output_path = tmp_path / "report.pdf"

    first_session = _make_session()
    first_session.add_measurement(_make_measurement(values={"voltage": 1.0}))
    assert PDFExporter().export(first_session, str(output_path)) is True

    second_session = _make_session()
    second_session.add_measurement(_make_measurement(values={"voltage": 9.999}))
    result = PDFExporter().export(second_session, str(output_path))

    assert result is True
    text = _extract_text(output_path)
    assert "9.999" in text
