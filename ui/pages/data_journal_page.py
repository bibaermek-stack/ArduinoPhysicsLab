"""DataJournalPage — "Деректер журналы" беті: сақталған зертхана жұмысы
сессияларының тарихын оқуға арналған (read-only V1).

Бұл бет ешбір serial port/``DeviceManager``-дің owner-і ЕМЕС — толығымен
``ISessionRepository`` арқылы оффлайн жұмыс істейді (нақты Arduino
қосылмаса да, бұрын сақталған сессиялар көрінеді/экспортталады).
Тізім тек summary сұрауын қолданады (``get_sessions()`` — measurement-
дерсіз); бір сессияның ``get_measurements()``-і тек "Ашу" басылғанда,
тек сол сессия үшін жүктеледі.
"""

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from domain.entities.classroom import Classroom
from domain.entities.experiment_definition import ExperimentDefinition
from domain.entities.experiment_session import ExperimentSession
from domain.entities.measurement import Measurement
from domain.entities.sensor_channel import SensorChannel
from domain.entities.student import Student
from domain.interfaces.i_classroom_repository import IClassroomRepository
from domain.interfaces.i_session_repository import ISessionRepository, SessionSummary
from domain.interfaces.i_student_progress_repository import IStudentProgressRepository
from domain.interfaces.i_student_repository import IStudentRepository
from domain.services.csv_exporter import CSVExporter
from infrastructure.storage.sqlite_classroom_repository import SqliteClassroomRepository
from infrastructure.storage.sqlite_session_repository import SqliteSessionRepository
from infrastructure.storage.sqlite_student_progress_repository import SqliteStudentProgressRepository
from infrastructure.storage.sqlite_student_repository import SqliteStudentRepository
from modules.module_registry import ModuleRegistry
from ui.themes.theme_manager import COLOR_TEXT_MUTED
from ui.widgets.live_graph import LiveGraphWidget
from ui.widgets.measurement_table import MeasurementTableWidget

# Phase 17: репозиторийде МҮЛДЕ сессия жоқ (Case A) — "Сүзгіге сәйкес
# деректер табылмады" (Case B, төменде) МҮЛДЕ БАСҚА себеп, сондықтан
# БӨЛЕК мәтін (§ "Do not use the same message for these two causes").
_EMPTY_REPOSITORY_TITLE = "Әзірге сақталған өлшеу деректері жоқ."
_EMPTY_REPOSITORY_HINT = "Зертханалық жұмыс орындалғаннан кейін өлшеу сессиялары осы жерде көрсетіледі."
_EMPTY_FILTERED_TITLE = "Сүзгіге сәйкес деректер табылмады."
_EMPTY_FILTERED_HINT = "Іздеу немесе сүзгі параметрлерін өзгертіп көріңіз."
_ALL_FILTER_TEXT = "Барлығы"
_SEARCH_PLACEHOLDER_TEXT = "Іздеу..."
# Phase 39C: "Оқушы" бағаны — Phase 39B-ге дейінгі (немесе Мұғалім
# режимінде жасалған) сессиялардың session_student_link жолы жоқ,
# бұл ЕШБІР "қате" ЕМЕС — тек ашық белгіленетін тарихи факт.
_UNASSIGNED_TEXT = "Тағайындалмаған ескі сессия"
# Phase 17: "Оқушы" бағаны ЕНДІ "Өлшеулер"-ден БҰРЫН (§ Phase 17 §4
# "Preferred visible columns" реті), соңғы баған "Ашу"-дан "Әрекет"
# тақырыбымен "Қарау"-ға ауыстырылды (§ "Replace the current ambiguous
# tiny icon/action control with a clear compact button").
_TABLE_HEADERS = ("Күні", "Зертханалық жұмыс", "Оқушы", "Өлшеулер", "Басталды", "Аяқталды", "Әрекет")
_ACTION_BUTTON_TEXT = "Қарау"
_NO_VALUE_TEXT = "—"


@dataclass(frozen=True)
class _JournalRow:
    """Бір журнал жолы: ``SessionSummary`` + осы сессияға тағайындалған
    оқушы/сынып (§ ``IStudentProgressRepository.get_student_for_session()``
    арқылы UI-деңгейде шешілген, ``ISessionRepository``-дің ӨЗІ ешбір
    student/classroom өрісін білмейді — § "Prefer adapters/view models
    at the UI layer" талабы). ``student``/``classroom`` — ЕСКІ
    тағайындалмаған сессияларда ЕКЕУІ ДЕ ``None``.
    """

    summary: SessionSummary
    student: Student | None
    classroom: Classroom | None


