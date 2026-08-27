"""ExperimentWorkspacePage — таңдалған зертхана жұмысына арналған ортақ
жұмыс беті.

Тек интерфейсті басқарады: мәндерді көрсету, графикті жаңарту, кестені
жаңарту, батырмалар мен хабарламалар. Валидация/есептеу логикасы
ExperimentController-де орналасқан.

``on_enter(experiment)`` шақырылған сайын (немесе "оралу" батырмасы
басылғанда) алдыңғы ``ExperimentController`` толық тоқтатылып, таңдалған
зертхана жұмысына арналған жаңасы құрылады — қосылған құрылғымен
байланыс сақталмайды, пайдаланушы құрылғыны қайта анықтауы (Identify)
керек болады. Бұл V1-ге арналған әдейі қабылданған қарапайымдату.
"""

import logging
from collections.abc import Callable

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from domain.entities.active_student_context import ActiveStudentContext
from domain.entities.connected_device import ConnectedDevice
from domain.entities.experiment_assessment import ExperimentAssessmentDefinition
from domain.entities.experiment_definition import ExperimentDefinition
from domain.entities.experiment_feedback_result import ExperimentFeedbackResult, TeacherAssessment
from domain.entities.measurement import Measurement
from domain.entities.user_role import UserRole
from domain.interfaces.i_active_student_repository import IActiveStudentRepository
from domain.interfaces.i_feedback_repository import IFeedbackRepository
from domain.interfaces.i_physics_module import IPhysicsModule
from domain.interfaces.i_question_repository import IQuestionRepository
from domain.interfaces.i_measurement_batch_repository import IMeasurementBatchRepository
from domain.interfaces.i_session_repository import ISessionRepository
from domain.interfaces.i_student_progress_repository import IStudentProgressRepository
from domain.services.csv_exporter import CSVExporter
from domain.services.excel_exporter import ExcelExporter
from domain.services.experiment_conclusion import build_automatic_conclusion
from domain.services.experiment_feedback_service import build_student_safe_result
from domain.services.experiment_report_data import build_experiment_report_data
from domain.services.pdf_exporter import PDFExporter
from domain.services.question_bank_assembly import build_assessment_definition
from infrastructure.serial_comm.device_manager import DeviceManager
from infrastructure.serial_comm.device_scanner import DeviceScanner
from infrastructure.storage.app_preferences import AppPreferences
from infrastructure.storage.sqlite_active_student_repository import SqliteActiveStudentRepository
from infrastructure.storage.sqlite_feedback_repository import SqliteFeedbackRepository
from infrastructure.storage.sqlite_question_repository import SqliteQuestionRepository
from infrastructure.storage.sqlite_measurement_batch_repository import SqliteMeasurementBatchRepository
from infrastructure.storage.sqlite_session_repository import SqliteSessionRepository
from infrastructure.storage.sqlite_student_progress_repository import SqliteStudentProgressRepository
from infrastructure.sync.sync_thread_controller import SyncThreadController
from modules.electricity.experiment_controller import ExperimentController
from modules.electricity.multi_sensor_experiment_coordinator import (
    MultiSensorExperimentCoordinator,
)
from modules.module_registry import ModuleRegistry
from ui.widgets.device_panel import DevicePanel
from ui.widgets.experiment_diagram_dialog import ExperimentDiagramDialog
from ui.widgets.experiment_feedback_dialog import ExperimentFeedbackDialog
from ui.widgets.experiment_guide_dialog import ExperimentGuideDialog
from ui.widgets.experiment_report_dialog import ExperimentReportDialog
from ui.widgets.experiment_workflow_indicator import (
    ExperimentWorkflowIndicator,
    WorkflowStepState,
)
from ui.widgets.measurement_summary_card import MeasurementSummaryCard
from ui.widgets.motion import fade_label_color
from ui.widgets.simplified_device_connect_dialog import SimplifiedDeviceConnectDialog
from ui.themes.theme_manager import (
    COLOR_ACCENT,
    COLOR_SUCCESS,
    COLOR_TEXT_MUTED,
    COLOR_TEXT_SECONDARY,
    COLOR_WARNING,
)
from ui.widgets.measurement_workspace import MeasurementWorkspace

_ControllerFactory = Callable[[ExperimentDefinition], ExperimentController]
_CoordinatorFactory = Callable[[ExperimentDefinition], MultiSensorExperimentCoordinator]
_Pipeline = ExperimentController | MultiSensorExperimentCoordinator

# статус -> (мәтін, түс). Тек presentation — эксперименттің нақты
# ішкі күйін (is_running/is_ready) қайталамайды, соларға сәйкес шақырылады.
_STATUS_WAITING = "waiting"
_STATUS_READY = "ready"
_STATUS_STARTING = "starting"
_STATUS_RUNNING = "running"
_STATUS_STOPPED = "stopped"
_STATUS_CONFIG: dict[str, tuple[str, str]] = {
    # Phase 32.1: көпше түрге ауыстырылды — endi workspace hardware
    # жоқ кезде де толық көрінетіндіктен, бұл статус енді нақты
    # required-device checklist-пен (бірнеше сенсор) бірге көрінеді.
    _STATUS_WAITING: ("Құрылғылар күтілуде", COLOR_TEXT_SECONDARY),
    _STATUS_READY: ("Дайын", COLOR_SUCCESS),
    _STATUS_STARTING: ("Іске қосылуда...", COLOR_WARNING),
    _STATUS_RUNNING: ("Өлшеу жүріп жатыр", COLOR_ACCENT),
    _STATUS_STOPPED: ("Тоқтатылды", COLOR_TEXT_MUTED),
}
# Elapsed-time readout UI refresh жиілігі ("Ток жұмысы мен қуаты"-дағы
# "УАҚЫТ" картасы) — 10Hz жеткілікті (spec §4/§18), authoritative clock
# ЕМЕС, тек MultiSensorExperimentCoordinator.elapsed_seconds()-ті
# мезгіл-мезгіл экранға шығаратын презентация таймері.
_ELAPSED_TIMER_INTERVAL_MS = 100

# § Phase 4 (Raw Arduino Measurement Cloud Sync) "Partial Session
# Upload": ``_elapsed_timer``-мен (10Hz) МҮЛДЕ БӨЛЕК, ӘЛДЕҚАЙДА сирек
# таймер — ЕШҚАШАН per-sample sqlite жазуы ЖОҚ (§ risk evaluation:
# секундына бірнеше рет sqlite commit жасау UI event loop-ты кідіртуі
# МҮМКІН, § "sync must never block Arduino acquisition"). Нақты
# интервал ЕНДІ ``AppPreferences.get_active_experiment_sync_interval_
# seconds()``-тен оқылады (§ Phase 5 "Configuration" — әдепкі 10с,
# құрылыс сәтінде ТЕК БІР рет оқылады, § ``__init__``).

_logger = logging.getLogger("apl.measurement_persist")

# Phase 39B: белсенді оқушысыз Оқушы режимінде эксперимент бетіне кіру —
# ЕШБІР pipeline құрылмайды, тек осы блокталған күй көрсетіледі
# (§ "Student mode must not begin a new measurement session" without a
# real locally selected student).
_BLOCKED_STATE_TITLE = "Оқушы таңдалмаған"
_BLOCKED_STATE_HINT = (
    "Өлшеуді бастау үшін алдымен өзіңізді оқушы ретінде таңдаңыз."
)
_SELECT_STUDENT_BUTTON_TEXT = "Оқушыны таңдау"

# Phase 41: WorkspaceBackdrop секция кілті үшін модуль атауы -> accent
# кілті. ``ui.pages.experiment_list_page._SECTION_ACCENT_BY_NAME``-мен
# бірдей мағынадағы, БІРАҚ бөлек презентациялық қажеттілік үшін қасақана
# қайталанған кесте (жобаның бұрыннан бар дублирлеу конвенциясы,
# § _SENSOR_TYPE_NAMES_KK).
_MODULE_ACCENT_BY_NAME: dict[str, str] = {
    "Жылу құбылыстары": "heat",
    "Электр құбылыстары": "electricity",
    "Электромагниттік құбылыстар": "electromagnetism",
    "Жарық құбылыстары": "light",
}


