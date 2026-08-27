"""learning_analytics — Phase 8 (Advanced Analytics & Learning Progress)
per-student topic performance + teacher alert оқу-моделі.

``StudentMonitoringSnapshot``-пен (Phase 6) БІРДЕЙ принцип — ЕШБІР жеке
кесте/жол ретінде сақталмайды, әр шақыруда ``domain/services/learning_
analytics.py`` НАҚТЫ жазбалардан (``StudentExperimentProgress``) қайта
құрастырады. "Топик" (тақырып) — жаңа таксономия ЕМЕС, бар ``ModuleRegistry``
(модуль) + ``ExperimentDefinition`` (тәжірибе) иерархиясы (§ Phase 8
Architecture Decision #2).

§ "weak/strong topic — score-based proxy, honestly labeled": ``level``
тек НАҚТЫ балл шегінен (``teacher_score``/``level1_percentage``) шығады —
ешқашан концепт-деңгейлі диагностика деп фабрикацияланбайды (§ ``domain/
services/learning_analytics.py`` докстрингі, толық түсіндірме).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class TopicPerformanceLevel(Enum):
    WEAK = "weak"
    STRONG = "strong"
    # § дерек жоқ (әлі бағаланбаған) НЕМЕСЕ орташа/шеткі аралықта —
    # "әлсіз" де, "күшті" де деп ЕШҚАШАН фабрикацияланбайды.
    NEUTRAL = "neutral"


@dataclass(frozen=True)
class TopicPerformance:
    """Бір тәжірибе ("топик/суб-топик") бойынша қорытынды көрсеткіш —
    БІР оқушының жолында (§ ``StudentLearningProgress.topics``) немесе
    сынып ауқымындағы жинақта (санақтар БІРНЕШЕ оқушыны қамтуы мүмкін)
    қайта пайдаланылады."""

    experiment_id: str
    experiment_title: str
    module_name: str
    attempted_count: int
    completed_count: int
    reviewed_count: int
    average_score: float | None
    completion_rate: float | None  # § completed/attempted, ЕШҚАШАН /enrolled (§ Architecture Decision #4)
    level: TopicPerformanceLevel


@dataclass(frozen=True)
class StudentLearningProgress:
    """Бір оқушының барлық тәжірибелер бойынша оқу үлгерімі — Analytics
    "Оқушылар бойынша үлгерім" кестесінің БІР жолы."""

    student_id: str
    student_name: str
    classroom_id: str
    classroom_name: str
    topics: tuple[TopicPerformance, ...] = field(default_factory=tuple)
    overall_average_score: float | None = None
    overall_completion_rate: float | None = None
    weakest_topic: TopicPerformance | None = None
    strongest_topic: TopicPerformance | None = None


class AlertKind(Enum):
    OVERDUE = "overdue"
    LOW_SCORE = "low_score"
    AWAITING_REVIEW_TOO_LONG = "awaiting_review_too_long"


@dataclass(frozen=True)
class TeacherAlert:
    """Мұғалім Бақылау тақтасындағы бір ескерту жолы — тек НАҚТЫ
    ``StudentExperimentProgress`` өрістерінен (§ "zero new repository
    dependency", Architecture Decision #5)."""

    kind: AlertKind
    student_id: str
    student_name: str
    classroom_id: str
    classroom_name: str
    experiment_id: str
    experiment_title: str
    message: str
    since: datetime | None
