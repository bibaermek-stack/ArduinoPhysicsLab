"""Қолданбаны құрастыратын (bootstrap) модуль.

QApplication объектісін құру және негізгі объектілерді (ModuleRegistry,
MainWindow) қолмен байланыстыру осы жерде жүзеге асады.

DI container қолданылмайды — барлық тәуелділік осы файлда қолмен беріледі
(manual wiring).

Phase 37A: қолданба ЕНДІ ``RoleSelectionPage``-тен басталады —
``MainWindow``/``DeviceManager`` тек рөл нақты таңдалғаннан (Мұғалім
үшін — PIN расталғаннан) КЕЙІН құрылады (§2: "must not initialize... serial
devices unnecessarily" дейінгі).
"""

import logging
import os
import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from ui.widgets.motion import install_button_motion

# УАҚЫТША ДИАГНОСТИКА (§ main.py-дегі debug.log). Осы ДӘЛ СОЛ логгер
# атын әр модуль қолданады — жалғыз FileHandler ``main.py``-де қосылған.
_trace_logger = logging.getLogger("apl.trace")

from domain.entities.user_role import UserRole
from domain.services.student_access_code import backfill_missing_student_codes
from domain.services.teacher_migration import backfill_default_teacher
from infrastructure.storage.database import get_default_database_path
from infrastructure.storage.sqlite_active_student_repository import SqliteActiveStudentRepository
from infrastructure.storage.sqlite_active_teacher_repository import SqliteActiveTeacherRepository
from infrastructure.storage.sqlite_classroom_repository import SqliteClassroomRepository
from infrastructure.storage.sqlite_feedback_repository import SqliteFeedbackRepository
from infrastructure.storage.sqlite_measurement_batch_repository import SqliteMeasurementBatchRepository
from infrastructure.storage.sqlite_session_repository import SqliteSessionRepository
from domain.services.sync_migration import (
    backfill_measurement_batches,
    backfill_session_sync_queue,
    backfill_sync_ids,
)
from infrastructure.storage.app_preferences import AppPreferences
from infrastructure.storage.sqlite_student_progress_repository import SqliteStudentProgressRepository
from infrastructure.storage.sqlite_student_repository import SqliteStudentRepository
from infrastructure.storage.sqlite_sync_outbox_repository import SqliteSyncOutboxRepository
from infrastructure.storage.sqlite_teacher_note_repository import SqliteTeacherNoteRepository
from infrastructure.storage.sqlite_teacher_repository import SqliteTeacherRepository
from infrastructure.sync.sync_thread_controller import SyncThreadController
from modules.electricity.module import ElectricityModule
from modules.electromagnetism.module import ElectromagnetismModule
from modules.heat.module import HeatModule
from modules.light.module import LightModule
from modules.module_registry import ModuleRegistry
from ui.main_window import MainWindow
from ui.pages.account_auth_page import AccountAuthPage
from ui.pages.role_selection_page import RoleSelectionPage
from ui.themes.theme_manager import apply_application_theme
from infrastructure.sync.account_api_client import AccountApiClient, AccountApiError


