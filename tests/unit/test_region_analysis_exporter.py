"""RegionAnalysisExporter: IO қатесі үнсіз False емес, ExportError."""

from pathlib import Path

import pytest

from core.exceptions import ExportError
from domain.services.region_analysis_exporter import (
    ChannelAnalysisSummary,
    RegionAnalysisExporter,
    RegionAnalysisSummary,
)


def _summary() -> RegionAnalysisSummary:
    return RegionAnalysisSummary(
        t1=0.0,
        t2=1.0,
        channels=(
            ChannelAnalysisSummary(
                display_name="Кернеу",
                unit="V",
                n=2,
                minimum=1.0,
                maximum=2.0,
                average=1.5,
                delta=1.0,
                std_dev=0.5,
                cv_percent=33.3,
                sem=0.35,
            ),
        ),
    )


def test_invalid_path_raises_export_error(tmp_path: Path) -> None:
    invalid_path = tmp_path / "no_such_directory" / "region.csv"

    with pytest.raises(ExportError, match="Файлды жазу мүмкін болмады"):
        RegionAnalysisExporter().export(_summary(), str(invalid_path))


def test_export_writes_csv(tmp_path: Path) -> None:
    output_path = tmp_path / "region.csv"

    assert RegionAnalysisExporter().export(_summary(), str(output_path)) is True
    text = output_path.read_text(encoding="utf-8")
    assert "Кернеу" in text
    assert "1.000000" in text
