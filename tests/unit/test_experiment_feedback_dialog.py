"""ExperimentFeedbackDialog (Phase 39A) юнит-тесттері: үш деңгей де
рендерленуі, жауап беру, толмаған жауапты валидациялау, дұрыс жауапты
жіберуге дейін жасырын ұстау, 1-деңгей есебін дұрыс есептеу, аяқталу
қорытындысын көрсету, драфт күйінің қайта ашқанда сақталуы, Мұғалім
секциясының рөлге тәуелді құрылуы.
"""

import sys

import pytest
from PySide6.QtWidgets import QApplication, QLabel, QRadioButton, QTextEdit

from domain.entities.experiment_assessment import (
    ExperimentAssessmentDefinition,
    MultipleChoiceQuestion,
    OpenResponseQuestion,
    ReflectionQuestion,
)
from domain.entities.experiment_feedback_result import (
    ExperimentFeedbackResult,
    MultipleChoiceAnswer,
    OpenResponseAnswer,
    ReflectionAnswer,
)
from domain.entities.user_role import UserRole
from ui.widgets.experiment_feedback_dialog import ExperimentFeedbackDialog


@pytest.fixture(scope="module", autouse=True)
def qt_application() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def _make_assessment() -> ExperimentAssessmentDefinition:
    return ExperimentAssessmentDefinition(
        level1_questions=(
            MultipleChoiceQuestion("l1-1", "Q1?", ("A", "B", "C"), correct_option_index=1),
            MultipleChoiceQuestion("l1-2", "Q2?", ("A", "B"), correct_option_index=0),
        ),
        level2_questions=(
            OpenResponseQuestion("l2-1", "Analyze the graph."),
            OpenResponseQuestion("l2-2", "Explain the error source."),
        ),
        level3_questions=(
            ReflectionQuestion("l3-1", "What did you learn?"),
            ReflectionQuestion("l3-2", "What was hard?"),
        ),
    )


def _make_dialog(role: UserRole = UserRole.STUDENT, existing_result=None) -> ExperimentFeedbackDialog:
    return ExperimentFeedbackDialog(
        "Test Experiment", "exp-1", "sess-1", _make_assessment(), existing_result, role
    )


def _answer_everything(dialog: ExperimentFeedbackDialog) -> None:
    dialog._level1_groups["l1-1"].button(1).setChecked(True)
    dialog._level1_groups["l1-2"].button(0).setChecked(True)
    dialog._level2_edits["l2-1"].setPlainText("my analysis")
    dialog._level2_edits["l2-2"].setPlainText("my error analysis")
    dialog._level3_edits["l3-1"].setPlainText("I learned resistance")
    dialog._level3_edits["l3-2"].setPlainText("Wiring was hard")
    dialog._self_assessment_buttons[4].setChecked(True)


# ---- Rendering all three levels ---------------------------------------------


def test_renders_all_level1_questions_as_radio_groups() -> None:
    dialog = _make_dialog()
    assert set(dialog._level1_groups.keys()) == {"l1-1", "l1-2"}
    radios = dialog._level1_groups["l1-1"].buttons()
    assert len(radios) == 3
    assert all(isinstance(r, QRadioButton) for r in radios)


def test_renders_all_level2_and_level3_questions_as_text_edits() -> None:
    dialog = _make_dialog()
    assert set(dialog._level2_edits.keys()) == {"l2-1", "l2-2"}
    assert set(dialog._level3_edits.keys()) == {"l3-1", "l3-2"}
    assert all(isinstance(e, QTextEdit) for e in dialog._level2_edits.values())


def test_self_assessment_buttons_span_configured_range() -> None:
    dialog = _make_dialog()
    assert set(dialog._self_assessment_buttons.keys()) == {1, 2, 3, 4, 5}


def test_tab_buttons_switch_level_stack_pages() -> None:
    dialog = _make_dialog()
    assert dialog._level_stack.currentIndex() == 0
    dialog._tab_level2_button.click()
    assert dialog._level_stack.currentIndex() == 1
    dialog._tab_level3_button.click()
    assert dialog._level_stack.currentIndex() == 2


# ---- Answering + no reveal before submit ------------------------------------


def test_does_not_show_correct_answers_before_submission() -> None:
    dialog = _make_dialog()
    texts = "\n".join(label.text() for label in dialog.findChildren(QLabel))
    assert "дұрыс" not in texts.lower()
    assert dialog._level1_score_label.isHidden() is True