class ExperimentWorkspacePage(QWidget):
    """Таңдалған зертхана жұмысы бойынша құрылғыны анықтау, өлшеуді
    бастау/тоқтату/тазалау және нәтижені экспорттау ағынын басқаратын бет.

    Coordinator: Workspace/DevicePanel сигналдарын ExperimentController-дің
    public әдістеріне жеткізеді және Controller-дің state/error
    сигналдарын Workspace/DevicePanel статусына жеткізеді. Өзі ешбір
    физикалық есептеу, парсинг немесе валидация жасамайды.
    """

    back_requested = Signal()
    student_selection_requested = Signal()
    measurement_running_changed = Signal(bool)

    def __init__(
        self,
        device_scanner: DeviceScanner | None = None,
        device_manager: DeviceManager | None = None,
        csv_exporter: CSVExporter | None = None,
        excel_exporter: ExcelExporter | None = None,
        pdf_exporter: PDFExporter | None = None,
        experiment_controller_factory: _ControllerFactory | None = None,
        multi_sensor_coordinator_factory: _CoordinatorFactory | None = None,
        session_repository: ISessionRepository | None = None,
        measurement_batch_repository: IMeasurementBatchRepository | None = None,
        feedback_repository: IFeedbackRepository | None = None,
        active_student_repository: IActiveStudentRepository | None = None,
        student_progress_repository: IStudentProgressRepository | None = None,
        question_repository: IQuestionRepository | None = None,
        app_preferences: AppPreferences | None = None,
        module_registry: ModuleRegistry | None = None,
        sync_thread_controller: SyncThreadController | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        # Data Journal: аяқталған сессияларды сақтайтын репозиторий. Әдепкі
        # ":memory:" (SqliteSessionRepository-дың өз әдепкісі) — сынақтар
        # нақты пайдаланушы дерегіне ЕШҚАШАН тимейді, тек app.py ғана
        # нақты файл жолымен беріледі.
        self._session_repository: ISessionRepository = (
            session_repository or SqliteSessionRepository()
        )
        # Phase 4 (Raw Arduino Measurement Cloud Sync): session_
        # repository-мен БІРДЕЙ "әдепкі :memory:" қауіпсіздік конвенциясы
        # (§ ``app.py``/``ui/main_window.py`` ғана нақты ортақ db_path
        # береді).
        self._measurement_batch_repository: IMeasurementBatchRepository = (
            measurement_batch_repository or SqliteMeasurementBatchRepository()
        )
        # Phase 39A: үш деңгейлі кері байланыс/бағалау — raw measurements-тен
        # МҮЛДЕ БӨЛЕК репозиторий (дәл session_repository-мен БІРДЕЙ
        # "әдепкі :memory:" қауіпсіздік конвенциясы).
        self._feedback_repository: IFeedbackRepository = (
            feedback_repository or SqliteFeedbackRepository()
        )
        # Phase 39B: белсенді оқушы контексті + сессия-оқушы байланысы —
        # dialogs/feedback репозиторийлерімен БІРДЕЙ "әдепкі :memory:"
        # қауіпсіздік конвенциясы.
        self._active_student_repository: IActiveStudentRepository = (
            active_student_repository or SqliteActiveStudentRepository()
        )
        self._student_progress_repository: IStudentProgressRepository = (
            student_progress_repository or SqliteStudentProgressRepository()
        )
        # Phase 20 (Question Bank): Мұғалім өңдеген/қосқан сұрақтар осы
        # репозиторийден оқылады — статик каталог (§ ``experiment.
        # assessment``) тек ОСЫ тәжірибе үшін репозиторийде ЖОҚ болғанда
        # ғана fallback ретінде қолданылады (§ ``_resolve_assessment()``).
        self._question_repository: IQuestionRepository = (
            question_repository or SqliteQuestionRepository()
        )
        self._current_assessment: ExperimentAssessmentDefinition | None = None
        # Phase 22 (Settings §6): "Графикті автоматты масштабтау" —
        # ТЕК жаңа MeasurementWorkspace/LiveGraphWidget данасының
        # бастапқы checkbox күйі үшін оқылады, белсенді өлшеуге ЕШҚАШАН
        # кері әсер етпейді.
        self._app_preferences: AppPreferences = app_preferences or AppPreferences()
        # § Phase 5 (Connectivity-Aware Automatic Sync): ЕРІКТІ — берілмесе
        # ЕШБІР жаңа QThread жаратылмайды (§ established "optional
        # dependency with safe default" паттерні, ``MainWindow.sync_
        # thread_controller``-мен БІРДЕЙ ұстаным — ``None`` кезінде
        # белсенді-тәжірибе sync триггері толығымен өшірілген, тек
        # жергілікті persist/batch жалғасады).
        self._sync_thread_controller: SyncThreadController | None = sync_thread_controller
        # Кезeng 29: header-дегі category chip/№badge үшін ғана қолданылады
        # (қай модуль осы тәжірибені ұсынатынын табу) — эксперимент
        # логикасына мүлде қатысы жоқ, presentation-only.
        self._module_registry = module_registry
        self._current_experiment: ExperimentDefinition | None = None
        self._required_sensor_count = 0
        self._connected_sensor_count = 0
        self._device_scanner = device_scanner or DeviceScanner()
        # DeviceManager — persistent connection lifecycle-ды иеленетін
        # application-деңгейлік сервис. Бұл бет MainWindow-да БІР рет
        # жасалып, барлық навигацияда қайта пайдаланылатындықтан
        # (Router.navigate() тек on_enter()-ді шақырады, бетті қайта
        # құрмайды), осы self._device_manager эксперимент ауысқанда
        # ЕШҚАШАН ауыстырылмайды — сенсор қосылымдары сақталады.
        self._device_manager = device_manager or DeviceManager()
        self._controller_factory: _ControllerFactory = (
            experiment_controller_factory
            or (lambda experiment: ExperimentController(definition=experiment))
        )
        self._coordinator_factory: _CoordinatorFactory = (
            multi_sensor_coordinator_factory
            or (
                lambda experiment: MultiSensorExperimentCoordinator(
                    definition=experiment, device_manager=self._device_manager
                )
            )
        )
        self._experiment_controller: _Pipeline | None = None
        self._selected_device: ConnectedDevice | None = None
        self._is_multi_device = False

        # "Ток жұмысы мен қуаты"-дағы "УАҚЫТ" readout-ын authoritative
        # coordinator.elapsed_seconds()-пен мезгіл-мезгіл жаңартатын
        # презентация-ғана таймер. Тек ACK-пен расталған running=True
        # сәтінен (_on_experiment_started) бастап іске қосылады, Stop/
        # Back/switch/teardown-да ӘРҚАШАН тоқтатылады (§13).
        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.setInterval(_ELAPSED_TIMER_INTERVAL_MS)
        self._elapsed_timer.timeout.connect(self._on_elapsed_timer_tick)

        # § Phase 4 "Partial Session Upload": ``_elapsed_timer``-ден
        # (10Hz, тек UI presentation) МҮЛДЕ БӨЛЕК, әлдеқайда сирек таймер
        # — тәжірибе жүріп жатқанда жиналған measurement-дерді бірте-
        # бірте (``append_measurements()``) жергілікті дерекқорға
        # жазады/batch-қа бөледі, ЭКСПЕРИМЕНТ АЯҚТАЛҒАНША КҮТПЕЙДІ (§
        # ``get_active_experiment_sync_interval_seconds()`` докстрингі —
        # risk evaluation негіздемесі осы жерде). § Phase 5: ДӘЛ осы tick
        # ЕНДІ (жаңа batch-тар пайда болғанда) ``sync_thread_controller.
        # run_sync_now()``-ды да шақырады (§ "reuse the existing Phase
        # 4 persist timer" — ЕКІНШІ таймер ЖОҚ, § модуль докстрингі).
        # Интервал ЕНДІ ``AppPreferences.get_active_experiment_sync_
        # interval_seconds()``-тен конфигурацияланады (§15 "Configuration").
        self._incremental_persist_timer = QTimer(self)
        self._incremental_persist_timer.setInterval(
            self._app_preferences.get_active_experiment_sync_interval_seconds() * 1000
        )
        self._incremental_persist_timer.timeout.connect(self._on_incremental_persist_timer_tick)
        self._persisted_measurement_count = 0

        # Формат -> (диалог тақырыбы, әдепкі файл аты, сүзгі, exporter,
        # сәтті/сәтсіз хабарламалар). CSV/Excel/PDF ағыны бірдей болғандықтан
        # (dialog → export() → status), triplication болдырмау үшін кесте.
        self._exporters: dict[str, tuple[str, str, str, object, str, str]] = {
            "csv": (
                "CSV экспорттау",
                "",
                "CSV файлдары (*.csv)",
                csv_exporter or CSVExporter(),
                "CSV сәтті сақталды",
                "CSV экспорты сәтсіз аяқталды",
            ),
            "excel": (
                "Excel экспорттау",
                "experiment_results.xlsx",
                "Excel Workbook (*.xlsx)",
                excel_exporter or ExcelExporter(),
                "Excel файлы сәтті сақталды",
                "Excel экспорттау сәтсіз аяқталды",
            ),
            "pdf": (
                "PDF экспорттау",
                "experiment_results.pdf",
                "PDF құжаты (*.pdf)",
                pdf_exporter or PDFExporter(),
                "PDF файлы сәтті сақталды",
                "PDF экспорттау сәтсіз аяқталды",
            ),
        }

        self._back_button = QPushButton("← Тәжірибелерге оралу", self)
        self._back_button.clicked.connect(self._on_back_clicked)

        # Phase 36: тәжірибенің НАҚТЫ өлшенген деректеріне негізделген
        # зертханалық есеп — тек ``experiment.report is not None``
        # болғанда көрінеді, "📘 Нұсқаулық"-тан СОЛ жақта
        # ("[Есеп] [Нұсқаулық] [Схема]" реті).
        self._report_button = QPushButton("📄 Есеп", self)
        self._report_button.clicked.connect(self._on_report_button_clicked)
        self._report_dialog: ExperimentReportDialog | None = None

        # Phase 35: тәжірибенің толық зертханалық нұсқаулығы — тек
        # ``experiment.guide is not None`` болғанда көрінеді (on_enter()),
        # "📐 Схема"-дан СОЛ жақта ("[Нұсқаулық] [Схема]" реті).
        self._guide_button = QPushButton("📘 Нұсқаулық", self)
        self._guide_button.clicked.connect(self._on_guide_button_clicked)
        self._guide_dialog: ExperimentGuideDialog | None = None

        # Phase 36.1: тәжірибенің НАҚТЫ (пайдаланушы дайындаған) қосылым
        # суреті — тек ``experiment.diagram is not None`` болғанда көрінеді,
        # "📘 Нұсқаулық"-тан ОҢ жақта ("[Есеп] [Нұсқаулық] [Схема]" реті,
        # көрінісі ӨЗГЕРІССІЗ — тек басу мінез-құлқы toggle-панельден
        # диалогқа ауысты).
        self._diagram_button = QPushButton("📐 Схема", self)
        self._diagram_button.clicked.connect(self._on_diagram_button_clicked)
        self._diagram_dialog: ExperimentDiagramDialog | None = None

        # Phase 39A: үш деңгейлі кері байланыс — тек
        # ``experiment.assessment is not None`` болғанда қолжетімді
        # (MeasurementSummaryCard-тегі батырма арқылы ашылады, Guide/
        # Report/Diagram-мен БІРДЕЙ WA_DeleteOnClose+finished паттерні).
        self._feedback_dialog: ExperimentFeedbackDialog | None = None
        # Есеп кемінде бір рет ашылды ма — "Кері байланысты бастау"
        # батырмасының қосымша қосылу шарты (§ "Feedback step becomes
        # available after... the report has been opened"). Әр on_enter()
        # сайын қалпына келеді (жаңа сессия — ескі прогресс жоқ).
        self._report_opened_at_least_once = False

        # Phase 37A: тікелей (Router/MainWindow-сыз) конструкцияланатын
        # тестердің ескі мінез-құлқын сақтау үшін әдепкі UserRole.STUDENT
        # (жеңілдетілген "Құрылғыны қосу" ағыны). Нақты қолданбада
        # ``MainWindow`` рөл таңдалғаннан кейін ``set_role()`` арқылы
        # дереу нақтылайды.
        self._current_role: UserRole = UserRole.STUDENT
        self._connect_dialog: SimplifiedDeviceConnectDialog | None = None

        top_row = QHBoxLayout()
        top_row.addWidget(self._back_button)
        top_row.addStretch(1)
        top_row.addWidget(self._report_button)
        top_row.addWidget(self._guide_button)
        top_row.addWidget(self._diagram_button)

        # Phase 38A: 5-қадамдық прогресс жолағы (Нұсқаулық/Схема/Құрылғы/
        # Өлшеу/Есеп) — визард ЕМЕС, тек ағымдағы прогресті көрсетеді.
        # Рөлге тәуелсіз (Оқушы да, Мұғалім де дәл осы жолақты көреді).
        self._workflow_indicator = ExperimentWorkflowIndicator(self)
        self._workflow_indicator.connect_device_requested.connect(
            self._on_connect_device_requested
        )

        # Кезeng 29: category chip ("ЭЛЕКТР ҚҰБЫЛЫСТАРЫ") + №badge — тек
        # presentation, ешбір экспериментке қатысты логика жоқ. Мазмұны
        # тек on_enter()-де, catalog/registry-ден оқылып толтырылады.
        self._category_chip_label = QLabel(self)
        self._category_chip_label.setObjectName("CategoryChip")
        self._category_chip_label.setVisible(False)

        self._number_badge_label = QLabel(self)
        self._number_badge_label.setObjectName("ExperimentNumberBadge")
        self._number_badge_label.setVisible(False)

        category_row = QHBoxLayout()
        category_row.addWidget(self._category_chip_label)
        category_row.addWidget(self._number_badge_label)
        category_row.addStretch(1)

        self._title_label = QLabel(self)
        title_font = self._title_label.font()
        title_font.setBold(True)
        title_font.setPointSize(title_font.pointSize() + 4)
        self._title_label.setFont(title_font)

        self._status_dot_label = QLabel("●", self)
        self._status_text_label = QLabel(self)
        self._status_text_label.setProperty("role", "secondary")
        # Кезeng 29: statys жолағының қосымша деталь бөлігі (elapsed уақыт/
        # қосылған құрылғы саны) — ЕШБІР жаңа күй машинасы жоқ, тек
        # бұрыннан бар _on_elapsed_timer_tick()/_on_readiness_changed()
        # деректерін көрсетеді.
        self._status_detail_label = QLabel(self)
        self._status_detail_label.setObjectName("StatusDetailLabel")

        title_row = QHBoxLayout()
        title_row.addWidget(self._title_label)
        title_row.addStretch(1)
        title_row.addWidget(self._status_dot_label)
        title_row.addWidget(self._status_text_label)
        title_row.addWidget(self._status_detail_label)

        self._description_label = QLabel(self)
        self._description_label.setWordWrap(True)
        self._description_label.setProperty("role", "secondary")

        # Phase 11: formula ЕНДІ ``role="muted"`` (description-нен
        # (secondary) бір деңгей ашығырақ) — оқылу реті бойынша "4.
        # formula" деңгейін "3. description"-нен визуалды ажырату үшін
        # (§ "Target reading order"). Мәтін/көрінуі/геометрия ӨЗГЕРМЕЙДІ.
        self._formula_label = QLabel(self)
        self._formula_label.setWordWrap(True)
        self._formula_label.setProperty("role", "muted")

        # Phase 39B: "Оқушы: Айдос С. / Сынып: 8А" — тек Оқушы режимінде,
        # белсенді оқушы БАР болғанда ғана көрінеді (§ "current workflow
        # continues unchanged" болғанда контекст еске салынады).
        self._active_student_header_label = QLabel(self)
        self._active_student_header_label.setObjectName("ActiveStudentHeaderLabel")
        self._active_student_header_label.setVisible(False)
        # Phase 4 (Workspace Layout Optimization) root cause fix: бұл
        # label ЕНДІ ЕШҚАШАН layout-қа қосылмайды (§ төмендегі
        # ескертуді қараңыз), БІРАҚ ``setVisible(True)`` әлі де сыртта
        # (``_on_active_student_changed``) шақырылады — layout-сыз,
        # visible виджет Qt-та ӨЗ ЕСКІ/әдепкі (0,0,100,30) geometry-сінде
        # көрінеді, "← Тәжірибелерге оралу" батырмасының ҮСТІНЕ түсіп
        # кетеді (§ НАҚТЫ скриншотта расталған регрессия). Түзету —
        # ЕШҚАШАН layout-қа тәуелсіз, ӨЗ бетінше 0×0 өлшемге бекітілген:
        # ``isHidden()`` (§ бар тест) ӘЛІ ДЕ setVisible()-ге сай дұрыс
        # жауап береді, БІРАҚ 0×0 виджет ешқашан бірде-бір пиксель
        # бермейді/ешнәрсенің үстіне түспейді.
        self._active_student_header_label.setFixedSize(0, 0)

        # Phase 38A: өлшеу тоқтағаннан кейінгі қорытынды карточка — бар
        # build_experiment_report_data() статистикасын көрсетеді, жаңа
        # есептеу жасамайды.
        self._summary_card = MeasurementSummaryCard(self)
        self._summary_card.open_report_requested.connect(self._on_report_button_clicked)
        self._summary_card.remeasure_requested.connect(self._on_remeasure_requested)
        self._summary_card.feedback_requested.connect(self._on_start_feedback_requested)

        # Phase 32.2: DevicePanel ЕНДІ эксперимент бетінде КӨРСЕТІЛМЕЙДІ —
        # ол dedicated "Құрылғылар" бетінде (DevicesPage) толық көшірмеленген
        # функционалдылық (сол ортақ DeviceManager-ден оқиды/жазады), ал
        # мұнда тек ~260px горизонталь орынды тегін алатын. Объект
        # construct etiледі (сигнал wiring/ескі single-device
        # ExperimentController жолын бұзбау үшін — DevicePanel класы
        # ӨЗІ жойылмады/бұзылмады, тек осы беттің КӨРІНЕТІН layout-ынан
        # алынды), бірақ ЕШҚАШАН layout-қа қосылмайды және әдепкі
        # бойынша жасырын — visual footprint нөл. Компакт readiness/
        # status индикаторы (title_row-дағы _status_text_label/
        # _status_detail_label, мыс. "Құрылғылар күтілуде  0 / 2
        # құрылғы") header-де сол қалпы қалады — жеке sidebar қайта
        # құрылмады.
        self._device_panel = DevicePanel(self)
        self._device_panel.setVisible(False)
        self._measurement_workspace = MeasurementWorkspace(
            self, default_auto_scale=self._app_preferences.get_auto_scale_default()
        )

        # Phase 39B: белсенді оқушысыз Оқушы режимінде эксперимент бетіне
        # кіру — ЕШБІР pipeline құрылмайды, "Оқушы таңдалмаған" блокталған
        # күйі ``_measurement_workspace``-тің ОРНЫНА көрсетіледі (§ "Do not
        # allow Start measurement"). ``_measurement_workspace`` атрибуты
        # ӨЗІ ЕШҚАШАН ауыстырылмайды — тек оны қоршаған контейнер өзгерді
        # (бұрыннан бар тесттердің ``page._measurement_workspace``
        # сілтемесі бұзылмайды).
        self._blocked_state_widget = self._build_blocked_state_widget()
        self._body_stack = QStackedWidget(self)
        self._body_stack.addWidget(self._measurement_workspace)
        self._body_stack.addWidget(self._blocked_state_widget)

        body_layout = QHBoxLayout()
        body_layout.addWidget(self._body_stack, 1)

        # Phase 32: shared workspace architecture fix. Header (top_row/
        # category_row/title_row/description/formula) — тек
        # sizeHint биіктігін алады, ЕШБІР stretch алмайды. body_layout
        # (MeasurementWorkspace) — ЖАЛҒЫЗ stretch=1 алушы, барлық қалған
        # бет биіктігін иеленеді. Бұрын бұл implicit түрде (тек
        # MeasurementWorkspace-тің expanding size policy-і арқылы)
        # жұмыс істейтін — енді ЕКІ жерде де (осында, әрі MeasurementWorkspace
        # өзінде) НАҚТЫ көрсетілген, кездейсоқ regression-ға қарсы.
        # Тестілеу үшін ашық: layout архитектурасының stretch/policy
        # келісімшарттарын pixel-perfect емес, seed-структура арқылы
        # тексеруге мүмкіндік береді (Phase 32, §17).
        self._body_layout = body_layout

        # Phase 4 (Workspace Layout Optimization): header тобы (top_row..
        # summary_card) тек sizeHint биіктігін алады (stretch=0), ал
        # ЖОҒАРЫДА, барлық осы тар аралықтардың қосындысы графикке
        # берілетін орынды азайтады — сондықтан margin/spacing ӘДЕЙІ
        # ықшамдалды (§ "Remove every unnecessary empty vertical gap").
        # ``_active_student_header_label`` ЕНДІ мұнда ЕШҚАШАН
        # қосылмайды — "Оқушы:/Сынып:" ақпараты бұл жерде артық (§
        # "They already exist elsewhere. They waste valuable graph
        # space."). Виджеттің ӨЗІ/``setVisible()``/``setText()``
        # логикасы ӘДЕЙІ тиілмеді (қолданыстағы тест контрактын бұзбау
        # үшін) — тек енді ЕШБІР layout-қа қосылмағандықтан, нақты
        # экранда ЕШҚАШАН орын алмайды/көрінбейді.
        layout = QVBoxLayout(self)
        layout.setSpacing(2)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.addLayout(top_row)
        layout.addWidget(self._workflow_indicator)
        layout.addLayout(category_row)
        layout.addLayout(title_row)
        layout.addWidget(self._description_label)
        layout.addWidget(self._formula_label)
        layout.addWidget(self._summary_card)
        layout.addLayout(body_layout, 1)

        self._set_status(_STATUS_WAITING)

        self._device_panel.scan_requested.connect(self._on_scan_requested)
        self._device_panel.identify_requested.connect(self._on_identify_requested)
        self._device_panel.device_selected.connect(self._on_device_selected)

        self._measurement_workspace.start_requested.connect(self._on_start_requested)
        self._measurement_workspace.stop_requested.connect(self._on_stop_requested)
        self._measurement_workspace.clear_requested.connect(self._on_clear_requested)
        self._measurement_workspace.export_requested.connect(self._on_export_requested)
        self._measurement_workspace.connect_device_requested.connect(
            self._on_connect_device_requested
        )

    def _build_blocked_state_widget(self) -> QWidget:
        """"Оқушы таңдалмаған" блокталған күйі — ``_measurement_workspace``-
        тің толық алмастырғышы (§ "Do not allow Start measurement" болғанда
        pipeline мүлде құрылмайды, сондықтан бұл жерде тек статикалық
        хабарлама/әрекет ғана бар, ешбір device/measurement виджеті жоқ).
        """
        widget = QWidget(self)

        title_label = QLabel(_BLOCKED_STATE_TITLE, widget)
        title_font = title_label.font()
        title_font.setBold(True)
        title_font.setPointSize(title_font.pointSize() + 3)
        title_label.setFont(title_font)

        hint_label = QLabel(_BLOCKED_STATE_HINT, widget)
        hint_label.setWordWrap(True)
        hint_label.setProperty("role", "secondary")
        # Layout-дың addWidget(..., AlignHCenter) флагы word-wrap QLabel-мен
        # бірге қолданылса, Qt heightForWidth-ті дұрыс есептемей, жолдар
        # бір-бірімен қабаттасып кетеді (белгілі Qt ерекшелігі) — сол
        # себепті центрлеу мұнда layout флагы АРҚЫЛЫ ЕМЕС, лейблдің ӨЗ
        # мәтін-туралау қасиеті арқылы орнатылады.
        hint_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        select_button = QPushButton(_SELECT_STUDENT_BUTTON_TEXT, widget)
        select_button.clicked.connect(self.student_selection_requested.emit)

        layout = QVBoxLayout(widget)
        layout.addStretch(1)
        layout.addWidget(title_label, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(hint_label)
        layout.addWidget(select_button, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch(1)
        return widget

    def _on_diagram_button_clicked(self) -> None:
        """Phase 36.1: Guide/Report диалогтарымен БІРДЕЙ оқшаулау
        принципі — диалог тек ``experiment.title``/``experiment.diagram``
        оқиды, сондықтан ашу/жабу өлшеу/график/A-B/region/zoom-pan
        күйіне архитектуралық түрде тие алмайды.
        """
        if self._current_experiment is None or self._current_experiment.diagram is None:
            return
        dialog = ExperimentDiagramDialog(
            self._current_experiment.title, self._current_experiment.diagram, parent=self
        )
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        # Guide/Report диалогтарында тапталған dangling C++ reference
        # қатесінің алдын алу үшін — дәл сол "finished" паттерні.
        dialog.finished.connect(self._on_diagram_dialog_finished)
        self._diagram_dialog = dialog
        dialog.show()
        self._workflow_indicator.set_diagram_state(WorkflowStepState.COMPLETED)

    def _on_diagram_dialog_finished(self) -> None:
        self._diagram_dialog = None

    def _on_guide_button_clicked(self) -> None:
        """Phase 35 §15: диалог ТЕК ``experiment.title``/``experiment.guide``
        оқиды — ``LiveGraphWidget``/``MeasurementWorkspace``/coordinator-ге
        ЕШБІР сілтемесі жоқ, сондықтан ашу/жабу өлшеу/график/A-B/region/
        zoom-pan күйіне architectural түрде тие алмайды. Әр басу сайын
        ЖАҢА диалог құрылады (``WA_DeleteOnClose`` — Qt жабылғанда нақты
        жояды), сондықтан қайталап ашу/жабу ешбір виджет/сигнал
        жинақтамайды.
        """
        if self._current_experiment is None or self._current_experiment.guide is None:
            return
        dialog = ExperimentGuideDialog(
            self._current_experiment.title, self._current_experiment.guide, parent=self
        )
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        # Диалог ӨЗ "Жабу" батырмасымен/Esc/X арқылы жабылса да,
        # ``self._guide_dialog`` дереу ``None``-ге тазалануы тиіс —
        # әйтпесе кейінірек ``on_enter()`` осы (WA_DeleteOnClose арқылы
        # НАҚТЫ жойылған) C++ данасына ``.close()`` шақырып,
        # "Internal C++ object already deleted" қатесін тудырады.
        dialog.finished.connect(self._on_guide_dialog_finished)
        self._guide_dialog = dialog
        dialog.show()
        self._workflow_indicator.set_guide_state(WorkflowStepState.COMPLETED)

    def _on_guide_dialog_finished(self) -> None:
        self._guide_dialog = None

    def _on_report_button_clicked(self) -> None:
        """Phase 36: НАҚТЫ (осы шақыру сәтіндегі) сессия/график күйінен
        дайын ``ExperimentReportData``/pixmap есептеп, ЖАҢА диалог
        көрсетеді. "Report updates when reopened" осы жерден келеді —
        әр басу ЖАҢА снапшот құрады, диалогтың ӨЗІ ешбір auto-refresh
        жасамайды. Диалогтың өзі session/graph-ты ЕШҚАШАН тікелей
        оқымайды (§15-мен БІРДЕЙ оқшаулау — тек дайын дерек қабылдайды),
        сондықтан ашу/жабу өлшеу/график күйіне architectural түрде
        тие алмайды.
        """
        if (
            self._current_experiment is None
            or self._current_experiment.report is None
            or self._experiment_controller is None
        ):
            return
        report_data = build_experiment_report_data(
            self._current_experiment, self._experiment_controller.session
        )
        graph_pixmap = self._measurement_workspace._live_graph.grab_plot_pixmap()

        # Phase 39A: тек НАҚТЫ сақталған кері байланыс болса ғана
        # беріледі — Оқушы режимінде ``teacher_assessment`` домен
        # деңгейінде алынып тасталады (``ExperimentReportDialog``-тың
        # өзі рөлді мүлде білмейді, тек берілген деректі рендерлейді).
        feedback_result: ExperimentFeedbackResult | None = None
        if self._current_experiment.assessment is not None:
            feedback_result = self._feedback_repository.get_result(
                self._experiment_controller.session.id
            )
            if feedback_result is not None and self._current_role is UserRole.STUDENT:
                feedback_result = build_student_safe_result(feedback_result)

        dialog = ExperimentReportDialog(
            self._current_experiment.title,
            self._current_experiment.guide,
            self._current_experiment.report,
            report_data,
            graph_pixmap,
            parent=self,
            automatic_conclusion=build_automatic_conclusion(report_data),
            assessment=self._current_experiment.assessment,
            feedback_result=feedback_result,
        )
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        # Дәл сол себеппен (_on_guide_dialog_finished-ті қараңыз) — диалог
        # ӨЗ батырмасымен жабылса да, сілтеме дереу тазалануы тиіс.
        dialog.finished.connect(self._on_report_dialog_finished)
        self._report_dialog = dialog
        dialog.show()
        self._workflow_indicator.set_report_state(WorkflowStepState.COMPLETED)
        self._report_opened_at_least_once = True
        self._update_feedback_button_enabled()

    def _on_report_dialog_finished(self) -> None:
        self._report_dialog = None

    def _resolve_assessment(
        self, experiment: ExperimentDefinition
    ) -> ExperimentAssessmentDefinition | None:
        """Phase 20 (Question Bank): ``experiment.id``-ге сай белсенді
        сұрақтарды репозиторийден оқиды. Репозиторийде осы тәжірибе үшін
        ЕШБІР жол жоқ болса (әлі Question Bank-та өңделмеген/статик
        каталогтан seed етілмеген), ``experiment.assessment`` (статик
        анықтама, ``None`` болуы мүмкін) ӨЗГЕРІССІЗ fallback ретінде
        қолданылады — § "reuse the same questions... do not force new
        behavior onto untouched experiments".
        """
        records = self._question_repository.list_for_experiment(experiment.id)
        return build_assessment_definition(records, experiment.assessment)

    def _on_start_feedback_requested(self) -> None:
        """``MeasurementSummaryCard``-тегі "Кері байланысты бастау"
        батырмасы — Guide/Report/Diagram-мен БІРДЕЙ оқшаулау принципі:
        диалог тек сұрақтар (§ ``_current_assessment`` — Question Bank
        репозиторийінен НЕМЕСЕ статик каталогтан, § ``_resolve_
        assessment()``) мен бұрын сақталған ``ExperimentFeedbackResult``
        (бар болса) қабылдайды, репозиторийге ӨЗІ ЕШБІР жазба жасамайды —
        барлық персистентация осы жерде, сигналдар арқылы.
        """
        if (
            self._current_experiment is None
            or self._current_assessment is None
            or self._experiment_controller is None
        ):
            return
        session_id = self._experiment_controller.session.id
        existing_result = self._feedback_repository.get_result(session_id)
        dialog = ExperimentFeedbackDialog(
            self._current_experiment.title,
            self._current_experiment.id,
            session_id,
            self._current_assessment,
            existing_result,
            self._current_role,
            parent=self,
        )
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.finished.connect(self._on_feedback_dialog_finished)
        dialog.draft_saved.connect(self._on_feedback_draft_saved)
        dialog.submitted.connect(self._on_feedback_submitted)
        dialog.teacher_assessment_saved.connect(self._on_feedback_teacher_assessment_saved)
        self._feedback_dialog = dialog
        dialog.show()
        self._workflow_indicator.set_feedback_state(WorkflowStepState.CURRENT)

    def _on_feedback_dialog_finished(self) -> None:
        self._feedback_dialog = None

    def _on_feedback_draft_saved(self, result: ExperimentFeedbackResult) -> None:
        try:
            self._feedback_repository.save_draft(result)
        except Exception as exc:  # қорғаныс: сақтау қатесі UI-ды құлатпайды
            self._measurement_workspace.show_status(f"Кері байланысты сақтау қатесі: {exc}")

    def _on_feedback_submitted(self, result: ExperimentFeedbackResult) -> None:
        try:
            self._feedback_repository.save_submission(result)
            self._workflow_indicator.set_feedback_state(WorkflowStepState.COMPLETED)
        except Exception as exc:
            self._measurement_workspace.show_status(f"Кері байланысты жіберу қатесі: {exc}")

    def _on_feedback_teacher_assessment_saved(self, teacher_assessment: TeacherAssessment) -> None:
        if self._experiment_controller is None or self._current_experiment is None:
            return
        try:
            self._feedback_repository.save_teacher_assessment(
                self._experiment_controller.session.id,
                self._current_experiment.id,
                teacher_assessment,
                self._current_role,
            )
        except PermissionError as exc:
            self._measurement_workspace.show_status(str(exc))
        except Exception as exc:
            self._measurement_workspace.show_status(f"Мұғалім бағасын сақтау қатесі: {exc}")

    def set_role(self, role: UserRole) -> None:
        """Ағымдағы рөлді орнатады — Оқушы режимінде ғана "🔌 Құрылғыны
        қосу" әрекеті көрінеді (Мұғалім режимінде толық ``DevicesPage``
        қолданылады, бұл беттегі мінез-құлық ӨЗГЕРМЕЙДІ).
        """
        self._current_role = role
        self._measurement_workspace.set_connect_action_visible(role is UserRole.STUDENT)

    def close_open_dialogs(self) -> None:
        """Ашық тұрған Guide/Report/Diagram диалогтарының БАРЛЫҒЫН қауіпсіз
        жабады (әрқайсысы ``WA_DeleteOnClose`` арқылы нақты жойылады,
        сілтемесі ``None``-ге түседі). Phase 37A: рөл ауыстыру кезінде
        ``MainWindow`` осыны шақырады — бұрын ``on_enter()``-тің өз
        ішінде қайталанған 3 бірдей блок осы БІР әдіске жинақталды
        (мінез-құлық өзгерген жоқ, таза рефакторинг).
        """
        if self._diagram_dialog is not None:
            self._diagram_dialog.close()
            self._diagram_dialog = None
        if self._guide_dialog is not None:
            self._guide_dialog.close()
            self._guide_dialog = None
        if self._report_dialog is not None:
            self._report_dialog.close()
            self._report_dialog = None
        if self._feedback_dialog is not None:
            self._feedback_dialog.close()
            self._feedback_dialog = None

    def _set_status(self, status: str) -> None:
        """Header-дегі статус индикаторын (● + мәтін) жаңартады. Тек
        presentation — ешбір experiment/controller күйін өзгертпейді.

        Phase 12 (§5 "Status Transitions"): логикалық статус (мәтін) ӘРҚАШАН
        осында бірден орнатылады — тек нүктенің ТҮСІ ``fade_label_color()``
        арқылы жұмсақ ауысады (150ms), ешбір delay функционалды жаққа
        әсер етпейді.
        """
        text, color = _STATUS_CONFIG.get(status, _STATUS_CONFIG[_STATUS_WAITING])
        fade_label_color(self._status_dot_label, color)
        self._status_text_label.setText(text)

    def _find_owning_module(self, experiment: ExperimentDefinition) -> IPhysicsModule | None:
        """Берілген тәжірибені ұсынатын ``IPhysicsModule``-ды табады
        (category chip үшін). ``module_registry`` берілмесе немесе
        сәйкес модуль табылмаса, ``None`` қайтарады — chip жәй жасырылады,
        ешбір exception шықпайды.
        """
        if self._module_registry is None:
            return None
        for module in self._module_registry.get_all():
            if any(exp.id == experiment.id for exp in module.get_experiments()):
                return module
        return None

    def current_module_accent_key(self) -> str | None:
        """Ағымдағы (``on_enter``-де орнатылған) тәжірибенің меншікті
        модулінің accent кілтін қайтарады ("heat"/"electricity"/
        "electromagnetism"/"light") — Phase 41 WorkspaceBackdrop секциясын
        route-қа тәуелсіз, нақты тәжірибеге тәуелді есептеу үшін
        ``MainWindow``-ге ашылған жалғыз public accessor. Тәжірибе әлі
        орнатылмаса немесе меншікті модуль табылмаса — ``None`` (шақырушы
        жалпы зертхана fallback-ін қолданады).
        """
        if self._current_experiment is None:
            return None
        module = self._find_owning_module(self._current_experiment)
        if module is None:
            return None
        return _MODULE_ACCENT_BY_NAME.get(module.get_name())

    def _update_category_header(self, experiment: ExperimentDefinition) -> None:
        module = self._find_owning_module(experiment)
        if module is not None:
            icon = module.get_icon() or ""
            self._category_chip_label.setText(f"{icon} {module.get_name()}".strip().upper())
            self._category_chip_label.setVisible(True)
        else:
            self._category_chip_label.setVisible(False)

        if experiment.display_number is not None:
            self._number_badge_label.setText(f"№{experiment.display_number}")
            self._number_badge_label.setVisible(True)
        else:
            self._number_badge_label.setVisible(False)

    def _update_status_detail(self) -> None:
        """Статус жолағының қосымша деталь бөлігін (elapsed уақыт +
        қосылған құрылғы саны) жаңартады. Тек multi-device тәжірибелерде
        мағыналы (single-device-де "1 құрылғы" деген ақпарат артық).
        """
        if not self._is_multi_device:
            self._status_detail_label.setText("")
            return

        parts: list[str] = []
        if self._required_sensor_count > 0:
            parts.append(f"{self._connected_sensor_count} / {self._required_sensor_count} құрылғы")
        if (
            self._experiment_controller is not None
            and hasattr(self._experiment_controller, "elapsed_seconds")
            and hasattr(self._experiment_controller, "is_starting")
            and (self._experiment_controller.is_running() or self._experiment_controller.is_starting())
        ):
            parts.append(f"{self._experiment_controller.elapsed_seconds():.2f} с")
        self._status_detail_label.setText("   ".join(parts))

    def on_enter(self, experiment: ExperimentDefinition) -> None:
        """Таңдалған зертхана жұмысына арналған таза күймен бастайды.

        ``experiment.requires_multiple_sensors()`` (2+ ``required_sensor_types``)
        болса ``MultiSensorExperimentCoordinator`` (бірнеше COM-порт бір
        мезгілде), әйтпесе бұрынғы бір-құрылғылы ``ExperimentController``
        қолданылады.

        Тақырып/сипаттама/формула мәтіні тек presentation мақсатында
        көрсетіледі — ``CalculationEngine`` формуланы бұл мәтіннен
        есептемейді (формула тек ``definition.formulas`` кілттері арқылы,
        алдын ала анықталған калькуляторлармен есептеледі).
        """
        self._teardown_pipeline()
        self._current_experiment = experiment
        # Phase 20: Question Bank-та өңделген/қосылған сұрақтар осы жерде
        # БІР РЕТ шешіледі (§ "Avoid duplicate repository queries") —
        # ``_on_start_feedback_requested()`` осы кэштелген мәнді қайта
        # пайдаланады, әр батырма басылған сайын репозиторийге қайта
        # сұрау салмайды.
        self._current_assessment = self._resolve_assessment(experiment)
        self._update_category_header(experiment)
        self._title_label.setText(experiment.title)
        self._description_label.setText(experiment.description)
        self._description_label.setVisible(bool(experiment.description))
        formula_text = "; ".join(experiment.formulas.values())
        self._formula_label.setText(f"Формула: {formula_text}" if formula_text else "")
        self._formula_label.setVisible(bool(formula_text))
        # Жаңа тәжірибеге ауысқанда (немесе рөл ауысқанда, §
        # close_open_dialogs()) ескі диаграмма/guide/есеп диалогтары
        # ЕШҚАШАН экранда қалмауы тиіс — тіпті ашық тұрса да, жабылады
        # (WA_DeleteOnClose оны нақты жояды).
        self.close_open_dialogs()

        # Phase 39B: Оқушы режимінде белсенді оқушы контекстін осы жерде-ақ
        # оқимыз — session identity қалыптасқанға дейін шешім қабылдау
        # үшін (§ "Ownership begins when the experiment session starts").
        # Мұғалім режимінде гейт мүлде жоқ (Мұғалімнің тексеру сессиялары
        # ешбір оқушыға тағайындалмайды — легаси-сессиямен БІРДЕЙ ереже).
        active_context: ActiveStudentContext | None = (
            self._active_student_repository.get()
            if self._current_role is UserRole.STUDENT
            else None
        )
        if self._current_role is UserRole.STUDENT and active_context is None:
            self._body_stack.setCurrentWidget(self._blocked_state_widget)
            self._workflow_indicator.setVisible(False)
            self._summary_card.setVisible(False)
            self._active_student_header_label.setVisible(False)
            self._diagram_button.setVisible(False)
            self._guide_button.setVisible(False)
            self._report_button.setVisible(False)
            return

        self._body_stack.setCurrentWidget(self._measurement_workspace)
        self._workflow_indicator.setVisible(True)
        self._summary_card.setVisible(True)
        # Мәтіннің ӨЗІ (аты/сынып) ``set_active_student_header_text()``
        # арқылы сырттан итеріледі (``MainWindow``, Sidebar-мен БІРДЕЙ
        # "dumb display" принципі — бұл бет атын/сыныбын шешу үшін жеке
        # IStudentRepository/IClassroomRepository қажет етпейді, тек
        # session-иеленуге қажетті ID-лерді ``active_context``-тен алады).
        self._active_student_header_label.setVisible(active_context is not None)

        self._diagram_button.setVisible(experiment.diagram is not None)
        self._guide_button.setVisible(experiment.guide is not None)
        self._report_button.setVisible(experiment.report is not None)
        self._measurement_workspace.set_connect_action_visible(
            self._current_role is UserRole.STUDENT
        )

        # Phase 38A: жаңа тәжірибеге ауысқанда прогресс жолағы мен
        # қорытынды карточка бастапқы күйге оралады (визард емес — тек
        # көрсеткіш, сондықтан ешбір навигацияны бөгемейді).
        self._report_opened_at_least_once = False
        self._workflow_indicator.reset(
            guide_available=experiment.guide is not None,
            diagram_available=experiment.diagram is not None,
            report_available=experiment.report is not None,
            feedback_available=self._current_assessment is not None,
        )
        self._summary_card.hide_summary()
        self._summary_card.set_feedback_available(self._current_assessment is not None)
        self._summary_card.set_feedback_button_enabled(False)

        self._measurement_workspace.configure_for_experiment(experiment)

        self._is_multi_device = experiment.requires_multiple_sensors()
        self._device_panel.set_required_sensor_types(
            experiment.required_sensor_types if self._is_multi_device else ()
        )

        # Phase 32.1: "0/N" деталін coordinator-дың бірінші readiness_
        # changed сигналын КҮТПЕЙ-АҚ бірден көрсету — 0 құрылғымен
        # ашылған тәжірибеде ЕШБІР сигнал ешқашан келмеуі мүмкін
        # (DeviceManager-де тіркелген сенсор жоқ болса,
        # refresh_from_device_manager() ештеңе emit етпейді), сондықтан
        # бұл мәнді осы жерде presentation-деңгейінде проактивті
        # орнату қажет (coordinator/readiness логикасына тимейді).
        self._required_sensor_count = (
            len(experiment.required_sensor_types) if self._is_multi_device else 0
        )
        self._connected_sensor_count = 0
        self._update_status_detail()

        if self._is_multi_device:
            coordinator = self._coordinator_factory(experiment)
            coordinator.device_identified.connect(self._on_device_identified)
            coordinator.device_identification_failed.connect(self._device_panel.show_message)
            coordinator.handshake_timeout.connect(self._on_handshake_timeout)
            coordinator.measurement_ready.connect(self._measurement_workspace.set_measurement)
            coordinator.measurement_ready.connect(self._on_measurement_ready_for_device_panel)
            coordinator.warning_occurred.connect(self._measurement_workspace.show_status)
            coordinator.port_error.connect(
                lambda port, message: self._measurement_workspace.show_status(
                    f"[{port}] {message}"
                )
            )
            coordinator.port_disconnected.connect(self._on_coordinator_port_disconnected)
            coordinator.readiness_changed.connect(self._on_readiness_changed)
            coordinator.experiment_started.connect(self._on_experiment_started)
            coordinator.start_failed.connect(self._on_start_failed)
            self._experiment_controller = coordinator
            # Persistent connections: осы сәтте DeviceManager-де ҚАЗІРДІҢ
            # ӨЗІНДЕ connected тұрған (алдыңғы тәжірибеден сақталған)
            # сенсорлар бірден "assigned" болады — қайта Анықтау керек
            # емес. Барлық connect()-тен КЕЙІН шақырылуы міндетті,
            # әйтпесе device_identified эмиссиясы жоғалып кетер еді.
            coordinator.refresh_from_device_manager()
        else:
            controller = self._controller_factory(experiment)
            controller.device_identified.connect(self._on_device_identified)
            controller.device_identification_failed.connect(self._device_panel.show_message)
            controller.handshake_timeout.connect(self._on_handshake_timeout)
            controller.measurement_ready.connect(self._measurement_workspace.set_measurement)
            controller.measurement_ready.connect(self._on_measurement_ready_for_device_panel)
            controller.error_occurred.connect(self._measurement_workspace.show_status)
            controller.disconnected.connect(self._on_device_disconnected)
            self._experiment_controller = controller

        # Phase 39B: session identity ДӘЛ ОСЫ СӘТТЕ қалыптасты
        # (``self._experiment_controller.session.id``) — байланыс дәл
        # осы жерде, алғашқы өлшеуге дейін жазылады (§ "Do not attach
        # student_id only when the report is opened"). Мұғалім
        # режимінде/``active_context is None`` кезінде ешбір жазба
        # жасалмайды (осы функция басында, ``active_context is None``
        # болса, Оқушы режимінде ертерек ``return`` етілген еді).
        if active_context is not None:
            self._student_progress_repository.link_session(
                self._experiment_controller.session.id,
                active_context.student_id,
                active_context.classroom_id,
                experiment.id,
            )

    def set_active_student_header_text(self, text: str | None) -> None:
        """Header-дегі "Оқушы: Айдос С. / Сынып: 8А" мәтінін орнатады —
        ``MainWindow`` белсенді оқушы контексі өзгерген сайын шақырады
        (Sidebar-мен БІРДЕЙ "dumb display" принципі).
        """
        self._active_student_header_label.setText(text or "")

    def refresh_active_student(self) -> None:
        """Белсенді оқушы Sidebar-дың "Оқушыны ауыстыру" әрекеті арқылы
        өзгергенде шақырылады. Ағымдағы тәжірибе экранда болса, ``on_enter()``-
        ді ҚАЙТА шақырады — бұл ЕСКІ сессияны (бар болса) оның НАҚТЫ
        тағайындалған оқушысымен дұрыс қорытындылап сақтайды
        (``_teardown_pipeline()`` арқылы) және ЖАҢА оқушыға арналған
        мүлде жаңа сессия құрады (жаңа ``session.id``, жаңа байланыс) —
        "never silently move an active session to another student"
        ережесі осылай орындалады: ескі сессия ешқашан қайта
        тағайындалмайды, тек жаңасы басқа оқушыға тиесілі болады.
        Белсенді өлшеу жүріп жатқанда бұл әдіс ЕШҚАШАН шақырылмауы тиіс
        (Sidebar-дың ауыстыру батырмасы ``is_measurement_running()``
        арқылы алдын ала өшіріледі).
        """
        if self._current_experiment is not None:
            self.on_enter(self._current_experiment)

    def is_measurement_running(self) -> bool:
        """Белсенді оқушыны ауыстыру әрекетін өшіру/қосу үшін —
        өлшеу жүріп жатқанда ауыстыру рұқсат етілмейді (§ "stop or
        reject switching during an active measurement").
        """
        return self._experiment_controller is not None and self._experiment_controller.is_running()

    def _emit_running_changed(self) -> None:
        self.measurement_running_changed.emit(self.is_measurement_running())

    def _on_back_clicked(self) -> None:
        self._teardown_pipeline()
        self.back_requested.emit()

    def _teardown_pipeline(self) -> None:
        """Ағымдағы pipeline-ды (``ExperimentController`` немесе
        ``MultiSensorExperimentCoordinator``) толық тоқтатып, DevicePanel/
        MeasurementWorkspace-ты бастапқы күйіне қайтарады.

        Бұл әдіс "Артқа" батырмасынан ДА, жаңа тәжірибеге ауысу
        (``on_enter()``) алдынан ДА шақырылатын жалғыз choke point —
        сондықтан Data Journal-ға сақтау (§7: "Back while running"/
        "Experiment switch") дәл осы жерде, pipeline ``shutdown()``
        етілместен бұрын орындалады (``.session`` сол сәтте әлі толық
        оқылады).
        """
        self._elapsed_timer.stop()
        self._incremental_persist_timer.stop()
        if self._experiment_controller is not None:
            if self._experiment_controller.is_running():
                self._experiment_controller.stop_experiment()
            self._finalize_and_persist_session()
            self._experiment_controller.shutdown()
            self._experiment_controller = None

        self._selected_device = None
        self._is_multi_device = False
        self._required_sensor_count = 0
        self._connected_sensor_count = 0
        self._device_panel.clear_devices()
        self._device_panel.set_required_sensor_types(())
        self._measurement_workspace.clear_device()
        self._measurement_workspace.set_ready(False)
        self._measurement_workspace.set_experiment_starting(False)
        self._set_status(_STATUS_WAITING)
        self._update_status_detail()
        self._emit_running_changed()

    def _on_scan_requested(self) -> None:
        self._device_panel.set_scanning(True)
        ports = self._device_scanner.scan()
        self._device_panel.set_ports(ports)
        self._device_panel.set_scanning(False)

    def _on_identify_requested(self, port_name: str, baud_rate: int) -> None:
        if self._experiment_controller is not None:
            self._experiment_controller.identify_device(port_name, baud_rate)

    def _on_device_identified(self, device: ConnectedDevice) -> None:
        self._device_panel.add_or_update_device(device)
        self._refresh_connect_dialog_if_open()

    def _on_connect_device_requested(self) -> None:
        """Phase 37A: Оқушы режиміндегі жеңілдетілген "Құрылғыны қосу"
        әрекеті — ЕШБІР жаңа scan/identify логикасы жоқ, тек бұрыннан
        бар (әдепкі бойынша жасырын) ``self._device_panel`` данасын
        диалогқа уақытша reparent етеді (``SimplifiedDeviceConnectDialog``
        docstring-ін қараңыз).
        """
        if self._connect_dialog is not None:
            return
        dialog = SimplifiedDeviceConnectDialog(
            self._device_panel, is_ready=self._is_pipeline_ready, parent=self
        )
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.finished.connect(self._on_connect_dialog_finished)
        self._connect_dialog = dialog
        dialog.show()

    def _on_connect_dialog_finished(self) -> None:
        self._connect_dialog = None

    def _is_pipeline_ready(self) -> bool:
        """Ағымдағы pipeline дайын ба, соны қайтарады —
        ``SimplifiedDeviceConnectDialog``-тың автоматты жабылуы үшін.
        ``MultiSensorExperimentCoordinator.is_ready()`` (production-дегі
        барлық 5 электр тәжірибесі) немесе ескі бір-құрылғылы
        ``ExperimentController`` үшін "құрылғы таңдалды ма" (``is_ready()``
        әдісі жоқ, себебі оның дайындығы single-device таңдаумен тепе-тең).
        """
        if self._experiment_controller is None:
            return False
        is_ready = getattr(self._experiment_controller, "is_ready", None)
        if callable(is_ready):
            return is_ready()
        return self._selected_device is not None

    def _refresh_connect_dialog_if_open(self) -> None:
        if self._connect_dialog is not None:
            self._connect_dialog.check_readiness()

    def _on_measurement_ready_for_device_panel(self, measurement: Measurement) -> None:
        """Кезeng 29: сенсор карточкаларының live-value көрсетуін
        (мыс. "5.333 V") жаңартады — ``measurement.values``-ты
        ``DevicePanel``-ге forward етеді. Ешбір жаңа есептеу/pipeline
        жоқ, тек презентация.
        """
        self._device_panel.update_measurement_value(measurement.values)

    def _on_handshake_timeout(self, port_name: str) -> None:
        self._device_panel.show_message(f"'{port_name}': HELLO handshake уақыты бітті")

    def _on_device_selected(self, device: ConnectedDevice) -> None:
        # Multi-device режимінде карточканы басу ешнәрсе білдірмейді — сенсор
        # рөліне тағайындау HELLO-дан келген sensor_type арқылы автоматты
        # орындалады (readiness_changed/DevicePanel checklist-і соны көрсетеді).
        if self._is_multi_device or self._experiment_controller is None:
            return
        if self._experiment_controller.is_running():
            self._experiment_controller.stop_experiment()
        self._experiment_controller.clear_session()

        self._selected_device = device
        self._measurement_workspace.set_device(device)
        self._set_status(_STATUS_READY)
        self._refresh_connect_dialog_if_open()
        self._workflow_indicator.set_device_state(WorkflowStepState.COMPLETED)

    def _on_device_disconnected(self) -> None:
        if self._selected_device is None:
            return
        if self._experiment_controller is not None and self._experiment_controller.is_running():
            self._experiment_controller.stop_experiment()

        self._selected_device = None
        self._measurement_workspace.clear_device()
        self._measurement_workspace.show_status("Құрылғымен байланыс үзілді")
        self._set_status(_STATUS_WAITING)
        self._workflow_indicator.set_device_state(WorkflowStepState.ATTENTION)

    def _on_coordinator_port_disconnected(self, port_name: str) -> None:
        """``MultiSensorExperimentCoordinator.port_disconnected``-ке
        жазылатын слот. Координатор өзі тәжірибені ішінен тоқтатады
        (``is_running()`` False болады) және ``readiness_changed`` шығарады
        (Start батырмасы ``_on_readiness_changed`` арқылы автоматты
        disabled болады) — бұл жерде тек UI статусын жаңарту жеткілікті.
        """
        self._elapsed_timer.stop()
        self._measurement_workspace.set_experiment_running(False)
        self._measurement_workspace.show_status(
            f"'{port_name}' порты ажыратылды — тәжірибе тоқтатылды"
        )
        self._set_status(_STATUS_WAITING)
        self._update_status_detail()

    def _on_readiness_changed(self, readiness: dict[str, bool]) -> None:
        """``MultiSensorExperimentCoordinator.readiness_changed``-ке
        жазылатын слот: DevicePanel checklist-ін жаңартады және барлық
        қажетті сенсор дайын болғанда ғана MeasurementWorkspace-тың
        Start/Clear батырмаларын ашады.
        """
        self._device_panel.set_sensor_readiness(readiness)
        is_ready = bool(readiness) and all(readiness.values())
        self._measurement_workspace.set_ready(is_ready)
        self._set_status(_STATUS_READY if is_ready else _STATUS_WAITING)
        self._required_sensor_count = len(readiness)
        self._connected_sensor_count = sum(1 for ready in readiness.values() if ready)
        self._update_status_detail()
        self._refresh_connect_dialog_if_open()
        self._workflow_indicator.set_device_state(
            WorkflowStepState.COMPLETED if is_ready else WorkflowStepState.ATTENTION
        )

    def _can_start(self) -> bool:
        if self._experiment_controller is None:
            return False
        if self._is_multi_device:
            return self._experiment_controller.is_ready()
        return self._selected_device is not None

    def _on_start_requested(self) -> None:
        try:
            if not self._can_start():
                self._measurement_workspace.show_status("Алдымен құрылғыны таңдаңыз")
                return
            self._experiment_controller.start_experiment()
            if self._is_multi_device:
                # ACK-gated: coordinator SET_EXP-ты барлық портқа жіберді,
                # бірақ ACK әлі келген жоқ — UI "running" деп ОПТИМИСТИК
                # көрсетпейді, тек ACK-тан кейін ғана (_on_experiment_started
                # немесе timeout-та _on_start_failed) шешіледі. Нақты
                # hardware-де осы кезеңде measurement пакеттері жоқ болатын
                # bug дәл осыдан туындаған еді.
                self._measurement_workspace.set_experiment_starting(True)
                self._measurement_workspace.show_status("Іске қосылуда...")
                self._set_status(_STATUS_STARTING)
            else:
                self._measurement_workspace.set_experiment_running(True)
                self._measurement_workspace.show_status("Өлшеу жүріп жатыр")
                self._set_status(_STATUS_RUNNING)
                # § Phase 4: multi-device жолында ``_incremental_persist_
                # timer`` тек ACK-тан кейін (§ ``_on_experiment_started``)
                # басталады — жалғыз-құрылғы жолында ЕШБІР ACK кезеңі жоқ
                # (§ жоғарыдағы "running" осы жерде дереу шешіледі).
                self._persisted_measurement_count = 0
                self._incremental_persist_timer.start()
            self._workflow_indicator.set_measurement_state(WorkflowStepState.CURRENT)
            self._emit_running_changed()
        except Exception as exc:  # қорғаныс: болжанбаған қате де UI-ды құлатпайды
            self._measurement_workspace.show_status(f"Бастау қатесі: {exc}")

    def _on_experiment_started(self) -> None:
        """``MultiSensorExperimentCoordinator.experiment_started``-ке
        жазылатын слот: БАРЛЫҚ порттан SET_EXP ACK расталғаннан кейін
        ғана шақырылады — нақты "running" күйге осы жерде ғана өтеміз.
        """
        self._measurement_workspace.set_experiment_starting(False)
        self._measurement_workspace.set_experiment_running(True)
        self._measurement_workspace.show_status("Өлшеу жүріп жатыр")
        self._set_status(_STATUS_RUNNING)
        # Elapsed-time таймері ДӘЛ осы жерде басталады (ACK-пен расталған
        # running=True сәті) — Start батырмасы басылған кезде ЕМЕС.
        self._elapsed_timer.start()
        self._persisted_measurement_count = 0
        self._incremental_persist_timer.start()
        self._update_status_detail()
        self._workflow_indicator.set_measurement_state(WorkflowStepState.CURRENT)
        self._emit_running_changed()

    def _on_elapsed_timer_tick(self) -> None:
        """10Hz UI refresh — тек multi-device pipeline-де, тек "time"
        арнасы конфигурацияланған тәжірибелерде көрінетін нәтиже береді
        (``MeasurementWorkspace.update_elapsed_time()`` "time" жоқ болса
        no-op). Authoritative мән ЕШҚАШАН бұл жерде есептелмейді — тек
        coordinator.elapsed_seconds()-ті оқиды.
        """
        if not self._is_multi_device or self._experiment_controller is None:
            return
        self._measurement_workspace.update_elapsed_time(
            self._experiment_controller.elapsed_seconds()
        )
        self._update_status_detail()

    def _on_incremental_persist_timer_tick(self) -> None:
        """§ Phase 4 "Partial Session Upload": тәжірибе жүріп жатқанда
        мерзімді (§ ``AppPreferences.get_active_experiment_sync_interval_
        seconds()``) соңғы флуштан кейінгі ЖАҢА measurement-дерді ғана ("құйрық", ``self.
        _persisted_measurement_count``-тан кейінгі) жергілікті дерекқорға
        жазады және толық ``chunk_size`` жапқан batch(тар)ды outbox-қа
        кезекке қояды (``finalize=False`` — тәжірибе ӘЛІ АЯҚТАЛҒАН ЖОҚ,
        соңғы толық емес "құйрық" batch тек ``_finalize_and_persist_
        session()``-де, Stop-та жиналады, § "do not lose tail samples").
        Сақтау қатесі (мыс. дискіге қатысы жоқ дерекқор құлпы) ЕШҚАШАН
        тіркеуді/UI-ды тоқтатпайды — келесі tick-те қайта көреді.
        """
        if self._experiment_controller is None:
            return
        session = self._experiment_controller.session
        new_measurements = tuple(session.measurements[self._persisted_measurement_count :])
        if not new_measurements:
            return
        try:
            self._session_repository.append_measurements(
                session.id,
                session.experiment_id,
                new_measurements,
                self._current_experiment,
                session.started_at,
            )
            self._persisted_measurement_count = len(session.measurements)
            chunk_size = self._app_preferences.get_measurement_batch_chunk_size()
            self._measurement_batch_repository.create_pending_batches_for_session(
                session.id, chunk_size, finalize=False
            )
        except Exception as exc:  # noqa: BLE001 - § "must never block acquisition"
            _logger.warning("incremental measurement persist failed: %s", exc)
            return
        # § Phase 5 §5 "Active-Experiment Near-Real-Time Sync": жаңа
        # measurement/batch жергілікті сақталған соң, желі сұрауының
        # ӨЗІ ЖЕКЕ QThread-де (§ ``SyncThreadController``/``SyncWorker``)
        # асинхронды түрде орындалады — бұл шақыру ӨЗІ ЕШҚАШАН
        # бұғатталмайды/күтпейді (§ "do not make the measurement
        # acquisition loop wait for sync"), тек кезекке қояды.
        # Коалесцирлеу ``SyncWorker.run_sync_now()``-тың ӨЗІНДЕ (§6) —
        # осы жерде ешбір қосымша "тым жиі" қорғанысы қажет ЕМЕС. БӨЛЕК
        # try/except — §5 докстрингінде АЙТЫЛҒАН "sync must never block
        # acquisition" қорғанысы sync-триггер қатесіне де қолданылады.
        if self._sync_thread_controller is not None:
            try:
                self._sync_thread_controller.run_sync_now()
            except Exception as exc:  # noqa: BLE001 - § "must never block acquisition"
                _logger.warning("active-experiment sync trigger failed: %s", exc)

    def _on_start_failed(self, message: str) -> None:
        """``MultiSensorExperimentCoordinator.start_failed``-ке жазылатын
        слот: ACK timeout ішінде барлық порттан растау келмегенде
        шақырылады. UI "ready" күйіне қайтады — пайдаланушы қайта Start
        баса алады.
        """
        self._elapsed_timer.stop()
        self._incremental_persist_timer.stop()
        self._measurement_workspace.set_experiment_starting(False)
        self._measurement_workspace.set_experiment_running(False)
        self._measurement_workspace.show_status(f"Іске қосу сәтсіз: {message}")
        self._set_status(_STATUS_READY)
        self._update_status_detail()
        self._emit_running_changed()

    def _on_stop_requested(self) -> None:
        try:
            if self._experiment_controller is None:
                return
            self._experiment_controller.stop_experiment()
            self._elapsed_timer.stop()
            self._incremental_persist_timer.stop()
            if self._is_multi_device:
                # Соңғы 100мс tick-тен КЕЙІН де elapsed мән дәл қазір
                # "мұздатылған" (frozen) мәнге сай болуы үшін бір рет
                # соңғы синхрондау — дисплей ешбір жуықтаусыз, дәл
                # authoritative frozen мәнмен тоқтайды.
                self._measurement_workspace.update_elapsed_time(
                    self._experiment_controller.elapsed_seconds()
                )
            self._finalize_and_persist_session()
            self._measurement_workspace.set_experiment_starting(False)
            self._measurement_workspace.set_experiment_running(False)
            self._measurement_workspace.show_status("Өлшеу тоқтатылды")
            self._set_status(_STATUS_STOPPED)
            self._update_status_detail()
            self._workflow_indicator.set_measurement_state(WorkflowStepState.COMPLETED)
            self._show_measurement_summary_if_available()
            self._emit_running_changed()
        except Exception as exc:
            self._measurement_workspace.show_status(f"Тоқтату қатесі: {exc}")

    def _show_measurement_summary_if_available(self) -> None:
        """Phase 38A: тоқтатылған сессияда кемінде бір өлшеу болса ғана
        қорытынды карточканы көрсетеді — бос тоқтату (0 өлшеу) жалған
        нөлдермен карточка көрсетпейді. Статистика ЖАҢА есептелмейді —
        Есеп батырмасы қолданатын ДӘЛ СОЛ
        ``build_experiment_report_data()``-дан алынады.
        """
        if self._current_experiment is None or self._experiment_controller is None:
            return
        session = self._experiment_controller.session
        if session.measurement_count == 0:
            return
        report_data = build_experiment_report_data(self._current_experiment, session)
        if not self._current_experiment.graph_y_channels:
            return
        primary_channel_key = self._current_experiment.graph_y_channels[0]
        for stats in report_data.channel_statistics:
            if stats.channel_key == primary_channel_key:
                self._summary_card.show_summary(stats)
                self._update_feedback_button_enabled()
                return

    def _update_feedback_button_enabled(self) -> None:
        """"Кері байланысты бастау" батырмасының қос шарты: кемінде 1
        НАҚТЫ өлшеу БАР ЖӘНЕ есеп кемінде бір рет ашылған (§ "Do not
        fabricate completion" — жалған "аяқталу" ешқашан көрсетілмейді).
        """
        has_measurement = (
            self._experiment_controller is not None
            and self._experiment_controller.session.measurement_count > 0
        )
        self._summary_card.set_feedback_button_enabled(
            has_measurement and self._report_opened_at_least_once
        )

    def _finalize_and_persist_session(self) -> None:
        """Ағымдағы сессияны Data Journal-ға сақтайды (бос сессия болса,
        ``SqliteSessionRepository.save_session()`` өзі ешнәрсе істемейді —
        §8-дегі жалғыз guard, шашыраңқы тексеру жоқ). Идемпотентті: осы
        әдіс бір сессия үшін бірнеше рет (Stop, содан кейін Back/switch,
        содан кейін app quit) шақырылса да, дубликат жол құрылмайды —
        ``session.id`` тұрақты қалады.
        """
        if self._experiment_controller is None:
            return
        try:
            session = self._experiment_controller.session
            self._session_repository.save_session(session, self._current_experiment)
            # § Phase 4 (Raw Arduino Measurement Cloud Sync): ``save_
            # session()`` тек ``session`` entity-ін outbox-қа қосады —
            # НАҚТЫ measurement-дерді (§ "the durable synchronization
            # unit should be a measurement batch") batch-қа бөлу/outbox-
            # қа қосу БӨЛЕК қадам. ``finalize=True`` — эксперимент
            # аяқталды, ``chunk_size``-тен АЗ қалған "құйрық" өлшемдер де
            # бір соңғы batch-қа жиналады (§ "do not lose tail samples").
            if session.measurements:
                chunk_size = self._app_preferences.get_measurement_batch_chunk_size()
                self._measurement_batch_repository.create_pending_batches_for_session(
                    session.id, chunk_size, finalize=True
                )
                # § Phase 5 acceptance §7 "stopping/finalizing the
                # experiment delivers the tail batch" — соңғы (толық
                # емес) batch-ты да КҮТПЕЙ, дереу кезекке қояды (§
                # коалесцирлеу ``SyncWorker``-дің ӨЗІНДЕ, § модуль
                # докстрингі).
                if self._sync_thread_controller is not None:
                    self._sync_thread_controller.run_sync_now()
        except Exception as exc:  # қорғаныс: сақтау қатесі UI-ды құлатпайды
            self._measurement_workspace.show_status(f"Сессияны сақтау қатесі: {exc}")

    def finalize_active_session(self) -> None:
        """Application жабылу алдында (``app.py``-дегі ``aboutToQuit``)
        шақырылады — қазіргі белсенді сессияны (бар болса әрі бос
        болмаса) сақтайды. Ешбір serial port/``DeviceManager``-ге қатысы
        жоқ (тек ``.session``-ды оқиды).
        """
        self._finalize_and_persist_session()

    def _on_clear_requested(self) -> None:
        try:
            if self._experiment_controller is None or self._experiment_controller.is_running():
                return
            self._experiment_controller.clear_session()
            self._measurement_workspace.clear_measurements()
            self._measurement_workspace.show_status("Өлшеу деректері тазаланды")
        except Exception as exc:
            self._measurement_workspace.show_status(f"Тазалау қатесі: {exc}")

    def _on_remeasure_requested(self) -> None:
        """Phase 38A: қорытынды карточкадағы "Қайта өлшеу" батырмасы —
        бұрыннан бар ``_on_clear_requested()``-ті ЕШБІР өзгеріссіз қайта
        қолданады, содан кейін карточканы жасырып, Өлшеу қадамын "○"
        күйіне қайтарады (Нұсқаулық/Схема/Құрылғы/Есеп прогресі
        сақталады — қайта өлшеу оларды жоймайды).
        """
        self._on_clear_requested()
        self._summary_card.hide_summary()
        self._workflow_indicator.set_measurement_state(WorkflowStepState.NOT_VISITED)

    def _on_export_requested(self, export_format: str) -> None:
        try:
            if self._experiment_controller is None:
                return
            session = self._experiment_controller.session
            if session.measurement_count == 0:
                self._measurement_workspace.show_status("Экспорттайтын дерек жоқ")
                return

            caption, default_name, file_filter, exporter, success_text, failure_text = (
                self._exporters[export_format]
            )

            file_path, _selected_filter = QFileDialog.getSaveFileName(
                self, caption, default_name, file_filter
            )
            if not file_path:
                return

            if exporter.export(session, file_path):
                self._measurement_workspace.show_status(success_text)
            else:
                self._measurement_workspace.show_status(failure_text)
        except Exception as exc:  # қорғаныс: болжанбаған қате де UI-ды құлатпайды
            self._measurement_workspace.show_status(f"Экспорт қатесі: {exc}")
