"""navigation_config — рөлге тәуелді бір ортақ навигация кестесі
(Phase 37A).

``Sidebar``/``MainWindow`` осы БІР кестеден оқиды — Оқушы/Мұғалім үшін
бөлек sidebar/MainWindow ЕШҚАШАН жасалмайды (§6 талабы). Әр ``NavigationItem``
``allowed_roles``-мен белгіленген; рөл бойынша сүзгі — қай батырма
көрінетінін ШЕШЕДІ, ал ``Router``-дегі guard hook (``ui/navigation/
router.py``) осыны НАҚТЫ РҰҚСАТ ретінде мәжбүрлейді (тек sidebar-дан
жасыру емес).

``ExperimentWorkspacePage`` (drill-down арқылы ашылатын, меню элементі
ЕМЕС) бұл кестеде жоқ — рөл сүзгісіне мүлде қатысы жоқ, екі рөлге де
бірдей нұсқа/данасы қолданылады.
"""

from dataclasses import dataclass

from domain.entities.user_role import UserRole

_STUDENT = frozenset({UserRole.STUDENT})
_TEACHER = frozenset({UserRole.TEACHER})
_BOTH = frozenset({UserRole.STUDENT, UserRole.TEACHER})


@dataclass(frozen=True)
class NavigationItem:
    key: str
    title: str
    icon: str
    allowed_roles: frozenset[UserRole]
    # Phase 6 (Sidebar Icon Integration): вендорленген Fluent SVG файл аты
    # (``Design/02_FluentIcons/svg/`` ішінде), бар болса ``Sidebar`` осыны
    # нақты ``QIcon`` ретінде қолданады (``icon`` emoji-ін ЕМЕС). ``None`` —
    # осы item үшін лайықты вендорленген иконка ЖОҚ (мыс. "Кері байланыс"-
    # қа сай chat/comment иконкасы вендорленбеген) — ЕСКІ emoji-негізді
    # көрініс өзгеріссіз қалады, ешбір орынбасар ойдан шығарылмайды.
    icon_svg: str | None = None


# Рет UI-де көрсетілу ретімен сәйкес.
NAVIGATION_ITEMS: tuple[NavigationItem, ...] = (
    NavigationItem("home", "Басты бет", "🏠", _STUDENT, "ic_fluent_home_24_regular.svg"),
    # "dashboard" (Мұғалім) — "home" (Оқушы) екеуі ЕШҚАШАН бір sidebar
    # данасында бірге көрінбейді (рөлге қарай өзара айрықша), сондықтан
    # "Home" иконкасын екеуіне де қайта пайдалану қауіпсіз (нақты
    # қайталанып көрінетін жол ЖОҚ).
    NavigationItem("dashboard", "Бақылау тақтасы", "📊", _TEACHER, "ic_fluent_home_24_regular.svg"),
    NavigationItem("classes", "Сыныптар мен оқушылар", "👥", _TEACHER, "ic_fluent_person_24_regular.svg"),
    NavigationItem("labs", "Зертханалық жұмыстар", "🧪", _BOTH, "ic_fluent_beaker_24_regular.svg"),
    # "my_results" (Оқушы) / "results" (Мұғалім) — жоғарыдағы "home"/
    # "dashboard"-пен БІРДЕЙ себеппен (өзара айрықша рөл) бір иконканы
    # қауіпсіз бөліседі.
    NavigationItem(
        "my_results", "Менің нәтижелерім", "📈", _STUDENT, "ic_fluent_clipboard_data_bar_24_regular.svg"
    ),
    NavigationItem("results", "Нәтижелер", "📈", _TEACHER, "ic_fluent_clipboard_data_bar_24_regular.svg"),
    # "data_log" — Phase 8 зерттеуінде "Notebook" бекітілді ("журнал"
    # мағынасына тікелей сай, "Нәтижелер"-дің Clipboard Data Bar-ынан
    # визуалды бөлек, сондықтан Мұғалім sidebar-ында екеуі бірге
    # көрінгенде де қайталанбайды).
    NavigationItem("data_log", "Деректер журналы", "📋", _TEACHER, "ic_fluent_notebook_24_regular.svg"),
    # "feedback_student"/"feedback_teacher" — Phase 8 зерттеуінде
    # "Comment" бекітілді (жай, әмбебап танылатын пікір/кері байланыс
    # белгісі, "Анықтама"-ның Question Circle-ынан бөлек).
    NavigationItem("feedback_student", "Кері байланыс", "💬", _STUDENT, "ic_fluent_comment_24_regular.svg"),
    NavigationItem(
        "feedback_teacher", "Кері байланысты тексеру", "💬", _TEACHER, "ic_fluent_comment_24_regular.svg"
    ),
    NavigationItem("analytics", "Аналитика", "📉", _TEACHER, "ic_fluent_chart_multiple_24_regular.svg"),
    NavigationItem("question_bank", "Сұрақтар банкі", "📚", _TEACHER, "ic_fluent_book_24_regular.svg"),
    NavigationItem("devices", "Құрылғылар", "🔌", _TEACHER, "ic_fluent_plug_connected_24_regular.svg"),
    NavigationItem("profile", "Профиль", "👤", _BOTH, "ic_fluent_person_24_filled.svg"),
    NavigationItem("people", "Адамдар", "🔎", _BOTH, "ic_fluent_people_swap_24_regular.svg"),
    NavigationItem("settings", "Баптаулар", "⚙", _TEACHER, "ic_fluent_settings_24_regular.svg"),
    NavigationItem("help", "Анықтама", "❓", _BOTH, "ic_fluent_question_circle_24_regular.svg"),
)


