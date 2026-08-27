"""ITeacherNoteRepository — мұғалімнің оқушыға жіберетін қысқа
пікірлерін сақтау/оқу интерфейсі (Phase 7).

``IFeedbackRepository``-мен БІРДЕЙ принцип: бұл модуль ешбір storage
технологиясын білмейді, тек ``TeacherNote`` domain entity-мен жұмыс
істейді. Нақты іске асыру ``infrastructure/storage/
sqlite_teacher_note_repository.py``-де.
"""

from abc import ABC, abstractmethod

from domain.entities.teacher_note import TeacherNote
from domain.entities.user_role import UserRole


class ITeacherNoteRepository(ABC):
    @abstractmethod
    def create(self, note: TeacherNote, role: UserRole) -> None:
        """Жаңа пікір жазады. ``role`` міндетті түрде ``UserRole.TEACHER``
        болуы керек — Оқушы режимінен тікелей шақырылса ``PermissionError``
        шығарады (§ ``save_teacher_assessment()``-пен БІРДЕЙ қорғаныс
        сызығы)."""
        raise NotImplementedError

    @abstractmethod
    def list_for_student(self, student_id: str) -> tuple[TeacherNote, ...]:
        """Берілген оқушыға жіберілген БАРЛЫҚ пікірді ``created_at``
        өсу ретімен қайтарады (§ "a feed, not a single slot")."""
        raise NotImplementedError

    @abstractmethod
    def mark_read(self, note_id: str, role: UserRole) -> None:
        """``read_at`` орнатады (ЕГЕР әлі орнатылмаса — идемпотентті,
        § "repeated sync must not regress read state"). ``role``
        міндетті түрде ``UserRole.STUDENT`` болуы керек. § ЖЕРГІЛІКТІ-
        тек мутация — ЕШБІР outbox жазуы жасалмайды (§ ``domain/
        entities/teacher_note.py`` докстрингі — "read_at" ешқашан
        синхрондалмайды)."""
        raise NotImplementedError

    # ---- Cloud Sync (Phase 7) --------------------------------------------
    #
    # Тек мұғалім авторлық жартысы синхрондалады (id/teacher_id/
    # student_id/classroom_id/experiment_id/session_id/message/
    # created_at) — ``read_at`` ЕШҚАШАН осы payload-та ЖОҚ.

    @abstractmethod
    def get_note_sync_payload(self, note_id: str) -> dict | None:
        raise NotImplementedError

    @abstractmethod
    def apply_remote_note(self, payload: dict) -> None:
        """§18 "Pull Sync" — ЕШБІР outbox жазуы ЖАСАЛМАЙДЫ."""
        raise NotImplementedError

    @abstractmethod
    def mark_note_synced(self, note_id: str, server_revision: int) -> None:
        raise NotImplementedError

    @abstractmethod
    def enqueue_note_for_sync(self, note_id: str) -> None:
        raise NotImplementedError
