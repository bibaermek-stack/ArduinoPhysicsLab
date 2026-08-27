"""Student — Мұғалім жасайтын жергілікті оқушы жазбасы (Phase 39B).

``classroom_id`` арқылы ``Classroom``-ға жатады. Аутентификация/пароль
ЖОҚ — оқушы тек локальды тізімнен таңдалады (§ "Do not fabricate student
identity", § "Do not implement student authentication").
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from domain.entities.sync_state import SyncState


@dataclass(frozen=True)
class Student:
    """Бір оқушы жазбасы. ``is_archived=True`` болса, қалыпты таңдау
    тізімдерінде (Оқушыны таңдау, Сыныптар мен оқушылар) көрсетілмейді.

    § Offline-First + Cloud Sync Foundation: ``sync_id``/``sync_state``/
    ``server_revision`` — § ``domain/entities/classroom.py``
    докстрингіндегі БІРДЕЙ принцип.
    """

    id: str
    classroom_id: str
    first_name: str
    last_name: str
    created_at: datetime
    updated_at: datetime
    middle_name: str = ""
    student_code: str = ""
    notes: str = ""
    is_archived: bool = False
    sync_id: str = ""
    sync_state: SyncState = SyncState.PENDING_UPLOAD
    server_revision: int | None = None

    @property
    def display_name(self) -> str:
        """"Тегі Аты" пішімі — тізімдерде/индикаторда бірізді қолданылады."""
        return f"{self.last_name} {self.first_name}".strip()

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.id:
            errors.append("Student.id бос болмауы керек")
        if not self.classroom_id:
            errors.append("Student.classroom_id бос болмауы керек")
        if not self.first_name.strip():
            errors.append("Оқушының аты бос болмауы керек")
        if not self.last_name.strip():
            errors.append("Оқушының тегі бос болмауы керек")
        return errors
