"""question_bank_seed — статик каталогтың (``ModuleRegistry``) бұрыннан
бар сұрақтарын бір реттік, ЕШҚАШАН жойылмайтын (non-destructive) түрде
``IQuestionRepository``-ге көшіреді (Phase 20).

Неге керек: сұрақтар ӘЗІРГЕ (Phase 20-ға дейін) тек Python коды ретінде
(``modules/*/experiments_config.py``) сақталған, ешбір SQLite кестесі
жоқ. Question Bank-тың ӨЗІ (репозиторий) енді жалғыз ащы шындық
(single source of truth) болғанда, репозиторий БОС күйде іске қосылса,
Мұғалім ЕШБІР сұрақ көрмейтін еді — бірақ студенттер ҚАЗІРГІ уақытта
ОСЫ статик сұрақтармен НАҚТЫ бағаланады. Сондықтан репозиторий
БІРІНШІ РЕТ (кез келген жол жоқ кезде) ашылғанда, статик каталог
сұрақтары дәл СОЛ ID-мен (``MultipleChoiceQuestion.id`` т.б.) көшіріледі
— § "Preserve existing data. No destructive migration."

Идемпотентті: репозиторийде КЕЗ КЕЛГЕН жол (тіпті мұрағатталған) болса,
ЕШБІР әрекет жасалмайды — Мұғалімнің кейінгі өңдеу/өшіру әрекеттері
ешқашан қайта жазылмайды.
"""

from __future__ import annotations

from datetime import datetime, timezone

from domain.entities.question_record import QuestionRecord
from domain.entities.user_role import UserRole
from domain.interfaces.i_question_repository import IQuestionRepository
from modules.module_registry import ModuleRegistry


def seed_questions_from_catalog(
    question_repository: IQuestionRepository, module_registry: ModuleRegistry
) -> None:
    if question_repository.list_all(include_archived=True):
        return

    now = datetime.now(timezone.utc)
    for module in module_registry.get_all():
        for experiment in module.get_experiments():
            if experiment.assessment is None:
                continue
            levels = (
                (1, experiment.assessment.level1_questions),
                (2, experiment.assessment.level2_questions),
                (3, experiment.assessment.level3_questions),
            )
            for level, questions in levels:
                for question in questions:
                    question_repository.create(
                        QuestionRecord(
                            id=question.id,
                            experiment_id=experiment.id,
                            level=level,
                            question=question,
                            is_active=True,
                            created_at=now,
                        ),
                        UserRole.TEACHER,
                    )
