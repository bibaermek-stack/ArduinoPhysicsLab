"""QuestionRecord — Question Bank-та (Phase 20) сақталатын БІР сұрақтың
персистенция-деңгейлік көрінісі.

Сұрақтың ӨЗІ (мәтін/нұсқалар/дұрыс жауап) ЕШҚАШАН қайта анықталмайды —
``domain.entities.experiment_assessment``-тегі ҮШ бұрыннан бар тип
(``MultipleChoiceQuestion``/``OpenResponseQuestion``/``ReflectionQuestion``)
СОЛ ҚАЛПЫ қайта пайдаланылады (§ "The Question Bank must reuse the same
underlying questions that the student workflow uses"). Бұл жазба тек
СОЛ типтердің қайсысы (``level`` арқылы), қай тәжірибеге жататыны
(``experiment_id``), белсенді/мұрағатталған күйі мен жасалу уақытын
қосады — persistence/сүзгі/сұрыптау үшін қажет, бірақ сұрақ мазмұнына
жат емес метадеректер.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from domain.entities.experiment_assessment import (
    MultipleChoiceQuestion,
    OpenResponseQuestion,
    ReflectionQuestion,
)

QuestionContent = MultipleChoiceQuestion | OpenResponseQuestion | ReflectionQuestion

LEVEL_MULTIPLE_CHOICE = 1
LEVEL_OPEN_RESPONSE = 2
LEVEL_REFLECTION = 3
VALID_LEVELS: tuple[int, ...] = (LEVEL_MULTIPLE_CHOICE, LEVEL_OPEN_RESPONSE, LEVEL_REFLECTION)


@dataclass(frozen=True)
class QuestionRecord:
    """Бір персистентелген сұрақ жолы. ``is_active=False`` — soft-delete/
    мұрағат (§ "If historical student answers reference question IDs and
    deletion would corrupt old work: DO NOT hard-delete") — ``Classroom``/
    ``Student``-тің ``is_archived`` конвенциясымен БІРДЕЙ рух, тек атауы
    осы доменге сай ("белсенді сұрақ" ұғымына тікелей сәйкес келеді).
    """

    id: str
    experiment_id: str
    level: int
    question: QuestionContent
    is_active: bool
    created_at: datetime

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.id:
            errors.append("QuestionRecord.id бос болмауы керек")
        if not self.experiment_id:
            errors.append("QuestionRecord.experiment_id бос болмауы керек")
        if self.level not in VALID_LEVELS:
            errors.append("QuestionRecord.level 1, 2 немесе 3 болуы керек")
        errors.extend(self.question.validate())
        return errors
