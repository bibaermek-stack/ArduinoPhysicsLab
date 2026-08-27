"""sync_auth — клиент жағының sync API кілтін конфигурациялау.

``domain/services/teacher_pin.py::_ENV_VAR_NAME``/``_DEFAULT_DEV_PIN``-
мен БІРДЕЙ established "opt-in env var + жергілікті әзірлеу әдепкісі"
конвенциясы, ``server/app/api/deps.py::get_configured_api_key()``-мен
ДӘЛ СӘЙКЕС мән беретін болу үшін (§10 "Never commit... API keys" —
кілт ешқашан қатты кодталмайды, тек орта айнымалысынан оқылады).
"""

from __future__ import annotations

import os

from core.deployment_config import load_deployment_config

_ENV_VAR_NAME = "APL_SYNC_API_KEY"
_DEV_DEFAULT_API_KEY = "dev-local-only-key"


def get_configured_sync_api_key() -> str:
    env_value = os.environ.get(_ENV_VAR_NAME, "").strip()
    if env_value:
        return env_value
    deployed = load_deployment_config().sync_api_key
    if deployed:
        return deployed
    return _DEV_DEFAULT_API_KEY
