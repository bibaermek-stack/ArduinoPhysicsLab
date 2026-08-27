"""PlaceholderPage — юнит-тесттері (Phase 37A)."""

import sys

import pytest
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from ui.pages.placeholder_page import PlaceholderPage


@pytest.fixture(scope="module", autouse=True)
def qt_application() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_title_and_description_rendered_as_labels() -> None:
    page = PlaceholderPage("Бақылау тақтасы", "Сынып бойынша жалпы шолу.")
    texts = [label.text() for label in page.findChildren(QLabel)]

    assert "Бақылау тақтасы" in texts
    assert "Сынып бойынша жалпы шолу." in texts


def test_status_text_always_present() -> None:
    page = PlaceholderPage("Кез келген тақырып", "Кез келген сипаттама.")
    texts = [label.text() for label in page.findChildren(QLabel)]

    assert "Келесі кезеңде іске асырылады" in texts


def test_back_button_click_emits_signal() -> None:
    page = PlaceholderPage("Тақырып", "Сипаттама")
    received = []
    page.back_requested.connect(lambda: received.append(True))
    back_button = next(b for b in page.findChildren(QPushButton) if b.text() == "← Артқа")

    back_button.click()

    assert received == [True]


def test_no_fabricated_data_beyond_given_text() -> None:
    """Тек берілген title/description/status көрсетіледі — ешбір
    статистика/сан/нәтиже ойдан шығарылмайды.
    """
    page = PlaceholderPage("Нәтижелер", "Оқушылардың нәтижелерін қарау.")
    texts = [label.text() for label in page.findChildren(QLabel)]

    assert len(texts) == 3  # title + description + status, ешбір қосымша жоқ


def test_different_instances_have_independent_text() -> None:
    dashboard_page = PlaceholderPage("Бақылау тақтасы", "Сипаттама 1")
    classes_page = PlaceholderPage("Сыныптар мен оқушылар", "Сипаттама 2")

    dashboard_texts = [label.text() for label in dashboard_page.findChildren(QLabel)]
    classes_texts = [label.text() for label in classes_page.findChildren(QLabel)]

    assert "Бақылау тақтасы" in dashboard_texts
    assert "Сыныптар мен оқушылар" in classes_texts
    assert "Бақылау тақтасы" not in classes_texts


# =====================================================================
# "Нәтижелер" беті: артық "← Артқа" control-ды алып тастау
# (show_back_button=False) — ескі мінез-құлық (default True) басқа
# placeholder route-тар (Аналитика/Сұрақтар банкі) үшін ӨЗГЕРІССІЗ қалуы
# керек.
# =====================================================================


def test_show_back_button_default_true_keeps_old_behavior() -> None:
    page = PlaceholderPage("Тақырып", "Сипаттама")

    buttons = [b for b in page.findChildren(QPushButton) if b.text() == "← Артқа"]

    assert len(buttons) == 1


def test_show_back_button_false_removes_button_entirely() -> None:
    page = PlaceholderPage("Нәтижелер", "Сипаттама", show_back_button=False)

    buttons = [b for b in page.findChildren(QPushButton) if b.text() == "← Артқа"]

    assert buttons == []


def test_show_back_button_false_title_becomes_first_layout_item() -> None:
    """§ "page title/content to naturally move upward" — батырма жоқта
    тақырып layout-тың БІРІНШІ элементі болуы керек (спейсер/бос орын
    ЖОҚ)."""
    page = PlaceholderPage("Нәтижелер", "Сипаттама", show_back_button=False)

    layout = page.layout()
    first_item_widget = layout.itemAt(0).widget()

    assert isinstance(first_item_widget, QLabel)
    assert first_item_widget.text() == "Нәтижелер"


def test_show_back_button_false_never_emits_back_requested() -> None:
    page = PlaceholderPage("Нәтижелер", "Сипаттама", show_back_button=False)
    received = []
    page.back_requested.connect(lambda: received.append(True))

    # Ешбір батырма жоқ болғандықтан, ешбір user interaction сигналды
    # шығара алмайды — тек ол ешқашан ЕШТЕҢЕден шақырылмайтынын растайды.
    assert page.findChildren(QPushButton) == []
    assert received == []
