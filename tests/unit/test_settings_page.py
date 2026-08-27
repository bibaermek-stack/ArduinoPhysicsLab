"""SettingsPage юнит-тесттері (Phase 22)."""

import os
import sys
import tempfile

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QFrame, QLabel, QLineEdit, QPushButton

from infrastructure.storage.app_preferences import AppPreferences
from infrastructure.storage.database import get_default_database_path
from ui.pages.placeholder_page import PlaceholderPage
from ui.pages.settings_page import SettingsPage


@pytest.fixture(scope="module", autouse=True)
def qt_application() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def temp_preferences():
    handle = tempfile.NamedTemporaryFile(suffix=".ini", delete=False)
    handle.close()
    settings = QSettings(handle.name, QSettings.Format.IniFormat)
    yield AppPreferences(settings), handle.name
    os.unlink(handle.name)


def _panel_titles(page: SettingsPage) -> list[str]:
    titles = []
    for frame in page.findChildren(QFrame):
        if frame.objectName() != "DashboardPanel":
            continue
        if frame.isHidden():
            continue
        for label in frame.findChildren(QLabel):
            if label.property("role") == "cardTitle":
                titles.append(label.text())
    return titles


# =====================================================================
# §1-2: Placeholder өшірілген, "← Артқа" ЖОҚ.
# =====================================================================


def test_settings_page_is_not_a_placeholder() -> None:
    page = SettingsPage()
    assert not isinstance(page, PlaceholderPage)


def test_settings_page_has_no_back_requested_signal() -> None:
    page = SettingsPage()
    assert not hasattr(page, "back_requested")


def test_settings_page_has_no_back_button() -> None:
    page = SettingsPage()
    assert all(button.text() != "← Артқа" for button in page.findChildren(QPushButton))


# =====================================================================
# §3: Тақырып/субтитр.
# =====================================================================


def test_title_and_subtitle_text() -> None:
    page = SettingsPage()
    labels = [label.text() for label in page.findChildren(QLabel)]
    assert "Баптаулар" in labels
    assert "Arduino Physics Lab жүйесінің параметрлерін басқару" in labels


# =====================================================================
# §4: 4 бөлім.
# =====================================================================


def test_all_five_sections_present() -> None:
    """§ Multi-Teacher Accounts §7: "МҰҒАЛІМДЕР" панелі "ДЕРЕКТЕР"-ден
    кейін қосылды."""
    page = SettingsPage()
    titles = _panel_titles(page)
    assert titles == ["ЖАЛПЫ", "ӨЛШЕУ", "ҚҰРЫЛҒЫЛАР", "ДЕРЕКТЕР", "МҰҒАЛІМДЕР"]


# =====================================================================
# §5: Нақты әдепкі мәндер (fabrication жоқ).
# =====================================================================


def test_language_defaults_to_kazakh_only() -> None:
    page = SettingsPage()
    labels = [label.text() for label in page.findChildren(QLabel)]
    assert "Қазақша" in labels


def test_theme_defaults_to_light_only() -> None:
    page = SettingsPage()
    labels = [label.text() for label in page.findChildren(QLabel)]
    assert "Ашық" in labels
    # § "do NOT expose a non-working Dark option" — dark mode МҮЛДЕ ЖОҚ.
    assert not any("Қараңғы" in text or "Dark" in text for text in labels)


def test_auto_scale_checkbox_default_matches_live_graph_current_behavior() -> None:
    page = SettingsPage()
    assert page._auto_scale_checkbox.isChecked() is True


def test_baud_rate_reflects_canonical_protocol_default() -> None:
    page = SettingsPage()
    labels = [label.text() for label in page.findChildren(QLabel)]
    assert any("115200" in text for text in labels)


def test_database_row_shows_real_active_database_name() -> None:
    page = SettingsPage()
    expected_name = get_default_database_path().name
    labels = [label.text() for label in page.findChildren(QLabel)]
    assert expected_name in labels


