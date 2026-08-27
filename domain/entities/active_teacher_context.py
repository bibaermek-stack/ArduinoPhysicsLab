"""ActiveTeacherContext — ағымдағы қолданба сессиясында аутентификацияланған
мұғалім (Multi-Teacher Accounts фазасы).

``ActiveStudentContext``-пен БІРДЕЙ принцип — тек ID сақтайды (``Teacher``-дің
толық жазбасы емес), ``IActiveTeacherRepository`` арқылы ``ITeacherRepository``-мен
бірге ажыратылады.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ActiveTeacherContext:
    teacher_id: str
