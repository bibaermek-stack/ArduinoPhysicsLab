"""StudentMonitoringDetailPage — жеке оқушының тәжірибесін ашық көру
беті (Phase 6: Teacher Live Classroom Monitoring Dashboard §7 "Live
Student Experiment View").

Графикті ЕКІНШІ рет жасамайды — бұрыннан бар ``LiveGraphWidget``-ті
(§ ``ExperimentWorkspacePage``-пен БІРДЕЙ виджет) қайта пайдаланады.
Толық measurement тарихы ТЕК осы бет ашылғанда жүктеледі (§
``domain/services/teacher_monitoring.compute_student_monitoring_
detail()`` докстрингі — "classroom overview must not render every
historical raw measurement").

§8 "Live Graph Behavior": графикті ӘРБІР жаңартуда ТОЛЫҚ қайта құрмайды
— тек ЖАҢА (§ ``_appended_measurement_count``-тан кейінгі) measurement-
дерді қосады (``LiveGraphWidget.append_measurement()``), ол ӨЗІ
``sequence_no`` ретін сақтайды (§ ``get_measurements()`` ӘЛДЕҚАШАН
ретімен қайтарады) және дубликат нүктелерден қорғалған (§
``LiveGraphWidget._try_add_point()``-тегі ``_seen_points`` dedup).
Сессия/тәжірибе ӨЗГЕРСЕ ғана толық ``set_measurements()`` қайта құрылады.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from PySide6.QtCore import QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from domain.entities.experiment_definition import ExperimentDefinition
from domain.entities.experiment_session import ExperimentSession
from domain.entities.monitoring_activity_state import MonitoringActivityState
from domain.entities.sync_state import SyncState
from domain.entities.teacher_note import TeacherNote
from domain.entities.user_role import UserRole
from domain.interfaces.i_active_teacher_repository import IActiveTeacherRepository
from domain.interfaces.i_classroom_repository import IClassroomRepository
from domain.interfaces.i_session_repository import ISessionRepository
from domain.interfaces.i_student_progress_repository import IStudentProgressRepository
from domain.interfaces.i_student_repository import IStudentRepository
from domain.interfaces.i_teacher_note_repository import ITeacherNoteRepository
from domain.services.teacher_monitoring import compute_student_monitoring_detail
from modules.module_registry import ModuleRegistry
from ui.themes.theme_manager import COLOR_ERROR, COLOR_SUCCESS, COLOR_TEXT_MUTED, COLOR_WARNING
from ui.widgets.live_graph import LiveGraphWidget

_PAGE_TITLE_PREFIX = "Тәжірибені бақылау: "
_NO_EXPERIMENT_TITLE = "Тәжірибе табылмады"
_NO_MEASUREMENTS_TITLE = "Әзірге өлшеу деректері жоқ"
_HISTORY_BUTTON_TEXT = "Тәжірибе тарихы"
_NOTES_TITLE = "Мұғалім пікірі"
_MESSAGE_PLACEHOLDER = "Оқушыға қысқа хабарлама..."
_SEND_BUTTON_TEXT = "Жіберу"
_NO_NOTES_TEXT = "Әзірге пікір жіберілмеген."

_ACTIVITY_LABEL: dict[MonitoringActivityState, tuple[str, str]] = {
    MonitoringActivityState.NOT_STARTED: ("● Бастамады", COLOR_TEXT_MUTED),
    MonitoringActivityState.ACTIVE: ("● Тәжірибе жүріп жатыр", COLOR_SUCCESS),
    MonitoringActivityState.STALE: ("● Дерек күтілуде", COLOR_WARNING),
    MonitoringActivityState.OFFLINE: ("● Офлайн", COLOR_ERROR),
    MonitoringActivityState.COMPLETED: ("● Аяқталды", COLOR_SUCCESS),
}

# § "honest delivery state" (Phase 7 §"Delivery/read semantics") —
# ``SyncState`` тікелей қайта пайдаланылады (§ ``Student``/``Classroom``-
# мен БІРДЕЙ), ЖАЛҒАН "оқылды" күйі ЕШҚАШАН көрсетілмейді (§ docs/
# sync_architecture.md).
_DELIVERY_LABEL: dict[SyncState, tuple[str, str]] = {
    SyncState.PENDING_UPLOAD: ("Жіберілуде", COLOR_WARNING),
    SyncState.SYNCED: ("Жеткізілді", COLOR_SUCCESS),
}

# § "auto-refresh" — бұл бет ӨЗ БЕТІНШЕ желі сұрамайды (§14 "Do NOT
# create independent network polling inside each dashboard widget"),
# тек ЭЛАПСЕД УАҚЫТ көрсеткішін секунд сайын жаңартады (§ ExperimentWorkspacePage-
# тегі ``_elapsed_timer``-мен БІРДЕЙ презентация-ғана мақсат).
_ELAPSED_TIMER_INTERVAL_MS = 1000


def _make_background_transparent(widget: QWidget) -> None:
    widget.setStyleSheet("background-color: transparent;")


def _format_elapsed(started_at: datetime | None, ended_at: datetime | None) -> str:
    if started_at is None:
        return "—"
    end = ended_at or datetime.now(timezone.utc)
    total_seconds = max(0, int((end - started_at).total_seconds()))
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


class StudentMonitoringDetailPage(QWidget):
    back_requested = Signal()
    # § Phase 7 (Part C "Session History"): "Тәжірибе тарихы" батырмасы
    # — student_id ғана тасиды (§ ``DataJournalPage`` ӨЗІ сессия
    # тізімін/сүзгісін иеленеді, § ``MainWindow`` осыны "data_journal"
    # route-қа ``student_id=...`` арқылы аударады).
    session_history_requested = Signal(str)

    def __init__(
        self,
        student_repository: IStudentRepository,
        classroom_repository: IClassroomRepository,
        student_progress_repository: IStudentProgressRepository,
        session_repository: ISessionRepository,
        module_registry: ModuleRegistry,
        teacher_note_repository: ITeacherNoteRepository | None = None,
        active_teacher_repository: IActiveTeacherRepository | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._student_repository = student_repository
        self._classroom_repository = classroom_repository
        self._student_progress_repository = student_progress_repository
        self._session_repository = session_repository
        self._module_registry = module_registry
        self._teacher_note_repository = teacher_note_repository
        self._active_teacher_repository = active_teacher_repository
        self._current_student_id: str | None = None
        self._current_experiment_id: str | None = None
        self._shown_session_id: str | None = None
        self._appended_measurement_count = 0
        self._detail_started_at: datetime | None = None
        self._detail_ended_at: datetime | None = None

        back_button = QPushButton("← Сыныпқа оралу", self)
        back_button.setObjectName("DashboardQuickActionButton")
        back_button.clicked.connect(self.back_requested.emit)

        self._history_button = QPushButton(_HISTORY_BUTTON_TEXT, self)
        self._history_button.setObjectName("DashboardQuickActionButton")
        self._history_button.clicked.connect(self._on_history_clicked)

        self._title_label = QLabel("", self)
        title_font = self._title_label.font()
        title_font.setBold(True)
        title_font.setPointSize(title_font.pointSize() + 4)
        self._title_label.setFont(title_font)

        top_row = QHBoxLayout()
        top_row.addWidget(self._title_label)
        top_row.addStretch(1)
        top_row.addWidget(self._history_button)
        top_row.addWidget(back_button)

        self._header_panel = self._build_header_panel()

        self._empty_label = QLabel("", self)
        self._empty_label.setProperty("role", "secondary")
        self._empty_label.setWordWrap(True)
        _make_background_transparent(self._empty_label)

        self._live_graph = LiveGraphWidget(self)
        self._feedback_panel = self._build_feedback_panel()

        layout = QVBoxLayout(self)
        layout.addLayout(top_row)
        layout.addWidget(self._header_panel)
        layout.addWidget(self._empty_label)
        layout.addWidget(self._live_graph, 1)
        layout.addWidget(self._feedback_panel)

        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.setInterval(_ELAPSED_TIMER_INTERVAL_MS)
        self._elapsed_timer.timeout.connect(self._update_elapsed_label)

    # ---- Router интерфейсі --------------------------------------------------

    def on_enter(self, student_id: str | None = None, experiment_id: str | None = None) -> None:
        """§ "sticky last value" — ``MainWindow`` auto-refresh кезінде
        параметрсіз қайта шақырады."""
        if student_id is not None:
            self._current_student_id = student_id
        if experiment_id is not None:
            self._current_experiment_id = experiment_id
        self._refresh()

    def hideEvent(self, event) -> None:  # noqa: N802 (Qt override name)
        super().hideEvent(event)
        self._elapsed_timer.stop()

    # ---- Тақырып панелі ---------------------------------------------------

    def _build_header_panel(self) -> QWidget:
        panel = QFrame(self)
        panel.setObjectName("DashboardPanel")

        self._status_label = QLabel("", panel)
        self._status_label.setProperty("role", "cardTitle")
        _make_background_transparent(self._status_label)

        self._info_label = QLabel("", panel)
        self._info_label.setProperty("role", "secondary")
        self._info_label.setWordWrap(True)
        _make_background_transparent(self._info_label)

        self._elapsed_label = QLabel("", panel)
        self._elapsed_label.setProperty("role", "secondary")
        _make_background_transparent(self._elapsed_label)

        row = QHBoxLayout()
        row.addWidget(self._status_label)
        row.addStretch(1)
        row.addWidget(self._elapsed_label)

        layout = QVBoxLayout(panel)
        layout.addLayout(row)
        layout.addWidget(self._info_label)
        return panel

    # ---- Мұғалім пікірі панелі (Phase 7 Part A/B) --------------------------

    def _build_feedback_panel(self) -> QWidget:
        panel = QFrame(self)
        panel.setObjectName("DashboardPanel")

        title_label = QLabel(_NOTES_TITLE, panel)
        title_label.setProperty("role", "cardTitle")
        _make_background_transparent(title_label)

        self._message_edit = QLineEdit(panel)
        self._message_edit.setPlaceholderText(_MESSAGE_PLACEHOLDER)
        self._message_edit.returnPressed.connect(self._on_send_clicked)

        send_button = QPushButton(_SEND_BUTTON_TEXT, panel)
        send_button.clicked.connect(self._on_send_clicked)

        input_row = QHBoxLayout()
        input_row.addWidget(self._message_edit, 1)
        input_row.addWidget(send_button)

        self._notes_list = QListWidget(panel)
        self._notes_list.setObjectName("StudentMonitoringNotesList")
        # § "compact area", графикпен теңдей биіктік алмауы үшін —
        # ~4-5 жол көрінерлік тұрақты биіктік.
        self._notes_list.setMaximumHeight(140)

        layout = QVBoxLayout(panel)
        layout.addWidget(title_label)
        layout.addLayout(input_row)
        layout.addWidget(self._notes_list)
        return panel

    def _on_history_clicked(self) -> None:
        if self._current_student_id is None:
            return
        self.session_history_requested.emit(self._current_student_id)

    def _on_send_clicked(self) -> None:
        message = self._message_edit.text().strip()
        if not message or self._current_student_id is None:
            return
        if self._teacher_note_repository is None or self._active_teacher_repository is None:
            return
        teacher_context = self._active_teacher_repository.get()
        if teacher_context is None:
            return
        student = self._student_repository.get(self._current_student_id)
        if student is None:
            return
        note = TeacherNote(
            id=str(uuid.uuid4()),
            teacher_id=teacher_context.teacher_id,
            student_id=self._current_student_id,
            classroom_id=student.classroom_id,
            message=message,
            created_at=datetime.now(timezone.utc),
            experiment_id=self._current_experiment_id,
        )
        self._teacher_note_repository.create(note, UserRole.TEACHER)
        self._message_edit.clear()
        self._refresh_notes()

    def _refresh_notes(self) -> None:
        self._notes_list.clear()
        if self._teacher_note_repository is None or self._current_student_id is None:
            return
        notes = self._teacher_note_repository.list_for_student(self._current_student_id)
        if not notes:
            item = QListWidgetItem(_NO_NOTES_TEXT)
            item.setForeground(QColor(COLOR_TEXT_MUTED))
            self._notes_list.addItem(item)
            return
        # § "newest first" — соңғы жіберілген пікір ЖОҒАРЫда (§ мұғалім
        # ЕҢ АЛДЫМЕН соңғысын көру керек, ``list_for_student()`` ӨЗІ
        # ескіден жаңаға қайтарады).
        for note in reversed(notes):
            delivery_text, color_hex = _DELIVERY_LABEL.get(
                note.sync_state, ("Жіберілуде", COLOR_WARNING)
            )
            time_text = note.created_at.astimezone().strftime("%H:%M")
            item = QListWidgetItem(f"{time_text}   {note.message}   [{delivery_text}]")
            item.setForeground(QColor(color_hex))
            self._notes_list.addItem(item)

    # ---- Дерек жаңарту ------------------------------------------------------

    def _iter_catalog_experiments_by_id(self) -> dict[str, ExperimentDefinition]:
        experiments: dict[str, ExperimentDefinition] = {}
        for module in self._module_registry.get_all():
            for experiment in module.get_experiments():
                experiments[experiment.id] = experiment
        return experiments

    def _refresh(self) -> None:
        self._history_button.setEnabled(self._current_student_id is not None)
        self._refresh_notes()
        if self._current_student_id is None or self._current_experiment_id is None:
            self._show_empty(_NO_EXPERIMENT_TITLE)
            return

        detail = compute_student_monitoring_detail(
            self._current_student_id,
            self._current_experiment_id,
            student_repository=self._student_repository,
            classroom_repository=self._classroom_repository,
            student_progress_repository=self._student_progress_repository,
            session_repository=self._session_repository,
            now=datetime.now(timezone.utc),
        )
        if detail is None:
            self._show_empty(_NO_EXPERIMENT_TITLE)
            return

        experiment = self._iter_catalog_experiments_by_id().get(detail.experiment_id)
        experiment_title = experiment.title if experiment is not None else (detail.experiment_id or "—")
        self._title_label.setText(f"{_PAGE_TITLE_PREFIX}{detail.student_name}")

        status_text, color_hex = _ACTIVITY_LABEL[detail.activity_state]
        self._status_label.setText(status_text)
        self._status_label.setStyleSheet(f"color: {color_hex}; background-color: transparent;")

        started_text = detail.started_at.astimezone().strftime("%H:%M:%S") if detail.started_at else "—"
        self._info_label.setText(
            f"{detail.classroom_name}   •   {experiment_title}   •   Басталды: {started_text}   •   "
            f"Өлшеу саны: {detail.measurement_count}"
        )
        self._detail_started_at = detail.started_at
        self._detail_ended_at = detail.ended_at
        self._update_elapsed_label()
        if detail.activity_state is MonitoringActivityState.ACTIVE and detail.ended_at is None:
            self._elapsed_timer.start()
        else:
            self._elapsed_timer.stop()

        if not detail.measurements:
            self._show_empty(_NO_MEASUREMENTS_TITLE, keep_header=True)
            self._shown_session_id = detail.session_id
            self._appended_measurement_count = 0
            self._live_graph.clear()
            return

        self._empty_label.setVisible(False)
        self._live_graph.setVisible(True)

        if experiment is not None and detail.session_id != self._shown_session_id:
            self._live_graph.configure_channels(
                experiment.get_display_channels(),
                x_channel=experiment.graph_x_channel,
                y_channels=experiment.graph_y_channels or None,
                connect_points=experiment.graph_connect_points,
                show_fit=experiment.graph_show_fit,
            )
            self._shown_session_id = detail.session_id
            self._appended_measurement_count = 0

        if self._appended_measurement_count == 0:
            local_session = ExperimentSession(
                id=detail.session_id or "monitoring-session",
                experiment_id=detail.experiment_id or "",
                started_at=detail.started_at or datetime.now(timezone.utc),
                measurements=list(detail.measurements),
            )
            self._live_graph.set_measurements(local_session)
            self._appended_measurement_count = len(detail.measurements)
        elif len(detail.measurements) > self._appended_measurement_count:
            # § "avoid unnecessarily rebuilding a huge graph every 10
            # seconds" — тек ЖАҢА "құйрықты" қосады (§ ``get_measurements()``
            # ЄЛДЕҚАШАН ``sequence_no`` ретімен қайтарады, ешбір қайта
            # реттеу ЕШҚАШАН болмайды).
            for measurement in detail.measurements[self._appended_measurement_count :]:
                self._live_graph.append_measurement(measurement)
            self._appended_measurement_count = len(detail.measurements)

    def _update_elapsed_label(self) -> None:
        self._elapsed_label.setText(f"Өткен уақыт: {_format_elapsed(self._detail_started_at, self._detail_ended_at)}")

    def _show_empty(self, text: str, keep_header: bool = False) -> None:
        self._empty_label.setText(text)
        self._empty_label.setVisible(True)
        self._live_graph.setVisible(False)
        self._elapsed_timer.stop()
        if not keep_header:
            self._title_label.setText("")
            self._status_label.setText("")
            self._info_label.setText("")
