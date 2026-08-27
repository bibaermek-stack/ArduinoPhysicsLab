"""Адамдарды іздеу, мұғалім/оқушы және дос өтініштері."""

from __future__ import annotations

from PySide6.QtWidgets import (
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


class PeoplePage(QWidget):
    def __init__(
        self,
        preferences: AppPreferences | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._preferences = preferences or AppPreferences()
        self._client = AccountApiClient(self._preferences)
        self._results: list[dict] = []
        self._incoming: list[dict] = []

        title = QLabel("Адамдар", self)
        title_font = title.font()
        title_font.setBold(True)
        title_font.setPointSize(title_font.pointSize() + 4)
        title.setFont(title_font)

        self._query = QLineEdit(self)
        self._query.setPlaceholderText("ID немесе аты бойынша іздеу (мысалы T-7K2M9Q)")
        search_btn = QPushButton("Іздеу", self)
        search_btn.clicked.connect(self._on_search)
        self._results_list = QListWidget(self)
        ts_btn = QPushButton("Мұғалім / оқушы өтініші", self)
        ts_btn.clicked.connect(self._on_teacher_student)
        friend_btn = QPushButton("Дос өтініші", self)
        friend_btn.clicked.connect(self._on_friend)
        self._incoming_list = QListWidget(self)
        accept_btn = QPushButton("Қабылдау", self)
        accept_btn.clicked.connect(self._on_accept)
        decline_btn = QPushButton("Қабылдамау", self)
        decline_btn.clicked.connect(self._on_decline)
        self._status = QLabel("", self)
        self._status.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addWidget(title)
        search_row = QHBoxLayout()
        search_row.addWidget(self._query, 1)
        search_row.addWidget(search_btn)
        layout.addLayout(search_row)
        layout.addWidget(self._results_list)
        action_row = QHBoxLayout()
        action_row.addWidget(ts_btn)
        action_row.addWidget(friend_btn)
        layout.addLayout(action_row)
        layout.addWidget(QLabel("Кіріс өтініштер", self))
        layout.addWidget(self._incoming_list)
        req_row = QHBoxLayout()
        req_row.addWidget(accept_btn)
        req_row.addWidget(decline_btn)
        layout.addLayout(req_row)
        layout.addWidget(self._status)

    def on_enter(self) -> None:
        self._refresh_incoming()

    def _selected_result(self) -> dict | None:
        row = self._results_list.currentRow()
        if row < 0 or row >= len(self._results):
            return None
        return self._results[row]

    def _selected_incoming(self) -> dict | None:
        row = self._incoming_list.currentRow()
        if row < 0 or row >= len(self._incoming):
            return None
        return self._incoming[row]

    def _on_search(self) -> None:
        try:
            self._results = self._client.search(self._query.text().strip())
        except AccountApiError as error:
            self._status.setText(str(error))
            return
        self._results_list.clear()
        for item in self._results:
            role = "Мұғалім" if item.get("role") == "teacher" else "Оқушы"
            self._results_list.addItem(QListWidgetItem(f"{item.get('public_id')} — {item.get('display_name')} ({role})"))
        self._status.setText(f"{len(self._results)} нәтиже")

    def _on_teacher_student(self) -> None:
        person = self._selected_result()
        if person is None:
            self._status.setText("Алдымен адамды таңдаңыз")
            return
        try:
            self._client.send_teacher_student(str(person["public_id"]))
        except AccountApiError as error:
            self._status.setText(str(error))
            return
        self._status.setText("Өтініш жіберілді")
        self._refresh_incoming()

    def _on_friend(self) -> None:
        person = self._selected_result()
        if person is None:
            self._status.setText("Алдымен адамды таңдаңыз")
            return
        try:
            self._client.send_friend(str(person["public_id"]))
        except AccountApiError as error:
            self._status.setText(str(error))
            return
        self._status.setText("Дос өтініші жіберілді")
        self._refresh_incoming()

    def _refresh_incoming(self) -> None:
        try:
            self._incoming = self._client.incoming()
        except AccountApiError:
            self._incoming = []
        self._incoming_list.clear()
        for item in self._incoming:
            kind = "дос" if item.get("kind") == "friend" else "мұғалім/оқушы"
            arrow = "←" if item.get("direction") == "incoming" else "→"
            self._incoming_list.addItem(
                QListWidgetItem(
                    f"{arrow} {item.get('from_display_name')} ({item.get('from_public_id')}) — {kind}"
                )
            )

    def _on_accept(self) -> None:
        item = self._selected_incoming()
        if item is None:
            self._status.setText("Өтінішті таңдаңыз")
            return
        try:
            self._client.accept(str(item["id"]))
        except AccountApiError as error:
            self._status.setText(str(error))
            return
        self._status.setText("Қабылданды")
        self._refresh_incoming()

    def _on_decline(self) -> None:
        item = self._selected_incoming()
        if item is None:
            self._status.setText("Өтінішті таңдаңыз")
            return
        try:
            self._client.decline(str(item["id"]))
        except AccountApiError as error:
            self._status.setText(str(error))
            return
        self._status.setText("Қабылданбады")
        self._refresh_incoming()
