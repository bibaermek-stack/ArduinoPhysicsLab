"""ExperimentReportDialog — тәжірибенің НАҚТЫ өлшенген деректеріне
негізделген зертханалық есеп диалогы (Phase 36, PDF/экспорт ЖОҚ —
тек архитектура/UI).

Бұл диалог ЕШБІР жаңа физикалық есептеу жасамайды: барлық статистика/
fit/қуат/жұмыс мәні шақырушыда (``ExperimentWorkspacePage``) АЛДЫН АЛА
``domain.services.experiment_report_data.build_experiment_report_data()``
арқылы есептеліп, ДАЙЫН ``ExperimentReportData`` ретінде беріледі —
диалогтың өзі тек РЕНДЕРЛЕЙДІ. Дәл осы себептен диалог ``LiveGraphWidget``/
``MeasurementWorkspace``/coordinator-ге ЕШБІР сілтемесі жоқ (``Experiment
GuideDialog``-пен БІРДЕЙ оқшаулау принципі) — ашу/жабу өлшеу/график/A-B/
region күйіне архитектуралық түрде тие алмайды.

"Live" болу қасиеті ("report updates when reopened") диалогтың ӨЗІНЕН
ЕМЕС — әр басу сайын ЖАҢА ``ExperimentReportData``/pixmap есептеліп,
ЖАҢА диалог данасы құрылуынан келеді (``ExperimentWorkspacePage.
_on_report_button_clicked()``). Диалог ешбір auto-refresh/polling
жасамайды.

``.show()`` арқылы (ЕШҚАШАН ``.exec()`` ЕМЕС) көрсетіледі.
"""

from __future__ import annotations

from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from domain.entities.experiment_assessment import ExperimentAssessmentDefinition
from domain.entities.experiment_definition import ExperimentGuide, ExperimentReport
from domain.entities.experiment_feedback_result import ExperimentFeedbackResult
from domain.services.experiment_report_data import ChannelReportStatistics, ExperimentReportData

_CLOSE_BUTTON_TEXT = "Жабу"
_DEFAULT_SIZE = (780, 860)
_NO_VALUE_TEXT = "—"

_SECTION_TITLE_OBJECTIVE = "Жұмыстың мақсаты"
_SECTION_TITLE_EQUIPMENT = "Қажетті құрал-жабдықтар"
_SECTION_TITLE_MEASURED_VALUES = "Өлшенген мәндер"
_SECTION_TITLE_GRAPHS = "График"
_SECTION_TITLE_CALCULATED = "Есептелген шамалар"
_SECTION_TITLE_AUTOMATIC_ANALYSIS = "Автоматты талдау"
_SECTION_TITLE_CONCLUSION = "Қорытынды"
_SECTION_TITLE_LEVEL1_RESULT = "1-деңгей: Тест нәтижесі"
_SECTION_TITLE_LEVEL2_ANSWERS = "2-деңгей: Талдау жауаптары"
_SECTION_TITLE_LEVEL3_REFLECTION = "3-деңгей: Рефлексия"
_SECTION_TITLE_TEACHER_ASSESSMENT = "Мұғалім бағасы"
_TEACHER_REVIEW_STATUS_TEXT = "Мұғалім тексереді"
_DRAFT_STATUS_TEXT = "Жоба (әлі жіберілмеген)"


