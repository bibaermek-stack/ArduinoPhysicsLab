"""ResultsPage — "Нәтижелер" беті (Phase 16, Мұғалім-тек).

Мұғалімге 4 сұраққа жылдам жауап беруге арналған: қай оқушылар
зертханалық жұмысты жіберді, қай жіберулер тексеруді күтуде, әр оқушы
қандай нәтиже/баға алды, нақты бір оқушының нәтижесін қалай тез табуға
болады.

Дерек көзі толығымен ``IStudentProgressRepository.list_submitted_progress()``
(§ ``TeacherFeedbackReviewPage``/``TeacherDashboardPage``-тегі "Соңғы
нәтижелер"-мен БІРДЕЙ дерек аясы — FEEDBACK_SUBMITTED/REVIEWED, яғни
НАҚТЫ жіберілген жұмыстар ғана) — ешбір параллель бизнес-логика/статус
есептеу ЖОҚ, тек презентация/сүзгі/сұрыптау (§ "Do not put business
logic directly into the page", ``ClassManagementPage``/
``TeacherFeedbackReviewPage``-мен БІРДЕЙ принцип).

"Қарау" батырмасы ``TeacherFeedbackReviewPage``-тің "Есепті ашу"
батырмасымен БІРДЕЙ, бұрыннан бар, оқу-ғана ``ExperimentReportDialog``-ты
қайта пайдаланады (§ Phase 16 талабы: "existing valid... detail view
exists -> Қарау should navigate/wire to it", жаңа есеп беті ЖОҚ). Бұл
бет ӘДЕЙІ бағалау (grading) мүмкіндігін ҰСЫНБАЙДЫ — тек қарау/іздеу —
бағалау жұмыс ағыны ЖАЛҒЫЗ ``TeacherFeedbackReviewPage``-де қалады (§
"Do NOT touch Feedback Review", қосарланған grading UI болдырмау үшін).

Сұрыптау ӘДЕЙІ Qt-тың ендірілген ``QTableWidget.setSortingEnabled()``
тақырып-шерту тетігі АРҚЫЛЫ ЕМЕС, ``TeacherFeedbackReviewPage``-тегі
"Сұрыптау" ашылмалы тізімімен (толық Python-деңгейлік қайта құрастыру)
іске асырылады — себебі ``setCellWidget()`` арқылы қойылған "Қарау"
батырмалары Qt-тың ішкі сұрыптау кезінде НАҚТЫ жолмен бірге ЖЫЛЖЫМАЙДЫ
(белгілі Qt шектеуі), бұл жол/батырма сәйкессіздігін тудырар еді.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from domain.entities.classroom import Classroom
from domain.entities.experiment_definition import ExperimentDefinition
from domain.entities.experiment_session import ExperimentSession
from domain.entities.student import Student
from domain.entities.student_experiment_progress import ProgressStatus, StudentExperimentProgress
from domain.interfaces.i_active_teacher_repository import IActiveTeacherRepository
from domain.interfaces.i_classroom_repository import IClassroomRepository
from domain.interfaces.i_feedback_repository import IFeedbackRepository
from domain.interfaces.i_session_repository import ISessionRepository
from domain.interfaces.i_student_progress_repository import IStudentProgressRepository
from domain.interfaces.i_student_repository import IStudentRepository
from domain.interfaces.i_teacher_repository import ITeacherRepository
from domain.services.experiment_conclusion import build_automatic_conclusion
from domain.services.experiment_report_data import build_experiment_report_data
from domain.services.teacher_scope import resolve_allowed_classroom_ids
from infrastructure.storage.sqlite_active_teacher_repository import SqliteActiveTeacherRepository
from infrastructure.storage.sqlite_teacher_repository import SqliteTeacherRepository
from modules.module_registry import ModuleRegistry
from ui.themes.theme_manager import COLOR_SUCCESS, COLOR_WARNING
from ui.widgets.experiment_report_dialog import ExperimentReportDialog

_PAGE_TITLE = "Нәтижелер"
_PAGE_SUBTITLE = "Оқушылардың зертханалық жұмыс нәтижелерін қарау және тексеру."

_NO_VALUE_TEXT = "—"
_ALL_FILTER_TEXT = "Барлығы"
_SEARCH_PLACEHOLDER_TEXT = "Іздеу..."
_OPEN_REPORT_TEXT = "Қарау"

_EMPTY_REPOSITORY_TITLE = "Әзірге зертханалық жұмыс нәтижелері жоқ."
_EMPTY_REPOSITORY_HINT = "Оқушылар зертханалық жұмыстарды орындағаннан кейін нәтижелер осы жерде көрсетіледі."
_EMPTY_FILTERED_TITLE = "Нәтиже табылмады."
_EMPTY_FILTERED_HINT = "Іздеу немесе сүзгі параметрлерін өзгертіп көріңіз."

_TABLE_HEADERS = ("Оқушы", "Сынып", "Зертханалық жұмыс", "Күні", "Күйі", "Баға", "")
_EXPERIMENT_COLUMN_INDEX = 2
_ACTION_COLUMN_INDEX = 6

# ``TeacherDashboardPage._RESULT_STATUS_TEXT``/``TeacherFeedbackReviewPage.
# _STATUS_TEXT``-пен БІРДЕЙ терминология/түс (§ "reuse existing... Do NOT
# introduce a second conflicting status-color system") — жалғыз локал
# көшірме, БАСҚА бет модулінен импортталмайды (§ жобаның бұрыннан бар,
# 3 жерде қайталанған per-page dict конвенциясы).
_STATUS_TEXT: dict[ProgressStatus, str] = {
    ProgressStatus.FEEDBACK_SUBMITTED: "Тексеруді күтуде",
    ProgressStatus.REVIEWED: "Тексерілді",
}
_STATUS_COLOR: dict[ProgressStatus, str] = {
    ProgressStatus.FEEDBACK_SUBMITTED: COLOR_WARNING,
    ProgressStatus.REVIEWED: COLOR_SUCCESS,
}

_STATUS_FILTER_ALL = "all"
_STATUS_FILTER_WAITING = "waiting"
_STATUS_FILTER_REVIEWED = "reviewed"
_STATUS_FILTER_OPTIONS: tuple[tuple[str, str], ...] = (
    (_STATUS_FILTER_ALL, _ALL_FILTER_TEXT),
    (_STATUS_FILTER_WAITING, "Тексеруді күтуде"),
    (_STATUS_FILTER_REVIEWED, "Тексерілді"),
)

_SORT_DEFAULT = "default"
_SORT_DATE_DESC = "date_desc"
_SORT_DATE_ASC = "date_asc"
_SORT_STUDENT = "student"
_SORT_CLASSROOM = "classroom"
_SORT_STATUS = "status"
_SORT_OPTIONS: tuple[tuple[str, str], ...] = (
    (_SORT_DEFAULT, "Әдепкі (күтуде + жаңа)"),
    (_SORT_DATE_DESC, "Күні (жаңадан)"),
    (_SORT_DATE_ASC, "Күні (ескіден)"),
    (_SORT_STUDENT, "Оқушы аты"),
    (_SORT_CLASSROOM, "Сынып"),
    (_SORT_STATUS, "Күйі"),
)


def _make_background_transparent(widget: QWidget) -> None:
    """§ ``teacher_dashboard_page._make_background_transparent()``-мен
    БІРДЕЙ себеп/түзету — ``role``-негізді ``QLabel`` өз ЕНІНЕ (QVBoxLayout-
    та толық созылған) сай ``COLOR_BACKGROUND`` тіктөртбұрышын ақ
    ``HomeSummaryCard`` үстінде бояп кетеді. instance-деңгейлік
    ``setStyleSheet()`` ғана жұмыс істейді."""
    widget.setStyleSheet("background-color: transparent;")


@dataclass(frozen=True)
class _ResultRow:
    student: Student
    classroom: Classroom | None
    experiment: ExperimentDefinition
    progress: StudentExperimentProgress


class ResultsPage(QWidget):
    """Мұғалім-тек: барлық сынып/оқушы бойынша жіберілген зертханалық
    жұмыс нәтижелерін іздеу/сүзгілеу/қарау беті.
    """

    def __init__(
        self,
        classroom_repository: IClassroomRepository,
        student_repository: IStudentRepository,
        student_progress_repository: IStudentProgressRepository,
        feedback_repository: IFeedbackRepository,
        session_repository: ISessionRepository,
        module_registry: ModuleRegistry,
        teacher_repository: ITeacherRepository | None = None,
        active_teacher_repository: IActiveTeacherRepository | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._classroom_repository = classroom_repository
        self._student_repository = student_repository
        self._student_progress_repository = student_progress_repository
        self._feedback_repository = feedback_repository
        self._session_repository = session_repository
        self._module_registry = module_registry
        self._teacher_repository = teacher_repository or SqliteTeacherRepository()
        self._active_teacher_repository = (
            active_teacher_repository or SqliteActiveTeacherRepository()
        )
        self._value_labels: dict[str, QLabel] = {}
        self._all_rows: tuple[_ResultRow, ...] = ()
        self._report_dialog: ExperimentReportDialog | None = None

        title_label = QLabel(_PAGE_TITLE, self)
        title_font = title_label.font()
        title_font.setBold(True)
        title_font.setPointSize(title_font.pointSize() + 4)
        title_label.setFont(title_font)

        subtitle_label = QLabel(_PAGE_SUBTITLE, self)
        subtitle_label.setProperty("role", "secondary")
        subtitle_label.setWordWrap(True)

        summary_row = QHBoxLayout()
        summary_row.addWidget(self._build_summary_card("total", "Барлық жұмыстар"), 1)
        summary_row.addWidget(self._build_summary_card("completed", "Аяқталған"), 1)
        summary_row.addWidget(self._build_summary_card("waiting", "Тексеруді күтуде"), 1)
        summary_row.addWidget(self._build_summary_card("average", "Орташа нәтиже"), 1)

        # Phase 16 скриншот аудитінде табылған/түзетілген бag: QComboBox
        # ӘДЕПКІ бойынша ӨЗ ЕҢ ҰЗЫН item мәтініне (мыс. толық тәжірибе
        # атауы/"Әдепкі (күтуде + жаңа)") сай ені өседі — max-width
        # шегісіз БАРЛЫҚ сүзгі+сұрыптау+іздеу БІР жолда 1366px енінде
        # терезе шетінен тыс шығып, іздеу өрісін дерлік нөлге дейін сығып
        # тастайтыны расталды (§ "no horizontal page scrollbar", "filter
        # alignment" тексеруі). Түзету екі бөлек: (1) әр combo-ға max-width
        # шегі (Qt ұзын мәтінді ӨЗІ elide (…) жасайды — жабық күйде, толық
        # мән dropdown ашылғанда әлі де көрінеді), (2) "Сұрыптау" (спецификацияның
        # 3-бөлімінің ӨЗ сүзгі-жолағында МҮЛДЕ ЖОҚ, 7-бөлімде БӨЛЕК талап
        # ретінде енгізілген) бөлек, ӨЗ жолына шығарылды — 4 сүзгі+іздеу
        # ғана негізгі жолда қалады.
        _FILTER_COMBO_MAX_WIDTH = 150
        _SORT_COMBO_MAX_WIDTH = 220

        self._classroom_filter_combo = QComboBox(self)
        self._classroom_filter_combo.setMaximumWidth(_FILTER_COMBO_MAX_WIDTH)
        self._classroom_filter_combo.currentIndexChanged.connect(self._on_classroom_filter_changed)

        self._student_filter_combo = QComboBox(self)
        self._student_filter_combo.setMaximumWidth(_FILTER_COMBO_MAX_WIDTH)
        self._student_filter_combo.currentIndexChanged.connect(self._on_filters_changed)

        self._experiment_filter_combo = QComboBox(self)
        self._experiment_filter_combo.setMaximumWidth(_FILTER_COMBO_MAX_WIDTH)
        self._experiment_filter_combo.currentIndexChanged.connect(self._on_filters_changed)

        self._status_filter_combo = QComboBox(self)
        self._status_filter_combo.setMaximumWidth(_FILTER_COMBO_MAX_WIDTH)
        for key, label in _STATUS_FILTER_OPTIONS:
            self._status_filter_combo.addItem(label, key)
        self._status_filter_combo.currentIndexChanged.connect(self._on_filters_changed)

        self._search_edit = QLineEdit(self)
        self._search_edit.setPlaceholderText(_SEARCH_PLACEHOLDER_TEXT)
        self._search_edit.setMinimumWidth(140)
        self._search_edit.textChanged.connect(self._on_filters_changed)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Сынып:", self))
        filter_row.addWidget(self._classroom_filter_combo)
        filter_row.addWidget(QLabel("Оқушы:", self))
        filter_row.addWidget(self._student_filter_combo)
        filter_row.addWidget(QLabel("Зертханалық жұмыс:", self))
        filter_row.addWidget(self._experiment_filter_combo)
        filter_row.addWidget(QLabel("Күйі:", self))
        filter_row.addWidget(self._status_filter_combo)
        filter_row.addWidget(self._search_edit, 1)
        self._filter_row = filter_row

        self._sort_combo = QComboBox(self)
        self._sort_combo.setMaximumWidth(_SORT_COMBO_MAX_WIDTH)
        for key, label in _SORT_OPTIONS:
            self._sort_combo.addItem(label, key)
        self._sort_combo.currentIndexChanged.connect(self._on_filters_changed)

        sort_row = QHBoxLayout()
        sort_row.addWidget(QLabel("Сұрыптау:", self))
        sort_row.addWidget(self._sort_combo)
        sort_row.addStretch(1)
        self._sort_row = sort_row

        # Скриншот аудитінде табылған бag (§ DataJournalPage-тегі ДӘЛ СОЛ,
        # алдымен ТАБЫЛҒАН/ТҮЗЕТІЛГЕН түбір себеп): кесте жасырын кезде
        # QVBoxLayout бос қалған кеңістікті ЕКІ белгінің АРАСЫНА/АЙНАЛАСЫНА
        # "фантом" саңылау ретінде бөліп тастайды (тіпті ``Fixed`` тік
        # size policy-мен де) — стретч-негізді "leftover space" есептеуінің
        # бүкіл класы сенімсіз. Түзету: "бос-күй" мен "кесте" ЕКІ БӨЛЕК
        # QStackedWidget парағы, setVisible()/stretch-ке сенудің орнына
        # setCurrentWidget() арқылы ауысады.
        self._empty_title_label = QLabel(self)
        self._empty_title_label.setObjectName("WorkspaceEmptyStateLabel")
        self._empty_title_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        empty_font = self._empty_title_label.font()
        empty_font.setBold(True)
        self._empty_title_label.setFont(empty_font)
        self._empty_hint_label = QLabel(self)
        self._empty_hint_label.setObjectName("WorkspaceEmptyStateLabel")
        self._empty_hint_label.setWordWrap(True)
        self._empty_hint_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        self._table = QTableWidget(0, len(_TABLE_HEADERS), self)
        self._table.setHorizontalHeaderLabels(list(_TABLE_HEADERS))
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionResizeMode(
            _EXPERIMENT_COLUMN_INDEX, QHeaderView.ResizeMode.Stretch
        )

        empty_state_widget = QWidget(self)
        empty_state_layout = QVBoxLayout(empty_state_widget)
        empty_state_layout.setContentsMargins(0, 0, 0, 0)
        empty_state_layout.addWidget(self._empty_title_label)
        empty_state_layout.addWidget(self._empty_hint_label)
        empty_state_layout.addStretch(1)

        results_container = QStackedWidget(self)
        results_container.setObjectName("ResultsTableContainer")
        results_container.addWidget(empty_state_widget)
        results_container.addWidget(self._table)
        self._results_stack = results_container

        layout = QVBoxLayout(self)
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        layout.addLayout(summary_row)
        layout.addLayout(filter_row)
        layout.addLayout(sort_row)
        layout.addWidget(results_container, 1)

        self._refresh()

    # ---- Router интерфейсі ------------------------------------------------

    def on_enter(self) -> None:
        self._refresh()

    # ---- Жинақы сандар карталары --------------------------------------------

    def _build_summary_card(self, key: str, label: str) -> QWidget:
        card = QFrame(self)
        card.setObjectName("HomeSummaryCard")

        value_label = QLabel("0", card)
        value_label.setProperty("role", "cardValue")
        _make_background_transparent(value_label)
        self._value_labels[key] = value_label

        caption_label = QLabel(label, card)
        caption_label.setProperty("role", "cardLabel")
        _make_background_transparent(caption_label)

        card_layout = QVBoxLayout(card)
        card_layout.addWidget(value_label)
        card_layout.addWidget(caption_label)
        return card

    # ---- Каталог көмекшісі --------------------------------------------------

    def _iter_catalog_experiments_by_id(self) -> dict[str, ExperimentDefinition]:
        experiments: dict[str, ExperimentDefinition] = {}
        for module in self._module_registry.get_all():
            for experiment in module.get_experiments():
                experiments[experiment.id] = experiment
        return experiments

    # ---- Дерек жаңарту -------------------------------------------------------

    def _refresh(self) -> None:
        experiments_by_id = self._iter_catalog_experiments_by_id()
        allowed_classroom_ids = resolve_allowed_classroom_ids(
            self._teacher_repository, self._active_teacher_repository
        )
        progress_list = self._student_progress_repository.list_submitted_progress(
            allowed_classroom_ids
        )

        rows: list[_ResultRow] = []
        for progress in progress_list:
            student = self._student_repository.get(progress.student_id)
            experiment = experiments_by_id.get(progress.experiment_id)
            if student is None or experiment is None:
                continue
            classroom = self._classroom_repository.get(student.classroom_id)
            rows.append(
                _ResultRow(student=student, classroom=classroom, experiment=experiment, progress=progress)
            )
        self._all_rows = tuple(rows)

        self._populate_classroom_filter()
        self._populate_experiment_filter(experiments_by_id)
        self._update_summary_cards()
        self._render_table()

    def _update_summary_cards(self) -> None:
        total = len(self._all_rows)
        completed = sum(1 for row in self._all_rows if row.progress.status is ProgressStatus.REVIEWED)
        waiting = sum(
            1 for row in self._all_rows if row.progress.status is ProgressStatus.FEEDBACK_SUBMITTED
        )
        scores = [
            row.progress.teacher_score for row in self._all_rows if row.progress.teacher_score is not None
        ]
        average_text = f"{sum(scores) / len(scores):.1f}" if scores else _NO_VALUE_TEXT

        self._value_labels["total"].setText(str(total))
        self._value_labels["completed"].setText(str(completed))
        self._value_labels["waiting"].setText(str(waiting))
        self._value_labels["average"].setText(average_text)

    # ---- Сүзгі тізімдерін толтыру ---------------------------------------------

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

    def _populate_experiment_filter(self, experiments_by_id: dict[str, ExperimentDefinition]) -> None:
        current = self._experiment_filter_combo.currentData()
        self._experiment_filter_combo.blockSignals(True)
        self._experiment_filter_combo.clear()
        self._experiment_filter_combo.addItem(_ALL_FILTER_TEXT, None)
        for experiment in experiments_by_id.values():
            self._experiment_filter_combo.addItem(experiment.title, experiment.id)
        restored = self._experiment_filter_combo.findData(current)
        self._experiment_filter_combo.setCurrentIndex(restored if restored >= 0 else 0)
        self._experiment_filter_combo.blockSignals(False)

    def _on_classroom_filter_changed(self, _index: int) -> None:
        self._populate_student_filter()
        self._render_table()

    def _on_filters_changed(self) -> None:
        self._render_table()

    # ---- Сүзгі/сұрыптау логикасы -----------------------------------------------

    def _filtered_sorted_rows(self) -> tuple[_ResultRow, ...]:
        rows = list(self._all_rows)

        classroom_id = self._classroom_filter_combo.currentData()
        if classroom_id is not None:
            rows = [row for row in rows if row.student.classroom_id == classroom_id]

        student_id = self._student_filter_combo.currentData()
        if student_id is not None:
            rows = [row for row in rows if row.student.id == student_id]

        experiment_id = self._experiment_filter_combo.currentData()
        if experiment_id is not None:
            rows = [row for row in rows if row.experiment.id == experiment_id]

        status_key = self._status_filter_combo.currentData()
        if status_key == _STATUS_FILTER_WAITING:
            rows = [row for row in rows if row.progress.status is ProgressStatus.FEEDBACK_SUBMITTED]
        elif status_key == _STATUS_FILTER_REVIEWED:
            rows = [row for row in rows if row.progress.status is ProgressStatus.REVIEWED]

        query = self._search_edit.text().strip().lower()
        if query:
            rows = [row for row in rows if self._row_matches_query(row, query)]

        return self._sorted_rows(rows)

    @staticmethod
    def _row_matches_query(row: _ResultRow, query: str) -> bool:
        classroom_name = row.classroom.name if row.classroom is not None else ""
        haystacks = (row.student.display_name, classroom_name, row.experiment.title)
        return any(query in haystack.lower() for haystack in haystacks)

    @staticmethod
    def _sort_date_key(row: _ResultRow) -> datetime:
        submitted_at = row.progress.submitted_at
        return submitted_at if submitted_at is not None else datetime.min.replace(tzinfo=timezone.utc)

    def _sorted_rows(self, rows: list[_ResultRow]) -> tuple[_ResultRow, ...]:
        sort_key = self._sort_combo.currentData()
        if sort_key == _SORT_DATE_ASC:
            rows.sort(key=self._sort_date_key)
        elif sort_key == _SORT_DATE_DESC:
            rows.sort(key=self._sort_date_key, reverse=True)
        elif sort_key == _SORT_STUDENT:
            rows.sort(key=lambda row: row.student.display_name)
        elif sort_key == _SORT_CLASSROOM:
            rows.sort(key=lambda row: row.classroom.name if row.classroom is not None else "")
        elif sort_key == _SORT_STATUS:
            rows.sort(
                key=lambda row: 0 if row.progress.status is ProgressStatus.FEEDBACK_SUBMITTED else 1
            )
        else:
            # Әдепкі (§ Phase 16 талабы): 1) тексеруді күтуде, 2) ЕҢ жаңа,
            # 3) қалғандары. Python-дың sort() тұрақты (stable) болғандықтан,
            # алдымен күні бойынша (жаңадан) сұрыпталады, содан кейін
            # статус басымдығы бойынша — әр топтың ІШІНДЕГІ күн реті сақталады.
            rows.sort(key=self._sort_date_key, reverse=True)
            rows.sort(
                key=lambda row: 0 if row.progress.status is ProgressStatus.FEEDBACK_SUBMITTED else 1
            )
        return tuple(rows)

    # ---- Кестені рендерлеу ----------------------------------------------------

    def _render_table(self) -> None:
        has_any_rows = len(self._all_rows) > 0
        rows = self._filtered_sorted_rows() if has_any_rows else ()
        has_visible_rows = len(rows) > 0

        for widget in (
            self._classroom_filter_combo,
            self._student_filter_combo,
            self._experiment_filter_combo,
            self._status_filter_combo,
            self._sort_combo,
            self._search_edit,
        ):
            widget.setVisible(has_any_rows)
        for row_layout in (self._filter_row, self._sort_row):
            for i in range(row_layout.count()):
                item = row_layout.itemAt(i)
                if item.widget() is not None and isinstance(item.widget(), QLabel):
                    item.widget().setVisible(has_any_rows)

        if not has_any_rows:
            self._empty_title_label.setText(_EMPTY_REPOSITORY_TITLE)
            self._empty_hint_label.setText(_EMPTY_REPOSITORY_HINT)
        elif not has_visible_rows:
            self._empty_title_label.setText(_EMPTY_FILTERED_TITLE)
            self._empty_hint_label.setText(_EMPTY_FILTERED_HINT)
        self._results_stack.setCurrentWidget(self._table if has_visible_rows else self._results_stack.widget(0))

        # setRowCount(0) ескі әрекет батырмалары виджетін viewport-тан
        # көрінбейтін түрде тастап кетеді, БІРАҚ Qt объект ағашынан ешқашан
        # өшірмейді (§ TeacherFeedbackReviewPage._render_table()-мен БІРДЕЙ
        # расталған bug). Нақты өшіру үшін әр ескі виджетті ЖОЛДАР
        # қысқартылмас бұрын setParent(None) + deleteLater() арқылы бөліп
        # алу керек.
        for row in range(self._table.rowCount()):
            old_widget = self._table.cellWidget(row, _ACTION_COLUMN_INDEX)
            if old_widget is not None:
                old_widget.setParent(None)
                old_widget.deleteLater()
        self._table.setRowCount(0)
        self._table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            self._populate_row(row_index, row)
        if has_visible_rows:
            self._table.resizeColumnsToContents()
            self._table.horizontalHeader().setSectionResizeMode(
                _EXPERIMENT_COLUMN_INDEX, QHeaderView.ResizeMode.Stretch
            )
            self._table.setColumnWidth(_ACTION_COLUMN_INDEX, 110)

    def _populate_row(self, row_index: int, row: _ResultRow) -> None:
        classroom_text = row.classroom.name if row.classroom is not None else _NO_VALUE_TEXT
        date_text = (
            row.progress.submitted_at.astimezone().strftime("%d.%m.%Y")
            if row.progress.submitted_at is not None
            else _NO_VALUE_TEXT
        )
        status_text = _STATUS_TEXT.get(row.progress.status, _NO_VALUE_TEXT)
        score_text = (
            str(row.progress.teacher_score) if row.progress.teacher_score is not None else _NO_VALUE_TEXT
        )

        values = (row.student.display_name, classroom_text, row.experiment.title, date_text)
        for column, text in enumerate(values):
            item = QTableWidgetItem(text)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(row_index, column, item)

        status_item = QTableWidgetItem(status_text)
        status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        color_hex = _STATUS_COLOR.get(row.progress.status)
        if color_hex is not None:
            status_item.setForeground(QColor(color_hex))
        self._table.setItem(row_index, 4, status_item)

        score_item = QTableWidgetItem(score_text)
        score_item.setFlags(score_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self._table.setItem(row_index, 5, score_item)

        action_widget = QWidget(self._table)
        action_layout = QHBoxLayout(action_widget)
        action_layout.setContentsMargins(0, 0, 0, 0)
        report_button = QPushButton(_OPEN_REPORT_TEXT, action_widget)
        report_button.setEnabled(
            row.experiment.report is not None and row.progress.latest_session_id is not None
        )
        report_button.clicked.connect(lambda _checked=False, r=row: self._on_open_report_clicked(r))
        action_layout.addWidget(report_button)
        self._table.setCellWidget(row_index, _ACTION_COLUMN_INDEX, action_widget)

    # ---- "Қарау": бұрыннан бар ExperimentReportDialog-ты қайта пайдалану --------

    def _build_session(self, session_id: str) -> ExperimentSession | None:
        summary = self._session_repository.get_session(session_id)
        if summary is None:
            return None
        measurements = self._session_repository.get_measurements(session_id)
        return ExperimentSession(
            id=summary.id,
            experiment_id=summary.experiment_id,
            started_at=summary.started_at,
            ended_at=summary.ended_at,
            measurements=list(measurements),
        )

    def _on_open_report_clicked(self, row: _ResultRow) -> None:
        session_id = row.progress.latest_session_id
        if session_id is None:
            return
        session = self._build_session(session_id)
        if session is None:
            return
        report_data = build_experiment_report_data(row.experiment, session)
        feedback_result = self._feedback_repository.get_result(session_id)

        dialog = ExperimentReportDialog(
            row.experiment.title,
            row.experiment.guide,
            row.experiment.report,
            report_data,
            graph_pixmap=None,
            parent=self,
            automatic_conclusion=build_automatic_conclusion(report_data),
            assessment=row.experiment.assessment,
            feedback_result=feedback_result,
        )
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.finished.connect(self._on_report_dialog_finished)
        self._report_dialog = dialog
        dialog.show()

    def _on_report_dialog_finished(self) -> None:
        self._report_dialog = None
