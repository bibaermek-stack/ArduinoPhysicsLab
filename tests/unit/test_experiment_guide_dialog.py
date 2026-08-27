"""ExperimentGuideDialog (Phase 35) үшін юнит-тесттер: секциялардың
бар/жоқтығы, нөмірленген тізімдер, формула көрсетілуі, скролл аймағы,
Жабу батырмасы.
"""

import sys

import pytest
from PySide6.QtWidgets import QApplication, QScrollArea

from domain.entities.experiment_definition import ExperimentGuide
from ui.widgets.experiment_guide_dialog import ExperimentGuideDialog


@pytest.fixture(scope="module", autouse=True)
def qt_application() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def _full_guide() -> ExperimentGuide:
    return ExperimentGuide(
        objective=("Мақсат 1", "Мақсат 2"),
        equipment=("Кернеу датчигі", "Ток датчигі"),
        theory="Қысқа теориялық түсіндірме.",
        formulas=("U = I × R", "R = U / I"),
        procedure=("Бірінші қадам.", "Екінші қадам."),
        safety=("Қауіпсіздік ережесі.",),
        control_questions=("Бақылау сұрағы?",),
    )


def test_dialog_shows_experiment_title_and_subtitle() -> None:
    dialog = ExperimentGuideDialog("Тізбек бөлігі үшін кернеудің ток күшіне тәуелділігін зерттеу", _full_guide())

    assert "Тізбек бөлігі үшін кернеудің ток күшіне тәуелділігін зерттеу" in dialog.windowTitle()


def test_dialog_contains_scroll_area() -> None:
    dialog = ExperimentGuideDialog("Тізбек бөлігі үшін кернеудің ток күшіне тәуелділігін зерттеу", _full_guide())

    scroll_areas = dialog.findChildren(QScrollArea)

    assert len(scroll_areas) == 1
    assert scroll_areas[0].widgetResizable() is True


def test_dialog_has_close_button_that_closes_dialog() -> None:
    dialog = ExperimentGuideDialog("Тізбек бөлігі үшін кернеудің ток күшіне тәуелділігін зерттеу", _full_guide())
    dialog.show()
    assert dialog.isVisible() is True

    dialog._close_button.click()

    assert dialog.isVisible() is False


def test_all_seven_sections_rendered_when_fully_populated() -> None:
    dialog = ExperimentGuideDialog("Тізбек бөлігі үшін кернеудің ток күшіне тәуелділігін зерттеу", _full_guide())

    # addStretch(1) + 7 секция.
    assert dialog._sections_layout.count() == 8


def test_empty_sections_are_not_rendered() -> None:
    """§6: бос tuple/str секциясы ЕШҚАШАН карточка ретінде көрсетілмейді."""
    guide = ExperimentGuide(objective=("Жалғыз мақсат",), formulas=("U = IR",))

    dialog = ExperimentGuideDialog("Тест", guide)

    # тек 2 секция (objective, formulas) + stretch.
    assert dialog._sections_layout.count() == 3


def test_completely_empty_guide_renders_no_sections() -> None:
    dialog = ExperimentGuideDialog("Тест", ExperimentGuide())

    assert dialog._sections_layout.count() == 1  # тек addStretch(1)


def test_procedure_steps_are_numbered_by_the_dialog_not_the_strings() -> None:
    from PySide6.QtWidgets import QLabel

    guide = ExperimentGuide(procedure=("Біріншісін жаса.", "Екіншісін жаса."))
    dialog = ExperimentGuideDialog("Тест", guide)

    section = dialog._build_numbered_section("Жұмысты орындау тәртібі", guide.procedure)
    texts = [label.text() for label in section.findChildren(QLabel)]

    assert "1. Біріншісін жаса." in texts
    assert "2. Екіншісін жаса." in texts


def test_control_questions_are_numbered() -> None:
    from PySide6.QtWidgets import QLabel

    guide = ExperimentGuide(control_questions=("Бірінші сұрақ?", "Екінші сұрақ?"))
    dialog = ExperimentGuideDialog("Тест", guide)

    section = dialog._build_numbered_section("Бақылау сұрақтары", guide.control_questions)
    texts = [label.text() for label in section.findChildren(QLabel)]

    assert "1. Бірінші сұрақ?" in texts
    assert "2. Екінші сұрақ?" in texts


def test_formulas_rendered_as_plain_unicode_text() -> None:
    from PySide6.QtWidgets import QLabel

    guide = ExperimentGuide(formulas=("U = I × R", "R = ΔU / ΔI"))
    dialog = ExperimentGuideDialog("Тест", guide)

    section = dialog._build_formula_section("Негізгі формулалар", guide.formulas)
    texts = [label.text() for label in section.findChildren(QLabel)]

    assert "U = I × R" in texts
    assert "R = ΔU / ΔI" in texts


def test_objective_and_equipment_rendered_as_bullets() -> None:
    from PySide6.QtWidgets import QLabel

    guide = ExperimentGuide(objective=("Бірінші мақсат.",))
    dialog = ExperimentGuideDialog("Тест", guide)

    section = dialog._build_bullet_section("Жұмыстың мақсаты", guide.objective)
    texts = [label.text() for label in section.findChildren(QLabel)]

    assert any("Бірінші мақсат." in text and text.startswith("•") for text in texts)


def test_dialog_never_touches_unrelated_state() -> None:
    """Архитектуралық кепілдік: диалог тек title/guide алады — ешбір
    graph/measurement/coordinator сілтемесі жоқ, сондықтан ашу/жабу
    оларға ЕШҚАШАН тие алмайды (§15).
    """
    import inspect

    signature = inspect.signature(ExperimentGuideDialog.__init__)
    assert set(signature.parameters.keys()) == {"self", "experiment_title", "guide", "parent"}
