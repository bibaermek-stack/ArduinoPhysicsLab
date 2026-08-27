"""Production-bootstrap routing regression suite (post-Phase-41 incident).

Барлық тесттер ``app.build_main_window()`` арқылы, яғни ``app.py``-дің
``run()``-ы НАҚТЫ шақыратын БІРДЕЙ функциямен ``MainWindow`` құрастырады
— тест пен нақты bootstrap арасында ЕШБІР алшақтық болмауы үшін (§
инцидент: скриншот-скрипт бір рет ``app.py``-ден алшақтап, жалған
нәтиже берген еді). Мұнда ешбір fake/mock бет қолданылмайды — тек
нақты page класстары.
"""

import sys

import pytest
from PySide6.QtWidgets import QApplication

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from app import build_main_window
from domain.entities.active_student_context import ActiveStudentContext
from domain.entities.classroom import Classroom
from domain.entities.student import Student
from domain.entities.user_role import UserRole
from datetime import datetime, timezone
from modules.electricity.experiments_config import OHMS_LAW_EXPERIMENT
from ui.pages.class_management_page import ClassManagementPage
from ui.pages.data_journal_page import DataJournalPage
from ui.pages.devices_page import DevicesPage
from ui.pages.experiment_list_page import ExperimentListPage
from ui.pages.experiment_workspace_page import ExperimentWorkspacePage
from ui.pages.help_page import HelpPage
from ui.pages.home_page import HomePage
from ui.pages.role_selection_page import RoleSelectionPage
from ui.pages.settings_page import SettingsPage
from domain.services.student_access_code import generate_unique_student_code
from ui.pages.student_feedback_page import StudentFeedbackPage
from ui.pages.student_results_page import StudentResultsPage
from ui.pages.teacher_dashboard_page import TeacherDashboardPage
from ui.pages.teacher_feedback_review_page import TeacherFeedbackReviewPage
from ui.widgets.teacher_pin_dialog import TeacherPinDialog

_DEV_PIN = "1234"  # § domain/services/teacher_pin.py::_DEFAULT_DEV_PIN

# route key -> expected concrete page class. Ең маңызды route-тар:
# зертхана каталогы, эксперимент жұмыс кеңістігі, рөл таңдау, Phase 41
# StudentFeedback/дашборд/т.б.
_EXPECTED_ROUTE_CLASSES: dict[str, type] = {
    "home": HomePage,
    "devices": DevicesPage,
    "experiment_list": ExperimentListPage,
    "experiment_workspace": ExperimentWorkspacePage,
    "data_journal": DataJournalPage,
    "settings": SettingsPage,
    "about": HelpPage,
    "role_selection": RoleSelectionPage,
    "classes": ClassManagementPage,
    "my_results": StudentResultsPage,
    "feedback_student": StudentFeedbackPage,
    "dashboard": TeacherDashboardPage,
    "feedback_teacher": TeacherFeedbackReviewPage,
}


@pytest.fixture(scope="module", autouse=True)
def qt_application() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def _build_window(role: UserRole = UserRole.TEACHER):
    return build_main_window(role, db_path=":memory:")


def _enter_teacher_pin(window, pin: str = _DEV_PIN) -> None:
    """§ Teacher Login Redesign: PIN ЕНДІ модальды ``TeacherPinDialog``
    ЕМЕС, беттің ІШІНДЕГІ ``_pin_edit``/``_teacher_login_button`` арқылы
    (§ ``role_selection_page.py``). Бұл функция "Мұғалім режимі"
    батырмасы басылып, "teacher_login" көрінісі АШЫЛҒАННАН КЕЙІН
    шақырылады деп болжайды."""
    role_page = window._role_selection_page
    role_page._pin_edit.setText(pin)
    role_page._teacher_login_button.click()


# =====================================================================
# 1-2. Production composition + route->page class identity
# =====================================================================


def test_build_main_window_uses_real_pages_not_fakes() -> None:
    window = _build_window()

    assert isinstance(window._experiment_list_page, ExperimentListPage)
    assert isinstance(window._role_selection_page, RoleSelectionPage)


