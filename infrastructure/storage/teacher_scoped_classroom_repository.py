"""TeacherScopedClassroomRepository — ``IClassroomRepository``-ді
ағымдағы аутентификацияланған мұғалімнің тағайындалған сыныптарымен
шектейтін decorator (Multi-Teacher Accounts фазасы, §6 "Data Ownership
/ Filtering").

Жазу/бір жазбалық оқу әдістері (``create``/``update``/``archive``/
``get``) ІШКІ репозиторийге ӨЗГЕРІССІЗ бағытталады — тек тізім қайтаратын
``list_active()``/``list_all()`` ағымдағы мұғалімнің меншікті
сыныптарымен сүзіледі. Бұл ЖАЛҒЫЗ орын — ``ClassManagementPage``/
``TeacherDashboardPage``/``AnalyticsPage``/``ResultsPage``/
``TeacherFeedbackReviewPage``/``DataJournalPage`` беттерінің ІШКІ
логикасы МҮЛДЕ ӨЗГЕРТІЛМЕЙДІ — олар осы decorator-ды қарапайым
``IClassroomRepository`` ретінде қабылдайды (§ "extend the existing
architecture instead of creating a disconnected second database").
"""

from __future__ import annotations

from domain.entities.classroom import Classroom
from domain.entities.user_role import UserRole
from domain.interfaces.i_active_teacher_repository import IActiveTeacherRepository
from domain.interfaces.i_classroom_repository import IClassroomRepository
from domain.interfaces.i_teacher_repository import ITeacherRepository
from domain.services.teacher_scope import resolve_allowed_classroom_ids


class TeacherScopedClassroomRepository(IClassroomRepository):
    def __init__(
        self,
        inner: IClassroomRepository,
        teacher_repository: ITeacherRepository,
        active_teacher_repository: IActiveTeacherRepository,
    ) -> None:
        self._inner = inner
        self._teacher_repository = teacher_repository
        self._active_teacher_repository = active_teacher_repository

    # ---- Өзгеріссіз бағытталатын әдістер --------------------------------

    def create(self, classroom: Classroom, role: UserRole) -> None:
        self._inner.create(classroom, role)

    def update(self, classroom: Classroom, role: UserRole) -> None:
        self._inner.update(classroom, role)

    def archive(self, classroom_id: str, role: UserRole, archived: bool = True) -> None:
        self._inner.archive(classroom_id, role, archived)

    def get(self, classroom_id: str) -> Classroom | None:
        return self._inner.get(classroom_id)

    # ---- Мұғалімге сүзілген тізімдер -------------------------------------

    def list_active(self) -> tuple[Classroom, ...]:
        return self._filtered(self._inner.list_active())

    def list_all(self) -> tuple[Classroom, ...]:
        return self._filtered(self._inner.list_all())

    def _filtered(self, classrooms: tuple[Classroom, ...]) -> tuple[Classroom, ...]:
        allowed_ids = resolve_allowed_classroom_ids(
            self._teacher_repository, self._active_teacher_repository
        )
        if allowed_ids is None:
            return classrooms
        return tuple(classroom for classroom in classrooms if classroom.id in allowed_ids)