def test_export_format_shows_only_csv() -> None:
    page = SettingsPage()
    labels = [label.text() for label in page.findChildren(QLabel)]
    assert "CSV" in labels
    # § "do not show XLSX/PDF unless they actually exist" — Data Journal
    # экспорт жолында тек CSVExporter қолданылады.
    assert not any(text in ("XLSX", "PDF", "Excel") for text in labels)


# =====================================================================
# §6: Әдейі omit етілген баптаулар — ЕШҚАШАН ойдан шығарылған контрол
# ретінде көрсетілмейді.
# =====================================================================


def test_no_fake_functional_combo_boxes_exposed() -> None:
    """§ "unsupported language/theme options not exposed" — тіл/тема/
    baud/экспорт барлығы АҚПАРАТТЫҚ QLabel, бірнеше опциясы бар жалған
    QComboBox ЕШҚАШАН жасалмайды."""
    page = SettingsPage()
    combo_boxes = page.findChildren(QComboBox)
    assert combo_boxes == []


def test_graph_window_setting_not_exposed() -> None:
    page = SettingsPage()
    labels = [label.text() for label in page.findChildren(QLabel)]
    assert not any("терезе" in text.lower() for text in labels)


def test_display_precision_setting_not_exposed() -> None:
    page = SettingsPage()
    labels = [label.text() for label in page.findChildren(QLabel)]
    assert not any("дәлдік" in text.lower() for text in labels)


def test_device_auto_refresh_setting_not_exposed() -> None:
    page = SettingsPage()
    labels = [label.text() for label in page.findChildren(QLabel)]
    assert not any("автоматты түрде жаңарту" in text.lower() for text in labels)


def test_remember_last_device_setting_not_exposed() -> None:
    page = SettingsPage()
    labels = [label.text() for label in page.findChildren(QLabel)]
    assert not any("соңғы құрылғы" in text.lower() for text in labels)


# =====================================================================
# §7-8: Баптау сақталады/қайта жүктеу кезінде қалпына келеді.
# =====================================================================


def test_toggling_auto_scale_checkbox_persists_immediately(temp_preferences) -> None:
    preferences, path = temp_preferences
    page = SettingsPage(app_preferences=preferences)

    page._auto_scale_checkbox.setChecked(False)

    reloaded = AppPreferences(QSettings(path, QSettings.Format.IniFormat))
    assert reloaded.get_auto_scale_default() is False


def test_restart_reload_restores_persisted_setting(temp_preferences) -> None:
    preferences, path = temp_preferences
    page = SettingsPage(app_preferences=preferences)
    page._auto_scale_checkbox.setChecked(False)

    # "Рестарт" эмуляциясы: СОЛ файлдан ЖАҢА AppPreferences/SettingsPage.
    reloaded_preferences = AppPreferences(QSettings(path, QSettings.Format.IniFormat))
    new_page = SettingsPage(app_preferences=reloaded_preferences)

    assert new_page._auto_scale_checkbox.isChecked() is False


def test_on_enter_resyncs_checkbox_from_preferences(temp_preferences) -> None:
    preferences, _path = temp_preferences
    page = SettingsPage(app_preferences=preferences)
    preferences.set_auto_scale_default(False)

    page.on_enter()

    assert page._auto_scale_checkbox.isChecked() is False


# =====================================================================
# §9: Reset — дерекқорға/домен деректеріне ЕШБІР қатысы жоқ.
# =====================================================================


def test_reset_button_requires_confirmation(temp_preferences, monkeypatch: pytest.MonkeyPatch) -> None:
    preferences, _path = temp_preferences
    page = SettingsPage(app_preferences=preferences)
    page._auto_scale_checkbox.setChecked(False)

    monkeypatch.setattr(page, "_confirm_reset", lambda _parent: False)
    page._reset_button.click()

    assert preferences.get_auto_scale_default() is False


