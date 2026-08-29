"""AnalyticsPage — "Аналитика" беті (Phase 19, Мұғалім-тек).

Бұрынғы ``PlaceholderPage``-тің орнына, ТЕК бар репозиторий/домен
деректерінен есептелген нақты мұғалім аналитикасы. Бұл бет ешбір жаңа
"тағайындау" (assignment) ұғымын ойлап шықпайды (§ ``ClassroomActivity
Snapshot`` модуль docstring-індегі принциппен БІРДЕЙ): ``IStudentProgress
Repository.list_all_progress()`` тек НАҚТЫ session_student_link байланысы
бар (яғни кемінде басталған) жұптарды қайтарады — ``ProgressStatus.
NOT_STARTED`` бұл жерде ешқашан болмайды, сондықтан "Жұмыстардың күйі"
панелінде де НЕГЕ "Басталмаған" себеті ЖОҚ екені осы жерде құжатталған
(§ ``_WORK_STATUS_ORDER`` төменде).

Барлық есептеу Qt-сыз таза функцияларда (``_build_records``/``_filter_*``/
``_compute_*``) орындалады — бет класы тек ОСЫ функциялардың нәтижесін
виджеттерге басады (§ "Do not put business logic directly into the
page", teacher_dashboard_page.py-мен БІРДЕЙ принцип). Снапшот ТЕК
``on_enter()``/сүзгі өзгерген сайын бір рет қайта есептеледі — әр сүзгі
ауысымы репозиторийге ЕШҚАШАН қайта сұрау салмайды (§ "Avoid duplicate
repository queries").
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QCursor
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from domain.entities.classroom import Classroom
from domain.entities.experiment_definition import ExperimentDefinition
from domain.entities.learning_analytics import StudentLearningProgress, TopicPerformanceLevel
from domain.entities.student_experiment_progress import ProgressStatus, StudentExperimentProgress
from domain.interfaces.i_active_teacher_repository import IActiveTeacherRepository
from domain.interfaces.i_classroom_repository import IClassroomRepository
from domain.interfaces.i_student_progress_repository import IStudentProgressRepository
from domain.interfaces.i_student_repository import IStudentRepository
from domain.interfaces.i_teacher_repository import ITeacherRepository
from domain.services.analytics_csv_exporter import AnalyticsCsvExporter
from domain.services.learning_analytics import compute_students_learning_progress
from domain.services.teacher_scope import resolve_allowed_classroom_ids
from infrastructure.storage.sqlite_active_teacher_repository import SqliteActiveTeacherRepository
from infrastructure.storage.sqlite_teacher_repository import SqliteTeacherRepository
from modules.module_registry import ModuleRegistry
from ui.themes.theme_manager import (
    COLOR_ACCENT,
    COLOR_BORDER,
    COLOR_ERROR,
    COLOR_GRAPH_AXIS,
    COLOR_GRAPH_BACKGROUND,
    COLOR_SUCCESS,
    COLOR_SURFACE,
    COLOR_TEXT_MUTED,
    COLOR_WARNING,
    RADIUS_SM,
    SPACING_LG,
    SPACING_MD,
    SPACING_XS,
)
from ui.widgets.class_activity_carousel import classroom_accent_color

# § ``ui/widgets/live_graph.py``-дегі ДӘЛ СОЛ шақыру (§10 "Reuse existing
# graph background/axis/text/grid tokens") — ОСЫ файлдың ӨЗІ де
# қолданады, ExperimentWorkspacePage-тің импорт РЕТІНЕ (импорт кезіндегі
# жанама эффект) ЕШҚАШАН сенбейді (§ модуль docstring-і: Analytics
# дербес, ExperimentWorkspacePage-сіз де дұрыс салынуы тиіс). Global
# ``pg`` конфигурациясы идемпотентті — екі рет шақырылса да қауіпсіз.
pg.setConfigOptions(background=COLOR_GRAPH_BACKGROUND, foreground=COLOR_GRAPH_AXIS)

_PAGE_TITLE = "Аналитика"
_PAGE_SUBTITLE = "Сыныптар мен зертханалық жұмыстардың оқу нәтижелерін талдау"

_ALL_FILTER_TEXT = "Барлығы"
_NO_VALUE_TEXT = "—"
_NO_DATA_TEXT = "Дерек жоқ"
_FILTER_COMBO_MAX_WIDTH = 190

_PERIOD_7_DAYS = "7d"
_PERIOD_30_DAYS = "30d"
_PERIOD_ALL_TIME = "all"
_PERIOD_OPTIONS: tuple[tuple[str, str], ...] = (
    (_PERIOD_7_DAYS, "7 күн"),
    (_PERIOD_30_DAYS, "30 күн"),
    (_PERIOD_ALL_TIME, "Барлық уақыт"),
)
# § "Use a 30-day default if actual timestamps allow it safely" —
# ``last_activity_at`` ХАТТА бір байланыс болса да ӘРҚАШАН tz-aware
# орнатылады (§ ``ExperimentSession.__post_init__`` валидациясы), сондықтан
# 30-күндік әдепкі қауіпсіз.
_DEFAULT_PERIOD = _PERIOD_30_DAYS

_EMPTY_TITLE_TEXT = "Аналитика үшін жеткілікті дерек әлі жиналған жоқ."
_EMPTY_HINT_TEXT = "Оқушылар зертханалық жұмыстарды орындаған сайын статистика осы жерде көрсетіледі."
_PANEL_NO_DATA_TEXT = "Таңдалған сүзгіге сай дерек жоқ."

# ``IStudentProgressRepository.compute_dashboard_counts()``-тегі "completed"
# анықтамасымен ДӘЛ БІРДЕЙ статус жиыны (§ "Reuse canonical domain status
# logic" — Analytics ӨЗ, екінші "аяқталды" анықтамасын ойлап шығармайды).
_COMPLETED_STATUSES = frozenset(
    {
        ProgressStatus.MEASUREMENT_COMPLETED,
        ProgressStatus.REPORT_COMPLETED,
        ProgressStatus.FEEDBACK_SUBMITTED,
        ProgressStatus.REVIEWED,
    }
)

# ``ui/pages/class_management_page.py``-дегі ``_STATUS_TEXT``/``_STATUS_
# COLOR``-мен БІРДЕЙ мәтін/түс (§ жобаның бұрыннан бар per-page dict
# дублирлеу конвенциясы — терминологияны қайта ойлап шығармау). ``NOT_
# STARTED`` ӘДЕЙІ ЖОҚ: ``list_all_progress()`` оны ешқашан қайтармайды
# (§ модуль docstring-і) — глобал "Басталмаған" саны "тағайындау"
# концепциясын талап етер еді, ол доменде жоқ.
_WORK_STATUS_ORDER: tuple[ProgressStatus, ...] = (
    ProgressStatus.IN_PROGRESS,
    ProgressStatus.MEASUREMENT_COMPLETED,
    ProgressStatus.REPORT_COMPLETED,
    ProgressStatus.FEEDBACK_SUBMITTED,
    ProgressStatus.REVIEWED,
)
_WORK_STATUS_TEXT: dict[ProgressStatus, str] = {
    ProgressStatus.IN_PROGRESS: "Өлшеу жүріп жатыр",
    ProgressStatus.MEASUREMENT_COMPLETED: "Өлшеу аяқталды",
    ProgressStatus.REPORT_COMPLETED: "Есеп ашылды",
    ProgressStatus.FEEDBACK_SUBMITTED: "Кері байланыс жіберілді",
    ProgressStatus.REVIEWED: "Тексерілді",
}
_WORK_STATUS_COLOR: dict[ProgressStatus, str] = {
    ProgressStatus.IN_PROGRESS: COLOR_ACCENT,
    ProgressStatus.MEASUREMENT_COMPLETED: COLOR_ACCENT,
    ProgressStatus.REPORT_COMPLETED: COLOR_ACCENT,
    ProgressStatus.FEEDBACK_SUBMITTED: COLOR_WARNING,
    ProgressStatus.REVIEWED: COLOR_SUCCESS,
}

_SCORE_AXIS_MAX = 10  # § "Scores should remain on the existing 0-10 grading scale"

# § Phase 8 (Advanced Analytics & Learning Progress) — "Оқушылар бойынша
# үлгерім" кестесі. ``TopicPerformanceLevel``-мен БІРДЕЙ, ЖАҢА түс-сөз
# сөздігі ойлап шығарылмайды (§ жобаның established dict конвенциясы).
_STUDENT_TABLE_HEADERS = (
    "Оқушы", "Сынып", "Орташа балл (0-10)", "Орындалу деңгейі", "Әлсіз тақырып", "Күшті тақырып", "",
)
_STUDENT_ACTION_BUTTON_TEXT = "Толығырақ"
_STUDENT_EXPORT_BUTTON_TEXT = "CSV экспорт"
_STUDENT_PANEL_TITLE = "Оқушылар бойынша үлгерім"
_STUDENT_EMPTY_TITLE_TEXT = "Таңдалған сүзгіге сай оқушы дерегі жоқ."
_TOPIC_LEVEL_COLOR: dict[TopicPerformanceLevel, str] = {
    TopicPerformanceLevel.WEAK: COLOR_ERROR,
    TopicPerformanceLevel.STRONG: COLOR_SUCCESS,
    TopicPerformanceLevel.NEUTRAL: COLOR_TEXT_MUTED,
}


def _make_background_transparent(widget: QWidget) -> None:
    """§ ``teacher_dashboard_page._make_background_transparent()``-мен
    БІРДЕЙ себеп/түзету — ``role``-негізді ``QLabel`` өз ЕНІНЕ (QVBoxLayout-
    та толық созылған) сай ``COLOR_BACKGROUND`` тіктөртбұрышын ақ
    ``HomeSummaryCard`` үстінде бояп кетеді. instance-деңгейлік
    ``setStyleSheet()`` ғана жұмыс істейді."""
    widget.setStyleSheet("background-color: transparent;")


# ==========================================================================
# ТАЗА ЕСЕПТЕУ ҚАБАТЫ (Qt-сыз) — dataclass + функциялар
# ==========================================================================


@dataclass(frozen=True)
class _ProgressRecord:
    """Бір ``(student, experiment)`` жұбының Analytics үшін керек, аралас
    (progress + classroom/student presentation) көрінісі. ``get_progress()``
    сияқты, ешқашан сақталмайды — ``_build_records()`` әр снапшотта қайта
    құрады."""

    student_id: str
    classroom_id: str
    classroom_name: str
    experiment_id: str
    status: ProgressStatus
    teacher_score: int | None
    last_activity_at: datetime | None


def _build_records(
    progress_list: tuple[StudentExperimentProgress, ...],
    student_repository: IStudentRepository,
    classroom_repository: IClassroomRepository,
) -> tuple[_ProgressRecord, ...]:
    """``ResultsPage._refresh()``-пен БІРДЕЙ join тәсілі (§ "student
    repository-ден classroom_id, содан кейін classroom repository-ден
    атау") — оқушы/сынып жойылған (тапталмаған сирек жағдай) жазба
    үнсіз өткізіп жіберіледі, ешқашан фабрикацияланбайды."""
    records: list[_ProgressRecord] = []
    for progress in progress_list:
        student = student_repository.get(progress.student_id)
        if student is None:
            continue
        classroom = classroom_repository.get(student.classroom_id)
        if classroom is None:
            continue
        records.append(
            _ProgressRecord(
                student_id=progress.student_id,
                classroom_id=classroom.id,
                classroom_name=classroom.name,
                experiment_id=progress.experiment_id,
                status=progress.status,
                teacher_score=progress.teacher_score,
                last_activity_at=progress.last_activity_at,
            )
        )
    return tuple(records)


def _filter_records(
    records: tuple[_ProgressRecord, ...],
    classroom_id: str | None,
    experiment_id: str | None,
) -> tuple[_ProgressRecord, ...]:
    """Сынып/Зертханалық жұмыс сүзгісін AND логикасымен қолданады (§5).
    Бұл функция КЕЗЕҢ (period) сүзгісін ЕШҚАШАН қолданбайды —§ модуль
    docstring-і: орташа балл/орындалу деңгейі/күту саны сияқты жинақы
    KPI-лар УАҚЫТ терезесіне ТӘУЕЛСІЗ, кумулятивті күй (Results/Dashboard
    беттеріндегі ДӘЛ СОЛ "Тексеруді күтуде" картасымен БІРДЕЙ, олар да
    ешқашан кезеңмен сүзілмейді)."""
    return tuple(
        record
        for record in records
        if (classroom_id is None or record.classroom_id == classroom_id)
        and (experiment_id is None or record.experiment_id == experiment_id)
    )


def _apply_period(
    records: tuple[_ProgressRecord, ...], period: str, now: datetime
) -> tuple[_ProgressRecord, ...]:
    """Тек УАҚЫТҚА БАЙЛАНЫСТЫ көріністер ("Белсенді оқушылар" KPI-і,
    "Белсенділік динамикасы" панелі) үшін қолданылады (§ ``_filter_records``
    docstring-і). ``last_activity_at`` жоқ жазба (теориялық түрде де
    болмауы тиіс — байланыс бар жерде әрқашан орнатылады) ешқашан
    кіргізілмейді, себебі кезеңге жатуын растау мүмкін емес."""
    if period == _PERIOD_ALL_TIME:
        return tuple(record for record in records if record.last_activity_at is not None)
    days = 7 if period == _PERIOD_7_DAYS else 30
    cutoff = now - timedelta(days=days)
    return tuple(
        record
        for record in records
        if record.last_activity_at is not None and record.last_activity_at >= cutoff
    )


def _average_score(records: tuple[_ProgressRecord, ...]) -> tuple[float | None, int]:
    """§ "mean of valid teacher scores from reviewed work only" —
    ``teacher_score`` тек ``ProgressStatus.REVIEWED``-те мағыналы (§
    ``StudentExperimentProgress`` докстрингі), сондықтан статус бойынша
    ЕКІНШІ рет сүзу ешбір қосымша семантика қоспайды, тек анық етеді.
    ``(орташа_немесе_None, тексерілген_саны)`` қайтарады."""
    scores = [
        record.teacher_score
        for record in records
        if record.status is ProgressStatus.REVIEWED and record.teacher_score is not None
    ]
    if not scores:
        return None, 0
    return sum(scores) / len(scores), len(scores)


@dataclass(frozen=True)
class AnalyticsKpis:
    average_score_text: str
    completion_rate_text: str
    active_students_text: str
    waiting_review_text: str


def compute_kpis(
    records_no_period: tuple[_ProgressRecord, ...],
    records_with_period: tuple[_ProgressRecord, ...],
) -> AnalyticsKpis:
    """4 KPI картасының мәтіндерін есептейді.

    - Орташа нәтиже: ``_average_score`` (§ жоғарыда), кезеңге тәуелсіз.
    - Орындалу деңгейі: ``_COMPLETED_STATUSES``-тегі статус саны / барлық
      НАҚТЫ басталған жұп саны (``len(records_no_period)``) * 100. Бөлгіш
      ЕШҚАШАН толық каталог × барлық оқушы санынан алынбайды — тек нақты
      сессия байланысы бар жұптар (§ "Do not invent an assignment
      concept"). Дерек болмаса "—".
    - Белсенді оқушылар: ``records_with_period`` (кезең сүзгісі қолданылған)
      ішіндегі бірегей ``student_id`` саны.
    - Тексеруді күтуде: ``records_no_period`` ішіндегі ``FEEDBACK_
      SUBMITTED`` саны (кезеңге тәуелсіз — нақты кезек, Results/Dashboard
      беттеріндегі ДӘЛ СОЛ картамен БІРДЕЙ семантика).
    """
    average, _count = _average_score(records_no_period)
    average_text = f"{average:.1f}" if average is not None else _NO_VALUE_TEXT

    total_started = len(records_no_period)
    if total_started == 0:
        completion_text = _NO_VALUE_TEXT
    else:
        completed = sum(1 for r in records_no_period if r.status in _COMPLETED_STATUSES)
        completion_text = f"{round(completed / total_started * 100)}%"

    active_students = len({record.student_id for record in records_with_period})

    waiting = sum(1 for r in records_no_period if r.status is ProgressStatus.FEEDBACK_SUBMITTED)

    return AnalyticsKpis(
        average_score_text=average_text,
        completion_rate_text=completion_text,
        active_students_text=str(active_students),
        waiting_review_text=str(waiting),
    )


@dataclass(frozen=True)
class ClassroomPerformanceRow:
    classroom_id: str
    classroom_name: str
    accent_color: str
    average_score: float | None
    reviewed_count: int


def compute_classroom_performance(
    records: tuple[_ProgressRecord, ...], classrooms: tuple[Classroom, ...]
) -> tuple[ClassroomPerformanceRow, ...]:
    """§6 — ``classrooms`` шеңберіндегі (шақырушы Сынып сүзгісіне сай
    ЕНДІ бір сыныпқа тарылтады, § ``AnalyticsPage._apply_filters()``)
    ӘРБІР сынып үшін бір жол қайтарады — тексерілген балл жоқ сынып
    ЕШҚАШАН тасталмайды, тек ``average_score=None`` (§ "show it as
    Дерек жоқ"). Реттеу — ``classroom_repository.list_active()``-тің ӨЗ
    атауы бойынша сұрыпталған ретімен (шақырушы береді, § "no second
    sort algorithm")."""
    rows: list[ClassroomPerformanceRow] = []
    for classroom in classrooms:
        classroom_records = tuple(r for r in records if r.classroom_id == classroom.id)
        average, count = _average_score(classroom_records)
        rows.append(
            ClassroomPerformanceRow(
                classroom_id=classroom.id,
                classroom_name=classroom.name,
                accent_color=classroom_accent_color(classroom.id, classroom.name),
                average_score=average,
                reviewed_count=count,
            )
        )
    return tuple(rows)


def compute_work_status_counts(records: tuple[_ProgressRecord, ...]) -> dict[ProgressStatus, int]:
    """§7 — тек доменде НАҚТЫ бар статустар (§ ``_WORK_STATUS_ORDER``)."""
    counts: dict[ProgressStatus, int] = {status: 0 for status in _WORK_STATUS_ORDER}
    for record in records:
        if record.status in counts:
            counts[record.status] += 1
    return counts


@dataclass(frozen=True)
class ExperimentPerformanceRow:
    experiment_id: str
    title: str
    display_number: int | None
    average_score: float | None
    reviewed_count: int


def compute_experiment_performance(
    records: tuple[_ProgressRecord, ...], experiments: tuple[ExperimentDefinition, ...]
) -> tuple[ExperimentPerformanceRow, ...]:
    """§8 — ``ModuleRegistry`` каталогының ӨЗ ретімен (hardcoded атау
    жоқ). ``experiments`` шеңберіндегі (шақырушы Зертханалық жұмыс
    сүзгісіне сай ЕНДІ бір тәжірибеге тарылтады) ӘРБІР тәжірибе үшін бір
    жол — ``compute_classroom_performance``-пен БІРДЕЙ "ешқашан
    тасталмайды, тек Дерек жоқ" ережесі."""
    rows: list[ExperimentPerformanceRow] = []
    for experiment in experiments:
        experiment_records = tuple(r for r in records if r.experiment_id == experiment.id)
        average, count = _average_score(experiment_records)
        rows.append(
            ExperimentPerformanceRow(
                experiment_id=experiment.id,
                title=experiment.title,
                display_number=experiment.display_number,
                average_score=average,
                reviewed_count=count,
            )
        )
    return tuple(rows)


@dataclass(frozen=True)
class ActivityTrendPoint:
    label: str
    count: int


def compute_activity_trend(
    records: tuple[_ProgressRecord, ...], period: str, now: datetime
) -> tuple[ActivityTrendPoint, ...]:
    """§9 — ``last_activity_at``-тың КҮНІ бойынша (жергілікті уақыт
    белдеуіне түрлендірілген, § жобаның ``astimezone().strftime()``
    конвенциясы) нақты белсенділік санағышы.

    - 7/30 күн: сол ауқымдағы КҮНДЕЛІКТІ себет — дерек жоқ күн 0-санмен
      көрсетіледі (§ "representing zero-count buckets inside a valid
      selected date range" — АУҚЫМНЫҢ ӨЗІ нақты, тек ІШІНДЕГІ бос себет).
    - Барлық уақыт: дерек болмаса бос tuple (жалған ауқым жоқ). Болса,
      НАҚТЫ ең ерте/ең соңғы белсенділік аралығы — 60 күннен аз болса
      күнделікті, әйтпесе апталық себет (§ "reasonable aggregation based
      on actual date span").
    """
    dated = [r for r in records if r.last_activity_at is not None]

    if period in (_PERIOD_7_DAYS, _PERIOD_30_DAYS):
        days = 7 if period == _PERIOD_7_DAYS else 30
        local_today = now.astimezone().date()
        bucket_dates = [local_today - timedelta(days=offset) for offset in range(days - 1, -1, -1)]
        counts = dict.fromkeys(bucket_dates, 0)
        for record in dated:
            day = record.last_activity_at.astimezone().date()
            if day in counts:
                counts[day] += 1
        return tuple(
            ActivityTrendPoint(label=day.strftime("%d.%m"), count=counts[day])
            for day in bucket_dates
        )

    # Барлық уақыт
    if not dated:
        return ()
    local_dates = [r.last_activity_at.astimezone().date() for r in dated]
    span_days = (max(local_dates) - min(local_dates)).days
    if span_days <= 60:
        bucket_dates = [min(local_dates) + timedelta(days=offset) for offset in range(span_days + 1)]
        counts = dict.fromkeys(bucket_dates, 0)
        for day in local_dates:
            counts[day] += 1
        return tuple(
            ActivityTrendPoint(label=day.strftime("%d.%m"), count=counts[day])
            for day in bucket_dates
        )

    # Апталық себет (ISO апта басы — дүйсенбі).
    week_starts = sorted({day - timedelta(days=day.weekday()) for day in local_dates})
    week_start_by_day = {day: day - timedelta(days=day.weekday()) for day in local_dates}
    counts = dict.fromkeys(week_starts, 0)
    for day in local_dates:
        counts[week_start_by_day[day]] += 1
    return tuple(
        ActivityTrendPoint(label=week_start.strftime("%d.%m"), count=counts[week_start])
        for week_start in week_starts
    )


def row_index_for_y(y_value: float, row_count: int) -> int | None:
    """Тінтуір Y-координатасын (view space) ЕҢ ЖАҚЫН bar-жол индексіне
    бейнелейді — ``pg.SignalProxy`` hover callback-інен бөлек тестелетін
    таза функция. Жол шекарасынан тыс болса ``None``."""
    if row_count <= 0:
        return None
    index = round(y_value)
    if index < 0 or index >= row_count:
        return None
    return index


# ==========================================================================
# QT ВИДЖЕТ ҚАБАТЫ
# ==========================================================================


class AnalyticsPage(QWidget):
    """"Аналитика" беті — бірінші деңгейлі sidebar тағайыны (§2: "← Артқа"
    батырмасы ЖОҚ, тақырып бірінші layout элементі)."""

    # § Phase 8 — "direct navigation from analytics to student monitoring,
    # session history and teacher feedback": ``StudentMonitoringDetailPage``
    # (Phase 6/7) ӘЛДЕҚАШАН ЕКЕУІН де (кері байланыс панелі + "Тәжірибе
    # тарихы" батырмасы) иеленеді — сондықтан ЖАЛҒЫЗ осы route жеткілікті
    # (§ ``classroom_monitoring_page.student_selected``-пен БІРДЕЙ пішін).
    student_monitoring_requested = Signal(str, str)  # student_id, experiment_id

    def __init__(
        self,
        classroom_repository: IClassroomRepository,
        student_repository: IStudentRepository,
        student_progress_repository: IStudentProgressRepository,
        module_registry: ModuleRegistry,
        teacher_repository: ITeacherRepository | None = None,
        active_teacher_repository: IActiveTeacherRepository | None = None,
        csv_exporter: AnalyticsCsvExporter | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._classroom_repository = classroom_repository
        self._student_repository = student_repository
        self._student_progress_repository = student_progress_repository
        self._module_registry = module_registry
        self._teacher_repository = teacher_repository or SqliteTeacherRepository()
        self._active_teacher_repository = (
            active_teacher_repository or SqliteActiveTeacherRepository()
        )

        self._all_records: tuple[_ProgressRecord, ...] = ()
        # § Phase 8 — ``compute_students_learning_progress()`` шикі
        # (raw) ``StudentExperimentProgress`` тізімін талап етеді, § "avoid
        # duplicate repository queries" — ``_refresh()``-те БІР рет
        # сұралған, ``_all_records``-пен ҚАТАР сақталады (§ ешбір
        # қосымша репозиторий шақыруы).
        self._all_progress: tuple[StudentExperimentProgress, ...] = ()
        self._student_rows: tuple[StudentLearningProgress, ...] = ()
        self._student_row_experiment_by_id: dict[str, str | None] = {}
        self._csv_exporter = csv_exporter or AnalyticsCsvExporter()
        self._value_labels: dict[str, QLabel] = {}

        title_label = QLabel(_PAGE_TITLE, self)
        title_font = title_label.font()
        title_font.setBold(True)
        title_font.setPointSize(title_font.pointSize() + 4)
        title_label.setFont(title_font)

        subtitle_label = QLabel(_PAGE_SUBTITLE, self)
        subtitle_label.setProperty("role", "secondary")
        subtitle_label.setWordWrap(True)

        kpi_row = QHBoxLayout()
        kpi_row.addWidget(self._build_kpi_card("average", "Орташа нәтиже"), 1)
        kpi_row.addWidget(self._build_kpi_card("completion", "Орындалу деңгейі"), 1)
        kpi_row.addWidget(self._build_kpi_card("active_students", "Белсенді оқушылар"), 1)
        kpi_row.addWidget(self._build_kpi_card("waiting", "Тексеруді күтуде"), 1)

        self._classroom_filter_combo = QComboBox(self)
        self._classroom_filter_combo.setMaximumWidth(_FILTER_COMBO_MAX_WIDTH)
        self._classroom_filter_combo.currentIndexChanged.connect(self._on_filters_changed)

        self._experiment_filter_combo = QComboBox(self)
        self._experiment_filter_combo.setMaximumWidth(_FILTER_COMBO_MAX_WIDTH)
        self._experiment_filter_combo.currentIndexChanged.connect(self._on_filters_changed)

        self._period_filter_combo = QComboBox(self)
        self._period_filter_combo.setMaximumWidth(_FILTER_COMBO_MAX_WIDTH)
        for key, label in _PERIOD_OPTIONS:
            self._period_filter_combo.addItem(label, key)
        self._period_filter_combo.setCurrentIndex(
            self._period_filter_combo.findData(_DEFAULT_PERIOD)
        )
        self._period_filter_combo.currentIndexChanged.connect(self._on_filters_changed)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Сынып:", self))
        filter_row.addWidget(self._classroom_filter_combo)
        filter_row.addWidget(QLabel("Зертханалық жұмыс:", self))
        filter_row.addWidget(self._experiment_filter_combo)
        filter_row.addWidget(QLabel("Кезең:", self))
        filter_row.addWidget(self._period_filter_combo)
        filter_row.addStretch(1)

        classroom_panel = self._build_classroom_performance_panel()
        work_status_panel = self._build_work_status_panel()
        experiment_panel = self._build_experiment_performance_panel()
        trend_panel = self._build_activity_trend_panel()
        student_progress_panel = self._build_student_progress_panel()

        panels_grid = QGridLayout()
        panels_grid.setColumnStretch(0, 2)
        panels_grid.setColumnStretch(1, 1)
        panels_grid.setRowStretch(0, 1)
        panels_grid.setRowStretch(1, 1)
        panels_grid.addWidget(classroom_panel, 0, 0)
        panels_grid.addWidget(work_status_panel, 0, 1)
        panels_grid.addWidget(experiment_panel, 1, 0)
        panels_grid.addWidget(trend_panel, 1, 1)

        content_widget = QWidget(self)
        _make_background_transparent(content_widget)
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.addWidget(title_label)
        content_layout.addWidget(subtitle_label)
        content_layout.addLayout(kpi_row)
        content_layout.addLayout(filter_row)
        content_layout.addLayout(panels_grid, 1)
        content_layout.addWidget(student_progress_panel, 1)
        self._content_widget = content_widget

        empty_page_title_label = QLabel(_PAGE_TITLE, self)
        empty_page_title_font = empty_page_title_label.font()
        empty_page_title_font.setBold(True)
        empty_page_title_font.setPointSize(empty_page_title_font.pointSize() + 4)
        empty_page_title_label.setFont(empty_page_title_font)

        self._empty_title_label = QLabel(_EMPTY_TITLE_TEXT, self)
        self._empty_title_label.setObjectName("WorkspaceEmptyStateLabel")
        empty_font = self._empty_title_label.font()
        empty_font.setBold(True)
        self._empty_title_label.setFont(empty_font)
        self._empty_hint_label = QLabel(_EMPTY_HINT_TEXT, self)
        self._empty_hint_label.setObjectName("WorkspaceEmptyStateLabel")
        self._empty_hint_label.setWordWrap(True)

        empty_widget = QWidget(self)
        _make_background_transparent(empty_widget)
        empty_layout = QVBoxLayout(empty_widget)
        empty_layout.setContentsMargins(0, 0, 0, 0)
        empty_layout.addWidget(empty_page_title_label)
        empty_layout.addWidget(self._empty_title_label)
        empty_layout.addWidget(self._empty_hint_label)
        empty_layout.addStretch(1)

        self._stack = QStackedWidget(self)
        self._stack.addWidget(empty_widget)
        self._stack.addWidget(content_widget)
        self._empty_page_widget = empty_widget

        layout = QVBoxLayout(self)
        layout.addWidget(self._stack)

        self._refresh()

    # ---- Router интерфейсі ------------------------------------------------

    def on_enter(self) -> None:
        self._refresh()

    # ---- KPI карточкалары (§4, HomeSummaryCard конвенциясы) ---------------

    def _build_kpi_card(self, key: str, label: str) -> QWidget:
        card = QFrame(self)
        card.setObjectName("HomeSummaryCard")

        value_label = QLabel(_NO_VALUE_TEXT, card)
        value_label.setProperty("role", "cardValue")
        _make_background_transparent(value_label)
        self._value_labels[key] = value_label

        caption_label = QLabel(label, card)
        caption_label.setProperty("role", "cardLabel")
        _make_background_transparent(caption_label)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(SPACING_LG, SPACING_MD, SPACING_LG, SPACING_MD)
        card_layout.setSpacing(SPACING_XS)
        card_layout.addWidget(value_label)
        card_layout.addWidget(caption_label)
        return card

    # ---- Панель қаңқасы (§18: DashboardPanel/cardTitle қайта пайдалану) ---

    def _build_panel_frame(self, title: str) -> tuple[QFrame, QVBoxLayout]:
        panel = QFrame(self)
        panel.setObjectName("DashboardPanel")
        panel.setMinimumHeight(190)

        title_label = QLabel(title, panel)
        title_label.setProperty("role", "cardTitle")
        _make_background_transparent(title_label)

        layout = QVBoxLayout(panel)
        layout.addWidget(title_label)
        return panel, layout

    def _build_stack_body(self, layout: QVBoxLayout) -> QStackedWidget:
        """Панель денесі — график/тарату виджеті НЕМЕСЕ "дерек жоқ" хабары
        (§12: "Do not leave an apparently broken blank chart grid")."""
        body_stack = QStackedWidget(self)
        no_data_label = QLabel(_PANEL_NO_DATA_TEXT, body_stack)
        no_data_label.setProperty("role", "secondary")
        no_data_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _make_background_transparent(no_data_label)
        body_stack.addWidget(no_data_label)
        layout.addWidget(body_stack, 1)
        return body_stack

    # ---- §6: Сыныптар бойынша үлгерім --------------------------------------

    def _build_classroom_performance_panel(self) -> QWidget:
        panel, layout = self._build_panel_frame("Сыныптар бойынша үлгерім")
        self._classroom_stack = self._build_stack_body(layout)

        plot = pg.PlotWidget(panel)
        plot.showGrid(x=True, y=False, alpha=0.08)
        plot.setMouseEnabled(x=False, y=False)
        plot.hideButtons()
        plot.getViewBox().invertY(True)
        plot.setLabel("bottom", "Орташа балл (0-10)")
        plot.getAxis("bottom").setTickSpacing(major=2, minor=1)
        self._classroom_plot = plot
        self._classroom_stack.addWidget(plot)
        return panel

    def _update_classroom_performance(self, rows: tuple[ClassroomPerformanceRow, ...]) -> None:
        self._classroom_plot.clear()
        if not rows:
            self._classroom_stack.setCurrentIndex(0)
            return
        self._classroom_stack.setCurrentIndex(1)

        x1_values: list[float] = []
        y0_values: list[float] = []
        y1_values: list[float] = []
        brushes: list[QColor] = []
        ticks: list[tuple[float, str]] = []
        for index, row in enumerate(rows):
            ticks.append((index, row.classroom_name))
            if row.average_score is None:
                label = pg.TextItem(_NO_DATA_TEXT, color=COLOR_TEXT_MUTED, anchor=(0, 0.5))
                label.setPos(0.15, index)
                self._classroom_plot.addItem(label)
                continue
            x1_values.append(row.average_score)
            y0_values.append(index - 0.35)
            y1_values.append(index + 0.35)
            brushes.append(QColor(row.accent_color))

        if x1_values:
            bar_item = pg.BarGraphItem(
                x0=0, x1=x1_values, y0=y0_values, y1=y1_values,
                brushes=brushes, pen=pg.mkPen(None),
            )
            self._classroom_plot.addItem(bar_item)

        self._classroom_plot.getAxis("left").setTicks([ticks])
        self._classroom_plot.setXRange(0, _SCORE_AXIS_MAX, padding=0.05)
        self._classroom_plot.setYRange(-0.5, len(rows) - 0.5, padding=0.08)

    # ---- §7: Жұмыстардың күйі -----------------------------------------------

    def _build_work_status_panel(self) -> QWidget:
        panel, layout = self._build_panel_frame("Жұмыстардың күйі")
        self._work_status_stack = self._build_stack_body(layout)

        rows_widget = QWidget(panel)
        rows_layout = QVBoxLayout(rows_widget)
        rows_layout.setContentsMargins(0, 0, 0, 0)
        self._work_status_bars: dict[ProgressStatus, tuple[QProgressBar, QLabel]] = {}
        for status in _WORK_STATUS_ORDER:
            row_layout = QHBoxLayout()
            text_label = QLabel(_WORK_STATUS_TEXT[status], rows_widget)
            text_label.setMinimumWidth(150)
            bar = QProgressBar(rows_widget)
            bar.setTextVisible(False)
            bar.setMaximumHeight(10)
            color = _WORK_STATUS_COLOR[status]
            bar.setStyleSheet(
                f"QProgressBar {{ border: 1px solid {COLOR_BORDER}; border-radius: {RADIUS_SM}px; "
                f"background-color: {COLOR_SURFACE}; }}"
                f"QProgressBar::chunk {{ background-color: {color}; border-radius: {RADIUS_SM}px; }}"
            )
            count_label = QLabel("0", rows_widget)
            count_label.setMinimumWidth(28)
            count_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            row_layout.addWidget(text_label)
            row_layout.addWidget(bar, 1)
            row_layout.addWidget(count_label)
            rows_layout.addLayout(row_layout)
            self._work_status_bars[status] = (bar, count_label)
        rows_layout.addStretch(1)

        self._work_status_stack.addWidget(rows_widget)
        return panel

    def _update_work_status(self, counts: dict[ProgressStatus, int]) -> None:
        total = sum(counts.values())
        if total == 0:
            self._work_status_stack.setCurrentIndex(0)
            return
        self._work_status_stack.setCurrentIndex(1)
        for status, (bar, count_label) in self._work_status_bars.items():
            count = counts.get(status, 0)
            bar.setMaximum(max(total, 1))
            bar.setValue(count)
            count_label.setText(str(count))

    # ---- §8: Зертханалық жұмыстар бойынша орташа нәтиже --------------------

    def _build_experiment_performance_panel(self) -> QWidget:
        panel, layout = self._build_panel_frame("Зертханалық жұмыстар бойынша орташа нәтиже")
        self._experiment_stack = self._build_stack_body(layout)

        plot = pg.PlotWidget(panel)
        plot.showGrid(x=True, y=False, alpha=0.08)
        plot.setMouseEnabled(x=False, y=False)
        plot.hideButtons()
        plot.getViewBox().invertY(True)
        plot.setLabel("bottom", "Орташа балл (0-10)")
        self._experiment_plot = plot
        self._experiment_rows: tuple[ExperimentPerformanceRow, ...] = ()
        self._experiment_hover_proxy = pg.SignalProxy(
            plot.scene().sigMouseMoved, rateLimit=30, slot=self._on_experiment_hover
        )
        self._experiment_stack.addWidget(plot)
        return panel

    def _update_experiment_performance(self, rows: tuple[ExperimentPerformanceRow, ...]) -> None:
        self._experiment_plot.clear()
        self._experiment_rows = rows
        if not rows:
            self._experiment_stack.setCurrentIndex(0)
            return
        self._experiment_stack.setCurrentIndex(1)

        x1_values: list[float] = []
        y0_values: list[float] = []
        y1_values: list[float] = []
        ticks: list[tuple[float, str]] = []
        for index, row in enumerate(rows):
            number_label = f"№{row.display_number}" if row.display_number is not None else "№?"
            ticks.append((index, number_label))
            if row.average_score is None:
                label = pg.TextItem(_NO_DATA_TEXT, color=COLOR_TEXT_MUTED, anchor=(0, 0.5))
                label.setPos(0.15, index)
                self._experiment_plot.addItem(label)
                continue
            x1_values.append(row.average_score)
            y0_values.append(index - 0.35)
            y1_values.append(index + 0.35)

        if x1_values:
            bar_item = pg.BarGraphItem(
                x0=0, x1=x1_values, y0=y0_values, y1=y1_values,
                brush=QColor(COLOR_ACCENT), pen=pg.mkPen(None),
            )
            self._experiment_plot.addItem(bar_item)

        self._experiment_plot.getAxis("left").setTicks([ticks])
        self._experiment_plot.setXRange(0, _SCORE_AXIS_MAX, padding=0.05)
        self._experiment_plot.setYRange(-0.5, len(rows) - 0.5, padding=0.08)

    def _on_experiment_hover(self, event: tuple) -> None:
        if not self._experiment_rows:
            QToolTip.hideText()
            return
        scene_pos = event[0]
        view_box = self._experiment_plot.getViewBox()
        if not self._experiment_plot.sceneBoundingRect().contains(scene_pos):
            QToolTip.hideText()
            return
        view_point = view_box.mapSceneToView(scene_pos)
        index = row_index_for_y(view_point.y(), len(self._experiment_rows))
        if index is None:
            QToolTip.hideText()
            return
        row = self._experiment_rows[index]
        number_text = f"№{row.display_number}" if row.display_number is not None else "№?"
        if row.average_score is None:
            text = f"{number_text} {row.title}\n{_NO_DATA_TEXT}"
        else:
            text = (
                f"{number_text} {row.title}\n"
                f"Орташа балл: {row.average_score:.1f}\n"
                f"Тексерілген жұмыс саны: {row.reviewed_count}"
            )
        QToolTip.showText(QCursor.pos(), text, self._experiment_plot)

    # ---- §9: Белсенділік динамикасы ----------------------------------------

    def _build_activity_trend_panel(self) -> QWidget:
        panel, layout = self._build_panel_frame("Белсенділік динамикасы")
        self._trend_stack = self._build_stack_body(layout)

        plot = pg.PlotWidget(panel)
        plot.showGrid(x=True, y=True, alpha=0.08)
        plot.setMouseEnabled(x=False, y=False)
        plot.hideButtons()
        plot.setLabel("left", "Белсенділік саны")
        self._trend_plot = plot
        self._trend_stack.addWidget(plot)
        return panel

    def _update_activity_trend(self, points: tuple[ActivityTrendPoint, ...]) -> None:
        self._trend_plot.clear()
        if not points:
            self._trend_stack.setCurrentIndex(0)
            return
        self._trend_stack.setCurrentIndex(1)

        x_values = list(range(len(points)))
        y_values = [point.count for point in points]
        self._trend_plot.plot(
            x_values, y_values, pen=pg.mkPen(COLOR_ACCENT, width=2),
            symbol="o", symbolSize=6, symbolBrush=QColor(COLOR_ACCENT), symbolPen=pg.mkPen(None),
        )

        # §9 "no overlapping axes" — көп себет кезінде тек әр N-ші белгіні
        # көрсету (§ results_page.py-дегі "no horizontal overflow" бag
        # түзетуімен БІРДЕЙ рух, тар өлшемде толық белгі жиынтығы сыймайды).
        # ``pg.AxisItem.setTicks()`` НАҚТЫ берілген позицияларды өзі
        # ЕШБІР қосымша collision-avoidance-сыз салады — панель тар
        # (2-баған grid-тегі кіші баған, § ``AnalyticsPage.__init__``
        # ``panels_grid.setColumnStretch``), сондықтан max саны 1366px-де
        # де ЕШБІР қабаттаспау үшін ЕДӘУІР шектеулі болуы тиіс (§ скриншот
        # аудитінде табылған/түзетілген регрессия).
        max_visible_ticks = 6
        step = max(1, -(-len(points) // max_visible_ticks))
        ticks = [(i, point.label) for i, point in enumerate(points) if i % step == 0]
        self._trend_plot.getAxis("bottom").setTicks([ticks])
        self._trend_plot.setXRange(-0.5, len(points) - 0.5, padding=0.02)
        self._trend_plot.setYRange(0, max(y_values + [1]), padding=0.15)

    # ---- Phase 8: Оқушылар бойынша үлгерім (per-student breakdown) --------

    def _build_student_progress_panel(self) -> QWidget:
        panel = QFrame(self)
        panel.setObjectName("DashboardPanel")
        panel.setMinimumHeight(220)

        title_label = QLabel(_STUDENT_PANEL_TITLE, panel)
        title_label.setProperty("role", "cardTitle")
        _make_background_transparent(title_label)

        export_button = QPushButton(_STUDENT_EXPORT_BUTTON_TEXT, panel)
        export_button.setEnabled(False)
        export_button.clicked.connect(self._on_export_csv_clicked)
        self._student_export_button = export_button

        self._student_export_status = QLabel("", panel)
        self._student_export_status.setProperty("role", "secondary")
        self._student_export_status.setWordWrap(True)

        header_row = QHBoxLayout()
        header_row.addWidget(title_label)
        header_row.addStretch(1)
        header_row.addWidget(self._student_export_status)
        header_row.addWidget(export_button)

        layout = QVBoxLayout(panel)
        layout.addLayout(header_row)

        self._student_stack = QStackedWidget(panel)

        empty_label = QLabel(_STUDENT_EMPTY_TITLE_TEXT, panel)
        empty_label.setProperty("role", "secondary")
        empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _make_background_transparent(empty_label)
        self._student_stack.addWidget(empty_label)

        table = QTableWidget(panel)
        table.setColumnCount(len(_STUDENT_TABLE_HEADERS))
        table.setHorizontalHeaderLabels(_STUDENT_TABLE_HEADERS)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        table.cellDoubleClicked.connect(self._on_student_row_activated)
        self._student_table = table
        self._student_stack.addWidget(table)

        layout.addWidget(self._student_stack, 1)
        return panel

    def _update_student_progress(self, rows: tuple[StudentLearningProgress, ...]) -> None:
        """§ ``compute_students_learning_progress()``-тің нәтижесін кестеге
        басады. Әр жол ``student_id`` бойынша ``self._student_rows``-та
        сақталады (§ "row activation" — қатар индексі арқылы қайта іздеу,
        ешбір қосымша репозиторий шақыруынсыз)."""
        self._student_rows = rows
        self._student_export_button.setEnabled(bool(rows))
        table = self._student_table
        if not rows:
            self._student_stack.setCurrentIndex(0)
            table.setRowCount(0)
            return
        self._student_stack.setCurrentIndex(1)

        # § "on_enter() қайта шақырылса да ЕШБІР ескі cellWidget қалмауы
        # тиіс" — ``setCellWidget()`` бар ұяшыққа қайта шақырылғанда ЕСКІ
        # виджетті КЕПІЛДІ жоймайды (Qt-тың нақты құжатталмаған тәртібі),
        # сондықтан ``clearContents()`` толық тазарту үшін ЖАҢА
        # ``setRowCount()``-тан БҰРЫН шақырылады.
        table.clearContents()
        table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            table.setItem(row_index, 0, QTableWidgetItem(row.student_name))
            table.setItem(row_index, 1, QTableWidgetItem(row.classroom_name))

            score_text = (
                f"{row.overall_average_score:.1f}"
                if row.overall_average_score is not None
                else _NO_VALUE_TEXT
            )
            table.setItem(row_index, 2, QTableWidgetItem(score_text))

            completion_text = (
                f"{round(row.overall_completion_rate * 100)}%"
                if row.overall_completion_rate is not None
                else _NO_VALUE_TEXT
            )
            table.setItem(row_index, 3, QTableWidgetItem(completion_text))

            weak_item = QTableWidgetItem(
                row.weakest_topic.experiment_title if row.weakest_topic is not None else _NO_VALUE_TEXT
            )
            if row.weakest_topic is not None:
                weak_item.setForeground(QColor(_TOPIC_LEVEL_COLOR[row.weakest_topic.level]))
            table.setItem(row_index, 4, weak_item)

            strong_item = QTableWidgetItem(
                row.strongest_topic.experiment_title if row.strongest_topic is not None else _NO_VALUE_TEXT
            )
            if row.strongest_topic is not None:
                strong_item.setForeground(QColor(_TOPIC_LEVEL_COLOR[row.strongest_topic.level]))
            table.setItem(row_index, 5, strong_item)

            action_button = QPushButton(_STUDENT_ACTION_BUTTON_TEXT, table)
            action_button.clicked.connect(
                lambda _checked=False, student_id=row.student_id: (
                    self._emit_student_monitoring_requested(student_id)
                )
            )
            table.setCellWidget(row_index, 6, action_button)

        # § "Соңғы нәтижелер" панеліндегі ДӘЛ БІРДЕЙ түзету (§
        # ``TeacherDashboardPage._refresh_recent_results()``) —
        # ``setCellWidget``/``QTableWidgetItem`` бастапқы баған ендерін
        # автоматты есептемейді, тек ``resizeColumnsToContents()`` кейін
        # шақырылса ғана қатарлар қабаттаспайды (§ бос-баған 0 Stretch
        # режимі resize-тен КЕЙІН қайта қойылады).
        table.resizeColumnsToContents()
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        # § "action button text must not be clipped" — ``resizeColumnsTo
        # Contents()`` батырма ЕНІН ол толық орналасқанға дейін (cell
        # widget-тің ӨЗ sizeHint-і layout-тан КЕЙІН ғана дәл болады)
        # есептейді, сондықтан соңғы (батырма) бағанға шамалы қосымша
        # орын қосылады (§ мәтіннің қиылып қалуын болдырмау).
        action_column = len(_STUDENT_TABLE_HEADERS) - 1
        table.setColumnWidth(action_column, table.columnWidth(action_column) + 24)

    def _on_student_row_activated(self, row: int, _column: int) -> None:
        if row < 0 or row >= len(self._student_rows):
            return
        self._emit_student_monitoring_requested(self._student_rows[row].student_id)

    def _emit_student_monitoring_requested(self, student_id: str) -> None:
        """§6 "reuse the existing ``student_monitoring`` route" — мақсатты
        ``experiment_id`` ретінде ЕҢ ӘЛСІЗ тақырып (§ мұғалімге ЕҢ бірінші
        назар аударуы қажет жер), ол жоқ болса (ешбір балл әлі бағаланбаса)
        осы оқушының БІРІНШІ тәжірибесі (§ "never silently emit an invalid
        route param")."""
        row = next((r for r in self._student_rows if r.student_id == student_id), None)
        if row is None:
            return
        if row.weakest_topic is not None:
            experiment_id = row.weakest_topic.experiment_id
        elif row.topics:
            experiment_id = row.topics[0].experiment_id
        else:
            return
        self.student_monitoring_requested.emit(student_id, experiment_id)

    def _on_export_csv_clicked(self) -> None:
        if not self._student_rows:
            return
        file_path, _filter = QFileDialog.getSaveFileName(
            self, _STUDENT_EXPORT_BUTTON_TEXT, "analytics.csv", "CSV (*.csv)"
        )
        if not file_path:
            return
        try:
            if self._csv_exporter.export(self._student_rows, file_path):
                self._student_export_status.setText("CSV сәтті сақталды")
            else:
                self._student_export_status.setText("CSV экспорты сәтсіз аяқталды")
        except Exception as exc:
            self._student_export_status.setText(f"Экспорт қатесі: {exc}")

    # ---- Дерек жаңарту -------------------------------------------------------

    def _iter_catalog_experiments(self) -> tuple[ExperimentDefinition, ...]:
        experiments: list[ExperimentDefinition] = []
        for module in self._module_registry.get_all():
            experiments.extend(module.get_experiments())
        return tuple(experiments)

    def _refresh(self) -> None:
        allowed_classroom_ids = resolve_allowed_classroom_ids(
            self._teacher_repository, self._active_teacher_repository
        )
        progress_list = self._student_progress_repository.list_all_progress(allowed_classroom_ids)
        self._all_progress = progress_list
        self._all_records = _build_records(
            progress_list, self._student_repository, self._classroom_repository
        )
        self._classrooms = self._classroom_repository.list_active()
        self._experiments = self._iter_catalog_experiments()

        # §12: тек ЕШБІР сынып болмаса ғана толық бет-деңгейлі
        # бос күй (§ жоғарыдағы docstring, "clean install" жағдайы) —
        # сыныптар/оқушылар бар, бірақ прогресс жоқ болса, сүзгі/KPI/
        # панельдер ӨЗ дербес "дерек жоқ" күйлерімен көрінеді.
        if not self._classrooms:
            self._stack.setCurrentIndex(0)
            return
        self._stack.setCurrentIndex(1)

        self._populate_classroom_filter()
        self._populate_experiment_filter()
        self._apply_filters()

    def _populate_classroom_filter(self) -> None:
        current = self._classroom_filter_combo.currentData()
        self._classroom_filter_combo.blockSignals(True)
        self._classroom_filter_combo.clear()
        self._classroom_filter_combo.addItem(_ALL_FILTER_TEXT, None)
        for classroom in self._classrooms:
            self._classroom_filter_combo.addItem(classroom.name, classroom.id)
        restored = self._classroom_filter_combo.findData(current)
        self._classroom_filter_combo.setCurrentIndex(restored if restored >= 0 else 0)
        self._classroom_filter_combo.blockSignals(False)

    def _populate_experiment_filter(self) -> None:
        current = self._experiment_filter_combo.currentData()
        self._experiment_filter_combo.blockSignals(True)
        self._experiment_filter_combo.clear()
        self._experiment_filter_combo.addItem(_ALL_FILTER_TEXT, None)
        for experiment in self._experiments:
            label = (
                f"№{experiment.display_number} {experiment.title}"
                if experiment.display_number is not None
                else experiment.title
            )
            self._experiment_filter_combo.addItem(label, experiment.id)
        restored = self._experiment_filter_combo.findData(current)
        self._experiment_filter_combo.setCurrentIndex(restored if restored >= 0 else 0)
        self._experiment_filter_combo.blockSignals(False)

    def _on_filters_changed(self) -> None:
        self._apply_filters()

    def _apply_filters(self) -> None:
        classroom_id = self._classroom_filter_combo.currentData()
        experiment_id = self._experiment_filter_combo.currentData()
        period = self._period_filter_combo.currentData() or _DEFAULT_PERIOD

        records_no_period = _filter_records(self._all_records, classroom_id, experiment_id)
        now = datetime.now(timezone.utc)
        records_with_period = _apply_period(records_no_period, period, now)

        kpis = compute_kpis(records_no_period, records_with_period)
        self._value_labels["average"].setText(kpis.average_score_text)
        self._value_labels["completion"].setText(kpis.completion_rate_text)
        self._value_labels["active_students"].setText(kpis.active_students_text)
        self._value_labels["waiting"].setText(kpis.waiting_review_text)

        # §5 "Classroom → experiment/time filtering should combine
        # logically with AND": Сынып сүзгісі белгілі бір сыныпқа
        # тарылтылса, "Сыныптар бойынша үлгерім" панелі де СОЛ бір
        # сыныпқа тарылады (басқа сыныптарды "Дерек жоқ" ретінде
        # көрсету — сүзгі мағынасына қайшы) — Зертханалық жұмыс
        # сүзгісімен де дәл сол симметриялы қатынас.
        classrooms_in_scope = tuple(
            c for c in self._classrooms if classroom_id is None or c.id == classroom_id
        )
        experiments_in_scope = tuple(
            e for e in self._experiments if experiment_id is None or e.id == experiment_id
        )

        self._update_classroom_performance(
            compute_classroom_performance(records_no_period, classrooms_in_scope)
        )
        self._update_work_status(compute_work_status_counts(records_no_period))
        self._update_experiment_performance(
            compute_experiment_performance(records_no_period, experiments_in_scope)
        )
        self._update_activity_trend(compute_activity_trend(records_with_period, period, now))

        # § "reuse existing filter results without duplicating classroom/
        # experiment filter logic" — ``records_no_period`` ӘЛДЕҚАШАН
        # сынып/тәжірибе сүзгісін қолданды, тек СОЛ (student_id,
        # experiment_id) жұптарына сай шикі ``StudentExperimentProgress``
        # жазбалары ғана ``compute_students_learning_progress()``-ке
        # беріледі (§ ешбір қосымша репозиторий сұрауы).
        pairs_in_scope = {(r.student_id, r.experiment_id) for r in records_no_period}
        progress_in_scope = tuple(
            p for p in self._all_progress if (p.student_id, p.experiment_id) in pairs_in_scope
        )
        student_rows = compute_students_learning_progress(
            progress_in_scope,
            student_repository=self._student_repository,
            classroom_repository=self._classroom_repository,
            module_registry=self._module_registry,
        )
        self._update_student_progress(tuple(sorted(student_rows, key=lambda r: r.student_name)))