def items_for_role(role: UserRole) -> tuple[NavigationItem, ...]:
    """Берілген рөлге көрінетін nav item-дерді, кестедегі ретпен қайтарады."""
    return tuple(item for item in NAVIGATION_ITEMS if role in item.allowed_roles)


# § Phase 6 (Teacher Live Classroom Monitoring Dashboard): "classroom_
# monitoring"/"student_monitoring" — sidebar менюінде ЖОҚ drill-down
# route-тар (§ ``experiment_workspace``-пен БІРДЕЙ түр), БІРАҚ, одан
# айырмашылығы, ТЕК мұғалімге арналған дерек көрсетеді (§4 "Teacher A
# must not see Teacher B's classroom" — рөл шекарасы да, "кестеде жоқ
# route әрқашан рұқсат" ЖАЛПЫ ережесінен нақты алып тасталуы керек,
# әйтпесе Оқушы рөлі де осы route-қа (гипотетикалық түрде) жете алар
# еді). ``NAVIGATION_ITEMS``-ке ҚОСЫЛМАЙДЫ — sidebar батырмасы ЕШҚАШАН
# жасалмайды.
#
# § Phase 7 audit — "data_journal" де осы жиынға ҚОСЫЛДЫ: бұл ROUTER
# кілті (``MainWindow._SIDEBAR_ROUTES["data_log"] == "data_journal"``),
# БІРАҚ ``NAVIGATION_ITEMS``-те тек "data_log" бар — "data_journal"
# кілтінің ӨЗІ бұл кестеде ЕШҚАШАН жоқ болатын. Демек ``is_route_
# allowed_for_role("data_journal", ...)`` бұрын "кестеде жоқ route
# әрқашан рұқсат" әдепкісіне құлап, Оқушы рөлі де (гипотетикалық
# navigate("data_journal") шақыруы арқылы) бұл мұғалім-тек бетке жете
# алатын алдын ала бар олқылық болатын (§ Phase 7 "Teacher B must not
# access unrelated students by manually navigating with IDs" талабын
# аудиттеу кезінде табылды/түзетілді — ``DataJournalPage`` ЕНДІ Phase 7-
# де ``student_id`` арқылы тереңдетілген сілтеме алатындықтан, бұл
# енді әрі қарай елемеуге болмайтын нақты қауіп).
_TEACHER_ONLY_DRILLDOWN_ROUTES = frozenset(
    {"classroom_monitoring", "student_monitoring", "data_journal"}
)


def is_route_allowed_for_role(route_key: str, role: UserRole) -> bool:
    """Рөл берілген route-қа бара алса ``True`` қайтарады.

    Кестеде жоқ route (мыс. ``experiment_workspace``, ``experiment_list``,
    ``role_selection`` — меню элементі емес, drill-down/қызметтік
    навигация) ӘРҚАШАН рұқсат етіледі — ТЕК ``_TEACHER_ONLY_DRILLDOWN_
    ROUTES``-тан басқа. ``TEACHER`` — үлкейтілген рөл (қолданыстағы
    барлық функцияны сақтау талабы), сондықтан кестедегі КЕЗ КЕЛГЕН
    route-қа қатынасы шектелмейді.
    """
    if role is UserRole.TEACHER:
        return True
    if route_key in _TEACHER_ONLY_DRILLDOWN_ROUTES:
        return False
    item = next((item for item in NAVIGATION_ITEMS if item.key == route_key), None)
    if item is None:
        return True
    return role in item.allowed_roles


def default_landing_route(role: UserRole) -> str:
    """Рөл бойынша ЕҢ АЛҒАШҚЫ (қолданба/ауысу сәтіндегі) route-ты қайтарады."""
    return "home" if role is UserRole.STUDENT else "dashboard"
