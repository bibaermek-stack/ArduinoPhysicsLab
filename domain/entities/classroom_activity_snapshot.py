"""ClassroomActivitySnapshot — бір сыныптың ЕҢ СОҢҒЫ белсенді тәжірибесі
бойынша қорытынды прогресс-бөлінісі (Phase 13, Teacher Dashboard "Бүгінгі
белсенділік" панелі).

Дерек моделінде "тағайындалған зертханалық жұмыс" деген бөлек ұғым ЖОҚ
(§ "No database schema change" — жаңа кесте/баған қосылмайды). Сондықтан
бір сыныптың "ағымдағы белсенділігі" ҚАНДАЙ тәжірибе екенін анықтау үшін
ЕҢ ХАЛАЛ тәсіл: сол сыныптағы ``session_student_link`` жазбаларының ІШІНЕН
ЕҢ СОҢҒЫ ``linked_at``-ы бар ``experiment_id``-ды таңдау (§
``SqliteStudentProgressRepository.compute_classroom_activity()``). Бұл
ЕШБІР жаңа ойдан шығарылған "тапсырма" ұғымын қоспайды — тек нақты соңғы
белсенділікті көрсетеді.

``experiment_title``/``display_number`` бұл жерде ӘДЕЙІ ЖОҚ — тәжірибе
каталогы (``ModuleRegistry``) storage қабатына тәуелсіз, ``TeacherFeedbackReviewPage.
_iter_catalog_experiments_by_id()``-пен БІРДЕЙ принцип: атауды/нөмірді
ТЕК шақырушы (UI page, module_registry-ге қатынасы бар) ``experiment_id``
арқылы өзі іздейді.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ClassroomActivitySnapshot:
    """Бір сыныптың ең соңғы белсенді тәжірибесі бойынша оқушы саны/
    прогресс бөлінісі. ``student_count`` осы сыныптағы БАРЛЫҚ (архивтелмеген)
    оқушы саны — бұл тәжірибеге байланысы жоқ оқушылар автоматты түрде
    ``not_started_count``-қа кіреді (§ "Бастамады").
    """

    classroom_id: str
    classroom_name: str
    experiment_id: str
    student_count: int
    completed_count: int
    in_progress_count: int
    not_started_count: int
    last_activity_at: datetime | None

    @property
    def completion_percentage(self) -> int:
        """Бүтін пайызбен дөңгелектелген аяқтау деңгейі (§ "67%").
        ``student_count == 0`` болса (теориялық жағдай, тексерілген
        сыныпта әрқашан кем дегенде осы snapshot-ты тудырған оқушы бар),
        0 қайтарады — ешқашан ZeroDivisionError шықпайды.
        """
        if self.student_count <= 0:
            return 0
        return round((self.completed_count / self.student_count) * 100)