def test_student_can_select_and_change_answers_before_submission() -> None:
    dialog = _make_dialog()
    group = dialog._level1_groups["l1-1"]
    group.button(0).setChecked(True)
    assert group.checkedId() == 0
    group.button(2).setChecked(True)
    assert group.checkedId() == 2


# ---- Validation on submit --------------------------------------------------


def test_submit_with_missing_answers_shows_validation_and_does_not_submit() -> None:
    dialog = _make_dialog()
    submitted_results = []
    dialog.submitted.connect(lambda r: submitted_results.append(r))

    dialog._on_submit_clicked()

    assert submitted_results == []
    assert dialog._validation_label.isHidden() is False
    assert "1-деңгей" in dialog._validation_label.text()
    assert "2-деңгей" in dialog._validation_label.text()
    assert "3-деңгей" in dialog._validation_label.text()
    assert "Өзін-өзі бағалау" in dialog._validation_label.text()


def test_submit_with_all_answers_succeeds() -> None:
    dialog = _make_dialog()
    _answer_everything(dialog)
    submitted_results = []
    dialog.submitted.connect(lambda r: submitted_results.append(r))

    dialog._on_submit_clicked()

    assert len(submitted_results) == 1
    assert dialog._validation_label.isHidden() is True


# ---- Level1 scoring ----------------------------------------------------------


def test_level1_score_calculated_correctly_on_submit() -> None:
    dialog = _make_dialog()
    _answer_everything(dialog)  # both l1-1 (correct=1) and l1-2 (correct=0) answered correctly
    submitted_results = []
    dialog.submitted.connect(lambda r: submitted_results.append(r))

    dialog._on_submit_clicked()

    result = submitted_results[0]
    assert result.level1_score == 2
    assert result.level1_total == 2
    assert result.level1_percentage == 100.0


def test_level1_score_reflects_wrong_answer() -> None:
    dialog = _make_dialog()
    _answer_everything(dialog)
    dialog._level1_groups["l1-2"].button(1).setChecked(True)  # wrong (correct=0)
    submitted_results = []
    dialog.submitted.connect(lambda r: submitted_results.append(r))

    dialog._on_submit_clicked()

    result = submitted_results[0]
    assert result.level1_score == 1
    assert result.level1_total == 2


# ---- Completion summary ------------------------------------------------------


def test_completion_summary_shown_after_submit() -> None:
    dialog = _make_dialog()
    _answer_everything(dialog)

    dialog._on_submit_clicked()

    assert dialog._body_stack.currentWidget() is dialog._summary_page
    assert "Кері байланыс аяқталды" in dialog._summary_label.text()
    assert "Мұғалім бағасын күтуде" in dialog._summary_label.text()


def test_level1_score_label_visible_and_correct_after_submit() -> None:
    dialog = _make_dialog()
    _answer_everything(dialog)

    dialog._on_submit_clicked()

    assert dialog._level1_score_label.isHidden() is False
    assert "2/2" in dialog._level1_score_label.text()


def test_submitted_dialog_disables_further_editing() -> None:
    dialog = _make_dialog()
    _answer_everything(dialog)
    dialog._on_submit_clicked()

    assert dialog._submit_button.isEnabled() is False
    assert dialog._save_draft_button.isEnabled() is False
    for group in dialog._level1_groups.values():
        for button in group.buttons():
            assert button.isEnabled() is False


# ---- Draft save/restore -------------------------------------------------------


def test_draft_saved_signal_emits_current_partial_state() -> None:
    dialog = _make_dialog()
    dialog._level2_edits["l2-1"].setPlainText("partial thought")
    drafts = []
    dialog.draft_saved.connect(lambda r: drafts.append(r))

    dialog._on_save_draft_clicked()

    assert len(drafts) == 1
    assert drafts[0].is_draft is True
    assert drafts[0].level2_answers[0].response_text == "partial thought"


