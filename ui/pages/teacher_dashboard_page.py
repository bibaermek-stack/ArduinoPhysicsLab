"""TeacherDashboardPage — "Бақылау тақтасы" беті (Phase 39B; Phase 13
"Activity Carousel + Quick Actions + Recent Results", Мұғалім-тек).

Жоғарғы 4 карточка (Сыныптар саны/Оқушылар саны/Аяқталған жұмыстар/
Тексеруді күтуде) ӨЗГЕРІССІЗ (§ Phase 13 "KEEP the existing 4 summary
cards... Do not enlarge them") — толығымен ``IStudentProgressRepository.
compute_dashboard_counts()``-тен.

Phase 13-тегі 3 жаңа секция:
- "Бүгінгі белсенділік" — ``ClassActivityCarousel`` (§ ``compute_classroom_
  activity()`` — тек ЕҢ соңғы белсенді сыныптар, ешбір ойдан шығарылған
  дерек жоқ).
- "Жылдам әрекеттер" — ТЕК қолданыстағы Router/навигацияны шақыратын
  сигналдар (``classes_requested``/``labs_requested``/``devices_requested``),
  ешбір параллель бизнес-логика жоқ.
- "Соңғы нәтижелер" — ``list_submitted_progress()``-тен (FEEDBACK_SUBMITTED/
  REVIEWED), ``TeacherFeedbackReviewPage``-пен БІРДЕЙ оқушы/сынып/тәжірибе
  іздеу тәсілі, ЕҢ соңғы 6 жазба.

Бұл бет тек презентация/агрегация (§ "Do not put business logic directly
into the page") — барлық статус/прогресс есептеуі репозиторийде қалады.
"""

from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache

from PySide6.QtCore import QByteArray, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.resource_paths import resource_path
from domain.entities.experiment_definition import ExperimentDefinition
from domain.entities.learning_analytics import AlertKind, TeacherAlert
from domain.entities.student_experiment_progress import ProgressStatus, StudentExperimentProgress
from domain.interfaces.i_active_teacher_repository import IActiveTeacherRepository
from domain.interfaces.i_classroom_repository import IClassroomRepository
from domain.interfaces.i_student_progress_repository import IStudentProgressRepository
from domain.interfaces.i_student_repository import IStudentRepository
from domain.interfaces.i_teacher_repository import ITeacherRepository
from domain.services.learning_analytics import compute_teacher_alerts
from domain.services.teacher_scope import resolve_allowed_classroom_ids
from infrastructure.storage.sqlite_active_teacher_repository import SqliteActiveTeacherRepository
from infrastructure.storage.sqlite_teacher_repository import SqliteTeacherRepository
from modules.module_registry import ModuleRegistry
from ui.themes.theme_manager import COLOR_ERROR, COLOR_SUCCESS, COLOR_WARNING
from ui.widgets.class_activity_carousel import (
    ActivityCardData,
    ClassActivityCarousel,
    classroom_accent_color,
)

_PAGE_TITLE = "Бақылау тақтасы"

# Жоба Design/ каталогы project root-та ("ui/pages/../../Design") — ЕКІ
# деңгей ЖОҒАРЫ (§ sidebar.py-дегі parents[2]-мен БІРДЕЙ принцип, тек осы
# файлдың ui/pages/ ішінде жатқанын ескеретін тереңдік).
_ICON_DIR = resource_path("Design", "02_FluentIcons", "svg")
_ICON_RENDER_PX = 64
_QUICK_ACTION_ICON_PX = 16

_EMPTY_RESULTS_TITLE = "Әзірге нәтижелер жоқ"
_EMPTY_RESULTS_HINT = "Оқушылар зертханалық жұмыстарды аяқтағаннан кейін нәтижелер осы жерде көрінеді."
_RESULTS_TABLE_HEADERS = ("Оқушы", "Сынып", "Зертханалық жұмыс", "Уақыты", "Күйі")
_MAX_RECENT_RESULTS = 6

