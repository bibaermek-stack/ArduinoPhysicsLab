"""ClassroomMonitoringPage — "Сыныпты бақылау" беті (Phase 6: Teacher
Live Classroom Monitoring Dashboard).

Тек презентация — барлық агрегация ``domain/services/teacher_monitoring.
compute_classroom_monitoring()``-те (§ "Do not put complex aggregation
logic directly inside Qt widgets"). Бұл бет ЕШҚАШАН студенттің
құрылғысына/Arduino-ға тікелей қатынамайды — тек ЖЕРГІЛІКТІ, ӘЛДЕҚАШАН
синхрондалған SQLite жазбаларын оқиды (§ "CLOUD SYNC -> teacher local
SQLite -> repository/read model -> UI" архитектуралық ережесі).

Авторизация: ШЫНАЙЫ шекара сервер жағында (Phase 3, ӨЗГЕРТІЛМЕГЕН) —
мұғалімнің жергілікті SQLite файлында БАСҚА мұғалімнің деректері
ФИЗИКАЛЫҚ ЖОҚ (pull authorization). Бұл бет ҚОСЫМША, "defense in depth"
тексеруін де жасайды: сынып таңдағышы ТЕК ``classroom_repository.
list_active()``-тен (§ ``TeacherScopedClassroomRepository`` — ағымдағы
мұғалімнің тағайындалған сыныптарымен сүзілген) толтырылады, және
``on_enter(classroom_id=...)`` сол тізімде ЖОҚ id алса, ЕШБІР дерек
көрсетпей бос/таңдау күйіне қайтады (§ "must remain true even if local
UI filtering is bypassed").
"""

from __future__ import annotations

from datetime import datetime, timezone

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from domain.entities.experiment_definition import ExperimentDefinition
from domain.entities.monitoring_activity_state import MonitoringActivityState
from domain.entities.student_monitoring_snapshot import ClassroomMonitoringSnapshot, StudentMonitoringSnapshot
from domain.interfaces.i_classroom_repository import IClassroomRepository
from domain.interfaces.i_session_repository import ISessionRepository
from domain.interfaces.i_student_progress_repository import IStudentProgressRepository
from domain.interfaces.i_student_repository import IStudentRepository
from domain.services.teacher_monitoring import compute_classroom_monitoring
from modules.module_registry import ModuleRegistry
from ui.themes.theme_manager import COLOR_ERROR, COLOR_SUCCESS, COLOR_TEXT_MUTED, COLOR_WARNING
from ui.widgets.class_activity_carousel import classroom_accent_color

_PAGE_TITLE = "Сыныпты бақылау"
_NO_CLASSROOMS_TITLE = "Сізде әлі тағайындалған сынып жоқ"
_NO_STUDENTS_TITLE = "Бұл сыныпта оқушы жоқ"
_NO_FILTER_MATCH_TITLE = "Бұл сүзгіге сәйкес оқушы жоқ"
_TABLE_HEADERS = ("Оқушы", "Тәжірибе", "Күйі", "Өлшеу саны", "Соңғы мән", "Соңғы жаңарту")

_ACTIVITY_LABEL: dict[MonitoringActivityState, tuple[str, str]] = {
    MonitoringActivityState.NOT_STARTED: ("● Бастамады", COLOR_TEXT_MUTED),
    MonitoringActivityState.ACTIVE: ("● Тәжірибе жүріп жатыр", COLOR_SUCCESS),
    MonitoringActivityState.STALE: ("● Дерек күтілуде", COLOR_WARNING),
    MonitoringActivityState.OFFLINE: ("● Офлайн", COLOR_ERROR),
    MonitoringActivityState.COMPLETED: ("● Аяқталды", COLOR_SUCCESS),
}

_FILTER_ALL = "Барлығы"
_FILTER_ACTIVE = "Белсенді"
_FILTER_COMPLETED = "Аяқталған"
_FILTER_AWAITING = "Дерек күтілуде"
_FILTER_OPTIONS = (_FILTER_ALL, _FILTER_ACTIVE, _FILTER_COMPLETED, _FILTER_AWAITING)