def test_reopening_with_existing_draft_restores_answers() -> None:
    existing = ExperimentFeedbackResult(
        experiment_id="exp-1",
        session_id="sess-1",
        level1_answers=(MultipleChoiceAnswer("l1-1", 1),),
        level2_answers=(OpenResponseAnswer("l2-1", "restored analysis"),),
        level3_answers=(ReflectionAnswer("l3-1", "restored reflection"),),
        self_assessment=3,
        is_draft=True,
    )
    dialog = _make_dialog(existing_result=existing)

    assert dialog._level1_groups["l1-1"].checkedId() == 1
    assert dialog._level2_edits["l2-1"].toPlainText() == "restored analysis"
    assert dialog._level3_edits["l3-1"].toPlainText() == "restored reflection"
    assert dialog._self_assessment_buttons[3].isChecked() is True
    # Draft (not submitted) should still show the editing page.
    assert dialog._body_stack.currentWidget() is dialog._editing_page


def test_reopening_with_submitted_result_shows_summary_directly() -> None:
    existing = ExperimentFeedbackResult(
        experiment_id="exp-1",
        session_id="sess-1",
        level1_answers=(MultipleChoiceAnswer("l1-1", 1),),
        level1_score=1,
        level1_total=2,
        level1_percentage=50.0,
        self_assessment=5,
        is_draft=False,
    )
    dialog = _make_dialog(existing_result=existing)

    assert dialog._body_stack.currentWidget() is dialog._summary_page
    assert dialog._submit_button.isEnabled() is False


# ---- Teacher-only section ------------------------------------------------------


def test_teacher_section_not_constructed_in_student_mode() -> None:
    dialog = _make_dialog(role=UserRole.STUDENT)
    assert dialog._teacher_status_label is None
    assert not hasattr(dialog, "_teacher_score_spin")


def test_teacher_section_constructed_in_teacher_mode() -> None:
    dialog = _make_dialog(role=UserRole.TEACHER)
    assert dialog._teacher_status_label is not None
    assert hasattr(dialog, "_teacher_score_spin")


def test_teacher_save_emits_signal_with_entered_values() -> None:
    dialog = _make_dialog(role=UserRole.TEACHER)
    saved = []
    dialog.teacher_assessment_saved.connect(lambda ta: saved.append(ta))

    dialog._teacher_score_spin.setValue(8)
    dialog._teacher_comment_edit.setPlainText("Nice work")
    dialog._on_teacher_save_clicked()

    assert len(saved) == 1
    assert saved[0].score == 8
    assert saved[0].comment == "Nice work"


def test_teacher_can_save_assessment_even_after_student_submitted() -> None:
    existing = ExperimentFeedbackResult(
        experiment_id="exp-1", session_id="sess-1", is_draft=False, self_assessment=4
    )
    dialog = _make_dialog(role=UserRole.TEACHER, existing_result=existing)
    saved = []
    dialog.teacher_assessment_saved.connect(lambda ta: saved.append(ta))

    dialog._teacher_score_spin.setValue(10)
    dialog._on_teacher_save_clicked()

    assert len(saved) == 1


def test_teacher_assessment_section_stays_visible_after_submission() -> None:
    """Phase 39B regression: Мұғалім бағасы секциясы бұрын
    ``_editing_page``-тің ІШІНДЕ орналасқан еді — жіберілген (``is_draft=
    False``) нәтиже ашылғанда ``_body_stack`` ``_summary_page``-ге
    ауысып, секцияны да МҮЛДЕ көрінбейтін ететін (нақты пайдаланушы
    оны экранда ешқашан көре алмайтын, тек тікелей объект қолмен
    манипуляцияланса ғана "жұмыс істейтін" bug). Секция ЕНДІ
    ``_body_stack``-тың СЫРТЫНДА — сол себепті бет ауысуына тәуелсіз,
    әрдайым нақты көрінеді.
    """
    existing = ExperimentFeedbackResult(
        experiment_id="exp-1", session_id="sess-1", is_draft=False, self_assessment=4
    )
    dialog = _make_dialog(role=UserRole.TEACHER, existing_result=existing)

    assert dialog._body_stack.currentWidget() is dialog._summary_page
    assert dialog._teacher_score_spin.isHidden() is False
    assert dialog._teacher_score_spin.parent() is not dialog._editing_page
    assert dialog._teacher_score_spin.parent() is not dialog._summary_page


# ---- Scroll behaviour ------------------------------------------------------


def test_editing_page_contains_scroll_area() -> None:
    from PySide6.QtWidgets import QScrollArea

    dialog = _make_dialog()
    scroll_areas = dialog._editing_page.findChildren(QScrollArea)
    assert len(scroll_areas) == 1
    assert scroll_areas[0].widgetResizable() is True