# ``TeacherFeedbackReviewPage._STATUS_TEXT``-пен БІРДЕЙ атаулар (§
# "reuse existing... terminology", терминологияны қайталап ойлап
# шығармау).
_RESULT_STATUS_TEXT: dict[ProgressStatus, str] = {
    ProgressStatus.FEEDBACK_SUBMITTED: "Тексеруді күтуде",
    ProgressStatus.REVIEWED: "Тексерілді",
}
# §14 "COLOR USAGE": Success — аяқталған/тексерілген, Warning — тексеруді
# күтуде. QTableWidgetItem QSS ``role`` property селекторын мұралай
# алмайды (QWidget ЕМЕС) — сондықтан түс ТІКЕЛЕЙ ThemeManager токенінен
# ``setForeground()`` арқылы қойылады (§ "Do not add arbitrary new hex
# colors in the page file" — екі мән де осы жердегі жалғыз, ТОКЕННЕН
# алынған import).
_RESULT_STATUS_COLOR: dict[ProgressStatus, str] = {
    ProgressStatus.FEEDBACK_SUBMITTED: COLOR_WARNING,
    ProgressStatus.REVIEWED: COLOR_SUCCESS,
}

# § Phase 8 (Advanced Analytics & Learning Progress) — "teacher dashboard
# alerts for incomplete or low-performing work" (§ Architecture Decision
# #5, ``compute_teacher_alerts()``). ``_RESULT_STATUS_*``-пен БІРДЕЙ
# конвенция: мәтін/түс тек осы файлда, ЕШБІР жаңа hex түс ойлап
# шығарылмайды (§ ``ui/themes/theme_manager.py`` токендері ғана).
_ALERT_KIND_TEXT: dict[AlertKind, str] = {
    AlertKind.OVERDUE: "Мерзімі өтті",
    AlertKind.LOW_SCORE: "Төмен баға",
    AlertKind.AWAITING_REVIEW_TOO_LONG: "Тексеру күтуде",
}
_ALERT_KIND_COLOR: dict[AlertKind, str] = {
    AlertKind.OVERDUE: COLOR_ERROR,
    AlertKind.LOW_SCORE: COLOR_ERROR,
    AlertKind.AWAITING_REVIEW_TOO_LONG: COLOR_WARNING,
}
_ALERTS_TABLE_HEADERS = ("Түрі", "Оқушы", "Сынып", "Хабарлама", "")
_ALERTS_ACTION_BUTTON_TEXT = "Қарау"
_EMPTY_ALERTS_TITLE = "Ескертулер жоқ"
_EMPTY_ALERTS_HINT = "Барлық жұмыстар уақтылы орындалуда және тексерілген."
_MAX_ALERTS = 8


@lru_cache(maxsize=None)
def _load_action_icon(svg_filename: str) -> QIcon:
    """Sidebar/graph toolbar-дегі icon loader-лармен БІРДЕЙ, бір pixmap-пен
    ``QIcon`` (§ live_graph._load_toolbar_icon — checked/selected күйі
    ЖОҚ, сондықтан екі-pixmap трюкі қажет емес)."""
    svg_bytes = (_ICON_DIR / svg_filename).read_bytes()
    icon = QIcon()
    icon.addPixmap(_render_svg_pixmap(svg_bytes), QIcon.Mode.Normal, QIcon.State.Off)
    return icon


def _make_background_transparent(widget: QWidget) -> None:
    """§ ``class_activity_carousel._make_background_transparent()``-мен
    БІРДЕЙ себеп/түзету — ``role``-негізді ``QLabel`` өз ЕНІНЕ (QVBoxLayout-
    та толық созылған) сай ``COLOR_BACKGROUND`` тіктөртбұрышын ақ
    ``DashboardPanel`` үстінде бояп кетеді. instance-деңгейлік
    ``setStyleSheet()`` ғана жұмыс істейді (эмпирикалық тексерілді,
    ``WA_StyledBackground`` бұл жағдайда ЕШБІР әсер етпейді)."""
    widget.setStyleSheet("background-color: transparent;")


def _render_svg_pixmap(svg_bytes: bytes) -> QPixmap:
    renderer = QSvgRenderer(QByteArray(svg_bytes))
    pixmap = QPixmap(_ICON_RENDER_PX, _ICON_RENDER_PX)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(_ICON_RENDER_PX / _QUICK_ACTION_ICON_PX)
    return pixmap


