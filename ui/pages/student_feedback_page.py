"""StudentFeedbackPage — "Кері байланыс" беті (Phase 41, Оқушы-тек).

Бос хабарлама алмасу/чат ЕМЕС — тек ағымдағы белсенді оқушының НАҚТЫ
жіберілген (``FEEDBACK_SUBMITTED``/``REVIEWED``) зертханалық жұмыстары
бойынша мұғалімнің бағасы мен пікірінің күйін көрсетеді.
``TeacherFeedbackReviewPage``-тің кезек/сүзгі/сұрыптау үлгісін,
``StudentResultsPage``-тің белсенді оқушы/блокталған күй үлгісін қайта
пайдаланады. ``[Ашу]`` ``ExperimentReportDialog``-ты НАҚТЫ (стрипталмаған)
``teacher_assessment``-пен ашады — бұл беттің НАҚ мақсаты оқушыға
мұғалімнің шынайы бағасы мен пікірін көрсету (§ "show the real score,
show the real teacher comment"). Қауіпсіздік деректі жасыруда ЕМЕС,
``ExperimentReportDialog``-тың өз рөлге тәуелсіз, тек ОҚУ-режимдегі
рендеринг архитектурасында — мұғалім бағасын/пікірін өзгертетін ЕШБІР
контрол (``QSpinBox``/``QTextEdit``) бұл диалогта ешқашан құрылмайды (§
"Do not allow the student to modify the teacher's score, teacher
comment, or reviewed state").
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from domain.entities.experiment_definition import ExperimentDefinition
from domain.entities.experiment_session import ExperimentSession
from domain.entities.student_experiment_progress import ProgressStatus, StudentExperimentProgress
from domain.entities.user_role import UserRole
from domain.interfaces.i_active_student_repository import IActiveStudentRepository
from domain.interfaces.i_feedback_repository import IFeedbackRepository
from domain.interfaces.i_session_repository import ISessionRepository
from domain.interfaces.i_student_progress_repository import IStudentProgressRepository
from domain.interfaces.i_student_repository import IStudentRepository
from domain.interfaces.i_teacher_note_repository import ITeacherNoteRepository
from domain.services.experiment_conclusion import build_automatic_conclusion
from domain.services.experiment_report_data import build_experiment_report_data
from modules.module_registry import ModuleRegistry
from ui.themes.theme_manager import COLOR_TEXT_MUTED
from ui.widgets.experiment_report_dialog import ExperimentReportDialog
from ui.widgets.home_summary_card import HomeSummaryCard, make_background_transparent

_PAGE_TITLE = "Кері байланыс"
_PAGE_SUBTITLE = "Зертханалық жұмыстар бойынша мұғалімнің бағасы мен пікірін қарау."
# § Phase 7 (Teacher Actions, Feedback Delivery, and Session History) —
# мұғалімнің қысқа пікірлер лентасы (§ ``TeacherNote``, ЕСКІ ``experiment_
# feedback``-тен БӨЛЕК тұжырымдама, § ``domain/entities/teacher_note.py``
# докстрингі), осы бетке қосылды — ЖАҢА бет/route ЖОҚ (§ "smallest
# coherent UI addition", "this is teacher feedback, not WhatsApp").
_NOTES_TITLE = "Мұғалім пікірі"
_NO_NOTES_TEXT = "Әзірге мұғалім пікірі жоқ."

_NO_ACTIVE_STUDENT_TEXT = "Оқушы таңдалмаған.\nЖалғастыру үшін оқушыны таңдаңыз."
_SELECT_STUDENT_BUTTON_TEXT = "Оқушыны таңдау"

_EMPTY_NO_SUBMISSIONS_TITLE = "Жіберілген кері байланыс жоқ"
_EMPTY_NO_SUBMISSIONS_HINT = (
    "Зертханалық жұмыс бойынша кері байланысты жібергеннен кейін, ол осы жерде көрінеді."
)
_EMPTY_NO_MATCH_TITLE = "Сұраныс бойынша нәтиже табылмады"

_SEARCH_PLACEHOLDER_TEXT = "Тәжірибе, санат немесе күйі бойынша іздеу..."
_OPEN_TEXT = "Ашу"
_NO_VALUE_TEXT = "—"
_COMMENT_PREVIEW_MAX_LEN = 60

_TABLE_HEADERS = ("Тәжірибе", "Жіберілген күні", "Күйі", "Мұғалім бағасы", "Мұғалім пікірі", "")

_STATUS_TEXT: dict[ProgressStatus, str] = {
    ProgressStatus.FEEDBACK_SUBMITTED: "Тексеруді күтуде",
    ProgressStatus.REVIEWED: "Тексерілді",
}

_FILTER_ALL = "all"
_FILTER_WAITING = "waiting"
_FILTER_REVIEWED = "reviewed"
_STATUS_FILTER_OPTIONS: tuple[tuple[str, str], ...] = (
    (_FILTER_ALL, "Барлығы"),
    (_FILTER_WAITING, "Тексеруді күтуде"),
    (_FILTER_REVIEWED, "Тексерілді"),
)

_SORT_DATE_DESC = "date_desc"
_SORT_DATE_ASC = "date_asc"
_SORT_TITLE = "title"
_SORT_OPTIONS: tuple[tuple[str, str], ...] = (
    (_SORT_DATE_DESC, "Күні: жаңадан"),
    (_SORT_DATE_ASC, "Күні: ескіден"),
    (_SORT_TITLE, "Тәжірибе атауы"),
)


@dataclass(frozen=True)
class _FeedbackRow:
    experiment: ExperimentDefinition
    module_name: str
    progress: StudentExperimentProgress
    teacher_comment: str | None


class StudentFeedbackPage(QWidget):
    """Белсенді оқушының өз жіберілген кері байланысының күйін көрсететін
    бет — басқа оқушылардың/тексерілмеген/жобадағы жазбалар ЕШҚАШАН
    көрінбейді.
    """

    student_selection_requested = Signal()

    def __init__(
        self,
        active_student_repository: IActiveStudentRepository,
        student_repository: IStudentRepository,
        student_progress_repository: IStudentProgressRepository,
        feedback_repository: IFeedbackRepository,
        session_repository: ISessionRepository,
        module_registry: ModuleRegistry,
        teacher_note_repository: ITeacherNoteRepository | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._active_student_repository = active_student_repository
        self._student_repository = student_repository
        self._student_progress_repository = student_progress_repository
        self._feedback_repository = feedback_repository
        self._session_repository = session_repository
        self._module_registry = module_registry
        self._teacher_note_repository = teacher_note_repository
        self._value_labels: dict[str, QLabel] = {}
        self._all_rows: tuple[_FeedbackRow, ...] = ()
        self._report_dialog: ExperimentReportDialog | None = None

        self._stack = QStackedWidget(self)
        self._stack.addWidget(self._build_blocked_view())
        self._stack.addWidget(self._build_content_view())

        layout = QVBoxLayout(self)
        layout.addWidget(self._stack)

    # ---- Router интерфейсі ------------------------------------------------

    def on_enter(self) -> None:
        self._refresh()

    # ---- Блокталған күй -----------------------------------------------------

    def _build_blocked_view(self) -> QWidget:
        view = QWidget(self)
        # Phase 41: WorkspaceBackdrop су таңбасы осы (әдетте ЕҢ бос)
        # күйде көрінуі үшін ThemeManager-де нақты селектормен мөлдір
        # етілген (§ "StudentFeedbackPage's own inner QStackedWidget" —
        # ондағы child view-лер жалпы QStackedWidget ережесінен ТЫС,
        # жеке аттас селектор қажет).
        view.setObjectName("StudentFeedbackBlockedView")
        hint_label = QLabel(_NO_ACTIVE_STUDENT_TEXT, view)
        hint_label.setWordWrap(True)
        select_button = QPushButton(_SELECT_STUDENT_BUTTON_TEXT, view)
        select_button.clicked.connect(self.student_selection_requested.emit)

        layout = QVBoxLayout(view)
        layout.addStretch(1)
        layout.addWidget(hint_label)
        layout.addWidget(select_button)
        layout.addStretch(1)
        return view

    # ---- Мазмұн көрінісі -------------------------------------------------

    def _build_content_view(self) -> QWidget:
        view = QWidget(self)
        # Phase 41 background regression fix: _build_blocked_view()-тегі
        # ("StudentFeedbackBlockedView") бірдей уәжбен — бұл ІШКІ
        # QStackedWidget-тің child view-і де жеке, аттас объект-аты
        # арқылы мөлдір етілуі керек (§ ThemeManager).
        view.setObjectName("StudentFeedbackContentView")

        title_label = QLabel(_PAGE_TITLE, view)
        title_font = title_label.font()
        title_font.setBold(True)
        title_font.setPointSize(title_font.pointSize() + 4)
        title_label.setFont(title_font)

        subtitle_label = QLabel(_PAGE_SUBTITLE, view)
        subtitle_label.setProperty("role", "secondary")
        subtitle_label.setWordWrap(True)

        self._notes_panel = self._build_notes_panel(view)

        summary_row = QHBoxLayout()
        summary_row.addWidget(self._build_summary_card("total_submitted", "Барлығы жіберілген"), 1)
        summary_row.addWidget(self._build_summary_card("waiting", "Тексеруді күтуде"), 1)
        summary_row.addWidget(self._build_summary_card("reviewed", "Тексерілді"), 1)

        self._search_edit = QLineEdit(view)
        self._search_edit.setPlaceholderText(_SEARCH_PLACEHOLDER_TEXT)
        self._search_edit.textChanged.connect(self._on_filters_changed)

        self._status_filter_combo = QComboBox(view)
        for key, label in _STATUS_FILTER_OPTIONS:
            self._status_filter_combo.addItem(label, key)
        self._status_filter_combo.currentIndexChanged.connect(self._on_filters_changed)

        self._sort_combo = QComboBox(view)
        for key, label in _SORT_OPTIONS:
            self._sort_combo.addItem(label, key)
        self._sort_combo.currentIndexChanged.connect(self._on_filters_changed)

        controls_row = QHBoxLayout()
        controls_row.addWidget(self._search_edit, 1)
        controls_row.addWidget(QLabel("Күйі:", view))
        controls_row.addWidget(self._status_filter_combo)
        controls_row.addWidget(QLabel("Сұрыптау:", view))
        controls_row.addWidget(self._sort_combo)

        self._empty_state_title_label = QLabel(view)
        self._empty_state_title_label.setObjectName("WorkspaceEmptyStateLabel")
        empty_font = self._empty_state_title_label.font()
        empty_font.setBold(True)
        self._empty_state_title_label.setFont(empty_font)
        self._empty_state_hint_label = QLabel(view)
        self._empty_state_hint_label.setObjectName("WorkspaceEmptyStateLabel")
        self._empty_state_hint_label.setWordWrap(True)

        self._table = QTableWidget(0, len(_TABLE_HEADERS), view)
        self._table.setHorizontalHeaderLabels(list(_TABLE_HEADERS))
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.verticalHeader().setVisible(False)
        # Тек БІР баған Stretch режимінде — TeacherFeedbackReviewPage-дегі
        # дәлелденген конвенциямен бірдей (екі баған бірдей Stretch
        # болса, Qt-тың header layout-ы соңғы бағанды дұрыс созбай,
        # кестенің оң жағында бос ақ орын қалдыратыны расталды).
        # "Мұғалім пікірі" ұзын мәтінді сыйдыру үшін ең маңызды баған.
        self._table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)

        results_container = QWidget(view)
        results_container.setObjectName("StudentFeedbackResultsContainer")
        results_layout = QVBoxLayout(results_container)
        results_layout.setContentsMargins(0, 0, 0, 0)
        results_layout.addWidget(self._empty_state_title_label)
        results_layout.addWidget(self._empty_state_hint_label)
        results_layout.addWidget(self._table, 1)

        layout = QVBoxLayout(view)
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        layout.addWidget(self._notes_panel)
        layout.addLayout(summary_row)
        layout.addLayout(controls_row)
        layout.addWidget(results_container, 1)
        return view

    def _build_notes_panel(self, parent: QWidget) -> QWidget:
        panel = QFrame(parent)
        panel.setObjectName("HomeSummaryCard")

        title_label = QLabel(_NOTES_TITLE, panel)
        title_label.setProperty("role", "cardTitle")
        make_background_transparent(title_label)

        self._notes_list = QListWidget(panel)
        self._notes_list.setObjectName("StudentFeedbackNotesList")
        # § "compact area, no chat/messaging system" — тұрақты, шағын
        # биіктік (§ "the smallest coherent UI addition").
        self._notes_list.setMaximumHeight(120)

        layout = QVBoxLayout(panel)
        layout.addWidget(title_label)
        layout.addWidget(self._notes_list)
        return panel

    def _build_summary_card(self, key: str, label: str) -> QWidget:
        card = HomeSummaryCard(label, parent=self)
        self._value_labels[key] = card.value_label
        return card

    # ---- Дерек жинау/сүзгілеу/сұрыптау -----------------------------------

    def _iter_catalog_experiments_with_module(self) -> tuple[tuple[ExperimentDefinition, str], ...]:
        pairs: list[tuple[ExperimentDefinition, str]] = []
        for module in self._module_registry.get_all():
            for experiment in module.get_experiments():
                pairs.append((experiment, module.get_name()))
        return tuple(pairs)

    def _refresh(self) -> None:
        context = self._active_student_repository.get()
        if context is None:
            self._stack.setCurrentIndex(0)
            return
        student = self._student_repository.get(context.student_id)
        if student is None:
            self._stack.setCurrentIndex(0)
            return
        self._stack.setCurrentIndex(1)
        self._refresh_notes(student.id)

        rows: list[_FeedbackRow] = []
        for experiment, module_name in self._iter_catalog_experiments_with_module():
            progress = self._student_progress_repository.get_progress(student.id, experiment.id)
            if progress.status not in (ProgressStatus.FEEDBACK_SUBMITTED, ProgressStatus.REVIEWED):
                continue
            teacher_comment = self._resolve_teacher_comment(progress)
            rows.append(
                _FeedbackRow(
                    experiment=experiment,
                    module_name=module_name,
                    progress=progress,
                    teacher_comment=teacher_comment,
                )
            )
        self._all_rows = tuple(rows)

        self._update_summary_cards()
        self._render_table()

    # ---- Мұғалім пікірі лентасы (Phase 7 Part B) --------------------------

    def _refresh_notes(self, student_id: str) -> None:
        self._notes_list.clear()
        if self._teacher_note_repository is None:
            return
        notes = self._teacher_note_repository.list_for_student(student_id)
        if not notes:
            item = QListWidgetItem(_NO_NOTES_TEXT)
            item.setForeground(QColor(COLOR_TEXT_MUTED))
            self._notes_list.addItem(item)
            return
        # § "newest first" — соңғы пікір ЖОҒАРЫда.
        for note in reversed(notes):
            time_text = note.created_at.astimezone().strftime("%H:%M")
            item = QListWidgetItem(f"{time_text}   {note.message}")
            if note.read_at is None:
                bold_font = QFont(item.font())
                bold_font.setBold(True)
                item.setFont(bold_font)
            self._notes_list.addItem(item)
        # § "seen it" cadence — ешбір қосымша клик қажет ЕМЕС (§ "do not
        # interrupt with blocking modal dialogs"): панель көрсетілгеннен
        # кейін БАРЛЫҚ пікір жергілікті "оқылды" деп белгіленеді (§
        # ``mark_read()`` идемпотентті — әлдеқашан оқылған жазбаны
        # ЕШҚАШАН қайта жазбайды, § ХАЛАЛ "read_at" ешқашан синхрондалмайды).
        for note in notes:
            self._teacher_note_repository.mark_read(note.id, UserRole.STUDENT)

    def _resolve_teacher_comment(self, progress: StudentExperimentProgress) -> str | None:
        if progress.status is not ProgressStatus.REVIEWED or progress.latest_session_id is None:
            return None
        feedback_result = self._feedback_repository.get_result(progress.latest_session_id)
        if feedback_result is None or feedback_result.teacher_assessment is None:
            return None
        return feedback_result.teacher_assessment.comment

    def _update_summary_cards(self) -> None:
        total_submitted = len(self._all_rows)
        waiting = sum(1 for row in self._all_rows if row.progress.status is ProgressStatus.FEEDBACK_SUBMITTED)
        reviewed = sum(1 for row in self._all_rows if row.progress.status is ProgressStatus.REVIEWED)
        self._value_labels["total_submitted"].setText(str(total_submitted))
        self._value_labels["waiting"].setText(str(waiting))
        self._value_labels["reviewed"].setText(str(reviewed))

    def _filtered_sorted_rows(self) -> tuple[_FeedbackRow, ...]:
        status_key = self._status_filter_combo.currentData()
        query = self._search_edit.text().strip().lower()

        rows = list(self._all_rows)
        if status_key == _FILTER_WAITING:
            rows = [row for row in rows if row.progress.status is ProgressStatus.FEEDBACK_SUBMITTED]
        elif status_key == _FILTER_REVIEWED:
            rows = [row for row in rows if row.progress.status is ProgressStatus.REVIEWED]

        if query:
            rows = [row for row in rows if self._row_matches_query(row, query)]

        sort_key = self._sort_combo.currentData()
        if sort_key == _SORT_DATE_ASC:
            rows.sort(key=self._sort_date_key)
        elif sort_key == _SORT_TITLE:
            rows.sort(key=lambda row: row.experiment.title)
        else:
            rows.sort(key=self._sort_date_key, reverse=True)

        return tuple(rows)

    @staticmethod
    def _sort_date_key(row: _FeedbackRow):
        submitted_at = row.progress.submitted_at
        return submitted_at if submitted_at is not None else datetime.min.replace(tzinfo=timezone.utc)

    @staticmethod
    def _row_matches_query(row: _FeedbackRow, query: str) -> bool:
        status_text = _STATUS_TEXT[row.progress.status]
        haystacks = (row.experiment.title, row.module_name, status_text)
        return any(query in haystack.lower() for haystack in haystacks)

    def _on_filters_changed(self) -> None:
        self._render_table()

    def _render_table(self) -> None:
        has_any = len(self._all_rows) > 0
        rows = self._filtered_sorted_rows()
        show_table = len(rows) > 0

        if not has_any:
            empty_title, empty_hint = _EMPTY_NO_SUBMISSIONS_TITLE, _EMPTY_NO_SUBMISSIONS_HINT
        elif not show_table:
            empty_title, empty_hint = _EMPTY_NO_MATCH_TITLE, ""
        else:
            empty_title, empty_hint = "", ""

        self._empty_state_title_label.setText(empty_title)
        self._empty_state_title_label.setVisible(bool(empty_title))
        self._empty_state_hint_label.setText(empty_hint)
        self._empty_state_hint_label.setVisible(bool(empty_hint))
        self._search_edit.setVisible(has_any)
        self._status_filter_combo.setVisible(has_any)
        self._sort_combo.setVisible(has_any)
        self._table.setVisible(show_table)

        # setRowCount(0) ескі "Ашу" батырма виджеттерін viewport-тан
        # көрінбейтін түрде тастап кетеді, БІРАҚ Qt объект ағашынан
        # ешқашан өшірмейді (§ DataJournalPage._render_list()-те
        # расталған дәл осындай bug). Нақты өшіру үшін әр ескі виджетті
        # ЖОЛДАР қысқартылмас бұрын setParent(None) + deleteLater()
        # арқылы бөліп алу керек (бетке қайта кіргенде — Router.navigate()
        # әр рет on_enter() шақырады).
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
        self._table.resizeColumnsToContents()
        self._table.setColumnWidth(len(_TABLE_HEADERS) - 1, 90)

    def _populate_row(self, row_index: int, row: _FeedbackRow) -> None:
        date_text = (
            row.progress.submitted_at.astimezone().strftime("%d.%m.%Y")
            if row.progress.submitted_at is not None
            else _NO_VALUE_TEXT
        )
        status_text = _STATUS_TEXT[row.progress.status]
        score_text = (
            str(row.progress.teacher_score) if row.progress.teacher_score is not None else _NO_VALUE_TEXT
        )
        comment_text = self._comment_preview(row.teacher_comment)

        values = (row.experiment.title, date_text, status_text, score_text, comment_text)
        for column, text in enumerate(values):
            item = QTableWidgetItem(text)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(row_index, column, item)

        open_button = QPushButton(_OPEN_TEXT, self._table)
        open_button.setEnabled(row.progress.latest_session_id is not None and row.experiment.report is not None)
        open_button.clicked.connect(lambda _checked=False, r=row: self._on_open_clicked(r))
        self._table.setCellWidget(row_index, len(_TABLE_HEADERS) - 1, open_button)

    @staticmethod
    def _comment_preview(comment: str | None) -> str:
        if not comment:
            return _NO_VALUE_TEXT
        if len(comment) <= _COMMENT_PREVIEW_MAX_LEN:
            return comment
        return comment[:_COMMENT_PREVIEW_MAX_LEN].rstrip() + "…"

    # ---- Есеп диалогын Оқушы-қауіпсіз режимде қайта пайдалану ----------------

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

    def _on_open_clicked(self, row: _FeedbackRow) -> None:
        session_id = row.progress.latest_session_id
        if session_id is None:
            return
        session = self._build_session(session_id)
        if session is None:
            return
        report_data = build_experiment_report_data(row.experiment, session)

        # ЕСКЕРТУ: ``StudentResultsPage``-тен айырмашылығы — бұл бетте
        # ``teacher_assessment`` ӘДЕЙІ СТРИПТАЛМАЙДЫ. Дәл осы беттің
        # мақсаты — оқушыға НАҚТЫ мұғалім бағасы/пікірін көрсету (§ "For a
        # reviewed item: show the real score, show the real teacher
        # comment"). Қауіпсіздік ``build_student_safe_result()``-те ЕМЕС,
        # ``ExperimentReportDialog``-тың өз архитектурасында — ол рөлге
        # тәуелсіз, тек ОҚУ-режимдегі ``QLabel``-дар арқылы рендерлейді,
        # ЕШБІР score/comment-ті ӨЗГЕРТЕТІН контрол (``QSpinBox``/
        # ``QTextEdit``) мұнда ешқашан құрылмайды.
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
