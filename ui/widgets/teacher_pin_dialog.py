"""TeacherPinDialog — Мұғалім режиміне кіру алдындағы қарапайым PIN
диалогы (Phase 37A).

Бұл жобадағы басқа диалогтар (Guide/Report/Diagram) әдейі ``.show()``
арқылы (ЕШҚАШАН ``.exec()`` ЕМЕС) көрсетіледі — өйткені олар АШЫҚ
тұрғанда астыңғы өлшеу/serial сигналдары бөгелместен жүре беруі тиіс.
PIN диалогы көрсетілетін сәтте ЕШБІР өлшеу/serial байланысы жоқ (рөл
таңдау экраны — ``MainWindow``/``DeviceManager`` әлі жоқ, немесе рөл
ауыстыру сәті), сондықтан бұл жерде қысқа модальды ``.exec()``
қолдану дұрыс әрі қауіпсіз (қате емес, саналы ерекшелік).
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from domain.services.teacher_pin import get_configured_pin_hash, verify_pin

_TITLE_TEXT = "Мұғалім режимі"
_PROMPT_TEXT = "Мұғалім PIN кодын енгізіңіз:"
_CONFIRM_BUTTON_TEXT = "Растау"
_CANCEL_BUTTON_TEXT = "Бас тарту"
_ERROR_TEXT = "PIN қате. Қайталап көріңіз."


class TeacherPinDialog(QDialog):
    """PIN енгізуді сұрап, ``exec()``-тен ``QDialog.Accepted``/``Rejected``
    қайтаратын қарапайым модальды диалог.

    ``expected_pin_hash`` тестілеу үшін ауыстырылатын параметр — әдепкі
    бойынша ``teacher_pin.get_configured_pin_hash()`` (``APL_TEACHER_PIN``
    орта айнымалысын немесе dev әдепкісін оқиды).
    """

    def __init__(
        self, expected_pin_hash: str | None = None, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(_TITLE_TEXT)
        self._expected_pin_hash = expected_pin_hash or get_configured_pin_hash()

        prompt_label = QLabel(_PROMPT_TEXT, self)

        self._pin_edit = QLineEdit(self)
        self._pin_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._pin_edit.returnPressed.connect(self._on_confirm_clicked)

        self._error_label = QLabel("", self)
        self._error_label.setProperty("role", "error")
        self._error_label.setWordWrap(True)
        self._error_label.setVisible(False)

        self._confirm_button = QPushButton(_CONFIRM_BUTTON_TEXT, self)
        self._confirm_button.setDefault(True)
        self._confirm_button.clicked.connect(self._on_confirm_clicked)

        self._cancel_button = QPushButton(_CANCEL_BUTTON_TEXT, self)
        self._cancel_button.clicked.connect(self.reject)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(self._cancel_button)
        button_row.addWidget(self._confirm_button)

        layout = QVBoxLayout(self)
        layout.addWidget(prompt_label)
        layout.addWidget(self._pin_edit)
        layout.addWidget(self._error_label)
        layout.addLayout(button_row)

    def _on_confirm_clicked(self) -> None:
        if verify_pin(self._pin_edit.text(), self._expected_pin_hash):
            self.accept()
            return
        self._error_label.setText(_ERROR_TEXT)
        self._error_label.setVisible(True)
        self._pin_edit.clear()
        self._pin_edit.setFocus()