@pytest.mark.parametrize("route_key,expected_class", list(_EXPECTED_ROUTE_CLASSES.items()))
def test_every_critical_route_resolves_to_expected_page_class(route_key: str, expected_class: type) -> None:
    window = _build_window()

    page = window._router._pages[route_key]

    assert isinstance(page, expected_class), (
        f"route '{route_key}' resolved to {type(page).__name__}, expected {expected_class.__name__}"
    )


def test_experiment_list_and_role_selection_are_never_the_same_widget() -> None:
    window = _build_window()

    experiments_page = window._router._pages["experiment_list"]
    role_page = window._router._pages["role_selection"]

    assert experiments_page is not role_page
    assert type(experiments_page) is not type(role_page)


def test_no_page_instance_registered_under_two_route_keys() -> None:
    window = _build_window()

    seen: dict[int, str] = {}
    for route_key, page in window._router._pages.items():
        page_id = id(page)
        assert page_id not in seen, (
            f"page instance registered under both '{seen.get(page_id)}' and '{route_key}'"
        )
        seen[page_id] = route_key


# =====================================================================
# 3-4. Navigating to the laboratory catalog in both roles
# =====================================================================


def test_teacher_labs_sidebar_click_opens_experiment_list_not_role_selection() -> None:
    window = _build_window(UserRole.TEACHER)

    window._sidebar.buttons["labs"].click()

    current = window._stack.currentWidget()
    assert current is window._experiment_list_page
    assert current is not window._role_selection_page


def test_student_labs_sidebar_click_opens_experiment_list() -> None:
    from domain.entities.active_student_context import ActiveStudentContext
    from domain.entities.classroom import Classroom
    from domain.entities.student import Student
    from datetime import datetime, timezone

    window = _build_window(UserRole.STUDENT)
    now = datetime.now(timezone.utc)
    window.classroom_repository.create(
        Classroom(id="c1", name="8А", created_at=now, updated_at=now), UserRole.TEACHER
    )
    window.student_repository.create(
        Student(id="s1", classroom_id="c1", first_name="Тест", last_name="Оқушы",
                created_at=now, updated_at=now),
        UserRole.TEACHER,
    )
    window.active_student_repository.set(ActiveStudentContext(classroom_id="c1", student_id="s1"))
    window._refresh_active_student_display()

    window._sidebar.buttons["labs"].click()

    current = window._stack.currentWidget()
    assert current is window._experiment_list_page


# =====================================================================
# 5-8. Role switching (real sidebar/RoleSelectionPage/full-page PIN
# login — § Teacher Login Redesign: no modal dialog anymore)
# =====================================================================


def test_switch_role_sidebar_action_opens_role_selection_page(qt_application: QApplication) -> None:
    window = _build_window(UserRole.TEACHER)

    window._sidebar._switch_role_button.click()

    assert window._stack.currentWidget() is window._role_selection_page


def test_student_button_changes_role_to_student(qt_application: QApplication) -> None:
    """§ Mode Switch + Student Access Screen Redesign: "Оқушы режимі"
    батырмасы ЕНДІ бірден рөлді ауыстырмайды — кіру-код формасына ғана
    өтеді (§ ``role_selection_page.py``). Рөл ТЕК жарамды код
    расталғаннан кейін ғана өзгереді."""
    window = _build_window(UserRole.TEACHER)
    code = _create_student(window)
    window._sidebar._switch_role_button.click()

    window._role_selection_page._student_button.click()
    qt_application.processEvents()
    assert window._current_role is UserRole.TEACHER  # әлі ауыспаған

    window._role_selection_page._code_edit.setText(code)
    window._role_selection_page._login_button.click()
    qt_application.processEvents()

    assert window._current_role is UserRole.STUDENT


def test_teacher_button_with_correct_pin_changes_role_to_teacher(qt_application: QApplication) -> None:
    window = _build_window(UserRole.STUDENT)
    from domain.entities.active_student_context import ActiveStudentContext

    window.active_student_repository.set(ActiveStudentContext(classroom_id="c1", student_id="s1"))
    window._sidebar._switch_role_button.click()

    window._role_selection_page._teacher_button.click()
    qt_application.processEvents()
    _enter_teacher_pin(window)
    qt_application.processEvents()

    assert window._current_role is UserRole.TEACHER


