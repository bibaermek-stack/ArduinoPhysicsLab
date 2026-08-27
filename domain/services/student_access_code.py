"""student_access_code — оқушының кіру коды генерациясы/backfill-і
(Phase — Mode Switch + Student Access Screen Redesign).

``Student.student_code`` (§ ``domain/entities/student.py``) бұрыннан бар
өріс — жаңа кесте/баған қажет ЕМЕС (§ "least invasive safe format after
auditing current schema"). Бұл модуль тек: (1) бірегей кодты кездейсоқ
генерациялайды (``code_exists()`` арқылы қақтығысты тексеріп), (2) кодсыз
қалған (бос ``student_code``) қолданыстағы оқушыларға бір реттік,
ЕШҚАШАН деструктивті ЕМЕС backfill жасайды — ``domain/services/
question_bank_seed.py``-мен БІРДЕЙ "idempotent one-time seed, called from
MainWindow.__init__" конвенциясы.

Код форматы: 6 таңбалы кездейсоқ сандық жол (мыс. "482731"). ``student_id``-
ден, жол ретінен (0001, 0002...) немесе Python ``hash()``-тен ЕШҚАШАН
туындамайды — тек ``secrets``-негізді кездейсоқтық + нақты репозиторий
арқылы қақтығыс тексеруі (§ "Do NOT use: student_id directly, sequential
numbers, Python hash()").
"""

from __future__ import annotations

import secrets
from dataclasses import replace
from datetime import datetime, timezone

from domain.entities.user_role import UserRole
from domain.interfaces.i_classroom_repository import IClassroomRepository
from domain.interfaces.i_student_repository import IStudentRepository

_CODE_LENGTH = 6
_CODE_DIGITS = "0123456789"
_MAX_GENERATION_ATTEMPTS = 50


def generate_unique_student_code(student_repository: IStudentRepository) -> str:
    """6 таңбалы кездейсоқ сандық кодты, ``code_exists()`` арқылы
    қақтығыс тексеріп, генерациялайды. ``secrets.choice`` криптографиялық
    сапалы генератор — Python ``random``/``hash()`` ЕМЕС.
    """
    for _ in range(_MAX_GENERATION_ATTEMPTS):
        code = "".join(secrets.choice(_CODE_DIGITS) for _ in range(_CODE_LENGTH))
        if not student_repository.code_exists(code):
            return code
    raise RuntimeError(
        f"{_MAX_GENERATION_ATTEMPTS} әрекеттен кейін де бірегей оқушы коды табылмады"
    )


def backfill_missing_student_codes(
    classroom_repository: IClassroomRepository,
    student_repository: IStudentRepository,
) -> int:
    """Кодсыз қалған (``student_code == ""``) БАРЛЫҚ қолданыстағы
    оқушыға (мұрағатталғандарды қоса) бірегей код тағайындайды —
    идемпотентті: код қойылған оқушыға ЕШҚАШАН қайта тимейді, ешбір
    жазба өшірілмейді/қайта жасалмайды (§ "Do not delete or recreate
    student records"). Тағайындалған кодтар санын қайтарады.
    """
    updated_count = 0
    for classroom in classroom_repository.list_active():
        for student in student_repository.list_by_classroom(classroom.id, include_archived=True):
            if student.student_code:
                continue
            code = generate_unique_student_code(student_repository)
            updated_student = replace(
                student, student_code=code, updated_at=datetime.now(timezone.utc)
            )
            # § "system-level maintenance operation, not a user action" —
            # ``ensure_can_manage_classroom_data()`` доменнің ӨЗІ талап
            # ететін guard, ағымдағы қолданушы рөліне қатысы жоқ (§
            # ``seed_questions_from_catalog``-пен БІРДЕЙ бір реттік
            # backfill принципі).
            student_repository.update(updated_student, UserRole.TEACHER)
            updated_count += 1
    return updated_count
