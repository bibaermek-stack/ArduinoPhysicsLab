"""ExperimentReportDialog (Phase 36) үшін юнит-тесттер: секциялардың
бар/жоқтығы (§ "hidden fields for unavailable calculations"), формула/
статистика көрсетілуі, бос қорытынды өрісі, скролл аймағы.
"""

import sys

import pytest
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QScrollArea, QTextEdit

from domain.entities.experiment_assessment import (
    ExperimentAssessmentDefinition,
    MultipleChoiceQuestion,
    OpenResponseQuestion,
    ReflectionQuestion,
)
from domain.entities.experiment_definition import ExperimentGuide, ExperimentReport
from domain.entities.experiment_feedback_result import (
    ExperimentFeedbackResult,
    MultipleChoiceAnswer,
    OpenResponseAnswer,
    ReflectionAnswer,
    TeacherAssessment,
)
from domain.services.experiment_report_data import ChannelReportStatistics, ExperimentReportData
from domain.services.graph_analysis import RegressionResult
from ui.widgets.experiment_report_dialog import ExperimentReportDialog


@pytest.fixture(scope="module", autouse=True)
def qt_application() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def _voltage_stats(n=5, latest=5.0, minimum=4.5, maximum=5.5, average=5.0) -> ChannelReportStatistics:
    return ChannelReportStatistics("voltage", "Кернеу", "V", 3, n, latest, minimum, maximum, average)


def _empty_data() -> ExperimentReportData:
    return ExperimentReportData(sample_count=0, duration_seconds=0.0, channel_statistics=())


def test_dialog_window_title_includes_experiment_and_report_title() -> None:
    report_config = ExperimentReport(title="Зертханалық есеп")
    dialog = ExperimentReportDialog("Тізбек бөлігі үшін кернеудің ток күшіне тәуелділігін зерттеу", None, report_config, _empty_data(), None)

    assert "Тізбек бөлігі үшін кернеудің ток күшіне тәуелділігін зерттеу" in dialog.windowTitle()
    assert "Зертханалық есеп" in dialog.windowTitle()


def test_dialog_contains_scroll_area() -> None:
    dialog = ExperimentReportDialog("Тест", None, ExperimentReport(), _empty_data(), None)

    scroll_areas = dialog.findChildren(QScrollArea)

    assert len(scroll_areas) == 1
    assert scroll_areas[0].widgetResizable() is True


def test_measured_values_section_always_present() -> None:
    dialog = ExperimentReportDialog("Тест", None, ExperimentReport(), _empty_data(), None)

    from PySide6.QtWidgets import QLabel

    texts = [label.text() for label in dialog.findChildren(QLabel)]
    assert any("Өлшенген мәндер" in text for text in texts)


def test_measured_values_shows_no_value_dash_for_empty_channel() -> None:
    from PySide6.QtWidgets import QLabel

    data = ExperimentReportData(
        sample_count=0,
        duration_seconds=0.0,
        channel_statistics=(
            ChannelReportStatistics("voltage", "Кернеу", "V", 3, 0, None, None, None, None),
        ),
    )
    dialog = ExperimentReportDialog("Тест", None, ExperimentReport(), data, None)

    texts = [label.text() for label in dialog.findChildren(QLabel)]
    assert any("Кернеу: —" in text for text in texts)


def test_measured_values_shows_real_statistics() -> None:
    from PySide6.QtWidgets import QLabel

    data = ExperimentReportData(
        sample_count=5, duration_seconds=12.5, channel_statistics=(_voltage_stats(),)
    )
    dialog = ExperimentReportDialog("Тест", None, ExperimentReport(), data, None)

    texts = "\n".join(label.text() for label in dialog.findChildren(QLabel))
    assert "5.000 V" in texts  # соңғы мән
    assert "N=5" in texts


def test_purpose_and_equipment_hidden_without_guide() -> None:
    from PySide6.QtWidgets import QLabel

    dialog = ExperimentReportDialog("Тест", None, ExperimentReport(), _empty_data(), None)

    texts = [label.text() for label in dialog.findChildren(QLabel)]
    assert not any("Жұмыстың мақсаты" in text for text in texts)
    assert not any("Қажетті құрал-жабдықтар" in text for text in texts)