def test_teacher_button_never_creates_pin_dialog(qt_application: QApplication) -> None:
    """§ "no teacher PIN modal/dialog is created" — толық экрандық
    teacher_login көрінісі ашылғанда, ``TeacherPinDialog`` данасы ЕШҚАШАН
    құрылмайды."""
    window = _build_window(UserRole.TEACHER)
    window._sidebar._switch_role_button.click()

    window._role_selection_page._teacher_button.click()
    qt_application.processEvents()
    _enter_teacher_pin(window)
    qt_application.processEvents()

    assert window._current_role is UserRole.TEACHER
    assert not any(
        isinstance(widget, TeacherPinDialog) for widget in qt_application.topLevelWidgets()
    )


def test_experiments_remain_navigable_after_role_change(qt_application: QApplication) -> None:
    window = _build_window(UserRole.TEACHER)
    code = _create_student(window)
    window._sidebar._switch_role_button.click()
    window._role_selection_page._student_button.click()
    qt_application.processEvents()
    window._role_selection_page._code_edit.setText(code)
    window._role_selection_page._login_button.click()
    qt_application.processEvents()
    assert window._current_role is UserRole.STUDENT

    window._sidebar.buttons["labs"].click()

    assert window._stack.currentWidget() is window._experiment_list_page


# =====================================================================
# 9. Repeated role switching does not duplicate pages/signals
# =====================================================================


def test_repeated_role_switching_does_not_duplicate_pages(qt_application: QApplication) -> None:
    window = _build_window(UserRole.TEACHER)
    code = _create_student(window)
    experiment_list_id = id(window._experiment_list_page)
    role_selection_id = id(window._role_selection_page)

    for _ in range(3):
        window._sidebar._switch_role_button.click()
        qt_application.processEvents()
        window._role_selection_page._student_button.click()
        qt_application.processEvents()
        window._role_selection_page._code_edit.setText(code)
        window._role_selection_page._login_button.click()
        qt_application.processEvents()
        window._sidebar._switch_role_button.click()
        qt_application.processEvents()
        window._role_selection_page._teacher_button.click()
        qt_application.processEvents()
        _enter_teacher_pin(window)
        qt_application.processEvents()

    assert id(window._experiment_list_page) == experiment_list_id
    assert id(window._role_selection_page) == role_selection_id
    assert window._current_role is UserRole.TEACHER

    window._sidebar.buttons["labs"].click()
    assert window._stack.currentWidget() is window._experiment_list_page


# =====================================================================
# 10-11. Full registry mapping + production/test-factory equivalence
# =====================================================================


def test_every_mainwindow_page_attribute_registered_under_intended_route() -> None:
    window = _build_window()

    attribute_to_route = {
        "_home_page": "home",
        "_devices_page": "devices",
        "_experiment_list_page": "experiment_list",
        "_experiment_workspace_page": "experiment_workspace",
        "_data_journal_page": "data_journal",
        "_settings_page": "settings",
        "_about_page": "about",
        "_role_selection_page": "role_selection",
        "_class_management_page": "classes",
        "_student_results_page": "my_results",
        "_student_feedback_page": "feedback_student",
        "_teacher_dashboard_page": "dashboard",
        "_teacher_feedback_review_page": "feedback_teacher",
    }

    for attribute_name, route_key in attribute_to_route.items():
        page_instance = getattr(window, attribute_name)
        registered_page = window._router._pages[route_key]
        assert page_instance is registered_page, (
            f"{attribute_name} is not the page registered under route '{route_key}'"
        )


def test_production_and_real_module_registry_factory_produce_same_route_set() -> None:
    """``build_main_window()`` (app.py composition) және
    ``MainWindow(module_registry=...)`` (тестерде кеңінен қолданылатын
    "нақты беттермен, тек фейк репозиторийсіз" factory паттерні) БІРДЕЙ
    route жиынын тіркеуі керек — екеуі арасында route-регистрация
    алшақтығы болмауы үшін.
    """
    from modules.module_registry import ModuleRegistry
    from ui.main_window import MainWindow

    production_window = _build_window()
    factory_window = MainWindow(module_registry=ModuleRegistry())

    assert set(production_window._router._pages.keys()) == set(factory_window._router._pages.keys())


