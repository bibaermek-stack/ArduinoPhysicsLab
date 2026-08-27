"""``core/logging_setup.py`` юнит-тесттері (Phase 9 — Production
Deployment, § Part H "Logging").

``LOCALAPPDATA`` орта айнымалысы ``tmp_path``-қа monkeypatch етіледі —
НАҚТЫ ``%LOCALAPPDATA%``-ге ЕШҚАШАН жазбайды (§ "Do not write brittle
tests tied to the developer's real machine state").
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from core.logging_setup import configure_rotating_logger, get_log_directory


def test_log_directory_is_outside_install_tree(monkeypatch, tmp_path: Path) -> None:
    """§ "writable data outside install directory" — журнал қалтасы
    ``%LOCALAPPDATA%\\ArduinoPhysicsLab\\logs\\`` пішінінде, ЕШҚАШАН
    жоба/орнату қалтасына қатысты есептелмейді."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    directory = get_log_directory()

    assert directory == tmp_path / "ArduinoPhysicsLab" / "logs"
    assert directory.is_dir()


def test_log_directory_created_idempotently(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    first = get_log_directory()
    second = get_log_directory()

    assert first == second
    assert first.is_dir()


def test_configure_rotating_logger_writes_to_expected_path(tmp_path: Path) -> None:
    logger_name = "apl.test.phase9.rotating"
    logger = configure_rotating_logger(logger_name, log_directory=tmp_path)
    logger.setLevel(logging.INFO)

    logger.info("hello from phase 9 test")
    for handler in logger.handlers:
        handler.flush()

    log_file = tmp_path / "debug.log"
    assert log_file.exists()
    assert "hello from phase 9 test" in log_file.read_text(encoding="utf-8")

    # § тазарту — келесі тесттерге handler сарқып қалмауы үшін.
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()


def test_configure_rotating_logger_is_idempotent(tmp_path: Path) -> None:
    """§ "must not silently duplicate every log line" — қайта шақыру
    ЕКІНШІ rotating handler қоспайды."""
    logger_name = "apl.test.phase9.idempotent"
    logger = configure_rotating_logger(logger_name, log_directory=tmp_path)
    configure_rotating_logger(logger_name, log_directory=tmp_path)
    configure_rotating_logger(logger_name, log_directory=tmp_path)

    rotating_handlers = [h for h in logger.handlers if isinstance(h, RotatingFileHandler)]
    assert len(rotating_handlers) == 1

    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()


def test_configure_rotating_logger_uses_rotation_settings(tmp_path: Path) -> None:
    """§ "use rotation if practical" — ``maxBytes``/``backupCount``
    нақты берілген мәндермен қолданылады, шексіз өсетін файл жоқ."""
    logger_name = "apl.test.phase9.rotation_config"
    logger = configure_rotating_logger(
        logger_name, log_directory=tmp_path, max_bytes=1024, backup_count=2
    )

    handler = next(h for h in logger.handlers if isinstance(h, RotatingFileHandler))
    assert handler.maxBytes == 1024
    assert handler.backupCount == 2

    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
