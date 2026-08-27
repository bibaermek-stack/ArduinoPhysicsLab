"""MainWindow — негізгі терезе.

Тек навигация shell-і: global ``Sidebar`` (сол жақ, жабылып/ашылатын) +
``Router`` арқылы ``HomePage`` → ``ExperimentListPage`` →
``ExperimentWorkspacePage`` беттері арасында, сондай-ақ ``SettingsPage``/
``HelpPage`` беттеріне ауысуды баптайды. Өзі ешбір құрылғы/тәжірибе
логикасын жасамайды — бәрі тиісті бетте орналасқан.

Phase 37A: рөл шеберлігі (``UserRole``) осы жерде тұрады.
``initial_role`` әдепкі бойынша ``UserRole.TEACHER`` — ескі (рөл
концепциясынан бұрынғы) барлық қолданушы/тест ``MainWindow()``-ды рөл
бермей құрастырады да, толық функционалдылықты (Құрылғылар/Баптаулар/
Деректер журналы) күтеді; Мұғалім — "барлығы қолжетімді" үлкейтілген
рөл болғандықтан, бұл әдепкі ескі мінез-құлықты дәл сақтайды. Нақты
қолданба (``app.py``) бұл әдепкіге ЕШҚАШАН сенбейді — рөлді әрдайым
PIN-мен расталған, пайдаланушы таңдаған мәнмен нақты береді.
"""

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

# УАҚЫТША ДИАГНОСТИКА (§ main.py-дегі debug.log).
_trace_logger = logging.getLogger("apl.trace")

from domain.entities.experiment_definition import ExperimentDefinition
from domain.entities.user_role import UserRole
from domain.interfaces.i_active_student_repository import IActiveStudentRepository
from domain.interfaces.i_active_teacher_repository import IActiveTeacherRepository
from domain.interfaces.i_classroom_repository import IClassroomRepository
from domain.interfaces.i_feedback_repository import IFeedbackRepository
from domain.interfaces.i_measurement_batch_repository import IMeasurementBatchRepository
from domain.interfaces.i_physics_module import IPhysicsModule
from domain.interfaces.i_question_repository import IQuestionRepository
from domain.interfaces.i_session_repository import ISessionRepository
from domain.interfaces.i_student_progress_repository import IStudentProgressRepository
from domain.interfaces.i_student_repository import IStudentRepository
from domain.interfaces.i_teacher_note_repository import ITeacherNoteRepository
from domain.interfaces.i_teacher_repository import ITeacherRepository
from domain.services.question_bank_seed import seed_questions_from_catalog
from domain.services.student_access_code import backfill_missing_student_codes
from domain.services.student_home_summary import compute_student_home_summary
from domain.services.sync_migration import (
    backfill_measurement_batches,
    backfill_session_sync_queue,
    backfill_sync_ids,
)
from domain.services.teacher_migration import backfill_default_teacher
from infrastructure.serial_comm.device_manager import DeviceManager
from infrastructure.storage.app_preferences import AppPreferences
from infrastructure.storage.sqlite_active_student_repository import SqliteActiveStudentRepository
from infrastructure.storage.sqlite_active_teacher_repository import SqliteActiveTeacherRepository
from infrastructure.storage.sqlite_classroom_repository import SqliteClassroomRepository
from infrastructure.storage.sqlite_feedback_repository import SqliteFeedbackRepository
from infrastructure.storage.sqlite_measurement_batch_repository import SqliteMeasurementBatchRepository
from infrastructure.storage.sqlite_question_repository import SqliteQuestionRepository
from infrastructure.storage.sqlite_session_repository import SqliteSessionRepository
from infrastructure.storage.sqlite_student_progress_repository import SqliteStudentProgressRepository
from infrastructure.storage.sqlite_student_repository import SqliteStudentRepository
from infrastructure.storage.sqlite_teacher_note_repository import SqliteTeacherNoteRepository
from infrastructure.storage.sqlite_teacher_repository import SqliteTeacherRepository
from infrastructure.storage.teacher_scoped_classroom_repository import TeacherScopedClassroomRepository
from infrastructure.sync.sync_thread_controller import SyncThreadController
from modules.module_registry import ModuleRegistry
from ui.navigation.background_category import resolve_experiment_category, resolve_route_category
from ui.navigation.navigation_config import default_landing_route, is_route_allowed_for_role
from ui.navigation.router import Router
from ui.pages.analytics_page import AnalyticsPage
from ui.pages.class_management_page import ClassManagementPage
from ui.pages.classroom_monitoring_page import ClassroomMonitoringPage
from ui.pages.data_journal_page import DataJournalPage
from ui.pages.devices_page import DevicesPage
from ui.pages.experiment_list_page import ExperimentListPage
from ui.pages.experiment_workspace_page import ExperimentWorkspacePage
from ui.pages.help_page import HelpPage
from ui.pages.home_page import HomePage
from ui.pages.people_page import PeoplePage
from ui.pages.profile_page import ProfilePage
from ui.pages.placeholder_page import PlaceholderPage
from ui.pages.question_bank_page import QuestionBankPage
from ui.pages.results_page import ResultsPage
from ui.pages.role_selection_page import RoleSelectionPage
from ui.pages.settings_page import SettingsPage
from ui.pages.student_feedback_page import StudentFeedbackPage
from ui.pages.student_monitoring_detail_page import StudentMonitoringDetailPage
from ui.pages.student_results_page import StudentResultsPage
from ui.pages.teacher_dashboard_page import TeacherDashboardPage
from ui.pages.teacher_feedback_review_page import TeacherFeedbackReviewPage
from ui.pages.teacher_management_page import TeacherManagementPage
from ui.widgets.sidebar import Sidebar
from ui.widgets.workspace_background import WorkspaceBackdrop

# Sidebar nav item key -> Router route name (nav item мен route атауы бір
# жерде әрдайым сәйкес келе бермейді, мыс. "help" -> "about").
_SIDEBAR_ROUTES: dict[str, str] = {
    "home": "home",
    "dashboard": "dashboard",
    "classes": "classes",
    "devices": "devices",
    "labs": "experiment_list",
    "my_results": "my_results",
    "results": "results",
    "data_log": "data_journal",
    "feedback_student": "feedback_student",
    "feedback_teacher": "feedback_teacher",
    "analytics": "analytics",
    "question_bank": "question_bank",
    "settings": "settings",
    "help": "about",
    "profile": "profile",
    "people": "people",
}

# Phase 37A/39B/40: жаңа Мұғалім-тек placeholder route-тары — (route
# атауы, тақырып, бір сөйлемдік сипаттама). Нақты дерек/логика ЖОҚ.
# Phase 39B "dashboard"/"classes"/"my_results", Phase 40 "feedback_teacher",
# Phase 16 "results", Phase 19 "analytics", Phase 20 "question_bank"
# route-тарын НАҚТЫ беттермен ауыстырды (төменде, ``_router.register()``
# арқылы) — енді осы тізімде БОС.
_PLACEHOLDER_ROUTES: tuple[tuple[str, str, str], ...] = ()

