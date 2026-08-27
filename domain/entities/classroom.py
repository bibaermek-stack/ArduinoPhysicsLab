"""Classroom — Мұғалім жасайтын жергілікті сынып жазбасы (Phase 39B).

Бұл модуль ешбір SQL/Qt білмейді — таза domain entity, ``ExperimentGuide``/
``ExperimentReport``-пен БІРДЕЙ frozen-dataclass + ``validate()`` конвенциясы.
Нақты сақтау ``infrastructure/storage/sqlite_classroom_repository.py``-де.

§ Offline-First + Cloud Sync Foundation: ``sync_id``/``sync_state``/
``server_revision`` — Cloud Sync-пен қатысты өрістер (§ ``domain/
entities/sync_state.py`` докстрингі). ``id`` (жергілікті PK) ӨЗГЕРІССІЗ
қалады — ``sync_id`` жасалу сәтінде ӘДЕПКІ бойынша ``id``-мен БІРДЕЙ
мәнге ие болады (§ "local primary key may remain unchanged... add a
stable sync/global identifier"), бірақ болашақта ажырата алатын БӨЛЕК
өріс.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from domain.entities.sync_state import SyncState


@dataclass(frozen=True)
class Classroom:
    """Бір сынып жазбасы. ``is_archived=True`` болса, қалыпты
    таңдау тізімдерінде (Оқушыны таңдау/Сынып қосу) көрсетілмейді —
    hard delete жоқ, тек мұрағаттау/қалпына келтіру.
    """

    id: str
    name: str
    created_at: datetime
    updated_at: datetime
    academic_year: str = ""
    description: str = ""
    is_archived: bool = False
    sync_id: str = ""
    sync_state: SyncState = SyncState.PENDING_UPLOAD
    server_revision: int | None = None

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.id:
            errors.append("Classroom.id бос болмауы керек")
        if not self.name.strip():
            errors.append("Сынып атауы бос болмауы керек")
        return errors
