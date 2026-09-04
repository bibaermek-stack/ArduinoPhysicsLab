"""build/windows_resources.py — VERSIONINFO мәтіні."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "build"))
from windows_resources import write_version_file


def test_version_file_contains_product_metadata(tmp_path: Path) -> None:
    path = write_version_file(tmp_path / "file_version_info.txt", "0.10.2")
    text = path.read_text(encoding="utf-8")
    assert "Arduino Physics Lab" in text
    assert "0.10.2.0" in text
    assert "OriginalFilename" in text
