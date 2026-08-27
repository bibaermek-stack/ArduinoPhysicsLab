"""Arduino Physics Lab қолданбасының кіру нүктесі (entry point).

Навигация/рөл ауыстыру ағынының диагностикасы "apl.trace" логгеріне
жазылады — § Phase 9 (Production Deployment & Release Readiness, Part
H "Logging") бойынша ``core/logging_setup.py`` арқылы, жазуға әрқашан
рұқсат етілген ``%LOCALAPPDATA%\\ArduinoPhysicsLab\\logs\\`` қалтасына,
ротациямен (§ бұрынғы, орнату қалтасының ІШІНДЕ, ротациясыз
``debug.log`` — өндірістік орнатуда жазу рұқсаты болмас еді).
"""

import logging
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

from core.logging_setup import configure_rotating_logger, get_log_directory
from core.version import __version__

# Барлық модуль осы ДӘЛ СОЛ логгер атын қолданады ("apl.trace") — жалғыз
# rotating file handler осында, бір рет, қосылады.
trace_logger = configure_rotating_logger("apl.trace")
trace_logger.setLevel(logging.DEBUG)
trace_logger.propagate = False

_console_handler = logging.StreamHandler(sys.stdout)
_console_handler.setFormatter(logging.Formatter("[TRACE] %(message)s"))
trace_logger.addHandler(_console_handler)


def _log_uncaught_exception(exc_type, exc_value, exc_tb) -> None:
    """16. Кез келген ұсталмаған exception-ды — Qt слот ІШІНДЕ шыққанын
    да қоса (PySide6 мұндайды әдепкі бойынша ЕШҚАШАН қолданбаны толық
    тоқтатпайды, тек stderr-ге басып, event loop-ты жалғастыра береді,
    сондықтан "батырма басса ешнәрсе болмайды" сияқты симптом консольсіз
    байқалмай қалуы мүмкін) — "apl.trace" логгерінің rotating файл
    handler-іне толық traceback-пен жазады. Консольге шығу ЕШҚАШАН
    өзгертілмейді (``sys.__excepthook__``
    әлі де шақырылады).
    """
    message = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    trace_logger.critical("UNCAUGHT EXCEPTION:\n%s", message)
    sys.__excepthook__(exc_type, exc_value, exc_tb)


sys.excepthook = _log_uncaught_exception

# 1-4. Қолданба іске қосылуы, cwd, executable/interpreter жолдары —
# кез келген ықтимал "стейл build/басқа checkout" сценарийін дереу
# анықтау үшін.
trace_logger.info("=== APPLICATION STARTUP ===")
trace_logger.info("0. Arduino Physics Lab version: %s", __version__)
trace_logger.info("1. Startup at %s", datetime.now().isoformat(timespec="seconds"))
trace_logger.info("2. Current working directory: %s", os.getcwd())
trace_logger.info("3. Script path (__file__): %s", Path(__file__).resolve())
trace_logger.info("4. Python executable: %s", sys.executable)
trace_logger.info("   Python version: %s", sys.version)
trace_logger.info("   sys.argv: %s", sys.argv)
trace_logger.info("5. Log directory: %s", get_log_directory())
trace_logger.info("   frozen (PyInstaller): %s", getattr(sys, "frozen", False))

from app import run

if __name__ == "__main__":
    sys.exit(run())
