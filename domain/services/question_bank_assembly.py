"""question_bank_assembly — персистентелген ``QuestionRecord`` жиынын
студент-workflow-дың дерек көзі (``ExperimentAssessmentDefinition``)
пішініне жинайтын таза функция (Phase 20).

``ExperimentWorkspacePage``-тің ЖАЛҒЫЗ шақырушысы — ``list_for_experiment()``
нәтижесін (белсенді сұрақтар) ``ExperimentFeedbackDialog``-қа берілетін
объектіге түрлендіреді. Сұрақ репозиторийінде ЖОҚ тәжірибе үшін статик
каталог анықтамасы (``fallback``) ӨЗГЕРІССІЗ қайтарылады — § "reuse the
same questions" ЕШБІР жаңа мінез-құлықты бұрыннан бар (репозиторийде әлі
өңделмеген) тәжірибелерге мәжбүрлемейді.
"""

from __future__ import annotations

from domain.entities.experiment_assessment import ExperimentAssessmentDefinition
from domain.entities.question_record import QuestionRecord


def build_assessment_definition(
    records: tuple[QuestionRecord, ...],
    fallback: ExperimentAssessmentDefinition | None,
) -> ExperimentAssessmentDefinition | None:
    """``records`` (бір тәжірибенің, ӘДЕТТЕ ТЕК белсенді сұрақтары) бос
    болса — ``fallback`` (статик каталог анықтамасы, ``None`` болуы
    мүмкін) өзгеріссіз қайтарылады. Бос болмаса, репозиторий сұрақтары
    деңгей бойынша топтастырылып, ЖАҢА ``ExperimentAssessmentDefinition``
    құрылады — ``self_assessment_min/max`` тек ``fallback``-тан
    мұраланады (Question Bank бұл өрістерді өзгертпейді, § "reflection
    self-assessment scale is not a per-question field").
    """
    if not records:
        return fallback

    level1 = tuple(record.question for record in records if record.level == 1)
    level2 = tuple(record.question for record in records if record.level == 2)
    level3 = tuple(record.question for record in records if record.level == 3)

    self_assessment_min = fallback.self_assessment_min if fallback is not None else 1
    self_assessment_max = fallback.self_assessment_max if fallback is not None else 5

    return ExperimentAssessmentDefinition(
        level1_questions=level1,
        level2_questions=level2,
        level3_questions=level3,
        self_assessment_min=self_assessment_min,
        self_assessment_max=self_assessment_max,
    )
