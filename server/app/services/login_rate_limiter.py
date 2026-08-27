"""login_rate_limiter — teacher/student login endpoint-теріне PIN/access-code
брутфорс шабуылынан қорғаныс (§ security audit "Login endpoints have no
rate-limiting").

Дизайн: identity (``"teacher:<sync_id>"``/``"student:<sync_id>"``) бойынша
ТЕК СӘТСІЗ әрекеттер саналады (§ дұрыс PIN-мен қайталап кіру ешқашан
блокталмауы тиіс). ``_MAX_ATTEMPTS``-тен асқанда identity ``_LOCKOUT_SECONDS``
уақытына құлыпталады, сәтті логин есептегішті дереу тазалайды.

Жады-ішінде (in-memory), процесс деңгейінде — бір ``uvicorn`` процесіне
жеткілікті (§ ``docs/deployment.md`` — ``--workers`` МҮЛДЕ көрсетілмеген,
бір процесс деп құжатталған). Көп-процесс/көп-instance деплойда бөлек
ортақ store (Redis және т.б.) қажет болар еді — бұл ЖОБАНЫҢ қазіргі
ауқымынан тыс (§ "avoid premature infra complexity", ``sync_backoff.py``-
дегі "fixed schedule, deliberately simple" конвенциясымен БІРДЕЙ рух).
"""

from __future__ import annotations

import time
from collections import defaultdict

_MAX_ATTEMPTS = 5
_LOCKOUT_SECONDS = 300.0  # 5 минут

_failed_attempts: dict[str, list[float]] = defaultdict(list)
_locked_until: dict[str, float] = {}


def is_locked(identity: str) -> bool:
    """``identity`` ағымда құлыпталған болса ``True`` қайтарады."""
    locked_until = _locked_until.get(identity)
    if locked_until is None:
        return False
    if time.monotonic() >= locked_until:
        # Құлып мерзімі өткен — тазалау (§ "unlock automatically", ешбір
        # admin әрекеті қажет емес).
        _locked_until.pop(identity, None)
        _failed_attempts.pop(identity, None)
        return False
    return True


def record_failure(identity: str) -> None:
    """Сәтсіз әрекетті тіркейді, ``_MAX_ATTEMPTS``-тен асса құлыптайды."""
    now = time.monotonic()
    attempts = _failed_attempts[identity]
    cutoff = now - _LOCKOUT_SECONDS
    attempts[:] = [t for t in attempts if t > cutoff]
    attempts.append(now)
    if len(attempts) >= _MAX_ATTEMPTS:
        _locked_until[identity] = now + _LOCKOUT_SECONDS


def record_success(identity: str) -> None:
    """Сәтті логин — сол identity үшін сәтсіз әрекет тарихын тазалайды."""
    _failed_attempts.pop(identity, None)
    _locked_until.pop(identity, None)


def reset_all() -> None:
    """Тек тесттер үшін — модуль-деңгейлік күйді толық тазалайды."""
    _failed_attempts.clear()
    _locked_until.clear()
