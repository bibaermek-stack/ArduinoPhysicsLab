"""teacher_monitoring — Phase 6 (Teacher Live Classroom Monitoring Dashboard)
read-model service.

Таза Python — ЕШБІР Qt тәуелділігі жоқ (§ ``domain/services/sync_engine.py``
докстрингіндегі БІРДЕЙ ұстаным: "UI-widget-ке күрделі агрегация логикасын
тікелей салмау"). Бұл модуль ЕШБІР жаңа кесте/баған иеленбейді — тек
Phase 1-5-те ӘЛДЕҚАШАН синхрондалған жазбаларды (``IStudentProgressRepository``/
``ISessionRepository``/``IClassroomRepository``/``IStudentRepository``)
оқып, ЖАҢА "мұғалімге көрсетуге дайын" оқу-моделін құрастырады.

§6 "Activity / Presence Semantics" — ХАЛАЛ (honest) ескерту: Phase 5
polling негізінде жұмыс істейді, персистентті "presence" арнасы ЖОҚ.
``classify_activity()`` ЕШҚАШАН шынайы желілік қосылымды білдірмейді —
тек "соңғы синхрондалған measurement қаншалықты жаңа" дегенді біледі:

    ACTIVE  — сессия ЖҮРІП ЖАТЫР ЖӘНЕ соңғы measurement ``active_window``
              ішінде (әдепкі 15с — Phase 5-тің ~10с белсенді-тәжірибе
              sync циклінен сәл артық, бір "өткізіп алынған" tick-ке
              төзімді).
    STALE   — сессия ЖҮРІП ЖАТЫР, БІРАҚ соңғы measurement ``active_
              window``-дан асып, ``stale_window``-ға дейін (әдепкі 60с)
              — "дерек күтілуде" (қысқа кідіріс НЕМЕСЕ жаңа желі үзілісі,
              әлі анық емес).
    OFFLINE — сессия ЖҮРІП ЖАТЫР, БІРАҚ соңғы measurement ``stale_
              window``-дан да асып кетті — ұзақ уақыт ЕШБІР дәлел жоқ
              (§ "honest" — бұл ФАКТІЛІК желі ажыратылуын ДӘЛЕЛДЕМЕЙДІ,
              тек "ұзақ уақыт жаңа дерек келмеді" дегенді білдіреді).
    COMPLETED / NOT_STARTED — ``ProgressStatus``-тан ТІКЕЛЕЙ (§ "reuse
              existing enums", ешбір қайталама концепция).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from domain.entities.monitoring_activity_state import MonitoringActivityState
from domain.entities.student_experiment_progress import ProgressStatus
from domain.entities.student_monitoring_snapshot import (
    ClassroomMonitoringSnapshot,
    StudentMonitoringDetail,
    StudentMonitoringSnapshot,
)
from domain.interfaces.i_classroom_repository import IClassroomRepository
from domain.interfaces.i_session_repository import ISessionRepository
from domain.interfaces.i_student_progress_repository import IStudentProgressRepository
from domain.interfaces.i_student_repository import IStudentRepository

# § Phase 5 active-experiment sync interval-мен (әдепкі 10с) сәйкес —
# бір "өткізіп алынған" tick-ке (желі жүктемесі/timing jitter) төзімді
# болу үшін сәл артық.
DEFAULT_ACTIVE_WINDOW = timedelta(seconds=15)
# § "STALE -> OFFLINE" еку жиілігі — бірнеше sync циклі (6+) өткізіп
# алынса ғана "ұзақ дәлелсіз" деп белгіленеді (§ "do not fabricate a
# disconnect after one missed tick").
DEFAULT_STALE_WINDOW = timedelta(seconds=60)


def classify_activity(
    progress_status: ProgressStatus,
    session_is_running: bool | None,
    latest_measurement_at: datetime | None,
    now: datetime,
    active_window: timedelta = DEFAULT_ACTIVE_WINDOW,
    stale_window: timedelta = DEFAULT_STALE_WINDOW,
) -> MonitoringActivityState:
    """Таза функция — толық тестелетін, ешбір репозиторийге тәуелсіз
    (§ ``tests/unit/test_teacher_monitoring.py``).

    § НАҚТЫ түбір себеп: ``ProgressStatus`` ӨЗІ "тәжірибе әлі жүріп жатыр
    ма" деген сұраққа СЕНІМДІ жауап бере АЛМАЙДЫ — ``derive_status()``
    ``measurement_count > 0``-ды бірден ``MEASUREMENT_COMPLETED`` деп
    белгілейді (§ Phase 2-нің ЕСКІ, "session тек Stop-та БІР рет
    сақталады" болжамымен жасалған, § ``student_experiment_progress.py``
    докстрингі), БІРАҚ Phase 4/5-тегі инкременталды ``append_
    measurements()`` арқасында ЭНДІ measurement_count > 0 БОЛСА да
    сессия ӘЛІ ШЫНЫМЕН жүріп жатуы мүмкін (``ended_at IS NULL``). Сол
    себепті ХАЛАЛ "әлі жүріп жатыр ма" сигналы — ``session_is_running``
    (§ ``SessionSummary.ended_at is None``), ЕШҚАШАН ``ProgressStatus``
    ЕМЕС. ``session_is_running=None`` — сессия жолы ӘЛІ құрылмаған
    (``session_student_link`` бар, бірақ бірінші ``append_measurements()``-
    тен БҰРЫН) — "әлі тірі, дәлел жоқ" деп қаралады (§ STALE, ЕШҚАШАН
    OFFLINE/COMPLETED фабрикацияланбайды)."""
    if progress_status is ProgressStatus.NOT_STARTED:
        return MonitoringActivityState.NOT_STARTED
    if session_is_running is False:
        return MonitoringActivityState.COMPLETED
    if latest_measurement_at is None:
        return MonitoringActivityState.STALE
    age = now - latest_measurement_at
    if age < timedelta(0):
        age = timedelta(0)  # § қорғаныс: сағат ауытқуы (clock skew) теріс жасқа әкелмейді
    if age <= active_window:
        return MonitoringActivityState.ACTIVE
    if age <= stale_window:
        return MonitoringActivityState.STALE
    return MonitoringActivityState.OFFLINE


def _select_latest_entry(entries: list, session_repository: ISessionRepository):
    """§ Бір оқушының БІРНЕШЕ ``(student, experiment)`` жұбы болуы мүмкін
    (әртүрлі зертханалық жұмыстар) — ЕҢ СОҢҒЫ БАСТАЛҒАН сессия "ағымдағы"
    деп есептеледі (§ ``compute_classroom_activity()``-тегі ``MAX(linked_
    at)``-пен БІРДЕЙ established методология)."""
    best = None
    best_started_at: datetime | None = None
    for entry in entries:
        summary = (
            session_repository.get_session(entry.latest_session_id)
            if entry.latest_session_id is not None
            else None
        )
        started_at = summary.started_at if summary is not None else None
        if best is None or (started_at is not None and (best_started_at is None or started_at > best_started_at)):
            best = entry
            best_started_at = started_at
    return best


def _resolve_last_update_at(
    session_repository: ISessionRepository, session_id: str | None, session_started_at: datetime | None
):
    if session_id is None:
        return None
    latest_measurement = session_repository.get_latest_measurement(session_id)
    if latest_measurement is not None:
        return latest_measurement.timestamp
    return session_started_at


def compute_classroom_monitoring(
    classroom_id: str,
    *,
    classroom_repository: IClassroomRepository,
    student_repository: IStudentRepository,
    student_progress_repository: IStudentProgressRepository,
    session_repository: ISessionRepository,
    now: datetime,
    active_window: timedelta = DEFAULT_ACTIVE_WINDOW,
    stale_window: timedelta = DEFAULT_STALE_WINDOW,
) -> ClassroomMonitoringSnapshot | None:
    """§3 "Classroom Monitoring Entry Point" / §5 "Student Monitoring
    Cards": берілген сыныптың БАРЛЫҚ (архивтелмеген) оқушысы үшін
    қорытынды snapshot құрастырады. Сынып табылмаса ``None`` (§ "student
    belonging to another teacher's classroom must never be shown" —
    шақырушы ӨЗІ ``allowed_classroom_ids``/teacher-scoped repository
    арқылы авторизацияны қамтамасыз етуі керек, § authorization
    boundary докстрингі төменде)."""
    classroom = classroom_repository.get(classroom_id)
    if classroom is None:
        return None

    students = student_repository.list_by_classroom(classroom_id)
    all_progress = student_progress_repository.list_all_progress(frozenset({classroom_id}))
    progress_by_student: dict[str, list] = {}
    for entry in all_progress:
        progress_by_student.setdefault(entry.student_id, []).append(entry)

    snapshots: list[StudentMonitoringSnapshot] = []
    for student in students:
        entries = progress_by_student.get(student.id, [])
        if not entries:
            snapshots.append(
                StudentMonitoringSnapshot(
                    student_id=student.id,
                    student_name=student.display_name,
                    classroom_id=classroom_id,
                    experiment_id=None,
                    progress_status=ProgressStatus.NOT_STARTED,
                    activity_state=MonitoringActivityState.NOT_STARTED,
                    latest_session_id=None,
                    measurement_count=0,
                )
            )
            continue

        winner = _select_latest_entry(entries, session_repository)
        summary = (
            session_repository.get_session(winner.latest_session_id)
            if winner.latest_session_id is not None
            else None
        )
        last_update_at = _resolve_last_update_at(
            session_repository, winner.latest_session_id, summary.started_at if summary is not None else None
        )
        session_is_running = None if summary is None else summary.ended_at is None
        activity_state = classify_activity(
            winner.status,
            session_is_running,
            last_update_at,
            now,
            active_window,
            stale_window,
        )
        latest_measurement = (
            session_repository.get_latest_measurement(winner.latest_session_id)
            if winner.latest_session_id is not None
            else None
        )
        snapshots.append(
            StudentMonitoringSnapshot(
                student_id=student.id,
                student_name=student.display_name,
                classroom_id=classroom_id,
                experiment_id=winner.experiment_id,
                progress_status=winner.status,
                activity_state=activity_state,
                latest_session_id=winner.latest_session_id,
                measurement_count=winner.measurement_count,
                latest_measurement_values=dict(latest_measurement.values) if latest_measurement is not None else {},
                started_at=summary.started_at if summary is not None else None,
                last_update_at=last_update_at,
            )
        )

    return ClassroomMonitoringSnapshot(
        classroom_id=classroom_id, classroom_name=classroom.name, generated_at=now, students=tuple(snapshots)
    )


def compute_student_monitoring_detail(
    student_id: str,
    experiment_id: str,
    *,
    student_repository: IStudentRepository,
    classroom_repository: IClassroomRepository,
    student_progress_repository: IStudentProgressRepository,
    session_repository: ISessionRepository,
    now: datetime,
    active_window: timedelta = DEFAULT_ACTIVE_WINDOW,
    stale_window: timedelta = DEFAULT_STALE_WINDOW,
) -> StudentMonitoringDetail | None:
    """§7 "Live Student Experiment View": ТОЛЫҚ (§ ``get_measurements()``)
    measurement тарихын жүктейді — ТЕК осы функция шақырылғанда (§
    "Load detailed raw graph data only when an individual experiment is
    opened"). Оқушы табылмаса ``None``."""
    student = student_repository.get(student_id)
    if student is None:
        return None
    classroom = classroom_repository.get(student.classroom_id)
    classroom_name = classroom.name if classroom is not None else "—"

    progress = student_progress_repository.get_progress(student_id, experiment_id)
    session_id = progress.latest_session_id
    summary = session_repository.get_session(session_id) if session_id is not None else None
    measurements = session_repository.get_measurements(session_id) if session_id is not None else ()
    last_update_at = (
        measurements[-1].timestamp
        if measurements
        else (summary.started_at if summary is not None else None)
    )
    session_is_running = None if summary is None else summary.ended_at is None
    activity_state = classify_activity(
        progress.status,
        session_is_running,
        last_update_at,
        now,
        active_window,
        stale_window,
    )

    return StudentMonitoringDetail(
        student_id=student_id,
        student_name=student.display_name,
        classroom_id=student.classroom_id,
        classroom_name=classroom_name,
        experiment_id=experiment_id,
        progress_status=progress.status,
        activity_state=activity_state,
        session_id=session_id,
        started_at=summary.started_at if summary is not None else None,
        ended_at=summary.ended_at if summary is not None else None,
        measurement_count=progress.measurement_count,
        measurements=measurements,
        last_update_at=last_update_at,
    )
