"""experiment_assessment — тәжірибенің үш деңгейлі кері байланыс
(педагогикалық бағалау) СҰРАҚТАРЫНЫҢ конфигурациясы (Phase 39A).

Бұл модуль ``ExperimentGuide``/``ExperimentReport``-пен БІРДЕЙ конвенция:
frozen dataclass + ``validate()`` (ешбір exception орындау уақытында
шықпайды, тек түсінікті қате хабарламалар тізімі). Бұл жерде тек
СҰРАҚТАР (конфигурация) сақталады — студенттің НАҚТЫ жауаптары мен
бағасы ``domain.entities.experiment_feedback_result`` модулінде, мүлде
бөлек (runtime дерек, experiment конфигурациясы ЕМЕС).
"""

from __future__ import annotations

from dataclasses import dataclass, field

_MIN_OPTIONS = 2


@dataclass(frozen=True)
class MultipleChoiceQuestion:
    """1-деңгей (Тест) сұрағы — бір ғана дұрыс жауабы бар."""

    id: str
    prompt: str
    options: tuple[str, ...]
    correct_option_index: int
    points: int = 1

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.id:
            errors.append("MultipleChoiceQuestion.id бос болмауы керек")
        if not self.prompt:
            errors.append(f"MultipleChoiceQuestion({self.id}).prompt бос болмауы керек")
        if len(self.options) < _MIN_OPTIONS:
            errors.append(
                f"MultipleChoiceQuestion({self.id}).options кемінде {_MIN_OPTIONS} нұсқа болуы керек"
            )
        if not (0 <= self.correct_option_index < len(self.options)):
            errors.append(
                f"MultipleChoiceQuestion({self.id}).correct_option_index "
                f"options ауқымында болуы керек"
            )
        if self.points <= 0:
            errors.append(f"MultipleChoiceQuestion({self.id}).points оң сан болуы керек")
        return errors


@dataclass(frozen=True)
class OpenResponseQuestion:
    """2-деңгей (Талдау) — ашық жауапты, мұғалім тексеретін сұрақ."""

    id: str
    prompt: str

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.id:
            errors.append("OpenResponseQuestion.id бос болмауы керек")
        if not self.prompt:
            errors.append(f"OpenResponseQuestion({self.id}).prompt бос болмауы керек")
        return errors


@dataclass(frozen=True)
class ReflectionQuestion:
    """3-деңгей (Рефлексия) — өзін-өзі бағалауға арналған сұрақ."""

    id: str
    prompt: str

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.id:
            errors.append("ReflectionQuestion.id бос болмауы керек")
        if not self.prompt:
            errors.append(f"ReflectionQuestion({self.id}).prompt бос болмауы керек")
        return errors


@dataclass(frozen=True)
class ExperimentAssessmentDefinition:
    """Бір тәжірибенің толық үш деңгейлі кері байланыс конфигурациясы —
    ``ExperimentWorkspacePage``/``ExperimentFeedbackDialog``-тың дерек
    көзі. Сұрақтар ЕШҚАШАН виджет кодында hardcode етілмейді — тек осы
    жерден (``ExperimentDefinition.assessment``) оқылады.
    """

    level1_questions: tuple[MultipleChoiceQuestion, ...] = field(default_factory=tuple)
    level2_questions: tuple[OpenResponseQuestion, ...] = field(default_factory=tuple)
    level3_questions: tuple[ReflectionQuestion, ...] = field(default_factory=tuple)
    self_assessment_min: int = 1
    self_assessment_max: int = 5

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.level1_questions:
            errors.append("ExperimentAssessmentDefinition.level1_questions бос болмауы тиіс")

        seen_ids: set[str] = set()
        for question in (*self.level1_questions, *self.level2_questions, *self.level3_questions):
            if question.id in seen_ids:
                errors.append(f"'{question.id}' сұрақ ID-і бірнеше рет қайталанды")
            seen_ids.add(question.id)
            errors.extend(question.validate())

        if self.self_assessment_min >= self.self_assessment_max:
            errors.append(
                "ExperimentAssessmentDefinition.self_assessment_min "
                "self_assessment_max мәнінен кіші болуы керек"
            )
        return errors