def test_purpose_and_equipment_reused_from_guide() -> None:
    from PySide6.QtWidgets import QLabel

    guide = ExperimentGuide(objective=("Мақсат мәтіні",), equipment=("Датчик",))
    dialog = ExperimentReportDialog("Тест", guide, ExperimentReport(), _empty_data(), None)

    texts = [label.text() for label in dialog.findChildren(QLabel)]
    assert any("Жұмыстың мақсаты" in text for text in texts)
    assert any("Мақсат мәтіні" in text for text in texts)
    assert any("Датчик" in text for text in texts)


def test_graph_section_hidden_when_pixmap_none() -> None:
    from PySide6.QtWidgets import QLabel

    dialog = ExperimentReportDialog("Тест", None, ExperimentReport(), _empty_data(), None)

    texts = [label.text() for label in dialog.findChildren(QLabel)]
    assert not any("График" == text for text in texts)


def test_graph_section_shown_when_pixmap_present() -> None:
    from PySide6.QtWidgets import QLabel

    pixmap = QPixmap(10, 10)
    pixmap.fill()
    dialog = ExperimentReportDialog("Тест", None, ExperimentReport(), _empty_data(), pixmap)

    texts = [label.text() for label in dialog.findChildren(QLabel)]
    assert any("График" in text for text in texts)


def test_calculated_quantities_hidden_when_nothing_available() -> None:
    """§ "hidden fields for unavailable calculations": fit/power/work
    барлығы None болса, секцияның ӨЗІ мүлде салынбайды.
    """
    from PySide6.QtWidgets import QLabel

    dialog = ExperimentReportDialog("Тест", None, ExperimentReport(), _empty_data(), None)

    texts = [label.text() for label in dialog.findChildren(QLabel)]
    assert not any("Есептелген шамалар" in text for text in texts)


def test_calculated_quantities_shows_only_available_fit_result() -> None:
    from PySide6.QtWidgets import QLabel

    data = ExperimentReportData(
        sample_count=5,
        duration_seconds=5.0,
        channel_statistics=(),
        fit_result=RegressionResult(
            valid=True, slope=87.68, intercept=-0.073, r_squared=1.0, rmse=0.0, n=5
        ),
        fit_x_symbol="I",
        fit_y_symbol="U",
        fit_result_prefix="R",
        fit_unit="Ω",
        fit_display_name="Кедергі",
    )
    dialog = ExperimentReportDialog("Тест", None, ExperimentReport(), data, None)

    texts = "\n".join(label.text() for label in dialog.findChildren(QLabel))
    assert "Есептелген шамалар" in texts
    assert "Кедергі (R) = 87.680 Ω" in texts
    assert "R² = 1.000" in texts
    # Power/work деректері жоқ болғандықтан, олардың мәтіні шықпауы тиіс.
    assert "Орташа қуат" not in texts
    assert "Жұмыс/энергия" not in texts


def test_calculated_quantities_shows_power_and_work_when_available() -> None:
    from PySide6.QtWidgets import QLabel

    data = ExperimentReportData(
        sample_count=5,
        duration_seconds=5.0,
        channel_statistics=(),
        power_average=1.234,
        work_energy=6.789,
    )
    dialog = ExperimentReportDialog("Тест", None, ExperimentReport(), data, None)

    texts = "\n".join(label.text() for label in dialog.findChildren(QLabel))
    assert "1.234 W" in texts
    assert "6.789 J" in texts


def test_conclusion_field_is_empty_text_edit() -> None:
    dialog = ExperimentReportDialog("Тест", None, ExperimentReport(), _empty_data(), None)

    text_edits = dialog.findChildren(QTextEdit)
    assert len(text_edits) == 1
    assert text_edits[0].toPlainText() == ""
    assert dialog.conclusion_edit is text_edits[0]


def test_conclusion_prompt_shown_when_configured() -> None:
    from PySide6.QtWidgets import QLabel

    report_config = ExperimentReport(conclusion_prompt="Тәжірибе нәтижесі бойынша жазыңыз.")
    dialog = ExperimentReportDialog("Тест", None, report_config, _empty_data(), None)

    texts = [label.text() for label in dialog.findChildren(QLabel)]
    assert any("Тәжірибе нәтижесі бойынша жазыңыз." in text for text in texts)


def test_close_button_closes_dialog() -> None:
    dialog = ExperimentReportDialog("Тест", None, ExperimentReport(), _empty_data(), None)
    dialog.show()
    assert dialog.isVisible() is True

    dialog._close_button.click()

    assert dialog.isVisible() is False


