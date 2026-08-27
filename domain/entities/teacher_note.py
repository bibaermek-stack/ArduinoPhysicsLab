"""TeacherNote — мұғалімнің оқушыға жіберетін қысқа пікірі/ескертпесі
(Phase 7: Teacher Actions, Feedback Delivery, and Session History).

``ExperimentFeedbackResult``/``TeacherAssessment``-тен (Phase 39A)
ӘДЕЙІ БӨЛЕК, ЖАҢА тұжырымдама — ол "оқушы жіберген есепті мұғалім
бағалайды" ағынына арналған (сессияға БІР ғана жазба), ал бұл жаңа
``TeacherNote`` "мұғалім оқушыға кез келген сәтте қысқа хабар
жібереді" ағыны (бір оқушыға УАҚЫТ бойынша КӨП жазба, § "a feed, not a
single graded slot"). Екеуін БІР кестеге қосу оларды МҮЛДЕ ӘРТҮРЛІ
концепцияларды жасанды түрде біріктірер еді — сол себепті жаңа, кіші,
аддитивті кесте (§ ``infrastructure/storage/database.py``).

``read_at`` — ТЕК ЖЕРГІЛІКТІ, ешқашан синхрондалмайды (§ ХАЛАЛ
(honest) шектеу): мұғалім жаққа "оқылды" күйін шынайы жеткізу үшін
``experiment_feedback``-тегідей екінші, тәуелсіз синхрондалатын жарты
керек болар еді (§ "two independent halves of one row" паттерні) — бұл
Phase 7-де ӘДЕЙІ КЕЙІНГЕ қалдырылды (§ docs/sync_architecture.md
"Delivery/read semantics" бөлімі). Мұғалім жағы тек ``sync_state``
(§ ``SqliteTeacherNoteRepository`` — "Жіберілуде"/"Жеткізілді") арқылы
шынайы жеткізу күйін көреді, ЕШҚАШАН жалған "оқылды" күйін көрсетпейді.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from domain.entities.sync_state import SyncState


@dataclass(frozen=True)
class TeacherNote:
    id: str
    teacher_id: str
    student_id: str
    classroom_id: str
    message: str
    created_at: datetime
    experiment_id: str | None = None
    session_id: str | None = None
    # § жергілікті-тек, синхрондалмайды (докстрингті қара).
    read_at: datetime | None = None
    # § ``Student``/``Classroom``/``Teacher``-мен БІРДЕЙ конвенция —
    # мұғалім жағының "Жіберілуде"/"Жеткізілді" КҮЙІН шынайы көрсету
    # үшін (§ docs/sync_architecture.md "Delivery/read semantics").
    sync_state: SyncState = SyncState.PENDING_UPLOAD

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.id:
            errors.append("TeacherNote.id бос болмауы керек")
        if not self.teacher_id:
            errors.append("TeacherNote.teacher_id бос болмауы керек")
        if not self.student_id:
            errors.append("TeacherNote.student_id бос болмауы керек")
        if not self.classroom_id:
            errors.append("TeacherNote.classroom_id бос болмауы керек")
        if not self.message.strip():
            errors.append("TeacherNote.message бос болмауы керек")
        return errors
