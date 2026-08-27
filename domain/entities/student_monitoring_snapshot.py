"""StudentMonitoringSnapshot / ClassroomMonitoringSnapshot — Phase 6
(Teacher Live Classroom Monitoring) сынып-шолу оқу-моделі.

``ClassroomActivitySnapshot``-пен (Phase 13) БІРДЕЙ принцип — ЕШБІР жеке
кесте/жол ретінде сақталмайды, әр шақыруда ``domain/services/teacher_
monitoring.py::compute_classroom_monitoring()`` НАҚТЫ жазбалардан қайта
құрастырады. ``ClassroomActivitySnapshot``-тан айырмашылығы: бір сынып
үшін БІР "ЕҢ соңғы белсенді тәжірибе" ЕМЕС, әр оқушының ӨЗ ЖЕКЕ ЕҢ
соңғы тәжірибесі бар (§ "student monitoring cards/rows" — әрбір оқушы
ӨЗ жеке тәжірибесін жасауы мүмкін, бір сыныпта бір мезгілде бірнеше
ӘРТҮРЛІ зертханалық жұмыс жүруі мүмкін).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from domain.entities.monitoring_activity_state import MonitoringActivityState
from domain.entities.student_experiment_progress import ProgressStatus


@dataclass(frozen=True)
class StudentMonitoringSnapshot:
    """Бір оқушының сынып-шолу картасы/жолы үшін қорытынды күйі.

    § "Do not render every historical raw measurement on the classroom
    overview" — ``latest_measurement_values`` ТЕК СОҢҒЫ БІР ``Measurement.
    values`` (§ ``ISessionRepository.get_latest_measurement()``), толық
    тарих ЕМЕС. Толық график тек ``StudentMonitoringDetail`` ашылғанда
    жүктеледі.
    """

    student_id: str
    student_name: str
    classroom_id: str
    experiment_id: str | None
    progress_status: ProgressStatus
    activity_state: MonitoringActivityState
    latest_session_id: str | None
    measurement_count: int
    latest_measurement_values: dict[str, float] = field(default_factory=dict)
    started_at: datetime | None = None
    # § "last update time" — соңғы measurement уақыты, ЖОҚ болса сессия
    # басталу уақытына, ол да ЖОҚ болса ``None``-ге құлайды (§ ``domain/
    # services/teacher_monitoring.py::_resolve_last_update_at()``).
    last_update_at: datetime | None = None


@dataclass(frozen=True)
class ClassroomMonitoringSnapshot:
    """Бір сыныптың толық бақылау-шолуы — ``ClassroomMonitoringPage``-тің
    ЖАЛҒЫЗ дерек көзі (§ "avoid putting complex aggregation logic
    directly inside Qt widgets")."""

    classroom_id: str
    classroom_name: str
    generated_at: datetime
    students: tuple[StudentMonitoringSnapshot, ...] = ()

    @property
    def total_students(self) -> int:
        return len(self.students)

    @property
    def active_count(self) -> int:
        return sum(1 for s in self.students if s.activity_state is MonitoringActivityState.ACTIVE)

    @property
    def completed_count(self) -> int:
        return sum(1 for s in self.students if s.activity_state is MonitoringActivityState.COMPLETED)

    @property
    def not_started_count(self) -> int:
        return sum(1 for s in self.students if s.activity_state is MonitoringActivityState.NOT_STARTED)

    @property
    def needs_attention_count(self) -> int:
        """§4 "number requiring attention if derivable" — STALE +
        OFFLINE (§ бұрын белсенді болған, енді жаңа дерексіз сессиялар)."""
        return sum(
            1
            for s in self.students
            if s.activity_state in (MonitoringActivityState.STALE, MonitoringActivityState.OFFLINE)
        )


@dataclass(frozen=True)
class StudentMonitoringDetail:
    """Жеке оқушының тәжірибесін ашық көру беті үшін толық дерек (§
    "Live Student Experiment View") — ``measurements`` ТОЛЫҚ тарих
    (§ ``ISessionRepository.get_measurements()``, тек НАҚТЫ ашылғанда
    жүктеледі)."""

    student_id: str
    student_name: str
    classroom_id: str
    classroom_name: str
    experiment_id: str | None
    progress_status: ProgressStatus
    activity_state: MonitoringActivityState
    session_id: str | None
    started_at: datetime | None
    ended_at: datetime | None
    measurement_count: int
    measurements: tuple = ()
    last_update_at: datetime | None = None
