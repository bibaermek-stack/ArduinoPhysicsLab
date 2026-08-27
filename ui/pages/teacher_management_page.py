"""TeacherManagementPage — Мұғалімдерді басқару беті (Multi-Teacher
Accounts фазасы, §7).

``Баптаулар → Мұғалімдерді басқару →`` батырмасы арқылы ашылатын
бөлек route (§ ``ClassManagementPage``-пен БІРДЕЙ CRUD/QDialog
конвенциясы: жеке форма-диалогтар, "Белсенді емес ету" — hard delete
ЕМЕС). §8/§9 талабы бойынша барлық валидация INLINE (жеке қате
жапсырмасы) — ЕШБІР ``QMessageBox`` popup қолданылмайды (§ "Do not use
disruptive popup error dialogs").

PIN өзгерту (§9 "Provide a separate action: PIN кодын өзгерту") ЖЕКЕ,
тәуелсіз ``_ChangePinDialog`` арқылы — аты-жөні/сыныптар/белсенділікті
сақтау ЕШҚАШАН PIN-ді қалпына келтірмейді (§ "Changing a teacher's name
or classes must NOT require resetting their PIN").
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from uuid import uuid4

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from domain.entities.classroom import Classroom
from domain.entities.teacher import Teacher
from domain.interfaces.i_classroom_repository import IClassroomRepository
from domain.interfaces.i_teacher_repository import ITeacherRepository
from domain.services.teacher_pin import hash_pin

_PAGE_TITLE = "Мұғалімдер"
_PAGE_SUBTITLE = "Жүйені пайдаланатын мұғалімдерді басқару"
_BACK_BUTTON_TEXT = "← Баптауларға оралу"
_ADD_TEACHER_BUTTON_TEXT = "+ Мұғалім қосу"
_EDIT_BUTTON_TEXT = "Өзгерту"
_TABLE_HEADERS = ("Мұғалім", "Сыныптар", "Күйі", "Әрекеттер")
_ACTIVE_TEXT = "Белсенді"
_INACTIVE_TEXT = "Белсенді емес"
_NO_CLASSROOMS_TEXT = "—"
_EMPTY_HINT_TEXT = "Мұғалімдер әлі қосылмаған"

_PIN_LENGTH = 6
_NAME_EMPTY_ERROR = "Аты-жөні бос болмауы керек"
_PIN_LENGTH_ERROR = f"PIN {_PIN_LENGTH} цифрдан тұруы керек"
_PIN_MISMATCH_ERROR = "PIN кодтары сәйкес келмейді"
_PIN_TAKEN_ERROR = "Бұл PIN басқа мұғалімге тиесілі"

_ADD_DIALOG_TITLE = "Мұғалім қосу"
_EDIT_DIALOG_TITLE = "Мұғалімді өзгерту"
_CHANGE_PIN_DIALOG_TITLE = "PIN кодын өзгерту"
_CANCEL_BUTTON_TEXT = "Бас тарту"
_ADD_CONFIRM_BUTTON_TEXT = "Мұғалімді қосу"
_SAVE_BUTTON_TEXT = "Сақтау"
_CHANGE_PIN_BUTTON_TEXT = "PIN кодын өзгерту"
_SAVE_PIN_BUTTON_TEXT = "PIN-ді сақтау"
_PIN_CHANGED_HINT = "PIN сәтті жаңартылды."


def _make_background_transparent(widget: QWidget) -> None:
    widget.setStyleSheet("background-color: transparent;")


class _ClassroomCheckboxList(QWidget):
    """Сыныптар чекбокс тізімі — §8 "Add Teacher" формасының "Сыныптар"
    бөлімі, §9 "Edit Teacher"-де қайта пайдаланылады."""

    def __init__(self, classrooms: tuple[Classroom, ...], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        self._checkboxes: dict[str, QCheckBox] = {}
        for classroom in classrooms:
            checkbox = QCheckBox(classroom.name, self)
            self._checkboxes[classroom.id] = checkbox
            layout.addWidget(checkbox)
        if not classrooms:
            empty_label = QLabel(_EMPTY_HINT_TEXT.replace("Мұғалімдер", "Сыныптар"), self)
            empty_label.setProperty("role", "secondary")
            layout.addWidget(empty_label)
        layout.addStretch(1)

    def checked_ids(self) -> tuple[str, ...]:
        return tuple(
            classroom_id for classroom_id, checkbox in self._checkboxes.items() if checkbox.isChecked()
        )

    def set_checked_ids(self, classroom_ids: tuple[str, ...]) -> None:
        checked = set(classroom_ids)
        for classroom_id, checkbox in self._checkboxes.items():
            checkbox.setChecked(classroom_id in checked)


class _ChangePinDialog(QDialog):
    """§9 "Provide a separate action: PIN кодын өзгерту" — өз алдына
    тәуелсіз диалог, растаса ДЕРЕУ ``teacher_repository.update()``
    шақырады (аты-жөні/сыныптар/белсенділік өзгерту ағынына ЕШБІР
    қатысы жоқ)."""

    def __init__(
        self,
        teacher_id: str,
        teacher_repository: ITeacherRepository,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(_CHANGE_PIN_DIALOG_TITLE)
        self._teacher_id = teacher_id
        self._teacher_repository = teacher_repository

        self._pin_edit = QLineEdit(self)
        self._pin_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._pin_confirm_edit = QLineEdit(self)
        self._pin_confirm_edit.setEchoMode(QLineEdit.EchoMode.Password)

        self._error_label = QLabel("", self)
        self._error_label.setProperty("role", "error")
        self._error_label.setWordWrap(True)
        self._error_label.setVisible(False)

        form = QFormLayout()
        form.addRow("Жаңа PIN:", self._pin_edit)
        form.addRow("Жаңа PIN қайталаңыз:", self._pin_confirm_edit)

        self._save_button = QPushButton(_SAVE_PIN_BUTTON_TEXT, self)
        self._save_button.setObjectName("PrimaryButton")
        self._save_button.clicked.connect(self._on_save_clicked)
        cancel_button = QPushButton(_CANCEL_BUTTON_TEXT, self)
        cancel_button.clicked.connect(self.reject)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(cancel_button)
        button_row.addWidget(self._save_button)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._error_label)
        layout.addLayout(button_row)

    def _show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.setVisible(True)

    def _on_save_clicked(self) -> None:
        pin = self._pin_edit.text().strip()
        pin_confirm = self._pin_confirm_edit.text().strip()
        if len(pin) != _PIN_LENGTH or not pin.isdigit():
            self._show_error(_PIN_LENGTH_ERROR)
            return
        if pin != pin_confirm:
            self._show_error(_PIN_MISMATCH_ERROR)
            return
        new_hash = hash_pin(pin)
        if self._teacher_repository.pin_hash_exists(new_hash, exclude_teacher_id=self._teacher_id):
            self._show_error(_PIN_TAKEN_ERROR)
            return

        teacher = self._teacher_repository.get(self._teacher_id)
        if teacher is None:
            self.reject()
            return
        updated = replace(teacher, pin_hash=new_hash, updated_at=datetime.now(timezone.utc))
        self._teacher_repository.update(updated)
        self.accept()


class _AddTeacherDialog(QDialog):
    """§8 "Add Teacher" — аты-жөні/жеке PIN/PIN растау/сыныптар, барлық
    валидация INLINE (§ error label, popup ЖОҚ)."""

    def __init__(
        self,
        classrooms: tuple[Classroom, ...],
        teacher_repository: ITeacherRepository,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(_ADD_DIALOG_TITLE)
        self._teacher_repository = teacher_repository

        self._name_edit = QLineEdit(self)
        self._pin_edit = QLineEdit(self)
        self._pin_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._pin_confirm_edit = QLineEdit(self)
        self._pin_confirm_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._classroom_list = _ClassroomCheckboxList(classrooms, self)

        classroom_scroll = QScrollArea(self)
        classroom_scroll.setWidgetResizable(True)
        classroom_scroll.setWidget(self._classroom_list)
        classroom_scroll.setMaximumHeight(160)

        self._error_label = QLabel("", self)
        self._error_label.setProperty("role", "error")
        self._error_label.setWordWrap(True)
        self._error_label.setVisible(False)

        form = QFormLayout()
        form.addRow("Аты-жөні:", self._name_edit)
        form.addRow("Жеке PIN:", self._pin_edit)
        form.addRow("PIN кодын қайталаңыз:", self._pin_confirm_edit)
        form.addRow("Сыныптар:", classroom_scroll)

        confirm_button = QPushButton(_ADD_CONFIRM_BUTTON_TEXT, self)
        confirm_button.setObjectName("PrimaryButton")
        confirm_button.clicked.connect(self._on_confirm_clicked)
        cancel_button = QPushButton(_CANCEL_BUTTON_TEXT, self)
        cancel_button.clicked.connect(self.reject)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(cancel_button)
        button_row.addWidget(confirm_button)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._error_label)
        layout.addLayout(button_row)

    def _show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.setVisible(True)

    def _on_confirm_clicked(self) -> None:
        name = self._name_edit.text().strip()
        if not name:
            self._show_error(_NAME_EMPTY_ERROR)
            return
        pin = self._pin_edit.text().strip()
        pin_confirm = self._pin_confirm_edit.text().strip()
        if len(pin) != _PIN_LENGTH or not pin.isdigit():
            self._show_error(_PIN_LENGTH_ERROR)
            return
        if pin != pin_confirm:
            self._show_error(_PIN_MISMATCH_ERROR)
            return
        if self._teacher_repository.pin_hash_exists(hash_pin(pin)):
            self._show_error(_PIN_TAKEN_ERROR)
            return
        self.accept()

    def get_values(self) -> tuple[str, str, tuple[str, ...]]:
        return (
            self._name_edit.text().strip(),
            self._pin_edit.text().strip(),
            self._classroom_list.checked_ids(),
        )


class _EditTeacherDialog(QDialog):
    """§9 "Edit Teacher" — аты-жөні/тағайындалған сыныптар/белсенділік.
    PIN-ге ЕШБІР қатысы жоқ (§ жеке "PIN кодын өзгерту" батырмасы,
    басылса ДЕРЕУ ``_ChangePinDialog`` ашады және ӨЗ бетінше сақтайды)."""

    def __init__(
        self,
        teacher: Teacher,
        classrooms: tuple[Classroom, ...],
        assigned_classroom_ids: tuple[str, ...],
        teacher_repository: ITeacherRepository,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(_EDIT_DIALOG_TITLE)
        self._teacher_id = teacher.id
        self._teacher_repository = teacher_repository

        self._name_edit = QLineEdit(teacher.full_name, self)
        self._active_checkbox = QCheckBox(_ACTIVE_TEXT, self)
        self._active_checkbox.setChecked(teacher.is_active)
        self._classroom_list = _ClassroomCheckboxList(classrooms, self)
        self._classroom_list.set_checked_ids(assigned_classroom_ids)

        classroom_scroll = QScrollArea(self)
        classroom_scroll.setWidgetResizable(True)
        classroom_scroll.setWidget(self._classroom_list)
        classroom_scroll.setMaximumHeight(160)

        self._error_label = QLabel("", self)
        self._error_label.setProperty("role", "error")
        self._error_label.setWordWrap(True)
        self._error_label.setVisible(False)

        self._pin_hint_label = QLabel("", self)
        self._pin_hint_label.setProperty("role", "secondary")
        self._pin_hint_label.setVisible(False)

        change_pin_button = QPushButton(_CHANGE_PIN_BUTTON_TEXT, self)
        change_pin_button.clicked.connect(self._on_change_pin_clicked)

        form = QFormLayout()
        form.addRow("Аты-жөні:", self._name_edit)
        form.addRow("Сыныптар:", classroom_scroll)
        form.addRow("", self._active_checkbox)
        form.addRow("", change_pin_button)
        form.addRow("", self._pin_hint_label)

        save_button = QPushButton(_SAVE_BUTTON_TEXT, self)
        save_button.setObjectName("PrimaryButton")
        save_button.clicked.connect(self._on_save_clicked)
        cancel_button = QPushButton(_CANCEL_BUTTON_TEXT, self)
        cancel_button.clicked.connect(self.reject)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(cancel_button)
        button_row.addWidget(save_button)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._error_label)
        layout.addLayout(button_row)

    def _on_change_pin_clicked(self) -> None:
        dialog = _ChangePinDialog(self._teacher_id, self._teacher_repository, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._pin_hint_label.setText(_PIN_CHANGED_HINT)
            self._pin_hint_label.setVisible(True)

    def _on_save_clicked(self) -> None:
        name = self._name_edit.text().strip()
        if not name:
            self._error_label.setText(_NAME_EMPTY_ERROR)
            self._error_label.setVisible(True)
            return
        self.accept()

    def get_values(self) -> tuple[str, bool, tuple[str, ...]]:
        return (
            self._name_edit.text().strip(),
            self._active_checkbox.isChecked(),
            self._classroom_list.checked_ids(),
        )


class TeacherManagementPage(QWidget):
    """§7 "Add a teacher management section inside: Баптаулар" — толық
    CRUD беті: тізім/қосу/өзгерту/белсенді(емес) ету. Hard delete ЖОҚ
    (§10 "Disable instead of Delete")."""

    back_requested = Signal()
    teachers_changed = Signal()

    def __init__(
        self,
        teacher_repository: ITeacherRepository,
        classroom_repository: IClassroomRepository,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._teacher_repository = teacher_repository
        self._classroom_repository = classroom_repository
        self._build_ui()

    def _build_ui(self) -> None:
        title_label = QLabel(_PAGE_TITLE, self)
        title_font = title_label.font()
        title_font.setBold(True)
        title_font.setPointSize(title_font.pointSize() + 4)
        title_label.setFont(title_font)

        subtitle_label = QLabel(_PAGE_SUBTITLE, self)
        subtitle_label.setProperty("role", "secondary")
        _make_background_transparent(title_label)
        _make_background_transparent(subtitle_label)

        header_layout = QVBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.addWidget(title_label)
        header_layout.addWidget(subtitle_label)

        self._back_button = QPushButton(_BACK_BUTTON_TEXT, self)
        self._back_button.setObjectName("HomeModuleCardAction")
        self._back_button.clicked.connect(self.back_requested)

        self._add_button = QPushButton(_ADD_TEACHER_BUTTON_TEXT, self)
        self._add_button.setObjectName("PrimaryButton")
        self._add_button.clicked.connect(self._on_add_teacher_clicked)

        action_row = QHBoxLayout()
        action_row.addWidget(self._back_button)
        action_row.addStretch(1)
        action_row.addWidget(self._add_button)

        self._empty_label = QLabel(_EMPTY_HINT_TEXT, self)
        self._empty_label.setProperty("role", "secondary")
        _make_background_transparent(self._empty_label)

        self._table = QTableWidget(0, len(_TABLE_HEADERS), self)
        self._table.setHorizontalHeaderLabels(_TABLE_HEADERS)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        layout = QVBoxLayout(self)
        layout.addLayout(header_layout)
        layout.addLayout(action_row)
        layout.addWidget(self._empty_label)
        layout.addWidget(self._table)

        self._refresh_table()

    # ---- Router интерфейсі --------------------------------------------------

    def on_enter(self) -> None:
        self._refresh_table()

    # ---- Ішкі логика --------------------------------------------------------

    def _clear_table(self) -> None:
        # § ``ClassManagementPage._clear_progress_table()``-пен БІРДЕЙ
        # белгілі Qt bug-і: ``setRowCount(0)`` ескі әрекет батырмалары
        # виджетін viewport-тан көрінбейтін түрде тастап кетеді, БІРАҚ
        # Qt объект ағашынан ешқашан өшірмейді — жолдар қысқартылмас
        # бұрын әр ескі cell widget-ті ЖЕКЕ ``setParent(None)`` +
        # ``deleteLater()`` арқылы бөліп алу керек.
        last_column = len(_TABLE_HEADERS) - 1
        for row in range(self._table.rowCount()):
            old_widget = self._table.cellWidget(row, last_column)
            if old_widget is not None:
                old_widget.setParent(None)
                old_widget.deleteLater()
        self._table.setRowCount(0)

    def _refresh_table(self) -> None:
        teachers = self._teacher_repository.list_all()
        classrooms_by_id = {c.id: c for c in self._classroom_repository.list_all()}

        self._empty_label.setVisible(not teachers)
        self._table.setVisible(bool(teachers))

        self._clear_table()
        self._table.setRowCount(len(teachers))
        for row, teacher in enumerate(teachers):
            assigned_ids = self._teacher_repository.list_assigned_classroom_ids(teacher.id)
            classroom_names = ", ".join(
                classrooms_by_id[classroom_id].name
                for classroom_id in assigned_ids
                if classroom_id in classrooms_by_id
            ) or _NO_CLASSROOMS_TEXT
            status_text = _ACTIVE_TEXT if teacher.is_active else _INACTIVE_TEXT

            name_item = QTableWidgetItem(teacher.full_name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(row, 0, name_item)

            classes_item = QTableWidgetItem(classroom_names)
            classes_item.setFlags(classes_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(row, 1, classes_item)

            status_item = QTableWidgetItem(status_text)
            status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(row, 2, status_item)

            action_widget = QWidget(self._table)
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(0, 0, 0, 0)
            edit_button = QPushButton(_EDIT_BUTTON_TEXT, action_widget)
            edit_button.clicked.connect(
                lambda _checked=False, t=teacher: self._on_edit_teacher_clicked(t)
            )
            action_layout.addWidget(edit_button)
            self._table.setCellWidget(row, 3, action_widget)

    def _on_add_teacher_clicked(self) -> None:
        classrooms = self._classroom_repository.list_active()
        dialog = _AddTeacherDialog(classrooms, self._teacher_repository, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name, pin, classroom_ids = dialog.get_values()
        now = datetime.now(timezone.utc)
        teacher = Teacher(
            id=str(uuid4()), full_name=name, pin_hash=hash_pin(pin), created_at=now, updated_at=now
        )
        self._teacher_repository.create(teacher, assigned_classroom_ids=classroom_ids)
        self._refresh_table()
        self.teachers_changed.emit()

    def _on_edit_teacher_clicked(self, teacher: Teacher) -> None:
        classrooms = self._classroom_repository.list_active()
        assigned_ids = self._teacher_repository.list_assigned_classroom_ids(teacher.id)
        dialog = _EditTeacherDialog(
            teacher, classrooms, assigned_ids, self._teacher_repository, parent=self
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            name, is_active, classroom_ids = dialog.get_values()
            updated = replace(
                teacher, full_name=name, is_active=is_active, updated_at=datetime.now(timezone.utc)
            )
            self._teacher_repository.update(updated)
            self._teacher_repository.set_assigned_classroom_ids(teacher.id, classroom_ids)
        # § PIN (егер "PIN кодын өзгерту" арқылы өзгертілген болса) ӨЗ
        # бетінше диалог ІШІНДЕ ЖАЗЫЛҒАН — сыртқы Cancel/Save нәтижесіне
        # ТӘУЕЛСІЗ, сондықтан кесте/сигнал ӘРҚАШАН жаңартылады.
        self._refresh_table()
        self.teachers_changed.emit()
