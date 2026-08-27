"""Teacher — жүйені пайдаланатын мұғалім жазбасы (Multi-Teacher Accounts
фазасы).

``Student``-пен БІРДЕЙ frozen-dataclass + ``validate()`` конвенциясы.
PIN мәтіні ЕШҚАШАН осы entity-де сақталмайды — тек ``pin_hash`` (§
``domain/services/teacher_pin.py::hash_pin()``, SHA-256), нақты сол
себеппен ``Student.student_code``-тен ерекшеленеді (оқушы коды ашық
мәтін ретінде сақталады — қатаң аутентификация емес, ал мұғалім PIN-і
жүйеге ЖАЗУ құқығын береді, § "do not store PIN as plain text").
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from domain.entities.sync_state import SyncState


@dataclass(frozen=True)
class Teacher:
    """Бір мұғалім жазбасы. ``is_active=False`` болса, PIN арқылы кіру
    ЕШҚАШАН сәтті болмайды (§ "disabled teacher PIN must no longer allow
    login") — hard delete жоқ, тек белсенді/белсенді емес.

    § Offline-First + Cloud Sync Foundation: ``sync_id``/``sync_state``/
    ``server_revision`` — § ``domain/entities/classroom.py``
    докстрингіндегі БІРДЕЙ принцип. ``pin_hash`` ЕШҚАШАН серверге
    ЖІБЕРІЛМЕЙДІ/логталмайды (§ "24. Logging" — synced payload-тан
    әдейі алынып тасталады, § ``domain/services/sync_payload.py``).
    """

    id: str
    full_name: str
    pin_hash: str
    created_at: datetime
    updated_at: datetime
    is_active: bool = True
    sync_id: str = ""
    sync_state: SyncState = SyncState.PENDING_UPLOAD
    server_revision: int | None = None

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.id:
            errors.append("Teacher.id бос болмауы керек")
        if not self.full_name.strip():
            errors.append("Мұғалімнің аты-жөні бос болмауы керек")
        if not self.pin_hash:
            errors.append("Teacher.pin_hash бос болмауы керек")
        return errors