# =====================================================================
# Incident regression: real hit-testing + real QTest.mouseClick,
# A-F scenarios (§ "role switching does not complete" incident).
#
# ROOT CAUSE (confirmed): ``WorkspaceBackdrop`` had
# ``WA_TransparentForMouseEvents`` set. Qt's REAL mouse-event delivery
# performs top-down hit-testing from the QSplitter -- and a widget with
# that attribute has its ENTIRE child subtree skipped during that
# hit-testing (not just itself), so no click anywhere inside the
# workspace pane (experiment cards, dialog buttons, the embedded
# RoleSelectionPage's own Student/Teacher buttons) could ever reach its
# target via a real screen-coordinate click. Direct-reference calls like
# ``widget.click()`` or ``QTest.mouseClick(widget, ...)`` bypass this
# hit-testing entirely, which is exactly why 70+ existing tests (and 3
# prior investigation rounds) never caught it. Fixed by removing the
# attribute (unnecessary in the first place -- WorkspaceBackdrop is the
# PARENT of the stack, not an overlay sibling, so children already take
# mouse-event priority over it with no extra attribute required).
#
# ``_click_via_real_hit_testing`` below is the authoritative regression
# guard: it clicks at the button's REAL SCREEN POSITION, targeted at the
# top-level window (forcing genuine hit-testing), instead of at the
# button object directly.
# =====================================================================


def _click_via_real_hit_testing(window, widget) -> None:
    """Нақты screen-coordinate негізді click — ``window``-ге бағытталған,
    ``widget``-тің НАҚТЫ экрандағы позициясында. Bұл Qt-тың шынайы
    hit-testing тетігін мәжбүрлейді (§ ``childAt()``-пен БІРДЕЙ
    алгоритм), тікелей ``widget.click()``/``QTest.mouseClick(widget,...)``-
    тен АЙЫРМАШЫЛЫҒЫ — сол екеуі hit-testing-ті мүлде айналып өтеді.
    """
    global_center = widget.mapToGlobal(widget.rect().center())
    local_pos = window.mapFromGlobal(global_center)
    resolved = window.childAt(local_pos)
    assert resolved is widget, (
        f"Real hit-testing at {widget}'s screen position resolved to {resolved!r}, "
        f"not the widget itself -- a click here would never reach it."
    )
    QTest.mouseClick(widget, Qt.MouseButton.LeftButton)


def _create_student(window, student_id: str = "s1") -> str:
    """Сынып (идемпотентті) + кодталған оқушыны құрады, кодын қайтарады.
    Белсенді оқушы контексін/навигацияны МҮЛДЕ өзгертпейді — рөлге
    тәуелсіз, кез келген уақытта қауіпсіз шақырылады (§ ``MainWindow.
    __init__``-тегі backfill бұл жазбаны әлі көрмеген, сондықтан код
    осында НАҚТЫ ``generate_unique_student_code()`` арқылы беріледі,
    § "New students receive a code")."""
    now = datetime.now(timezone.utc)
    if window.classroom_repository.get("c1") is None:
        window.classroom_repository.create(
            Classroom(id="c1", name="8А", created_at=now, updated_at=now), UserRole.TEACHER
        )
    code = generate_unique_student_code(window.student_repository)
    window.student_repository.create(
        Student(id=student_id, classroom_id="c1", first_name="Тест", last_name="Оқушы",
                created_at=now, updated_at=now, student_code=code),
        UserRole.TEACHER,
    )
    return code


def _seed_student(window, student_id: str = "s1") -> None:
    """§ "already logged in" күйінің ЭКВИВАЛЕНТІ — ТЕК репозиторийге
    жазу емес, ``window._router.navigate("home")`` да шақырады (§ нақты
    сәтті логиннен КЕЙІН sidebar қайта көрінетінімен БІРДЕЙ, § ``_on_
    student_selected``). Бұл хелпер тек STUDENT рөліндегі терезелерде
    қолданылады — Оқушы режимінде код кірместен "тікелей" белсенді
    оқушыны орнату қажет сценарийлер үшін (нақты UI логин ағынын
    ЖЕКЕ ``_switch_role_via_real_clicks`` тексереді)."""
    _create_student(window, student_id)
    window.active_student_repository.set(ActiveStudentContext(classroom_id="c1", student_id=student_id))
    window._refresh_active_student_display()
    window._router.navigate("home")


