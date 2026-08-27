"""IFeedbackRepository — үш деңгейлі кері байланыс нәтижесін сақтау/оқу
интерфейсі (Phase 39A).

``ISessionRepository``-мен БІРДЕЙ принцип: бұл модуль ешбір storage
технологиясын білмейді, тек domain entity-лерімен (``ExperimentFeedbackResult``/
``TeacherAssessment``) жұмыс істейді. Нақты іске асыру
``infrastructure/storage/sqlite_feedback_repository.py``-де.

Raw ``measurements``/``experiment_sessions`` кестелерінен МҮЛДЕ БӨЛЕК —
бұл репозиторий өлшеу дерегін ешқашан оқымайды/жазбайды, тек
``session_id`` арқылы сілтеме жасайды.
"""

from abc import ABC, abstractmethod

from domain.entities.experiment_feedback_result import ExperimentFeedbackResult, TeacherAssessment
from domain.entities.user_role import UserRole


class IFeedbackRepository(ABC):
    """Бір сессияға (``session_id``) БІР ғана кері байланыс жазбасын
    сақтау/оқу үшін абстрактілі интерфейс.
    """

    @abstractmethod
    def save_draft(self, result: ExperimentFeedbackResult) -> None:
        """Жобаны (draft, ``is_draft=True``) сақтайды. Бірдей
        ``session_id``-мен қайта шақырылса, идемпотентті түрде
        ауыстырады.
        """
        raise NotImplementedError

    @abstractmethod
    def save_submission(self, result: ExperimentFeedbackResult) -> None:
        """Түпкілікті жіберуді (``is_draft=False``, ``submitted_at``
        орнатылған) сақтайды.
        """
        raise NotImplementedError

    @abstractmethod
    def get_result(self, session_id: str) -> ExperimentFeedbackResult | None:
        """Берілген сессияға арналған кері байланыс жазбасын қайтарады
        (жоқ болса ``None``) — ``teacher_assessment`` де ҚОСА (рөлге
        қатысты сүзу шақырушының жауапкершілігі, бұл әдіс шикі толық
        жазбаны қайтарады).
        """
        raise NotImplementedError

    @abstractmethod
    def save_teacher_assessment(
        self,
        session_id: str,
        experiment_id: str,
        teacher_assessment: TeacherAssessment,
        role: UserRole,
    ) -> None:
        """Мұғалім бағасын сақтайды. ``role`` міндетті түрде
        ``UserRole.TEACHER`` болуы керек — Оқушы режимінен тікелей
        шақырылса ``PermissionError`` шығарады (қорғаныстың екінші
        сызығы — ``domain.services.experiment_feedback_service.
        apply_teacher_assessment()``-пен қатар). Егер ``session_id``
        үшін жазба әлі жоқ болса (студент әлі жоба/жіберу сақтамаған
        болса да), Мұғалім бағалай алуы тиіс — сондықтан бос
        (level1/2/3 толтырылмаған) жазба алдын ала жасалады.
        """
        raise NotImplementedError

    # ---- Cloud Sync (Phase 2: Experiment Session + Results + Feedback) ---
    #
    # ``experiment_feedback`` БІР физикалық жол, БІРАҚ ЕКІ тәуелсіз
    # синхрондалатын логикалық entity-ді тасиды: "feedback_result"
    # (оқушы авторлық бағандары) және "teacher_assessment" (мұғалім
    # бағандары) — § database.py/sqlite_feedback_repository.py
    # докстрингтері: екеуі ЕШҚАШАН бір-бірінің бағандарын ЖОймайды,
    # сол принцип sync payload-та да сақталады (§ Phase 2 Final Report
    # "7. Feedback synchronization").

    @abstractmethod
    def get_feedback_sync_payload(self, session_id: str) -> dict | None:
        """Тек оқушы авторлық бағандарын (level1/2/3, is_draft,
        submitted_at) сым (wire) payload түрінде қайтарады."""
        raise NotImplementedError

    @abstractmethod
    def apply_remote_feedback(self, payload: dict) -> None:
        """§18 "Pull Sync" — тек оқушы авторлық бағандарды жазады,
        ``teacher_score``/``teacher_comment``/``teacher_reviewed``
        бағандарын ЕШҚАШАН тимейді (§ ``_save()``-пен БІРДЕЙ принцип).
        ЕШБІР outbox жазуы ЖАСАЛМАЙДЫ."""
        raise NotImplementedError

    @abstractmethod
    def mark_feedback_synced(self, session_id: str, server_revision: int) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_teacher_assessment_sync_payload(self, session_id: str) -> dict | None:
        """Тек мұғалім бағандарын қайтарады — ``teacher_score is None``
        (әлі бағаланбаған) болса ``None`` (§ синхрондауға ЕШБІР мән жоқ)."""
        raise NotImplementedError

    @abstractmethod
    def apply_remote_teacher_assessment(self, payload: dict) -> None:
        """§18 "Pull Sync" — тек мұғалім бағандарын жазады, оқушы
        авторлық бағандарды ЕШҚАШАН тимейді (§ ``save_teacher_
        assessment()``-пен БІРДЕЙ принцип). ЕШБІР outbox жазуы
        ЖАСАЛМАЙДЫ."""
        raise NotImplementedError

    @abstractmethod
    def mark_teacher_assessment_synced(self, session_id: str, server_revision: int) -> None:
        raise NotImplementedError

    @abstractmethod
    def enqueue_feedback_for_sync(self, session_id: str) -> None:
        """§ Phase 2 backfill: ескі кері байланыс жазбаларын outbox-қа
        қосу үшін."""
        raise NotImplementedError

    @abstractmethod
    def enqueue_teacher_assessment_for_sync(self, session_id: str) -> None:
        """§ Phase 2 backfill — тек ``teacher_score is not None``
        (нақты бағаланған) жазбалар үшін мәнді."""
        raise NotImplementedError
