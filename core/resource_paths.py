"""Даму (dev) және PyInstaller-мен пакеттелген (frozen) режимдер үшін
БІРДЕЙ, ЖАЛҒЫЗ ресурс-жол механизмі (Phase 9 — Production Deployment &
Release Readiness, § Part C "Resource Path Abstraction").

Бұрын ``Design/``/``ui/resources/images/`` сияқты жоба-түбірі ресурстарын
шақыратын әрбір файл ӨЗ ``Path(__file__).resolve().parents[N] / ...``
тізбегін қайталайтын (§ ``ui/widgets/sidebar.py``, ``ui/pages/role_
selection_page.py``, ``ui/pages/teacher_dashboard_page.py``, ``ui/widgets/
live_graph.py``, ``modules/electricity/experiments_config.py`` — барлығы
ДӘЛ БІРДЕЙ ``parents[2]`` заңдылығы). Бұл dev режимде жұмыс істейді, БІРАҚ
PyInstaller bundle ішінде ``__file__`` уақытша ``_MEIPASS`` қалтасына
бағытталады, ал сол жердегі каталог құрылымы ``datas=`` арқылы ЖЕКЕ
қосылған файлдармен ғана шектеледі — сондықтан scatter-тілген
``parents[N]`` тізбектері пакеттелген қолданбада бұзылады.

``resource_path()`` осы екі режимді бір жерде ажыратады: ``sys.frozen``
ақиқат болса (PyInstaller орнатады, § onedir және onefile екеуінде де)
``sys._MEIPASS``-тен, әйтпесе осы файлдың ӨЗ орналасуынан жоба түбірін
есептейді — шақырушы файл dev режимде ҚАЙ терең деңгейде жатқанына
ЕШҚАШАН тәуелді емес (§ бұрынғы ``parents[2]``-нің үзілуі мүмкін —
файл жылжытылса терендік те өзгереді; енді бір орталық функция).
"""

from __future__ import annotations

import sys
from pathlib import Path


def _project_root() -> Path:
    """Dev режимде — жоба түбірі (осы файл ``core/resource_paths.py``,
    сондықтан бір деңгей жоғары). Frozen режимде — ``sys._MEIPASS``
    (PyInstaller-дың ``datas=`` арқылы қосылған файлдарды осы жерге
    орналастыратын қалтасы, § onedir-де де, onefile-де де орнатылады)."""
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        # § қорғаныс: теориялық жағдай (frozen, БІРАҚ _MEIPASS жоқ) —
        # exe-мен БІРДЕЙ қалта (onedir bundle root-ы).
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_path(*parts: str) -> Path:
    """Жоба түбіріне қатысты ресурс жолын қайтарады — dev режимде НАҚТЫ
    файлдық жүйедегі, frozen режимде bundle ішіндегі орналасу. Мысалы:
    ``resource_path("Design", "02_FluentIcons", "svg")``."""
    return _project_root().joinpath(*parts)