# Phase 41: QSplitter-дегі Sidebar-дың бастапқы/жабылған ені —
# ``ui.widgets.sidebar``-дың өз ``_EXPANDED_WIDTH``/``_COLLAPSED_WIDTH``
# мәндерімен БІРДЕЙ (қасақана дублирленген жеке константа, жобаның
# бұрыннан бар кіші lookup/константа дублирлеу конвенциясы).
_SIDEBAR_DEFAULT_WIDTH = 230
_SIDEBAR_COLLAPSED_WIDTH = 60

# § Offline-First + Cloud Sync Foundation §14 "Sync Status UI": ``domain.
# entities.sync_status.SyncStatus``-тың ``.value``-мен сәйкес кілттер —
# ``SyncThreadController.sync_finished``-тен ҚАРАПАЙЫМ ``str`` ретінде
# келеді (Qt Signal-дың enum-ды тікелей тасымалдамауының орнына, § ``sync_
# engine.py`` докстрингінде түсіндірілген ұстаным). "syncing" аралық
# күйі ``sync_started`` сигналында бөлек өңделеді (төменде).
_SYNC_STATUS_DISPLAY: dict[str, tuple[str, str]] = {
    "offline": ("● Офлайн", "#9AA1AC"),
    "synced": ("● Синхрондалды", "#2E7D32"),
    "sync_error": ("● Синхрондау қатесі", "#C62828"),
    # § Phase 3 (Production Authentication + Authorization) §9 "UI
    # Integration": "Authentication required" — ``SyncStatus.SYNC_ERROR``-
    # дан ӘДЕЙІ бөлек түс/мәтін (§ "сервер қатесі" ЕМЕС, "жергілікті
    # credential серверде қабылданбады немесе ешкім кірмеген" деп нақты
    # хабарлау үшін, § ``sync_engine.py::SyncStatus.AUTH_REQUIRED``).
    "auth_required": ("● Аутентификация қажет", "#F9A825"),
}
_SYNC_STATUS_SYNCING = ("● Синхрондалуда...", "#F9A825")
# § Phase 5 (Connectivity-Aware Automatic Sync) §9 "UI Status": жеңіл
# connectivity ping-нің ӨЗ индикаторы — "офлайн" мәтіні/түсі ЕСКІ
# ``_SYNC_STATUS_DISPLAY["offline"]``-мен БІРДЕЙ (§ "do not create a
# second status vocabulary"), тек "онлайн" осында ЖАҢА (§ ескі
# ``SyncStatus.ONLINE`` мәні бұрын ЕШҚАШАН эмитацияланбаған).
_CONNECTIVITY_STATUS_ONLINE = ("● Онлайн", "#2E7D32")

# § Phase 5 §8 "Teacher Monitoring Update Strategy": pull-мен жаңа дерек
# келгенде (§ ``_on_sync_finished`` "pulled > 0") ЕГЕР ағымдағы route
# осы жиында болса, сол беттің ``on_enter()``-ін ҚАЙТА шақырады (§ ол
# ӨЗІ идемпотентті ``self._refresh()``, навигация ЕШҚАШАН қайталанбайды
# — тек дерек жаңарады, § ``ui/navigation/router.py`` докстрингі).
_AUTO_REFRESHABLE_ROUTES = frozenset(
    {
        "dashboard", "results", "analytics", "data_journal", "feedback_teacher", "my_results", "feedback_student",
        # § Phase 6 (Teacher Live Classroom Monitoring Dashboard) §14
        # "Auto-Refresh": ЕКІ жаңа route де ``on_enter(param=None)``
        # "sticky last value" паттерні арқылы параметрсіз қайта
        # шақыруды қауіпсіз өңдейді (§ ``ClassroomMonitoringPage``/
        # ``StudentMonitoringDetailPage`` докстрингтері).
        "classroom_monitoring", "student_monitoring",
    }
)


