"""experiment_feedback_result — студенттің НАҚТЫ жауаптары мен
мұғалімнің бағасы (runtime дерек, Phase 39A).

``domain.entities.experiment_assessment`` тек СҰРАҚТАРДЫ (конфигурация)
сақтайды — бұл модуль ЖАУАПТАРДЫ сақтайды, дәл ``Measurement``/
``ExperimentSession``-нің ``ExperimentDefinition``-нен бөлек болуымен
БІРДЕЙ себеппен (эксперимент конфигурациясы vs. сессия дерегі).

``TeacherAssessment`` әдейі ЖЕКЕ, ІШКІ (nested) объект ретінде сақталады
(``ExperimentFeedbackResult.teacher_assessment``) — Оқушы режиміне
арналған "қауіпсіз" нұсқасын жасау (``build_student_safe_result()``,
``domain/services/experiment_feedback_service.py``) тек осы БІР өрісті
``None``-ге ауыстырады, үш бөлек жалаң өріспен салыстырғанда әлдеқайда
қарапайым және сенімді.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

_TEACHER_SCORE_MIN = 0
_TEACHER_SCORE_MAX = 10


@dataclass(frozen=True)
class MultipleChoiceAnswer:
    """1-деңгей сұрағына студенттің таңдаған нұсқасы."""

    question_id: str
    selected_option_index: int


@dataclass(frozen=True)
class OpenResponseAnswer:
    """2-деңгей сұрағына студенттің ашық жауабы."""

    question_id: str
    response_text: str


@dataclass(frozen=True)
class ReflectionAnswer:
    """3-деңгей сұрағына студенттің рефлексиялық жауабы."""

    question_id: str
    response_text: str


@dataclass(frozen=True)
class TeacherAssessment:
    """Мұғалімнің бағасы — Оқушы режимінде ЕШҚАШАН көрсетілмеуі/
    сақталмауы тиіс (§ "Security and role enforcement").
    """

    score: int
    comment: str = ""
    reviewed: bool = True

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not (_TEACHER_SCORE_MIN <= self.score <= _TEACHER_SCORE_MAX):
            errors.append(
                f"TeacherAssessment.score {_TEACHER_SCORE_MIN}..{_TEACHER_SCORE_MAX} "
                "ауқымында болуы керек"
            )
        return errors


@dataclass(frozen=True)
class ExperimentFeedbackResult:
    """Бір сессияға (``session_id``) арналған толық кері байланыс
    жазбасы — жоба бойынша сессияға БІР ғана жазба (draft немесе
    submitted).
    """

    experiment_id: str
    session_id: str
    level1_answers: tuple[MultipleChoiceAnswer, ...] = field(default_factory=tuple)
    level1_score: int = 0
    level1_total: int = 0
    level1_percentage: float = 0.0
    level2_answers: tuple[OpenResponseAnswer, ...] = field(default_factory=tuple)
    level3_answers: tuple[ReflectionAnswer, ...] = field(default_factory=tuple)
    self_assessment: int | None = None
    is_draft: bool = True
    submitted_at: datetime | None = None
    teacher_assessment: TeacherAssessment | None = None

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.experiment_id:
            errors.append("ExperimentFeedbackResult.experiment_id бос болмауы керек")
        if not self.session_id:
            errors.append("ExperimentFeedbackResult.session_id бос болмауы керек")
        if self.level1_total > 0 and not (0 <= self.level1_score <= self.level1_total):
            errors.append(
                "ExperimentFeedbackResult.level1_score 0..level1_total ауқымында болуы керек"
            )
        if not (0.0 <= self.level1_percentage <= 100.0):
            errors.append("ExperimentFeedbackResult.level1_percentage 0..100 ауқымында болуы керек")
        if self.teacher_assessment is not None:
            errors.extend(self.teacher_assessment.validate())
        return errors
