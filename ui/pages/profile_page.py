"""Профиль беті — ID, аты, сурет."""

from __future__ import annotations

import base64

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from infrastructure.storage.app_preferences import AppPreferences
from infrastructure.sync.account_api_client import AccountApiClient, AccountApiError


class ConnectTeacherDialog(QDialog):
    """Оқушы мұғалім кодын енгізеді немесе аты бойынша іздейді."""

    def __init__(self, client: AccountApiClient, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._client = client
        self._results: list[dict] = []
        self.setWindowTitle("Мұғалімге қосылу")

        self._code_edit = QLineEdit(self)
        self._code_edit.setPlaceholderText("Мұғалім коды, мысалы T-7K2M9Q")
        code_btn = QPushButton("Кодпен қосылу", self)
        code_btn.setObjectName("PrimaryButton")
        code_btn.clicked.connect(self._on_connect_code)

        self._search_edit = QLineEdit(self)
        self._search_edit.setPlaceholderText("Аты-жөні бойынша іздеу")
        search_btn = QPushButton("Іздеу", self)
        search_btn.clicked.connect(self._on_search)
        self._results_list = QListWidget(self)
        pick_btn = QPushButton("Таңдалған мұғалімге өтініш", self)
        pick_btn.clicked.connect(self._on_connect_selected)
        self._error = QLabel("", self)
        self._error.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Мұғаліміңіздің кодын енгізіңіз", self))
        layout.addWidget(self._code_edit)
        layout.addWidget(code_btn)
        layout.addWidget(QLabel("Немесе аты-жөні бойынша іздеңіз", self))
        search_row = QHBoxLayout()
        search_row.addWidget(self._search_edit, 1)
        search_row.addWidget(search_btn)
        layout.addLayout(search_row)
        layout.addWidget(self._results_list)
        layout.addWidget(pick_btn)
        layout.addWidget(self._error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_connect_code(self) -> None:
        try:
            self._client.connect_teacher(self._code_edit.text().strip())
        except AccountApiError as error:
            self._error.setText(str(error))
            return
        self.accept()

    def _on_search(self) -> None:
        try:
            self._results = self._client.search_teachers(self._search_edit.text().strip())
        except AccountApiError as error:
            self._error.setText(str(error))
            return
        self._results_list.clear()
        for item in self._results:
            self._results_list.addItem(
                QListWidgetItem(f"{item.get('public_id')} — {item.get('display_name')}")
            )
        self._error.setText(f"{len(self._results)} мұғалім" if self._results else "Табылмады")

    def _on_connect_selected(self) -> None:
        row = self._results_list.currentRow()
        if row < 0 or row >= len(self._results):
            self._error.setText("Алдымен мұғалімді таңдаңыз")
            return
        try:
            self._client.connect_teacher(str(self._results[row].get("public_id") or ""))
        except AccountApiError as error:
            self._error.setText(str(error))
            return
        self.accept()


class ProfilePage(QWidget):
    logout_requested = Signal()

    def __init__(
        self,
        preferences: AppPreferences | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._preferences = preferences or AppPreferences()
        self._client = AccountApiClient(self._preferences)

        title = QLabel("Профиль", self)
        title_font = title.font()
        title_font.setBold(True)
        title_font.setPointSize(title_font.pointSize() + 4)
        title.setFont(title_font)

        self._photo = QLabel(self)
        self._photo.setFixedSize(120, 120)
        self._photo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._photo.setText("Сурет жоқ")
        self._photo.setStyleSheet("border: 1px solid #ccc; border-radius: 8px;")

        self._id_label = QLabel("ID: —", self)
        self._role_label = QLabel("Рөл: —", self)
        self._link_label = QLabel("", self)
        self._link_label.setWordWrap(True)
        self._link_label.setProperty("role", "secondary")
        self._connect_btn = QPushButton("Мұғалімге қосылу", self)
        self._connect_btn.clicked.connect(self._on_connect_teacher)
        self._connect_btn.hide()
        self._name_edit = QLineEdit(self)
        self._status = QLabel("", self)
        self._status.setWordWrap(True)

        photo_btn = QPushButton("Сурет қою", self)
        photo_btn.clicked.connect(self._on_pick_photo)
        save_btn = QPushButton("Сақтау", self)
        save_btn.setObjectName("PrimaryButton")
        save_btn.clicked.connect(self._on_save)
        copy_btn = QPushButton("ID көшіру", self)
        copy_btn.clicked.connect(self._on_copy_id)
        logout_btn = QPushButton("Шығу", self)
        logout_btn.setProperty("variant", "danger")
        logout_btn.style().unpolish(logout_btn)
        logout_btn.style().polish(logout_btn)
        logout_btn.clicked.connect(self._on_logout)
        self._logout_hint = QLabel(
            "Басқа аккаунтпен кіру немесе жаңасын тіркеу үшін шығыңыз.",
            self,
        )
        self._logout_hint.setProperty("role", "secondary")
        self._logout_hint.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addWidget(title)
        row = QHBoxLayout()
        row.addWidget(self._photo)
        col = QVBoxLayout()
        col.addWidget(self._id_label)
        col.addWidget(self._role_label)
        col.addWidget(self._link_label)
        col.addWidget(self._connect_btn)
        col.addWidget(self._name_edit)
        col.addWidget(photo_btn)
        col.addWidget(save_btn)
        col.addWidget(copy_btn)
        col.addWidget(logout_btn)
        col.addWidget(self._logout_hint)
        row.addLayout(col, 1)
        layout.addLayout(row)
        layout.addWidget(self._status)
        layout.addStretch(1)

    def on_enter(self) -> None:
        try:
            me = self._client.me()
        except AccountApiError as error:
            self._status.setText(str(error))
            return
        self._id_label.setText(f"ID: {me.get('public_id') or '—'}")
        role = me.get("role") or "—"
        role_kk = {"teacher": "Мұғалім", "student": "Оқушы"}.get(role, role)
        self._role_label.setText(f"Рөл: {role_kk}")
        self._name_edit.setText(str(me.get("display_name") or ""))
        photo = me.get("photo_base64")
        if photo:
            raw = base64.b64decode(photo)
            image = QImage.fromData(raw)
            self._photo.setPixmap(QPixmap.fromImage(image).scaled(120, 120, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self._status.setText("")
        self._apply_link(me)

    def _apply_link(self, me: dict) -> None:
        role = me.get("role")
        status = me.get("link_status") or "independent"
        teacher = me.get("teacher") or {}
        if role == "teacher":
            self._link_label.setText(f"Оқушыларға берілетін код: {me.get('public_id') or '—'}")
            self._connect_btn.hide()
            return
        if role != "student":
            self._link_label.setText("")
            self._connect_btn.hide()
            return
        if status == "active" and teacher:
            self._link_label.setText(
                f"Сіздің жетекшіңіз: {teacher.get('display_name')} ({teacher.get('public_id')})"
            )
            self._connect_btn.hide()
            return
        if status == "pending":
            name = teacher.get("display_name") or teacher.get("public_id") or "мұғалім"
            self._link_label.setText(f"Өтініш жіберілді: {name}. Қабылдау күтілуде.")
            self._connect_btn.hide()
            return
        self._link_label.setText("Дербес режим (мұғалім таңдалмаған)")
        self._connect_btn.show()

    def _on_connect_teacher(self) -> None:
        dialog = ConnectTeacherDialog(self._client, self)
        if dialog.exec():
            self.on_enter()
            self._status.setText("Өтініш жіберілді. Мұғалім қабылдағаннан кейін сыныпқа қосыласыз.")

    def _on_copy_id(self) -> None:
        from PySide6.QtWidgets import QApplication

        text = self._id_label.text().replace("ID: ", "").strip()
        QApplication.clipboard().setText(text)

    def _on_pick_photo(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Сурет таңдау", "", "Images (*.png *.jpg *.jpeg)")
        if not path:
            return
        with open(path, "rb") as handle:
            raw = handle.read()
        encoded = base64.b64encode(raw).decode("ascii")
        try:
            me = self._client.update_me(photo_base64=encoded)
        except AccountApiError as error:
            self._status.setText(str(error))
            return
        self._status.setText("Сурет сақталды")
        photo = me.get("photo_base64")
        if photo:
            image = QImage.fromData(base64.b64decode(photo))
            self._photo.setPixmap(QPixmap.fromImage(image).scaled(120, 120, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def _on_save(self) -> None:
        try:
            self._client.update_me(display_name=self._name_edit.text().strip())
        except AccountApiError as error:
            self._status.setText(str(error))
            return
        self._status.setText("Профиль сақталды")

    def _on_logout(self) -> None:
        self._preferences.clear_account_session()
        self._preferences.clear_sync_auth_token()
        self.logout_requested.emit()
