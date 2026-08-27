"""IStudentProgressRepository — сессия-оқушы байланысы + студенттің
эксперимент бойынша прогресін есептеу интерфейсі (Phase 39B).

Бұл репозиторий raw ``measurements``/``experiment_sessions`` кестелерін
ешқашан ӨЗІ жаңа кесте ретінде қайталамайды — тек ``session_student_link``
кестесін иеленеді, ал прогресс/дашборд сандарын есептеу үшін
``ISessionRepository``/``IFeedbackRepository``-ді (композиция арқылы)
шақырады. ``StudentExperimentProgress`` ЕШҚАШАН материалды сақталмайды —
әр шақыруда НАҚТЫ жазбалардан қайта есептеледі.
"""

from abc import ABC, abstractmethod

from domain.entities.classroom_activity_snapshot import ClassroomActivitySnapshot
from domain.entities.student_experiment_progress import StudentExperimentProgress


class IStudentProgressRepository(ABC):
    @abstractmethod
    def link_session(
        self, session_id: str, student_id: str, classroom_id: str, experiment_id: str
    ) -> None:
        """Жаңа сессияны белсенді оқушыға байланыстырады — ``on_enter()``-де,
        сессия сәйкестігі қалыптасқан сәтте-ақ (алғашқы өлшеуге дейін)
        шақырылады. Идемпотентті (``session_id`` PRIMARY KEY).
        """
        raise NotImplementedError

    @abstractmethod
    def get_student_for_session(self, session_id: str) -> str | None:
        """Берілген сессияға тағайындалған оқушының ID-ін қайтарады
        (жоқ болса — ескі/тағайындалмаған сессия — ``None``).
        """
        raise NotImplementedError

    # ---- Cloud Sync (Phase 2: Experiment Session + Results + Feedback) ---

    @abstractmethod
    def get_link_sync_payload(self, session_id: str) -> dict | None:
        """§9 "API Contract": байланысты сым (wire) payload түрінде
        қайтарады — ``student_id``/``classroom_id`` глобал ``sync_id``-ге
        аударылады (§4 "must reference global/sync IDs, never another
        machine's local-only database row IDs"). ``session_id`` ӨЗІ
        entity_sync_id (жеке sync_id бағаны жоқ)."""
        raise NotImplementedError

    @abstractmethod
    def apply_remote_link(self, payload: dict) -> None:
        """§18 "Pull Sync" — ЕШБІР outbox жазуы ЖАСАЛМАЙДЫ."""
        raise NotImplementedError

    @abstractmethod
    def mark_link_synced(self, session_id: str, server_revision: int) -> None:
        raise NotImplementedError

    @abstractmethod
    def enqueue_link_for_sync(self, session_id: str) -> None:
        """§ Phase 2 backfill: ескі байланыстарды outbox-қа қосу үшін."""
        raise NotImplementedError

    @abstractmethod
    def list_all_link_session_ids(self) -> tuple[str, ...]:
        """§ Phase 2 backfill: ``experiment_sessions`` жолы ЖОҚ (§
        "session_student_link has no FK dependency on experiment_
        sessions") "жетім" байланыстарды ҚОСА, БАРЛЫҚ session_id-ды
        қайтарады."""
        raise NotImplementedError

    @abstractmethod
    def get_progress(self, student_id: str, experiment_id: str) -> StudentExperimentProgress:
        """Берілген оқушы/эксперимент жұбы үшін НАҚТЫ жазбалардан
        қорытынды прогресс есептейді (сессия байланысы болмаса
        ``ProgressStatus.NOT_STARTED``-пен қайтарады, ешқашан
        ``None``/exception шығармайды).
        """
        raise NotImplementedError

    @abstractmethod
    def list_progress_for_student(
        self, student_id: str, experiment_ids: tuple[str, ...]
    ) -> tuple[StudentExperimentProgress, ...]:
        """Берілген эксперимент тізімінің әрқайсысы үшін
        ``get_progress()``-ті шақырып, ретімен қайтарады."""
        raise NotImplementedError

    @abstractmethod
    def compute_dashboard_counts(
        self, allowed_classroom_ids: frozenset[str] | None = None
    ) -> dict[str, int]:
        """Мұғалім Бақылау тақтасы үшін жинақы сандар: ``classrooms``,
        ``students``, ``completed``, ``awaiting_review`` кілттерімен
        (нақты репозиторий сұрауларынан, ешбір ойдан шығарылған сан жоқ).

        ``allowed_classroom_ids`` берілсе (§ Multi-Teacher Accounts —
        ағымдағы мұғалімнің тағайындалған сыныптары), нәтиже ТЕК сол
        сыныптармен шектеледі. ``None`` (әдепкі) — шектеусіз, БАРЛЫҚ
        қолданыстағы шақырушыларға (тесттерге ҚОСА) ЕШБІР әсер етпейді.
        """
        raise NotImplementedError

    @abstractmethod
    def list_submitted_progress(
        self, allowed_classroom_ids: frozenset[str] | None = None
    ) -> tuple[StudentExperimentProgress, ...]:
        """Барлық оқушы/эксперимент жұптары бойынша НАҚТЫ жіберілген
        (``ProgressStatus.FEEDBACK_SUBMITTED`` немесе ``ProgressStatus.
        REVIEWED``) прогресс жазбаларын қайтарады — Мұғалімнің "Кері
        байланысты тексеру" кезегі (Phase 40) үшін. Тек жоба (draft)
        сатысында қалған немесе әлі басталмаған жұптар ЕШҚАШАН
        қайтарылмайды (§ "status must be derived from real persisted
        records" — ``compute_dashboard_counts()``-пен БІРДЕЙ принцип).

        ``allowed_classroom_ids`` — ``compute_dashboard_counts()``-пен
        БІРДЕЙ мағына.
        """
        raise NotImplementedError

    @abstractmethod
    def list_all_progress(
        self, allowed_classroom_ids: frozenset[str] | None = None
    ) -> tuple[StudentExperimentProgress, ...]:
        """Барлық НАҚТЫ байланысқан ``(student_id, experiment_id)`` жұбы
        үшін ағымдағы прогресті, статус бойынша сүзгісіз қайтарады
        (``list_submitted_progress()``/``compute_dashboard_counts()``-пен
        БІРДЕЙ ``session_student_link`` pairs-негізді есептеу). Байланысы
        жоқ жұп (``ProgressStatus.NOT_STARTED``) бұл жерде ЕШҚАШАН
        болмайды — ол "тағайындау" концепциясын талап етер еді, ол
        доменде ЖОҚ (§ ``ClassroomActivitySnapshot`` модуль docstring-і).
        Analytics беті (Phase 19) үшін.

        ``allowed_classroom_ids`` — ``compute_dashboard_counts()``-пен
        БІРДЕЙ мағына.
        """
        raise NotImplementedError

    @abstractmethod
    def compute_classroom_activity(
        self, allowed_classroom_ids: frozenset[str] | None = None
    ) -> tuple[ClassroomActivitySnapshot, ...]:
        """Phase 13 (Teacher Dashboard "Бүгінгі белсенділік"): белсенді
        (мұрағатталмаған) сыныптардың атауы бойынша сұрыпталған тізімін
        қайтарады — тек ЕШБІР session_student_link байланысы жоқ сыныптар
        нәтижеге кірмейді (§ "DO NOT fabricate activity information").
        Әр сынып үшін ЕҢ СОҢҒЫ белсенді ``experiment_id`` (ең үлкен
        ``linked_at``) таңдалады, сол сыныптың БАРЛЫҚ оқушысы үшін СОЛ
        тәжірибе бойынша ``get_progress()`` қайта пайдаланылып, аяқтады/
        орындауда/бастамады санына бөлінеді.

        ``allowed_classroom_ids`` — ``compute_dashboard_counts()``-пен
        БІРДЕЙ мағына.
        """
        raise NotImplementedError
