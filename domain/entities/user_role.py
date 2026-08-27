"""UserRole — қолданбаның екі рөлі (Оқушы/Мұғалім).

Phase 37A: рөл тек осы typed enum арқылы ұсынылады — жасырын
widget-күйі немесе ерікті жол (string) арқылы ЕМЕС. ``.value`` болашақ
сериализация/лог үшін тұрақты жол береді, бірақ бұл модуль өзі ешбір
persistence жасамайды (Phase 37A: рөл сессиялар арасында сақталмайды).
"""

from enum import Enum


class UserRole(Enum):
    STUDENT = "student"
    TEACHER = "teacher"