def test_reset_confirmed_restores_default_auto_scale(temp_preferences, monkeypatch: pytest.MonkeyPatch) -> None:
    preferences, _path = temp_preferences
    page = SettingsPage(app_preferences=preferences)
    page._auto_scale_checkbox.setChecked(False)

    monkeypatch.setattr(page, "_confirm_reset", lambda _parent: True)
    page._reset_button.click()

    assert preferences.get_auto_scale_default() is True
    assert page._auto_scale_checkbox.isChecked() is True


def test_reset_does_not_touch_unrelated_settings_keys(temp_preferences, monkeypatch: pytest.MonkeyPatch) -> None:
    preferences, path = temp_preferences
    raw_settings = QSettings(path, QSettings.Format.IniFormat)
    raw_settings.setValue("unrelated/other_key", "should survive")
    raw_settings.sync()

    page = SettingsPage(app_preferences=preferences)
    monkeypatch.setattr(page, "_confirm_reset", lambda _parent: True)
    page._reset_button.click()

    survivor_check = QSettings(path, QSettings.Format.IniFormat)
    assert survivor_check.value("unrelated/other_key") == "should survive"


def test_reset_button_exists_at_page_bottom() -> None:
    page = SettingsPage()
    assert page._reset_button.text() == "Әдепкі баптауларды қалпына келтіру"


def test_confirm_reset_uses_kazakh_button_text_not_qdialogbuttonbox_defaults() -> None:
    from ui.pages.settings_page import _RESET_CANCEL_BUTTON, _RESET_CONFIRM_BUTTON, _RESET_CONFIRM_TEXT

    assert _RESET_CONFIRM_TEXT == "Әдепкі баптауларды қалпына келтіресіз бе?"
    assert _RESET_CONFIRM_BUTTON == "Қалпына келтіру"
    assert _RESET_CANCEL_BUTTON == "Болдырмау"


# =====================================================================
# §10: Дерекқор қауіпсіздігі — ешбір destructive DB батырма ЖОҚ.
# =====================================================================


def test_no_destructive_database_actions_exposed() -> None:
    page = SettingsPage()
    button_texts = [button.text().lower() for button in page.findChildren(QPushButton)]
    forbidden_keywords = ("өшір", "тазала", "қалпына келтір дерекқор", "factory", "drop")
    for text in button_texts:
        if text == "әдепкі баптауларды қалпына келтіру".lower():
            continue
        assert not any(keyword in text for keyword in forbidden_keywords)


def test_open_data_folder_button_present() -> None:
    page = SettingsPage()
    assert any(
        button.text() == "Деректер қалтасын ашу" for button in page.findChildren(QPushButton)
    )


# =====================================================================
# §11: Popup/watermark/theme.
# =====================================================================


def test_settings_page_listed_in_transparent_root_classes() -> None:
    from ui.themes.theme_manager import ThemeManager

    stylesheet = ThemeManager().build_stylesheet()
    assert "SettingsPage" in stylesheet


def test_settings_page_root_has_no_instance_level_stylesheet() -> None:
    """§ Phase 20 регрессиясы — контейнерге instance-деңгейлік
    ``setStyleSheet()`` ЕШҚАШАН қолданылмайды (глобал QSS арқылы ғана)."""
    page = SettingsPage()
    assert page.styleSheet() == ""


def test_buttons_have_no_instance_level_stylesheet() -> None:
    page = SettingsPage()
    assert page._reset_button.styleSheet() == ""


def test_cloud_sync_panel_is_hidden() -> None:
    page = SettingsPage()
    assert page._sync_enabled_checkbox.parent().isHidden()
    assert "БҰЛТТЫҚ СИНХРОНДАУ" not in _panel_titles(page)


def test_toggling_sync_enabled_persists_immediately(temp_preferences) -> None:
    preferences, path = temp_preferences
    page = SettingsPage(app_preferences=preferences)

    page._sync_enabled_checkbox.setChecked(True)

    reloaded = AppPreferences(QSettings(path, QSettings.Format.IniFormat))
    assert reloaded.get_sync_enabled() is True