# §13 "Sorting": белсенді -> назар аударуды қажет ету -> жақында
# аяқталған -> дерексіз/бастамаған. Санат ІШІНДЕ ЕҢ ЖАҢА белсенділік
# алдымен (§ ``last_update_at`` кему ретімен, ``None`` — соңында).
_SORT_RANK: dict[MonitoringActivityState, int] = {
    MonitoringActivityState.ACTIVE: 0,
    MonitoringActivityState.STALE: 1,
    MonitoringActivityState.OFFLINE: 1,
    MonitoringActivityState.COMPLETED: 2,
    MonitoringActivityState.NOT_STARTED: 3,
}


def _make_background_transparent(widget: QWidget) -> None:
    widget.setStyleSheet("background-color: transparent;")


def _sort_key(snapshot: StudentMonitoringSnapshot) -> tuple:
    rank = _SORT_RANK[snapshot.activity_state]
    recency = snapshot.last_update_at or datetime.min.replace(tzinfo=timezone.utc)
    return (rank, -recency.timestamp())


class ClassroomMonitoringPage(QWidget):
    student_selected = Signal(str, str)  # student_id, experiment_id
    back_requested = Signal()

    def __init__(
        self,
        classroom_repository: IClassroomRepository,
        student_repository: IStudentRepository,
        student_progress_repository: IStudentProgressRepository,
        session_repository: ISessionRepository,
        module_registry: ModuleRegistry,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._classroom_repository = classroom_repository
        self._student_repository = student_repository
        self._student_progress_repository = student_progress_repository
        self._session_repository = session_repository
        self._module_registry = module_registry
        self._current_classroom_id: str | None = None
        self._current_filter = _FILTER_ALL
        self._current_snapshot: ClassroomMonitoringSnapshot | None = None
        self._row_student_ids: list[tuple[str, str | None]] = []

        title_label = QLabel(_PAGE_TITLE, self)
        title_font = title_label.font()
        title_font.setBold(True)
        title_font.setPointSize(title_font.pointSize() + 4)
        title_label.setFont(title_font)

        back_button = QPushButton("← Бақылау тақтасына оралу", self)
        back_button.setObjectName("DashboardQuickActionButton")
        back_button.clicked.connect(self.back_requested.emit)

        top_row = QHBoxLayout()
        top_row.addWidget(title_label)
        top_row.addStretch(1)
        top_row.addWidget(back_button)

        self._classroom_list = QListWidget(self)
        self._classroom_list.setObjectName("ClassroomMonitoringPicker")
        self._classroom_list.setMaximumWidth(240)
        self._classroom_list.currentItemChanged.connect(self._on_classroom_picked)

        self._header_panel = self._build_header_panel()
        self._filter_combo = QComboBox(self)
        self._filter_combo.addItems(_FILTER_OPTIONS)
        self._filter_combo.currentTextChanged.connect(self._on_filter_changed)

        self._empty_label = QLabel("", self)
        self._empty_label.setProperty("role", "secondary")
        self._empty_label.setWordWrap(True)
        _make_background_transparent(self._empty_label)

        self._table = QTableWidget(0, len(_TABLE_HEADERS), self)
        self._table.setHorizontalHeaderLabels(_TABLE_HEADERS)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.cellDoubleClicked.connect(self._on_row_activated)

        right_column = QVBoxLayout()
        right_column.addWidget(self._header_panel)
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Сүзгі:", self))
        filter_row.addWidget(self._filter_combo)
        filter_row.addStretch(1)
        right_column.addLayout(filter_row)
        right_column.addWidget(self._empty_label)
        right_column.addWidget(self._table)

        body_row = QHBoxLayout()
        body_row.addWidget(self._classroom_list)
        body_row.addLayout(right_column, 1)

        layout = QVBoxLayout(self)
        layout.addLayout(top_row)
        layout.addLayout(body_row)

    # ---- Router интерфейсі --------------------------------------------------

    def on_enter(self, classroom_id: str | None = None) -> None:
        """§ "sticky last value" паттерні — ``MainWindow``-дың Phase 5
        auto-refresh choke point-ы ЕШБІР параметрсіз қайта шақырады
        (§ ``_refresh_current_page_if_data_dependent()``), сондықтан
        ``classroom_id=None`` "СОЛ сыныпты жаңарт" дегенді білдіреді.
        § "defense in depth" — жаңа ``classroom_id`` ЕҢ АЛДЫМЕН
        орнатылады, СОДАН КЕЙІН ``_reload_classroom_list()`` оны
        рұқсат етілген тізіммен тексереді/тазалайды (§ реттің
        МАҢЫЗДЫЛЫҒЫ — бұрын керісінше болып, тексеру үстінен
        жазылатын нақты қате табылды/түзетілді)."""
        if classroom_id is not None:
            self._current_classroom_id = classroom_id
        self._reload_classroom_list()
        self._select_classroom_in_list(self._current_classroom_id)
        self._refresh()

    # ---- Сынып таңдағышы ------------------------------------------------

    def _reload_classroom_list(self) -> None:
        self._classroom_list.blockSignals(True)
        self._classroom_list.clear()
        classrooms = self._classroom_repository.list_active()
        for classroom in classrooms:
            item = QListWidgetItem(classroom.name)
            item.setData(Qt.ItemDataRole.UserRole, classroom.id)
            item.setForeground(QColor(classroom_accent_color(classroom.id, classroom.name)))
            self._classroom_list.addItem(item)
        self._classroom_list.blockSignals(False)
        allowed_ids = {classroom.id for classroom in classrooms}
        # § "defense in depth" — рұқсат етілмеген/жойылған classroom_id
        # ЕШБІР дерек көрсетпей тазаланады.
        if self._current_classroom_id is not None and self._current_classroom_id not in allowed_ids:
            self._current_classroom_id = None
        if self._current_classroom_id is None and classrooms:
            self._current_classroom_id = classrooms[0].id

    def _select_classroom_in_list(self, classroom_id: str | None) -> None:
        for row in range(self._classroom_list.count()):
            item = self._classroom_list.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == classroom_id:
                self._classroom_list.blockSignals(True)
                self._classroom_list.setCurrentItem(item)
                self._classroom_list.blockSignals(False)
                return

    def _on_classroom_picked(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        if current is None:
            return
        self._current_classroom_id = current.data(Qt.ItemDataRole.UserRole)
        self._refresh()

    def _on_filter_changed(self, text: str) -> None:
        self._current_filter = text
        self._render_table()

    # ---- Тақырып панелі ---------------------------------------------------

    def _build_header_panel(self) -> QWidget:
        panel = QFrame(self)
        panel.setObjectName("DashboardPanel")

        self._classroom_name_label = QLabel("", panel)
        self._classroom_name_label.setProperty("role", "cardTitle")
        _make_background_transparent(self._classroom_name_label)

        self._summary_label = QLabel("", panel)
        self._summary_label.setProperty("role", "secondary")
        self._summary_label.setWordWrap(True)
        _make_background_transparent(self._summary_label)

        layout = QVBoxLayout(panel)
        layout.addWidget(self._classroom_name_label)
        layout.addWidget(self._summary_label)
        return panel

    # ---- Дерек жаңарту ------------------------------------------------------

    def _iter_catalog_experiments_by_id(self) -> dict[str, ExperimentDefinition]:
        experiments: dict[str, ExperimentDefinition] = {}
        for module in self._module_registry.get_all():
            for experiment in module.get_experiments():
                experiments[experiment.id] = experiment
        return experiments

    def _refresh(self) -> None:
        if self._current_classroom_id is None:
            self._current_snapshot = None
            self._classroom_name_label.setText("")
            self._summary_label.setText(_NO_CLASSROOMS_TITLE)
            self._table.setVisible(False)
            self._empty_label.setVisible(True)
            self._empty_label.setText(_NO_CLASSROOMS_TITLE)
            self._table.setRowCount(0)
            return

        snapshot = compute_classroom_monitoring(
            self._current_classroom_id,
            classroom_repository=self._classroom_repository,
            student_repository=self._student_repository,
            student_progress_repository=self._student_progress_repository,
            session_repository=self._session_repository,
            now=datetime.now(timezone.utc),
        )
        self._current_snapshot = snapshot
        if snapshot is None:
            self._classroom_name_label.setText("")
            self._summary_label.setText(_NO_CLASSROOMS_TITLE)
            self._table.setVisible(False)
            self._empty_label.setVisible(True)
            self._empty_label.setText(_NO_CLASSROOMS_TITLE)
            self._table.setRowCount(0)
            return

        self._classroom_name_label.setText(snapshot.classroom_name)
        self._summary_label.setText(
            f"Оқушылар: {snapshot.total_students}   Белсенді: {snapshot.active_count}   "
            f"Аяқталған: {snapshot.completed_count}   Назар аудару керек: {snapshot.needs_attention_count}"
        )
        self._render_table()

    def _filtered_students(self, snapshot: ClassroomMonitoringSnapshot) -> tuple[StudentMonitoringSnapshot, ...]:
        if self._current_filter == _FILTER_ALL:
            return snapshot.students
        if self._current_filter == _FILTER_ACTIVE:
            return tuple(s for s in snapshot.students if s.activity_state is MonitoringActivityState.ACTIVE)
        if self._current_filter == _FILTER_COMPLETED:
            return tuple(s for s in snapshot.students if s.activity_state is MonitoringActivityState.COMPLETED)
        if self._current_filter == _FILTER_AWAITING:
            return tuple(
                s
                for s in snapshot.students
                if s.activity_state in (MonitoringActivityState.STALE, MonitoringActivityState.OFFLINE)
            )
        return snapshot.students

    def _render_table(self) -> None:
        snapshot = self._current_snapshot
        if snapshot is None or snapshot.total_students == 0:
            self._table.setVisible(False)
            self._empty_label.setVisible(True)
            self._empty_label.setText(_NO_STUDENTS_TITLE)
            self._table.setRowCount(0)
            self._row_student_ids = []
            return

        students = sorted(self._filtered_students(snapshot), key=_sort_key)
        if not students:
            self._table.setVisible(False)
            self._empty_label.setVisible(True)
            self._empty_label.setText(_NO_FILTER_MATCH_TITLE)
            self._table.setRowCount(0)
            self._row_student_ids = []
            return

        self._empty_label.setVisible(False)
        self._table.setVisible(True)
        experiments_by_id = self._iter_catalog_experiments_by_id()
        self._table.setRowCount(len(students))
        self._row_student_ids = []
        for row_index, student in enumerate(students):
            self._populate_row(row_index, student, experiments_by_id)
            self._row_student_ids.append((student.student_id, student.experiment_id))
        self._table.resizeColumnsToContents()
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

    def _populate_row(
        self, row_index: int, student: StudentMonitoringSnapshot, experiments_by_id: dict[str, ExperimentDefinition]
    ) -> None:
        experiment = experiments_by_id.get(student.experiment_id) if student.experiment_id else None
        experiment_title = experiment.title if experiment is not None else "—"

        self._table.setItem(row_index, 0, QTableWidgetItem(student.student_name))
        self._table.setItem(row_index, 1, QTableWidgetItem(experiment_title))

        status_text, color_hex = _ACTIVITY_LABEL[student.activity_state]
        status_item = QTableWidgetItem(status_text)
        status_item.setForeground(QColor(color_hex))
        self._table.setItem(row_index, 2, status_item)

        self._table.setItem(row_index, 3, QTableWidgetItem(str(student.measurement_count)))

        values_text = _format_latest_values(student.latest_measurement_values, experiment)
        self._table.setItem(row_index, 4, QTableWidgetItem(values_text))

        update_text = _format_relative_time(student.last_update_at)
        self._table.setItem(row_index, 5, QTableWidgetItem(update_text))

    def _on_row_activated(self, row: int, _column: int) -> None:
        if row < 0 or row >= len(self._row_student_ids):
            return
        student_id, experiment_id = self._row_student_ids[row]
        if experiment_id is None:
            return  # § "Бастамады" қатары — ашатын тәжірибе жоқ
        self.student_selected.emit(student_id, experiment_id)


def _format_latest_values(values: dict[str, float], experiment: ExperimentDefinition | None) -> str:
    if not values:
        return "—"
    channel_map = {}
    if experiment is not None:
        channel_map = {channel.key: channel for channel in experiment.get_display_channels()}
    parts = []
    for key, value in values.items():
        channel = channel_map.get(key)
        if channel is not None:
            parts.append(f"{channel.display_name}: {value:.{channel.decimals}f} {channel.unit}")
        else:
            parts.append(f"{key}: {value:g}")
    return "   ".join(parts)


def _format_relative_time(timestamp: datetime | None) -> str:
    if timestamp is None:
        return "—"
    now = datetime.now(timezone.utc)
    age = now - timestamp
    seconds = max(0, int(age.total_seconds()))
    if seconds < 5:
        return "дәл қазір"
    if seconds < 60:
        return f"{seconds}с бұрын"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}мин бұрын"
    return timestamp.astimezone().strftime("%H:%M")
