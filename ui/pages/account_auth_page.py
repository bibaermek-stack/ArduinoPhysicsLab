"""Email/Google кіру экраны — қолданбаның бірінші беті."""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from PySide6.QtCore import QRectF, QUrl, Qt, Signal
from PySide6.QtGui import QColor, QDesktopServices, QPainter
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from infrastructure.storage.app_preferences import AppPreferences
from infrastructure.sync.account_api_client import AccountApiClient, AccountApiError
from ui.themes.theme_manager import COLOR_ERROR, theme_color
from ui.widgets.animated_atom_widget import paint_atom

_WINDOW_TITLE = "Arduino Physics Lab"
_CARD_WIDTH = 520


class AccountAuthPage(QWidget):
    authenticated = Signal(object)  # dict payload
    skip_offline = Signal()
    google_token_received = Signal(str, bool)

    def __init__(
        self,
        preferences: AppPreferences | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(_WINDOW_TITLE)
        self._preferences = preferences or AppPreferences()
        self._client = AccountApiClient(self._preferences)
        self._server: HTTPServer | None = None
        self.google_token_received.connect(self.handle_google_token)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        row.addStretch(1)
        self._card = QFrame(self)
        self._card.setObjectName("EntrySurfaceCard")
        self._card.setFixedWidth(_CARD_WIDTH)
        layout = QVBoxLayout(self._card)

        title = QLabel(_WINDOW_TITLE, self._card)
        title.setObjectName("EntryTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle = QLabel(
            "Email немесе Google арқылы кіріңіз. Бірнеше аккаунт тіркеуге болады.",
            self._card,
        )
        subtitle.setProperty("role", "secondary")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)

        self._saved_frame = QFrame(self._card)
        self._saved_frame.setObjectName("EntrySurfaceCard")
        saved_layout = QVBoxLayout(self._saved_frame)
        saved_layout.setContentsMargins(0, 0, 0, 8)
        saved_title = QLabel("Сақталған аккаунттар", self._saved_frame)
        saved_title.setProperty("role", "secondary")
        saved_layout.addWidget(saved_title)
        self._saved_list = QVBoxLayout()
        saved_layout.addLayout(self._saved_list)

        self._name_edit = QLineEdit(self._card)
        self._name_edit.setPlaceholderText("Аты-жөні (тіркелу үшін)")
        self._email_edit = QLineEdit(self._card)
        self._email_edit.setPlaceholderText("Email")
        self._password_edit = QLineEdit(self._card)
        self._password_edit.setPlaceholderText("Құпия сөз (кемінде 6 таңба)")
        self._password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._error = QLabel("", self._card)
        self._error.setObjectName("EntryErrorLabel")
        self._error.setWordWrap(True)
        self._error.setStyleSheet(f"color: {COLOR_ERROR}; background: transparent;")

        login_btn = QPushButton("Кіру", self._card)
        login_btn.setObjectName("PrimaryButton")
        login_btn.clicked.connect(self._on_login)
        register_btn = QPushButton("Тіркелу", self._card)
        register_btn.clicked.connect(self._on_register)
        google_btn = QPushButton("Google арқылы кіру", self._card)
        google_btn.clicked.connect(self._on_google)
        offline_btn = QPushButton("Интернетсіз кіру (PIN / код)", self._card)
        offline_btn.clicked.connect(self.skip_offline)

        for widget in (
            title,
            subtitle,
            self._saved_frame,
            self._name_edit,
            self._email_edit,
            self._password_edit,
            self._error,
            login_btn,
            register_btn,
            google_btn,
            offline_btn,
        ):
            layout.addWidget(widget)
        self.refresh_saved_accounts()

        row.addWidget(self._card, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addStretch(1)
        outer.addStretch(1)
        outer.addLayout(row)
        outer.addStretch(1)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor(theme_color("COLOR_BACKGROUND")))
        side = min(self.width(), self.height()) * 0.62
        if side > 0:
            paint_atom(painter, QRectF(-side * 0.22, -side * 0.22, side, side), 0.0, opacity=0.06, animated=False)
        painter.end()

    def prepare_for_reuse(self) -> None:
        self._password_edit.clear()
        self._error.setText("")
        self.refresh_saved_accounts()

    def refresh_saved_accounts(self) -> None:
        while self._saved_list.count():
            item = self._saved_list.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        accounts = self._preferences.list_saved_accounts()
        self._saved_frame.setVisible(bool(accounts))
        for account in accounts:
            self._saved_list.addWidget(self._make_saved_row(account))

    def _make_saved_row(self, account: dict[str, str]) -> QWidget:
        row = QWidget(self._saved_frame)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        name = account.get("display_name") or account.get("email") or "Аккаунт"
        email = account.get("email") or ""
        public_id = account.get("public_id") or ""
        label = " · ".join(part for part in (name, email or public_id) if part)
        open_btn = QPushButton(label, row)
        open_btn.setToolTip("Осы аккаунтпен кіру")
        open_btn.clicked.connect(lambda _checked=False, acc=account: self._on_saved_account_clicked(acc))
        remove_btn = QPushButton("Өшіру", row)
        remove_btn.clicked.connect(lambda _checked=False, acc=account: self._on_remove_saved_account(acc))
        layout.addWidget(open_btn, 1)
        layout.addWidget(remove_btn)
        return row

    def _on_saved_account_clicked(self, account: dict[str, str]) -> None:
        token = account.get("token") or ""
        if token:
            payload = {
                "access_token": token,
                "account_id": account.get("account_id") or "",
                "display_name": account.get("display_name") or "",
                "role": account.get("role") or "",
                "public_id": account.get("public_id") or "",
                "needs_role": not bool(account.get("role")),
            }
            self._emit_payload(payload, account.get("email") or "")
            return
        self._email_edit.setText(account.get("email") or "")
        self._password_edit.setFocus()
        self._set_error("Құпия сөзді енгізіп, Кіру басыңыз")

    def _on_remove_saved_account(self, account: dict[str, str]) -> None:
        self._preferences.remove_saved_account(
            account_id=account.get("account_id") or "",
            email=account.get("email") or "",
        )
        self.refresh_saved_accounts()

    def _set_error(self, text: str) -> None:
        self._error.setText(text)

    def _emit_payload(self, payload: dict, email: str) -> None:
        self._client.store_session(payload, email=email)
        self.authenticated.emit(payload)

    def _on_login(self) -> None:
        email = self._email_edit.text().strip()
        password = self._password_edit.text()
        if not email or not password:
            self._set_error("Email мен құпия сөзді енгізіңіз")
            return
        try:
            payload = self._client.login(email, password)
        except AccountApiError as error:
            self._set_error(str(error))
            return
        self._emit_payload(payload, email)

    def _on_register(self) -> None:
        email = self._email_edit.text().strip()
        password = self._password_edit.text()
        name = self._name_edit.text().strip()
        if not email or not password:
            self._set_error("Email мен құпия сөзді енгізіңіз")
            return
        try:
            payload = self._client.register(email, password, name)
        except AccountApiError as error:
            self._set_error(str(error))
            return
        self._emit_payload(payload, email)

    def _on_google(self) -> None:
        self._set_error("")
        try:
            server = HTTPServer(("127.0.0.1", 0), _GoogleCallbackHandler)
        except OSError as error:
            self._set_error(f"Google кіру ашылмады: {error}")
            return
        port = server.server_address[1]
        _GoogleCallbackHandler.page = self
        self._server = server
        threading.Thread(target=server.handle_request, daemon=True).start()
        QDesktopServices.openUrl(QUrl(self._client.google_start_url(port)))

    def handle_google_token(self, token: str, needs_role: bool) -> None:
        payload = {
            "access_token": token,
            "account_id": "",
            "display_name": "",
            "role": None if needs_role else self._preferences.get_account_role(),
            "public_id": None,
            "needs_role": needs_role,
        }
        self._client.store_session(payload, email="")
        try:
            me = self._client.me()
            payload.update(
                {
                    "account_id": me.get("account_id"),
                    "display_name": me.get("display_name"),
                    "role": me.get("role"),
                    "public_id": me.get("public_id"),
                    "needs_role": me.get("needs_role"),
                    "access_token": self._preferences.get_account_token() or token,
                }
            )
            self._client.store_session(payload, email=str(me.get("email") or ""))
        except AccountApiError:
            payload["needs_role"] = needs_role
        self.authenticated.emit(payload)


class _GoogleCallbackHandler(BaseHTTPRequestHandler):
    page: AccountAuthPage | None = None

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        token = (params.get("token") or [""])[0]
        needs_role = (params.get("needs_role") or ["1"])[0] == "1"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write("Кіру сәтті. Терезені жабуға болады.".encode("utf-8"))
        if token and self.page is not None:
            self.page.google_token_received.emit(token, needs_role)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return
