"""Профиль беті — ID, аты, сурет."""

from __future__ import annotations

import base64

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from infrastructure.storage.app_preferences import AppPreferences
from infrastructure.sync.account_api_client import AccountApiClient, AccountApiError


class ProfilePage(QWidget):
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

        layout = QVBoxLayout(self)
        layout.addWidget(title)
        row = QHBoxLayout()
        row.addWidget(self._photo)
        col = QVBoxLayout()
        col.addWidget(self._id_label)
        col.addWidget(self._role_label)
        col.addWidget(self._name_edit)
        col.addWidget(photo_btn)
        col.addWidget(save_btn)
        col.addWidget(copy_btn)
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