def build_main_window(
    role: UserRole,
    db_path: str | Path | None = None,
    *,
    classroom_repository: SqliteClassroomRepository | None = None,
    student_repository: SqliteStudentRepository | None = None,
    active_student_repository: SqliteActiveStudentRepository | None = None,
    teacher_repository: SqliteTeacherRepository | None = None,
    active_teacher_repository: SqliteActiveTeacherRepository | None = None,
    sync_thread_controller: SyncThreadController | None = None,
) -> MainWindow:
    """Нақты қолданбамен (``run()``) БІРДЕЙ репозиторий/``MainWindow``
    composition — регрессия-тест пен нақты bootstrap арасында ЕШБІР
    алшақтық болмауы үшін, ``run()``-ның ӨЗІ де осы функцияны шақырады
    (§ Phase 41 кейінгі инцидент: скриншот-скрипт бір рет ``app.py``-ден
    алшақтап, жалған нәтиже берген еді — енді regression тест те, нақты
    bootstrap та БІР ғана функцияны шақырады, екеуі ешқашан ажырамайды).

    Mode Switch + Student Access Screen Redesign: ``classroom_repository``/
    ``student_repository``/``active_student_repository`` міндетті емес —
    ``run()`` бастапқы ``RoleSelectionPage`` экраны үшін осыларды
    АЛДЫН АЛА (``MainWindow`` құрылғанға дейін) құрастырады да, дәл СОЛ
    данаcын осында БЕРЕДІ (§ "Do NOT create a second active-student state
    variable" — оқушы кіру коды бастапқы экранда ЖАЗЫЛСА, MainWindow дәл
    СОЛ жазбаны, СОЛ физикалық SQLite байланысымен көреді). Берілмесе
    (мыс. тестерде), бұрынғыдай өз данасын құрастырады.
    """
    if db_path is None:
        db_path = get_default_database_path()
    _trace_logger.info("5. Database path: %s", db_path)

    # § Offline-First + Cloud Sync Foundation §16 "Background Sync": ТЕК
    # ҚҰРАСТЫРУ — ``SyncThreadController.__init__`` ешбір QThread
    # жаратпайды (§ ``infrastructure/sync/sync_thread_controller.py``
    # докстрингі, ``SerialThreadController``-мен БІРДЕЙ lazy-thread
    # принципі), сондықтан бұл жол регрессия тестерге ЕШБІР жаңа
    # thread/желі әрекетін қоспайды — нақты синхрондау тек ``run()``
    # startup-тан кейін немесе қолмен сұралғанда ғана басталады.
    sync_thread_controller = sync_thread_controller or SyncThreadController(str(db_path))
    # § Phase 2 (Experiment Session + Results + Feedback Cloud Sync) —
    # инцидент түзетуі: Phase 1-де ``sync_outbox_repository`` НАҚТЫ UI
    # жазатын репозиторийлерге ЕШҚАШАН БЕРІЛМЕГЕН болатын (тек
    # ``SyncWorker`` өз БӨЛЕК данасын құрастыратын, MainWindow-дың нақты
    # жазу жолымен МҮЛДЕ байланыссыз) — сол себепті нақты пайдаланушы
    # жазбалары (сынып/оқушы/мұғалім/сессия/кері байланыс) ЕШҚАШАН outbox-
    # қа түспей келген. Бұл жерде БІР ортақ outbox данасы құрылып, БАРЛЫҚ
    # осы функция иеленетін репозиторийге беріледі (§ Final Report "3.
    # discovered and fixed Phase 1 wiring gap").
    sync_outbox_repository = SqliteSyncOutboxRepository(db_path=db_path)

    # Phase 12 ("Subtle Motion System" §11): БІР reusable QApplication-
    # деңгейлік event filter — Sidebar/PrimaryButton/variant="secondary"/
    # "icon" (graph toolbar-ды да қамтиды) батырмаларының hover/pressed/
    # checked ауысуын орталықтан анимациялайды. ``run()`` ЖӘНЕ регрессия-
    # тесттер БІРДЕЙ осы функцияны шақыратындықтан (§ модуль docstring-і)
    # орнату дәл осында — қайталама орнатудан ``install_button_motion()``
    # өзі сақтайды.
    app_instance = QApplication.instance()
    if app_instance is not None:
        install_button_motion(app_instance)

    module_registry = ModuleRegistry()
    module_registry.register(HeatModule())
    module_registry.register(ElectricityModule())
    module_registry.register(ElectromagnetismModule())
    module_registry.register(LightModule())

    session_repository = SqliteSessionRepository(
        db_path=db_path, sync_outbox_repository=sync_outbox_repository
    )
    # Phase 4 (Raw Arduino Measurement Cloud Sync): session_repository-
    # мен БІРДЕЙ физикалық файл/outbox данасы.
    measurement_batch_repository = SqliteMeasurementBatchRepository(
        db_path=db_path, sync_outbox_repository=sync_outbox_repository
    )
    # Phase 39A: сол физикалық файл, бөлек кесте/байланыс (raw
    # measurements-тен МҮЛДЕ бөлек репозиторий).
    feedback_repository = SqliteFeedbackRepository(
        db_path=db_path, sync_outbox_repository=sync_outbox_repository
    )
    # Phase 7 (Teacher Actions, Feedback Delivery, and Session History):
    # feedback_repository-мен БІРДЕЙ ортақ-данасы принципі, БІРАҚ МҮЛДЕ
    # БӨЛЕК кесте/тұжырымдама (§ ``domain/entities/teacher_note.py``
    # докстрингі).
    teacher_note_repository = SqliteTeacherNoteRepository(
        db_path=db_path, sync_outbox_repository=sync_outbox_repository
    )
    # Phase 39B: сыныптар/оқушылар/белсенді оқушы/прогресс — БАРЛЫҒЫ
    # сол физикалық файл, әрқайсысы өз кестесімен/байланысымен.
    classroom_repository = classroom_repository or SqliteClassroomRepository(
        db_path=db_path, sync_outbox_repository=sync_outbox_repository
    )
    student_repository = student_repository or SqliteStudentRepository(
        db_path=db_path, sync_outbox_repository=sync_outbox_repository
    )
    active_student_repository = active_student_repository or SqliteActiveStudentRepository(
        db_path=db_path
    )
    # Multi-Teacher Accounts фазасы: classroom/student/active_student-
    # мен БІРДЕЙ принцип — ``run()`` бастапқы экран үшін АЛДЫН АЛА
    # құрастырса, дәл СОЛ данасы осында беріледі.
    teacher_repository = teacher_repository or SqliteTeacherRepository(
        db_path=db_path, sync_outbox_repository=sync_outbox_repository
    )
    active_teacher_repository = active_teacher_repository or SqliteActiveTeacherRepository(
        db_path=db_path
    )
    student_progress_repository = SqliteStudentProgressRepository(
        db_path=db_path,
        session_repository=session_repository,
        feedback_repository=feedback_repository,
        classroom_repository=classroom_repository,
        student_repository=student_repository,
        sync_outbox_repository=sync_outbox_repository,
    )

    # § Phase 1/2 backfill — ескі (sync-тен бұрынғы) жазбаларды outbox-қа
    # қосады (§ ``domain/services/sync_migration.py`` докстрингі).
    # Идемпотентті, ``backfill_missing_student_codes()``/``backfill_
    # default_teacher()``-мен БІРДЕЙ конвенция бойынша әр іске қосуда
    # шақырылады.
    backfill_sync_ids(classroom_repository, student_repository, teacher_repository)
    backfill_session_sync_queue(session_repository, student_progress_repository, feedback_repository)
    # § Phase 4 "Legacy Measurement Handling" backfill — Phase 4 кодынан
    # БҰРЫН жазылған сессиялардың raw measurement-дерін batch-қа бөліп
    # кезекке қояды (§ ``sync_migration.py::backfill_measurement_
    # batches()`` докстрингі), жоғарыдағы екі backfill-мен БІРДЕЙ
    # конвенция.
    backfill_measurement_batches(
        session_repository, measurement_batch_repository, AppPreferences().get_measurement_batch_chunk_size()
    )

    window = MainWindow(
        module_registry=module_registry,
        session_repository=session_repository,
        measurement_batch_repository=measurement_batch_repository,
        feedback_repository=feedback_repository,
        teacher_note_repository=teacher_note_repository,
        classroom_repository=classroom_repository,
        student_repository=student_repository,
        active_student_repository=active_student_repository,
        teacher_repository=teacher_repository,
        active_teacher_repository=active_teacher_repository,
        student_progress_repository=student_progress_repository,
        initial_role=role,
        sync_thread_controller=sync_thread_controller,
    )
    _trace_logger.info("11. MainWindow constructed, id=%s, role=%s", id(window), role)
    return window


