"""ExperimentFeedbackDialog — тәжірибеден кейінгі үш деңгейлі кері
байланыс/бағалау диалогы (Phase 39A): 1-деңгей Тест, 2-деңгей Талдау,
3-деңгей Рефлексия + өзін-өзі бағалау, плюс Мұғалім режимінде ғана
көрінетін Мұғалім бағасы секциясы.

Бұл диалог ``ExperimentGuideDialog``/``ExperimentReportDialog``-пен
БІРДЕЙ оқшаулау принципіне бағынады — ``ExperimentController``/
coordinator/session-ге ЕШБІР тікелей сілтемесі жоқ, тек
``ExperimentAssessmentDefinition`` (сұрақтар) мен міндетті емес
``ExperimentFeedbackResult`` (бұрын сақталған жоба/жіберілген жауап)
қабылдайды. Репозиторийге ЕШБІР жазба осы файлда жасалмайды — диалог
тек ``draft_saved``/``submitted``/``teacher_assessment_saved``
сигналдарын НАҚТЫ domain объектілерімен шығарады,
``ExperimentWorkspacePage`` (жалғыз координатор) осыларды тыңдап,
``IFeedbackRepository``-ге өзі жазады — дәл ``SqliteSessionRepository``-мен
БІРДЕЙ "жалғыз координатор" архитектурасы.

Мұғалім бағасы секциясы ``role is UserRole.TEACHER`` болғанда ҒАНА
ҚҰРЫЛАДЫ (жай ЖАСЫРЫЛМАЙДЫ) — Оқушы режимінде бұл виджеттер объект
ретінде мүлде жоқ. Домен деңгейіндегі нақты рұқсат тексеруі
(``PermissionError``) ``domain.services.experiment_feedback_service.
apply_teacher_assessment()``-те, бұл UI сол тексерудің ЕКІНШІ,
тәуелсіз қорғаныс сызығы ғана.

``.show()`` арқылы (ЕШҚАШАН ``.exec()`` ЕМЕС) көрсетіледі — өлшеу/
serial ағынын ешқашан бөгемейді.
"""

from __future__ import annotations

from datetime import datetime, timezone

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from domain.entities.experiment_assessment import ExperimentAssessmentDefinition
from domain.entities.experiment_feedback_result import (
    ExperimentFeedbackResult,
    MultipleChoiceAnswer,
    OpenResponseAnswer,
    ReflectionAnswer,
    TeacherAssessment,
)
from domain.entities.user_role import UserRole
from domain.services.experiment_feedback_service import score_level1

_SUBTITLE_TEXT = "Кері байланыс"
_CLOSE_BUTTON_TEXT = "Жабу"
_SAVE_DRAFT_BUTTON_TEXT = "Сақтау"
_SUBMIT_BUTTON_TEXT = "Жіберу"
_TAB_LEVEL1_TEXT = "1. Тест"
_TAB_LEVEL2_TEXT = "2. Талдау"
_TAB_LEVEL3_TEXT = "3. Рефлексия"
_TEACHER_REVIEW_STATUS_TEXT = "Мұғалім тексереді"
_DEFAULT_SIZE = (760, 780)

_TEACHER_SECTION_TITLE = "Мұғалім бағасы"
_TEACHER_SCORE_LABEL = "Мұғалім бағасы (0–10):"
_TEACHER_COMMENT_LABEL = "Мұғалім пікірі:"
_TEACHER_REVIEWED_LABEL = "Қаралды"
_TEACHER_SAVE_BUTTON_TEXT = "Мұғалім бағасын сақтау"


