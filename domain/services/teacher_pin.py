"""teacher_pin — Мұғалім PIN хэштеу/тексеру негізгі функциялары
(Phase 37A), Multi-Teacher Accounts фазасында КӨП мұғалімнің әрқайсысы
өз ``pin_hash``-ымен пайдаланады (§ ``resolve_teacher_by_pin()``).

PIN мәтіні ЕШҚАШАН сақталмайды/салыстырылмайды — тек SHA-256 хэші
(``hash_pin``), ``hmac.compare_digest`` арқылы тұрақты-уақытты салыстыру
(``verify_pin``).

``_DEFAULT_DEV_PIN``/``get_configured_pin_hash()``/``APL_TEACHER_PIN``
ЕНДІ тек ЕСКІ, бір-мұғалімдік конфигурацияның артефактісі — Multi-
Teacher Accounts фазасының миграциясы (§ ``domain/services/
teacher_migration.py::backfill_default_teacher()``) осыны БІР РЕТ
дефолт ``Teacher`` жазбасына айналдыру үшін қолданады (§ "Do NOT
simply destroy it... create/migrate a default teacher account safely"),
содан кейін нақты аутентификация толығымен ``teachers`` кестесіндегі
жеке ``pin_hash``-тар арқылы жүреді.
"""

import hashlib
import hmac
import os

from domain.entities.teacher import Teacher
from domain.interfaces.i_teacher_repository import ITeacherRepository

_DEFAULT_DEV_PIN = "1234"
_ENV_VAR_NAME = "APL_TEACHER_PIN"


def hash_pin(pin: str) -> str:
    """PIN мәтінінің SHA-256 hex дайджестін қайтарады."""
    return hashlib.sha256(pin.encode("utf-8")).hexdigest()


def get_configured_pin_hash() -> str:
    """Ағымдағы конфигурацияланған (``APL_TEACHER_PIN`` немесе әдепкі
    dev PIN) PIN-нің хэшін қайтарады. § ЕСКІ бір-мұғалімдік конфигурация
    — тек ``backfill_default_teacher()`` миграциясы үшін қалдырылған.
    """
    pin = os.environ.get(_ENV_VAR_NAME) or _DEFAULT_DEV_PIN
    return hash_pin(pin)


def verify_pin(entered_pin: str, expected_hash: str) -> bool:
    """Енгізілген PIN хэші ``expected_hash``-пен сәйкес келсе ``True``."""
    return hmac.compare_digest(hash_pin(entered_pin), expected_hash)


def resolve_teacher_by_pin(entered_pin: str, teacher_repository: ITeacherRepository) -> Teacher | None:
    """Енгізілген PIN-ге сәйкес БЕЛСЕНДІ мұғалімді іздейді (§ "Application
    searches teacher accounts... PIN identifies teacher"). Тек белсенді
    мұғалімдер арасында ізделеді (§ "disabled teacher PIN must no longer
    allow login") — ``hmac.compare_digest`` арқылы тұрақты-уақытты
    салыстыру әр жазба үшін (уақыт негізді есеп жүргізуден қорғау,
    "PIN коды қате" хабарламасы қай себеппен сәтсіз болғанын ЕШҚАШАН
    ашпайды).
    """
    entered_hash = hash_pin(entered_pin)
    for teacher in teacher_repository.list_active():
        if hmac.compare_digest(entered_hash, teacher.pin_hash):
            return teacher
    return None
