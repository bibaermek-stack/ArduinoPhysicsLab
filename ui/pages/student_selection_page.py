"""StudentSelectionPage — "Оқушыны таңдаңыз" беті (Phase 39B).

Оқушы режимінде белсенді оқушы әлі таңдалмаса көрсетілетін Router беті
(§ "Do not silently create an anonymous student" — жаңа өлшеу сессиясы
осы бет арқылы нақты таңдалған оқушысыз ЕШҚАШАН басталмайды). Мұғалім
режиміне ешбір қатысы жоқ, класс/оқушы өзгерту контролдары мұнда мүлде
жоқ (тек оқу/таңдау).
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from domain.entities.active_student_context import ActiveStudentContext
from domain.interfaces.i_active_student_repository import IActiveStudentRepository
from domain.interfaces.i_classroom_repository import IClassroomRepository
from domain.interfaces.i_student_repository import IStudentRepository

_TITLE_TEXT = "Оқушыны таңдаңыз"
_CLASSROOM_LABEL_TEXT = "Сынып:"
_STUDENT_LABEL_TEXT = "Оқушы:"
_CONTINUE_BUTTON_TEXT = "Жалғастыру"
_EMPTY_STATE_TEXT = (
    "Оқушылар тізімі әлі жасалмаған.\nМұғалім режимінде сынып пен оқушыны қосыңыз."
)


class StudentSelectionPage(QWidget):
    """Сынып/оқушы dropdown-дары + "Жалғастыру" — таңдалғанда белсенді
    оқушы контексін сақтап, ``student_selected`` сигналын шығарады.
    """

    student_selected = Signal()

    def __init__(
        self,
        classroom_repository: IClassroomRepository,
        student_repository: IStudentRepository,
        active_student_repository: IActiveStudentRepository,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._classroom_repository = classroom_repository
        self._student_repository = student_repository
        self._active_student_repository = active_student_repository

        title_label = QLabel(_TITLE_TEXT, self)
        title_font = title_label.font()
        title_font.setBold(True)
        title_font.setPointSize(title_font.pointSize() + 4)
        title_label.setFont(title_font)

        self._empty_state_label = QLabel(_EMPTY_STATE_TEXT, self)
        self._empty_state_label.setWordWrap(True)
        self._empty_state_label.setProperty("role", "secondary")

        self._classroom_combo = QComboBox(self)
        self._classroom_combo.currentIndexChanged.connect(self._on_classroom_changed)

        self._student_combo = QComboBox(self)
        self._student_combo.currentIndexChanged.connect(self._update_continue_enabled)

        classroom_row = QHBoxLayout()
        classroom_row.addWidget(QLabel(_CLASSROOM_LABEL_TEXT, self))
        classroom_row.addWidget(self._classroom_combo, 1)

        student_row = QHBoxLayout()
        student_row.addWidget(QLabel(_STUDENT_LABEL_TEXT, self))
        student_row.addWidget(self._student_combo, 1)

        self._continue_button = QPushButton(_CONTINUE_BUTTON_TEXT, self)
        self._continue_button.clicked.connect(self._on_continue_clicked)

        self._form_container = QWidget(self)
        form_layout = QVBoxLayout(self._form_container)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.addLayout(classroom_row)
        form_layout.addLayout(student_row)
        form_layout.addWidget(self._continue_button)

        layout = QVBoxLayout(self)
        layout.addStretch(1)
        layout.addWidget(title_label)
        layout.addWidget(self._empty_state_label)
        layout.addWidget(self._form_container)
        layout.addStretch(1)

        self._refresh()

    # ---- Router интерфейсі ------------------------------------------------

    def on_enter(self) -> None:
        self._refresh()

    # ---- Ішкі логика ------------------------------------------------------

    def _refresh(self) -> None:
        classrooms = self._classroom_repository.list_active()
        has_any_student = any(
            self._student_repository.list_by_classroom(classroom.id) for classroom in classrooms
        )
        is_empty = not classrooms or not has_any_student
        self._empty_state_label.setVisible(is_empty)
        self._form_container.setVisible(not is_empty)
        if is_empty:
            return

        active_context = self._active_student_repository.get()

        self._classroom_combo.blockSignals(True)
        self._classroom_combo.clear()
        for classroom in classrooms:
            self._classroom_combo.addItem(classroom.name, classroom.id)
        if active_context is not None:
            index = self._classroom_combo.findData(active_context.classroom_id)
            if index >= 0:
                self._classroom_combo.setCurrentIndex(index)
        self._classroom_combo.blockSignals(False)

        self._populate_students(preferred_student_id=active_context.student_id if active_context else None)

    def _on_classroom_changed(self, _index: int) -> None:
        self._populate_students()

    def _populate_students(self, preferred_student_id: str | None = None) -> None:
        classroom_id = self._classroom_combo.currentData()
        self._student_combo.blockSignals(True)
        self._student_combo.clear()
        if classroom_id is not None:
            for student in self._student_repository.list_by_classroom(classroom_id):
                self._student_combo.addItem(student.display_name, student.id)
            if preferred_student_id is not None:
                index = self._student_combo.findData(preferred_student_id)
                if index >= 0:
                    self._student_combo.setCurrentIndex(index)
        self._student_combo.blockSignals(False)
        self._update_continue_enabled()

    def _update_continue_enabled(self) -> None:
        self._continue_button.setEnabled(
            self._classroom_combo.currentData() is not None
            and self._student_combo.currentData() is not None
        )

    def _on_continue_clicked(self) -> None:
        classroom_id = self._classroom_combo.currentData()
        student_id = self._student_combo.currentData()
        if classroom_id is None or student_id is None:
            return
        self._active_student_repository.set(
            ActiveStudentContext(classroom_id=classroom_id, student_id=student_id)
        )
        self.student_selected.emit()
