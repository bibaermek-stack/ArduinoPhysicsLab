"""AnalyticsCsvExporter үшін юнит-тесттер (Phase 8)."""

import csv
from pathlib import Path

import pytest

from core.exceptions import ExportError
from domain.entities.learning_analytics import TopicPerformance, TopicPerformanceLevel
from domain.services.analytics_csv_exporter import AnalyticsCsvExporter
from domain.entities.learning_analytics import StudentLearningProgress


def _topic(experiment_id: str = "ohms-law", title: str = "Ом заңы", score: float | None = 7.0) -> TopicPerformance:
    return TopicPerformance(
        experiment_id=experiment_id, experiment_title=title, module_name="Электр құбылыстары",
        attempted_count=1, completed_count=1, reviewed_count=1, average_score=score,
        completion_rate=1.0, level=TopicPerformanceLevel.NEUTRAL,
    )


def _row(
    student_name: str = "Асанов Асан", classroom_name: str = "8А",
    overall_average_score: float | None = 7.0, overall_completion_rate: float | None = 0.5,
    weakest: TopicPerformance | None = None, strongest: TopicPerformance | None = None,
) -> StudentLearningProgress:
    return StudentLearningProgress(
        student_id="s1", student_name=student_name, classroom_id="ca", classroom_name=classroom_name,
        overall_average_score=overall_average_score, overall_completion_rate=overall_completion_rate,
        weakest_topic=weakest, strongest_topic=strongest,
    )


def _read_rows(path: Path) -> list[list[str]]:
    with open(path, encoding="utf-8", newline="") as csv_file:
        return list(csv.reader(csv_file))


def test_empty_rows_creates_no_file(tmp_path: Path) -> None:
    output_path = tmp_path / "export.csv"

    result = AnalyticsCsvExporter().export((), str(output_path))

    assert result is False
    assert not output_path.exists()


def test_header_row_matches_specification(tmp_path: Path) -> None:
    output_path = tmp_path / "export.csv"

    AnalyticsCsvExporter().export((_row(),), str(output_path))

    rows = _read_rows(output_path)
    assert rows[0] == [
        "Оқушы", "Сынып", "Орташа балл (0-10)", "Орындалу деңгейі (%)", "Әлсіз тақырып", "Күшті тақырып",
    ]


def test_one_row_is_exported_with_correct_values(tmp_path: Path) -> None:
    output_path = tmp_path / "export.csv"
    weak = _topic("ohms-law", "Ом заңы", 3.0)
    strong = _topic("current-voltage", "Ток пен кернеу", 9.0)

    AnalyticsCsvExporter().export(
        (_row(overall_average_score=6.0, overall_completion_rate=0.75, weakest=weak, strongest=strong),),
        str(output_path),
    )

    rows = _read_rows(output_path)
    assert rows[1] == ["Асанов Асан", "8А", "6.0", "75", "Ом заңы", "Ток пен кернеу"]


def test_missing_score_and_topics_are_written_as_empty_cells(tmp_path: Path) -> None:
    output_path = tmp_path / "export.csv"

    AnalyticsCsvExporter().export(
        (_row(overall_average_score=None, overall_completion_rate=None, weakest=None, strongest=None),),
        str(output_path),
    )

    rows = _read_rows(output_path)
    assert rows[1][2:] == ["", "", "", ""]


def test_multiple_rows_exported_in_order(tmp_path: Path) -> None:
    output_path = tmp_path / "export.csv"
    rows_in = (
        _row(student_name="Оқушы Бірінші"),
        _row(student_name="Оқушы Екінші"),
    )

    AnalyticsCsvExporter().export(rows_in, str(output_path))

    rows = _read_rows(output_path)
    assert [row[0] for row in rows[1:]] == ["Оқушы Бірінші", "Оқушы Екінші"]


def test_invalid_output_path_raises_export_error(tmp_path: Path) -> None:
    invalid_path = tmp_path / "no_such_directory" / "export.csv"

    with pytest.raises(ExportError, match="Файлды жазу мүмкін болмады"):
        AnalyticsCsvExporter().export((_row(),), str(invalid_path))


def test_file_is_utf8_encoded_and_readable(tmp_path: Path) -> None:
    output_path = tmp_path / "export.csv"

    AnalyticsCsvExporter().export((_row(),), str(output_path))

    raw_bytes = output_path.read_bytes()
    text = raw_bytes.decode("utf-8")
    assert "Асанов" in text
