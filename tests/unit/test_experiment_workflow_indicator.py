"""ExperimentWorkflowIndicator (Phase 38A) — таза презентациялық виджет
тестері: әр `set_*_state()` дұрыс белгіні көрсетеді, `reset()`
guide/diagram/report `None` болғанда дереу "✓" қояды, құрылғы
`ATTENTION` күйінде inline хабарлама+батырма көрінеді, ал `COMPLETED`-те
жасырылады, және байланыс батырмасы сигнал шығарады.
"""

import sys

import pytest
from PySide6.QtWidgets import QApplication

from ui.widgets.experiment_workflow_indicator import (
    ExperimentWorkflowIndicator,
    WorkflowStepState,
)


@pytest.fixture(scope="module", autouse=True)
def qt_application() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def _make_indicator() -> ExperimentWorkflowIndicator:
    return ExperimentWorkflowIndicator()


def test_initial_state_shows_not_visited_and_device_attention() -> None:
    indicator = _make_indicator()

    assert indicator._guide_label.text() == "○ Нұсқаулық"
    assert indicator._diagram_label.text() == "○ Схема"
    assert indicator._device_label.text() == "! Құрылғы"
    assert indicator._measurement_label.text() == "○ Өлшеу"
    assert indicator._report_label.text() == "○ Есеп"
    assert indicator._feedback_label.text() == "○ Кері байланыс"
    assert not indicator._device_attention_container.isHidden()


def test_set_guide_state_completed_updates_icon() -> None:
    indicator = _make_indicator()

    indicator.set_guide_state(WorkflowStepState.COMPLETED)

    assert indicator._guide_label.text() == "✓ Нұсқаулық"


def test_set_diagram_state_current_updates_icon() -> None:
    indicator = _make_indicator()

    indicator.set_diagram_state(WorkflowStepState.CURRENT)

    assert indicator._diagram_label.text() == "● Схема"


def test_set_report_state_attention_updates_icon() -> None:
    indicator = _make_indicator()

    indicator.set_report_state(WorkflowStepState.ATTENTION)

    assert indicator._report_label.text() == "! Есеп"


def test_set_measurement_state_transitions() -> None:
    indicator = _make_indicator()

    indicator.set_measurement_state(WorkflowStepState.CURRENT)
    assert indicator._measurement_label.text() == "● Өлшеу"

    indicator.set_measurement_state(WorkflowStepState.COMPLETED)
    assert indicator._measurement_label.text() == "✓ Өлшеу"


def test_device_attention_container_visible_only_in_attention_state() -> None:
    indicator = _make_indicator()

    # Бастапқыда __init__ device күйі ATTENTION болғандықтан көрінеді.
    assert not indicator._device_attention_container.isHidden()

    indicator.set_device_state(WorkflowStepState.COMPLETED)
    assert indicator._device_attention_container.isHidden()

    indicator.set_device_state(WorkflowStepState.ATTENTION)
    assert not indicator._device_attention_container.isHidden()


def test_connect_device_button_click_emits_signal() -> None:
    indicator = _make_indicator()
    received: list[None] = []
    indicator.connect_device_requested.connect(lambda: received.append(None))

    indicator._connect_device_button.click()

    assert len(received) == 1


def test_reset_seeds_completed_for_unavailable_steps() -> None:
    indicator = _make_indicator()
    # Алдымен барлық қадамды "ласта" — reset() шынымен қайта орнатуын тексеру үшін.
    indicator.set_guide_state(WorkflowStepState.COMPLETED)
    indicator.set_diagram_state(WorkflowStepState.COMPLETED)
    indicator.set_report_state(WorkflowStepState.COMPLETED)
    indicator.set_measurement_state(WorkflowStepState.COMPLETED)
    indicator.set_device_state(WorkflowStepState.COMPLETED)
    indicator.set_feedback_state(WorkflowStepState.COMPLETED)

    indicator.reset(
        guide_available=False,
        diagram_available=True,
        report_available=False,
        feedback_available=False,
    )

    assert indicator._guide_label.text() == "✓ Нұсқаулық"
    assert indicator._diagram_label.text() == "○ Схема"
    assert indicator._report_label.text() == "✓ Есеп"
    assert indicator._measurement_label.text() == "○ Өлшеу"
    assert indicator._device_label.text() == "! Құрылғы"
    assert indicator._feedback_label.text() == "✓ Кері байланыс"
    assert not indicator._device_attention_container.isHidden()


def test_reset_defaults_to_all_available() -> None:
    indicator = _make_indicator()
    indicator.set_guide_state(WorkflowStepState.COMPLETED)

    indicator.reset()

    assert indicator._guide_label.text() == "○ Нұсқаулық"
    assert indicator._diagram_label.text() == "○ Схема"
    assert indicator._report_label.text() == "○ Есеп"
    assert indicator._feedback_label.text() == "○ Кері байланыс"


def test_set_feedback_state_transitions() -> None:
    indicator = _make_indicator()

    indicator.set_feedback_state(WorkflowStepState.CURRENT)
    assert indicator._feedback_label.text() == "● Кері байланыс"

    indicator.set_feedback_state(WorkflowStepState.COMPLETED)
    assert indicator._feedback_label.text() == "✓ Кері байланыс"