class ExperimentReportDialog(QDialog):
    """Бір тәжірибенің зертханалық есебі — скролленетін диалог терезесі.

    Тек НАҚТЫ мазмұны бар секциялар ғана салынады (Phase 35 §6-мен
    БІРДЕЙ конвенция) — "Өлшенген мәндер" мен "Қорытынды" ӘРҚАШАН
    көрінеді (олар әрқашан мағыналы: бос сессия "—" күйін көрсетеді,
    қорытынды студент жазуы үшін бос өріс), қалғандары шартты.
    """

    def __init__(
        self,
        experiment_title: str,
        guide: ExperimentGuide | None,
        report_config: ExperimentReport,
        report_data: ExperimentReportData,
        graph_pixmap: QPixmap | None,
        parent: QWidget | None = None,
        automatic_conclusion: str = "",
        assessment: ExperimentAssessmentDefinition | None = None,
        feedback_result: ExperimentFeedbackResult | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{report_config.title} — {experiment_title}")
        self.resize(*_DEFAULT_SIZE)

        title_label = QLabel(experiment_title, self)
        title_font = title_label.font()
        title_font.setBold(True)
        title_font.setPointSize(title_font.pointSize() + 4)
        title_label.setFont(title_font)

        subtitle_label = QLabel(report_config.title, self)
        subtitle_label.setProperty("role", "secondary")

        header_layout = QVBoxLayout()
        header_layout.addWidget(title_label)
        header_layout.addWidget(subtitle_label)

        self._sections_layout = QVBoxLayout()
        self._sections_layout.addStretch(1)
        self._populate_sections(
            guide,
            report_config,
            report_data,
            graph_pixmap,
            automatic_conclusion,
            assessment,
            feedback_result,
        )

        content_widget = QWidget(self)
        content_widget.setLayout(self._sections_layout)

        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setWidget(content_widget)

        self._close_button = QPushButton(_CLOSE_BUTTON_TEXT, self)
        self._close_button.clicked.connect(self.close)

        footer_layout = QHBoxLayout()
        footer_layout.addStretch(1)
        footer_layout.addWidget(self._close_button)

        layout = QVBoxLayout(self)
        layout.addLayout(header_layout)
        layout.addWidget(scroll_area, 1)
        layout.addLayout(footer_layout)

    # ---- Ішкі логика -----------------------------------------------------

    def _populate_sections(
        self,
        guide: ExperimentGuide | None,
        report_config: ExperimentReport,
        report_data: ExperimentReportData,
        graph_pixmap: QPixmap | None,
        automatic_conclusion: str,
        assessment: ExperimentAssessmentDefinition | None,
        feedback_result: ExperimentFeedbackResult | None,
    ) -> None:
        insert_index = self._sections_layout.count() - 1  # addStretch(1)-ден бұрын

        def add_section(section: QFrame | None) -> None:
            nonlocal insert_index
            if section is None:
                return
            self._sections_layout.insertWidget(insert_index, section)
            insert_index += 1

        if guide is not None:
            add_section(self._build_bullet_section(_SECTION_TITLE_OBJECTIVE, guide.objective))
            add_section(self._build_bullet_section(_SECTION_TITLE_EQUIPMENT, guide.equipment))

        add_section(self._build_measured_values_section(report_data))
        add_section(self._build_graph_section(graph_pixmap))
        add_section(self._build_calculated_quantities_section(report_data))
        add_section(self._build_automatic_analysis_section(automatic_conclusion))
        add_section(self._build_conclusion_section(report_config))

        # Phase 39A: тек НАҚТЫ кері байланыс дерегі бар болғанда ғана
        # қосылады — ескі есептер (feedback_result=None) МҮЛДЕ
        # өзгеріссіз рендерленеді.
        if feedback_result is not None and assessment is not None:
            add_section(self._build_level1_result_section(feedback_result))
            add_section(self._build_level2_answers_section(assessment, feedback_result))
            add_section(self._build_level3_reflection_section(assessment, feedback_result))
            # Мұғалім бағасы ТЕК feedback_result.teacher_assessment бар
            # болғанда рендерленеді — Оқушы режиміне арналған нұсқа
            # (ExperimentWorkspacePage-тен ``build_student_safe_result()``
            # арқылы келген) бұл өрісті ЕШҚАШАН қамтымайды, сондықтан
            # бұл диалог рөлге тәуелсіз, тек берілген дерекке сүйенеді.
            if feedback_result.teacher_assessment is not None:
                add_section(self._build_teacher_assessment_section(feedback_result))

    def _build_section_frame(self, title: str) -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame(self)
        frame.setObjectName("GuideSection")
        frame.setFrameShape(QFrame.Shape.StyledPanel)

        title_label = QLabel(title, frame)
        title_label.setProperty("role", "sectionTitle")

        layout = QVBoxLayout(frame)
        layout.addWidget(title_label)
        return frame, layout

    def _build_bullet_section(self, title: str, items: tuple[str, ...]) -> QFrame | None:
        if not items:
            return None
        frame, layout = self._build_section_frame(title)
        for item in items:
            item_label = QLabel(f"•  {item}", frame)
            item_label.setWordWrap(True)
            layout.addWidget(item_label)
        return frame

    def _build_measured_values_section(self, report_data: ExperimentReportData) -> QFrame:
        frame, layout = self._build_section_frame(_SECTION_TITLE_MEASURED_VALUES)

        summary_label = QLabel(
            f"Өлшеу саны: {report_data.sample_count}      "
            f"Ұзақтығы: {report_data.duration_seconds:.1f} с",
            frame,
        )
        layout.addWidget(summary_label)

        for stats in report_data.channel_statistics:
            layout.addWidget(self._build_channel_stats_label(frame, stats))
        return frame

    def _build_channel_stats_label(
        self, parent: QWidget, stats: ChannelReportStatistics
    ) -> QLabel:
        if stats.n == 0:
            text = f"{stats.display_name}: {_NO_VALUE_TEXT}"
        else:
            unit = stats.unit
            decimals = stats.decimals
            text = (
                f"{stats.display_name} (N={stats.n})   "
                f"соңғы {stats.latest:.{decimals}f} {unit}   "
                f"орташа {stats.average:.{decimals}f} {unit}   "
                f"min {stats.minimum:.{decimals}f} {unit}   "
                f"max {stats.maximum:.{decimals}f} {unit}"
            ).rstrip()
        label = QLabel(text, parent)
        label.setWordWrap(True)
        return label

    def _build_graph_section(self, graph_pixmap: QPixmap | None) -> QFrame | None:
        if graph_pixmap is None or graph_pixmap.isNull():
            return None
        frame, layout = self._build_section_frame(_SECTION_TITLE_GRAPHS)
        image_label = QLabel(frame)
        image_label.setPixmap(graph_pixmap)
        layout.addWidget(image_label)
        return frame

    def _build_calculated_quantities_section(
        self, report_data: ExperimentReportData
    ) -> QFrame | None:
        lines: list[str] = []

        result = report_data.fit_result
        if result is not None and result.slope is not None and result.intercept is not None:
            unit_suffix = f" {report_data.fit_unit}" if report_data.fit_unit else ""
            prefix = report_data.fit_result_prefix
            if report_data.fit_display_name:
                prefix = f"{report_data.fit_display_name} ({prefix})"
            lines.append(
                f"{report_data.fit_y_symbol} = {result.slope:.3f}·{report_data.fit_x_symbol} "
                f"+ {result.intercept:.3f}"
            )
            lines.append(f"{prefix} = {result.slope:.3f}{unit_suffix}")
            if result.r_squared is not None:
                lines.append(f"R² = {result.r_squared:.3f}")

        if report_data.power_average is not None:
            lines.append(f"Орташа қуат (P) = {report_data.power_average:.3f} W")

        if report_data.work_energy is not None:
            lines.append(f"Жұмыс/энергия (A) = {report_data.work_energy:.3f} J")

        if not lines:
            return None

        frame, layout = self._build_section_frame(_SECTION_TITLE_CALCULATED)
        for line in lines:
            line_label = QLabel(line, frame)
            line_label.setWordWrap(True)
            layout.addWidget(line_label)
        return frame

    def _build_automatic_analysis_section(self, automatic_conclusion: str) -> QFrame | None:
        """Phase 38B: ``domain.services.experiment_conclusion.
        build_automatic_conclusion()``-тан дайын келген мәтінді ТЕК
        көрсететін, оқуға арналған (read-only) секция — жаңа есептеу
        жасамайды, студенттің өз "Қорытынды" өрісін алмастырмайды (сол
        секция ӨЗГЕРІССІЗ, тура осының астында қалады).
        """
        if not automatic_conclusion:
            return None
        frame, layout = self._build_section_frame(_SECTION_TITLE_AUTOMATIC_ANALYSIS)
        text_label = QLabel(automatic_conclusion, frame)
        text_label.setWordWrap(True)
        layout.addWidget(text_label)
        return frame

    def _build_conclusion_section(self, report_config: ExperimentReport) -> QFrame:
        frame, layout = self._build_section_frame(_SECTION_TITLE_CONCLUSION)
        if report_config.conclusion_prompt:
            prompt_label = QLabel(report_config.conclusion_prompt, frame)
            prompt_label.setProperty("role", "secondary")
            prompt_label.setWordWrap(True)
            layout.addWidget(prompt_label)

        self.conclusion_edit = QTextEdit(frame)
        self.conclusion_edit.setPlaceholderText(
            "Тәжірибе нәтижелері бойынша қорытындыңызды осы жерге жазыңыз."
        )
        self.conclusion_edit.setMinimumHeight(120)
        layout.addWidget(self.conclusion_edit)
        return frame

    def _build_level1_result_section(self, feedback_result: ExperimentFeedbackResult) -> QFrame:
        frame, layout = self._build_section_frame(_SECTION_TITLE_LEVEL1_RESULT)
        if feedback_result.is_draft:
            status_label = QLabel(_DRAFT_STATUS_TEXT, frame)
            status_label.setProperty("role", "secondary")
            layout.addWidget(status_label)
        else:
            result_label = QLabel(
                f"{feedback_result.level1_score}/{feedback_result.level1_total} "
                f"({feedback_result.level1_percentage:.0f}%)",
                frame,
            )
            layout.addWidget(result_label)
        return frame

    def _build_level2_answers_section(
        self, assessment: ExperimentAssessmentDefinition, feedback_result: ExperimentFeedbackResult
    ) -> QFrame | None:
        if not assessment.level2_questions:
            return None
        frame, layout = self._build_section_frame(_SECTION_TITLE_LEVEL2_ANSWERS)
        answers_by_question = {a.question_id: a.response_text for a in feedback_result.level2_answers}
        for question in assessment.level2_questions:
            prompt_label = QLabel(question.prompt, frame)
            prompt_label.setProperty("role", "secondary")
            prompt_label.setWordWrap(True)
            layout.addWidget(prompt_label)
            answer_label = QLabel(answers_by_question.get(question.id) or _NO_VALUE_TEXT, frame)
            answer_label.setWordWrap(True)
            layout.addWidget(answer_label)

        status_label = QLabel(_TEACHER_REVIEW_STATUS_TEXT, frame)
        status_label.setProperty("role", "secondary")
        layout.addWidget(status_label)
        return frame

    def _build_level3_reflection_section(
        self, assessment: ExperimentAssessmentDefinition, feedback_result: ExperimentFeedbackResult
    ) -> QFrame | None:
        if not assessment.level3_questions:
            return None
        frame, layout = self._build_section_frame(_SECTION_TITLE_LEVEL3_REFLECTION)
        answers_by_question = {a.question_id: a.response_text for a in feedback_result.level3_answers}
        for question in assessment.level3_questions:
            prompt_label = QLabel(question.prompt, frame)
            prompt_label.setProperty("role", "secondary")
            prompt_label.setWordWrap(True)
            layout.addWidget(prompt_label)
            answer_label = QLabel(answers_by_question.get(question.id) or _NO_VALUE_TEXT, frame)
            answer_label.setWordWrap(True)
            layout.addWidget(answer_label)

        if feedback_result.self_assessment is not None:
            self_assessment_label = QLabel(
                f"Өзін-өзі бағалау: {feedback_result.self_assessment}/"
                f"{assessment.self_assessment_max}",
                frame,
            )
            layout.addWidget(self_assessment_label)
        return frame

    def _build_teacher_assessment_section(
        self, feedback_result: ExperimentFeedbackResult
    ) -> QFrame | None:
        teacher_assessment = feedback_result.teacher_assessment
        if teacher_assessment is None:
            return None
        frame, layout = self._build_section_frame(_SECTION_TITLE_TEACHER_ASSESSMENT)
        score_label = QLabel(f"Баға: {teacher_assessment.score}/10", frame)
        layout.addWidget(score_label)
        if teacher_assessment.comment:
            comment_label = QLabel(teacher_assessment.comment, frame)
            comment_label.setWordWrap(True)
            layout.addWidget(comment_label)
        reviewed_label = QLabel(
            "Қаралды" if teacher_assessment.reviewed else "Қаралмаған", frame
        )
        reviewed_label.setProperty("role", "secondary")
        layout.addWidget(reviewed_label)
        return frame
