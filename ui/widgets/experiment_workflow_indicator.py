"""ExperimentWorkflowIndicator — тәжірибе жұмыс беттерінің үстіндегі
6-қадамдық прогресс жолағы (Phase 38A, Phase 39A-да 6-қадамға (Кері
байланыс) кеңейтілді).

Бұл ВИЗАРД ЕМЕС — студент кез келген қадамға (Нұсқаулық/Схема/Есеп
батырмаларына, тіпті Start-қа) кез келген уақытта, кез келген ретпен
бара алады. Виджет ешбір навигацияны мәжбүрлемейді/бөгемейді — тек
ағымдағы прогресті КӨРСЕТЕДІ. ``ExperimentWorkspacePage``-тегі бұрыннан
бар оқиғалардың (батырма басу, readiness өзгеруі, Start/Stop) нәтижесінде
СЫРТТАН ``set_*_state()`` арқылы жаңартылады — бұл виджеттің өзі
``ExperimentController``/``MultiSensorExperimentCoordinator``/
``LiveGraphWidget``-ке ЕШБІР тікелей сілтемесі жоқ (Guide/Report/Diagram
диалогтарымен БІРДЕЙ оқшаулау кепілдігі).
"""

from __future__ import annotations

from enum import Enum

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

_STEP_GUIDE_TITLE = "Нұсқаулық"
_STEP_DIAGRAM_TITLE = "Схема"
_STEP_DEVICE_TITLE = "Құрылғы"
_STEP_MEASUREMENT_TITLE = "Өлшеу"
_STEP_REPORT_TITLE = "Есеп"
_STEP_FEEDBACK_TITLE = "Кері байланыс"

_DEVICE_ATTENTION_TEXT = "Құрылғы қосылмаған"
_CONNECT_BUTTON_TEXT = "Құрылғыны қосу"


class WorkflowStepState(Enum):
    NOT_VISITED = "not_visited"  # ○
    CURRENT = "current"  # ●
    COMPLETED = "completed"  # ✓
    ATTENTION = "attention"  # !


_ICON_BY_STATE = {
    WorkflowStepState.NOT_VISITED: "○",
    WorkflowStepState.CURRENT: "●",
    WorkflowStepState.COMPLETED: "✓",
    WorkflowStepState.ATTENTION: "!",
}


