"""ISessionRepository — аяқталған ExperimentSession-дарды сақтау/оқу
интерфейсі (Data Journal).

Бұл модуль ешбір storage технологиясын (sqlite және т.б.) білмейді —
тек ExperimentSession/Measurement domain entity-лерімен және таза
Python типтерімен жұмыс істейді. Нақты іске асыру
``infrastructure/storage/sqlite_session_repository.py``-де.

``SessionSummary`` — журнал тізімі/детальі үшін жеңіл read-model
проекциясы (каталог/эксперимент метадатасы + сессия статистикасы).
Бұл жаңа domain entity ЕМЕС, тек репозиторий оқу нәтижесінің пішіні.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from domain.entities.experiment_definition import ExperimentDefinition
from domain.entities.experiment_session import ExperimentSession
from domain.entities.measurement import Measurement


@dataclass(frozen=True)
class SessionSummary:
    """Бір сақталған сессияның қысқаша метадатасы (measurement тізімінсіз)."""

    id: str
    experiment_id: str
    experiment_title: str
    experiment_display_number: int | None
    started_at: datetime
    ended_at: datetime | None
    status: str
    measurement_count: int
    created_at: datetime


class ISessionRepository(ABC):
    """Аяқталған тәжірибе сессияларын сақтау/оқу үшін абстрактілі интерфейс."""

    @abstractmethod
    def save_session(
        self,
        session: ExperimentSession,
        experiment_metadata: ExperimentDefinition | None = None,
    ) -> None:
        """Сессияны сақтайды. ``session.measurements`` бос болса, ешнәрсе
        істемейді (бос сессиялар журналда сақталмайды). Бірдей
        ``session.id``-мен қайта шақырылса, идемпотентті түрде
        (жаңа деректермен) ауыстырады — дубликат жол құрылмайды.
        """
        raise NotImplementedError

    @abstractmethod
    def get_sessions(
        self, limit: int | None = None, experiment_id: str | None = None
    ) -> tuple[SessionSummary, ...]:
        """Сақталған сессиялардың қысқаша тізімін қайтарады (measurement-
        дерсіз, тек метадата), ``started_at`` бойынша ЖАҢАдан ЕСКІге қарай
        сұрыпталған.
        """
        raise NotImplementedError

    @abstractmethod
    def get_session(self, session_id: str) -> SessionSummary | None:
        """Бір сессияның қысқаша метадатасын қайтарады (жоқ болса ``None``)."""
        raise NotImplementedError

    @abstractmethod
    def get_measurements(self, session_id: str) -> tuple[Measurement, ...]:
        """Берілген сессияға жататын барлық ``Measurement``-ті ретімен
        қайтарады (тек сол сессия ғана — басқа сессиялар жүктелмейді).
        """
        raise NotImplementedError

    @abstractmethod
    def get_latest_measurement(self, session_id: str) -> Measurement | None:
        """§ Phase 6 (Teacher Live Classroom Monitoring): ``sequence_
        no``-ы ЕҢ ҮЛКЕН БІР ғана ``Measurement``-ті қайтарады (сессияда
        ешбір өлшеу жоқ болса — ``None``). ``get_measurements()``-тен
        айырмашылығы — БҮКІЛ тарихты жүктемейді (§ "classroom overview
        must not render every historical raw measurement" — сынып
        шолуы әр оқушы үшін тек СОҢҒЫ мәнді көрсетеді, толық график тек
        жеке тәжірибе ашылғанда ғана жүктеледі, § ``get_measurements()``
        докстрингі)."""
        raise NotImplementedError

    @abstractmethod
    def count_sessions(self) -> int:
        """Сақталған сессиялардың жалпы санын қайтарады."""
        raise NotImplementedError

    @abstractmethod
    def exists(self, session_id: str) -> bool:
        """Берілген ID-мен сессия сақталғанын қайтарады."""
        raise NotImplementedError

    # ---- Cloud Sync (Phase 2: Experiment Session + Results + Feedback) ---

    @abstractmethod
    def get_sync_payload(self, session_id: str) -> dict | None:
        """§9 "API Contract": сессияны сым (wire) payload түрінде
        қайтарады (``sync_state``/``server_revision``-ты ҚОСА) — жоқ
        болса ``None``. ``session_id`` ӨЗІ entity_sync_id ретінде
        қолданылады (§ Phase 2 дизайны: жеке ``sync_id`` бағаны ЖОҚ,
        ``id`` ӘЛДЕҚАШАН UUID).
        """
        raise NotImplementedError

    @abstractmethod
    def apply_remote_session(self, payload: dict) -> None:
        """§18 "Pull Sync": сервер жіберген сессия жазбасын жергілікті
        дерекқорға жазады — ЕШБІР outbox жазуы ЖАСАЛМАЙДЫ (§ established
        "apply_remote_* never re-enqueues" паттерні)."""
        raise NotImplementedError

    @abstractmethod
    def mark_session_synced(self, session_id: str, server_revision: int) -> None:
        """Push растауынан кейін ``SYNCED`` деп белгілейді."""
        raise NotImplementedError

    @abstractmethod
    def enqueue_for_sync(self, session_id: str) -> None:
        """§ Phase 2 backfill: ескі (Phase 2 кодынан бұрын жазылған)
        сессияларды outbox-қа қосу үшін — ``save_session()``-нің ӨЗ
        ішкі enqueue логикасын сыртқа ашады."""
        raise NotImplementedError

    # ---- Cloud Sync (Phase 4: Raw Arduino Measurement Cloud Sync) --------

    @abstractmethod
    def append_measurements(
        self,
        session_id: str,
        experiment_id: str,
        new_measurements: tuple[Measurement, ...],
        experiment_metadata: ExperimentDefinition | None = None,
        started_at: datetime | None = None,
    ) -> int:
        """§ "Partial Session Upload": ЖАҢА measurement-дерді ҮСТЕМЕЛЕЙ
        жазады (§ ``save_session()``-тен айырмашылығы — ЕШБІР ескі жол
        ЖОЙЫЛМАЙДЫ, тек ЖАҢАлары ағымдағы ең үлкен ``sequence_no``-дан
        КЕЙІН қосылады). Тәжірибе жүріп жатқанда мерзімді шақырылуға
        арналған — ``ExperimentSession.measurements`` тізімі толық
        болғанша КҮТПЕЙДІ (§ "do not wait until an experiment ends
        before synchronization can begin"). ``experiment_sessions``
        жазбасы ӘЛІ ЖОҚ болса, ``status='in_progress'``-пен АЛДЫН АЛА
        жасалады (кейінгі ``save_session()`` шақыруы қалыпты аяқталған
        күймен ҚАУІПСІЗ АЛМАСТЫРАДЫ — § "safely superseded"). Жаңадан
        енгізілген жол санын қайтарады (``new_measurements`` бос болса
        — ``0``, ЕШБІР жазу жасалмайды)."""
        raise NotImplementedError
