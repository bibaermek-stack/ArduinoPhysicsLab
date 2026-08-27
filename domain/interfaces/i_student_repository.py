"""IStudentRepository — жергілікті оқушыларды сақтау/оқу интерфейсі
(Phase 39B). ``IClassroomRepository``-мен БІРДЕЙ рөл-қорғаныс принципі."""

from abc import ABC, abstractmethod

from domain.entities.student import Student
from domain.entities.user_role import UserRole


class IStudentRepository(ABC):
    @abstractmethod
    def create(self, student: Student, role: UserRole) -> None:
        raise NotImplementedError

    @abstractmethod
    def update(self, student: Student, role: UserRole) -> None:
        raise NotImplementedError

    @abstractmethod
    def archive(self, student_id: str, role: UserRole, archived: bool = True) -> None:
        raise NotImplementedError

    @abstractmethod
    def get(self, student_id: str) -> Student | None:
        raise NotImplementedError

    @abstractmethod
    def list_by_classroom(self, classroom_id: str, include_archived: bool = False) -> tuple[Student, ...]:
        """Берілген сыныптағы оқушыларды тегі/аты бойынша сұрыпталған
        қайтарады.
        """
        raise NotImplementedError

    @abstractmethod
    def search(self, classroom_id: str, query: str) -> tuple[Student, ...]:
        """``display_name`` немесе ``student_code`` бойынша (регистрге
        сезімтал емес, ішінара сәйкестік) сүзеді — мұрағатталғандар
        ешқашан қайтарылмайды.
        """
        raise NotImplementedError

    @abstractmethod
    def code_exists(self, student_code: str, exclude_student_id: str | None = None) -> bool:
        """Берілген (бос емес) ``student_code``-тың кез келген белсенді
        (мұрағатталмаған) оқушыда — БАРЛЫҚ сыныптар бойынша — қолданылып
        тұрғанын тексереді (мектеп ішінде бірегей код есептеледі, тек бір
        сыныпта емес) — қайталама код қабылданбауы үшін.
        """
        raise NotImplementedError

    @abstractmethod
    def get_by_code(self, student_code: str) -> Student | None:
        """Оқушы кіру кодын нақты (дәл) сәйкестендіру арқылы іздейді —
        тек белсенді (мұрағатталмаған) оқушылар арасында (§ "repository
        lookup must be exact", "an invalid code" — мұрағатталған оқушы
        кодымен кіру де жарамсыз деп есептеледі). Табылмаса ``None``.
        """
        raise NotImplementedError