class ExperimentWorkflowIndicator(QWidget):
    """Алты қадамды (Нұсқаулық/Схема/Құрылғы/Өлшеу/Есеп/Кері байланыс)
    көрсететін, таза презентациялық жолақ.
    """

    connect_device_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ExperimentWorkflowIndicator")

        self._guide_label = self._build_step_label()
        self._diagram_label = self._build_step_label()
        self._device_label = self._build_step_label()
        self._measurement_label = self._build_step_label()
        self._report_label = self._build_step_label()
        self._feedback_label = self._build_step_label()

        steps_row = QHBoxLayout()
        steps_row.addWidget(self._guide_label)
        steps_row.addWidget(self._diagram_label)
        steps_row.addWidget(self._device_label)
        steps_row.addWidget(self._measurement_label)
        steps_row.addWidget(self._report_label)
        steps_row.addWidget(self._feedback_label)
        steps_row.addStretch(1)

        self._device_attention_label = QLabel(_DEVICE_ATTENTION_TEXT, self)
        self._device_attention_label.setProperty("role", "error")

        self._connect_device_button = QPushButton(_CONNECT_BUTTON_TEXT, self)
        self._connect_device_button.clicked.connect(self.connect_device_requested)

        # Phase 4 (Workspace Layout Optimization): бұрын бұл ішкі
        # QHBoxLayout-тың ӨЗ (default, ~9px) contentsMargins-і болатын —
        # graph аймағына ешбір мағыналы пайда бермейтін ~18px тік орынды
        # ысырап ететін (§ "Restore compact desktop layout... remove
        # unnecessary vertical spacing"). Сыртқы ``layout`` бұрыннан
        # margin-сыз (0,0,0,0) еді — ІШКІ layout та солай болуы керек.
        self._device_attention_row = QHBoxLayout()
        self._device_attention_row.setContentsMargins(0, 0, 0, 0)
        self._device_attention_row.addWidget(self._device_attention_label)
        self._device_attention_row.addWidget(self._connect_device_button)
        self._device_attention_row.addStretch(1)
        self._device_attention_container = QWidget(self)
        self._device_attention_container.setLayout(self._device_attention_row)
        self._device_attention_container.setVisible(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addLayout(steps_row)
        layout.addWidget(self._device_attention_container)

        self._guide_state = WorkflowStepState.NOT_VISITED
        self._diagram_state = WorkflowStepState.NOT_VISITED
        self._device_state = WorkflowStepState.ATTENTION
        self._measurement_state = WorkflowStepState.NOT_VISITED
        self._report_state = WorkflowStepState.NOT_VISITED
        self._feedback_state = WorkflowStepState.NOT_VISITED
        self._render_all()

    def _build_step_label(self) -> QLabel:
        label = QLabel(self)
        label.setProperty("role", "sectionTitle")
        return label

    # ---- Public API --------------------------------------------------

    def reset(
        self,
        guide_available: bool = True,
        diagram_available: bool = True,
        report_available: bool = True,
        feedback_available: bool = True,
    ) -> None:
        """Жаңа тәжірибеге ауысқанда (``on_enter()``) шақырылады — барлық
        қадам бастапқы күйге оралады. ``*_available=False`` (яғни
        ``experiment.guide``/``.diagram``/``.report``/``.assessment is
        None``) болса, сол қадам дереу "✓" болып көрсетіледі — орындалуы
        КЕРЕК ешнәрсе жоқ, сондықтан ол мәңгі "толтырылмаған" болып
        қалмайды.
        """
        self.set_guide_state(
            WorkflowStepState.COMPLETED if not guide_available else WorkflowStepState.NOT_VISITED
        )
        self.set_diagram_state(
            WorkflowStepState.COMPLETED
            if not diagram_available
            else WorkflowStepState.NOT_VISITED
        )
        self.set_device_state(WorkflowStepState.ATTENTION)
        self.set_measurement_state(WorkflowStepState.NOT_VISITED)
        self.set_report_state(
            WorkflowStepState.COMPLETED if not report_available else WorkflowStepState.NOT_VISITED
        )
        self.set_feedback_state(
            WorkflowStepState.COMPLETED
            if not feedback_available
            else WorkflowStepState.NOT_VISITED
        )

    def set_guide_state(self, state: WorkflowStepState) -> None:
        self._guide_state = state
        self._render_step(self._guide_label, _STEP_GUIDE_TITLE, state)

    def set_diagram_state(self, state: WorkflowStepState) -> None:
        self._diagram_state = state
        self._render_step(self._diagram_label, _STEP_DIAGRAM_TITLE, state)

    def set_device_state(self, state: WorkflowStepState) -> None:
        self._device_state = state
        self._render_step(self._device_label, _STEP_DEVICE_TITLE, state)
        self._device_attention_container.setVisible(state is WorkflowStepState.ATTENTION)

    def set_measurement_state(self, state: WorkflowStepState) -> None:
        self._measurement_state = state
        self._render_step(self._measurement_label, _STEP_MEASUREMENT_TITLE, state)

    def set_report_state(self, state: WorkflowStepState) -> None:
        self._report_state = state
        self._render_step(self._report_label, _STEP_REPORT_TITLE, state)

    def set_feedback_state(self, state: WorkflowStepState) -> None:
        self._feedback_state = state
        self._render_step(self._feedback_label, _STEP_FEEDBACK_TITLE, state)

    # ---- Ішкі логика ---------------------------------------------------

    def _render_all(self) -> None:
        self._render_step(self._guide_label, _STEP_GUIDE_TITLE, self._guide_state)
        self._render_step(self._diagram_label, _STEP_DIAGRAM_TITLE, self._diagram_state)
        self._render_step(self._device_label, _STEP_DEVICE_TITLE, self._device_state)
        self._render_step(
            self._measurement_label, _STEP_MEASUREMENT_TITLE, self._measurement_state
        )
        self._render_step(self._report_label, _STEP_REPORT_TITLE, self._report_state)
        self._render_step(self._feedback_label, _STEP_FEEDBACK_TITLE, self._feedback_state)
        self._device_attention_container.setVisible(
            self._device_state is WorkflowStepState.ATTENTION
        )

    @staticmethod
    def _render_step(label: QLabel, title: str, state: WorkflowStepState) -> None:
        label.setText(f"{_ICON_BY_STATE[state]} {title}")
