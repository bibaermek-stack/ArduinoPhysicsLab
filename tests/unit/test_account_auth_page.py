"""AccountAuthPage — юнит-тесттері.

Бұрын толығымен тестсіз болған бет (§ desktop-app gap analysis): email/
password валидациясы, login/register/Google callback ағындары —
әсіресе ``_on_google()``-дің нақты локал ``HTTPServer`` көтеріп, OAuth
callback-ты фондық тредте қабылдап, ``google_token_received`` сигналын
GUI тредіне queued connection арқылы жіберетін бөлігі ешбір тестпен
қамтылмаған еді.

Нақты сыртқы желіге ЕШҚАШАН шықпайды — ``AccountApiClient`` орнына
``_FakeAccountApiClient`` ``page._client``-ке тікелей ауыстырылады
(constructor-да client үшін DI seam жоқ — § gap analysis "no dependency
seam" ескертуі, сондықтан осы жерде private attribute-ты тікелей
ауыстыру ЖАЛҒЫЗ мүмкін тәсіл). Google callback тесттері ғана нақты
локал ``127.0.0.1`` socket қолданады (§ ``_on_google()``-дің өз
өндірістік жолы дәл осылай істейді) — ``QDesktopServices.openUrl()``
ғана monkeypatch етіледі (нақты браузер ашылмауы үшін).
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
import urllib.request

import pytest
from PySide6.QtCore import QCoreApplication, QSettings
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QLineEdit, QPushButton

from infrastructure.storage.app_preferences import AppPreferences
from infrastructure.sync.account_api_client import AccountApiError
from ui.pages.account_auth_page import AccountAuthPage


@pytest.fixture(scope="module", autouse=True)
def qt_application() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def preferences() -> AppPreferences:
    handle = tempfile.NamedTemporaryFile(suffix=".ini", delete=False)
    handle.close()
    settings = QSettings(handle.name, QSettings.Format.IniFormat)
    yield AppPreferences(settings)
    os.unlink(handle.name)


class _FakeAccountApiClient:
    """§ ``AccountApiClient``-тің тест дублеры — нақты ``httpx`` шақыруы
    ЕШҚАШАН жасалмайды."""

    def __init__(self) -> None:
        self.login_calls: list[tuple[str, str]] = []
        self.register_calls: list[tuple[str, str, str]] = []
        self.stored_sessions: list[tuple[dict, str]] = []
        self.me_calls = 0
        self.login_result: dict = {}
        self.login_error: AccountApiError | None = None
        self.register_result: dict = {}
        self.register_error: AccountApiError | None = None
        self.me_result: dict = {}
        self.me_error: AccountApiError | None = None

    def login(self, email: str, password: str) -> dict:
        self.login_calls.append((email, password))
        if self.login_error is not None:
            raise self.login_error
        return self.login_result

    def register(self, email: str, password: str, name: str) -> dict:
        self.register_calls.append((email, password, name))
        if self.register_error is not None:
            raise self.register_error
        return self.register_result

    def google_start_url(self, desktop_port: int) -> str:
        return "http://example.invalid/start"

    def me(self) -> dict:
        self.me_calls += 1
        if self.me_error is not None:
            raise self.me_error
        return self.me_result

    def store_session(self, payload: dict, email: str = "") -> None:
        self.stored_sessions.append((dict(payload), email))


@pytest.fixture
def page_factory(qt_application: QApplication, preferences: AppPreferences):
    created: list[AccountAuthPage] = []

    def _factory() -> tuple[AccountAuthPage, _FakeAccountApiClient]:
        page = AccountAuthPage(preferences=preferences)
        fake_client = _FakeAccountApiClient()
        page._client = fake_client
        created.append(page)
        return page, fake_client

    yield _factory

    for page in created:
        page.hide()


def _wait_until(condition, timeout_s: float = 5.0) -> bool:
    """Фондық тредтен queued-connection арқылы жіберілген сигналды GUI
    event loop-ы өңдегенше поллайды (§ ``_on_google()``-дің нақты
    ``threading.Thread`` + ``HTTPServer.handle_request()`` жолы)."""
    deadline = time.monotonic() + timeout_s
    while not condition() and time.monotonic() < deadline:
        QCoreApplication.processEvents()
        time.sleep(0.01)
    return condition()


# ---- Валидация ---------------------------------------------------------


def test_empty_email_shows_error_on_login(page_factory) -> None:
    page, client = page_factory()
    page._email_edit.setText("")
    page._password_edit.setText("secret1")

    page._on_login()

    assert page._error.text() == "Email мен құпия сөзді енгізіңіз"
    assert client.login_calls == []


def test_empty_password_shows_error_on_login(page_factory) -> None:
    page, client = page_factory()
    page._email_edit.setText("a@b.com")
    page._password_edit.setText("")

    page._on_login()

    assert page._error.text() == "Email мен құпия сөзді енгізіңіз"
    assert client.login_calls == []


def test_empty_email_or_password_shows_error_on_register(page_factory) -> None:
    page, client = page_factory()
    page._email_edit.setText("a@b.com")
    page._password_edit.setText("")

    page._on_register()

    assert page._error.text() == "Email мен құпия сөзді енгізіңіз"
    assert client.register_calls == []


def test_password_field_uses_password_echo_mode(page_factory) -> None:
    page, _ = page_factory()
    assert page._password_edit.echoMode() == QLineEdit.EchoMode.Password


# ---- Login ---------------------------------------------------------------


def test_login_success_trims_email_stores_session_and_emits(page_factory) -> None:
    page, client = page_factory()
    client.login_result = {
        "access_token": "tok-1",
        "account_id": "acc-1",
        "display_name": "Aigerim",
        "role": "teacher",
        "public_id": "T-01",
    }
    page._email_edit.setText("  aigerim@example.com  ")
    page._password_edit.setText("secret1")
    received: list[dict] = []
    page.authenticated.connect(received.append)

    page._on_login()

    assert client.login_calls == [("aigerim@example.com", "secret1")]
    assert received == [client.login_result]
    assert client.stored_sessions == [(client.login_result, "aigerim@example.com")]
    assert page._error.text() == ""


def test_login_failure_shows_error_and_does_not_emit(page_factory) -> None:
    page, client = page_factory()
    client.login_error = AccountApiError("Email немесе құпия сөз қате")
    page._email_edit.setText("aigerim@example.com")
    page._password_edit.setText("wrong")
    received: list[dict] = []
    page.authenticated.connect(received.append)

    page._on_login()

    assert page._error.text() == "Email немесе құпия сөз қате"
    assert received == []
    assert client.stored_sessions == []


# ---- Тіркелу ---------------------------------------------------------------


def test_register_success_passes_trimmed_email_and_name(page_factory) -> None:
    page, client = page_factory()
    client.register_result = {"access_token": "tok-2", "account_id": "acc-2"}
    page._name_edit.setText("  Nurlan Bekov  ")
    page._email_edit.setText("  nurlan@example.com  ")
    page._password_edit.setText("secret2")
    received: list[dict] = []
    page.authenticated.connect(received.append)

    page._on_register()

    assert client.register_calls == [("nurlan@example.com", "secret2", "Nurlan Bekov")]
    assert received == [client.register_result]


def test_register_failure_shows_error(page_factory) -> None:
    page, client = page_factory()
    client.register_error = AccountApiError("Бұл email тіркелген")
    page._email_edit.setText("dup@example.com")
    page._password_edit.setText("secret2")

    page._on_register()

    assert page._error.text() == "Бұл email тіркелген"


def test_saved_account_with_token_emits_authenticated(page_factory, preferences: AppPreferences) -> None:
    preferences.upsert_saved_account(
        account_id="acc-9",
        email="saved@school.kz",
        display_name="Сақталған",
        role="teacher",
        public_id="T-09",
        token="tok-saved",
    )
    page, client = page_factory()
    received: list[dict] = []
    page.authenticated.connect(received.append)

    open_btn = next(
        b for b in page._saved_frame.findChildren(QPushButton) if "Сақталған" in b.text()
    )
    open_btn.click()

    assert received[0]["access_token"] == "tok-saved"
    assert client.stored_sessions[0][1] == "saved@school.kz"


def test_remove_saved_account_hides_row(page_factory, preferences: AppPreferences) -> None:
    preferences.upsert_saved_account(
        account_id="acc-9",
        email="saved@school.kz",
        display_name="Сақталған",
        role="teacher",
        public_id="T-09",
        token="tok-saved",
    )
    page, _client = page_factory()
    remove_btn = next(b for b in page._saved_frame.findChildren(QPushButton) if b.text() == "Өшіру")
    remove_btn.click()

    assert preferences.list_saved_accounts() == ()
    assert page._saved_frame.isVisible() is False


# ---- Интернетсіз кіру батырмасы ---------------------------------------------


def test_offline_button_emits_skip_offline(page_factory) -> None:
    page, _ = page_factory()
    button = next(
        b for b in page._card.findChildren(QPushButton)
        if b.text() == "Интернетсіз кіру"
    )
    received: list[None] = []
    page.skip_offline.connect(lambda: received.append(None))

    button.click()

    assert len(received) == 1


# ---- handle_google_token() ----------------------------------------------


def test_handle_google_token_resolves_role_via_me_when_role_known(page_factory) -> None:
    page, client = page_factory()
    client.me_result = {
        "account_id": "acc-3",
        "display_name": "Madina",
        "role": "student",
        "public_id": "S-09",
        "needs_role": False,
        "email": "madina@example.com",
    }
    received: list[dict] = []
    page.authenticated.connect(received.append)

    page.handle_google_token("g-token", False)

    assert client.me_calls == 1
    assert received[-1]["display_name"] == "Madina"
    assert received[-1]["role"] == "student"
    assert received[-1]["needs_role"] is False
    assert client.stored_sessions[-1][1] == "madina@example.com"


def test_handle_google_token_me_failure_falls_back_to_needs_role_flag(page_factory) -> None:
    page, client = page_factory()
    client.me_error = AccountApiError("Токен жарамсыз")
    received: list[dict] = []
    page.authenticated.connect(received.append)

    page.handle_google_token("g-token", True)

    assert received[-1]["needs_role"] is True
    assert received[-1]["access_token"] == "g-token"


# ---- Google OAuth callback: нақты локал HTTPServer ---------------------


def test_google_flow_starts_local_server_and_delivers_callback(page_factory, monkeypatch) -> None:
    page, client = page_factory()
    client.me_result = {
        "account_id": "acc-4",
        "display_name": "Serik",
        "role": "teacher",
        "public_id": "T-02",
        "needs_role": False,
        "email": "serik@example.com",
    }
    opened_urls: list[str] = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened_urls.append(url.toString()))

    page._on_google()

    assert page._server is not None
    port = page._server.server_address[1]
    received: list[dict] = []
    page.authenticated.connect(received.append)

    response = urllib.request.urlopen(
        f"http://127.0.0.1:{port}/callback?token=real-token&needs_role=0", timeout=5
    )
    assert response.status == 200

    assert _wait_until(lambda: bool(received)), (
        "google_token_received signal GUI тредіне уақытында жеткізілмеді"
    )
    assert received[0]["display_name"] == "Serik"
    assert client.me_calls == 1
    assert len(opened_urls) == 1


def test_google_callback_missing_needs_role_defaults_to_true(page_factory, monkeypatch) -> None:
    page, client = page_factory()
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: None)

    page._on_google()
    port = page._server.server_address[1]
    received: list[tuple[str, bool]] = []
    page.google_token_received.connect(lambda t, n: received.append((t, n)))

    urllib.request.urlopen(f"http://127.0.0.1:{port}/callback?token=abc", timeout=5)

    assert _wait_until(lambda: bool(received))
    assert received == [("abc", True)]


def test_google_callback_without_token_does_not_emit(page_factory, monkeypatch) -> None:
    page, client = page_factory()
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: None)

    page._on_google()
    port = page._server.server_address[1]
    received: list[tuple[str, bool]] = []
    page.google_token_received.connect(lambda t, n: received.append((t, n)))

    response = urllib.request.urlopen(f"http://127.0.0.1:{port}/callback?needs_role=1", timeout=5)
    assert response.status == 200

    # Токен жоқ болса, сигнал ЕШҚАШАН шықпауы керек — сол "жоқ" күйдің
    # өзін growатпайтынын растау үшін event loop-ты біраз уақыт поллаймыз.
    _wait_until(lambda: False, timeout_s=0.5)

    assert received == []
    assert client.me_calls == 0
