"""TeacherFeedbackReviewPage — "Кері байланысты тексеру" беті
(Phase 40, Мұғалім-тек).

``ClassManagementPage`` сынып→оқушы drill-down арқылы БІР оқушының
прогресін көрсетеді — бұл бет, керісінше, БАРЛЫҚ сыныптар/оқушылар
бойынша НАҚТЫ жіберілген (``FEEDBACK_SUBMITTED``/``REVIEWED``) есептерді
БІР жалпақ кезек ретінде көрсетеді (іздеу/сүзгі/сұрыптаумен). Есеп/кері
байланыс диалогтары ``ExperimentReportDialog``/``ExperimentFeedbackDialog``-ты
``ClassManagementPage``-дегідей ӘРІ ҚАРАЙ рендерлеу жүйесін ЕШБІР
қайталамай қайта пайдаланады — бұл беттің өз жаңа коды тек кезек
құрастыру/сүзгілеу/сұрыптау (презентация), персистенция желімі
``ClassManagementPage``-мен БІРДЕЙ (``IFeedbackRepository``-ге жазу).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from domain.entities.classroom import Classroom
from domain.entities.experiment_definition import ExperimentDefinition
from domain.entities.experiment_feedback_result import ExperimentFeedbackResult, TeacherAssessment
from domain.entities.experiment_session import ExperimentSession
from domain.entities.student import Student
from domain.entities.student_experiment_progress import ProgressStatus, StudentExperimentProgress
from domain.entities.user_role import UserRole
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
from ui.widgets.experiment_feedback_dialog import ExperimentFeedbackDialog
from ui.widgets.experiment_report_dialog import ExperimentReportDialog
from ui.widgets.home_summary_card import HomeSummaryCard

_PAGE_TITLE = "Кері байланысты тексеру"
_OPEN_REPORT_TEXT = "Есепті ашу"
# Phase 18: жеке "Бағалау" батырмасы орнына, жол статусына тәуелді БІР
# негізгі әрекет (§ "For pending submissions: Тексеру. For reviewed
# submissions: Қарау."). Екеуі де ДӘЛ СОЛ, өзгертілмеген
# ``ExperimentFeedbackDialog``-ты ашады — тек мәтін өзгереді, диалогтың
# ӨЗІ (0-10 баға/пікір/"Мұғалім бағасын сақтау") ЕШБІР жаңа grading
# механизмі ЖОҚ, толығымен қайта пайдаланылады (§ "Do NOT create a
# second competing grading implementation"). "Есепті ашу" (толық
# есеп/өлшеулер/қорытынды, ``ExperimentReportDialog``) БӨЛЕК, екінші
# батырма ретінде сақталды — ол ортақ, 5 БАСҚА бетте де (Нәтижелер/
# Сыныптар мен оқушылар/Деректер журналы емес, бірақ Experiment
# Workspace/Student Feedback/Student Results/Class Management/Results)
# қолданылатын диалог класы, оны БІРІКТІРУ/қайта жазу осы фазаның
# "Do not modify unrelated code" шегінен шығар еді (§ толық негіздеме
# қорытынды есепте).
_ACTION_PENDING_TEXT = "Тексеру"
_ACTION_REVIEWED_TEXT = "Қарау"
_NO_VALUE_TEXT = "—"
_EMPTY_REPOSITORY_TITLE = "Жіберілген жұмыстар жоқ"
_EMPTY_REPOSITORY_HINT = "Оқушылар жұмыстарын тексеруге жібергеннен кейін олар осы жерде көрсетіледі."
_EMPTY_FILTERED_TITLE = "Сүзгіге сәйкес жұмыстар табылмады."
_EMPTY_FILTERED_HINT = "Іздеу немесе сүзгі параметрлерін өзгертіп көріңіз."
_ALL_FILTER_TEXT = "Барлығы"
_SEARCH_PLACEHOLDER_TEXT = "Оқушы, сынып немесе тәжірибе бойынша іздеу..."

_STATUS_TEXT: dict[ProgressStatus, str] = {
    ProgressStatus.FEEDBACK_SUBMITTED: "Тексеруді күтуде",
    ProgressStatus.REVIEWED: "Тексерілді",
}
# §4 "Status colors must reuse existing ThemeManager semantic colors" —
# Results/Data Journal беттеріндегі ДӘЛ СОЛ 2 токен/мағына, жаңа түс
# жүйесі ЖОҚ.
_STATUS_COLOR: dict[ProgressStatus, str] = {
    ProgressStatus.FEEDBACK_SUBMITTED: COLOR_WARNING,
    ProgressStatus.REVIEWED: COLOR_SUCCESS,
}

# Phase 18 §4 "Preferred columns": Оқушы/Сынып/Зертханалық жұмыс/
# Жіберілген күні/Күйі/Баға/Әрекет — Күйі ЕНДІ Баға-дан БҰРЫН (бұрын
# керісінше еді), "Тәжірибе"->"Зертханалық жұмыс" (Results/Data Journal-
# мен БІРДЕЙ термин), соңғы баған "Тексеру" тақырыбынан "Әрекет"-ке
# ауысты (§ ескі тақырып іс жүзінде СТАТУС баганын білдіретін, ал НАҚТЫ
# әрекет батырмасы жасырын "" тақырыппен еді — шатастыратын атау
# қатесі, осы фазада түзетілді).
_TABLE_HEADERS = ("Оқушы", "Сынып", "Зертханалық жұмыс", "Жіберілген күні", "Күйі", "Баға", "Әрекет")
_EXPERIMENT_COLUMN_INDEX = 2

_FILTER_ALL = "all"
_FILTER_WAITING = "waiting"
_FILTER_REVIEWED = "reviewed"
_STATUS_FILTER_OPTIONS: tuple[tuple[str, str], ...] = (
    (_FILTER_ALL, _ALL_FILTER_TEXT),
    (_FILTER_WAITING, "Тексеруді күтуде"),
    (_FILTER_REVIEWED, "Тексерілді"),
)

_SORT_DATE_DESC = "date_desc"
_SORT_DATE_ASC = "date_asc"
_SORT_STUDENT = "student"
_SORT_CLASSROOM = "classroom"
# §3 "Ең жаңасы/Ең ескісі" ұсынылған, БІРАҚ Results/Data Journal
# беттерінде осы ДӘЛ концепция үшін "Күні (жаңадан)"/"Күні (ескіден)"
# мәтіні ӘЛДЕҚАШАН қолданыста (§ Phase 16/17) — терминологияны
# қайталап ойлап шығармау үшін (§ жобаның бұрыннан бар "reuse existing
# terminology" принципі) СОЛ мәтін осында да сақталды.
_SORT_OPTIONS: tuple[tuple[str, str], ...] = (
    (_SORT_DATE_DESC, "Күні (жаңадан)"),
    (_SORT_DATE_ASC, "Күні (ескіден)"),
    (_SORT_STUDENT, "Оқушы аты"),
    (_SORT_CLASSROOM, "Сынып"),
)


@dataclass(frozen=True)
class _ReviewRow:
    student: Student
    classroom: Classroom | None
    experiment: ExperimentDefinition
    progress: StudentExperimentProgress


class TeacherFeedbackReviewPage(QWidget):
    """Мұғалім-тек: барлық сынып/оқушы бойынша жіберілген есептердің
    жалпақ тексеру кезегі.
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
        self._all_rows: tuple[_ReviewRow, ...] = ()
        self._feedback_dialog: ExperimentFeedbackDialog | None = None
        self._report_dialog: ExperimentReportDialog | None = None

        title_label = QLabel(_PAGE_TITLE, self)
        title_font = title_label.font()
        title_font.setBold(True)
        title_font.setPointSize(title_font.pointSize() + 4)
        title_label.setFont(title_font)

        summary_row = QHBoxLayout()
        summary_row.addWidget(self._build_summary_card("total_submitted", "Барлығы жіберілген"), 1)
        summary_row.addWidget(self._build_summary_card("waiting", "Тексеруді күтуде"), 1)
        summary_row.addWidget(self._build_summary_card("reviewed", "Тексерілді"), 1)

        # Phase 18 §3: combo-лар ӨЗ ЕҢ ҰЗЫН item мәтініне сай енге өседі —
        # Results/Data Journal беттерінде (§ Phase 16/17) скриншот
        # аудитінде табылған ДӘЛ СОЛ layout-overflow bug-ты АЛДЫН АЛУ
        # үшін, осы жерде БІРДЕН max/min-width шектеулері қойылады.
        _FILTER_COMBO_MAX_WIDTH = 150

        self._classroom_filter_combo = QComboBox(self)
        self._classroom_filter_combo.setMaximumWidth(_FILTER_COMBO_MAX_WIDTH)
        self._classroom_filter_combo.setMinimumWidth(1)
        self._classroom_filter_combo.currentIndexChanged.connect(self._on_classroom_filter_changed)

        self._student_filter_combo = QComboBox(self)
        self._student_filter_combo.setMaximumWidth(_FILTER_COMBO_MAX_WIDTH)
        self._student_filter_combo.setMinimumWidth(1)
        self._student_filter_combo.currentIndexChanged.connect(self._on_filters_changed)

        self._experiment_filter_combo = QComboBox(self)
        self._experiment_filter_combo.setMaximumWidth(_FILTER_COMBO_MAX_WIDTH)
        self._experiment_filter_combo.setMinimumWidth(1)
        self._experiment_filter_combo.currentIndexChanged.connect(self._on_filters_changed)

        self._status_filter_combo = QComboBox(self)
        self._status_filter_combo.setMaximumWidth(_FILTER_COMBO_MAX_WIDTH)
        self._status_filter_combo.setMinimumWidth(1)
        for key, label in _STATUS_FILTER_OPTIONS:
            self._status_filter_combo.addItem(label, key)
        self._status_filter_combo.currentIndexChanged.connect(self._on_filters_changed)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Сынып:", self))
        filter_row.addWidget(self._classroom_filter_combo)
        filter_row.addWidget(QLabel("Оқушы:", self))
        filter_row.addWidget(self._student_filter_combo)
        filter_row.addWidget(QLabel("Зертханалық жұмыс:", self))
        filter_row.addWidget(self._experiment_filter_combo)
        filter_row.addWidget(QLabel("Күйі:", self))
        filter_row.addWidget(self._status_filter_combo)
        self._filter_row = filter_row

        self._search_edit = QLineEdit(self)
        self._search_edit.setPlaceholderText(_SEARCH_PLACEHOLDER_TEXT)
        self._search_edit.setMinimumWidth(140)
        self._search_edit.textChanged.connect(self._on_filters_changed)

        self._sort_combo = QComboBox(self)
        self._sort_combo.setMaximumWidth(220)
        for key, label in _SORT_OPTIONS:
            self._sort_combo.addItem(label, key)
        self._sort_combo.currentIndexChanged.connect(self._on_filters_changed)

        controls_row = QHBoxLayout()
        controls_row.addWidget(QLabel("Сұрыптау:", self))
        controls_row.addWidget(self._sort_combo)
        controls_row.addWidget(self._search_edit, 1)
        self._controls_row = controls_row

        self._empty_state_title_label = QLabel(self)
        self._empty_state_title_label.setObjectName("WorkspaceEmptyStateLabel")
        empty_font = self._empty_state_title_label.font()
        empty_font.setBold(True)
        self._empty_state_title_label.setFont(empty_font)
        self._empty_state_hint_label = QLabel(self)
        self._empty_state_hint_label.setObjectName("WorkspaceEmptyStateLabel")
        self._empty_state_hint_label.setWordWrap(True)

        self._table = QTableWidget(0, len(_TABLE_HEADERS), self)
        self._table.setHorizontalHeaderLabels(list(_TABLE_HEADERS))
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionResizeMode(
            _EXPERIMENT_COLUMN_INDEX, QHeaderView.ResizeMode.Stretch
        )

        # Phase 18: Data Journal-да (§ Phase 17) табылған Qt ерекшелігі —
        # ``QVBoxLayout``-та stretch=1 бар ЖАСЫРЫН кестенің қасындағы
        # stretch=0 title/hint белгілері арасына фантом бос саңылау
        # кірістіретіні — осы бетте АЛДЫН АЛА болдырмау үшін
        # ``QStackedWidget`` (2 парақ: "бос-күй" виджеті мен кесте)
        # қолданылады, ЕШҚАШАН қарапайым ``addWidget(table, 1)``+
        # ``setVisible()`` ЕМЕС.
        empty_state_widget = QWidget(self)
        empty_state_layout = QVBoxLayout(empty_state_widget)
        empty_state_layout.setContentsMargins(0, 0, 0, 0)
        empty_state_layout.addWidget(self._empty_state_title_label)
        empty_state_layout.addWidget(self._empty_state_hint_label)
        empty_state_layout.addStretch(1)

        results_container = QStackedWidget(self)
        results_container.setObjectName("TeacherFeedbackResultsContainer")
        results_container.addWidget(empty_state_widget)
        results_container.addWidget(self._table)
        self._results_stack = results_container

        layout = QVBoxLayout(self)
        layout.addWidget(title_label)
        layout.addLayout(summary_row)
        layout.addLayout(filter_row)
        layout.addLayout(controls_row)
        layout.addWidget(results_container, 1)

        self._refresh()

    # ---- Router интерфейсі ------------------------------------------------

    def on_enter(self) -> None:
        self._refresh()

    # ---- Жинақы сандар карталары --------------------------------------------

    def _build_summary_card(self, key: str, label: str) -> QWidget:
        card = HomeSummaryCard(label, parent=self)
        self._value_labels[key] = card.value_label
        return card

    # ---- Кезек құрастыру/сүзгілеу/сұрыптау -----------------------------------

    def _iter_catalog_experiments_by_id(self) -> dict[str, ExperimentDefinition]:
        experiments: dict[str, ExperimentDefinition] = {}
        for module in self._module_registry.get_all():
            for experiment in module.get_experiments():
                experiments[experiment.id] = experiment
        return experiments

    def _refresh(self) -> None:
        experiments_by_id = self._iter_catalog_experiments_by_id()
        allowed_classroom_ids = resolve_allowed_classroom_ids(
            self._teacher_repository, self._active_teacher_repository
        )
        progress_list = self._student_progress_repository.list_submitted_progress(
            allowed_classroom_ids
        )

        rows: list[_ReviewRow] = []
        for progress in progress_list:
            student = self._student_repository.get(progress.student_id)
            experiment = experiments_by_id.get(progress.experiment_id)
            if student is None or experiment is None:
                continue
            classroom = self._classroom_repository.get(student.classroom_id)
            rows.append(_ReviewRow(student=student, classroom=classroom, experiment=experiment, progress=progress))
        self._all_rows = tuple(rows)

        self._populate_classroom_filter()
        self._populate_experiment_filter(experiments_by_id)
        self._update_summary_cards()
        self._render_table()

    # ---- Сынып->Оқушы каскады (§ Results/Data Journal-мен БІРДЕЙ паттерн) ---

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

    def _update_summary_cards(self) -> None:
        total_submitted = len(self._all_rows)
        waiting = sum(
            1 for row in self._all_rows if row.progress.status is ProgressStatus.FEEDBACK_SUBMITTED
        )
        reviewed = sum(1 for row in self._all_rows if row.progress.status is ProgressStatus.REVIEWED)
        self._value_labels["total_submitted"].setText(str(total_submitted))
        self._value_labels["waiting"].setText(str(waiting))
        self._value_labels["reviewed"].setText(str(reviewed))

    def _filtered_sorted_rows(self) -> tuple[_ReviewRow, ...]:
        status_key = self._status_filter_combo.currentData()
        query = self._search_edit.text().strip().lower()

        rows = list(self._all_rows)

        classroom_id = self._classroom_filter_combo.currentData()
        if classroom_id is not None:
            rows = [row for row in rows if row.classroom is not None and row.classroom.id == classroom_id]

        student_id = self._student_filter_combo.currentData()
        if student_id is not None:
            rows = [row for row in rows if row.student.id == student_id]

        experiment_id = self._experiment_filter_combo.currentData()
        if experiment_id is not None:
            rows = [row for row in rows if row.experiment.id == experiment_id]

        if status_key == _FILTER_WAITING:
            rows = [row for row in rows if row.progress.status is ProgressStatus.FEEDBACK_SUBMITTED]
        elif status_key == _FILTER_REVIEWED:
            rows = [row for row in rows if row.progress.status is ProgressStatus.REVIEWED]

        if query:
            rows = [row for row in rows if self._row_matches_query(row, query)]

        sort_key = self._sort_combo.currentData()
        if sort_key == _SORT_DATE_ASC:
            rows.sort(key=self._sort_date_key)
        elif sort_key == _SORT_STUDENT:
            rows.sort(key=lambda row: row.student.display_name)
        elif sort_key == _SORT_CLASSROOM:
            rows.sort(key=lambda row: row.classroom.name if row.classroom is not None else "")
        else:
            rows.sort(key=self._sort_date_key, reverse=True)

        return tuple(rows)

    @staticmethod
    def _sort_date_key(row: _ReviewRow):
        submitted_at = row.progress.submitted_at
        # datetime-сіз (ешқашан болмауы тиіс, submitted статус ЕШҚАШАН
        # submitted_at-сыз есептелмейді) жол сұрыптауда ЕШҚАШАН құламауы
        # үшін ең ерте мүмкін мәнге түседі.
        return submitted_at if submitted_at is not None else datetime.min.replace(tzinfo=timezone.utc)

    @staticmethod
    def _row_matches_query(row: _ReviewRow, query: str) -> bool:
        classroom_name = row.classroom.name if row.classroom is not None else ""
        haystacks = (row.student.display_name, classroom_name, row.experiment.title)
        return any(query in haystack.lower() for haystack in haystacks)

    def _on_filters_changed(self) -> None:
        self._render_table()

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
        for row_layout in (self._filter_row, self._controls_row):
            for i in range(row_layout.count()):
                item = row_layout.itemAt(i)
                if item.widget() is not None and isinstance(item.widget(), QLabel):
                    item.widget().setVisible(has_any_rows)

        if not has_any_rows:
            self._empty_state_title_label.setText(_EMPTY_REPOSITORY_TITLE)
            self._empty_state_hint_label.setText(_EMPTY_REPOSITORY_HINT)
        elif not has_visible_rows:
            self._empty_state_title_label.setText(_EMPTY_FILTERED_TITLE)
            self._empty_state_hint_label.setText(_EMPTY_FILTERED_HINT)
        self._results_stack.setCurrentWidget(
            self._table if has_visible_rows else self._results_stack.widget(0)
        )

        # setRowCount(0) шақыру ескі әрекет батырмалары виджетін
        # viewport-тан көрінбейтін түрде тастап кетеді, БІРАҚ Qt объект
        # ағашынан ешқашан өшірмейді (§ DataJournalPage._render_list()-те
        # расталған дәл осындай bug). Нақты өшіру үшін әр ескі виджетті
        # ЖОЛДАР қысқартылмас бұрын setParent(None) + deleteLater() арқылы
        # бөліп алу керек.
        last_column = len(_TABLE_HEADERS) - 1
        for row in range(self._table.rowCount()):
            old_widget = self._table.cellWidget(row, last_column)
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
            self._table.setColumnWidth(last_column, 200)

    def _populate_row(self, row_index: int, row: _ReviewRow) -> None:
        classroom_text = row.classroom.name if row.classroom is not None else _NO_VALUE_TEXT
        date_text = (
            row.progress.submitted_at.astimezone().strftime("%d.%m.%Y %H:%M")
            if row.progress.submitted_at is not None
            else _NO_VALUE_TEXT
        )
        score_text = (
            str(row.progress.teacher_score) if row.progress.teacher_score is not None else _NO_VALUE_TEXT
        )
        status_text = _STATUS_TEXT[row.progress.status]

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

        is_reviewed = row.progress.status is ProgressStatus.REVIEWED
        review_button = QPushButton(
            _ACTION_REVIEWED_TEXT if is_reviewed else _ACTION_PENDING_TEXT, action_widget
        )
        review_button.setEnabled(row.experiment.assessment is not None)
        review_button.clicked.connect(
            lambda _checked=False, r=row: self._on_open_feedback_clicked(r)
        )
        action_layout.addWidget(review_button)

        report_button = QPushButton(_OPEN_REPORT_TEXT, action_widget)
        report_button.setEnabled(row.experiment.report is not None)
        report_button.clicked.connect(
            lambda _checked=False, r=row: self._on_open_report_clicked(r)
        )
        action_layout.addWidget(report_button)

        self._table.setCellWidget(row_index, len(_TABLE_HEADERS) - 1, action_widget)

    # ---- Есеп/кері байланыс диалогтарын қайта пайдалану ----------------------

    def _build_session(self, session_id: str) -> ExperimentSession | None:
        summary = self._session_repository.get_session(session_id)
        if summary is None:
            return None
        measurements = self._session_repository.get_measurements(session_id)
        return ExperimentSession(
            id=summary.id, experiment_id=summary.experiment_id,
            started_at=summary.started_at, ended_at=summary.ended_at,
            measurements=list(measurements),
        )

    def _on_open_report_clicked(self, row: _ReviewRow) -> None:
        session_id = row.progress.latest_session_id
        if session_id is None:
            return
        session = self._build_session(session_id)
        if session is None:
            return
        report_data = build_experiment_report_data(row.experiment, session)
        feedback_result = self._feedback_repository.get_result(session_id)

        dialog = ExperimentReportDialog(
            row.experiment.title, row.experiment.guide, row.experiment.report, report_data,
            graph_pixmap=None, parent=self,
            automatic_conclusion=build_automatic_conclusion(report_data),
            assessment=row.experiment.assessment, feedback_result=feedback_result,
        )
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.finished.connect(self._on_report_dialog_finished)
        self._report_dialog = dialog
        dialog.show()

    def _on_report_dialog_finished(self) -> None:
        self._report_dialog = None

    def _on_open_feedback_clicked(self, row: _ReviewRow) -> None:
        session_id = row.progress.latest_session_id
        if session_id is None or row.experiment.assessment is None:
            return
        existing_result = self._feedback_repository.get_result(session_id)
        dialog = ExperimentFeedbackDialog(
            row.experiment.title, row.experiment.id, session_id, row.experiment.assessment,
            existing_result, UserRole.TEACHER, parent=self,
        )
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.finished.connect(self._on_feedback_dialog_finished)
        dialog.draft_saved.connect(self._on_feedback_draft_saved)
        dialog.submitted.connect(self._on_feedback_submitted)
        dialog.teacher_assessment_saved.connect(
            lambda assessment, sid=session_id, eid=row.experiment.id: self._on_feedback_teacher_assessment_saved(
                sid, eid, assessment
            )
        )
        self._feedback_dialog = dialog
        dialog.show()

    def _on_feedback_dialog_finished(self) -> None:
        self._feedback_dialog = None
        self._refresh()

    def _on_feedback_draft_saved(self, result: ExperimentFeedbackResult) -> None:
        self._feedback_repository.save_draft(result)

    def _on_feedback_submitted(self, result: ExperimentFeedbackResult) -> None:
        self._feedback_repository.save_submission(result)

    def _on_feedback_teacher_assessment_saved(
        self, session_id: str, experiment_id: str, teacher_assessment: TeacherAssessment
    ) -> None:
        self._feedback_repository.save_teacher_assessment(
            session_id, experiment_id, teacher_assessment, UserRole.TEACHER
        )
        self._refresh()
