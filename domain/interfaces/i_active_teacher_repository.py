"""IActiveTeacherRepository — ағымдағы аутентификацияланған мұғалім
контексін сақтау/оқу интерфейсі (Multi-Teacher Accounts фазасы).

``IActiveStudentRepository``-мен БІРДЕЙ жалғыз-жол принципі. Жазу тек
``RoleSelectionPage``-тің teacher-login ағынынан (PIN расталғаннан
кейін) немесе ``MainWindow``-дың "Режімді ауыстыру"/logout әрекетінен
(``clear()``) келеді.
"""

from abc import ABC, abstractmethod

from domain.entities.active_teacher_context import ActiveTeacherContext


class IActiveTeacherRepository(ABC):
    @abstractmethod
    def set(self, context: ActiveTeacherContext) -> None:
        raise NotImplementedError

    @abstractmethod
    def get(self) -> ActiveTeacherContext | None:
        raise NotImplementedError

    @abstractmethod
    def clear(self) -> None:
        raise NotImplementedError
