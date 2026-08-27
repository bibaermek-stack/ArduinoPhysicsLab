"""student_home_summary — Оқушы "Басты бет" дашбордына арналған, ТЕК
қолданыстағы ``IStudentProgressRepository``/``ModuleRegistry``
деректерінен есептелетін, таза (Qt-сыз, оңай тестіленетін) агрегация
(Phase — Student Home Dashboard Redesign).

Ешбір жаңа дерек моделі/кесте/статус мағынасы ойдан шығарылмайды — тек
``MainWindow._compute_active_student_counts()``-те бұрыннан бар канондық
"аяқталған"/"орындалып жатыр"/"қаралмаған" анықтамасын (§ ProgressStatus)
және ``teacher_dashboard_page._refresh_recent_results()``-тегі recency-
сұрыптау өрнегін бір жерге жинайды — HomePage-тің "zero-repository-access"
дизайны сақталады (§ HomePage докстрингі): бұл модуль ``MainWindow``-да
шақырылады, нәтиже HomePage-ке дайын, оқуға арналған деректер ретінде
беріледі.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from domain.entities.experiment_definition import ExperimentDefinition
from domain.entities.student_experiment_progress import ProgressStatus, StudentExperimentProgress
from domain.interfaces.i_physics_module import IPhysicsModule
from domain.interfaces.i_student_progress_repository import IStudentProgressRepository
from modules.module_registry import ModuleRegistry

# § ``MainWindow._compute_active_student_counts()``-пен БІРДЕЙ канондық
# "аяқталған" анықтамасы — осы бір жерден ғана оқылады, енді екі рет
# анықталмайды.
COMPLETED_STATUSES: tuple[ProgressStatus, ...] = (
    ProgressStatus.MEASUREMENT_COMPLETED,
    ProgressStatus.REPORT_COMPLETED,
    ProgressStatus.FEEDBACK_SUBMITTED,
    ProgressStatus.REVIEWED,
)

_DEFAULT_MAX_RECENT_RESULTS = 3


@dataclass(frozen=True)
class ResumableExperiment:
    """"Жалғастыру" карточкасы үшін таңдалған, шын мәнінде орындалып
    жатқан (``ProgressStatus.IN_PROGRESS``) тәжірибе."""

    experiment: ExperimentDefinition
    module: IPhysicsModule


@dataclass(frozen=True)
class CategoryProgress:
    """Бір физика бөлімі бойынша нақты каталог/прогресс есебі —
    numerator (аяқталған) ЖӘНЕ denominator (каталогтағы жалпы саны)
    екеуі де НАҚТЫ дереккөзден (§ "do not hardcode 2/6")."""

    module: IPhysicsModule
    completed: int
    total: int


@dataclass(frozen=True)
class RecentResult:
    """"Соңғы нәтижелер" бір жолы — ``teacher_score`` тек
    ``ProgressStatus.REVIEWED``-те мағыналы (§ analytics_page.py-мен
    БІРДЕЙ ереже), әйтпесе ``None`` (UI "—" көрсетеді)."""

    experiment: ExperimentDefinition
    teacher_score: int | None


@dataclass(frozen=True)
class StudentHomeSummary:
    in_progress_count: int
    completed_count: int
    awaiting_review_count: int
    resumable: ResumableExperiment | None
    category_progress: tuple[CategoryProgress, ...]
    recent_results: tuple[RecentResult, ...]


def _recency_key(progress: StudentExperimentProgress) -> datetime:
    """§ ``teacher_dashboard_page.TeacherDashboardPage._recency_key()``-мен
    БІРДЕЙ өрнек — "соңғы белсенділік" ЕШҚАШАН екі бөлек анықтамамен
    есептелмейді."""
    timestamp = progress.submitted_at or progress.last_activity_at
    return timestamp if timestamp is not None else datetime.min.replace(tzinfo=timezone.utc)


def compute_student_home_summary(
    module_registry: ModuleRegistry,
    student_progress_repository: IStudentProgressRepository,
    student_id: str,
    max_recent_results: int = _DEFAULT_MAX_RECENT_RESULTS,
) -> StudentHomeSummary:
    """Белсенді оқушының "Басты бет" дашборды үшін қажетті БАРЛЫҚ
    сандарды/таңдауларды БІР ``list_progress_for_student()`` шақыруынан
    есептейді (§ "do not implement parallel counting logic" — қосымша
    репозиторий сұрауы жоқ, тек composition).
    """
    modules = module_registry.get_all()

    experiment_lookup: dict[str, tuple[ExperimentDefinition, IPhysicsModule]] = {}
    experiment_ids: list[str] = []
    for module in modules:
        for experiment in module.get_experiments():
            experiment_lookup[experiment.id] = (experiment, module)
            experiment_ids.append(experiment.id)

    progress_list = student_progress_repository.list_progress_for_student(
        student_id, tuple(experiment_ids)
    )
    progress_by_experiment_id = {progress.experiment_id: progress for progress in progress_list}

    completed_count = sum(1 for p in progress_list if p.status in COMPLETED_STATUSES)
    in_progress_count = sum(1 for p in progress_list if p.status is ProgressStatus.IN_PROGRESS)
    awaiting_review_count = sum(
        1 for p in progress_list if p.status is ProgressStatus.FEEDBACK_SUBMITTED
    )

    resumable = _select_resumable(progress_list, experiment_lookup)

    category_progress = tuple(
        CategoryProgress(
            module=module,
            completed=sum(
                1
                for experiment in module.get_experiments()
                if (progress := progress_by_experiment_id.get(experiment.id)) is not None
                and progress.status in COMPLETED_STATUSES
            ),
            total=len(module.get_experiments()),
        )
        for module in modules
    )

    recent_results = _select_recent_results(progress_list, experiment_lookup, max_recent_results)

    return StudentHomeSummary(
        in_progress_count=in_progress_count,
        completed_count=completed_count,
        awaiting_review_count=awaiting_review_count,
        resumable=resumable,
        category_progress=category_progress,
        recent_results=recent_results,
    )


def _select_resumable(
    progress_list: tuple[StudentExperimentProgress, ...],
    experiment_lookup: dict[str, tuple[ExperimentDefinition, IPhysicsModule]],
) -> ResumableExperiment | None:
    """§ "genuinely in-progress experiment/session ... use the most
    recently active one if multiple are valid".

    Шектеу (§ audit): ``SqliteSessionRepository.save_session()`` бос (0
    өлшеу) сессияны ЕШҚАШАН сақтамайды, сондықтан НАҚТЫ IN_PROGRESS
    жазбаның ``last_activity_at``-ы іс жүзінде әрдайым ``None`` (сессия
    әлі "experiment_sessions" кестесіне жазылмаған). Осы жағдайда
    ``_recency_key`` барлық үміткерге бірдей ``datetime.min`` қайтарады —
    ``sort()`` ТҰРАҚТЫ (stable) болғандықтан, нәтиже ешбір сан ойдан
    шығармай, каталог ретімен ДЕТЕРМИНИСТІК болып қалады.
    """
    in_progress = [p for p in progress_list if p.status is ProgressStatus.IN_PROGRESS]
    if not in_progress:
        return None
    in_progress.sort(key=_recency_key, reverse=True)
    lookup = experiment_lookup.get(in_progress[0].experiment_id)
    if lookup is None:
        return None
    experiment, module = lookup
    return ResumableExperiment(experiment=experiment, module=module)


def _select_recent_results(
    progress_list: tuple[StudentExperimentProgress, ...],
    experiment_lookup: dict[str, tuple[ExperimentDefinition, IPhysicsModule]],
    limit: int,
) -> tuple[RecentResult, ...]:
    completed = [p for p in progress_list if p.status in COMPLETED_STATUSES]
    completed.sort(key=_recency_key, reverse=True)

    results: list[RecentResult] = []
    for progress in completed[:limit]:
        lookup = experiment_lookup.get(progress.experiment_id)
        if lookup is None:
            continue
        experiment, _module = lookup
        # § analytics_page.py "teacher_score тек REVIEWED-те мағыналы".
        score = progress.teacher_score if progress.status is ProgressStatus.REVIEWED else None
        results.append(RecentResult(experiment=experiment, teacher_score=score))
    return tuple(results)