def _switch_role_via_real_clicks(window, qt_app, to_role: UserRole, student_id: str = "s1") -> None:
    """Sidebar 'Режімді ауыстыру' -> embedded RoleSelectionPage
    Student/Teacher button -> (Teacher болса) PIN 1234 -- БАРЛЫҒЫ НАҚТЫ
    hit-testing-пен тексерілген click арқылы.

    STUDENT тармағы ЕНДІ толық код-логин ағынын орындайды (§ Mode
    Switch + Student Access Screen Redesign — "Оқушы режимі" батырмасы
    енді бірден рөлді ауыстырмайды): ``student_id`` алдын ала
    ``_create_student()``/``_seed_student()`` арқылы КОДПЕН құрылған
    болуы тиіс.
    """
    _click_via_real_hit_testing(window, window._sidebar._switch_role_button)
    qt_app.processEvents()
    assert window._stack.currentWidget() is window._role_selection_page

    if to_role is UserRole.STUDENT:
        _click_via_real_hit_testing(window, window._role_selection_page._student_button)
        qt_app.processEvents()
        student = window.student_repository.get(student_id)
        assert student is not None and student.student_code, (
            "STUDENT-ге ауысу үшін кодталған оқушы алдын ала бар болуы керек"
        )
        window._role_selection_page._code_edit.setText(student.student_code)
        _click_via_real_hit_testing(window, window._role_selection_page._login_button)
    else:
        _click_via_real_hit_testing(window, window._role_selection_page._teacher_button)
        qt_app.processEvents()
        window._role_selection_page._pin_edit.setText(_DEV_PIN)
        _click_via_real_hit_testing(window, window._role_selection_page._teacher_login_button)
    qt_app.processEvents()


def test_hit_testing_reaches_embedded_role_buttons_through_real_mainwindow(qt_application: QApplication) -> None:
    """Инцидент-репро: ЖОҚ hit-testing-мен (яғни түзетусіз) бұл тест
    ``AssertionError``-мен сәтсіз аяқталар еді -- ``window.childAt()``
    осы екі батырма үшін де ешқашан ЕШТЕҢЕ таппас еді.
    """
    window = _build_window(UserRole.TEACHER)
    window.show()
    window._sidebar._switch_role_button.click()

    role_page = window._role_selection_page
    global_center = role_page._teacher_button.mapToGlobal(role_page._teacher_button.rect().center())
    local_pos = window.mapFromGlobal(global_center)

    assert window.childAt(local_pos) is role_page._teacher_button


# ---- A. Student: Labs -> real experiment -> workspace --------------------


def test_scenario_a_student_labs_to_real_experiment_workspace(qt_application: QApplication) -> None:
    window = _build_window(UserRole.STUDENT)
    window.show()
    _seed_student(window)

    assert "labs" in window._sidebar.buttons
    _click_via_real_hit_testing(window, window._sidebar.buttons["labs"])
    assert window._stack.currentWidget() is window._experiment_list_page

    window._experiment_list_page.experiment_selected.emit(OHMS_LAW_EXPERIMENT)
    assert window._stack.currentWidget() is window._experiment_workspace_page


# ---- B. Student -> Teacher round trip -------------------------------------


def test_scenario_b_student_to_teacher_full_round_trip(qt_application: QApplication) -> None:
    window = _build_window(UserRole.STUDENT)
    window.show()
    _seed_student(window)

    _switch_role_via_real_clicks(window, qt_application, UserRole.TEACHER)

    assert window._current_role is UserRole.TEACHER
    assert window._sidebar.role() is UserRole.TEACHER
    for teacher_only_route in ("dashboard", "classes", "feedback_teacher", "devices"):
        assert window._router.navigate(teacher_only_route) is True, f"'{teacher_only_route}' should open for Teacher"

    _click_via_real_hit_testing(window, window._sidebar.buttons["labs"])
    assert window._stack.currentWidget() is window._experiment_list_page
    window._experiment_list_page.experiment_selected.emit(OHMS_LAW_EXPERIMENT)
    assert window._stack.currentWidget() is window._experiment_workspace_page


# ---- C. Teacher -> Student round trip -------------------------------------


