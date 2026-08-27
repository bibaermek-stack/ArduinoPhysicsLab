"""learning_analytics — Phase 8 (Advanced Analytics & Learning Progress)
per-student topic performance + teacher alert read-model service.

Таза Python — ЕШБІР Qt тәуелділігі жоқ (§ ``domain/services/teacher_
monitoring.py`` докстрингіндегі БІРДЕЙ ұстаным: "UI-widget-ке күрделі
агрегация логикасын тікелей салмау"). Бұл модуль ЕШБІР жаңа кесте/баған
иеленбейді — тек Phase 1-7-де ӘЛДЕҚАШАН синхрондалған жазбаларды
(``IStudentProgressRepository``/``IStudentRepository``/``IClassroomRepository``/
``ISessionRepository``) оқып, ЖАҢА "мұғалімге көрсетуге дайын" оқу-моделін
құрастырады (§ Phase 8 Architecture Decision).

§3 "weak/strong topic — score-based proxy, ХАЛАЛ (honest) ескерту": бұл
модуль ЕШҚАШАН нақты концепт-деңгейлі диагностика жасамайды — тек
``teacher_score`` (0-10, ``ProgressStatus.REVIEWED`` кезінде) немесе,
ол әлі жоқ болса, ``level1_percentage``-ті 0-10 шкаласына масштабтап
пайдаланады (§ ``StudentExperimentProgress`` докстрингі — бұл өрістер
Phase 39B-ден бері бар, БІРАҚ Phase 8-ге дейін еш жерде оқылмаған).
Шынайы сұрақ/концепт-деңгейлі талдау ``questions`` кестесіне ``topic``
бағанын қосуды талап етер еді (§ докстрингінде әрі қарай "Explicitly
deferred" туралы ескерту, ЖОҚ, Phase 8 бұл схема өзгерісін жасамайды).

§4 "laboratory completion statistics — completed/attempted, ЕШҚАШАН
/enrolled": доменде "тағайындау" (assignment) ұғымы ЖОҚ (§ ``domain/
entities/classroom_activity_snapshot.py`` докстрингіндегі БІРДЕЙ ескерту)
— толу деңгейі ӘРҚАШАН "осы тәжірибені БАСТАҒАН оқушылардың қаншасы
аяқтады", ешқашан "барлық тізімдегі оқушыға қатысты" пайыз емес.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from domain.entities.learning_analytics import (
    AlertKind,
    StudentLearningProgress,
    TeacherAlert,
    TopicPerformance,
    TopicPerformanceLevel,
)
from domain.entities.measurement import Measurement
from domain.entities.student_experiment_progress import ProgressStatus, StudentExperimentProgress
from domain.interfaces.i_classroom_repository import IClassroomRepository
from domain.interfaces.i_session_repository import ISessionRepository
from domain.interfaces.i_student_repository import IStudentRepository
from domain.services.graph_analysis import RegionStatistics, compute_region_statistics
from modules.module_registry import ModuleRegistry

# § ``AnalyticsPage._COMPLETED_STATUSES``-пен ДӘЛ БІРДЕЙ жиын (§ "Reuse
# canonical domain status logic" — Phase 8 ӨЗ, екінші "аяқталды"
# анықтамасын ойлап шығармайды).
_COMPLETED_STATUSES = frozenset(
    {
        ProgressStatus.MEASUREMENT_COMPLETED,
        ProgressStatus.REPORT_COMPLETED,
        ProgressStatus.FEEDBACK_SUBMITTED,
        ProgressStatus.REVIEWED,
    }
)

# § 0-10 шкаласы (``AnalyticsPage._SCORE_AXIS_MAX``-пен БІРДЕЙ, "Scores
# should remain on the existing 0-10 grading scale").
DEFAULT_WEAK_THRESHOLD = 5.0
DEFAULT_STRONG_THRESHOLD = 8.0
# § "one missed tick tolerance"-ке ұқсас рух — қысқа кідіріс ЕШҚАШАН
# "мерзімі өткен" деп фабрикацияланбайды, тек шынымен ұзақ үзіліс.
DEFAULT_OVERDUE_DAYS = 7
DEFAULT_LOW_SCORE_THRESHOLD = DEFAULT_WEAK_THRESHOLD
DEFAULT_AWAITING_REVIEW_DAYS = 3


def resolve_channel_value(measurement: Measurement, channel_key: str) -> float | None:
    """§7a "power not always a derived value" — ``"power"`` кейбір
    тәжірибелерде (Ohm's Law/metal-resistance-temperature) ``derived_
    values``-те ЖОҚ (§ ``formulas`` тізімінде тек ``"resistance"``
    болғандықтан). ``CalculationEngine._calculate_power``-мен ДӘЛ БІРДЕЙ
    формула (``P = U × I``) осында ЖАҢАДАН есептеледі, ТЕК Analytics
    КӨРСЕТУ үшін — ``Measurement.derived_values``-ты ЕШҚАШАН мутациаламайды
    (жаңа мән ешбір сақталған жазбаға ЕШҚАШАН жазылмайды)."""
    value = measurement.get_value(channel_key)
    if value is not None:
        return value
    if channel_key == "power":
        voltage = measurement.get_value("voltage")
        current = measurement.get_value("current")
        if voltage is not None and current is not None:
            return voltage * current
    return None


def compute_channel_trend(
    session_repository: ISessionRepository, session_ids: tuple[str, ...], channel_key: str
) -> RegionStatistics:
    """§ "measurement analytics using existing voltage/current data" —
    оқушының БІРНЕШЕ тәжірибе әрекеті (session) бойынша пулдалған
    (pooled) арна мәндерінің min/max/avg/std статистикасы. Жіңішке
    орауыш қана (§ "a thin wrapper, not new math") — нақты есептеу
    толығымен ``graph_analysis.compute_region_statistics()``-те, бос
    тізім үшін де НАҚТЫ ``n=0``/``None`` қайтарады (§ ЕШҚАШАН жалған
    нөл фабрикацияламайды)."""
    values: list[float] = []
    for session_id in session_ids:
        for measurement in session_repository.get_measurements(session_id):
            value = resolve_channel_value(measurement, channel_key)
            if value is not None:
                values.append(value)
    return compute_region_statistics(values)


def _resolve_score(progress: StudentExperimentProgress) -> float | None:
    """§3 докстрингі — ``teacher_score`` (0-10, ``REVIEWED``) БАСЫМ, ол
    жоқ болса ``level1_percentage`` (0-100) 0-10 шкаласына масштабталады."""
    if progress.teacher_score is not None:
        return float(progress.teacher_score)
    if progress.level1_percentage is not None:
        return progress.level1_percentage / 10.0
    return None


def _classify(
    average_score: float | None, weak_threshold: float, strong_threshold: float
) -> TopicPerformanceLevel:
    if average_score is None:
        return TopicPerformanceLevel.NEUTRAL
    if average_score < weak_threshold:
        return TopicPerformanceLevel.WEAK
    if average_score >= strong_threshold:
        return TopicPerformanceLevel.STRONG
    return TopicPerformanceLevel.NEUTRAL


def _module_name_for_experiment(module_registry: ModuleRegistry, experiment_id: str) -> str:
    for module in module_registry.get_all():
        for experiment in module.get_experiments():
            if experiment.id == experiment_id:
                return module.get_name()
    return "—"


def _experiment_title(module_registry: ModuleRegistry, experiment_id: str) -> str:
    for module in module_registry.get_all():
        for experiment in module.get_experiments():
            if experiment.id == experiment_id:
                return experiment.title
    return experiment_id


def compute_students_learning_progress(
    progress_list: tuple[StudentExperimentProgress, ...],
    *,
    student_repository: IStudentRepository,
    classroom_repository: IClassroomRepository,
    module_registry: ModuleRegistry,
    weak_threshold: float = DEFAULT_WEAK_THRESHOLD,
    strong_threshold: float = DEFAULT_STRONG_THRESHOLD,
) -> tuple[StudentLearningProgress, ...]:
    """§ "Оқушылар бойынша үлгерім" кестесінің ЖАЛҒЫЗ дерек көзі.

    ``progress_list`` шақырушыдан келеді (§ ``IStudentProgressRepository.
    list_all_progress(allowed_classroom_ids)`` — АЛДЫН АЛА бір рет
    сұралған, § "Avoid duplicate repository queries", ``AnalyticsPage``-
    тің ӨЗ established конвенциясымен БІРДЕЙ). ``ProgressStatus.NOT_
    STARTED`` бұл тізімде ЕШҚАШАН болмайды (§ ``list_all_progress()``
    докстрингі), сондықтан бұл функция да оны ЕШҚАШАН қоспайды.
    """
    by_student: dict[str, list[StudentExperimentProgress]] = {}
    for progress in progress_list:
        by_student.setdefault(progress.student_id, []).append(progress)

    results: list[StudentLearningProgress] = []
    for student_id, entries in by_student.items():
        student = student_repository.get(student_id)
        if student is None:
            continue
        classroom = classroom_repository.get(student.classroom_id)
        classroom_name = classroom.name if classroom is not None else "—"

        topics: list[TopicPerformance] = []
        for progress in entries:
            score = _resolve_score(progress)
            topics.append(
                TopicPerformance(
                    experiment_id=progress.experiment_id,
                    experiment_title=_experiment_title(module_registry, progress.experiment_id),
                    module_name=_module_name_for_experiment(module_registry, progress.experiment_id),
                    attempted_count=1,
                    completed_count=1 if progress.status in _COMPLETED_STATUSES else 0,
                    reviewed_count=1 if progress.status is ProgressStatus.REVIEWED else 0,
                    average_score=score,
                    completion_rate=1.0 if progress.status in _COMPLETED_STATUSES else 0.0,
                    level=_classify(score, weak_threshold, strong_threshold),
                )
            )

        scored_topics = [t for t in topics if t.average_score is not None]
        overall_average = (
            sum(t.average_score for t in scored_topics) / len(scored_topics)
            if scored_topics
            else None
        )
        overall_completion_rate = (
            sum(1 for t in topics if t.completed_count > 0) / len(topics) if topics else None
        )
        weakest = min(scored_topics, key=lambda t: t.average_score) if scored_topics else None
        strongest = max(scored_topics, key=lambda t: t.average_score) if scored_topics else None

        results.append(
            StudentLearningProgress(
                student_id=student_id,
                student_name=student.display_name,
                classroom_id=student.classroom_id,
                classroom_name=classroom_name,
                topics=tuple(topics),
                overall_average_score=overall_average,
                overall_completion_rate=overall_completion_rate,
                weakest_topic=weakest,
                strongest_topic=strongest,
            )
        )
    return tuple(results)


def compute_teacher_alerts(
    progress_list: tuple[StudentExperimentProgress, ...],
    *,
    student_repository: IStudentRepository,
    classroom_repository: IClassroomRepository,
    module_registry: ModuleRegistry,
    now: datetime,
    overdue_days: int = DEFAULT_OVERDUE_DAYS,
    low_score_threshold: float = DEFAULT_LOW_SCORE_THRESHOLD,
    awaiting_review_days: int = DEFAULT_AWAITING_REVIEW_DAYS,
) -> tuple[TeacherAlert, ...]:
    """§5 "Dashboard alerts = a new pure function over existing progress
    data, zero new repository dependency" — үш ескерту түрі:

    - OVERDUE: ``IN_PROGRESS`` (өлшеу басталған, БІРАҚ 0 өлшеу — § ``derive_
      status()`` докстрингі) және ``last_activity_at`` ``overdue_days``-тен
      ескі. ``NOT_STARTED`` ЕШҚАШАН кірмейді (§ "тағайындау" ұғымы жоқ).
    - LOW_SCORE: ``REVIEWED`` және ``teacher_score < low_score_threshold``.
    - AWAITING_REVIEW_TOO_LONG: ``FEEDBACK_SUBMITTED`` және ``submitted_at``
      ``awaiting_review_days``-тен ескі.

    Ретсіз (unordered) tuple қайтарады — сұрыптау/топтастыру UI
    деңгейінде (§ "keep aggregation pure, presentation in the widget").
    """
    alerts: list[TeacherAlert] = []
    overdue_cutoff = now - timedelta(days=overdue_days)
    awaiting_cutoff = now - timedelta(days=awaiting_review_days)

    for progress in progress_list:
        student = student_repository.get(progress.student_id)
        if student is None:
            continue
        classroom = classroom_repository.get(student.classroom_id)
        classroom_id = classroom.id if classroom is not None else student.classroom_id
        classroom_name = classroom.name if classroom is not None else "—"
        experiment_title = _experiment_title(module_registry, progress.experiment_id)

        if (
            progress.status is ProgressStatus.IN_PROGRESS
            and progress.last_activity_at is not None
            and progress.last_activity_at < overdue_cutoff
        ):
            alerts.append(
                TeacherAlert(
                    kind=AlertKind.OVERDUE,
                    student_id=student.id,
                    student_name=student.display_name,
                    classroom_id=classroom_id,
                    classroom_name=classroom_name,
                    experiment_id=progress.experiment_id,
                    experiment_title=experiment_title,
                    message=f"«{experiment_title}» тәжірибесі {overdue_days} күннен астам уақыт өлшеусіз тұр",
                    since=progress.last_activity_at,
                )
            )

        if (
            progress.status is ProgressStatus.REVIEWED
            and progress.teacher_score is not None
            and progress.teacher_score < low_score_threshold
        ):
            alerts.append(
                TeacherAlert(
                    kind=AlertKind.LOW_SCORE,
                    student_id=student.id,
                    student_name=student.display_name,
                    classroom_id=classroom_id,
                    classroom_name=classroom_name,
                    experiment_id=progress.experiment_id,
                    experiment_title=experiment_title,
                    message=f"«{experiment_title}» бойынша төмен баға: {progress.teacher_score}/10",
                    since=progress.submitted_at,
                )
            )

        if (
            progress.status is ProgressStatus.FEEDBACK_SUBMITTED
            and progress.submitted_at is not None
            and progress.submitted_at < awaiting_cutoff
        ):
            alerts.append(
                TeacherAlert(
                    kind=AlertKind.AWAITING_REVIEW_TOO_LONG,
                    student_id=student.id,
                    student_name=student.display_name,
                    classroom_id=classroom_id,
                    classroom_name=classroom_name,
                    experiment_id=progress.experiment_id,
                    experiment_title=experiment_title,
                    message=f"«{experiment_title}» кері байланысы {awaiting_review_days} күннен астам тексерусіз тұр",
                    since=progress.submitted_at,
                )
            )

    return tuple(alerts)
