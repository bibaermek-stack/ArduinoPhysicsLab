"""HelpPage юнит-тесттері (Phase — Help/About)."""

import sys

import pytest
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QPushButton

from core.version import __version__
from ui.pages.help_page import HelpPage
from ui.pages.placeholder_page import PlaceholderPage


@pytest.fixture(scope="module", autouse=True)
def qt_application() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def _panel_titles(page: HelpPage) -> list[str]:
    titles = []
    for frame in page.findChildren(QFrame):
        if frame.objectName() != "DashboardPanel":
            continue
        for label in frame.findChildren(QLabel):
            if label.property("role") == "cardTitle":
                titles.append(label.text())
    return titles


# =====================================================================
# §1-2: Placeholder өшірілген, "← Артқа" ЖОҚ.
# =====================================================================


def test_help_page_is_not_a_placeholder() -> None:
    page = HelpPage()
    assert not isinstance(page, PlaceholderPage)


def test_help_page_has_no_back_requested_signal() -> None:
    page = HelpPage()
    assert not hasattr(page, "back_requested")


def test_help_page_has_no_back_button() -> None:
    page = HelpPage()
    assert all(button.text() != "← Артқа" for button in page.findChildren(QPushButton))


# =====================================================================
# §3: Тақырып/субтитр.
# =====================================================================


def test_title_and_subtitle_text() -> None:
    page = HelpPage()
    labels = [label.text() for label in page.findChildren(QLabel)]
    assert "Анықтама" in labels
    assert (
        "Arduino Physics Lab жүйесін пайдалану бойынша қысқаша нұсқаулық" in labels
    )


# =====================================================================
# §4-5: FAQ сұрақтары/аккордион.
# =====================================================================


def test_all_four_faq_questions_present() -> None:
    page = HelpPage()
    expected = {
        "Құрылғыны қалай қосуға болады?",
        "Зертханалық жұмысты қалай бастауға болады?",
        "Өлшеу нәтижелерін қайдан көруге болады?",
        "Құрылғы анықталмаса не істеу керек?",
    }
    actual = {button.text() for button in page._faq_buttons}
    assert actual == expected


def test_faq_answers_hidden_by_default() -> None:
    page = HelpPage()
    assert all(not answer.isVisible() for answer in page._faq_answers)
    assert all(not button.isChecked() for button in page._faq_buttons)


def test_faq_expands_on_click() -> None:
    page = HelpPage()
    page.show()

    page._faq_buttons[0].click()

    assert page._faq_answers[0].isVisible()
    assert "USB" in page._faq_answers[0].text()


def test_faq_collapses_on_second_click() -> None:
    page = HelpPage()
    page.show()

    page._faq_buttons[0].click()
    page._faq_buttons[0].click()

    assert not page._faq_answers[0].isVisible()


def test_only_one_faq_open_at_a_time() -> None:
    page = HelpPage()
    page.show()

    page._faq_buttons[0].click()
    assert page._faq_answers[0].isVisible()

    page._faq_buttons[2].click()

    assert not page._faq_answers[0].isVisible()
    assert not page._faq_buttons[0].isChecked()
    assert page._faq_answers[2].isVisible()


# =====================================================================
# §7-8: Бағдарлама туралы.
# =====================================================================


def test_about_section_present() -> None:
    page = HelpPage()
    assert "Бағдарлама туралы" in _panel_titles(page)


def test_version_displayed() -> None:
    """§ Phase 9 "one canonical version source" — ``core/version.py``
    мәні көрсетіледі, ЕШБІР қатты кодталған "1.0.0" емес."""
    page = HelpPage()
    labels = [label.text() for label in page.findChildren(QLabel)]
    assert __version__ in labels


def test_about_section_shows_platform_language_and_mode() -> None:
    page = HelpPage()
    labels = [label.text() for label in page.findChildren(QLabel)]
    assert "Windows" in labels
    assert "Қазақша" in labels
    assert "Мұғалім / Оқушы" in labels


def test_about_section_does_not_invent_company_or_contact_info() -> None:
    page = HelpPage()
    labels = " ".join(label.text() for label in page.findChildren(QLabel))
    assert "@" not in labels
    assert "http" not in labels
    assert "©" not in labels


# =====================================================================
# §9: Негізгі бөлімдер.
# =====================================================================


def test_main_sections_present() -> None:
    page = HelpPage()
    assert "Негізгі бөлімдер" in _panel_titles(page)


def test_main_sections_lists_all_eight_entries() -> None:
    page = HelpPage()
    labels = [label.text() for label in page.findChildren(QLabel)]
    expected_titles = (
        "Бақылау тақтасы",
        "Сыныптар мен оқушылар",
        "Зертханалық жұмыстар",
        "Нәтижелер",
        "Деректер журналы",
        "Кері байланысты тексеру",
        "Аналитика",
        "Құрылғылар",
    )
    for title in expected_titles:
        assert any(title in text for text in labels)


# =====================================================================
# §10-11: Route/placeholder регрессиясы.
# =====================================================================


