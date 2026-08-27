"""Таратылатын (production) клиенттің сервер баптауы.

QSettings-те пайдаланушы әлі ештеңе сақтамағанда, пакеттелген ``.exe``
қасындағы ``deployment.json`` оқылады — әр алушының Windows тізілімін
қолмен өзгертудің қажеті жоқ.

Іздеу тәртібі (бірінші табылған файл жеңеді):

1. ``APL_DEPLOYMENT_CONFIG`` орта айнымалысы (тест/оператор override)
2. frozen: ``ArduinoPhysicsLab.exe``-мен БІР қалтадағы ``deployment.json``
3. frozen: PyInstaller ``_MEIPASS`` ішіндегі көшірме
4. dev: жоба түбіріндегі ``deployment.json``
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DeploymentConfig:
    sync_api_base_url: str = ""
    sync_enabled: bool | None = None
    sync_api_key: str = ""


def _candidate_paths() -> list[Path]:
    paths: list[Path] = []
    env_path = os.environ.get("APL_DEPLOYMENT_CONFIG", "").strip()
    if env_path:
        return [Path(env_path)]
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            paths.append(Path(meipass) / "deployment.json")
        paths.append(Path(sys.executable).resolve().parent / "deployment.json")
    else:
        paths.append(Path(__file__).resolve().parent.parent / "deployment.json")
    return paths


def _from_mapping(data: dict) -> DeploymentConfig:
    url = str(data.get("sync_api_base_url") or "").strip()
    api_key = str(data.get("sync_api_key") or "").strip()
    raw_enabled = data.get("sync_enabled", None)
    enabled: bool | None
    if isinstance(raw_enabled, bool):
        enabled = raw_enabled
    elif raw_enabled is None or raw_enabled == "":
        enabled = None
    else:
        enabled = str(raw_enabled).strip().lower() in ("true", "1", "yes")
    return DeploymentConfig(
        sync_api_base_url=url,
        sync_enabled=enabled,
        sync_api_key=api_key,
    )


def load_deployment_config() -> DeploymentConfig:
    """Бірінші оқылатын жарамды ``deployment.json``. Файл жоқ/бұзық
    болса — бос әдепкі (кодтағы localhost / sync-off сақталады)."""
    for path in _candidate_paths():
        if not path.is_file():
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if not isinstance(raw, dict):
            continue
        return _from_mapping(raw)
    return DeploymentConfig()