class ExperimentFeedbackDialog(QDialog):
    """Бір тәжірибенің үш деңгейлі кері байланысы — скролленетін,
    таза (repository-сіз) диалог терезесі.
    """

    draft_saved = Signal(object)  # ExperimentFeedbackResult
    submitted = Signal(object)  # ExperimentFeedbackResult
    teacher_assessment_saved = Signal(object)  # TeacherAssessment

    def __init__(
        self,
        experiment_title: str,
        experiment_id: str,
        session_id: str,
        assessment: ExperimentAssessmentDefinition,
        existing_result: ExperimentFeedbackResult | None,
        role: UserRole,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._experiment_id = experiment_id
        self._session_id = session_id
        self._assessment = assessment
        self._role = role

        self._level1_groups: dict[str, QButtonGroup] = {}
        self._level2_edits: dict[str, QTextEdit] = {}
        self._level3_edits: dict[str, QTextEdit] = {}
        self._self_assessment_group = QButtonGroup(self)
        self._self_assessment_group.setExclusive(True)
        self._self_assessment_buttons: dict[int, QPushButton] = {}

        self.setWindowTitle(f"{_SUBTITLE_TEXT} — {experiment_title}")
        self.resize(*_DEFAULT_SIZE)

        title_label = QLabel(experiment_title, self)
        title_font = title_label.font()
        title_font.setBold(True)
        title_font.setPointSize(title_font.pointSize() + 4)
        title_label.setFont(title_font)

        subtitle_label = QLabel(_SUBTITLE_TEXT, self)
        subtitle_label.setProperty("role", "secondary")

        header_layout = QVBoxLayout()
        header_layout.addWidget(title_label)
        header_layout.addWidget(subtitle_label)

        self._body_stack = QStackedWidget(self)
        self._teacher_status_label: QLabel | None = None
        self._editing_page = self._build_editing_page(assessment)
        self._summary_page = self._build_summary_page_placeholder()
        self._body_stack.addWidget(self._editing_page)
        self._body_stack.addWidget(self._summary_page)

        layout = QVBoxLayout(self)
        layout.addLayout(header_layout)
        layout.addWidget(self._body_stack, 1)

        # Мұғалім бағасы секциясы ӘДЕЙІ ``_body_stack``-тың СЫРТЫНДА (тек
        # Level1/2/3 ғана "editing_page" ↔ "summary_page" ауысады) —
        # әйтпесе студент жіберген соң (``is_draft=False``) бүкіл
        # ``_editing_page`` жасырылып, ІШІНДЕ орналасқан Мұғалім бағасы
        # секциясы да МҮЛДЕ көрінбей қалатын (расталған bug: Мұғалім
        # ешқашан қол жеткізе алмайтын). "Teacher Assessment remains
        # editable regardless of submission state" осылай шынымен
        # орындалады, тек кодта деп жазылып қоймай.
        if self._role is UserRole.TEACHER:
            layout.addWidget(self._build_teacher_assessment_section(self))

        self._validation_label = QLabel(self)
        self._validation_label.setProperty("role", "error")
        self._validation_label.setWordWrap(True)
        self._validation_label.setVisible(False)
        layout.addWidget(self._validation_label)

        self._save_draft_button = QPushButton(_SAVE_DRAFT_BUTTON_TEXT, self)
        self._save_draft_button.clicked.connect(self._on_save_draft_clicked)
        self._submit_button = QPushButton(_SUBMIT_BUTTON_TEXT, self)
        self._submit_button.setObjectName("PrimaryButton")
        self._submit_button.clicked.connect(self._on_submit_clicked)
        self._close_button = QPushButton(_CLOSE_BUTTON_TEXT, self)
        self._close_button.clicked.connect(self.close)

        footer_layout = QHBoxLayout()
        footer_layout.addStretch(1)
        footer_layout.addWidget(self._save_draft_button)
        footer_layout.addWidget(self._submit_button)
        footer_layout.addWidget(self._close_button)
        layout.addLayout(footer_layout)

        self._is_submitted = False
        if existing_result is not None:
            self._restore_from_result(existing_result)

    # ---- Құрылыс -------------------------------------------------------------

    def _build_editing_page(self, assessment: ExperimentAssessmentDefinition) -> QWidget:
        page = QWidget(self)
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)

        self._tab_level1_button = QPushButton(_TAB_LEVEL1_TEXT, page)
        self._tab_level2_button = QPushButton(_TAB_LEVEL2_TEXT, page)
        self._tab_level3_button = QPushButton(_TAB_LEVEL3_TEXT, page)
        for button in (self._tab_level1_button, self._tab_level2_button, self._tab_level3_button):
            button.setCheckable(True)
        self._tab_level1_button.setChecked(True)

        self._tab_group = QButtonGroup(page)
        self._tab_group.setExclusive(True)
        self._tab_group.addButton(self._tab_level1_button, 0)
        self._tab_group.addButton(self._tab_level2_button, 1)
        self._tab_group.addButton(self._tab_level3_button, 2)

        tab_row = QHBoxLayout()
        tab_row.addWidget(self._tab_level1_button)
        tab_row.addWidget(self._tab_level2_button)
        tab_row.addWidget(self._tab_level3_button)
        tab_row.addStretch(1)
        page_layout.addLayout(tab_row)

        self._level_stack = QStackedWidget(page)
        self._level_stack.addWidget(self._build_level1_page(assessment))
        self._level_stack.addWidget(self._build_level2_page(assessment))
        self._level_stack.addWidget(self._build_level3_page(assessment))
        self._tab_group.idClicked.connect(self._level_stack.setCurrentIndex)

        scroll_area = QScrollArea(page)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setWidget(self._level_stack)
        page_layout.addWidget(scroll_area, 1)

        return page

    def _build_level1_page(self, assessment: ExperimentAssessmentDefinition) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)

        self._level1_score_label = QLabel(page)
        self._level1_score_label.setProperty("role", "sectionTitle")
        self._level1_score_label.setVisible(False)
        layout.addWidget(self._level1_score_label)

        for question in assessment.level1_questions:
            frame, frame_layout = self._build_question_frame(page, question.prompt)
            group = QButtonGroup(frame)
            group.setExclusive(True)
            for index, option_text in enumerate(question.options):
                radio = QRadioButton(option_text, frame)
                group.addButton(radio, index)
                frame_layout.addWidget(radio)
            self._level1_groups[question.id] = group
            layout.addWidget(frame)

        layout.addStretch(1)
        return page

    def _build_level2_page(self, assessment: ExperimentAssessmentDefinition) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)

        for question in assessment.level2_questions:
            frame, frame_layout = self._build_question_frame(page, question.prompt)
            edit = QTextEdit(frame)
            edit.setMinimumHeight(80)
            frame_layout.addWidget(edit)
            self._level2_edits[question.id] = edit
            layout.addWidget(frame)

        self._level2_status_label = QLabel(page)
        self._level2_status_label.setProperty("role", "secondary")
        self._level2_status_label.setVisible(False)
        layout.addWidget(self._level2_status_label)

        layout.addStretch(1)
        return page

    def _build_level3_page(self, assessment: ExperimentAssessmentDefinition) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)

        for question in assessment.level3_questions:
            frame, frame_layout = self._build_question_frame(page, question.prompt)
            edit = QTextEdit(frame)
            edit.setMinimumHeight(80)
            frame_layout.addWidget(edit)
            self._level3_edits[question.id] = edit
            layout.addWidget(frame)

        self_assessment_frame, self_assessment_layout = self._build_question_frame(
            page, "Сабақты бағалаңыз:"
        )
        buttons_row = QHBoxLayout()
        for value in range(assessment.self_assessment_min, assessment.self_assessment_max + 1):
            button = QPushButton(str(value), self_assessment_frame)
            button.setCheckable(True)
            self._self_assessment_group.addButton(button, value)
            self._self_assessment_buttons[value] = button
            buttons_row.addWidget(button)
        buttons_row.addStretch(1)
        self_assessment_layout.addLayout(buttons_row)
        layout.addWidget(self_assessment_frame)

        layout.addStretch(1)
        return page

    def _build_teacher_assessment_section(self, parent: QWidget) -> QFrame:
        frame = QFrame(parent)
        frame.setObjectName("GuideSection")
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(frame)

        title_label = QLabel(_TEACHER_SECTION_TITLE, frame)
        title_label.setProperty("role", "sectionTitle")
        layout.addWidget(title_label)

        score_row = QHBoxLayout()
        score_row.addWidget(QLabel(_TEACHER_SCORE_LABEL, frame))
        self._teacher_score_spin = QSpinBox(frame)
        self._teacher_score_spin.setRange(0, 10)
        score_row.addWidget(self._teacher_score_spin)
        score_row.addStretch(1)
        layout.addLayout(score_row)

        layout.addWidget(QLabel(_TEACHER_COMMENT_LABEL, frame))
        self._teacher_comment_edit = QTextEdit(frame)
        self._teacher_comment_edit.setMinimumHeight(80)
        layout.addWidget(self._teacher_comment_edit)

        self._teacher_reviewed_checkbox = QCheckBox(_TEACHER_REVIEWED_LABEL, frame)
        self._teacher_reviewed_checkbox.setChecked(True)
        layout.addWidget(self._teacher_reviewed_checkbox)

        self._teacher_save_button = QPushButton(_TEACHER_SAVE_BUTTON_TEXT, frame)
        self._teacher_save_button.clicked.connect(self._on_teacher_save_clicked)
        self._teacher_status_label = QLabel(frame)
        self._teacher_status_label.setProperty("role", "secondary")

        teacher_footer = QHBoxLayout()
        teacher_footer.addWidget(self._teacher_save_button)
        teacher_footer.addWidget(self._teacher_status_label)
        teacher_footer.addStretch(1)
        layout.addLayout(teacher_footer)

        return frame

    def _build_question_frame(self, parent: QWidget, prompt: str) -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame(parent)
        frame.setObjectName("GuideSection")
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(frame)
        prompt_label = QLabel(prompt, frame)
        prompt_label.setWordWrap(True)
        layout.addWidget(prompt_label)
        return frame, layout

    def _build_summary_page_placeholder(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        self._summary_label = QLabel(page)
        self._summary_label.setWordWrap(True)
        layout.addWidget(self._summary_label)
        layout.addStretch(1)
        return page

    # ---- Жауап жинау / қалпына келтіру ---------------------------------------

    def _collect_level1_answers(self) -> tuple[MultipleChoiceAnswer, ...]:
        answers = []
        for question_id, group in self._level1_groups.items():
            checked_id = group.checkedId()
            if checked_id != -1:
                answers.append(MultipleChoiceAnswer(question_id=question_id, selected_option_index=checked_id))
        return tuple(answers)

    def _collect_level2_answers(self) -> tuple[OpenResponseAnswer, ...]:
        return tuple(
            OpenResponseAnswer(question_id=question_id, response_text=edit.toPlainText())
            for question_id, edit in self._level2_edits.items()
        )

    def _collect_level3_answers(self) -> tuple[ReflectionAnswer, ...]:
        return tuple(
            ReflectionAnswer(question_id=question_id, response_text=edit.toPlainText())
            for question_id, edit in self._level3_edits.items()
        )

    def _selected_self_assessment(self) -> int | None:
        checked_id = self._self_assessment_group.checkedId()
        return checked_id if checked_id != -1 else None

    def _restore_from_result(self, result: ExperimentFeedbackResult) -> None:
        answers_by_question = {answer.question_id: answer.selected_option_index for answer in result.level1_answers}
        for question_id, group in self._level1_groups.items():
            selected = answers_by_question.get(question_id)
            if selected is not None:
                button = group.button(selected)
                if button is not None:
                    button.setChecked(True)

        level2_by_question = {answer.question_id: answer.response_text for answer in result.level2_answers}
        for question_id, edit in self._level2_edits.items():
            edit.setPlainText(level2_by_question.get(question_id, ""))

        level3_by_question = {answer.question_id: answer.response_text for answer in result.level3_answers}
        for question_id, edit in self._level3_edits.items():
            edit.setPlainText(level3_by_question.get(question_id, ""))

        if result.self_assessment is not None:
            button = self._self_assessment_buttons.get(result.self_assessment)
            if button is not None:
                button.setChecked(True)

        if self._role is UserRole.TEACHER and result.teacher_assessment is not None:
            self._teacher_score_spin.setValue(result.teacher_assessment.score)
            self._teacher_comment_edit.setPlainText(result.teacher_assessment.comment)
            self._teacher_reviewed_checkbox.setChecked(result.teacher_assessment.reviewed)

        if not result.is_draft:
            self._show_submitted_summary(result)

    # ---- Әрекеттер -------------------------------------------------------------

    def _build_current_result(self, is_draft: bool) -> ExperimentFeedbackResult:
        level1_answers = self._collect_level1_answers()
        score, total, percentage = score_level1(self._assessment, level1_answers)
        return ExperimentFeedbackResult(
            experiment_id=self._experiment_id,
            session_id=self._session_id,
            level1_answers=level1_answers,
            level1_score=score,
            level1_total=total,
            level1_percentage=percentage,
            level2_answers=self._collect_level2_answers(),
            level3_answers=self._collect_level3_answers(),
            self_assessment=self._selected_self_assessment(),
            is_draft=is_draft,
            submitted_at=None if is_draft else datetime.now(timezone.utc),
        )

    def _on_save_draft_clicked(self) -> None:
        self._validation_label.setVisible(False)
        result = self._build_current_result(is_draft=True)
        self.draft_saved.emit(result)

    def _missing_answer_messages(self) -> list[str]:
        missing: list[str] = []
        unanswered_level1 = sum(1 for group in self._level1_groups.values() if group.checkedId() == -1)
        if unanswered_level1:
            missing.append(f"1-деңгей (Тест): {unanswered_level1} сұраққа жауап берілмеген.")

        empty_level2 = sum(1 for edit in self._level2_edits.values() if not edit.toPlainText().strip())
        if empty_level2:
            missing.append(f"2-деңгей (Талдау): {empty_level2} сұраққа жауап жазылмаған.")

        empty_level3 = sum(1 for edit in self._level3_edits.values() if not edit.toPlainText().strip())
        if empty_level3:
            missing.append(f"3-деңгей (Рефлексия): {empty_level3} сұраққа жауап жазылмаған.")

        if self._selected_self_assessment() is None:
            missing.append("Өзін-өзі бағалау таңдалмаған.")

        return missing

    def _on_submit_clicked(self) -> None:
        missing = self._missing_answer_messages()
        if missing:
            self._validation_label.setText(
                "Жіберу үшін барлық сұраққа жауап беріңіз:\n" + "\n".join(f"• {m}" for m in missing)
            )
            self._validation_label.setVisible(True)
            return

        self._validation_label.setVisible(False)
        result = self._build_current_result(is_draft=False)
        self.submitted.emit(result)
        self._show_submitted_summary(result)

    def _on_teacher_save_clicked(self) -> None:
        teacher_assessment = TeacherAssessment(
            score=self._teacher_score_spin.value(),
            comment=self._teacher_comment_edit.toPlainText(),
            reviewed=self._teacher_reviewed_checkbox.isChecked(),
        )
        self.teacher_assessment_saved.emit(teacher_assessment)
        if self._teacher_status_label is not None:
            self._teacher_status_label.setText("Сақталды.")

    def _show_submitted_summary(self, result: ExperimentFeedbackResult) -> None:
        self._is_submitted = True
        self._submit_button.setEnabled(False)
        self._save_draft_button.setEnabled(False)
        for group in self._level1_groups.values():
            for button in group.buttons():
                button.setEnabled(False)
        for edit in (*self._level2_edits.values(), *self._level3_edits.values()):
            edit.setReadOnly(True)
        for button in self._self_assessment_buttons.values():
            button.setEnabled(False)

        self._level1_score_label.setText(
            f"1-деңгей: Тест — {result.level1_score}/{result.level1_total} "
            f"({result.level1_percentage:.0f}%)"
        )
        self._level1_score_label.setVisible(True)
        self._level2_status_label.setText(_TEACHER_REVIEW_STATUS_TEXT)
        self._level2_status_label.setVisible(True)

        self._summary_label.setText(
            "Кері байланыс аяқталды\n\n"
            f"1-деңгей: Тест\n{result.level1_score}/{result.level1_total} — "
            f"{result.level1_percentage:.0f}%\n\n"
            f"2-деңгей: Талдау\n{_TEACHER_REVIEW_STATUS_TEXT}\n\n"
            "3-деңгей: Рефлексия\nЖауап сақталды\n\n"
            f"Өзін-өзі бағалау:\n{result.self_assessment}/"
            f"{self._assessment.self_assessment_max}\n\n"
            "Жалпы күйі:\nМұғалім бағасын күтуде"
        )
        self._body_stack.setCurrentWidget(self._summary_page)
