"""teacher_scope — ағымдағы аутентификацияланған мұғалімге рұқсат
етілген сынып ID жиынын шешу (Multi-Teacher Accounts фазасы).

``TeacherScopedClassroomRepository`` (сынып/оқушы шолу үшін) ЖӘНЕ
Бақылау тақтасы/Аналитика/Нәтижелер/Кері байланысты тексеру беттері
(жинақы сандар/тізімдер үшін) БІРДЕЙ осы функцияны шақырады — екі жерде
де "рұқсат етілген сынып" анықтамасы ЕШҚАШАН алшақтамайды.
"""

from __future__ import annotations

from domain.interfaces.i_active_teacher_repository import IActiveTeacherRepository
from domain.interfaces.i_teacher_repository import ITeacherRepository


def resolve_allowed_classroom_ids(
    teacher_repository: ITeacherRepository,
    active_teacher_repository: IActiveTeacherRepository,
) -> frozenset[str] | None:
    """Ағымдағы аутентификацияланған мұғалімге тағайындалған сынып
    ID жиынын қайтарады. Аутентификацияланған мұғалім ЖОҚ болса (§ ескі/
    тестілік конфигурация, немесе ``Teacher`` жазбасы әлі табылмаса)
    ``None`` қайтарады — "шектеусіз" дегенді білдіреді (§ backward
    compatibility, ЕШБІР қолданыстағы шақырушы бұзылмайды).
    """
    context = active_teacher_repository.get()
    if context is None:
        return None
    teacher = teacher_repository.get(context.teacher_id)
    if teacher is None:
        return None
    return frozenset(teacher_repository.list_assigned_classroom_ids(teacher.id))
