"""IQuestionRepository — Question Bank (Phase 20) сұрақтарын сақтау/оқу
интерфейсі.

``IClassroomRepository``/``IStudentRepository``-мен БІРДЕЙ принцип: тек
domain entity (``QuestionRecord``) және таза Python типтерімен жұмыс
істейді, жазу әдістері ``role: UserRole`` қабылдайды (Мұғалім емес
рөлден шақырылса ``PermissionError``). Нақты іске асыру
``infrastructure/storage/sqlite_question_repository.py``-де.
"""

from abc import ABC, abstractmethod

from domain.entities.question_record import QuestionRecord
from domain.entities.user_role import UserRole


class IQuestionRepository(ABC):
    @abstractmethod
    def create(self, record: QuestionRecord, role: UserRole) -> None:
        """Жаңа сұрақ жазбасын сақтайды."""
        raise NotImplementedError

    @abstractmethod
    def update(self, record: QuestionRecord, role: UserRole) -> None:
        """Бар сұрақ жазбасын (``record.id`` бойынша) жаңартады."""
        raise NotImplementedError

    @abstractmethod
    def archive(self, question_id: str, role: UserRole, archived: bool = True) -> None:
        """Сұрақты мұрағаттайды (``archived=False`` — қалпына келтіру).
        Hard delete ЖОҚ — тарихи оқушы жауаптары ``question_id`` арқылы
        сілтеме жасайды, сондықтан жол ЕШҚАШАН физикалық өшірілмейді.
        """
        raise NotImplementedError

    @abstractmethod
    def get(self, question_id: str) -> QuestionRecord | None:
        raise NotImplementedError

    @abstractmethod
    def list_all(self, include_archived: bool = False) -> tuple[QuestionRecord, ...]:
        """Барлық сұрақтарды ``(experiment_id, level, created_at)`` бойынша
        тұрақты (stable) ретпен қайтарады."""
        raise NotImplementedError

    @abstractmethod
    def list_for_experiment(
        self, experiment_id: str, include_archived: bool = False
    ) -> tuple[QuestionRecord, ...]:
        """Берілген тәжірибенің сұрақтарын ``(level, created_at)`` бойынша
        тұрақты ретпен қайтарады."""
        raise NotImplementedError
