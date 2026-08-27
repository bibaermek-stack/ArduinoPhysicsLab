"""IActiveStudentRepository — ағымдағы белсенді оқушы контексін
сақтау/оқу интерфейсі (Phase 39B).

Жалғыз жол (``active_student_state``, ``id=1``) — ешбір рөл-тексеру
жоқ (жазу тек ``StudentSelectionPage``/Sidebar-дың "Оқушыны ауыстыру"
ағынынан келеді, екеуі де Оқушы режимінде ғана қолжетімді UI деңгейінде;
доменде қосымша қорғау қажет емес, себебі бұл "кім екенін таңдау" ғана,
жазу/бағалау әрекеті емес).
"""

from abc import ABC, abstractmethod

from domain.entities.active_student_context import ActiveStudentContext


class IActiveStudentRepository(ABC):
    @abstractmethod
    def set(self, context: ActiveStudentContext) -> None:
        raise NotImplementedError

    @abstractmethod
    def get(self) -> ActiveStudentContext | None:
        raise NotImplementedError

    @abstractmethod
    def clear(self) -> None:
        raise NotImplementedError