# ---- Phase 38B: "Автоматты талдау" секциясы ------------------------------


def test_automatic_analysis_section_hidden_when_empty_string() -> None:
    from PySide6.QtWidgets import QLabel

    dialog = ExperimentReportDialog(
        "Тест", None, ExperimentReport(), _empty_data(), None, automatic_conclusion=""
    )

    texts = [label.text() for label in dialog.findChildren(QLabel)]
    assert not any("Автоматты талдау" in text for text in texts)


def test_automatic_analysis_section_hidden_by_default_when_omitted() -> None:
    from PySide6.QtWidgets import QLabel

    dialog = ExperimentReportDialog("Тест", None, ExperimentReport(), _empty_data(), None)

    texts = [label.text() for label in dialog.findChildren(QLabel)]
    assert not any("Автоматты талдау" in text for text in texts)


def test_automatic_analysis_section_shown_with_passed_text() -> None:
    from PySide6.QtWidgets import QLabel

    dialog = ExperimentReportDialog(
        "Тест",
        None,
        ExperimentReport(),
        _empty_data(),
        None,
        automatic_conclusion="Сызықтық тәуелділік анықталды: R ≈ 12.300 Ω (R²=0.990).",
    )

    texts = "\n".join(label.text() for label in dialog.findChildren(QLabel))
    assert "Автоматты талдау" in texts
    assert "Сызықтық тәуелділік анықталды: R ≈ 12.300 Ω (R²=0.990)." in texts


def test_automatic_analysis_section_appears_above_conclusion_text_edit() -> None:
    """Студенттің өз "Қорытынды" өрісі ЕШҚАШАН алмастырылмайды — жаңа
    секция тек соның үстінде қосымша ретінде көрінеді.
    """
    dialog = ExperimentReportDialog(
        "Тест",
        None,
        ExperimentReport(),
        _empty_data(),
        None,
        automatic_conclusion="Автоматты мәтін.",
    )

    text_edits = dialog.findChildren(QTextEdit)
    assert len(text_edits) == 1
    assert text_edits[0].toPlainText() == ""
    assert dialog.conclusion_edit is text_edits[0]


# =====================================================================
# Phase 39A: Кері байланыс/бағалау секциялары
# =====================================================================


def _assessment() -> ExperimentAssessmentDefinition:
    return ExperimentAssessmentDefinition(
        level1_questions=(MultipleChoiceQuestion("l1-1", "Q?", ("A", "B"), 0),),
        level2_questions=(OpenResponseQuestion("l2-1", "Analyze the graph"),),
        level3_questions=(ReflectionQuestion("l3-1", "What did you learn?"),),
    )


def _submitted_feedback_result(teacher_assessment=None) -> ExperimentFeedbackResult:
    return ExperimentFeedbackResult(
        experiment_id="ohms-law",
        session_id="s1",
        level1_answers=(MultipleChoiceAnswer("l1-1", 0),),
        level1_score=1,
        level1_total=1,
        level1_percentage=100.0,
        level2_answers=(OpenResponseAnswer("l2-1", "Linear relationship"),),
        level3_answers=(ReflectionAnswer("l3-1", "I learned about resistance"),),
        self_assessment=4,
        is_draft=False,
        teacher_assessment=teacher_assessment,
    )


def test_no_feedback_sections_when_feedback_result_is_none() -> None:
    from PySide6.QtWidgets import QLabel

    dialog = ExperimentReportDialog(
        "Тест", None, ExperimentReport(), _empty_data(), None, assessment=_assessment()
    )

    texts = "\n".join(label.text() for label in dialog.findChildren(QLabel))
    assert "1-деңгей" not in texts
    assert "2-деңгей" not in texts
    assert "3-деңгей" not in texts
    assert "Мұғалім бағасы" not in texts


def test_level1_result_section_shows_score_when_submitted() -> None:
    from PySide6.QtWidgets import QLabel

    dialog = ExperimentReportDialog(
        "Тест",
        None,
        ExperimentReport(),
        _empty_data(),
        None,
        assessment=_assessment(),
        feedback_result=_submitted_feedback_result(),
    )

    texts = "\n".join(label.text() for label in dialog.findChildren(QLabel))
    assert "1-деңгей: Тест нәтижесі" in texts
    assert "1/1 (100%)" in texts


