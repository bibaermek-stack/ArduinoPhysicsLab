"""Экспорт жазуын пайдаланушыға көрінетін ``ExportError``-ға орайды.

Бұрын CSV/Excel/PDF IO қатесі үнсіз ``False`` қайтаратын — UI тек
жалпы «сәтсіз» деген. График сурет экспорты ``capture_status`` арқылы
себебін көрсетеді; осы көмекші сол тәртіпті файл экспортына қолданады.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from core.exceptions import ExportError

_logger = logging.getLogger(__name__)


def write_export(output_path: str | Path, write_callback: Callable[[], None]) -> bool:
    """``write_callback`` сәтті аяқталса ``True``.

    Бос сессия сияқты домендік «жазуға ештеңе жоқ» жағдайы осында
    келмейді — шақырушы алдын ала ``False`` қайтарады. Диск/жол/рұқсат
    қатесі ``ExportError`` (қазақша себеп) ретінде шығады.
    """
    try:
        write_callback()
        return True
    except ExportError:
        raise
    except OSError as exc:
        _logger.warning("Экспорт жазуы сәтсіз: %s (%s)", output_path, exc)
        raise ExportError(f"Файлды жазу мүмкін болмады: {output_path} ({exc})") from exc
    except Exception as exc:
        _logger.warning("Экспорт қатесі: %s (%s)", output_path, exc)
        raise ExportError(f"Экспорт қатесі: {exc}") from exc
