"""IClassroomRepository — жергілікті сыныптарды сақтау/оқу интерфейсі
(Phase 39B).

``ISessionRepository``/``IFeedbackRepository``-мен БІРДЕЙ принцип: тек
domain entity (``Classroom``) және таза Python типтерімен жұмыс істейді.
Нақты іске асыру ``infrastructure/storage/sqlite_classroom_repository.py``-де.
Жазу әдістері ``role: UserRole`` қабылдайды — Мұғалім емес рөлден
шақырылса ``PermissionError`` шығарады (``domain.services.
student_access_control.ensure_can_manage_classroom_data()`` арқылы,
UI-дан тыс екінші қорғаныс сызығы).
"""

from abc import ABC, abstractmethod

from domain.entities.classroom import Classroom
from domain.entities.user_role import UserRole


class IClassroomRepository(ABC):
    @abstractmethod
    def create(self, classroom: Classroom, role: UserRole) -> None:
        """Жаңа сынып жазбасын сақтайды."""
        raise NotImplementedError

    @abstractmethod
    def update(self, classroom: Classroom, role: UserRole) -> None:
        """Бар сынып жазбасын (``classroom.id`` бойынша) жаңартады."""
        raise NotImplementedError

    @abstractmethod
    def archive(self, classroom_id: str, role: UserRole, archived: bool = True) -> None:
        """Сыныпты мұрағаттайды (``archived=False`` — қалпына келтіру).
        Hard delete жоқ.
        """
        raise NotImplementedError

    @abstractmethod
    def get(self, classroom_id: str) -> Classroom | None:
        raise NotImplementedError

    @abstractmethod
    def list_active(self) -> tuple[Classroom, ...]:
        """Мұрағатталмаған сыныптарды атауы бойынша сұрыпталған
        қайтарады (қалыпты таңдау тізімдері үшін).
        """
        raise NotImplementedError

    @abstractmethod
    def list_all(self) -> tuple[Classroom, ...]:
        """Мұрағатталғандарды ҚОСА барлық сыныптарды қайтарады
        (Сыныптар мен оқушылар бетінің толық тізімі үшін).
        """
        raise NotImplementedError