def test_scenario_c_teacher_to_student_full_round_trip(qt_application: QApplication) -> None:
    window = _build_window(UserRole.TEACHER)
    window.show()
    # § "Selecting Student mode transitions to a login card" — рөл ТЕК
    # жарамды кодпен ауысатындықтан, кодталған оқушы АЛДЫН АЛА болуы
    # керек (мұғалім рөлінде жазу қауіпсіз, навигацияға әсер етпейді).
    _create_student(window)

    _switch_role_via_real_clicks(window, qt_application, UserRole.STUDENT)

    assert window._current_role is UserRole.STUDENT
    assert window._sidebar.role() is UserRole.STUDENT
    for teacher_only_route in ("dashboard", "classes", "feedback_teacher"):
        assert window._router.navigate(teacher_only_route) is False, (
            f"'{teacher_only_route}' must be rejected for Student"
        )

    _click_via_real_hit_testing(window, window._sidebar.buttons["labs"])
    assert window._stack.currentWidget() is window._experiment_list_page
    window._experiment_list_page.experiment_selected.emit(OHMS_LAW_EXPERIMENT)
    assert window._stack.currentWidget() is window._experiment_workspace_page


# ---- D. Repeated round trips: no duplication ------------------------------


def test_scenario_d_repeated_round_trips_no_duplication(qt_application: QApplication) -> None:
    window = _build_window(UserRole.STUDENT)
    window.show()
    _seed_student(window)

    window_id = id(window)
    sidebar_id = id(window._sidebar)
    role_page_id = id(window._role_selection_page)
    experiment_list_id = id(window._experiment_list_page)

    top_level_mainwindows_before = sum(
        1 for w in qt_application.topLevelWidgets() if type(w).__name__ == "MainWindow" and w.isVisible()
    )

    for _ in range(3):
        _switch_role_via_real_clicks(window, qt_application, UserRole.TEACHER)
        _switch_role_via_real_clicks(window, qt_application, UserRole.STUDENT)

    visible_mainwindows = [
        w for w in qt_application.topLevelWidgets() if type(w).__name__ == "MainWindow" and w.isVisible()
    ]
    orphan_role_selection_windows = [
        w for w in qt_application.topLevelWidgets()
        if type(w).__name__ == "RoleSelectionPage" and w.parent() is None and w.isVisible()
    ]

    assert len(visible_mainwindows) == max(1, top_level_mainwindows_before)
    assert orphan_role_selection_windows == []
    assert id(window) == window_id
    assert id(window._sidebar) == sidebar_id
    assert id(window._role_selection_page) == role_page_id
    assert id(window._experiment_list_page) == experiment_list_id
    assert window._current_role is UserRole.STUDENT

    _click_via_real_hit_testing(window, window._sidebar.buttons["labs"])
    assert window._stack.currentWidget() is window._experiment_list_page
    window._experiment_list_page.experiment_selected.emit(OHMS_LAW_EXPERIMENT)
    assert window._stack.currentWidget() is window._experiment_workspace_page


# ---- E. Wrong PIN ----------------------------------------------------------


def test_scenario_e_wrong_pin_does_not_activate_teacher(qt_application: QApplication) -> None:
    """§ Teacher Login Redesign: қате PIN бетті ЕШҚАШАН ЖАППАЙДЫ/
    ӘКЕТПЕЙДІ — "teacher_login" көрінісінде қалады, inline қате
    хабарлама көрінеді (§ ескі ``TeacherPinDialog._on_confirm_clicked``-
    тегі "wrong PIN never closes the dialog" семантикасымен БІРДЕЙ, енді
    модаль ЕМЕС, беттің ӨЗІНДЕ).
    """
    window = _build_window(UserRole.STUDENT)
    window.show()
    _seed_student(window)

    window._sidebar._switch_role_button.click()
    assert window._stack.currentWidget() is window._role_selection_page

    window._role_selection_page._teacher_button.click()
    _enter_teacher_pin(window, pin="0000")
    qt_application.processEvents()

    assert window._current_role is UserRole.STUDENT
    assert window._role_selection_page._teacher_login_view.isVisibleTo(window._role_selection_page)
    assert window._role_selection_page._pin_error_label.isVisibleTo(window._role_selection_page)
    assert not any(
        isinstance(widget, TeacherPinDialog) for widget in qt_application.topLevelWidgets()
    )

    window._sidebar.buttons["labs"].click()
    assert window._stack.currentWidget() is window._experiment_list_page

    # Correct PIN afterwards still works.
    window._sidebar._switch_role_button.click()
    window._role_selection_page._teacher_button.click()
    _enter_teacher_pin(window)
    qt_application.processEvents()
    assert window._current_role is UserRole.TEACHER


