"""experiment_feedback_service — Кері байланыс/бағалау есептеулерінің
жалғыз, эксперименттен ТӘУЕЛСІЗ (генерик) domain сервисі (Phase 39A).

``domain.services.experiment_conclusion``-мен БІРДЕЙ принцип: таза
функциялар, Qt жоқ, ешбір экспериментке hardcode тәуелділік жоқ.

Мұғалім бағасын сақтау/өзгерту әрекеті ТЕК осы модуль арқылы өтеді —
``apply_teacher_assessment()`` рөлді нақты тексереді (``PermissionError``)
және бұл тексеру виджет/UI деңгейінде ЕМЕС, domain шекарасында орындалады
(§ "Security and role enforcement": "must be protected at the action/
domain boundary, not only hidden visually").
"""

from __future__ import annotations

import dataclasses

from domain.entities.experiment_assessment import ExperimentAssessmentDefinition
from domain.entities.experiment_feedback_result import (
    ExperimentFeedbackResult,
    MultipleChoiceAnswer,
    TeacherAssessment,
)
from domain.entities.user_role import UserRole


def score_level1(
    assessment: ExperimentAssessmentDefinition,
    answers: tuple[MultipleChoiceAnswer, ...],
) -> tuple[int, int, float]:
    """1-деңгей (Тест) нәтижесін есептейді: ``(score, total, percentage)``.

    ``total`` — ``level1_questions`` ішіндегі сұрақ саны (points ЕМЕС —
    әр сұрақ бірлік ретінде саналады, спецификацияның "1 point per
    correct answer" талабына сай). Жауап жоқ немесе сұрақ табылмаса,
    сол сұрақ қате деп есептеледі (жалған "дұрыс" ЕШҚАШАН берілмейді).
    """
    answers_by_question = {answer.question_id: answer for answer in answers}
    total = len(assessment.level1_questions)
    score = 0
    for question in assessment.level1_questions:
        answer = answers_by_question.get(question.id)
        if answer is not None and answer.selected_option_index == question.correct_option_index:
            score += 1

    percentage = (score / total * 100.0) if total > 0 else 0.0
    return score, total, percentage


def build_student_safe_result(result: ExperimentFeedbackResult) -> ExperimentFeedbackResult:
    """Оқушы режиміне арналған көшірмені қайтарады — ``teacher_assessment``
    ЕШҚАШАН осы нәтижеде болмайды (тек виджетте жасырылу ЕМЕС, дерек
    деңгейінде мүлде жоқ).
    """
    return dataclasses.replace(result, teacher_assessment=None)


def apply_teacher_assessment(
    result: ExperimentFeedbackResult,
    teacher_assessment: TeacherAssessment,
    role: UserRole,
) -> ExperimentFeedbackResult:
    """Мұғалімнің бағасын нәтижеге қосады. ``role`` міндетті түрде
    ``UserRole.TEACHER`` болуы керек — Оқушы режимінен келген тікелей
    шақыру ``PermissionError`` арқылы бас тартылады (UI-де батырма
    жасырылуына ТӘУЕЛСІЗ, дербес қорғаныс сызығы).
    """
    if role is not UserRole.TEACHER:
        raise PermissionError(
            "Мұғалім бағасын тек Мұғалім режимінде сақтауға болады"
        )
    return dataclasses.replace(result, teacher_assessment=teacher_assessment)
