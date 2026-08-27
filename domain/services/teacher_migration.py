"""teacher_migration — ескі бір-мұғалімдік PIN конфигурациясынан
Multi-Teacher Accounts моделіне қауіпсіз, идемпотентті бір реттік
көшу (§20 "First Teacher / Backward Compatibility").

``backfill_missing_student_codes()``-пен БІРДЕЙ принцип — ``app.py``
ЖӘНЕ ``MainWindow`` екеуі де осыны шақырады, идемпотентті болғандықтан
қайталап шақыру қауіпсіз (қолданбаны бірнеше рет іске қосу мұғалімдерді
ЕШҚАШАН қайталамайды/тағайындауларды қалпына келтірмейді/PIN-дерді
ысырмайды).
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from domain.entities.teacher import Teacher
from domain.interfaces.i_classroom_repository import IClassroomRepository
from domain.interfaces.i_teacher_repository import ITeacherRepository
from domain.services.teacher_pin import get_configured_pin_hash

_DEFAULT_TEACHER_NAME = "Бастапқы мұғалім"


def backfill_default_teacher(
    teacher_repository: ITeacherRepository,
    classroom_repository: IClassroomRepository,
) -> Teacher | None:
    """``teachers`` кестесі БОС болса (§ "if there is an existing teacher
    PIN but no Teacher record yet"), ескі жалғыз-PIN конфигурациясының
    (``APL_TEACHER_PIN``/dev әдепкісі "1234") хэшімен БІР дефолт
    ``Teacher`` жазбасын құрады, барлық қолданыстағы сыныпты соған
    тағайындайды (§ "Do not lose access to Teacher Mode after the
    migration" — көшуден кейін дәл сол PIN, дәл сол толық қолжетімділік
    жұмыс істеуі керек).

    ``teachers`` кестесінде КЕМ ДЕГЕНДЕ бір жазба болса, ЕШТЕҢЕ
    жасамайды (идемпотентті) — мұғалімдер ЕШҚАШАН қайталанбайды.
    Жаңадан құрылған жазбаны қайтарады (немесе миграция қажет
    болмаса ``None``).
    """
    if teacher_repository.list_all():
        return None

    now = datetime.now(timezone.utc)
    teacher = Teacher(
        id=str(uuid4()),
        full_name=_DEFAULT_TEACHER_NAME,
        pin_hash=get_configured_pin_hash(),
        created_at=now,
        updated_at=now,
        is_active=True,
    )
    all_classroom_ids = tuple(classroom.id for classroom in classroom_repository.list_all())
    teacher_repository.create(teacher, assigned_classroom_ids=all_classroom_ids)
    return teacher