def test_saving_valid_sync_url_persists(temp_preferences) -> None:
    preferences, path = temp_preferences
    page = SettingsPage(app_preferences=preferences)
    page._sync_url_edit.setText("https://lab.example.kz")
    page._on_sync_url_editing_finished()

    reloaded = AppPreferences(QSettings(path, QSettings.Format.IniFormat))
    assert reloaded.get_sync_api_base_url() == "https://lab.example.kz"
    assert page._sync_url_error_label.text() == ""


def test_invalid_sync_url_does_not_persist(temp_preferences) -> None:
    preferences, path = temp_preferences
    preferences.set_sync_api_base_url("https://lab.example.kz")
    page = SettingsPage(app_preferences=preferences)
    page._sync_url_edit.setText("not-a-url")
    page._on_sync_url_editing_finished()

    reloaded = AppPreferences(QSettings(path, QSettings.Format.IniFormat))
    assert reloaded.get_sync_api_base_url() == "https://lab.example.kz"
    assert "http://" in page._sync_url_error_label.text()
    assert page._sync_url_edit.text() == "https://lab.example.kz"


def test_checkbox_uses_leaf_widget_transparency_pattern() -> None:
    """§ established pattern — QCheckBox сияқты жапырақ (interactive
    балалары жоқ) виджет ақ DashboardPanel үстінде opaque
    QWidget{background-color} ережесіне ұшырамауы үшін instance-деңгейлік
    ``setStyleSheet()`` қолданады (§ ``_make_background_transparent()``,
    контейнерлерге ЕМЕС, ТЕК жапырақ виджеттерге қауіпсіз)."""
    page = SettingsPage()
    assert page._auto_scale_checkbox.styleSheet() == "background-color: transparent;"


# =====================================================================
# §12: Геометрия — 1366x768 және 1920x1080.
# =====================================================================


def test_1366x768_smoke_layout() -> None:
    page = SettingsPage()
    page.resize(1366, 768)
    page.show()

    assert page.width() == 1366
    assert _panel_titles(page) == ["ЖАЛПЫ", "ӨЛШЕУ", "ҚҰРЫЛҒЫЛАР", "ДЕРЕКТЕР", "МҰҒАЛІМДЕР"]
    assert page._reset_button.isVisible()


def test_1920x1080_smoke_layout() -> None:
    page = SettingsPage()
    page.resize(1920, 1080)
    page.show()

    assert page.width() == 1920
    assert _panel_titles(page) == ["ЖАЛПЫ", "ӨЛШЕУ", "ҚҰРЫЛҒЫЛАР", "ДЕРЕКТЕР", "МҰҒАЛІМДЕР"]
    assert page._reset_button.isVisible()


def test_no_scroll_area_needed_content_fits_without_scrolling() -> None:
    """§ "vertical-only scrolling if genuinely needed" — audit: 4 бөлім +
    тақырып + reset батырмасы 1366x768-ге scroll-сыз сыяды (§ screenshot
    тексерілді), сондықтан ЕШБІР QScrollArea қажет емес — бұл сонымен
    қатар QScrollArea-ның 3+ деңгей тереңдіктегі QLabel-дерге транспарентті
    QSS ережесі жетпейтін белгілі тұзақтан аулақ болады."""
    from PySide6.QtWidgets import QScrollArea

    page = SettingsPage()
    assert page.findChildren(QScrollArea) == []


# ---- МҰҒАЛІМДЕР (Multi-Teacher Accounts §7) -----------------------------


def test_manage_teachers_button_emits_signal() -> None:
    page = SettingsPage()
    received: list[None] = []
    page.manage_teachers_requested.connect(lambda: received.append(None))

    for button in page.findChildren(QPushButton):
        if button.text() == "Мұғалімдерді басқару →":
            button.click()
            break
    else:
        raise AssertionError("Мұғалімдерді басқару батырмасы табылмады")

    assert received == [None]


def test_set_teacher_count_updates_label() -> None:
    page = SettingsPage()

    page.set_teacher_count(3)

    assert "3" in page._teacher_count_label.text()


def test_teacher_count_defaults_to_zero() -> None:
    page = SettingsPage()

    assert "0" in page._teacher_count_label.text()