def test_help_route_no_longer_placeholder_via_main_window() -> None:
    from ui.main_window import MainWindow

    window = MainWindow()
    assert isinstance(window._about_page, HelpPage)
    assert not isinstance(window._about_page, PlaceholderPage)
    assert window._router._pages["about"] is window._about_page


def test_question_bank_placeholder_behavior_unaffected() -> None:
    """§11 "Existing Question Bank placeholder behavior is NOT accidentally
    changed" — Help беті QuestionBankPage-ті ЕШБІР жаңармайды/ауыстырмайды."""
    from ui.main_window import MainWindow
    from ui.pages.question_bank_page import QuestionBankPage

    window = MainWindow()
    assert isinstance(window._question_bank_page, QuestionBankPage)
    assert window._router._pages["question_bank"] is window._question_bank_page


# =====================================================================
# §12: Watermark/theme.
# =====================================================================


def test_help_page_listed_in_transparent_root_classes() -> None:
    from ui.themes.theme_manager import ThemeManager

    stylesheet = ThemeManager().build_stylesheet()
    assert "HelpPage" in stylesheet


def test_help_page_root_has_no_instance_level_stylesheet() -> None:
    page = HelpPage()
    assert page.styleSheet() == ""


def test_faq_header_buttons_use_leaf_widget_style_override_only() -> None:
    """§ established leaf-widget pattern — FAQ header батырмасының
    instance stylesheet-і ТЕК text-align/padding орнатады, background-
    color/border-ды ЕШҚАШАН қайта анықтамайды (глобал QSS-тен мұраланады)."""
    page = HelpPage()
    for button in page._faq_buttons:
        assert "background-color" not in button.styleSheet()
        assert "border" not in button.styleSheet()


# =====================================================================
# Жұмысты бастау / Жиі кездесетін мәселелер (content completion).
# =====================================================================


def test_workflow_section_present() -> None:
    page = HelpPage()
    assert "Жұмысты бастау" in _panel_titles(page)


def test_workflow_step_titles_present() -> None:
    page = HelpPage()
    labels = [label.text() for label in page.findChildren(QLabel)]
    for title in ("Құрылғыны қосу", "Зертханалық жұмысты таңдау", "Өлшеуді бастау"):
        assert title in labels


def test_workflow_step_numbers_present() -> None:
    page = HelpPage()
    labels = [label.text() for label in page.findChildren(QLabel)]
    for number in ("1", "2", "3"):
        assert number in labels


def test_troubleshooting_section_present() -> None:
    page = HelpPage()
    assert "Жиі кездесетін мәселелер" in _panel_titles(page)


def test_troubleshooting_titles_present() -> None:
    page = HelpPage()
    labels = [label.text() for label in page.findChildren(QLabel)]
    for title in (
        "COM порт көрінбейді",
        "Сенсордан дерек келмейді",
        "Құрылғы байланысы үзіліп қалды",
    ):
        assert title in labels


def test_faq_accordion_still_works_after_content_completion() -> None:
    page = HelpPage()
    page.show()

    page._faq_buttons[0].click()
    assert page._faq_answers[0].isVisible()

    page._faq_buttons[0].click()
    assert not page._faq_answers[0].isVisible()


def test_right_column_about_content_unchanged() -> None:
    page = HelpPage()
    labels = [label.text() for label in page.findChildren(QLabel)]
    assert "Бағдарлама туралы" in _panel_titles(page)
    assert "Arduino Physics Lab" in labels
    assert __version__ in labels
    assert "Windows" in labels
    assert "Қазақша" in labels
    assert "Мұғалім / Оқушы" in labels


def test_faq_panel_no_longer_stretches_to_fill_height() -> None:
    """§ "Do not stretch the FAQ container to the full available height
    anymore" — панель тек ӨЗ мазмұнына қажетті биіктікті алады."""
    page = HelpPage()
    page.resize(1366, 768)
    page.show()

    faq_panel = next(
        frame
        for frame in page.findChildren(QFrame)
        if frame.objectName() == "DashboardPanel"
        and any(
            label.property("role") == "cardTitle" and label.text() == "Жылдам көмек"
            for label in frame.findChildren(QLabel)
        )
    )
    assert faq_panel.height() < 300


# =====================================================================
# Геометрия — 1366x768 және 1920x1080.
# =====================================================================


def test_1366x768_smoke_layout() -> None:
    page = HelpPage()
    page.resize(1366, 768)
    page.show()

    assert page.width() == 1366
    assert _panel_titles(page) == [
        "Жылдам көмек",
        "Жұмысты бастау",
        "Жиі кездесетін мәселелер",
        "Бағдарлама туралы",
        "Негізгі бөлімдер",
    ]


def test_1920x1080_smoke_layout() -> None:
    page = HelpPage()
    page.resize(1920, 1080)
    page.show()

    assert page.width() == 1920
    assert _panel_titles(page) == [
        "Жылдам көмек",
        "Жұмысты бастау",
        "Жиі кездесетін мәселелер",
        "Бағдарлама туралы",
        "Негізгі бөлімдер",
    ]


def test_no_scroll_area_present() -> None:
    from PySide6.QtWidgets import QScrollArea

    page = HelpPage()
    assert page.findChildren(QScrollArea) == []