# ---- F. Back keeps current role --------------------------------------------


def test_scenario_f_back_from_teacher_login_keeps_current_role(qt_application: QApplication) -> None:
    """§ Teacher Login Redesign: "← Артқа" (ескі "Бас тарту"/cancel
    орнына) рөлді ӨЗГЕРТПЕЙДІ, мод таңдау көрінісіне қайтарады."""
    window = _build_window(UserRole.STUDENT)
    window.show()
    _seed_student(window)

    _click_via_real_hit_testing(window, window._sidebar._switch_role_button)
    qt_application.processEvents()

    _click_via_real_hit_testing(window, window._role_selection_page._teacher_button)
    qt_application.processEvents()
    assert window._role_selection_page._teacher_login_view.isVisibleTo(window._role_selection_page)

    _click_via_real_hit_testing(window, window._role_selection_page._teacher_login_back_button)
    qt_application.processEvents()

    assert window._current_role is UserRole.STUDENT
    assert window._stack.currentWidget() is window._role_selection_page
    assert window._role_selection_page._mode_view.isVisibleTo(window._role_selection_page)


def test_scenario_f_returning_from_role_selection_without_choosing_keeps_role() -> None:
    window = _build_window(UserRole.TEACHER)
    window.show()

    window._sidebar._switch_role_button.click()
    assert window._stack.currentWidget() is window._role_selection_page

    # "Артқа" эквиваленті — рөл таңдамай, тікелей басқа route-қа кету
    # (мыс. sidebar-дың басқа батырмасын басу) ағымдағы рөлді өзгертпеуі
    # тиіс, себебі role_selected сигналы ЕШҚАШАН эмитацияланған жоқ.
    window._router.navigate("dashboard")

    assert window._current_role is UserRole.TEACHER


# =====================================================================
# Phase 41 background regression fix (4-ші есеп): route/experiment-module
# category resolution pipeline-нің НАҚТЫ навигация арқылы ұшынан-ұшына
# (end-to-end) тексерісі — WorkspaceBackdrop.current_category() дәйектілігі
# каталог/эксперимент workspace арасында дәл алдын ала белгіленген
# ретпен ауысуы керек.
# =====================================================================


def test_background_category_sequence_across_experiment_workspace_navigation(
    qt_application: QApplication,
) -> None:
    """home -> labs -> тәжірибе №1 (heat) -> labs -> тәжірибе №4
    (electricity) -> labs -> тәжірибе №9 (electromagnetism) -> labs ->
    тәжірибе №11 (light) дәйектілігінде ``WorkspaceBackdrop.
    current_category()`` дәл СОЛ реттілікпен ауысуы керек (§ 1-2=heat,
    3-8=electricity, 9-10=electromagnetism, 11=light каталог нөмірлеуі).
    """
    from modules.electromagnetism.experiments_config import ELECTROMAGNETISM_EXPERIMENTS
    from modules.heat.experiments_config import HEAT_EXPERIMENTS
    from modules.light.experiments_config import LIGHT_EXPERIMENTS

    window = _build_window(UserRole.TEACHER)

    def _category() -> str:
        return window._workspace_backdrop.current_category()

    window._router.navigate("dashboard")
    assert _category() == "home"

    window._router.navigate("experiment_list")
    assert _category() == "laboratory"

    window._router.navigate("experiment_workspace", experiment=HEAT_EXPERIMENTS[0])
    assert _category() == "heat"

    window._router.navigate("experiment_list")
    assert _category() == "laboratory"

    window._router.navigate("experiment_workspace", experiment=OHMS_LAW_EXPERIMENT)
    assert _category() == "electricity"

    window._router.navigate("experiment_list")
    assert _category() == "laboratory"

    window._router.navigate(
        "experiment_workspace", experiment=ELECTROMAGNETISM_EXPERIMENTS[0]
    )
    assert _category() == "electromagnetism"

    window._router.navigate("experiment_list")
    assert _category() == "laboratory"

    window._router.navigate("experiment_workspace", experiment=LIGHT_EXPERIMENTS[0])
    assert _category() == "light"
