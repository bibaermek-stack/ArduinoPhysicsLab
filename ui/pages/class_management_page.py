"""ClassManagementPage — "Сыныптар мен оқушылар" беті (Phase 39B,
Мұғалім-тек).

3-бағаналы layout: (1) сыныптар тізімі + қосу/өзгерту/мұрағаттау,
(2) таңдалған сыныптағы оқушылар + іздеу + қосу/өзгерту/мұрағаттау,
(3) таңдалған оқушының прогресс-шолуы + [Есепті ашу]/[Кері байланысты
ашу]/[Бағалау] әрекеттері.

Барлық CRUD ``IClassroomRepository``/``IStudentRepository`` арқылы (§
"Do not place SQL directly in UI widgets"). Есеп/кері байланыс диалогтары
``ExperimentReportDialog``/``ExperimentFeedbackDialog``-ты ӘРІ ҚАРАЙ
рендерлеу жүйесін ЕШБІР қайталамай қайта пайдаланады (§ "Do not create
duplicate report/feedback rendering systems") — тек осы беттің өз
персистенция-желімі (draft/submit/teacher_assessment сигналдарын
``IFeedbackRepository``-ге жазу) жаңа, себебі бұл ``ExperimentWorkspacePage``-
ден бөлек координатор контексі.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from uuid import uuid4

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
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
from domain.interfaces.i_classroom_repository import IClassroomRepository
from domain.interfaces.i_feedback_repository import IFeedbackRepository
from domain.interfaces.i_session_repository import ISessionRepository
from domain.interfaces.i_student_progress_repository import IStudentProgressRepository
from domain.interfaces.i_student_repository import IStudentRepository
from domain.services.experiment_conclusion import build_automatic_conclusion
from domain.services.experiment_report_data import build_experiment_report_data
from domain.services.student_access_code import generate_unique_student_code
from modules.module_registry import ModuleRegistry
from ui.themes.theme_manager import (
    COLOR_ACCENT,
    COLOR_BORDER_SUBTLE,
    COLOR_SUCCESS,
    COLOR_TEXT_MUTED,
    COLOR_WARNING,
)
from ui.widgets.class_activity_carousel import classroom_accent_color
from ui.widgets.experiment_feedback_dialog import ExperimentFeedbackDialog
from ui.widgets.experiment_report_dialog import ExperimentReportDialog

_PAGE_TITLE = "Сыныптар мен оқушылар"
_ADD_CLASSROOM_TEXT = "+ Сынып қосу"
_EDIT_TEXT = "Өзгерту"
_ARCHIVE_TEXT = "Мұрағаттау"
_RESTORE_TEXT = "Қалпына келтіру"
_ADD_STUDENT_TEXT = "+ Оқушы қосу"
_SEARCH_PLACEHOLDER_TEXT = "Іздеу..."
_OPEN_REPORT_TEXT = "Есепті ашу"
_OPEN_FEEDBACK_TEXT = "Кері байланысты ашу"
_GRADE_TEXT = "Бағалау"
_ARCHIVED_SUFFIX = " (мұрағатталған)"
_NO_SELECTION_HINT_TEXT = "Оқушыны таңдаңыз"

_REGENERATE_CODE_TITLE = "Жаңа кіру коды"
_REGENERATE_CODE_TEXT = "Жаңа кіру коды жасалсын ба? Ескі код енді жұмыс істемейді."
_REGENERATE_CODE_CONFIRM_BUTTON = "Жаңа код жасау"
_REGENERATE_CODE_CANCEL_BUTTON = "Болдырмау"


def confirm_regenerate_code(parent: QWidget) -> bool:
    """§ ``question_bank_page.confirm_delete()``-пен БІРДЕЙ тәсіл —
    ``QDialogButtonBox.StandardButton`` авто-мәтіні қазақшаға
    аударылмайды, сондықтан мәтіні НАҚТЫ көрсетілген жай батырмалар
    қолданылады."""
    box = QMessageBox(parent)
    box.setWindowTitle(_REGENERATE_CODE_TITLE)
    box.setText(_REGENERATE_CODE_TEXT)
    confirm_button = box.addButton(
        _REGENERATE_CODE_CONFIRM_BUTTON, QMessageBox.ButtonRole.DestructiveRole
    )
    cancel_button = box.addButton(_REGENERATE_CODE_CANCEL_BUTTON, QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(cancel_button)
    box.exec()
    return box.clickedButton() is confirm_button

_STATUS_TEXT: dict[ProgressStatus, str] = {
    ProgressStatus.NOT_STARTED: "Басталмаған",
    ProgressStatus.IN_PROGRESS: "Өлшеу жүріп жатыр",
    ProgressStatus.MEASUREMENT_COMPLETED: "Өлшеу аяқталды",
    ProgressStatus.REPORT_COMPLETED: "Есеп ашылды",
    ProgressStatus.FEEDBACK_SUBMITTED: "Кері байланыс жіберілді",
    ProgressStatus.REVIEWED: "Тексерілді",
}
# Phase 14 (§7 "LABORATORY PROGRESS TABLE"): ТЕК қолданбаның бар семантикалық
# токендері — ешбір жаңа/кездейсоқ түс ойлап шығарылмайды.
# FEEDBACK_SUBMITTED->WARNING/REVIEWED->SUCCESS TeacherDashboardPage._RESULT_
# STATUS_COLOR-мен ӘДЕЙІ БІРДЕЙ (§ "Do not invent a second completion
# definition" — қолданба бойынша БІР ғана статус-түс сөздігі рухы).
_STATUS_COLOR: dict[ProgressStatus, str] = {
    ProgressStatus.NOT_STARTED: COLOR_TEXT_MUTED,
    ProgressStatus.IN_PROGRESS: COLOR_ACCENT,
    ProgressStatus.MEASUREMENT_COMPLETED: COLOR_ACCENT,
    ProgressStatus.REPORT_COMPLETED: COLOR_ACCENT,
    ProgressStatus.FEEDBACK_SUBMITTED: COLOR_WARNING,
    ProgressStatus.REVIEWED: COLOR_SUCCESS,
}
_PROGRESS_TABLE_HEADERS = (
    "№", "Зертханалық жұмыс", "Күйі", "Соңғы күні", "Тест", "Өзін-өзі", "Мұғалім", "Тексеру", "",
)
_NO_VALUE_TEXT = "—"

_NO_CLASSROOMS_TEXT = "Сыныптар әлі қосылмаған"
_NO_STUDENTS_IN_CLASSROOM_TEXT = "Бұл сыныпта оқушылар жоқ"
_NO_SEARCH_RESULTS_TEXT = "Іздеу нәтижесі табылмады"


def _make_background_transparent(widget: QWidget) -> None:
    """§ ``teacher_dashboard_page._make_background_transparent()``-пен/
    ``class_activity_carousel``-мен БІРДЕЙ, эмпирикалық түрде расталған
    түзету (Phase 13) — ``role``-негізді/жай ``QLabel`` бос
    ``QWidget {{ background-color: COLOR_BACKGROUND }}`` ережесін өз
    енімен мұралайды, тізім жолындағы (``QListWidget`` selection-подсветка)
    итем-widget контейнерінде сұр тіктөртбұрыш ретінде көрінеді.
    ``WA_StyledBackground`` ЕШБІР әсер етпейді — тек instance-деңгейлік
    ``setStyleSheet()`` жұмыс істейді.
    """
    widget.setStyleSheet("background-color: transparent;")


def _tinted_rgba(accent_hex: str, alpha: int = 26) -> str:
    """§ Phase 13 ``_accent_tint()``-пен БІРДЕЙ рецепт — badge фоны үшін
    accent түсінің төмен-alpha rgba() нұсқасы."""
    color = QColor(accent_hex)
    return f"rgba({color.red()}, {color.green()}, {color.blue()}, {alpha})"


class _ClassroomRowWidget(QFrame):
    """Сыныптар тізіміндегі бір жол: [accent marker] атауы ... саны (§
    Phase 14 §2 "CLASSROOM LIST"). ``QListWidgetItem.setItemWidget()``
    арқылы қолданылады — АСТЫҢҒЫ ``QListWidgetItem.setText()`` де ПАРАЛЛЕЛЬ
    орнатылады (§ osы файлдың ӨЗІНДЕ), сондықтан тізімнің НАҚТЫ таңдау/
    CRUD механизмі (``currentItemChanged``, ``UserRole`` data) МҮЛДЕ
    өзгеріссіз қалады — тек көрнекі ұсыну қосымша қабат.
    """

    def __init__(self, name_text: str, student_count: int, accent_color: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        _make_background_transparent(self)

        self._marker = QFrame(self)
        self._marker.setFixedWidth(3)
        _make_background_transparent(self._marker)
        self._marker.setStyleSheet(f"background-color: {accent_color}; border: none;")

        self.name_label = QLabel(name_text, self)
        _make_background_transparent(self.name_label)

        self.count_label = QLabel(str(student_count), self)
        self.count_label.setProperty("role", "secondary")
        _make_background_transparent(self.count_label)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 8, 2)
        layout.addWidget(self._marker)
        layout.addSpacing(6)
        layout.addWidget(self.name_label, 1)
        layout.addWidget(self.count_label, 0, Qt.AlignmentFlag.AlignRight)

        self._accent_color = accent_color
        self.set_selected(False)

    def set_selected(self, selected: bool) -> None:
        """§ "Apply classroom accent subtly: selected classroom left
        marker - optionally selected classroom name/accent indicator" —
        marker ӘРҚАШАН accent-пен көрінеді (§ "8A must remain Amber
        here" — тұрақты сынып identity), тек аты ТЕК таңдалғанда
        accent-пен ерекшеленеді (§ "Selection must still follow the
        existing Fluent selection style" — негізгі selection ЖОҒАРЫДАН,
        list widget-тің ӨЗ ерекшелену түсімен, бұл ТЕК қосымша РЕҢК).
        """
        if selected:
            self.name_label.setStyleSheet(f"color: {self._accent_color}; background-color: transparent;")
        else:
            self.name_label.setStyleSheet("background-color: transparent;")


class _ClassroomFormDialog(QDialog):
    """Сынып қосу/өзгерту формасы — репозиторийге ЕШБІР жазба жасамайды,
    тек енгізілген мәндерді қайтарады (``get_values()``).
    """

    def __init__(self, existing: Classroom | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Сынып қосу" if existing is None else "Сыныпты өзгерту")

        self._name_edit = QLineEdit(existing.name if existing is not None else "", self)
        self._year_edit = QLineEdit(existing.academic_year if existing is not None else "", self)
        self._description_edit = QTextEdit(self)
        self._description_edit.setPlainText(existing.description if existing is not None else "")
        self._description_edit.setMinimumHeight(80)

        form = QFormLayout()
        form.addRow("Сынып атауы:", self._name_edit)
        form.addRow("Оқу жылы:", self._year_edit)
        form.addRow("Сипаттама:", self._description_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        buttons.accepted.connect(self._on_accept_clicked)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _on_accept_clicked(self) -> None:
        if not self._name_edit.text().strip():
            QMessageBox.warning(self, "Қате", "Сынып атауы бос болмауы керек")
            return
        self.accept()

    def get_values(self) -> tuple[str, str, str]:
        return (
            self._name_edit.text().strip(),
            self._year_edit.text().strip(),
            self._description_edit.toPlainText().strip(),
        )


class _StudentFormDialog(QDialog):
    """Оқушы қосу/өзгерту формасы — қайталама (белсенді) код тексеруі
    ЖОБА беруші (``code_conflict_checker``) арқылы, репозиторийге ЕШБІР
    тікелей қатынасы жоқ.
    """

    def __init__(
        self,
        code_conflict_checker,
        existing: Student | None = None,
        initial_code: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._code_conflict_checker = code_conflict_checker
        self.setWindowTitle("Оқушы қосу" if existing is None else "Оқушыны өзгерту")

        self._first_name_edit = QLineEdit(existing.first_name if existing is not None else "", self)
        self._last_name_edit = QLineEdit(existing.last_name if existing is not None else "", self)
        self._middle_name_edit = QLineEdit(existing.middle_name if existing is not None else "", self)
        self._code_edit = QLineEdit(
            existing.student_code if existing is not None else initial_code, self
        )
        self._notes_edit = QTextEdit(self)
        self._notes_edit.setPlainText(existing.notes if existing is not None else "")
        self._notes_edit.setMinimumHeight(60)

        form = QFormLayout()
        form.addRow("Аты:", self._first_name_edit)
        form.addRow("Тегі:", self._last_name_edit)
        form.addRow("Әкесінің аты:", self._middle_name_edit)
        form.addRow("Оқушы коды:", self._code_edit)
        form.addRow("Ескертпе:", self._notes_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        buttons.accepted.connect(self._on_accept_clicked)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _on_accept_clicked(self) -> None:
        if not self._first_name_edit.text().strip():
            QMessageBox.warning(self, "Қате", "Оқушының аты бос болмауы керек")
            return
        if not self._last_name_edit.text().strip():
            QMessageBox.warning(self, "Қате", "Оқушының тегі бос болмауы керек")
            return
        code = self._code_edit.text().strip()
        if code and self._code_conflict_checker(code):
            QMessageBox.warning(self, "Қате", "Бұл оқушы коды қолданыста")
            return
        self.accept()

    def get_values(self) -> tuple[str, str, str, str, str]:
        return (
            self._first_name_edit.text().strip(),
            self._last_name_edit.text().strip(),
            self._middle_name_edit.text().strip(),
            self._code_edit.text().strip(),
            self._notes_edit.toPlainText().strip(),
        )


class ClassManagementPage(QWidget):
    """Мұғалім-тек: сынып/оқушы CRUD + таңдалған оқушының зертханалық
    прогресс-шолуы.
    """

    def __init__(
        self,
        classroom_repository: IClassroomRepository,
        student_repository: IStudentRepository,
        student_progress_repository: IStudentProgressRepository,
        feedback_repository: IFeedbackRepository,
        session_repository: ISessionRepository,
        module_registry: ModuleRegistry,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._classroom_repository = classroom_repository
        self._student_repository = student_repository
        self._student_progress_repository = student_progress_repository
        self._feedback_repository = feedback_repository
        self._session_repository = session_repository
        self._module_registry = module_registry
        self._selected_classroom_id: str | None = None
        self._selected_student_id: str | None = None
        self._feedback_dialog: ExperimentFeedbackDialog | None = None
        self._report_dialog: ExperimentReportDialog | None = None

        title_label = QLabel(_PAGE_TITLE, self)
        title_font = title_label.font()
        title_font.setBold(True)
        title_font.setPointSize(title_font.pointSize() + 4)
        title_label.setFont(title_font)

        columns_layout = QHBoxLayout()
        columns_layout.addWidget(self._build_classroom_column(), 1)
        columns_layout.addWidget(self._build_student_column(), 1)
        columns_layout.addWidget(self._build_detail_column(), 2)

        layout = QVBoxLayout(self)
        layout.addWidget(title_label)
        layout.addLayout(columns_layout, 1)

        self._refresh_classrooms()

    # ---- Router интерфейсі ------------------------------------------------

    def on_enter(self) -> None:
        self._refresh_classrooms()

    # ---- Баған 1: сыныптар -------------------------------------------------

    def _build_classroom_column(self) -> QWidget:
        column = QWidget(self)
        self._classroom_header_label = QLabel("Сыныптар", column)
        self._classroom_empty_label = QLabel(_NO_CLASSROOMS_TEXT, column)
        self._classroom_empty_label.setProperty("role", "secondary")
        self._classroom_empty_label.setVisible(False)

        self._classroom_list = QListWidget(column)
        self._classroom_list.currentItemChanged.connect(self._on_classroom_selected)
        self._classroom_row_widgets: dict[str, _ClassroomRowWidget] = {}

        add_button = QPushButton(_ADD_CLASSROOM_TEXT, column)
        add_button.clicked.connect(self._on_add_classroom_clicked)
        self._edit_classroom_button = QPushButton(_EDIT_TEXT, column)
        self._edit_classroom_button.clicked.connect(self._on_edit_classroom_clicked)
        self._edit_classroom_button.setEnabled(False)
        self._archive_classroom_button = QPushButton(_ARCHIVE_TEXT, column)
        self._archive_classroom_button.clicked.connect(self._on_archive_classroom_clicked)
        self._archive_classroom_button.setEnabled(False)

        button_row = QHBoxLayout()
        button_row.addWidget(self._edit_classroom_button)
        button_row.addWidget(self._archive_classroom_button)

        layout = QVBoxLayout(column)
        layout.addWidget(self._classroom_header_label)
        layout.addWidget(self._classroom_empty_label)
        layout.addWidget(self._classroom_list, 1)
        layout.addWidget(add_button)
        layout.addLayout(button_row)
        return column

    def _refresh_classrooms(self) -> None:
        previous_id = self._selected_classroom_id
        self._classroom_list.clear()
        self._classroom_row_widgets = {}
        classrooms = self._classroom_repository.list_all()
        self._classroom_header_label.setText(f"Сыныптар · {len(classrooms)}")
        self._classroom_empty_label.setVisible(len(classrooms) == 0)
        self._classroom_list.setVisible(len(classrooms) > 0)

        for classroom in classrooms:
            text = classroom.name + (_ARCHIVED_SUFFIX if classroom.is_archived else "")
            item = QListWidgetItem()
            # МАҢЫЗДЫ: ``item.setText()`` ЕШҚАШАН шақырылмайды — эмпирикалық
            # түрде расталды, ``setItemWidget()`` итемнің ӨЗ мәтінін
            # ЖАСЫРМАЙДЫ (Qt бұл екеуін ҚАБАТТАП сызады), сондықтан
            # мәтінді ЕКІ РЕТ (item.text() + row_widget.name_label)
            # көрсетуге әкелер еді (скриншот аудитінде табылған регрессия).
            # Нақты көрсетілетін атау ТЕК ``row_widget.name_label``-де;
            # таңдау/CRUD ``UserRole`` data-мен өзгеріссіз жұмыс істейді.
            item.setData(Qt.ItemDataRole.UserRole, classroom.id)
            # § "The student count must come from real repository data" —
            # сыныптар саны әдетте аз (бірнеше ондаған), сондықтан әр
            # сыныпқа бір ``list_by_classroom()`` шақыруы қауіпсіз (§12
            # "Performance" — бұл N+1 ЕМЕС, тізім жаңарған сайын БІР рет
            # есептелетін O(сыныптар саны) операция, оқушы санына тәуелсіз).
            student_count = len(
                self._student_repository.list_by_classroom(classroom.id, include_archived=True)
            )
            accent = classroom_accent_color(classroom.id, classroom.name)
            row_widget = _ClassroomRowWidget(text, student_count, accent, self._classroom_list)
            item.setSizeHint(row_widget.sizeHint())
            self._classroom_list.addItem(item)
            self._classroom_list.setItemWidget(item, row_widget)
            self._classroom_row_widgets[classroom.id] = row_widget

        for row in range(self._classroom_list.count()):
            item = self._classroom_list.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == previous_id:
                self._classroom_list.setCurrentItem(item)
                return
        if self._classroom_list.count() > 0:
            self._classroom_list.setCurrentRow(0)
        else:
            self._selected_classroom_id = None
            self._update_classroom_button_states()
            self._refresh_students()

    def _on_classroom_selected(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        self._selected_classroom_id = current.data(Qt.ItemDataRole.UserRole) if current is not None else None
        for classroom_id, row_widget in self._classroom_row_widgets.items():
            row_widget.set_selected(classroom_id == self._selected_classroom_id)
        self._update_classroom_button_states()
        self._refresh_students()

    def _update_classroom_button_states(self) -> None:
        """§8 "ACTION BUTTONS": Edit/Archive — ешбір сынып таңдалмаса
        өшірулі."""
        has_selection = self._selected_classroom_id is not None
        self._edit_classroom_button.setEnabled(has_selection)
        self._archive_classroom_button.setEnabled(has_selection)

    def _on_add_classroom_clicked(self) -> None:
        dialog = _ClassroomFormDialog(parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name, academic_year, description = dialog.get_values()
        now = datetime.now(timezone.utc)
        classroom = Classroom(
            id=str(uuid4()), name=name, academic_year=academic_year, description=description,
            created_at=now, updated_at=now,
        )
        self._classroom_repository.create(classroom, UserRole.TEACHER)
        self._selected_classroom_id = classroom.id
        self._refresh_classrooms()

    def _on_edit_classroom_clicked(self) -> None:
        if self._selected_classroom_id is None:
            return
        existing = self._classroom_repository.get(self._selected_classroom_id)
        if existing is None:
            return
        dialog = _ClassroomFormDialog(existing=existing, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name, academic_year, description = dialog.get_values()
        updated = Classroom(
            id=existing.id, name=name, academic_year=academic_year, description=description,
            created_at=existing.created_at, updated_at=existing.updated_at,
            is_archived=existing.is_archived,
        )
        self._classroom_repository.update(updated, UserRole.TEACHER)
        self._refresh_classrooms()

    def _on_archive_classroom_clicked(self) -> None:
        if self._selected_classroom_id is None:
            return
        existing = self._classroom_repository.get(self._selected_classroom_id)
        if existing is None:
            return
        self._classroom_repository.archive(existing.id, UserRole.TEACHER, archived=not existing.is_archived)
        self._refresh_classrooms()

    # ---- Баған 2: оқушылар --------------------------------------------------

    def _build_student_column(self) -> QWidget:
        column = QWidget(self)
        self._student_header_label = QLabel("Оқушылар", column)
        self._search_edit = QLineEdit(column)
        self._search_edit.setPlaceholderText(_SEARCH_PLACEHOLDER_TEXT)
        self._search_edit.textChanged.connect(self._on_search_changed)

        self._student_empty_label = QLabel(column)
        self._student_empty_label.setProperty("role", "secondary")
        self._student_empty_label.setVisible(False)

        self._student_list = QListWidget(column)
        self._student_list.currentItemChanged.connect(self._on_student_selected)

        self._add_student_button = QPushButton(_ADD_STUDENT_TEXT, column)
        self._add_student_button.clicked.connect(self._on_add_student_clicked)
        self._add_student_button.setEnabled(False)
        self._edit_student_button = QPushButton(_EDIT_TEXT, column)
        self._edit_student_button.clicked.connect(self._on_edit_student_clicked)
        self._edit_student_button.setEnabled(False)
        self._archive_student_button = QPushButton(_ARCHIVE_TEXT, column)
        self._archive_student_button.clicked.connect(self._on_archive_student_clicked)
        self._archive_student_button.setEnabled(False)

        button_row = QHBoxLayout()
        button_row.addWidget(self._edit_student_button)
        button_row.addWidget(self._archive_student_button)

        layout = QVBoxLayout(column)
        layout.addWidget(self._student_header_label)
        layout.addWidget(self._search_edit)
        layout.addWidget(self._student_empty_label)
        layout.addWidget(self._student_list, 1)
        layout.addWidget(self._add_student_button)
        layout.addLayout(button_row)
        return column

    def _refresh_students(self) -> None:
        previous_id = self._selected_student_id
        self._student_list.clear()
        query = self._search_edit.text().strip()
        students: tuple[Student, ...] = ()
        if self._selected_classroom_id is not None:
            students = (
                self._student_repository.search(self._selected_classroom_id, query)
                if query
                else self._student_repository.list_by_classroom(
                    self._selected_classroom_id, include_archived=True
                )
            )
            for student in students:
                text = student.display_name + (_ARCHIVED_SUFFIX if student.is_archived else "")
                item = QListWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, student.id)
                self._student_list.addItem(item)

        self._student_header_label.setText(f"Оқушылар · {len(students)}")
        self._add_student_button.setEnabled(self._selected_classroom_id is not None)
        # §9 "EMPTY STATES" B/D: сынып бос ЕМЕС (§ таңдалған), бірақ
        # көрсетілетін тізім бос болса — себебі іздеу сұрауы бар/жоқ
        # екеніне қарай ажыратылады.
        is_empty = len(students) == 0 and self._selected_classroom_id is not None
        self._student_empty_label.setText(_NO_SEARCH_RESULTS_TEXT if query else _NO_STUDENTS_IN_CLASSROOM_TEXT)
        self._student_empty_label.setVisible(is_empty)
        self._student_list.setVisible(not is_empty)

        for row in range(self._student_list.count()):
            item = self._student_list.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == previous_id:
                self._student_list.setCurrentItem(item)
                return
        if self._student_list.count() > 0:
            self._student_list.setCurrentRow(0)
        else:
            self._selected_student_id = None
            self._update_student_button_states()
            self._refresh_details()

    def _on_search_changed(self, _text: str) -> None:
        self._refresh_students()

    def _update_student_button_states(self) -> None:
        """§8 "ACTION BUTTONS": Edit/Archive — ешбір оқушы таңдалмаса
        өшірулі (Add Student — ``_refresh_students()``-те, сынып
        таңдалуына тәуелді, ЕНДІ бөлек басқарылады)."""
        has_selection = self._selected_student_id is not None
        self._edit_student_button.setEnabled(has_selection)
        self._archive_student_button.setEnabled(has_selection)

    def _on_student_selected(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        self._selected_student_id = current.data(Qt.ItemDataRole.UserRole) if current is not None else None
        self._update_student_button_states()
        self._refresh_details()

    def _on_add_student_clicked(self) -> None:
        if self._selected_classroom_id is None:
            return
        # § "When a new student is created by a teacher, automatically
        # generate a unique access code" — диалог АЛДЫН АЛА толтырылған
        # кодпен ашылады (мұғалім қаласа, әлі де қолмен өзгерте алады —
        # § қолданыстағы код өрісінің функционалдығы сақталады).
        initial_code = generate_unique_student_code(self._student_repository)
        dialog = _StudentFormDialog(
            self._student_repository.code_exists, initial_code=initial_code, parent=self
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        first_name, last_name, middle_name, code, notes = dialog.get_values()
        now = datetime.now(timezone.utc)
        student = Student(
            id=str(uuid4()), classroom_id=self._selected_classroom_id,
            first_name=first_name, last_name=last_name, created_at=now, updated_at=now,
            middle_name=middle_name, student_code=code, notes=notes,
        )
        self._student_repository.create(student, UserRole.TEACHER)
        self._selected_student_id = student.id
        self._refresh_students()

    def _on_edit_student_clicked(self) -> None:
        if self._selected_student_id is None:
            return
        existing = self._student_repository.get(self._selected_student_id)
        if existing is None:
            return
        checker = lambda code: self._student_repository.code_exists(code, exclude_student_id=existing.id)
        dialog = _StudentFormDialog(checker, existing=existing, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        first_name, last_name, middle_name, code, notes = dialog.get_values()
        updated = Student(
            id=existing.id, classroom_id=existing.classroom_id,
            first_name=first_name, last_name=last_name,
            created_at=existing.created_at, updated_at=existing.updated_at,
            middle_name=middle_name, student_code=code, notes=notes,
            is_archived=existing.is_archived,
        )
        self._student_repository.update(updated, UserRole.TEACHER)
        self._refresh_students()

    def _on_archive_student_clicked(self) -> None:
        if self._selected_student_id is None:
            return
        existing = self._student_repository.get(self._selected_student_id)
        if existing is None:
            return
        self._student_repository.archive(existing.id, UserRole.TEACHER, archived=not existing.is_archived)
        self._refresh_students()

    def _on_copy_code_clicked(self) -> None:
        if self._selected_student_id is None:
            return
        student = self._student_repository.get(self._selected_student_id)
        if student is None or not student.student_code:
            return
        QApplication.clipboard().setText(student.student_code)

    def _on_regenerate_code_clicked(self) -> None:
        """§7 "Optionally: Жаңа код жасау... old code must stop working,
        new code persists, require a small confirmation dialog" — ескі
        код жай ғана ЖАҢА кодпен ауыстырылады (§ ``update()``), сондықтан
        ескі код автоматты түрде енді ешбір оқушыға сәйкес келмейді
        (``get_by_code()`` оны ЕШҚАШАН таппайды)."""
        if self._selected_student_id is None:
            return
        student = self._student_repository.get(self._selected_student_id)
        if student is None:
            return
        if not confirm_regenerate_code(self):
            return
        new_code = generate_unique_student_code(self._student_repository)
        updated = replace(
            student, student_code=new_code, updated_at=datetime.now(timezone.utc)
        )
        self._student_repository.update(updated, UserRole.TEACHER)
        self._refresh_details()

    # ---- Баған 3: прогресс-шолу ---------------------------------------------

    def _build_detail_column(self) -> QWidget:
        column = QWidget(self)

        self._detail_hint_label = QLabel(_NO_SELECTION_HINT_TEXT, column)
        self._detail_hint_label.setProperty("role", "secondary")

        self._student_name_label = QLabel(column)
        name_font = self._student_name_label.font()
        name_font.setBold(True)
        name_font.setPointSize(name_font.pointSize() + 2)
        self._student_name_label.setFont(name_font)

        # §4 "SELECTED STUDENT HEADER": сынып badge-і (тонирленген фон +
        # accent мәтін) — Phase 13 ``classroom_accent_color()``-мен БІРДЕЙ,
        # ЕШБІР жаңа color mapping жүйесі жоқ.
        self._classroom_name_label = QLabel(column)

        # Mode Switch + Student Access Screen Redesign §7: таңдалған
        # оқушының кіру коды — ықшам, тек детальды аймақта (§ "Do not
        # clutter the student list rows with long codes").
        self._student_code_label = QLabel(column)
        self._student_code_label.setProperty("role", "secondary")
        self._copy_code_button = QPushButton("Кодты көшіру", column)
        self._copy_code_button.setObjectName("HomeModuleCardAction")
        self._copy_code_button.clicked.connect(self._on_copy_code_clicked)
        self._regenerate_code_button = QPushButton("Жаңа код жасау", column)
        self._regenerate_code_button.setObjectName("HomeModuleCardAction")
        self._regenerate_code_button.clicked.connect(self._on_regenerate_code_clicked)
        code_row = QHBoxLayout()
        code_row.addWidget(self._student_code_label)
        code_row.addWidget(self._copy_code_button)
        code_row.addWidget(self._regenerate_code_button)
        code_row.addStretch(1)

        # §5 "STUDENT PROGRESS SUMMARY": ықшам 4 stat cell.
        self._stat_value_labels: dict[str, QLabel] = {}
        stats_row = QHBoxLayout()
        stats_row.addWidget(self._build_progress_stat("total", "Барлығы"))
        stats_row.addWidget(self._build_progress_stat("completed", "Аяқталған"))
        stats_row.addWidget(self._build_progress_stat("in_progress", "Орындауда"))
        stats_row.addWidget(self._build_progress_stat("not_started", "Басталмаған"))
        stats_row.addStretch(1)

        self._review_counts_label = QLabel(column)
        self._review_counts_label.setProperty("role", "secondary")
        # §13 "GEOMETRY SAFETY": wordWrap МІНДЕТТІ — ЕШБІР QLabel wordWrap
        # ЖОҚ кезде өз толық (бір жолдық) мәтін енін auto minimumSizeHint
        # ретінде бүкіл баған тізбегіне (§ QVBoxLayout) таратады, бұл 1366px-де
        # sidebar-ды МІНДЕТТІ ені (230px) астына сығып шығаратыны эмпирикалық
        # түрде расталды (регрессия, скриншот/геометрия аудитінде табылды).
        self._review_counts_label.setWordWrap(True)

        # §6 "OVERALL PROGRESS BAR".
        progress_header_row = QHBoxLayout()
        progress_header_row.addWidget(QLabel("Жалпы прогресс", column))
        progress_header_row.addStretch(1)
        self._overall_progress_percentage_label = QLabel("0%", column)
        progress_header_row.addWidget(self._overall_progress_percentage_label)

        self._overall_progress_bar = QProgressBar(column)
        # § "DashboardActivityBar" (Phase 13) — жіңішке, Fluent-стильді
        # прогресс жолағы QSS-і ҚАЙТА пайдаланылады (§11 "no duplicated
        # color mapping/architecture churn" рухы — жаңа QSS ойлап
        # шығармау).
        self._overall_progress_bar.setObjectName("DashboardActivityBar")
        self._overall_progress_bar.setRange(0, 100)
        self._overall_progress_bar.setTextVisible(False)
        self._overall_progress_bar.setFixedHeight(8)

        self._progress_empty_label = QLabel("Прогресс жазбалары жоқ", column)
        self._progress_empty_label.setProperty("role", "secondary")
        self._progress_empty_label.setVisible(False)

        self._progress_table = QTableWidget(0, len(_PROGRESS_TABLE_HEADERS), column)
        self._progress_table.setHorizontalHeaderLabels(list(_PROGRESS_TABLE_HEADERS))
        self._progress_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._progress_table.verticalHeader().setVisible(False)
        self._progress_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        layout = QVBoxLayout(column)
        layout.addWidget(self._detail_hint_label)
        layout.addWidget(self._student_name_label)
        # § "no saturated solid fill" / badge ықшам болуы тиіс — ЕШБІР
        # size policy hack ЕМЕС (§ "Ignored"-тен алынған сабақ),
        # ``addWidget(..., alignment=AlignLeft)`` layout-қа виджетті ӨЗ
        # sizeHint-іне сай, толық жолды ЕМЕС, солға туралап орналастыруды
        # айтады — badge ешқашан бүкіл баған енін толтырмайды.
        layout.addWidget(self._classroom_name_label, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addSpacing(4)
        layout.addLayout(code_row)
        layout.addSpacing(4)
        layout.addLayout(stats_row)
        layout.addWidget(self._review_counts_label)
        layout.addSpacing(2)
        layout.addLayout(progress_header_row)
        layout.addWidget(self._overall_progress_bar)
        layout.addSpacing(4)
        layout.addWidget(self._progress_empty_label)
        layout.addWidget(self._progress_table, 1)
        return column

    def _build_progress_stat(self, key: str, caption: str) -> QWidget:
        container = QWidget(self)
        value_label = QLabel("0", container)
        value_label.setProperty("role", "cardValue")
        self._stat_value_labels[key] = value_label
        caption_label = QLabel(caption, container)
        caption_label.setProperty("role", "cardLabel")
        # §13 "GEOMETRY SAFETY": каптиондар ("Басталмаған" сияқты бір
        # ұзын сөз, wordWrap көмектеспейді) — ЕШБІР wordWrap ЖОҚ QLabel
        # өз ТОЛЫҚ мәтін енін minimumSizeHint ретінде ата-тек layout-қа
        # (4 cell қосындысы) таратып, 1366px-де sidebar-ды 230px-тен
        # 210px-ке дейін сығып шығаратыны эмпирикалық түрде расталды
        # (регрессия). ЕСКЕРТУ: ``setMinimumWidth(0)`` ЕШБІР әсер
        # етпейді — Qt мұны ``QSize.isEmpty()`` ретінде қарап, ӨЗ
        # minimumSizeHint()-іне қайта оралады (эмпирикалық түрде
        # табылды); "1" (нөл ЕМЕС) мән ғана нақты қолданылады. Бұл ТЕК
        # ҚАТАҢ ЕДӘУІР (floor) шектеуін алып тастайды — preferred-size
        # негізді ҚАЛЫПТЫ layout бөлу мінез-құлқына тимейді, сондықтан
        # жеткілікті орын болғанда мәтін толық көрінеді.
        caption_label.setMinimumWidth(1)
        col = QVBoxLayout(container)
        col.setContentsMargins(0, 0, 12, 0)
        col.addWidget(value_label)
        col.addWidget(caption_label)
        return container

    def _iter_catalog_experiments(self) -> tuple[ExperimentDefinition, ...]:
        experiments: list[ExperimentDefinition] = []
        for module in self._module_registry.get_all():
            experiments.extend(module.get_experiments())
        experiments.sort(key=lambda e: (e.display_number is None, e.display_number or 0))
        return tuple(experiments)

    def _clear_progress_table(self) -> None:
        # setRowCount(0) шақыру ескі әрекет батырмалары виджетін
        # viewport-тан көрінбейтін түрде тастап кетеді, БІРАҚ Qt объект
        # ағашынан ешқашан өшірмейді (§ DataJournalPage._render_list()-те
        # расталған дәл осындай bug). Нақты өшіру үшін әр ескі виджетті
        # ЖОЛДАР қысқартылмас бұрын setParent(None) + deleteLater() арқылы
        # бөліп алу керек.
        last_column = len(_PROGRESS_TABLE_HEADERS) - 1
        for row in range(self._progress_table.rowCount()):
            old_widget = self._progress_table.cellWidget(row, last_column)
            if old_widget is not None:
                old_widget.setParent(None)
                old_widget.deleteLater()
        self._progress_table.setRowCount(0)

    def _refresh_details(self) -> None:
        if self._selected_student_id is None:
            self._detail_hint_label.setVisible(True)
            self._student_name_label.setText("")
            self._classroom_name_label.setText("")
            self._classroom_name_label.setVisible(False)
            self._student_code_label.setText("")
            self._copy_code_button.setVisible(False)
            self._regenerate_code_button.setVisible(False)
            self._review_counts_label.setText("")
            self._reset_progress_summary()
            self._clear_progress_table()
            self._progress_table.setVisible(True)
            self._progress_empty_label.setVisible(False)
            return

        student = self._student_repository.get(self._selected_student_id)
        if student is None:
            return
        classroom = self._classroom_repository.get(student.classroom_id)

        self._detail_hint_label.setVisible(False)
        self._student_name_label.setText(student.display_name)

        # Mode Switch + Student Access Screen Redesign §7 "Teacher view of
        # student code" — "Кіру коды: {code}" + "Кодты көшіру"/"Жаңа код
        # жасау" (§ regeneration ЕШҚАШАН авто емес, тек нақты растаудан
        # кейін — ``_on_regenerate_code_clicked``).
        self._student_code_label.setText(f"Кіру коды: {student.student_code}")
        self._copy_code_button.setVisible(True)
        self._regenerate_code_button.setVisible(True)

        # §4 "SELECTED STUDENT HEADER" — accent badge, Phase 13 mapping-мен
        # БІРДЕЙ.
        if classroom is not None:
            accent = classroom_accent_color(classroom.id, classroom.name)
            self._classroom_name_label.setText(classroom.name)
            self._classroom_name_label.setStyleSheet(
                f"color: {accent}; background-color: {_tinted_rgba(accent)};"
                f" border-radius: 4px; padding: 2px 8px;"
            )
            self._classroom_name_label.setVisible(True)
        else:
            accent = COLOR_ACCENT
            self._classroom_name_label.setText(_NO_VALUE_TEXT)
            self._classroom_name_label.setVisible(True)

        self._clear_progress_table()

        experiments = self._iter_catalog_experiments()
        progress_list = [
            self._student_progress_repository.get_progress(student.id, experiment.id)
            for experiment in experiments
        ]

        # §6 "OVERALL PROGRESS BAR": "completed / total * 100" — "Аяқталған"
        # осы беттің ӨЗ, бұрыннан бар анықтамасымен (REVIEWED саны) —
        # § "Do not invent a second completion definition".
        total = len(progress_list)
        completed = sum(1 for p in progress_list if p.status is ProgressStatus.REVIEWED)
        in_progress = sum(1 for p in progress_list if p.status is ProgressStatus.IN_PROGRESS)
        not_started = sum(1 for p in progress_list if p.status is ProgressStatus.NOT_STARTED)
        awaiting_review = sum(1 for p in progress_list if p.status is ProgressStatus.FEEDBACK_SUBMITTED)
        reviewed = completed

        self._stat_value_labels["total"].setText(str(total))
        self._stat_value_labels["completed"].setText(str(completed))
        self._stat_value_labels["in_progress"].setText(str(in_progress))
        self._stat_value_labels["not_started"].setText(str(not_started))
        self._review_counts_label.setText(
            f"Тексеруді күтуде: {awaiting_review}     Тексерілді: {reviewed}"
        )

        percentage = round((completed / total) * 100) if total > 0 else 0
        self._overall_progress_bar.setValue(percentage)
        self._overall_progress_bar.setStyleSheet(
            f"QProgressBar#DashboardActivityBar {{ border: none; border-radius: 4px;"
            f" background-color: {COLOR_BORDER_SUBTLE}; }}"
            f"QProgressBar#DashboardActivityBar::chunk {{ background-color: {accent};"
            f" border-radius: 4px; }}"
        )
        self._overall_progress_percentage_label.setText(f"{percentage}%")

        # §9 "EMPTY STATES" C: каталогта тіпті тәжірибе жоқ болса (edge
        # case), кесте/сан орнына бейтарап хабар.
        has_progress = total > 0
        self._progress_table.setVisible(has_progress)
        self._progress_empty_label.setVisible(not has_progress)

        self._progress_table.setRowCount(len(experiments))
        for row, (experiment, progress) in enumerate(zip(experiments, progress_list)):
            self._populate_progress_row(row, experiment, progress)
        self._progress_table.resizeColumnsToContents()
        # Соңғы баған (3 әрекет батырмасы бар widget) — ``resizeColumnsToContents()``
        # cell widget-тердің sizeHint()-ін әрдайым сенімді өлшемейді (белгілі
        # Qt ерекшелігі), тым тар баған батырмаларды көрші бағандарға
        # қабаттастырып жібереді. Сондықтан бекітілген, батырмалардың
        # нақты еніне сай кең мән қолмен орнатылады.
        self._progress_table.setColumnWidth(len(_PROGRESS_TABLE_HEADERS) - 1, 420)

    def _reset_progress_summary(self) -> None:
        for label in self._stat_value_labels.values():
            label.setText("0")
        self._overall_progress_bar.setValue(0)
        self._overall_progress_bar.setStyleSheet("")
        self._overall_progress_percentage_label.setText("0%")

    def _populate_progress_row(
        self, row: int, experiment: ExperimentDefinition, progress: StudentExperimentProgress
    ) -> None:
        number_text = f"№{experiment.display_number}" if experiment.display_number is not None else _NO_VALUE_TEXT
        test_text = (
            f"{progress.level1_score}/{progress.level1_total}"
            if progress.level1_score is not None and progress.level1_total is not None
            else _NO_VALUE_TEXT
        )
        self_assessment_text = (
            str(progress.self_assessment) if progress.self_assessment is not None else _NO_VALUE_TEXT
        )
        teacher_score_text = (
            str(progress.teacher_score) if progress.teacher_score is not None else _NO_VALUE_TEXT
        )
        review_text = "Тексерілді" if progress.teacher_reviewed else "Тексерілмеді"
        date_text = (
            progress.last_activity_at.astimezone().strftime("%d.%m.%Y")
            if progress.last_activity_at is not None
            else _NO_VALUE_TEXT
        )

        status_column_index = 2
        values = (
            number_text, experiment.title, _STATUS_TEXT[progress.status], date_text,
            test_text, self_assessment_text, teacher_score_text, review_text,
        )
        for column, text in enumerate(values):
            item = QTableWidgetItem(text)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if column == status_column_index:
                # §7 "LABORATORY PROGRESS TABLE": тек статус мәтінінің
                # ӨЗІ түстенеді (§ "Do NOT color entire table rows"),
                # қолданыстағы семантикалық токендермен (_STATUS_COLOR).
                item.setForeground(QColor(_STATUS_COLOR[progress.status]))
            self._progress_table.setItem(row, column, item)

        action_widget = QWidget(self._progress_table)
        action_layout = QHBoxLayout(action_widget)
        action_layout.setContentsMargins(0, 0, 0, 0)

        report_button = QPushButton(_OPEN_REPORT_TEXT, action_widget)
        report_button.setEnabled(progress.latest_session_id is not None and experiment.report is not None)
        report_button.clicked.connect(
            lambda _checked=False, e=experiment, p=progress: self._on_open_report_clicked(e, p)
        )
        action_layout.addWidget(report_button)

        feedback_button = QPushButton(_OPEN_FEEDBACK_TEXT, action_widget)
        feedback_button.setEnabled(progress.latest_session_id is not None and experiment.assessment is not None)
        feedback_button.clicked.connect(
            lambda _checked=False, e=experiment, p=progress: self._on_open_feedback_clicked(e, p)
        )
        action_layout.addWidget(feedback_button)

        grade_button = QPushButton(_GRADE_TEXT, action_widget)
        grade_button.setEnabled(progress.latest_session_id is not None and experiment.assessment is not None)
        grade_button.clicked.connect(
            lambda _checked=False, e=experiment, p=progress: self._on_open_feedback_clicked(e, p)
        )
        action_layout.addWidget(grade_button)

        self._progress_table.setCellWidget(row, len(_PROGRESS_TABLE_HEADERS) - 1, action_widget)

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

    def _on_open_report_clicked(self, experiment: ExperimentDefinition, progress: StudentExperimentProgress) -> None:
        if progress.latest_session_id is None:
            return
        session = self._build_session(progress.latest_session_id)
        if session is None:
            return
        report_data = build_experiment_report_data(experiment, session)
        feedback_result = self._feedback_repository.get_result(progress.latest_session_id)

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

    def _on_open_feedback_clicked(self, experiment: ExperimentDefinition, progress: StudentExperimentProgress) -> None:
        if progress.latest_session_id is None or experiment.assessment is None:
            return
        session_id = progress.latest_session_id
        existing_result = self._feedback_repository.get_result(session_id)
        dialog = ExperimentFeedbackDialog(
            experiment.title, experiment.id, session_id, experiment.assessment,
            existing_result, UserRole.TEACHER, parent=self,
        )
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.finished.connect(self._on_feedback_dialog_finished)
        dialog.draft_saved.connect(self._on_feedback_draft_saved)
        dialog.submitted.connect(self._on_feedback_submitted)
        dialog.teacher_assessment_saved.connect(
            lambda assessment, sid=session_id, eid=experiment.id: self._on_feedback_teacher_assessment_saved(
                sid, eid, assessment
            )
        )
        self._feedback_dialog = dialog
        dialog.show()

    def _on_feedback_dialog_finished(self) -> None:
        self._feedback_dialog = None
        self._refresh_details()

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
        self._refresh_details()