def _configure_debug_logging() -> None:
    """``APL_DEBUG_SERIAL=1`` орта айнымалысы қойылса, ``DeviceIdentifier``-дің
    COM/HELLO diagnostic логтарын консольге шығарады (уақытша, hardware
    ақауларын аудиттеуге арналған — әдепкі бойынша өшірулі).
    """
    if not os.environ.get("APL_DEBUG_SERIAL"):
        return
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s.%(msecs)03d [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def run() -> int:
    """QApplication-ды құрып, рөл таңдау/оқушы кіру экранын көрсетіп,
    event loop-ты жүргізеді. ``MainWindow``/``DeviceManager`` ТЕК рөл
    нақты таңдалғаннан (немесе оқушы кіру коды расталғаннан) кейін
    құрылады (§2).

    Mode Switch + Student Access Screen Redesign: ``RoleSelectionPage``
    (мод таңдау + оқушы кіру коды бір ғана визуалды бет, § модуль
    докстрингі) ЕНДІ ``classroom_repository``/``student_repository``/
    ``active_student_repository``-ді ӨЗІ АЛДЫН АЛА қажет етеді (оқушы
    кодын шешу/``active_student_repository.set()`` үшін), сондықтан бұл
    репозиторийлер ``MainWindow`` құрылғанға дейін осында құрастырылады
    да, дәл СОЛ данасы ``build_main_window()``-ге беріледі — ЕКІНШІ
    active-student дереккөзі ЕШҚАШАН жасалмайды (§ "single source of
    truth"). Дәл СОЛ себеппен кодсыз қалған қолданыстағы оқушыларға
    арналған backfill де осы жерде, ``RoleSelectionPage`` көрсетілгенге
    ДЕЙІН жүреді — әйтпесе бастапқы экранда әлі кодсыз оқушы кіре
    алмас еді.
    """
    _configure_debug_logging()
    # Data Journal DB жолы (QStandardPaths.AppDataLocation) осы атаулар
    # орнатылғанға дейін дұрыс есептелмейді.
    QCoreApplication.setOrganizationName("ArduinoPhysicsLab")
    QCoreApplication.setApplicationName("ArduinoPhysicsLab")

    app = QApplication(sys.argv)
    apply_application_theme(AppPreferences().get_theme())
    # § "existing motion helper if already safe/available" — hover/
    # pressed/focus қозғалысы startup экранында да жұмыс істеуі үшін
    # (бұрын тек ``build_main_window()`` шақырылғанда, яғни рөл
    # таңдалғаннан КЕЙІН ғана орнатылатын — өзін-өзі сақтандыратын
    # болғандықтан ерте шақыру қауіпсіз, § модуль докстрингі).
    install_button_motion(app)

    db_path = get_default_database_path()
    _trace_logger.info("5. Database path: %s", db_path)
    # § Phase 2 wiring-gap fix (§ ``build_main_window()`` докстрингі) —
    # осы данасы ``build_main_window()``-дегі БӨЛЕК (БІРАҚ СОЛ физикалық
    # файлға көрсететін) outbox данасымен функционалды бірдей.
    sync_outbox_repository = SqliteSyncOutboxRepository(db_path=db_path)
    classroom_repository = SqliteClassroomRepository(
        db_path=db_path, sync_outbox_repository=sync_outbox_repository
    )
    student_repository = SqliteStudentRepository(
        db_path=db_path, sync_outbox_repository=sync_outbox_repository
    )
    active_student_repository = SqliteActiveStudentRepository(db_path=db_path)
    backfill_missing_student_codes(classroom_repository, student_repository)
    # Multi-Teacher Accounts §11 "First Teacher / Backward Compatibility":
    # ескі жалғыз-PIN конфигурациясынан БІР дефолт мұғалім жазбасын
    # идемпотентті түрде құрады (§ RoleSelectionPage-тің PIN арқылы
    # мұғалім іздеуі осы ``teacher_repository``-ге тәуелді, сондықтан
    # бұл ``RoleSelectionPage`` көрсетілгенге ДЕЙІН жүруі керек).
    teacher_repository = SqliteTeacherRepository(
        db_path=db_path, sync_outbox_repository=sync_outbox_repository
    )
    active_teacher_repository = SqliteActiveTeacherRepository(db_path=db_path)
    backfill_default_teacher(teacher_repository, classroom_repository)
    backfill_sync_ids(classroom_repository, student_repository, teacher_repository)

    app_preferences = AppPreferences()
    account_client = AccountApiClient(app_preferences)
    role_selection_page = RoleSelectionPage(
        student_repository=student_repository,
        active_student_repository=active_student_repository,
        teacher_repository=teacher_repository,
        active_teacher_repository=active_teacher_repository,
    )
    account_auth_page = AccountAuthPage(preferences=app_preferences)
    _trace_logger.info("6. AccountAuthPage opened")
    main_window_holder: list[MainWindow] = []
    cloud_role_page_holder: list[RoleSelectionPage] = []

    def _open_main_window(role: UserRole) -> None:
        _trace_logger.info("10. _open_main_window() entered, role=%s", role)
        window = build_main_window(
            role,
            db_path=db_path,
            classroom_repository=classroom_repository,
            student_repository=student_repository,
            active_student_repository=active_student_repository,
            teacher_repository=teacher_repository,
            active_teacher_repository=active_teacher_repository,
        )
        main_window_holder.append(window)
        # Кезeng 29: терезе әдепкі бойынша sizeHint()-ке (sidebar + бет
        # мазмұны) сай кішкентай өлшемде ашылатын — экранның үлкен бөлігі
        # пайдаланылмай қалатын. showMaximized() экранды толық пайдалануды
        # қамтамасыз етеді (MainWindow.setMinimumSize() төменгі шектеу ретінде).
        window.showMaximized()

        # Persistent sensor connections (DeviceManager, MainWindow арқылы
        # application lifetime бойы иеленіледі) ТЕК application шынымен
        # жабылғанда жабылады — эксперимент/бет ауысу кезінде ЕМЕС.
        app.aboutToQuit.connect(window.device_manager.shutdown_all)
        # Data Journal: белсенді (бар болса) сессияны жабылу алдында сақтайды —
        # ешбір serial port/DeviceManager-ге қатысы жоқ, тек .session-ды оқиды.
        app.aboutToQuit.connect(window._experiment_workspace_page.finalize_active_session)
        # § Offline-First + Cloud Sync Foundation §16 "triggers: startup-
        # after-UI": терезе көрсетілгеннен КЕЙІН ғана сұралады (§ "must
        # never block application startup") ЖӘНЕ жабылу алдында graceful
        # тоқтатылады (§ ``SerialThreadController``-мен БІРДЕЙ ``stop()``
        # конвенциясы). ``AppPreferences.get_sync_enabled()`` кодтағы
        # әдепкісі ``False``, БІРАҚ таратылатын ``deployment.json`` оны
        # қосуы мүмкін — сонда бірінші іске қосылымда HTTP сұрауы кетеді.
        if window.sync_thread_controller is not None:
            app.aboutToQuit.connect(window.sync_thread_controller.stop)
            window.trigger_manual_sync()

        window.logout_requested.connect(_on_logout)
        role_selection_page.close()
        account_auth_page.hide()
        for page in cloud_role_page_holder:
            page.close()

    def _show_cloud_role_picker() -> None:
        picker = RoleSelectionPage(
            student_repository=student_repository,
            active_student_repository=active_student_repository,
            teacher_repository=teacher_repository,
            active_teacher_repository=active_teacher_repository,
            cloud_account_mode=True,
        )
        cloud_role_page_holder.append(picker)

        def _picked_teacher(_role: UserRole) -> None:
            try:
                payload = account_client.select_role("teacher")
                account_client.store_session(payload, email="")
            except AccountApiError:
                pass
            picker.close()
            _open_main_window(UserRole.TEACHER)

        def _picked_student() -> None:
            try:
                payload = account_client.select_role("student")
                account_client.store_session(payload, email="")
            except AccountApiError:
                pass
            picker.close()
            _open_main_window(UserRole.STUDENT)

        picker.role_selected.connect(_picked_teacher)
        picker.student_login_succeeded.connect(_picked_student)
        picker.showMaximized()
        account_auth_page.hide()

    def _on_authenticated(payload: object) -> None:
        data = payload if isinstance(payload, dict) else {}
        needs_role = bool(data.get("needs_role") or not data.get("role"))
        if needs_role:
            _show_cloud_role_picker()
            return
        role = UserRole.TEACHER if data.get("role") == "teacher" else UserRole.STUDENT
        account_auth_page.hide()
        _open_main_window(role)

    def _detach_main_windows() -> None:
        while main_window_holder:
            window = main_window_holder.pop()
            try:
                app.aboutToQuit.disconnect(window.device_manager.shutdown_all)
            except (TypeError, RuntimeError):
                pass
            try:
                app.aboutToQuit.disconnect(window._experiment_workspace_page.finalize_active_session)
            except (TypeError, RuntimeError):
                pass
            if window.sync_thread_controller is not None:
                try:
                    app.aboutToQuit.disconnect(window.sync_thread_controller.stop)
                except (TypeError, RuntimeError):
                    pass
                window.sync_thread_controller.stop()
            window.device_manager.shutdown_all()
            window.close()

    def _on_logout() -> None:
        app_preferences.clear_account_session()
        app_preferences.clear_sync_auth_token()
        account_auth_page.prepare_for_reuse()
        account_auth_page.showMaximized()
        account_auth_page.raise_()
        account_auth_page.activateWindow()
        _detach_main_windows()

    def _start_offline() -> None:
        account_auth_page.hide()
        role_selection_page.showMaximized()

    account_auth_page.authenticated.connect(_on_authenticated)
    account_auth_page.skip_offline.connect(_start_offline)
    role_selection_page.role_selected.connect(_open_main_window)
    role_selection_page.student_login_succeeded.connect(
        lambda: _open_main_window(UserRole.STUDENT)
    )

    cached_role = app_preferences.get_account_role()
    cached_token = app_preferences.get_account_token()
    if cached_token and cached_role in ("teacher", "student"):
        _open_main_window(UserRole.TEACHER if cached_role == "teacher" else UserRole.STUDENT)
    else:
        account_auth_page.showMaximized()

    return app.exec()
