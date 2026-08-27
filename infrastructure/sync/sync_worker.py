"""SyncWorker — worker thread ішінде өмір сүретін, ``SyncEngine``-ді
іске қосатын QObject (§16 "Background Sync": "never do HTTP on the Qt
main thread").

``SerialWorker``-мен ДӘЛ БІРДЕЙ Worker Object pattern: барлық thread-
сезімтал ресурс (sqlite3 байланыстары, ``httpx.Client``, ``QTimer``)
worker thread-ке ``moveToThread()`` жасалғаннан КЕЙІН, ``initialize()``
слотында ғана құрылады — конструктор тек қарапайым мәндерді (db_path)
сақтайды.

§27 "Logging": бұл модуль payload МАЗМҰНЫН ЕШҚАШАН логтамайды/
сигналға шығармайды — тек ``SyncResult.status``/сандар/қате мәтіні
(§ ``domain/services/sync_engine.py`` докстрингі — сол ұстаным осында
жалғасады).

§ Phase 5 (Connectivity-Aware Automatic Sync + Near-Real-Time Classroom
Monitoring): ЕКІ ЖАҢА, ӨЗ мақсатына сай тәуелсіз таймер қосылды —

    ``_connectivity_timer`` — ЖЕҢІЛ (тек ``check_health()``, ЕШБІР
    толық push/pull ЕМЕС), қысқа интервалды (§ ``AppPreferences.
    get_connectivity_check_interval_seconds()``, әдепкі 12с) —
    OFFLINE->ONLINE ауысуын анықтап, СОЛ СӘТТЕ ғана ``run_sync_now()``
    шақырады (§4 "Connectivity-Restored Push Trigger" — тұрақты
    ONLINE күйде ӘРБІР tick толық циклды ЕШҚАШАН қайта бастамайды,
    § "avoid excessive server requests when idle").

    ``_periodic_timer`` — Phase 1-3-тегі ескі БЕКІТІЛГЕН 15-минуттық
    таймердің ӨЗІ, ЕНДІ рөлге БЕЙІМ: ағымдағы белсенді сәйкестік
    мұғалім болса, ҚЫСҚА ``teacher_auto_refresh_interval_seconds``
    (әдепкі 10с) қолданады — §8 "Teacher Monitoring Update Strategy".
    Оқушы/белгісіз рөлде ЕСКІ 15-минуттық интервал ӨЗГЕРІССІЗ қалады
    (§ "avoid excessive server requests when idle" — оқушы жақындығы
    connectivity-restored/active-experiment триггерлері арқылы
    қамтамасыз етіледі, § ``experiment_workspace_page.py``).

``run_sync_now()`` (§6 "Sync Trigger Coalescing") ЕНДІ БАСҚА
триггерден бас тартпайды (ескі "drop-on-busy" мінез-құлқы ОРНЫНА) —
циклда болса, ЖАЛҒЫЗ ``_rerun_requested`` жалауын орнатады да, ағымдағы
цикл аяқталғанда ДӘЛ БІР рет қосымша циклды өзі шақырады (§ "if useful,
remember that another sync was requested and run one additional cycle
afterward" — рекурсия ЕМЕС, ``while`` циклы, § "never run multiple
overlapping SyncEngine cycles" HARD requirement).
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from domain.services.connectivity_monitor import ConnectivityMonitor
from domain.services.sync_auth import get_configured_sync_api_key
from domain.services.sync_engine import SyncEngine
from infrastructure.storage.app_preferences import AppPreferences
from infrastructure.storage.sqlite_active_student_repository import SqliteActiveStudentRepository
from infrastructure.storage.sqlite_active_teacher_repository import SqliteActiveTeacherRepository
from infrastructure.storage.sqlite_classroom_repository import SqliteClassroomRepository
from infrastructure.storage.sqlite_feedback_repository import SqliteFeedbackRepository
from infrastructure.storage.sqlite_measurement_batch_repository import SqliteMeasurementBatchRepository
from infrastructure.storage.sqlite_session_repository import SqliteSessionRepository
from infrastructure.storage.sqlite_student_progress_repository import SqliteStudentProgressRepository
from infrastructure.storage.sqlite_student_repository import SqliteStudentRepository
from infrastructure.storage.sqlite_sync_outbox_repository import SqliteSyncOutboxRepository
from infrastructure.storage.sqlite_teacher_note_repository import SqliteTeacherNoteRepository
from infrastructure.storage.sqlite_teacher_repository import SqliteTeacherRepository
from infrastructure.sync.http_sync_api_client import HttpSyncApiClient

# §16 "no continuous polling" / "low-frequency periodic" — 15 минут сайын
# бір рет, тек ``AppPreferences.get_sync_enabled()`` ақиқат болса, ТЕК
# оқушы/белгісіз рөл үшін (§ Phase 5 модуль докстрингі — мұғалім рөлі
# ЖЫЛДАМ ``teacher_auto_refresh_interval_seconds``-ты қолданады).
_PERIODIC_INTERVAL_MS = 15 * 60 * 1000
_ROLE_TEACHER = "teacher"


class SyncWorker(QObject):
    sync_started = Signal()
    # status(str) — SyncStatus.value, pushed(int), pulled(int), errors_joined(str),
    # pending_count(int) — §24 "Sync Indicator": қалған outbox жазба саны
    # (§ "pending outbox count may be exposed subtly").
    sync_finished = Signal(str, int, int, str, int)
    error_occurred = Signal(str)
    # § Phase 5 §9 "UI Status": is_online(bool), pending_count(int) — ТЕК
    # НАҚТЫ ауысу болғанда эмитацияланады (§ ``ConnectivityMonitor.
    # check().changed`` — "avoid noisy UI", тұрақты online/offline
    # күйде ЕШБІР қайталама сигнал жоқ).
    connectivity_changed = Signal(bool, int)

    def __init__(self, db_path: str) -> None:
        super().__init__()
        self._db_path = db_path
        self._preferences: AppPreferences | None = None
        self._engine: SyncEngine | None = None
        self._outbox_repository: SqliteSyncOutboxRepository | None = None
        self._active_teacher_repository: SqliteActiveTeacherRepository | None = None
        self._active_student_repository: SqliteActiveStudentRepository | None = None
        self._api_client: HttpSyncApiClient | None = None
        self._periodic_timer: QTimer | None = None
        self._connectivity_timer: QTimer | None = None
        self._is_syncing = False
        self._rerun_requested = False
        self._connectivity_monitor = ConnectivityMonitor()

    @Slot()
    def initialize(self) -> None:
        """``AppPreferences``/репозиторийлер/``SyncEngine``-ді worker
        thread ішінде құрады. Екінші рет шақырылса ешнәрсе жасамайды."""
        if self._engine is not None:
            return
        try:
            self._preferences = AppPreferences()
            outbox_repository = SqliteSyncOutboxRepository(self._db_path)
            self._outbox_repository = outbox_repository
            classroom_repository = SqliteClassroomRepository(
                self._db_path, sync_outbox_repository=outbox_repository
            )
            student_repository = SqliteStudentRepository(
                self._db_path, sync_outbox_repository=outbox_repository
            )
            teacher_repository = SqliteTeacherRepository(
                self._db_path, sync_outbox_repository=outbox_repository
            )
            # § Phase 2 (Experiment Session + Results + Feedback Cloud
            # Sync): session_repository/feedback_repository БІРІНШІ
            # (student_progress_repository оларды композиция арқылы
            # қолданады, § ``SqliteStudentProgressRepository`` докстрингі).
            session_repository = SqliteSessionRepository(
                self._db_path, sync_outbox_repository=outbox_repository
            )
            feedback_repository = SqliteFeedbackRepository(
                self._db_path, sync_outbox_repository=outbox_repository
            )
            student_progress_repository = SqliteStudentProgressRepository(
                self._db_path,
                session_repository=session_repository,
                feedback_repository=feedback_repository,
                classroom_repository=classroom_repository,
                student_repository=student_repository,
                sync_outbox_repository=outbox_repository,
            )
            # § Phase 4 (Raw Arduino Measurement Cloud Sync): БАСҚА
            # репозиторийлермен БІРДЕЙ ортақ ``self._db_path`` (§ "each
            # separate sqlite3.connect(':memory:') creates an isolated
            # database" қатесінен қорғаныс — өндірісте нақты файл жолы
            # болғандықтан бұл қате мүмкін ЕМЕС, БІРАҚ паттерн бірдей
            # сақталады).
            measurement_batch_repository = SqliteMeasurementBatchRepository(
                self._db_path, sync_outbox_repository=outbox_repository
            )
            # § Phase 7 (Teacher Actions, Feedback Delivery, and Session
            # History): БАСҚА репозиторийлермен БІРДЕЙ ортақ ``self._db_path``.
            teacher_note_repository = SqliteTeacherNoteRepository(
                self._db_path, sync_outbox_repository=outbox_repository
            )
            api_client = HttpSyncApiClient(
                base_url=self._preferences.get_sync_api_base_url(),
                api_key=get_configured_sync_api_key(),
                request_timeout=self._preferences.get_sync_request_timeout(),
            )
            self._api_client = api_client
            # § Phase 3 (Production Authentication + Authorization):
            # ЖЕРГІЛІКТІ "кім қазір кірген" контекстін оқу үшін (§
            # ``role_selection_page.py`` PIN/код растаған сәтте осы
            # кестелерге жазады). Мұғалім БАСЫМ (§ екеуі де сирек, тек
            # рөл ауысу кезінде БІРАЗ уақыт қатар қалуы мүмкін жағдай
            # үшін қорғаныс ретінде). ``self.`` атрибуттары ретінде
            # сақталады (§ Phase 5: ``_periodic_interval_ms()`` де ДӘЛ
            # осы логиканы қайта пайдаланады, § модуль докстрингі).
            self._active_teacher_repository = SqliteActiveTeacherRepository(self._db_path)
            self._active_student_repository = SqliteActiveStudentRepository(self._db_path)

            self._engine = SyncEngine(
                classroom_repository,
                student_repository,
                teacher_repository,
                outbox_repository,
                api_client,
                get_pull_cursor=self._preferences.get_sync_pull_cursor,
                set_pull_cursor=self._preferences.set_sync_pull_cursor,
                session_repository=session_repository,
                student_progress_repository=student_progress_repository,
                feedback_repository=feedback_repository,
                get_active_role_and_sync_id=self._get_active_role_and_sync_id,
                get_cached_token=self._preferences.get_sync_auth_token,
                set_cached_token=self._preferences.set_sync_auth_token,
                measurement_batch_repository=measurement_batch_repository,
                teacher_note_repository=teacher_note_repository,
            )

            self._periodic_timer = QTimer(self)
            self._periodic_timer.setSingleShot(True)
            self._periodic_timer.timeout.connect(self._on_periodic_timer_tick)
            self._periodic_timer.start(self._periodic_interval_ms())

            self._connectivity_timer = QTimer(self)
            self._connectivity_timer.setInterval(self._connectivity_check_interval_ms())
            self._connectivity_timer.timeout.connect(self._on_connectivity_timer_tick)
            self._connectivity_timer.start()
        except Exception as exc:  # қорғаныс: болжанбаған қате де сыртқа шықпайды
            self.error_occurred.emit(f"SyncWorker.initialize() қатесі: {exc}")

    def _get_active_role_and_sync_id(self) -> tuple[str, str] | None:
        if self._active_teacher_repository is None or self._active_student_repository is None:
            return None
        teacher_context = self._active_teacher_repository.get()
        if teacher_context is not None:
            return _ROLE_TEACHER, teacher_context.teacher_id
        student_context = self._active_student_repository.get()
        if student_context is not None:
            return "student", student_context.student_id
        return None

    def _periodic_interval_ms(self) -> int:
        """§8 "Teacher Monitoring Update Strategy": мұғалім рөлі
        белсенді болса ҚЫСҚА auto-refresh интервалы, әйтпесе ЕСКІ
        15-минуттық "eventual consistency" сақшысы (§ модуль
        докстрингі)."""
        identity = self._get_active_role_and_sync_id()
        if identity is not None and identity[0] == _ROLE_TEACHER and self._preferences is not None:
            return max(1, self._preferences.get_teacher_auto_refresh_interval_seconds()) * 1000
        return _PERIODIC_INTERVAL_MS

    def _connectivity_check_interval_ms(self) -> int:
        if self._preferences is None:
            return 12_000
        return max(1, self._preferences.get_connectivity_check_interval_seconds()) * 1000

    @Slot()
    def _on_periodic_timer_tick(self) -> None:
        self.run_sync_now()
        # § "single-shot self-reschedule" паттерні — рөл өзгерсе (мыс.
        # оқушы -> мұғалім), келесі tick ЖАҢА (қысқа/ұзын) интервалмен
        # қайта есептеледі (§ Qt-тың айнымалы-интервалды repeating
        # timer үшін стандартты идиомасы).
        if self._periodic_timer is not None:
            self._periodic_timer.start(self._periodic_interval_ms())

    @Slot()
    def _on_connectivity_timer_tick(self) -> None:
        """§3 "Automatic Connectivity Monitor": ЖЕҢІЛ ``check_health()``
        ғана — толық push/pull циклі ЕМЕС. Толық цикл ӘЛІ ЖҮРІП жатса
        (§ ``_is_syncing``), бұл tick ешнәрсе жасамайды (§ "avoid
        excessive server requests" — толық цикл ӨЗІ де байланысты
        дәлелдейді, § ``_run_sync_cycle()`` соңында мемлекет
        ``_connectivity_monitor``-ға ЖЕТКІЗІЛЕДІ)."""
        if self._engine is None or self._is_syncing or self._api_client is None:
            return
        self._apply_live_sync_config()
        is_online = self._api_client.check_health()
        self._update_connectivity_state(is_online, trigger_sync_on_restore=True)

    def _update_connectivity_state(self, is_online: bool, trigger_sync_on_restore: bool) -> None:
        """§ ЕКІ ШАҚЫРУШЫ, ЕКІ ӘРТҮРЛІ мақсат: ``_on_connectivity_timer_
        tick()`` (жеңіл ping) ЖАҢА "connectivity restored" анықтаса,
        ЖЕДЕЛ ``run_sync_now()`` шақыруы КЕРЕК (§4). ``_run_sync_cycle()``
        (ТОЛЫҚ цикл ӨЗ нәтижесінен мемлекетті жаңартады) — ЕШҚАШАН
        ``trigger_sync_on_restore=True`` бермейді, әйтпесе ӘРБІР
        "офлайннан кейінгі бірінші сәтті цикл" ӨЗ-ӨЗІН рекурсивті түрде
        тағы бір қосымша циклға коалесцирлеп жіберер еді (§ нақты
        табылған/түзетілген қате — "sync storm of one extra cycle
        every time connectivity is first established")."""
        result = self._connectivity_monitor.check(is_online)
        if result.changed:
            pending_count = (
                self._outbox_repository.count_pending() if self._outbox_repository is not None else 0
            )
            self.connectivity_changed.emit(result.is_online, pending_count)
        if result.just_came_online and trigger_sync_on_restore:
            # §4 "Connectivity-Restored Push Trigger" — ЖЕДЕЛ, дереу
            # (debounce/тұрақтылық кезеңі: келесі ``_connectivity_timer``
            # tick-і ӨЗІ табиғи debounce рөлін атқарады — жиілігі
            # ``connectivity_check_interval_seconds``-пен шектелген,
            # § "avoid sync storms").
            self.run_sync_now()

    @Slot()
    def run_sync_now(self) -> None:
        """§6 "Sync Trigger Coalescing": БІР рет push+pull циклін
        жүргізеді. Қатар шақырылса (мыс. периодты timer, connectivity-
        restored, белсенді тәжірибе, қолмен сұрау бірнешеуі бір
        мезгілде түссе), ЕКІНШІ шақыру циклды ҚАЙТА БАСТАМАЙДЫ — тек
        "тағы бір рет керек" жалауын орнатады, ағымдағы цикл
        аяқталғанда ДӘЛ БІР қосымша цикл автоматты жүреді (§ "never
        run multiple overlapping SyncEngine cycles" HARD requirement,
        § модуль докстрингі)."""
        if self._engine is None:
            return
        self._apply_live_sync_config()
        if self._preferences is not None and not self._preferences.get_sync_enabled():
            return
        if self._is_syncing:
            self._rerun_requested = True
            return
        self._run_sync_cycle()

    def _run_sync_cycle(self) -> None:
        """§ "while" циклы — рекурсия ЕМЕС (§ "avoid recursive sync
        loops" — көп триггер жиналса да, Python call stack ешқашан
        өспейді, § модуль докстрингі)."""
        while True:
            self._is_syncing = True
            self._rerun_requested = False
            self.sync_started.emit()
            try:
                result = self._engine.run_sync()
                pending_count = (
                    self._outbox_repository.count_pending() if self._outbox_repository is not None else 0
                )
                self.sync_finished.emit(
                    result.status.value, result.pushed, result.pulled, "; ".join(result.errors), pending_count
                )
                # § connectivity-монитор мемлекетін толық циклдің ӨЗ
                # нәтижесімен де жаңартады — арнайы ping-сіз де "соңғы
                # белгілі" күй дұрыс қалады (§ ``SyncStatus.OFFLINE``
                # ЖАЛҒЫЗ "желі жоқ" сигналы). ``trigger_sync_on_restore=
                # False`` — ӨЗІМІЗ ДӘЛ ҚАЗІР бір толық циклды аяқтадық,
                # тағы бірін ШАҚЫРУДЫҢ қажеті ЖОҚ (§ ``_update_
                # connectivity_state()`` докстрингі — түзетілген қате).
                self._update_connectivity_state(
                    result.status.value != "offline", trigger_sync_on_restore=False
                )
            except Exception as exc:  # noqa: BLE001 - желі/сервер қатесі күтілетін жол
                self.error_occurred.emit(f"run_sync_now() қатесі: {exc}")
            finally:
                self._is_syncing = False
            if not self._rerun_requested:
                break
            # § "sync disabled" күйі коалесцирленген қайта-циклда да
            # құрметтелуі керек — пайдаланушы дәл осы аралықта sync-ты
            # өшірсе, қосымша цикл ЕШҚАШАН жүрмейді.
            if self._preferences is not None and not self._preferences.get_sync_enabled():
                break

    def _apply_live_sync_config(self) -> None:
        """Баптауларда өзгерген URL/кілтті келесі циклге дереу қолданады.
        Тест дублерлерінде ``configure`` болмаса ештеңе жасамайды."""
        if self._api_client is None or self._preferences is None:
            return
        configure = getattr(self._api_client, "configure", None)
        if configure is None:
            return
        configure(
            base_url=self._preferences.get_sync_api_base_url(),
            api_key=get_configured_sync_api_key(),
            request_timeout=self._preferences.get_sync_request_timeout(),
        )

    def shutdown(self) -> None:
        """Екі таймерді де тоқтатады. sqlite3 байланыстары процесс
        аяқталғанда ОС арқылы жабылады (§ басқа sqlite репозиторийлерде
        де ерекше ``close()`` шақыру талап етілмейтін established
        конвенция)."""
        if self._periodic_timer is not None:
            self._periodic_timer.stop()
            self._periodic_timer = None
        if self._connectivity_timer is not None:
            self._connectivity_timer.stop()
            self._connectivity_timer = None
        self._engine = None
