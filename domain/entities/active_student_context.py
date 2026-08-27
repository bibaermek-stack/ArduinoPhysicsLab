"""ActiveStudentContext — ағымдағы қолданба сессиясында таңдалған оқушы
(Phase 39B).

Тек екі ID сақтайды — ``Classroom``/``Student``-тің толық жазбасы емес,
солардың кілттері ғана (``IActiveStudentRepository`` арқылы
``IClassroomRepository``/``IStudentRepository``-мен бірге ажыратылады).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ActiveStudentContext:
    classroom_id: str
    student_id: str
