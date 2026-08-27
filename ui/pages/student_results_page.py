"""StudentResultsPage — "Менің нәтижелерім" беті (Phase 39B, Оқушы-тек).

Тек ағымдағы белсенді оқушының өз нәтижелерін көрсетеді — Мұғалім бағасы
БАҒАНЫ мүлде жоқ (тек тексеру статусы), Phase 39A-дың "student reports
must not display teacher-only fields" ережесін жалғастырады.
``[Нәтижені ашу]`` ``ExperimentReportDialog``-ты
``build_student_safe_result()`` арқылы стрипталған кері байланыспен
қайта пайдаланады — ЕШБІР жаңа рендерлеу жүйесі жоқ.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
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
from domain.interfaces.i_active_student_repository import IActiveStudentRepository
from domain.interfaces.i_feedback_repository import IFeedbackRepository
from domain.interfaces.i_session_repository import ISessionRepository
from domain.interfaces.i_student_progress_repository import IStudentProgressRepository
from domain.interfaces.i_student_repository import IStudentRepository
from domain.services.experiment_conclusion import build_automatic_conclusion
from domain.services.experiment_feedback_service import build_student_safe_result
from domain.services.experiment_report_data import build_experiment_report_data
from modules.module_registry import ModuleRegistry
from ui.widgets.experiment_report_dialog import ExperimentReportDialog

_PAGE_TITLE = "Менің нәтижелерім"
_NO_ACTIVE_STUDENT_TEXT = (
    "Оқушы таңдалмаған.\nЖалғастыру үшін оқушыны таңдаңыз."
)
_SELECT_STUDENT_BUTTON_TEXT = "Оқушыны таңдау"
_TABLE_HEADERS = (
    "№", "Зертханалық жұмыс", "Күйі", "Тест нәтижесі", "Өзін-өзі бағалау", "Күні", "",
)
_OPEN_RESULT_TEXT = "Нәтижені ашу"
_NO_VALUE_TEXT = "—"

_STATUS_TEXT: dict[ProgressStatus, str] = {
    ProgressStatus.NOT_STARTED: "Басталмаған",
    ProgressStatus.IN_PROGRESS: "Өлшеу жүріп жатыр",
    ProgressStatus.MEASUREMENT_COMPLETED: "Өлшеу аяқталды",
    ProgressStatus.REPORT_COMPLETED: "Есеп ашылды",
    ProgressStatus.FEEDBACK_SUBMITTED: "Тексерілмеді",
    ProgressStatus.REVIEWED: "Тексерілді",
}


class StudentResultsPage(QWidget):
    """Белсенді оқушының өз прогресс тізімі — басқа оқушылар/ескі
    (тағайындалмаған) сессиялар ЕШҚАШАН көрінбейді.
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
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._active_student_repository = active_student_repository
        self._student_repository = student_repository
        self._student_progress_repository = student_progress_repository
        self._feedback_repository = feedback_repository
        self._session_repository = session_repository
        self._module_registry = module_registry
        self._report_dialog: ExperimentReportDialog | None = None

        self._stack = QStackedWidget(self)
        self._stack.addWidget(self._build_blocked_view())
        self._stack.addWidget(self._build_results_view())

        layout = QVBoxLayout(self)
        layout.addWidget(self._stack)

    # ---- Router интерфейсі ------------------------------------------------

    def on_enter(self) -> None:
        self._refresh()

    # ---- Блокталған күй -----------------------------------------------------

    def _build_blocked_view(self) -> QWidget:
        view = QWidget(self)
        # Phase 41: WorkspaceBackdrop су таңбасы осы (әдетте ЕҢ бос) күйде
        # көрінуі үшін ThemeManager-де нақты селектормен мөлдір етілген.
        view.setObjectName("StudentResultsBlockedView")
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

    # ---- Нәтижелер тізімі -----------------------------------------------------

    def _build_results_view(self) -> QWidget:
        view = QWidget(self)
        # Phase 41 background regression fix: _build_blocked_view()-тегі
        # ("StudentResultsBlockedView") бірдей уәжбен — бұл ІШКІ
        # QStackedWidget-тің child view-і де жеке, аттас объект-аты
        # арқылы мөлдір етілуі керек (§ ThemeManager).
        view.setObjectName("StudentResultsView")
        title_label = QLabel(_PAGE_TITLE, view)
        title_font = title_label.font()
        title_font.setBold(True)
        title_font.setPointSize(title_font.pointSize() + 4)
        title_label.setFont(title_font)

        self._active_student_label = QLabel(view)
        self._active_student_label.setProperty("role", "secondary")

        self._table = QTableWidget(0, len(_TABLE_HEADERS), view)
        self._table.setHorizontalHeaderLabels(list(_TABLE_HEADERS))
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        layout = QVBoxLayout(view)
        layout.addWidget(title_label)
        layout.addWidget(self._active_student_label)
        layout.addWidget(self._table, 1)
        return view

    # ---- Ішкі логика ------------------------------------------------------

    def _iter_catalog_experiments(self) -> tuple[ExperimentDefinition, ...]:
        experiments: list[ExperimentDefinition] = []
        for module in self._module_registry.get_all():
            experiments.extend(module.get_experiments())
        experiments.sort(key=lambda e: (e.display_number is None, e.display_number or 0))
        return tuple(experiments)

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
        self._active_student_label.setText(f"Оқушы: {student.display_name}")

        experiments = self._iter_catalog_experiments()
        progress_list = [
            self._student_progress_repository.get_progress(student.id, experiment.id)
            for experiment in experiments
        ]
        rows = [
            (experiment, progress)
            for experiment, progress in zip(experiments, progress_list)
            if progress.status is not ProgressStatus.NOT_STARTED
        ]

        # setRowCount(0) шақыру ескі "Нәтижені ашу" батырмаларын
        # viewport-тан көрінбейтін түрде тастап кетеді, БІРАҚ Qt объект
        # ағашынан ешқашан өшірмейді (§ DataJournalPage._render_list()-те
        # расталған дәл осындай bug). Нақты өшіру үшін әр ескі виджетті
        # ЖОЛДАР қысқартылмас бұрын setParent(None) + deleteLater() арқылы
        # бөліп алу керек (бетке қайта кіргенде — Router.navigate() әр рет
        # on_enter() шақырады).
        last_column = len(_TABLE_HEADERS) - 1
        for row in range(self._table.rowCount()):
            old_widget = self._table.cellWidget(row, last_column)
            if old_widget is not None:
                old_widget.setParent(None)
                old_widget.deleteLater()
        self._table.setRowCount(0)
        self._table.setRowCount(len(rows))
        for row, (experiment, progress) in enumerate(rows):
            self._populate_row(row, experiment, progress)
        self._table.resizeColumnsToContents()

    def _populate_row(
        self, row: int, experiment: ExperimentDefinition, progress: StudentExperimentProgress
    ) -> None:
        number_text = f"№{experiment.display_number}" if experiment.display_number is not None else _NO_VALUE_TEXT
        test_text = (
            f"{progress.level1_score}/{progress.level1_total} "
            f"({progress.level1_percentage:.0f}%)"
            if progress.level1_score is not None and progress.level1_total is not None
            else _NO_VALUE_TEXT
        )
        self_assessment_text = (
            str(progress.self_assessment) if progress.self_assessment is not None else _NO_VALUE_TEXT
        )
        date_text = (
            progress.last_activity_at.astimezone().strftime("%d.%m.%Y")
            if progress.last_activity_at is not None
            else _NO_VALUE_TEXT
        )
        status_text = _STATUS_TEXT[progress.status]

        values = (number_text, experiment.title, status_text, test_text, self_assessment_text, date_text)
        for column, text in enumerate(values):
            item = QTableWidgetItem(text)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(row, column, item)

        open_button = QPushButton(_OPEN_RESULT_TEXT, self._table)
        open_button.setEnabled(progress.latest_session_id is not None and experiment.report is not None)
        open_button.clicked.connect(
            lambda _checked=False, e=experiment, p=progress: self._on_open_result_clicked(e, p)
        )
        self._table.setCellWidget(row, len(_TABLE_HEADERS) - 1, open_button)

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

    def _on_open_result_clicked(
        self, experiment: ExperimentDefinition, progress: StudentExperimentProgress
    ) -> None:
        if progress.latest_session_id is None:
            return
        session = self._build_session(progress.latest_session_id)
        if session is None:
            return
        report_data = build_experiment_report_data(experiment, session)

        feedback_result = self._feedback_repository.get_result(progress.latest_session_id)
        if feedback_result is not None:
            feedback_result = build_student_safe_result(feedback_result)

        dialog = ExperimentReportDialog(
            experiment.title, experiment.guide, experiment.report, report_data,
            graph_pixmap=None, parent=self,
            automatic_conclusion=build_automatic_conclusion(report_data),
            assessment=experiment.assessment, feedback_result=feedback_result,
        )
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.finished.connect(self._on_report_dialog_finished)
        self._report_dialog = dialog
        dialog.show()

    def _on_report_dialog_finished(self) -> None:
        self._report_dialog = None