class _AssignSessionDialog(QDialog):
    """Phase 39C: ескі/тағайындалмаған сессияны нақты оқушыға тағайындау
    формасы — ``ClassManagementPage``-дегі ``_ClassroomFormDialog``/
    ``_StudentFormDialog``-пен БІРДЕЙ пішін (``.exec()``, тек таңдалған
    мәндерді қайтарады, репозиторийге ӨЗІ ЕШБІР жазба жасамайды —
    жазу ЖАЛҒЫЗ ``DataJournalPage``-де, ``get_selection()`` арқылы алынған
    мәндермен).
    """

    def __init__(
        self,
        classroom_repository: IClassroomRepository,
        student_repository: IStudentRepository,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._student_repository = student_repository
        self.setWindowTitle("Оқушыға тағайындау")

        self._classroom_combo = QComboBox(self)
        for classroom in classroom_repository.list_active():
            self._classroom_combo.addItem(classroom.name, classroom.id)
        self._classroom_combo.currentIndexChanged.connect(self._on_classroom_changed)

        self._student_combo = QComboBox(self)

        form = QFormLayout()
        form.addRow("Сынып:", self._classroom_combo)
        form.addRow("Оқушы:", self._student_combo)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        buttons.accepted.connect(self._on_accept_clicked)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

        self._populate_students()

    def _on_classroom_changed(self, _index: int) -> None:
        self._populate_students()

    def _populate_students(self) -> None:
        classroom_id = self._classroom_combo.currentData()
        self._student_combo.clear()
        if classroom_id is not None:
            for student in self._student_repository.list_by_classroom(classroom_id):
                self._student_combo.addItem(student.display_name, student.id)

    def _on_accept_clicked(self) -> None:
        if self._classroom_combo.currentData() is None or self._student_combo.currentData() is None:
            QMessageBox.warning(self, "Қате", "Сынып пен оқушыны таңдаңыз")
            return
        self.accept()

    def get_selection(self) -> tuple[str, str]:
        """``(classroom_id, student_id)`` қайтарады — тек ``accept()``-тен
        кейін шақырылуы тиіс.
        """
        return self._classroom_combo.currentData(), self._student_combo.currentData()


class DataJournalPage(QWidget):
    """Сақталған тәжірибе сессияларының тарихын (тек оқу) көрсететін бет."""

    def __init__(
        self,
        session_repository: ISessionRepository | None = None,
        module_registry: ModuleRegistry | None = None,
        csv_exporter: CSVExporter | None = None,
        classroom_repository: IClassroomRepository | None = None,
        student_repository: IStudentRepository | None = None,
        student_progress_repository: IStudentProgressRepository | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._session_repository: ISessionRepository = (
            session_repository or SqliteSessionRepository()
        )
        self._module_registry = module_registry
        self._csv_exporter = csv_exporter or CSVExporter()
        # Phase 39C: сессия-оқушы тағайындауын оқу/жазу үшін — session_
        # repository-мен БІРДЕЙ "әдепкі :memory:" қауіпсіздік конвенциясы,
        # тек ``app.py``/``MainWindow`` нақты (ортақ) данасын береді.
        self._classroom_repository: IClassroomRepository = (
            classroom_repository or SqliteClassroomRepository()
        )
        self._student_repository: IStudentRepository = (
            student_repository or SqliteStudentRepository()
        )
        self._student_progress_repository: IStudentProgressRepository = (
            student_progress_repository or SqliteStudentProgressRepository()
        )
        self._sessions: tuple[SessionSummary, ...] = ()
        self._rows: tuple[_JournalRow, ...] = ()
        self._current_detail: tuple[SessionSummary, tuple[Measurement, ...]] | None = None

        self._stack = QStackedWidget(self)
        self._stack.addWidget(self._build_list_view())
        self._stack.addWidget(self._build_detail_view())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._stack)

        self._render_list()

    # ---- Router интерфейсі ------------------------------------------------

    def on_enter(self, student_id: str | None = None, session_id: str | None = None) -> None:
        """Бет көрсетілер алдында тізімді қайта оқиды (тек summary
        сұрауы — measurement жүктелмейді). ``Жаңарту`` батырмасынан
        айырмашылығы: барлық сүзгі/іздеу әдепкі "Барлығы"/бос күйге
        қайтарылады (§ Phase 17 "on_enter резет, refresh САҚТАЙДЫ").

        § Phase 7 (Part C "Session History"): ``student_id``/``session_id``
        ЕРІКТІ — берілсе (§ ``StudentMonitoringDetailPage``-тегі
        "Тәжірибе тарихы" батырмасынан), журналды СОЛ оқушыға сүзеді
        (қажет болса, тікелей сессия бөлшегін ашады). Екеуі де ``None``
        болса (§ ЕСКІ, sidebar-дан қалыпты навигация) — мінез-құлық
        МҮЛДЕ ӨЗГЕРТІЛМЕГЕН (§ backward compatibility). ``student_id``
        жергілікті ЕШБІР сессиямен байланысты болмаса (§ рұқсат
        етілмеген/белгісіз id), қауіпсіз "Барлығы" күйіне құлайды —
        авторизацияның НАҚТЫ шекарасы сервер-жақты pull сүзгісінде
        (§ бұл сынып/оқушы жазбасы жергілікті SQLite-де МҮЛДЕ ЖОҚ
        болуы мүмкін, § docs/sync_architecture.md).
        """
        self._stack.setCurrentIndex(0)
        self._filter_combo.setCurrentIndex(0)
        self._date_filter_combo.setCurrentIndex(0)
        self._search_edit.clear()
        if student_id is None:
            self._classroom_filter_combo.setCurrentIndex(0)
            self._student_filter_combo.setCurrentIndex(0)
        self._refresh()
        if student_id is not None:
            self._apply_student_filter(student_id)
        if session_id is not None:
            self._on_open_clicked(session_id)

    def _apply_student_filter(self, student_id: str) -> None:
        student = self._student_repository.get(student_id)
        if student is None:
            self._classroom_filter_combo.setCurrentIndex(0)
            self._student_filter_combo.setCurrentIndex(0)
            return
        classroom_index = self._classroom_filter_combo.findData(student.classroom_id)
        self._classroom_filter_combo.setCurrentIndex(classroom_index if classroom_index >= 0 else 0)
        student_index = self._student_filter_combo.findData(student_id)
        self._student_filter_combo.setCurrentIndex(student_index if student_index >= 0 else 0)

    # ---- List view ------------------------------------------------------

    def _build_list_view(self) -> QWidget:
        view = QWidget(self)
        view.setObjectName("DataJournalListView")

        title_label = QLabel("Деректер журналы", view)
        title_font = title_label.font()
        title_font.setBold(True)
        title_font.setPointSize(title_font.pointSize() + 4)
        title_label.setFont(title_font)

        subtitle_label = QLabel(
            "Сақталған зертханалық өлшеулер мен тәжірибе нәтижелері", view
        )
        subtitle_label.setProperty("role", "secondary")

        header_text_layout = QVBoxLayout()
        header_text_layout.setContentsMargins(0, 0, 0, 0)
        header_text_layout.addWidget(title_label)
        header_text_layout.addWidget(subtitle_label)

        self._refresh_button = QPushButton("↻ Жаңарту", view)
        self._refresh_button.clicked.connect(self._refresh)

        header_row = QHBoxLayout()
        header_row.addLayout(header_text_layout)
        header_row.addStretch(1)
        header_row.addWidget(self._refresh_button, 0, Qt.AlignmentFlag.AlignTop)

        # Phase 17: combo-лар ӨЗ ЕҢ ҰЗЫН item мәтініне сай енге өседі —
        # max-width шегісіз бұл 1366px енінде іздеу жолағын сығып
        # тастайтыны (§ Results page-тегі БІРДЕЙ, скриншот аудитінде
        # табылған bug) АЛДЫН АЛА белгілі, сондықтан ОСЫ жерде бірден
        # шектелген.
        _FILTER_COMBO_MAX_WIDTH = 150

        # Скриншот аудитінде табылған бag (§ Phase 14-тегі ДӘЛ СОЛ түбір
        # себеп: "long content inflates ancestor minimum size"): QComboBox
        # ӨЗ minimumSizeHint()-ін ЕҢ ҰЗЫН item мәтініне сай есептейді,
        # setMaximumWidth() бұған ӘСЕР ЕТПЕЙДІ (тек РЕНДЕР ениін шектейді).
        # QStackedWidget#WorkspaceStack ӨЗ minimumSizeHint-ін тіркелген
        # БАРЛЫҚ парақтың ЕҢ үлкенін алатындықтан, бұл 4 combo DataJournalPage-ті
        # sidebar-ды 230px-тен 215px-ке дейін сығатын ЖАҢА "ең үлкен парақ"
        # етіп шығарғаны расталды. Түзету: Phase 14-тегі ДӘЛ СОЛ
        # ``setMinimumWidth(1)`` (0 ЕМЕС — Qt мұны "бос" деп санап, елемейді)
        # — combo әлі де max-width-ке дейін ЕРКІН өседі, тек ЕҢ КІШІ есептелетін
        # мән енді 1px.
        self._filter_combo = QComboBox(view)
        self._filter_combo.setMaximumWidth(_FILTER_COMBO_MAX_WIDTH)
        self._filter_combo.setMinimumWidth(1)
        self._filter_combo.addItem(_ALL_FILTER_TEXT, None)
        self._filter_combo.currentIndexChanged.connect(self._on_filter_changed)

        self._classroom_filter_combo = QComboBox(view)
        self._classroom_filter_combo.setMaximumWidth(_FILTER_COMBO_MAX_WIDTH)
        self._classroom_filter_combo.setMinimumWidth(1)
        self._classroom_filter_combo.currentIndexChanged.connect(self._on_classroom_filter_changed)

        self._student_filter_combo = QComboBox(view)
        self._student_filter_combo.setMaximumWidth(_FILTER_COMBO_MAX_WIDTH)
        self._student_filter_combo.setMinimumWidth(1)
        self._student_filter_combo.currentIndexChanged.connect(self._on_filters_changed)

        self._date_filter_combo = QComboBox(view)
        self._date_filter_combo.setMaximumWidth(_FILTER_COMBO_MAX_WIDTH)
        self._date_filter_combo.setMinimumWidth(1)
        self._date_filter_combo.currentIndexChanged.connect(self._on_filters_changed)

        self._search_edit = QLineEdit(view)
        self._search_edit.setPlaceholderText(_SEARCH_PLACEHOLDER_TEXT)
        self._search_edit.setMinimumWidth(140)
        self._search_edit.textChanged.connect(self._on_filters_changed)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Сынып:", view))
        filter_row.addWidget(self._classroom_filter_combo)
        filter_row.addWidget(QLabel("Оқушы:", view))
        filter_row.addWidget(self._student_filter_combo)
        filter_row.addWidget(QLabel("Зертханалық жұмыс:", view))
        filter_row.addWidget(self._filter_combo)
        filter_row.addWidget(QLabel("Күні:", view))
        filter_row.addWidget(self._date_filter_combo)
        filter_row.addWidget(self._search_edit, 1)
        self._filter_row = filter_row

        # Скриншот аудитінде табылған бag: репозиторий толығымен бос
        # болғанда (кесте жасырын, § Phase 32 "hidden table -> size 0")
        # QLabel-дің ӘДЕПКІ тік ``Preferred`` size policy-і бос қалған
        # тік кеңістікті ЕКІ белгінің АРАСЫНА тең бөліп, әр белгіні
        # (title/hint) шамамен 350px биіктікке "созатыны" расталды —
        # мәтін бір жол болса да. ``Fixed`` тік policy белгіні НАҚТЫ өз
        # мәтін биіктігіне шектейді.
        self._empty_state_title_label = QLabel(view)
        self._empty_state_title_label.setObjectName("WorkspaceEmptyStateLabel")
        self._empty_state_title_label.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        empty_font = self._empty_state_title_label.font()
        empty_font.setBold(True)
        self._empty_state_title_label.setFont(empty_font)
        self._empty_state_hint_label = QLabel(view)
        self._empty_state_hint_label.setObjectName("WorkspaceEmptyStateLabel")
        self._empty_state_hint_label.setWordWrap(True)
        self._empty_state_hint_label.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )

        self._table = QTableWidget(0, len(_TABLE_HEADERS), view)
        self._table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._table.setHorizontalHeaderLabels(list(_TABLE_HEADERS))
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setStretchLastSection(False)
        self._table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )

        # Phase 32 layout архитектурасы (кесте/empty-state бір ортақ
        # контейнерге оралған, СОЛ контейнер сыртқы layout-та stretch=1
        # алады) Phase 17-де ЖАҢА ашылған екінші бag тудырды: 4 жаңа
        # сүзгі қосылғаннан кейін ЖИІ болатын "толығымен бос репозиторий"
        # (Case A) күйінде, Qt-тың QVBoxLayout-ы жасырын (stretch=1)
        # кестенің орнына бос кеңістікті title/hint белгілерінің
        # АРАСЫНА/АЙНАЛАСЫНА үш бөлек "фантом" саңылау ретінде бөліп
        # тастайтыны (тіпті ``QSizePolicy.Policy.Fixed`` тік саясатымен
        # де) скриншот аудитінде расталды — ЕСКІ Phase 32 stretch-негізді
        # тәсіл осы жаңа сценарийде ЖЕТКІЛІКСІЗ. Түзету: осы бекітілмеген
        # Qt stretch-қайта-бөлу ерекшелігінің БҮКІЛ класын болдырмау үшін,
        # "бос-күй" мен "кесте" енді ЕКІ БӨЛЕК QStackedWidget парағы —
        # әр парақ ӘРҚАШАН БҮКІЛ қолжетімді ауданды алады (стретч-негізді
        # "leftover space" есептеуі мүлде жоқ), DataJournalPage-тің ӨЗІ
        # тізім/бөлшек ауысуы үшін ҚОЛДАНАТЫН ДӘЛ СОЛ паттерн.
        empty_state_widget = QWidget(view)
        empty_state_layout = QVBoxLayout(empty_state_widget)
        empty_state_layout.setContentsMargins(0, 0, 0, 0)
        empty_state_layout.addWidget(self._empty_state_title_label)
        empty_state_layout.addWidget(self._empty_state_hint_label)
        empty_state_layout.addStretch(1)

        results_container = QStackedWidget(view)
        results_container.setObjectName("DataJournalResultsContainer")
        results_container.addWidget(empty_state_widget)
        results_container.addWidget(self._table)
        self._results_stack = results_container

        layout = QVBoxLayout(view)
        layout.addLayout(header_row)
        layout.addLayout(filter_row)
        layout.addWidget(results_container, 1)
        return view

    def _refresh(self) -> None:
        experiment_id = self._filter_combo.currentData()
        self._sessions = self._session_repository.get_sessions(experiment_id=experiment_id)
        self._rebuild_filter_options()
        self._rows = self._build_rows()
        self._render_list()

    def _rebuild_filter_options(self) -> None:
        # Сүзгі опцияларын БАРЛЫҚ сақталған сессиялардан құрастырамыз
        # (ағымдағы сүзгі нәтижесінен емес), әйтпесе "Тәжірибе" сүзгісі
        # тек соңғы таңдалған опцияны ғана көрсетіп қалады.
        all_sessions = self._session_repository.get_sessions()
        current_data = self._filter_combo.currentData()

        seen: dict[str, str] = {}
        dates_seen: dict[str, str] = {}
        for session in all_sessions:
            seen.setdefault(session.experiment_id, session.experiment_title)
            date_key = session.started_at.astimezone().strftime("%d.%m.%Y")
            dates_seen.setdefault(date_key, date_key)

        self._filter_combo.blockSignals(True)
        self._filter_combo.clear()
        self._filter_combo.addItem(_ALL_FILTER_TEXT, None)
        for experiment_id, title in seen.items():
            self._filter_combo.addItem(title, experiment_id)
        index = self._filter_combo.findData(current_data)
        self._filter_combo.setCurrentIndex(index if index >= 0 else 0)
        self._filter_combo.blockSignals(False)

        current_date = self._date_filter_combo.currentData()
        self._date_filter_combo.blockSignals(True)
        self._date_filter_combo.clear()
        self._date_filter_combo.addItem(_ALL_FILTER_TEXT, None)
        # Күндер ЖАҢАдан ЕСКІге қарай — ``get_sessions()``-тің ӨЗ реті
        # (started_at DESC) бойынша, қосымша қайта сұрыптау қажет емес.
        for date_key in dates_seen:
            self._date_filter_combo.addItem(date_key, date_key)
        date_index = self._date_filter_combo.findData(current_date)
        self._date_filter_combo.setCurrentIndex(date_index if date_index >= 0 else 0)
        self._date_filter_combo.blockSignals(False)

        self._populate_classroom_filter()

    def _on_filter_changed(self, _index: int) -> None:
        experiment_id = self._filter_combo.currentData()
        self._sessions = self._session_repository.get_sessions(experiment_id=experiment_id)
        self._rows = self._build_rows()
        self._render_list()

    def _on_filters_changed(self) -> None:
        self._render_list()

    # ---- Сынып->Оқушы каскады (§ Results page-мен БІРДЕЙ паттерн) ---------

    def _populate_classroom_filter(self) -> None:
        current = self._classroom_filter_combo.currentData()
        self._classroom_filter_combo.blockSignals(True)
        self._classroom_filter_combo.clear()
        self._classroom_filter_combo.addItem(_ALL_FILTER_TEXT, None)
        for classroom in self._classroom_repository.list_active():
            self._classroom_filter_combo.addItem(classroom.name, classroom.id)
        restored = self._classroom_filter_combo.findData(current)
        self._classroom_filter_combo.setCurrentIndex(restored if restored >= 0 else 0)
        self._classroom_filter_combo.blockSignals(False)
        self._populate_student_filter()

    def _populate_student_filter(self) -> None:
        current = self._student_filter_combo.currentData()
        classroom_id = self._classroom_filter_combo.currentData()

        if classroom_id is not None:
            students = list(self._student_repository.list_by_classroom(classroom_id))
        else:
            students = []
            for classroom in self._classroom_repository.list_active():
                students.extend(self._student_repository.list_by_classroom(classroom.id))
            students.sort(key=lambda student: student.display_name)

        self._student_filter_combo.blockSignals(True)
        self._student_filter_combo.clear()
        self._student_filter_combo.addItem(_ALL_FILTER_TEXT, None)
        for student in students:
            self._student_filter_combo.addItem(student.display_name, student.id)
        restored = self._student_filter_combo.findData(current)
        self._student_filter_combo.setCurrentIndex(restored if restored >= 0 else 0)
        self._student_filter_combo.blockSignals(False)

    def _on_classroom_filter_changed(self, _index: int) -> None:
        self._populate_student_filter()
        self._render_list()

    # ---- Жол құрастыру/сүзгілеу (§ UI-деңгейлік adapter, ISessionRepository
    # ӨЗІ ешбір student/classroom өрісін білмейді) ---------------------------

    def _resolve_student_and_classroom(self, session_id: str) -> tuple[Student | None, Classroom | None]:
        """Phase 39C-тен кеңейтілген: тағайындалған оқушы ЖӘНЕ оның
        сыныбын қайтарады (Phase 17 сынып/оқушы сүзгісі үшін). Ескі
        тағайындалмаған сессияда ЕКЕУІ ДЕ ``None`` — ешбір жалған/ойдан
        шығарылған байланыс ЕШҚАШАН жасалмайды.
        """
        student_id = self._student_progress_repository.get_student_for_session(session_id)
        if student_id is None:
            return None, None
        student = self._student_repository.get(student_id)
        if student is None:
            return None, None
        classroom = self._classroom_repository.get(student.classroom_id)
        return student, classroom

    def _build_rows(self) -> tuple[_JournalRow, ...]:
        rows = []
        for summary in self._sessions:
            student, classroom = self._resolve_student_and_classroom(summary.id)
            rows.append(_JournalRow(summary=summary, student=student, classroom=classroom))
        return tuple(rows)

    def _filtered_rows(self) -> tuple[_JournalRow, ...]:
        rows = list(self._rows)

        classroom_id = self._classroom_filter_combo.currentData()
        if classroom_id is not None:
            rows = [row for row in rows if row.classroom is not None and row.classroom.id == classroom_id]

        student_id = self._student_filter_combo.currentData()
        if student_id is not None:
            rows = [row for row in rows if row.student is not None and row.student.id == student_id]

        date_key = self._date_filter_combo.currentData()
        if date_key is not None:
            rows = [
                row for row in rows
                if row.summary.started_at.astimezone().strftime("%d.%m.%Y") == date_key
            ]

        query = self._search_edit.text().strip().lower()
        if query:
            rows = [row for row in rows if self._row_matches_query(row, query)]

        return tuple(rows)

    @staticmethod
    def _row_matches_query(row: _JournalRow, query: str) -> bool:
        student_text = row.student.display_name if row.student is not None else _UNASSIGNED_TEXT
        classroom_text = row.classroom.name if row.classroom is not None else ""
        haystacks = (student_text, classroom_text, row.summary.experiment_title)
        return any(query in haystack.lower() for haystack in haystacks)

    def _render_list(self) -> None:
        has_any_sessions = self._session_repository.count_sessions() > 0
        visible_rows = self._filtered_rows() if has_any_sessions else ()
        has_visible_rows = len(visible_rows) > 0

        for widget in (
            self._classroom_filter_combo,
            self._student_filter_combo,
            self._filter_combo,
            self._date_filter_combo,
            self._search_edit,
        ):
            widget.setVisible(has_any_sessions)
        for i in range(self._filter_row.count()):
            item = self._filter_row.itemAt(i)
            if item.widget() is not None and isinstance(item.widget(), QLabel):
                item.widget().setVisible(has_any_sessions)

        if not has_any_sessions:
            self._empty_state_title_label.setText(_EMPTY_REPOSITORY_TITLE)
            self._empty_state_hint_label.setText(_EMPTY_REPOSITORY_HINT)
        elif not has_visible_rows:
            self._empty_state_title_label.setText(_EMPTY_FILTERED_TITLE)
            self._empty_state_hint_label.setText(_EMPTY_FILTERED_HINT)
        self._results_stack.setCurrentWidget(
            self._table if has_visible_rows else self._results_stack.widget(0)
        )

        # QTableWidget cell widget-ке (setCellWidget) иелік етпейді — тек
        # setRowCount(0) шақыру ескі "Қарау" батырмаларын viewport-тан
        # көрінбейтін түрде тастап кетеді, БІРАҚ Qt объект ағашынан
        # ешқашан өшірмейді (расталды: изолденген Qt тестінде
        # setRowCount(0)+setRowCount(n) қайталанғанда viewport.findChildren
        # әр итерацияда +1 өсіп отырды). Нақты өшіру үшін әр ескі
        # виджетті ЖОЛДАР қысқартылмас бұрын setParent(None) +
        # deleteLater() арқылы бөліп алу керек (бетке қайта кіргенде —
        # Router.navigate() әр рет on_enter() шақырады).
        last_column = len(_TABLE_HEADERS) - 1
        for row in range(self._table.rowCount()):
            old_widget = self._table.cellWidget(row, last_column)
            if old_widget is not None:
                old_widget.setParent(None)
                old_widget.deleteLater()
        self._table.setRowCount(0)
        self._table.setRowCount(len(visible_rows))
        for row_index, journal_row in enumerate(visible_rows):
            self._populate_row(row_index, journal_row)
        if has_visible_rows:
            self._table.resizeColumnsToContents()
            self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            # Скриншот аудитінде табылған бag: ``resizeColumnsToContents()``
            # ``setCellWidget()``-пен қойылған "Қарау" батырмасының НАҚТЫ
            # sizeHint-ін дұрыс есептемей, батырма мәтінін екі жағынан
            # кесіп тастайтыны расталды (§ Results/Feedback Review
            # беттеріндегі ДӘЛ СОЛ, әлдеқашан қолданылған түзету —
            # соңғы (Әрекет) бағанға НАҚТЫ ЕН қолмен беріледі).
            self._table.setColumnWidth(len(_TABLE_HEADERS) - 1, 100)

    def _populate_row(self, row: int, journal_row: _JournalRow) -> None:
        summary = journal_row.summary
        started_local = summary.started_at.astimezone()
        ended_local = summary.ended_at.astimezone() if summary.ended_at is not None else None

        title_text = (
            f"{summary.experiment_display_number}. {summary.experiment_title}"
            if summary.experiment_display_number is not None
            else summary.experiment_title
        )
        student_text = (
            journal_row.student.display_name if journal_row.student is not None else _UNASSIGNED_TEXT
        )

        values = (
            started_local.strftime("%d.%m.%Y"),
            title_text,
            student_text,
            f"{summary.measurement_count} өлшеу",
            started_local.strftime("%H:%M"),
            ended_local.strftime("%H:%M") if ended_local is not None else _NO_VALUE_TEXT,
        )
        for column, text in enumerate(values):
            item = QTableWidgetItem(text)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            # Ескі тағайындалмаған сессия — § "Visually distinguish them
            # subtly using the existing neutral/muted palette" (қате-түс
            # ЕМЕС, тек бейтарап "secondary" мәтін реңі). Тек "Оқушы"
            # бағанының ӨЗІ, қалған жол НЕЙТРАЛ қалады (§ "Keep the rest
            # of each row neutral").
            if column == 2 and journal_row.student is None:
                item.setForeground(QColor(COLOR_TEXT_MUTED))
            self._table.setItem(row, column, item)

        open_button = QPushButton(_ACTION_BUTTON_TEXT, self._table)
        open_button.clicked.connect(
            lambda _checked=False, session_id=summary.id: self._on_open_clicked(session_id)
        )
        self._table.setCellWidget(row, len(_TABLE_HEADERS) - 1, open_button)

    # ---- Detail view ------------------------------------------------------

    def _build_detail_view(self) -> QWidget:
        view = QWidget(self)
        view.setObjectName("DataJournalDetailView")

        self._detail_back_button = QPushButton("← Журналға оралу", view)
        self._detail_back_button.clicked.connect(self._on_back_to_list_clicked)

        self._detail_export_button = QPushButton("CSV экспорт", view)
        self._detail_export_button.clicked.connect(self._on_export_clicked)

        # Phase 39C: тек НАҚТЫ тағайындалмаған сессияда ғана көрінеді
        # (``_render_detail()``-де орнатылады) — қайта тағайындау мүлде
        # мүмкін емес (§ "never silently move a session" — рұқсат етілмеуі
        # арқылы, guard-пен ЕМЕС).
        self._assign_button = QPushButton("Оқушыға тағайындау", view)
        self._assign_button.clicked.connect(self._on_assign_button_clicked)

        top_row = QHBoxLayout()
        top_row.addWidget(self._detail_back_button)
        top_row.addStretch(1)
        top_row.addWidget(self._assign_button)
        top_row.addWidget(self._detail_export_button)

        self._detail_title_label = QLabel(view)
        detail_title_font = self._detail_title_label.font()
        detail_title_font.setBold(True)
        detail_title_font.setPointSize(detail_title_font.pointSize() + 2)
        self._detail_title_label.setFont(detail_title_font)

        self._detail_meta_label = QLabel(view)
        self._detail_meta_label.setProperty("role", "secondary")
        self._detail_meta_label.setWordWrap(True)

        self._detail_table = MeasurementTableWidget(view)
        self._detail_graph = LiveGraphWidget(view)

        # Phase 17: "1. Measurement table 2. Measurement graph" —
        # ``MeasurementWorkspace._build_placeholders_section()``-тегі
        # graph:table 13:7 ара қатынасымен БІРДЕЙ, бұрыннан бар "graph:
        # table splitter" конвенциясы (§ "reuse existing graph/chart
        # component... simplest existing project convention").
        detail_splitter = QSplitter(Qt.Orientation.Horizontal, view)
        detail_splitter.addWidget(self._detail_graph)
        detail_splitter.addWidget(self._detail_table)
        detail_splitter.setStretchFactor(0, 13)
        detail_splitter.setStretchFactor(1, 7)
        detail_splitter.setSizes([650, 350])

        # Phase 17 скриншот аудитінде табылған/түзетілген нақты бag:
        # ``LiveGraphWidget``-тің НАҚТЫ (pyqtgraph негізді) минималды ені
        # ``MeasurementWorkspace``-тегідей ҮЛКЕН — splitter-ды ТІКЕЛЕЙ
        # (QScrollArea-сыз) осы бетке салу ``QStackedWidget#WorkspaceStack``-тың
        # minimumSizeHint-ін (БАРЛЫҚ тіркелген парақтың ЕҢ үлкенін алады)
        # ұлғайтып, sidebar-ды 230px-тен 215px-ке дейін сығып шығарғаны
        # расталды (§ ``measurement_workspace.py``-дегі ДӘЛ СОЛ, бұрыннан
        # құжатталған "GraphTableScrollArea" тәуекелі). Түзету ДӘЛ СОЛ
        # QScrollArea-мен орау паттернін қайта пайдаланады.
        scroll_area = QScrollArea(view)
        scroll_area.setObjectName("DataJournalDetailScrollArea")
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        scroll_area.setWidget(detail_splitter)

        layout = QVBoxLayout(view)
        layout.addLayout(top_row)
        layout.addWidget(self._detail_title_label)
        layout.addWidget(self._detail_meta_label)
        layout.addWidget(scroll_area, 1)
        return view

    def _on_open_clicked(self, session_id: str) -> None:
        summary = self._session_repository.get_session(session_id)
        if summary is None:
            return
        measurements = self._session_repository.get_measurements(session_id)
        self._current_detail = (summary, measurements)
        self._render_detail(summary, measurements)
        self._stack.setCurrentIndex(1)

    def _on_assign_button_clicked(self) -> None:
        if self._current_detail is None:
            return
        summary, _measurements = self._current_detail
        dialog = _AssignSessionDialog(
            self._classroom_repository, self._student_repository, parent=self
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        classroom_id, student_id = dialog.get_selection()
        self._student_progress_repository.link_session(
            summary.id, student_id, classroom_id, summary.experiment_id
        )
        self._assign_button.setVisible(False)

    def _render_detail(
        self, summary: SessionSummary, measurements: tuple[Measurement, ...]
    ) -> None:
        title_text = (
            f"{summary.experiment_display_number}. {summary.experiment_title}"
            if summary.experiment_display_number is not None
            else summary.experiment_title
        )
        self._detail_title_label.setText(title_text)

        started_local = summary.started_at.astimezone()
        ended_local = summary.ended_at.astimezone() if summary.ended_at is not None else None
        ended_text = ended_local.strftime("%d.%m.%Y %H:%M") if ended_local is not None else _NO_VALUE_TEXT

        # Phase 17 §6 "Header": тақырып/күні/уақыт/өлшеу санынан БӨЛЕК,
        # оқушы/сынып та көрсетілуі керек — ЕСКІ тағайындалмаған
        # сессияда ашық "Тағайындалмаған ескі сессия" мәтіні (§
        # _resolve_student_and_classroom(), ешбір жалған байланыс жоқ).
        student, classroom = self._resolve_student_and_classroom(summary.id)
        student_text = student.display_name if student is not None else _UNASSIGNED_TEXT
        classroom_text = classroom.name if classroom is not None else _NO_VALUE_TEXT
        student_line = student_text if student is None else f"{student_text} ({classroom_text})"

        self._detail_meta_label.setText(
            f"{student_line} • {started_local.strftime('%d.%m.%Y %H:%M')} — {ended_text} • "
            f"{summary.measurement_count} өлшеу"
        )
        self._assign_button.setVisible(student is None)

        experiment = self._resolve_experiment(summary.experiment_id)
        channels = self._resolve_channels(experiment, measurements)
        self._detail_table.configure_channels(channels)
        for measurement in measurements:
            self._detail_table.append_measurement(measurement)

        self._configure_and_feed_graph(experiment, channels, summary, measurements)

    def _resolve_experiment(self, experiment_id: str) -> ExperimentDefinition | None:
        if self._module_registry is None:
            return None
        for module in self._module_registry.get_all():
            for experiment in module.get_experiments():
                if experiment.id == experiment_id:
                    return experiment
        return None

    def _resolve_channels(
        self, experiment: ExperimentDefinition | None, measurements: tuple[Measurement, ...]
    ) -> tuple[SensorChannel, ...]:
        if experiment is not None:
            return experiment.get_display_channels()

        # Каталогта табылмаса (мыс. эксперимент кейін өшірілген/өзгерген) —
        # measurement-дің өз кілттерінен жалпы бағандар құрамыз, ешқашан
        # құламайды.
        if not measurements:
            return ()
        keys = list(measurements[0].values.keys()) + list(measurements[0].derived_values.keys())
        return tuple(
            SensorChannel(key=key, display_name=key, unit="", required=False)
            for key in keys
        )

    def _configure_and_feed_graph(
        self,
        experiment: ExperimentDefinition | None,
        channels: tuple[SensorChannel, ...],
        summary: SessionSummary,
        measurements: tuple[Measurement, ...],
    ) -> None:
        """§7 "reuse existing graph/chart component" — ``LiveGraphWidget``
        ЖИВ жұмыс кеңістігімен БІРДЕЙ ``configure_channels()``/
        ``set_measurements()`` арқылы, тек ``capture_mode`` ӘДЕЙІ
        ЕШҚАШАН қосылмайды: "capture" (қолмен нүкте сақтау) тек ЖИВ
        сеанс кезінде мағыналы, ал журналда САҚТАЛҒАН барлық нүкте
        ӘРҚАШАН толық көрсетілуі керек (§ "graphing must work exactly
        the same if measurements exist").
        """
        self._detail_graph.configure_channels(
            channels,
            x_channel=experiment.graph_x_channel if experiment is not None else None,
            y_channels=(experiment.graph_y_channels or None) if experiment is not None else None,
            connect_points=experiment.graph_connect_points if experiment is not None else True,
            show_fit=experiment.graph_show_fit if experiment is not None else False,
            x_label=experiment.graph_x_label if experiment is not None else None,
            y_label=experiment.graph_y_label if experiment is not None else None,
            title=experiment.graph_title if experiment is not None else None,
            capture_mode=False,
            experiment_title=experiment.title if experiment is not None else summary.experiment_title,
        )
        session = ExperimentSession(
            id=summary.id,
            experiment_id=summary.experiment_id,
            started_at=summary.started_at,
            ended_at=summary.ended_at,
            measurements=list(measurements),
        )
        self._detail_graph.set_measurements(session)

    def _on_back_to_list_clicked(self) -> None:
        self._stack.setCurrentIndex(0)

    def _on_export_clicked(self) -> None:
        if self._current_detail is None:
            return
        summary, measurements = self._current_detail
        if not measurements:
            return

        session = ExperimentSession(
            id=summary.id,
            experiment_id=summary.experiment_id,
            started_at=summary.started_at,
            ended_at=summary.ended_at,
            measurements=list(measurements),
        )

        file_path, _selected_filter = QFileDialog.getSaveFileName(
            self, "CSV экспорттау", "", "CSV файлдары (*.csv)"
        )
        if not file_path:
            return

        self._csv_exporter.export(session, file_path)