class TeacherDashboardPage(QWidget):
    classes_requested = Signal()
    labs_requested = Signal()
    devices_requested = Signal()
    results_requested = Signal()
    # § Phase 6 (Teacher Live Classroom Monitoring Dashboard): "Сыныпты
    # бақылау" жылдам әрекеті — ``ClassroomMonitoringPage``-ке ЕШБІР
    # алдын ала таңдалған classroom_id-сіз ашылады (§ бет ӨЗІ таңдағышты
    # көрсетеді).
    classroom_monitoring_requested = Signal()
    # § Phase 8 — ``AnalyticsPage.student_monitoring_requested``-пен ДӘЛ
    # БІРДЕЙ пішін (§ "reuse the existing student_monitoring route"),
    # ескерту қатарындағы "Қарау" батырмасынан шақырылады.
    student_monitoring_requested = Signal(str, str)  # student_id, experiment_id

    def __init__(
        self,
        student_progress_repository: IStudentProgressRepository,
        classroom_repository: IClassroomRepository,
        student_repository: IStudentRepository,
        module_registry: ModuleRegistry,
        teacher_repository: ITeacherRepository | None = None,
        active_teacher_repository: IActiveTeacherRepository | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._student_progress_repository = student_progress_repository
        self._classroom_repository = classroom_repository
        self._student_repository = student_repository
        self._module_registry = module_registry
        self._teacher_repository = teacher_repository or SqliteTeacherRepository()
        self._active_teacher_repository = (
            active_teacher_repository or SqliteActiveTeacherRepository()
        )
        self._value_labels: dict[str, QLabel] = {}
        self._alerts: tuple[TeacherAlert, ...] = ()

        title_label = QLabel(_PAGE_TITLE, self)
        title_font = title_label.font()
        title_font.setBold(True)
        title_font.setPointSize(title_font.pointSize() + 4)
        title_label.setFont(title_font)

        summary_row = QHBoxLayout()
        summary_row.addWidget(self._build_summary_card("classrooms", "Сыныптар саны"), 1)
        summary_row.addWidget(self._build_summary_card("students", "Оқушылар саны"), 1)
        summary_row.addWidget(self._build_summary_card("completed", "Аяқталған жұмыстар"), 1)
        summary_row.addWidget(self._build_summary_card("awaiting_review", "Тексеруді күтуде"), 1)

        middle_row = QHBoxLayout()
        middle_row.addWidget(self._build_activity_panel(), 3)
        middle_row.addWidget(self._build_quick_actions_panel(), 2)

        layout = QVBoxLayout(self)
        layout.addWidget(title_label)
        layout.addLayout(summary_row)
        layout.addLayout(middle_row)
        layout.addWidget(self._build_alerts_panel())
        layout.addWidget(self._build_recent_results_panel())
        layout.addStretch(1)

        self._refresh()

    # ---- Router интерфейсі ------------------------------------------------

    def on_enter(self) -> None:
        self._refresh()
        self._activity_carousel.start()

    def hideEvent(self, event) -> None:  # noqa: N802 (Qt override name)
        super().hideEvent(event)
        self._activity_carousel.stop()

    # ---- Summary карточкалары (§ "KEEP the existing 4 summary cards") -----

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

    # ---- "Бүгінгі белсенділік" ---------------------------------------------

    def _build_activity_panel(self) -> QWidget:
        panel = QFrame(self)
        panel.setObjectName("DashboardPanel")

        title_label = QLabel("Бүгінгі белсенділік", panel)
        title_label.setProperty("role", "cardTitle")
        _make_background_transparent(title_label)

        self._activity_carousel = ClassActivityCarousel(panel)
        self._activity_carousel.set_start_lab_callback(self.labs_requested.emit)

        layout = QVBoxLayout(panel)
        layout.addWidget(title_label)
        layout.addWidget(self._activity_carousel)
        return panel

    # ---- "Жылдам әрекеттер" ------------------------------------------------

    def _build_quick_actions_panel(self) -> QWidget:
        panel = QFrame(self)
        panel.setObjectName("DashboardPanel")

        title_label = QLabel("Жылдам әрекеттер", panel)
        title_label.setProperty("role", "cardTitle")
        _make_background_transparent(title_label)

        layout = QVBoxLayout(panel)
        layout.addWidget(title_label)
        layout.addWidget(
            self._build_quick_action_button(
                "Сынып құру", "ic_fluent_person_24_regular.svg", self.classes_requested
            )
        )
        layout.addWidget(
            self._build_quick_action_button(
                "Оқушы қосу", "ic_fluent_person_24_regular.svg", self.classes_requested
            )
        )
        layout.addWidget(
            self._build_quick_action_button(
                "Зертханалық жұмысты бастау", "ic_fluent_play_24_regular.svg", self.labs_requested
            )
        )
        layout.addWidget(
            self._build_quick_action_button(
                "Сыныпты бақылау", "ic_fluent_person_24_regular.svg", self.classroom_monitoring_requested
            )
        )
        layout.addWidget(
            self._build_quick_action_button(
                "Құрылғыны қосу", "ic_fluent_plug_connected_24_regular.svg", self.devices_requested
            )
        )
        layout.addStretch(1)
        return panel

    def _build_quick_action_button(self, text: str, icon_svg: str, signal) -> QPushButton:
        button = QPushButton(text, self)
        button.setObjectName("DashboardQuickActionButton")
        button.setIcon(_load_action_icon(icon_svg))
        button.setIconSize(QSize(_QUICK_ACTION_ICON_PX, _QUICK_ACTION_ICON_PX))
        button.clicked.connect(signal.emit)
        return button

    # ---- Phase 8: Ескертулер (teacher alerts) ------------------------------

    def _build_alerts_panel(self) -> QWidget:
        panel = QFrame(self)
        panel.setObjectName("DashboardPanel")

        title_label = QLabel("Ескертулер", panel)
        title_label.setProperty("role", "cardTitle")
        _make_background_transparent(title_label)

        self._alerts_empty_title_label = QLabel(_EMPTY_ALERTS_TITLE, panel)
        self._alerts_empty_title_label.setProperty("role", "cardTitle")
        _make_background_transparent(self._alerts_empty_title_label)
        self._alerts_empty_hint_label = QLabel(_EMPTY_ALERTS_HINT, panel)
        self._alerts_empty_hint_label.setProperty("role", "secondary")
        self._alerts_empty_hint_label.setWordWrap(True)
        _make_background_transparent(self._alerts_empty_hint_label)

        self._alerts_table = QTableWidget(0, len(_ALERTS_TABLE_HEADERS), panel)
        self._alerts_table.setHorizontalHeaderLabels(_ALERTS_TABLE_HEADERS)
        self._alerts_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._alerts_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._alerts_table.verticalHeader().setVisible(False)
        self._alerts_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

        layout = QVBoxLayout(panel)
        layout.addWidget(title_label)
        layout.addWidget(self._alerts_empty_title_label)
        layout.addWidget(self._alerts_empty_hint_label)
        layout.addWidget(self._alerts_table)
        return panel

    def _refresh_alerts(self) -> None:
        progress_list = self._student_progress_repository.list_all_progress(
            self._allowed_classroom_ids()
        )
        alerts = compute_teacher_alerts(
            progress_list,
            student_repository=self._student_repository,
            classroom_repository=self._classroom_repository,
            module_registry=self._module_registry,
            now=datetime.now(timezone.utc),
        )
        # § "most urgent first" — ``since`` жоқ (ешқашан болмауы тиіс, §
        # ``compute_teacher_alerts()`` докстрингі) ЕҢ ескі ретінде
        # қарастырылады, ЕШҚАШАН жалған "жаңа" деп фабрикацияланбайды.
        alerts = tuple(
            sorted(alerts, key=lambda a: a.since or datetime.min.replace(tzinfo=timezone.utc))
        )[:_MAX_ALERTS]
        self._alerts = alerts

        has_rows = len(alerts) > 0
        self._alerts_empty_title_label.setVisible(not has_rows)
        self._alerts_empty_hint_label.setVisible(not has_rows)
        self._alerts_table.setVisible(has_rows)

        # § ``AnalyticsPage._update_student_progress()``-пен БІРДЕЙ түзету
        # — cellWidget бар кестені қайта толтырғанда ЕСКІ виджеттер
        # қалмауы үшін ``clearContents()`` ЖАҢА ``setRowCount()``-тан
        # БҰРЫН шақырылады.
        self._alerts_table.clearContents()
        self._alerts_table.setRowCount(len(alerts))
        for row_index, alert in enumerate(alerts):
            self._populate_alert_row(row_index, alert)
        if has_rows:
            self._alerts_table.resizeColumnsToContents()
            self._alerts_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
            # § ``AnalyticsPage._update_student_progress()``-пен БІРДЕЙ
            # түзету — "Қарау" батырма мәтінінің қиылып қалуын болдырмау.
            action_column = len(_ALERTS_TABLE_HEADERS) - 1
            self._alerts_table.setColumnWidth(
                action_column, self._alerts_table.columnWidth(action_column) + 24
            )

    def _populate_alert_row(self, row_index: int, alert: TeacherAlert) -> None:
        kind_item = QTableWidgetItem(_ALERT_KIND_TEXT.get(alert.kind, "—"))
        color_hex = _ALERT_KIND_COLOR.get(alert.kind)
        if color_hex is not None:
            kind_item.setForeground(QColor(color_hex))
        self._alerts_table.setItem(row_index, 0, kind_item)
        self._alerts_table.setItem(row_index, 1, QTableWidgetItem(alert.student_name))
        self._alerts_table.setItem(row_index, 2, QTableWidgetItem(alert.classroom_name))
        self._alerts_table.setItem(row_index, 3, QTableWidgetItem(alert.message))

        action_button = QPushButton(_ALERTS_ACTION_BUTTON_TEXT, self._alerts_table)
        action_button.clicked.connect(
            lambda _checked=False, student_id=alert.student_id, experiment_id=alert.experiment_id: (
                self.student_monitoring_requested.emit(student_id, experiment_id)
            )
        )
        self._alerts_table.setCellWidget(row_index, 4, action_button)

    # ---- "Соңғы нәтижелер" --------------------------------------------------

    def _build_recent_results_panel(self) -> QWidget:
        panel = QFrame(self)
        panel.setObjectName("DashboardPanel")

        header_row = QHBoxLayout()
        title_label = QLabel("Соңғы нәтижелер", panel)
        title_label.setProperty("role", "cardTitle")
        _make_background_transparent(title_label)
        header_row.addWidget(title_label)
        header_row.addStretch(1)
        view_all_button = QPushButton("Барлық нәтижелерді көру →", panel)
        view_all_button.setObjectName("DashboardQuickActionButton")
        view_all_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        view_all_button.clicked.connect(self.results_requested.emit)
        header_row.addWidget(view_all_button)

        self._results_empty_title_label = QLabel(_EMPTY_RESULTS_TITLE, panel)
        self._results_empty_title_label.setProperty("role", "cardTitle")
        _make_background_transparent(self._results_empty_title_label)
        self._results_empty_hint_label = QLabel(_EMPTY_RESULTS_HINT, panel)
        self._results_empty_hint_label.setProperty("role", "secondary")
        self._results_empty_hint_label.setWordWrap(True)
        _make_background_transparent(self._results_empty_hint_label)

        self._results_table = QTableWidget(0, len(_RESULTS_TABLE_HEADERS), panel)
        self._results_table.setHorizontalHeaderLabels(_RESULTS_TABLE_HEADERS)
        self._results_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._results_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._results_table.verticalHeader().setVisible(False)
        self._results_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)

        layout = QVBoxLayout(panel)
        layout.addLayout(header_row)
        layout.addWidget(self._results_empty_title_label)
        layout.addWidget(self._results_empty_hint_label)
        layout.addWidget(self._results_table)
        return panel

    # ---- Ішкі логика ------------------------------------------------------

    def _iter_catalog_experiments_by_id(self) -> dict[str, ExperimentDefinition]:
        experiments: dict[str, ExperimentDefinition] = {}
        for module in self._module_registry.get_all():
            for experiment in module.get_experiments():
                experiments[experiment.id] = experiment
        return experiments

    def _allowed_classroom_ids(self) -> frozenset[str] | None:
        """§ Multi-Teacher Accounts §6 "Data Ownership / Filtering" —
        ``compute_dashboard_counts()``/``compute_classroom_activity()``/
        ``list_submitted_progress()`` ЕШБІР ``classroom_repository``
        консультация етпейтіндіктен (§ ``session_student_link`` тікелей
        сұралады), ағымдағы мұғалімнің тағайындалған сыныптарын ОСЫ
        жерде нақты есептеп, әр шақыруға беру керек."""
        return resolve_allowed_classroom_ids(self._teacher_repository, self._active_teacher_repository)

    def _refresh(self) -> None:
        allowed_classroom_ids = self._allowed_classroom_ids()
        counts = self._student_progress_repository.compute_dashboard_counts(allowed_classroom_ids)
        for key, label in self._value_labels.items():
            label.setText(str(counts.get(key, 0)))

        experiments_by_id = self._iter_catalog_experiments_by_id()
        self._refresh_activity(experiments_by_id)
        self._refresh_alerts()
        self._refresh_recent_results(experiments_by_id)

    def _refresh_activity(self, experiments_by_id: dict[str, ExperimentDefinition]) -> None:
        snapshots = self._student_progress_repository.compute_classroom_activity(
            self._allowed_classroom_ids()
        )
        cards: list[ActivityCardData] = []
        for snapshot in snapshots:
            experiment = experiments_by_id.get(snapshot.experiment_id)
            if experiment is None:
                continue
            label = (
                f"№{experiment.display_number}   {experiment.title}"
                if experiment.display_number is not None
                else experiment.title
            )
            cards.append(
                ActivityCardData(
                    classroom_name=snapshot.classroom_name,
                    experiment_label=label,
                    student_count=snapshot.student_count,
                    completed_count=snapshot.completed_count,
                    in_progress_count=snapshot.in_progress_count,
                    not_started_count=snapshot.not_started_count,
                    percentage=snapshot.completion_percentage,
                    accent_color=classroom_accent_color(snapshot.classroom_id, snapshot.classroom_name),
                )
            )
        self._activity_carousel.set_items(tuple(cards))

    def _refresh_recent_results(self, experiments_by_id: dict[str, ExperimentDefinition]) -> None:
        progress_list = self._student_progress_repository.list_submitted_progress(
            self._allowed_classroom_ids()
        )

        rows: list[tuple[StudentExperimentProgress, str, str, str]] = []
        for progress in progress_list:
            student = self._student_repository.get(progress.student_id)
            experiment = experiments_by_id.get(progress.experiment_id)
            if student is None or experiment is None:
                continue
            classroom = self._classroom_repository.get(student.classroom_id)
            classroom_name = classroom.name if classroom is not None else "—"
            rows.append((progress, student.display_name, classroom_name, experiment.title))

        rows.sort(key=lambda row: self._recency_key(row[0]), reverse=True)
        rows = rows[:_MAX_RECENT_RESULTS]

        has_rows = len(rows) > 0
        self._results_empty_title_label.setVisible(not has_rows)
        self._results_empty_hint_label.setVisible(not has_rows)
        self._results_table.setVisible(has_rows)

        self._results_table.setRowCount(len(rows))
        for row_index, (progress, student_name, classroom_name, experiment_title) in enumerate(rows):
            self._populate_result_row(row_index, progress, student_name, classroom_name, experiment_title)
        if has_rows:
            self._results_table.resizeColumnsToContents()
            self._results_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)

    @staticmethod
    def _recency_key(progress: StudentExperimentProgress) -> datetime:
        timestamp = progress.submitted_at or progress.last_activity_at
        return timestamp if timestamp is not None else datetime.min.replace(tzinfo=timezone.utc)

    def _populate_result_row(
        self,
        row_index: int,
        progress: StudentExperimentProgress,
        student_name: str,
        classroom_name: str,
        experiment_title: str,
    ) -> None:
        timestamp = progress.submitted_at or progress.last_activity_at
        time_text = timestamp.astimezone().strftime("%H:%M") if timestamp is not None else "—"

        self._results_table.setItem(row_index, 0, QTableWidgetItem(student_name))
        self._results_table.setItem(row_index, 1, QTableWidgetItem(classroom_name))
        self._results_table.setItem(row_index, 2, QTableWidgetItem(experiment_title))
        self._results_table.setItem(row_index, 3, QTableWidgetItem(time_text))

        status_text = _RESULT_STATUS_TEXT.get(progress.status, "—")
        status_item = QTableWidgetItem(status_text)
        color_hex = _RESULT_STATUS_COLOR.get(progress.status)
        if color_hex is not None:
            status_item.setForeground(QColor(color_hex))
        self._results_table.setItem(row_index, 4, status_item)
