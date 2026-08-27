"""``AppPreferences`` — Phase 9 (Production Deployment) юнит-тесттері:
sync server URL схема валидациясы (§ Part K "HTTPS / Network Model",
"server URL validation" / "HTTPS URL support" талаптары).

§ ``tests/unit/test_settings_page.py::temp_preferences``-пен БІРДЕЙ
конвенция — ``MagicMock`` ЕМЕС, нақты уақытша ``.ini`` файлға
негізделген ``QSettings`` (§ ``QSettings()`` бос mock мәнді
"сақтамайды" — ``.value()`` ӘРҚАШАН жаңа Mock қайтарар еді).
"""

import os
import sys
import tempfile

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from infrastructure.storage.app_preferences import AppPreferences


@pytest.fixture(scope="module", autouse=True)
def qt_application() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def preferences():
    handle = tempfile.NamedTemporaryFile(suffix=".ini", delete=False)
    handle.close()
    settings = QSettings(handle.name, QSettings.Format.IniFormat)
    yield AppPreferences(settings)
    os.unlink(handle.name)


def test_https_url_accepted(preferences: AppPreferences) -> None:
    """§ "production desktop app must NOT hardcode localhost... must
    support a remote HTTPS server"."""
    preferences.set_sync_api_base_url("https://physics-lab.example.kz")

    assert preferences.get_sync_api_base_url() == "https://physics-lab.example.kz"


def test_http_url_still_accepted_for_local_dev(preferences: AppPreferences) -> None:
    """§ "Development can still use something like http://127.0.0.1:8000"."""
    preferences.set_sync_api_base_url("http://127.0.0.1:8000")

    assert preferences.get_sync_api_base_url() == "http://127.0.0.1:8000"


@pytest.mark.parametrize(
    "invalid_url",
    [
        "ftp://example.com",
        "javascript:alert(1)",
        "not-a-url-at-all",
        "",
        "   ",
        "physics-lab.example.kz",  # § схема ЖОҚ
    ],
)
def test_non_http_scheme_is_rejected(preferences: AppPreferences, invalid_url: str) -> None:
    with pytest.raises(ValueError):
        preferences.set_sync_api_base_url(invalid_url)


def test_rejected_url_never_gets_stored(preferences: AppPreferences) -> None:
    """§ "жарамсыз мән ЕШҚАШАН үнсіз сақталмайды" — валидация сәтсіз
    болса, ескі мән өзгеріссіз қалады."""
    preferences.set_sync_api_base_url("https://original.example.kz")

    with pytest.raises(ValueError):
        preferences.set_sync_api_base_url("ftp://malicious.example.com")

    assert preferences.get_sync_api_base_url() == "https://original.example.kz"


def test_default_url_is_not_forced_to_localhost_only(preferences: AppPreferences) -> None:
    """§ "server base URL is already configurable (default http://
    127.0.0.1:8000, not forced to localhost)" — әдепкі мән ӨЗГЕРТІЛЕ
    алады, тексеру осы конфигурацияланатындығын растайды."""
    preferences.set_sync_api_base_url("https://school-a.example.kz")
    preferences.set_sync_api_base_url("https://school-b.example.kz")

    assert preferences.get_sync_api_base_url() == "https://school-b.example.kz"