def test_level1_result_section_shows_draft_status_when_not_submitted() -> None:
    from PySide6.QtWidgets import QLabel

    draft = ExperimentFeedbackResult(experiment_id="ohms-law", session_id="s1", is_draft=True)
    dialog = ExperimentReportDialog(
        "Тест",
        None,
        ExperimentReport(),
        _empty_data(),
        None,
        assessment=_assessment(),
        feedback_result=draft,
    )

    texts = "\n".join(label.text() for label in dialog.findChildren(QLabel))
    assert "Жоба" in texts


def test_level2_section_shows_prompts_answers_and_review_status() -> None:
    from PySide6.QtWidgets import QLabel

    dialog = ExperimentReportDialog(
        "Тест",
        None,
        ExperimentReport(),
        _empty_data(),
        None,
        assessment=_assessment(),
        feedback_result=_submitted_feedback_result(),
    )

    texts = "\n".join(label.text() for label in dialog.findChildren(QLabel))
    assert "2-деңгей: Талдау жауаптары" in texts
    assert "Analyze the graph" in texts
    assert "Linear relationship" in texts
    assert "Мұғалім тексереді" in texts


def test_level3_section_shows_reflection_and_self_assessment() -> None:
    from PySide6.QtWidgets import QLabel

    dialog = ExperimentReportDialog(
        "Тест",
        None,
        ExperimentReport(),
        _empty_data(),
        None,
        assessment=_assessment(),
        feedback_result=_submitted_feedback_result(),
    )

    texts = "\n".join(label.text() for label in dialog.findChildren(QLabel))
    assert "3-деңгей: Рефлексия" in texts
    assert "I learned about resistance" in texts
    assert "Өзін-өзі бағалау: 4/5" in texts


def test_teacher_assessment_section_hidden_when_absent() -> None:
    from PySide6.QtWidgets import QLabel

    dialog = ExperimentReportDialog(
        "Тест",
        None,
        ExperimentReport(),
        _empty_data(),
        None,
        assessment=_assessment(),
        feedback_result=_submitted_feedback_result(teacher_assessment=None),
    )

    texts = "\n".join(label.text() for label in dialog.findChildren(QLabel))
    assert "Мұғалім бағасы" not in texts


def test_teacher_assessment_section_shown_when_present() -> None:
    from PySide6.QtWidgets import QLabel

    dialog = ExperimentReportDialog(
        "Тест",
        None,
        ExperimentReport(),
        _empty_data(),
        None,
        assessment=_assessment(),
        feedback_result=_submitted_feedback_result(
            teacher_assessment=TeacherAssessment(score=9, comment="Great job")
        ),
    )

    texts = "\n".join(label.text() for label in dialog.findChildren(QLabel))
    assert "Мұғалім бағасы" in texts
    assert "Баға: 9/10" in texts
    assert "Great job" in texts
    assert "Қаралды" in texts


def test_student_safe_result_never_renders_teacher_fields() -> None:
    """§ "Student report must not render teacher score/comment": бұл
    диалог тек берілген деректі рендерлейді — ``build_student_safe_result()``
    арқылы алдын ала тазаланған нәтиже берілсе, ешбір Мұғалім секциясы
    пайда болмайды.
    """
    from PySide6.QtWidgets import QLabel

    from domain.services.experiment_feedback_service import build_student_safe_result

    full_result = _submitted_feedback_result(
        teacher_assessment=TeacherAssessment(score=10, comment="Confidential comment")
    )
    student_safe = build_student_safe_result(full_result)

    dialog = ExperimentReportDialog(
        "Тест",
        None,
        ExperimentReport(),
        _empty_data(),
        None,
        assessment=_assessment(),
        feedback_result=student_safe,
    )

    texts = "\n".join(label.text() for label in dialog.findChildren(QLabel))
    assert "Confidential comment" not in texts
    assert "Мұғалім бағасы" not in texts


def test_old_report_call_signature_without_new_params_still_works() -> None:
    """Ескі шақыру сигнатурасы (assessment/feedback_result берілмей)
    ӘЛІ ДЕ жұмыс істеуі керек — толық backward compatibility.
    """
    dialog = ExperimentReportDialog("Тест", None, ExperimentReport(), _empty_data(), None)
    assert dialog is not None