class MainWindow(QMainWindow):
    """Негізгі терезе: global ``Sidebar`` арқылы қолжетімді ``HomePage`` →
    ``ExperimentListPage`` → ``ExperimentWorkspacePage`` навигация ағынын,
    сондай-ақ ``SettingsPage``/``HelpPage`` беттерін баптайтын жіңішке shell.

    ``self.device_manager`` — application lifetime бойы өмір сүретін
    persistent құрылғы қосылымдары (бір рет осында жасалады, ``Experiment
    WorkspacePage``-ке беріледі — сол бет барлық навигацияда қайта
    пайдаланылатындықтан, сенсор қосылымдары эксперимент ауысқанда
    сақталады). ``app.py`` осы атрибутты ``QApplication.aboutToQuit``-ке
    жалғап, application жабылғанда ғана порттарды жабады. Рөл ауысуы
    (§7 "Режимді ауыстыру") бұл терезені/``device_manager``-ды ЕШҚАШАН
    қайта құрмайды — тек навигация/рөл күйі өзгереді.
    """

    def __init__(
        self,
        module_registry: ModuleRegistry | None = None,
        device_manager: DeviceManager | None = None,
        session_repository: ISessionRepository | None = None,
        measurement_batch_repository: IMeasurementBatchRepository | None = None,
        feedback_repository: IFeedbackRepository | None = None,
        teacher_note_repository: ITeacherNoteRepository | None = None,
        classroom_repository: IClassroomRepository | None = None,
        student_repository: IStudentRepository | None = None,
        active_student_repository: IActiveStudentRepository | None = None,
        teacher_repository: ITeacherRepository | None = None,
        active_teacher_repository: IActiveTeacherRepository | None = None,
        student_progress_repository: IStudentProgressRepository | None = None,
        initial_role: UserRole = UserRole.TEACHER,
        home_page: HomePage | None = None,
        devices_page: DevicesPage | None = None,
        experiment_list_page: ExperimentListPage | None = None,
        experiment_workspace_page: ExperimentWorkspacePage | None = None,
        data_journal_page: DataJournalPage | None = None,
        settings_page: SettingsPage | None = None,
        about_page: HelpPage | None = None,
        role_selection_page: RoleSelectionPage | None = None,
        class_management_page: ClassManagementPage | None = None,
        student_results_page: StudentResultsPage | None = None,
        student_feedback_page: StudentFeedbackPage | None = None,
        teacher_dashboard_page: TeacherDashboardPage | None = None,
        teacher_feedback_review_page: TeacherFeedbackReviewPage | None = None,
        teacher_management_page: TeacherManagementPage | None = None,
        results_page: ResultsPage | None = None,
        analytics_page: AnalyticsPage | None = None,
        question_repository: IQuestionRepository | None = None,
        question_bank_page: QuestionBankPage | None = None,
        app_preferences: AppPreferences | None = None,
        sync_thread_controller: SyncThreadController | None = None,
        classroom_monitoring_page: ClassroomMonitoringPage | None = None,
        student_monitoring_page: StudentMonitoringDetailPage | None = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle("Arduino Physics Lab")
        # Кезeng 29: терезе енді showMaximized() арқылы ашылады (app.py) —
        # бұл төменгі шектеу (auto-resize/қолмен кішірейту кезінде де
        # layout бұзылмауы үшін).
        self.setMinimumSize(1024, 700)

        self._current_role = initial_role
        self._module_registry = module_registry or ModuleRegistry()
        self.device_manager = device_manager or DeviceManager()
        # Data Journal: аяқталған сессияларды сақтайтын ортақ репозиторий
        # (ExperimentWorkspacePage жазады, DataJournalPage оқиды). Әдепкі
        # ":memory:" (SqliteSessionRepository-дың өз әдепкісі) — тек
        # app.py ғана нақты файл жолымен береді.
        self.session_repository: ISessionRepository = (
            session_repository or SqliteSessionRepository()
        )
        # Phase 4 (Raw Arduino Measurement Cloud Sync): session_
        # repository-мен БІРДЕЙ ортақ-данасы принципі (ExperimentWorkspacePage
        # жазады, ``SyncWorker`` push/pull етеді).
        self.measurement_batch_repository: IMeasurementBatchRepository = (
            measurement_batch_repository or SqliteMeasurementBatchRepository()
        )
        # Phase 39A: үш деңгейлі кері байланыс/бағалау — raw
        # measurements-тен МҮЛДЕ БӨЛЕК репозиторий, session_repository-мен
        # БІРДЕЙ ортақ-данасы принципі (ExperimentWorkspacePage жазады).
        self.feedback_repository: IFeedbackRepository = (
            feedback_repository or SqliteFeedbackRepository()
        )
        # Phase 7 (Teacher Actions, Feedback Delivery, and Session History):
        # feedback_repository-мен БІРДЕЙ ортақ-данасы принципі, БІРАҚ МҮЛДЕ
        # БӨЛЕК кесте/тұжырымдама.
        self.teacher_note_repository: ITeacherNoteRepository = (
            teacher_note_repository or SqliteTeacherNoteRepository()
        )
        # Phase 39B: сыныптар/оқушылар/белсенді оқушы/прогресс —
        # session_repository/feedback_repository-мен БІРДЕЙ ортақ-данасы
        # принципі (бәрі бір физикалық файлды бөліседі, ``app.py``-де).
        self.classroom_repository: IClassroomRepository = (
            classroom_repository or SqliteClassroomRepository()
        )
        self.student_repository: IStudentRepository = (
            student_repository or SqliteStudentRepository()
        )
        self.active_student_repository: IActiveStudentRepository = (
            active_student_repository or SqliteActiveStudentRepository()
        )
        # Multi-Teacher Accounts фазасы: жүйені пайдаланатын мұғалім
        # аккаунттары — classroom_repository/student_repository-мен
        # БІРДЕЙ ортақ-данасы принципі.
        self.teacher_repository: ITeacherRepository = (
            teacher_repository or SqliteTeacherRepository()
        )
        self.active_teacher_repository: IActiveTeacherRepository = (
            active_teacher_repository or SqliteActiveTeacherRepository()
        )
        self.student_progress_repository: IStudentProgressRepository = (
            student_progress_repository or SqliteStudentProgressRepository(
                session_repository=self.session_repository,
                feedback_repository=self.feedback_repository,
                classroom_repository=self.classroom_repository,
                student_repository=self.student_repository,
            )
        )
        # Phase 20 (Question Bank): бақылау/рефлексия сұрақтары — session_
        # repository-мен БІРДЕЙ ортақ-данасы принципі (Question Bank
        # жазады, ExperimentWorkspacePage оқиды/студентке көрсетеді).
        # Репозиторий БОС болса (жаңа/ескі дерекқор файлы), статик
        # каталогтың (§ ``ExperimentDefinition.assessment``) бұрыннан бар
        # сұрақтары бір реттік, ЕШҚАШАН жойылмайтын түрде көшіріледі (§
        # "Preserve existing data. No destructive migration").
        # Phase 22 (Settings): SettingsPage жазады/ExperimentWorkspacePage
        # (жаңа MeasurementWorkspace данасының бастапқы күйі үшін) оқиды —
        # session_repository-мен БІРДЕЙ ортақ-данасы принципі.
        self.app_preferences: AppPreferences = app_preferences or AppPreferences()
        # § Offline-First + Cloud Sync Foundation §16 "Background Sync":
        # ``None`` әдепкісі ЕШБІР жаңа QThread жаратпайды (§ бұрыннан бар
        # 2000+ regression тестер ``MainWindow()``-ды осы параметрсіз
        # құрастырады, § "no unnecessary hardware/network initialization"
        # принципімен БІРДЕЙ). Тек ``app.py::run()`` нақты данасын береді
        # ЖӘНЕ startup-тан кейін нақты іске қосады (§ ``build_main_window()``
        # ӨЗІ де тек ҚҰРАСТЫРАДЫ, синхрондауды АВТОМАТТЫ ЕШҚАШАН бастамайды).
        self.sync_thread_controller: SyncThreadController | None = sync_thread_controller
        # § Phase 5 (Connectivity-Aware Automatic Sync): ағымдағы route
        # атауын сақтайды (§ ``_on_route_changed()`` — "auto-refresh the
        # currently visible data-dependent page on pull") ЖӘНЕ толық
        # sync циклі жүріп жатқанын білдіреді (§ ``_on_connectivity_
        # changed()`` "Синхрондалуда..." мәтінін ЕШҚАШАН баспайды).
        self._current_route_name: str | None = None
        self._is_sync_cycle_active = False
        self.question_repository: IQuestionRepository = (
            question_repository or SqliteQuestionRepository()
        )
        seed_questions_from_catalog(self.question_repository, self._module_registry)
        # Mode Switch + Student Access Screen Redesign: кодсыз қалған
        # қолданыстағы оқушыларға бір реттік, идемпотентті backfill (§
        # ``seed_questions_from_catalog``-пен БІРДЕЙ принцип). ``app.py``
        # ЖӘНЕ ``MainWindow`` екеуі де осыны шақырады (startup экраны
        # ``MainWindow`` құрылғанға дейін кодты қажет етеді) — идемпотентті
        # болғандықтан қайталап шақыру қауіпсіз.
        backfill_missing_student_codes(self.classroom_repository, self.student_repository)
        # Multi-Teacher Accounts §11 "First Teacher / Backward
        # Compatibility": ``teachers`` кестесі БОС болса, ескі жалғыз-PIN
        # конфигурациясынан БІР дефолт мұғалім жазбасын құрады (§
        # ``backfill_missing_student_codes``-пен БІРДЕЙ идемпотентті
        # принцип — ``app.py`` ЖӘНЕ ``MainWindow`` екеуі де шақырады).
        backfill_default_teacher(self.teacher_repository, self.classroom_repository)
        # § Phase 1/2 backfill (§ ``domain/services/sync_migration.py``
        # докстрингі) — идемпотентті, ``backfill_default_teacher``-мен
        # БІРДЕЙ конвенция. ``sync_outbox_repository`` берілмеген
        # репозиторийлерде (мыс. raw ``MainWindow()`` тестерде) бұл
        # шақыру толықтай ешнәрсе жасамайды (§ ``_enqueue()`` ``None``
        # outbox-та no-op).
        backfill_sync_ids(self.classroom_repository, self.student_repository, self.teacher_repository)
        backfill_session_sync_queue(
            self.session_repository, self.student_progress_repository, self.feedback_repository
        )
        # § Phase 4 "Legacy Measurement Handling" backfill (§ ``sync_
        # migration.py::backfill_measurement_batches()`` докстрингі) —
        # жоғарыдағы екі backfill-мен БІРДЕЙ конвенция.
        backfill_measurement_batches(
            self.session_repository,
            self.measurement_batch_repository,
            self.app_preferences.get_measurement_batch_chunk_size(),
        )
        # §6 "Data Ownership / Filtering": Мұғалім-тек беттер (Сыныптар
        # мен оқушылар/Бақылау тақтасы/Кері байланысты тексеру/Нәтижелер/
        # Аналитика/Деректер журналы) осы БІР decorator арқылы АҒЫМДАҒЫ
        # аутентификацияланған мұғалімнің тағайындалған сыныптарымен
        # шектеледі — беттердің ІШКІ логикасы МҮЛДЕ өзгертілмейді (§
        # "extend the existing architecture", decorator тек ``list_
        # active()``/``list_all()``-ті сүзеді, жазу әдістері/``get()``
        # өзгеріссіз ішкі репозиторийге бағытталады).
        self._teacher_scoped_classroom_repository: IClassroomRepository = (
            TeacherScopedClassroomRepository(
                self.classroom_repository, self.teacher_repository, self.active_teacher_repository
            )
        )

        self._sidebar = Sidebar(
            role=self._current_role, device_manager=self.device_manager, parent=self
        )
        # Ескі top-nav-bar кезіндегі public атрибут келісімін сақтау үшін
        # (тестер ``window._settings_button``/``window._about_button``
        # арқылы тікелей қол жеткізеді) — жаңа батырма жасалмайды, тек
        # sidebar-дың дәл сол объектілеріне алиас қойылады. Мұғалім-тек
        # батырмалар болғандықтан, Оқушы рөлінде бұл алиастар ЖОҚ болуы
        # мүмкін (батырма сол рөлде мүлде жоқ) — қауіпсіз ``.get()``.
        self._settings_button = self._sidebar.buttons.get("settings")
        self._about_button = self._sidebar.buttons.get("help")
        self._sidebar.navigate_requested.connect(self._on_sidebar_navigate)
        self._sidebar.switch_role_requested.connect(self._on_switch_role_requested)
        self._sidebar.switch_student_requested.connect(self._on_switch_student_requested)

        self._stack = QStackedWidget(self)
        self._stack.setObjectName("WorkspaceStack")
        # 15. УАҚЫТША ДИАГНОСТИКА: QStackedWidget-тің әр бет ауысуы.
        self._stack.currentChanged.connect(self._on_stack_current_changed)
        self._router = Router(self._stack, is_route_allowed=self._is_route_allowed)
        self._router.route_changed.connect(self._on_route_changed)

        # Phase 41: WorkspaceBackdrop — ``self._stack``-ты ораған, секцияға
        # тәуелді су таңба фонын салатын контейнер (§ ThemeManager-де
        # ``QStackedWidget#WorkspaceStack``/бет класы селекторлары арқылы
        # мөлдір етілген, сондықтан су таңба беттердің НАҚТЫ бос
        # аймағында ғана көрінеді).
        self._workspace_backdrop = WorkspaceBackdrop(self)
        backdrop_layout = QVBoxLayout(self._workspace_backdrop)
        backdrop_layout.setContentsMargins(0, 0, 0, 0)
        backdrop_layout.addWidget(self._stack)

        # Phase 41: Sidebar/жұмыс кеңістігі арасында сүйрелетін бөлгіш.
        # ``setChildrenCollapsible(False)`` — сүйреумен КЕЗДЕЙСОҚ толық
        # жабылу МҮМКІН ЕМЕС, тек Sidebar-дың өз "collapse" батырмасы
        # ғана нақты жабады (``collapse_toggled`` арқылы). Анимациясыз,
        # ЖЕДЕЛ өлшем ауысуы — Qt-тың дефолт сүйреу/``setSizes()``
        # мінез-құлқы, қосымша QPropertyAnimation ЕШҚАШАН қосылмаған.
        self._splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self._splitter.setObjectName("MainWindowSplitter")
        self._splitter.setChildrenCollapsible(False)
        self._splitter.setHandleWidth(5)
        self._splitter.addWidget(self._sidebar)
        self._splitter.addWidget(self._workspace_backdrop)
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setSizes([_SIDEBAR_DEFAULT_WIDTH, 4000])
        self._sidebar.collapse_toggled.connect(self._on_sidebar_collapse_toggled)
        self.setCentralWidget(self._splitter)

        self._home_page = home_page or HomePage(
            self._module_registry, device_manager=self.device_manager
        )
        self._home_page.set_devices_action_visible(self._current_role is UserRole.TEACHER)
        self._devices_page = devices_page or DevicesPage(device_manager=self.device_manager)
        self._experiment_list_page = experiment_list_page or ExperimentListPage(
            module_registry=self._module_registry
        )
        self._experiment_workspace_page = experiment_workspace_page or (
            ExperimentWorkspacePage(
                device_manager=self.device_manager,
                session_repository=self.session_repository,
                measurement_batch_repository=self.measurement_batch_repository,
                feedback_repository=self.feedback_repository,
                active_student_repository=self.active_student_repository,
                student_progress_repository=self.student_progress_repository,
                question_repository=self.question_repository,
                module_registry=self._module_registry,
                app_preferences=self.app_preferences,
                sync_thread_controller=self.sync_thread_controller,
            )
        )
        self._experiment_workspace_page.set_role(self._current_role)
        self._data_journal_page = data_journal_page or DataJournalPage(
            session_repository=self.session_repository,
            module_registry=self._module_registry,
            classroom_repository=self._teacher_scoped_classroom_repository,
            student_repository=self.student_repository,
            student_progress_repository=self.student_progress_repository,
        )
        self._settings_page = settings_page or SettingsPage(
            app_preferences=self.app_preferences
        )
        self._settings_page.set_teacher_count(len(self.teacher_repository.list_active()))
        self._about_page = about_page or HelpPage()
        self._role_selection_page = role_selection_page or RoleSelectionPage(
            student_repository=self.student_repository,
            active_student_repository=self.active_student_repository,
            teacher_repository=self.teacher_repository,
            active_teacher_repository=self.active_teacher_repository,
        )
        self._teacher_management_page = teacher_management_page or TeacherManagementPage(
            teacher_repository=self.teacher_repository,
            classroom_repository=self.classroom_repository,
        )

        # Phase 39B: нақты Сыныптар/Оқушыны таңдау/Менің нәтижелерім/
        # Бақылау тақтасы беттері — 3 бұрынғы PlaceholderPage-тің орнына.
        # §6 "Data Ownership / Filtering": ``classroom_repository`` ЕНДІ
        # мұғалім-тек беттерге ТЕАCHER-SCOPED decorator арқылы беріледі
        # (§ ``_teacher_scoped_classroom_repository`` жоғарыда) — беттің
        # ІШКІ логикасы МҮЛДЕ өзгертілмеген, тек классрум тізімі енді
        # ағымдағы мұғалімнің тағайындалған сыныптарымен шектеледі.
        self._class_management_page = class_management_page or ClassManagementPage(
            classroom_repository=self._teacher_scoped_classroom_repository,
            student_repository=self.student_repository,
            student_progress_repository=self.student_progress_repository,
            feedback_repository=self.feedback_repository,
            session_repository=self.session_repository,
            module_registry=self._module_registry,
        )
        self._student_results_page = student_results_page or StudentResultsPage(
            active_student_repository=self.active_student_repository,
            student_repository=self.student_repository,
            student_progress_repository=self.student_progress_repository,
            feedback_repository=self.feedback_repository,
            session_repository=self.session_repository,
            module_registry=self._module_registry,
        )
        self._student_feedback_page = student_feedback_page or StudentFeedbackPage(
            active_student_repository=self.active_student_repository,
            student_repository=self.student_repository,
            student_progress_repository=self.student_progress_repository,
            feedback_repository=self.feedback_repository,
            session_repository=self.session_repository,
            module_registry=self._module_registry,
            teacher_note_repository=self.teacher_note_repository,
        )
        self._teacher_dashboard_page = teacher_dashboard_page or TeacherDashboardPage(
            student_progress_repository=self.student_progress_repository,
            classroom_repository=self._teacher_scoped_classroom_repository,
            student_repository=self.student_repository,
            module_registry=self._module_registry,
            teacher_repository=self.teacher_repository,
            active_teacher_repository=self.active_teacher_repository,
        )
        self._teacher_feedback_review_page = teacher_feedback_review_page or TeacherFeedbackReviewPage(
            classroom_repository=self._teacher_scoped_classroom_repository,
            student_repository=self.student_repository,
            student_progress_repository=self.student_progress_repository,
            feedback_repository=self.feedback_repository,
            session_repository=self.session_repository,
            module_registry=self._module_registry,
            teacher_repository=self.teacher_repository,
            active_teacher_repository=self.active_teacher_repository,
        )
        self._results_page = results_page or ResultsPage(
            classroom_repository=self._teacher_scoped_classroom_repository,
            student_repository=self.student_repository,
            student_progress_repository=self.student_progress_repository,
            feedback_repository=self.feedback_repository,
            session_repository=self.session_repository,
            module_registry=self._module_registry,
            teacher_repository=self.teacher_repository,
            active_teacher_repository=self.active_teacher_repository,
        )
        self._analytics_page = analytics_page or AnalyticsPage(
            classroom_repository=self._teacher_scoped_classroom_repository,
            student_repository=self.student_repository,
            student_progress_repository=self.student_progress_repository,
            module_registry=self._module_registry,
            teacher_repository=self.teacher_repository,
            active_teacher_repository=self.active_teacher_repository,
        )
        self._question_bank_page = question_bank_page or QuestionBankPage(
            question_repository=self.question_repository,
            module_registry=self._module_registry,
        )
        # § Phase 6 (Teacher Live Classroom Monitoring Dashboard):
        # ``_teacher_scoped_classroom_repository``-мен БІРДЕЙ мұғалім-
        # шектеу принципі (§ басқа мұғалім-тек беттермен БІРДЕЙ).
        self._classroom_monitoring_page = classroom_monitoring_page or ClassroomMonitoringPage(
            classroom_repository=self._teacher_scoped_classroom_repository,
            student_repository=self.student_repository,
            student_progress_repository=self.student_progress_repository,
            session_repository=self.session_repository,
            module_registry=self._module_registry,
        )
        self._student_monitoring_page = student_monitoring_page or StudentMonitoringDetailPage(
            student_repository=self.student_repository,
            classroom_repository=self._teacher_scoped_classroom_repository,
            student_progress_repository=self.student_progress_repository,
            session_repository=self.session_repository,
            module_registry=self._module_registry,
            teacher_note_repository=self.teacher_note_repository,
            active_teacher_repository=self.active_teacher_repository,
        )

        self._profile_page = ProfilePage(preferences=self.app_preferences)
        self._people_page = PeoplePage(preferences=self.app_preferences)
        self._router.register("profile", self._profile_page)
        self._router.register("people", self._people_page)
        self._router.register("home", self._home_page)
        self._router.register("devices", self._devices_page)
        self._router.register("experiment_list", self._experiment_list_page)
        self._router.register("experiment_workspace", self._experiment_workspace_page)
        self._router.register("data_journal", self._data_journal_page)
        self._router.register("settings", self._settings_page)
        self._router.register("about", self._about_page)
        self._router.register("role_selection", self._role_selection_page)
        self._router.register("classes", self._class_management_page)
        self._router.register("my_results", self._student_results_page)
        self._router.register("feedback_student", self._student_feedback_page)
        self._router.register("dashboard", self._teacher_dashboard_page)
        self._router.register("feedback_teacher", self._teacher_feedback_review_page)
        self._router.register("results", self._results_page)
        self._router.register("analytics", self._analytics_page)
        self._router.register("question_bank", self._question_bank_page)
        self._router.register("teacher_management", self._teacher_management_page)
        self._router.register("classroom_monitoring", self._classroom_monitoring_page)
        self._router.register("student_monitoring", self._student_monitoring_page)

        self._placeholder_pages: dict[str, PlaceholderPage] = {}
        for route_key, title, description in _PLACEHOLDER_ROUTES:
            page = PlaceholderPage(title, description)
            page.back_requested.connect(self._on_placeholder_back)
            self._router.register(route_key, page)
            self._placeholder_pages[route_key] = page

        self._home_page.module_selected.connect(self._on_module_selected)
        self._home_page.experiment_selected.connect(self._on_experiment_selected)
        self._home_page.devices_requested.connect(lambda: self._router.navigate("devices"))
        self._home_page.labs_requested.connect(
            lambda: self._router.navigate("experiment_list")
        )
        self._home_page.results_requested.connect(lambda: self._router.navigate("my_results"))
        self._experiment_list_page.experiment_selected.connect(
            self._on_experiment_selected
        )
        self._experiment_list_page.back_requested.connect(self._on_experiment_list_back)
        self._experiment_workspace_page.back_requested.connect(
            self._on_experiment_workspace_back
        )
        self._experiment_workspace_page.student_selection_requested.connect(
            self._open_student_login
        )
        self._experiment_workspace_page.measurement_running_changed.connect(
            lambda running: self._sidebar.set_switch_student_enabled(not running)
        )
        self._role_selection_page.role_selected.connect(self._on_role_selected)
        self._role_selection_page.student_login_succeeded.connect(
            self._on_student_login_succeeded
        )
        self._student_results_page.student_selection_requested.connect(
            self._open_student_login
        )
        self._student_feedback_page.student_selection_requested.connect(
            self._open_student_login
        )
        # Phase 13 (Teacher Dashboard Quick Actions) — HomePage-тегі
        # devices_requested/labs_requested-пен БІРДЕЙ "page emits signal,
        # MainWindow navigates" конвенциясы (§ "Sidebar-дың Router-ді
        # өзі білмейді" принципімен БІРДЕЙ, беттерге де қолданылады).
        self._teacher_dashboard_page.classes_requested.connect(
            lambda: self._router.navigate("classes")
        )
        self._teacher_dashboard_page.labs_requested.connect(
            lambda: self._router.navigate("experiment_list")
        )
        self._teacher_dashboard_page.devices_requested.connect(
            lambda: self._router.navigate("devices")
        )
        self._teacher_dashboard_page.results_requested.connect(
            lambda: self._router.navigate("results")
        )
        # § Phase 6 (Teacher Live Classroom Monitoring Dashboard): Dashboard
        # → Classroom → Student → Experiment detail навигация тізбегі,
        # артқа қайту сигналдарымен қоса (§20 "Navigation").
        self._teacher_dashboard_page.classroom_monitoring_requested.connect(
            lambda: self._router.navigate("classroom_monitoring")
        )
        self._classroom_monitoring_page.student_selected.connect(
            lambda student_id, experiment_id: self._router.navigate(
                "student_monitoring", student_id=student_id, experiment_id=experiment_id
            )
        )
        # § Phase 8 (Advanced Analytics & Learning Progress): "direct
        # navigation from analytics to student monitoring" —
        # ``classroom_monitoring_page.student_selected``-пен ДӘЛ БІРДЕЙ
        # пішін/мақсат route (§ Architecture Decision #6, ЖАҢА бет ЖОҚ).
        self._analytics_page.student_monitoring_requested.connect(
            lambda student_id, experiment_id: self._router.navigate(
                "student_monitoring", student_id=student_id, experiment_id=experiment_id
            )
        )
        self._teacher_dashboard_page.student_monitoring_requested.connect(
            lambda student_id, experiment_id: self._router.navigate(
                "student_monitoring", student_id=student_id, experiment_id=experiment_id
            )
        )
        self._classroom_monitoring_page.back_requested.connect(
            lambda: self._router.navigate("dashboard")
        )
        self._student_monitoring_page.back_requested.connect(
            lambda: self._router.navigate("classroom_monitoring")
        )
        # § Phase 7 (Part C "Session History"): StudentMonitoringDetailPage
        # → DataJournalPage, student_id арқылы сүзілген (§ ЖАҢА бет ЖОҚ,
        # § "reuse ResultsPage/DataJournalPage if they already provide
        # the required functionality" — ``DataJournalPage`` ӨЗІ Live
        # GraphWidget-ті ӘЛДЕҚАШАН иеленеді).
        self._student_monitoring_page.session_history_requested.connect(
            lambda student_id: self._router.navigate("data_journal", student_id=student_id)
        )
        # §7 "Add a teacher management section inside: Баптаулар" —
        # SettingsPage-тің ӨЗІ навигацияны білмейді (§ "Sidebar-дың
        # Router-ді өзі білмейді" принципімен БІРДЕЙ), тек сұраныс
        # сигналын шығарады.
        self._settings_page.manage_teachers_requested.connect(
            lambda: self._router.navigate("teacher_management")
        )
        # § Offline-First + Cloud Sync Foundation §15 "Manual Sync":
        # SettingsPage-тің "Қазір синхрондау" батырмасы — ``trigger_
        # manual_sync()`` контроллер жоқ болса қауіпсіз ешнәрсе жасамайды.
        self._settings_page.sync_now_requested.connect(self.trigger_manual_sync)
        if self.sync_thread_controller is not None:
            self.sync_thread_controller.sync_started.connect(self._on_sync_started)
            self.sync_thread_controller.sync_finished.connect(self._on_sync_finished)
            self.sync_thread_controller.error_occurred.connect(self._on_sync_error)
            # § Phase 5 (Connectivity-Aware Automatic Sync) §9 "UI Status".
            self.sync_thread_controller.connectivity_changed.connect(self._on_connectivity_changed)
        self._teacher_management_page.back_requested.connect(
            lambda: self._router.navigate("settings")
        )
        self._teacher_management_page.teachers_changed.connect(
            self._on_teachers_changed
        )

        self._refresh_active_student_display()
        self._refresh_active_teacher_display()
        _trace_logger.info(
            "11. MainWindow.__init__ finished, id=%s, role=%s", id(self), self._current_role
        )
        self._navigate_to_role_landing(self._current_role)

    def _on_stack_current_changed(self, index: int) -> None:
        """15. УАҚЫТША ДИАГНОСТИКА: ``self._stack`` (WorkspaceStack) ішінде
        ағымдағы бет ауысқан сайын шақырылады."""
        widget = self._stack.widget(index)
        _trace_logger.info(
            "15. QStackedWidget page changed -> index=%s, widget=%s", index, type(widget).__name__
        )

    def _is_route_allowed(self, route_name: str) -> bool:
        return is_route_allowed_for_role(route_name, self._current_role)

    def _on_route_changed(self, route_name: str) -> None:
        """``Router.route_changed`` — WorkspaceBackdrop-тың секциясын
        route-қа сай жаңартады. ``experiment_workspace`` route-ы үшін
        секция НАҚТЫ ағымдағы тәжірибенің меншікті модуліне тәуелді
        (``ExperimentWorkspacePage.current_module_accent_key()``),
        қалған барлық route үшін статикалық кесте жеткілікті.
        """
        self._current_route_name = route_name
        if route_name == "experiment_workspace":
            category = resolve_experiment_category(
                self._experiment_workspace_page.current_module_accent_key()
            )
        else:
            category = resolve_route_category(route_name)
        self._workspace_backdrop.set_category(category)
        # Mode Switch + Student Access Screen Redesign §13: "MODE SWITCH
        # SCREEN"/"STUDENT CODE ENTRY" — sidebar толық жасырылады (ені/
        # collapse күйі ЕШҚАШАН өзгертілмейді, § "Do not permanently
        # alter sidebar width"). Qt QSplitter жасырын пейнаның тұтқасын
        # автоматты жасырады — "ghost divider" қалмайды.
        self._sidebar.setVisible(route_name != "role_selection")

    def _on_sidebar_collapse_toggled(self, collapsed: bool) -> None:
        """Sidebar батырмасы жаңа collapsed күйін хабарлағанда, splitter-дің
        нақты пиксель бөлінісін ЖЕДЕЛ (анимациясыз) қайта белгілейді —
        Sidebar-дың өз ``setFixedWidth``/``setMinimumWidth``/
        ``setMaximumWidth`` шақыруы ғана splitter-дің ІШКІ layout-ын
        әрдайым дереу дұрыс қайта бөлуге кепілдік бермейді.
        """
        width = _SIDEBAR_COLLAPSED_WIDTH if collapsed else _SIDEBAR_DEFAULT_WIDTH
        self._splitter.setSizes([width, 4000])

    def _navigate_to_role_landing(self, role: UserRole) -> None:
        """Рөлге сай бастапқы route-қа өтеді. Оқушы режимінде белсенді
        оқушы әлі таңдалмаса, ЕШҚАШАН "home"-ге ЕМЕС — "Оқушыны таңдаңыз"
        бетіне бағыттайды (§ "Student mode must not begin a new
        measurement session" — сол сияқты, ешбір бет мүлде ашылмайды,
        әйтпесе оқушысыз "Басты бет" көрінер еді).
        """
        if role is UserRole.STUDENT and self.active_student_repository.get() is None:
            self._open_student_login()
            return
        self._router.navigate(default_landing_route(role))

    def _open_student_login(self) -> None:
        """§ "Student switching... should now open the same full-screen
        Student Login surface. Do not show the old classroom/student
        dropdown screen." — ескі ``StudentSelectionPage`` route-ы МҮЛДЕ
        ЖОҚ, барлық "оқушыны таңда/ауыстыр" сұранысы ДӘЛ СОЛ
        ``RoleSelectionPage``-ке, тікелей кіру-код көрінісіне бағытталады
        (мод таңдау экраны аттап өтіледі)."""
        self._router.navigate("role_selection", view="student_login")

    def _on_module_selected(self, module: IPhysicsModule) -> None:
        self._router.navigate("experiment_list", module=module)

    def _on_experiment_list_back(self) -> None:
        self._router.navigate("home")

    def _on_experiment_selected(self, experiment: ExperimentDefinition) -> None:
        self._router.navigate("experiment_workspace", experiment=experiment)

    def _on_experiment_workspace_back(self) -> None:
        # Тәжірибе HomePage-тен single-module drill-down арқылы да, sidebar/
        # Home-нің толық Labs каталогынан да ашылуы мүмкін — Back екеуінде
        # де БІРДЕЙ, әрдайым толық каталогқа апарады (module беруcіз,
        # experiment_list.on_enter()-дің module=None әдепкісі). Бұрын
        # соңғы single-module таңдауын ("_current_module") қайта
        # пайдаланатын, соның салдарынан stale модуль (мыс. эксперимент
        # sidebar арқылы ашылса) Back-та қате көрсетілетін.
        self._router.navigate("experiment_list")

    def _on_placeholder_back(self) -> None:
        self._router.navigate(default_landing_route(self._current_role))

    def _on_sidebar_navigate(self, key: str) -> None:
        self._router.navigate(_SIDEBAR_ROUTES[key])

    def _on_switch_role_requested(self) -> None:
        # §14 "Logout / Switch Mode": "Режімді ауыстыру" ЖАЗЫЛҒАН мұғалім
        # контекстін ДЕРЕУ тазалайды (§ "CLEAR current_teacher... Never
        # leave the previous teacher identity cached in the UI") — жаңа
        # логин ӘРҚАШАН таза сессиямен басталады, ескі мұғалім аты бір
        # сәтке де көрінбейді (route "role_selection"-ге ауысу сидбарды
        # дереу жасырады).
        self.active_teacher_repository.clear()
        self._refresh_active_teacher_display()
        self._router.navigate("role_selection")

    def _on_role_selected(self, role: UserRole) -> None:
        """"🔁 Режимді ауыстыру" ағыны — ``MainWindow``/``device_manager``/
        сессия күйі ЕШҚАШАН қайта құрылмайды, тек навигация/рөл өзгереді.
        """
        self._experiment_workspace_page.close_open_dialogs()
        self._current_role = role
        self._experiment_workspace_page.set_role(role)
        self._sidebar.set_role(role)
        self._home_page.set_devices_action_visible(role is UserRole.TEACHER)
        self._refresh_active_student_display()
        self._refresh_active_teacher_display()
        self._navigate_to_role_landing(role)

    def _on_switch_student_requested(self) -> None:
        """Sidebar-дың "👤 Оқушыны ауыстыру" әрекеті. Белсенді өлшеу жүріп
        жатса (§ "stop or reject switching during an active measurement"),
        Sidebar батырмасы ӘЛДЕҚАШАН ``set_switch_student_enabled(False)``
        арқылы өшірілген болуы тиіс — бұл тексеру екінші, тәуелсіз
        қорғаныс сызығы.
        """
        if self._experiment_workspace_page.is_measurement_running():
            return
        self._experiment_workspace_page.close_open_dialogs()
        self._open_student_login()

    def _on_student_login_succeeded(self) -> None:
        """``RoleSelectionPage.student_login_succeeded`` — код расталды,
        ``active_student_repository`` ЖАҢА беттің ӨЗІНДЕ ЖАЗЫЛҒАН (§
        жалғыз canonical дереккөз, § "Do NOT create a second active-
        student state variable"). Егер рөл әлі Оқушы болмаса (бастапқы
        кіру НЕМЕСЕ "Режімді ауыстыру"), ``_on_role_selected``-ті ҚАЙТА
        пайдаланамыз — ``_navigate_to_role_landing`` енді НАҚТЫ белсенді
        оқушыны табады, сондықтан қайта redirect-сіз тіке "Басты бетке"
        өтеді. Рөл ӘЛДЕҚАШАН Оқушы болса ("Оқушыны ауыстыру"), жай ғана
        ``_on_student_selected()``-ті қайта пайдаланамыз.
        """
        if self._current_role is not UserRole.STUDENT:
            self._on_role_selected(UserRole.STUDENT)
            return
        self._on_student_selected()

    def _on_student_selected(self) -> None:
        """Белсенді оқушы контексі ЕНДІ ``active_student_repository``-де
        сақталған. Экспериментов бетінің блокталған күйі/ownership-і
        ағымдағы тәжірибе болса ғана ``refresh_active_student()`` арқылы
        қайта бағаланады (§ "load the selected student's relevant
        progress").
        """
        self._refresh_active_student_display()
        self._experiment_workspace_page.refresh_active_student()
        self._router.navigate(default_landing_route(UserRole.STUDENT))

    def _refresh_active_student_display(self) -> None:
        """Sidebar/ExperimentWorkspacePage/HomePage-тегі белсенді оқушы
        мәтінін/қорытындысын жаңартады — тек Оқушы режимінде мағыналы,
        Мұғалім режимінде барлығы тазаланады (Sidebar-дың ӨЗІ де рөлге
        қарай жасырады, бірақ мәтін де стейл қалмауы үшін тазаланады).
        """
        if self._current_role is not UserRole.STUDENT:
            self._sidebar.set_active_student_text(None)
            self._experiment_workspace_page.set_active_student_header_text(None)
            self._home_page.set_student_context(None, None, None)
            return

        context = self.active_student_repository.get()
        if context is None:
            self._sidebar.set_active_student_text(None)
            self._experiment_workspace_page.set_active_student_header_text(None)
            self._home_page.set_student_context(None, None, None)
            return

        student = self.student_repository.get(context.student_id)
        classroom = self.classroom_repository.get(context.classroom_id)
        if student is None:
            self._sidebar.set_active_student_text(None)
            self._experiment_workspace_page.set_active_student_header_text(None)
            self._home_page.set_student_context(None, None, None)
            return

        classroom_name = classroom.name if classroom is not None else "—"
        text = f"Оқушы: {student.display_name}\nСынып: {classroom_name}"
        self._sidebar.set_active_student_text(text)
        self._experiment_workspace_page.set_active_student_header_text(text)

        summary = compute_student_home_summary(
            self._module_registry, self.student_progress_repository, student.id
        )
        self._home_page.set_student_context(student.display_name, classroom_name, summary)

    def _refresh_active_teacher_display(self) -> None:
        """§5 "Teacher Dashboard": Sidebar-дағы аутентификацияланған
        мұғалімнің аты-жөнін жаңартады — тек Мұғалім режимінде мағыналы
        (§ ``_refresh_active_student_display()``-пен БІРДЕЙ принцип,
        Мұғалім еместе/контекст жоқта/жазба табылмаса ӘРҚАШАН тазаланады,
        § "no Teacher A information may remain visible").
        """
        if self._current_role is not UserRole.TEACHER:
            self._sidebar.set_active_teacher_text(None)
            return
        context = self.active_teacher_repository.get()
        if context is None:
            self._sidebar.set_active_teacher_text(None)
            return
        teacher = self.teacher_repository.get(context.teacher_id)
        if teacher is None:
            self._sidebar.set_active_teacher_text(None)
            return
        self._sidebar.set_active_teacher_text(teacher.full_name)

    def _on_teachers_changed(self) -> None:
        """``TeacherManagementPage.teachers_changed`` — мұғалім қосылған/
        өзгертілген/белсенді(емес) етілгенде, Баптаулар бетіндегі
        мұғалім санын ЖӘНЕ (ағымдағы аутентификацияланған мұғалім өз
        атын өзгерткен болуы мүмкін болғандықтан) Sidebar-дағы аты-жөнін
        жаңартады."""
        self._settings_page.set_teacher_count(len(self.teacher_repository.list_active()))
        self._refresh_active_teacher_display()

    # ---- Offline-First + Cloud Sync Foundation §14/§15 --------------------

    def trigger_manual_sync(self) -> None:
        """§15 "Manual Sync": Баптаулар бетіндегі "Қазір синхрондау"
        батырмасы ЖӘНЕ ``app.py::run()`` startup-after-UI триггерінің
        ортақ кіру нүктесі. Контроллер берілмеген болса (мыс. тестер,
        немесе әлі рөл таңдалмаған экран) ешнәрсе жасамайды."""
        if self.sync_thread_controller is not None:
            self.sync_thread_controller.run_sync_now()

    def _on_sync_started(self) -> None:
        self._is_sync_cycle_active = True
        text, color = _SYNC_STATUS_SYNCING
        self._sidebar.set_sync_status_text(text, color)
        self._settings_page.set_sync_status_text(text)

    def _on_sync_finished(
        self, status: str, pushed: int, pulled: int, errors: str, pending_count: int
    ) -> None:
        self._is_sync_cycle_active = False
        text, color = _SYNC_STATUS_DISPLAY.get(status, _SYNC_STATUS_DISPLAY["sync_error"])
        self._sidebar.set_sync_status_text(text, color)
        detail = f"{text} (жүктелді: {pushed}, алынды: {pulled})"
        # §24 "Sync Indicator": pending outbox саны тек НӨЛДЕН КӨП болғанда
        # ғана көрсетіледі (§ "do not clutter the interface" — қалыпты,
        # толық синхрондалған күйде ешбір қосымша мәтін жоқ).
        if pending_count > 0:
            detail += f", Синхрондауды күтуде: {pending_count}"
        self._settings_page.set_sync_status_text(detail)
        # § Phase 5 §8 "Teacher Monitoring Update Strategy" / "smallest
        # safe mechanism": жаңа pull-мен келген дерек БАР болса ЖӘНЕ
        # пайдаланушы дәл ҚАЗІР сол деректі көрсететін бетте тұрса,
        # сол бетті ҚАЙТА жаңартады — polling ЕШБІР бет ІШІНДЕ ЖОҚ,
        # тек осы БІР орталық choke point-та.
        if pulled > 0 and self._current_route_name in _AUTO_REFRESHABLE_ROUTES:
            self._refresh_current_page_if_data_dependent()

    def _refresh_current_page_if_data_dependent(self) -> None:
        page = self._stack.currentWidget()
        on_enter = getattr(page, "on_enter", None)
        if callable(on_enter):
            on_enter()

    def _on_sync_error(self, message: str) -> None:
        self._is_sync_cycle_active = False
        text, color = _SYNC_STATUS_DISPLAY["sync_error"]
        self._sidebar.set_sync_status_text(text, color)
        self._settings_page.set_sync_status_text(f"{text}: {message}")

    def _on_connectivity_changed(self, is_online: bool, pending_count: int) -> None:
        """§3/§9 "UI Status": ЖЕҢІЛ connectivity ping-нің НӘТИЖЕСІ —
        толық sync циклі ЖҮРІП ЖАТҚАНДА (§ ``_is_sync_cycle_active``)
        бұл ЕШҚАШАН "Синхрондалуда..."/қорытынды мәтінін үстінен
        жазбайды (§ ``_on_sync_started``/``_on_sync_finished`` ӨЗДЕРІ
        дәлірек ақпарат көрсетеді)."""
        if self._is_sync_cycle_active:
            return
        if is_online:
            text, color = _CONNECTIVITY_STATUS_ONLINE
        else:
            text, color = _SYNC_STATUS_DISPLAY["offline"]
        self._sidebar.set_sync_status_text(text, color)
        detail = text
        if pending_count > 0:
            detail += f", Синхрондауды күтуде: {pending_count}"
        self._settings_page.set_sync_status_text(detail)
