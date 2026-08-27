"""student_access_control — сынып/оқушы деректеріне қатысты рөл негізіндегі
рұқсат тексерулері (Phase 39B).

Phase 39A-дың ``apply_teacher_assessment()``-пен БІРДЕЙ принцип: бұл таза
функциялар "рұқсат-гейт-ты тек UI-де жасырмау" талабының домен-деңгейлік
жартысы — ``SqliteClassroomRepository``/``SqliteStudentRepository``-дың
жазу әдістері осыларды шақырады (репозиторий деңгейінде ЕКІНШІ, тәуелсіз
қорғаныс сызығы), UI виджеттері Мұғалім рөлінде ҒАНА құрылады.
"""

from __future__ import annotations

from domain.entities.user_role import UserRole


def ensure_can_manage_classroom_data(role: UserRole) -> None:
    """Сынып/оқушы жазбаларын құру/өзгерту/мұрағаттау тек Мұғалім
    режимінде рұқсат етіледі.
    """
    if role is not UserRole.TEACHER:
        raise PermissionError(
            "Сынып/оқушы деректерін тек Мұғалім режимінде басқаруға болады"
        )


def ensure_can_save_teacher_assessment(role: UserRole) -> None:
    """Мұғалім бағасын сақтау тек Мұғалім режимінде рұқсат етіледі."""
    if role is not UserRole.TEACHER:
        raise PermissionError(
            "Мұғалім бағасын тек Мұғалім режимінде сақтауға болады"
        )


def ensure_can_manage_questions(role: UserRole) -> None:
    """Question Bank сұрақтарын құру/өзгерту/мұрағаттау тек Мұғалім
    режимінде рұқсат етіледі (Phase 20) — ``ensure_can_manage_classroom_
    data()``-пен БІРДЕЙ принцип."""
    if role is not UserRole.TEACHER:
        raise PermissionError(
            "Сұрақтар банкін тек Мұғалім режимінде басқаруға болады"
        )


def ensure_can_view_student(
    role: UserRole, requested_student_id: str, active_student_id: str | None
) -> None:
    """Оқушы режимінде тек ӨЗ ``active_student_id``-ін қарауға болады —
    тікелей UI әрекеті арқылы басқа оқушыны сұрау болдырмайды.
    """
    if role is UserRole.TEACHER:
        return
    if active_student_id is None or requested_student_id != active_student_id:
        raise PermissionError(
            "Оқушы режимінде тек өз нәтижелеріңізді қарауға болады"
        )
