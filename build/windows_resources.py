"""PyInstaller үшін VERSIONINFO және .ico (қолтаңбасыз .exe эвристикасын азайту)."""

from __future__ import annotations

import struct
from pathlib import Path


def write_version_file(output_path: Path, version: str) -> Path:
    parts = [int(piece) for piece in version.split(".")]
    while len(parts) < 4:
        parts.append(0)
    filevers = tuple(parts[:4])
    dotted = ".".join(str(part) for part in filevers)
    output_path.write_text(
        f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={filevers!r},
    prodvers={filevers!r},
    mask=0x3F,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0),
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [
          StringStruct('CompanyName', 'Arduino Physics Lab'),
          StringStruct('FileDescription', 'Arduino Physics Lab — school physics laboratory'),
          StringStruct('FileVersion', '{dotted}'),
          StringStruct('InternalName', 'ArduinoPhysicsLab'),
          StringStruct('LegalCopyright', 'MIT License'),
          StringStruct('OriginalFilename', 'ArduinoPhysicsLab.exe'),
          StringStruct('ProductName', 'Arduino Physics Lab'),
          StringStruct('ProductVersion', '{dotted}'),
        ],
      ),
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])]),
  ],
)
""",
        encoding="utf-8",
    )
    return output_path


def _png_to_ico(png_bytes: bytes, size: int) -> bytes:
    """PNG-ді бір өлшемді ICO контейнеріне салады (Vista+)."""
    entry = struct.pack(
        "<BBBBHHII",
        size if size < 256 else 0,
        size if size < 256 else 0,
        0,
        0,
        1,
        32,
        len(png_bytes),
        22,
    )
    return b"\x00\x00\x01\x00\x01\x00" + entry + png_bytes


def write_app_icon(output_path: Path, svg_path: Path, size: int = 256) -> Path | None:
    try:
        from PySide6.QtCore import QBuffer, QIODevice, QRectF, Qt
        from PySide6.QtGui import QImage, QPainter
        from PySide6.QtSvg import QSvgRenderer
        from PySide6.QtWidgets import QApplication
    except ImportError:
        return None

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    renderer = QSvgRenderer(str(svg_path))
    if not renderer.isValid():
        return None
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    output_path.write_bytes(_png_to_ico(bytes(buffer.data()), size))
    return output_path


def prepare(project_root: Path) -> tuple[Path, Path | None]:
    pack_dir = project_root / "build" / "packaged"
    pack_dir.mkdir(parents=True, exist_ok=True)
    import sys

    sys.path.insert(0, str(project_root))
    from core.version import __version__

    version_path = write_version_file(pack_dir / "file_version_info.txt", __version__)
    svg_path = project_root / "server" / "app" / "web" / "static" / "favicon.svg"
    icon_path = write_app_icon(pack_dir / "app.ico", svg_path) if svg_path.is_file() else None
    return version_path, icon_path
