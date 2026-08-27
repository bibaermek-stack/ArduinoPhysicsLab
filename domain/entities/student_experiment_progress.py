"""StudentExperimentProgress — бір оқушының бір тәжірибе бойынша
есептелген (ЕШҚАШАН сақталмайтын) прогресс күйі (Phase 39B).

``ProgressStatus`` НАҚТЫ сақталған жазбалардан (``session_student_link``/
``ISessionRepository``/``IFeedbackRepository``) шығарылады —
``derive_status()`` УИ-ден тыс, домен деңгейінде, дербес тестіленеді
(§ "Do not allow UI code to invent status independently").
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from domain.entities.experiment_feedback_result import ExperimentFeedbackResult


class ProgressStatus(Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    MEASUREMENT_COMPLETED = "measurement_completed"
    REPORT_COMPLETED = "report_completed"
    FEEDBACK_SUBMITTED = "feedback_submitted"
    REVIEWED = "reviewed"


@dataclass(frozen=True)
class StudentExperimentProgress:
    """Бір ``(student_id, experiment_id)`` жұбына арналған қорытынды
    күй-презентациясы — тек оқу-моделі, ешбір жеке кесте/жол ретінде
    сақталмайды (``IStudentProgressRepository.get_progress()`` осы
    объектіні ӘРҚАШАН жаңадан құрастырады).
    """

    student_id: str
    experiment_id: str
    status: ProgressStatus
    latest_session_id: str | None = None
    measurement_count: int = 0
    report_opened: bool = False
    level1_score: int | None = None
    level1_total: int | None = None
    level1_percentage: float | None = None
    self_assessment: int | None = None
    teacher_score: int | None = None
    teacher_reviewed: bool = False
    last_activity_at: datetime | None = None
    submitted_at: datetime | None = None


def derive_status(
    has_link: bool,
    measurement_count: int,
    feedback_result: ExperimentFeedbackResult | None,
) -> ProgressStatus:
    """Прогресс күйін НАҚТЫ дерек негізінде есептейді (жалған "аяқталу"
    ешқашан ойдан шығарылмайды):

    - Сессия байланысы жоқ -> НЕ БАСТАЛҒАН.
    - Байланыс бар, бірақ 0 өлшеу -> ӨЛШЕУ ЖҮРІП ЖАТЫР.
    - >=1 өлшеу, кері байланыс жазбасы мүлде жоқ -> ӨЛШЕУ АЯҚТАЛДЫ.
    - Кері байланыс жазбасы бар, ``is_draft=True`` -> ЕСЕП АШЫЛДЫ (жоба
      сатысы — есеп/кері байланыс диалогы кемінде бір рет ашылған).
    - ``is_draft=False`` (жіберілген), мұғалім бағасы жоқ -> КЕРІ БАЙЛАНЫС
      ЖІБЕРІЛДІ.
    - ``teacher_assessment is not None`` -> ТЕКСЕРІЛДІ.
    """
    if not has_link:
        return ProgressStatus.NOT_STARTED
    if measurement_count == 0:
        return ProgressStatus.IN_PROGRESS
    if feedback_result is None:
        return ProgressStatus.MEASUREMENT_COMPLETED
    if feedback_result.is_draft:
        return ProgressStatus.REPORT_COMPLETED
    if feedback_result.teacher_assessment is not None:
        return ProgressStatus.REVIEWED
    return ProgressStatus.FEEDBACK_SUBMITTED
