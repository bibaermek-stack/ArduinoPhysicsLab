"""Production логтау баптауы (Phase 9 — Production Deployment & Release
Readiness, § Part H "Logging").

Бұрын ``main.py`` ``debug.log``-ты ӨЗ жанында (жоба/орнату қалтасында,
``mode="w"`` — әр іске қосылымда толық тазартылатын) жазатын, бұл екеуі
де қате: (1) ``Program Files`` астында орнатылған қолданбаға жазу
рұқсаты болмайды (§ "writable data outside install directory"), (2)
ротация жоқ болғандықтан ұзақ сессияда файл шексіз өседі. Бұл модуль
``database.py::get_default_database_path()``-пен БІРДЕЙ түбір қалтаны
(``%LOCALAPPDATA%\\ArduinoPhysicsLab\\``) қолданады, БІРАҚ
``QStandardPaths`` ЕМЕС — бұл модуль ``main.py``-де ЕҢ БІРІНШІ, ``QCore
Application`` org/app атауы орнатылғанға (§ ``app.py::run()``) дейін
шақырылатындықтан, ``%LOCALAPPDATA%`` орта айнымалысынан ТІКЕЛЕЙ оқиды.

§ "But NEVER log: student access codes, teacher PINs, hashes, JWT
tokens, secrets, full confidential feedback text" — бұл модуль ӨЗІ
ешбір мазмұнды логтамайды (тек handler/директория құрады); шақырушы
код (``main.py``, ``sync_engine.py`` және т.б.) осы ережені бұрыннан
сақтайды (§ ``app_preferences.py`` докстрингі — токен ешқашан
логталмайды).
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

_APP_DIR_NAME = "ArduinoPhysicsLab"
_LOG_FILENAME = "debug.log"
_DEFAULT_MAX_BYTES = 2 * 1024 * 1024  # 2 MB — § "use rotation if practical"
_DEFAULT_BACKUP_COUNT = 3


def get_log_directory() -> Path:
    """Журнал файлдары жазылатын қалта — орнату (install) қалтасының
    СЫРТЫНДА, пайдаланушыға тән, жазуға әрқашан рұқсат етілген орын."""
    base = os.environ.get("LOCALAPPDATA")
    root = Path(base) if base else Path.home() / "AppData" / "Local"
    directory = root / _APP_DIR_NAME / "logs"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def configure_rotating_logger(
    logger_name: str,
    *,
    log_directory: Path | None = None,
    max_bytes: int = _DEFAULT_MAX_BYTES,
    backup_count: int = _DEFAULT_BACKUP_COUNT,
) -> logging.Logger:
    """``logger_name`` логгеріне ротацияланатын файл handler-ін қосады.

    Идемпотентті — бұл функция БҰРЫН осы ДӘЛ логгерге қосқан handler
    әлдеқашан бар болса, ЕКІНШІ рет қосылмайды (§ қайта шақырылу
    қауіпсіз, мыс. тестте немесе қайта импорт жағдайында қос жазба
    пайда болмайды).
    """
    logger = logging.getLogger(logger_name)
    directory = log_directory if log_directory is not None else get_log_directory()
    log_path = directory / _LOG_FILENAME

    for existing_handler in logger.handlers:
        if getattr(existing_handler, "_apl_managed_rotating_handler", False):
            return logger

    handler = RotatingFileHandler(
        log_path, mode="a", maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
    )
    handler._apl_managed_rotating_handler = True
    handler.setFormatter(
        logging.Formatter("%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    )
    logger.addHandler(handler)
    return logger
