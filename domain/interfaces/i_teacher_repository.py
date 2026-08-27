"""ITeacherRepository — мұғалім аккаунттарын және мұғалім↔сынып
байланысын сақтау/оқу интерфейсі (Multi-Teacher Accounts фазасы).

``IClassroomRepository``/``IStudentRepository``-мен БІРДЕЙ пішін — тек
domain entity (``Teacher``) және таза Python типтерімен жұмыс істейді,
нақты іске асыру ``infrastructure/storage/sqlite_teacher_repository.py``-де.

Мұғалім↔сынып байланысы көп-көпке (many-to-many) — бір сынып бірнеше
мұғалімге қолжетімді бола алады (§ "A class may be accessible by more
than one teacher if required"), ``Classroom`` жазбасының ӨЗІ ЕШҚАШАН
қайталанбайды/өзгертілмейді, тек жеке байланыс кестесі арқылы.
"""

from abc import ABC, abstractmethod

from domain.entities.teacher import Teacher


class ITeacherRepository(ABC):
    @abstractmethod
    def create(self, teacher: Teacher, assigned_classroom_ids: tuple[str, ...] = ()) -> None:
        """Жаңа мұғалім жазбасын сақтайды, бір мезгілде тағайындалған
        сыныптар байланысын да орнатады (§ "Add Teacher" формасы аты/PIN/
        сыныптарды бір әрекетте жібереді)."""
        raise NotImplementedError

    @abstractmethod
    def update(self, teacher: Teacher) -> None:
        """Бар мұғалім жазбасын (``teacher.id`` бойынша) жаңартады —
        аты-жөні/``is_active``/``pin_hash``. Сынып тағайындауларына
        ЕШБІР қатысы жоқ (§ ``set_assigned_classroom_ids()`` бөлек)."""
        raise NotImplementedError

    @abstractmethod
    def get(self, teacher_id: str) -> Teacher | None:
        raise NotImplementedError

    @abstractmethod
    def list_all(self) -> tuple[Teacher, ...]:
        """Барлық мұғалімдерді (белсенді еместі ҚОСА) аты-жөні бойынша
        сұрыпталған қайтарады — Мұғалімдерді басқару бетінің толық
        тізімі үшін."""
        raise NotImplementedError

    @abstractmethod
    def list_active(self) -> tuple[Teacher, ...]:
        """Тек белсенді мұғалімдерді қайтарады (§ PIN кіру іздеуі осыны
        қолданады — белсенді емес мұғалім ЕШҚАШАН кіре алмайды)."""
        raise NotImplementedError

    @abstractmethod
    def pin_hash_exists(self, pin_hash: str, exclude_teacher_id: str | None = None) -> bool:
        """Берілген ``pin_hash``-тың кез келген белсенді мұғалімде
        қолданылып тұрғанын тексереді (§ "PIN must be unique per active
        teacher")."""
        raise NotImplementedError

    @abstractmethod
    def set_assigned_classroom_ids(self, teacher_id: str, classroom_ids: tuple[str, ...]) -> None:
        """Мұғалімнің тағайындалған сыныптар жиынын ТОЛЫҚ алмастырады
        (§ Add/Edit Teacher форм-дары "таңдалған чекбокстар" күйін
        тікелей бір әрекетте жібереді — жеке қосу/алу diff-і қажет
        емес)."""
        raise NotImplementedError

    @abstractmethod
    def list_assigned_classroom_ids(self, teacher_id: str) -> tuple[str, ...]:
        raise NotImplementedError

    @abstractmethod
    def list_teacher_ids_for_classroom(self, classroom_id: str) -> tuple[str, ...]:
        """Берілген сыныпқа қолжетімді барлық мұғалім ID-ін қайтарады
        (§ "A class may be accessible by more than one teacher")."""
        raise NotImplementedError
