"""MeasurementCard — Vernier/LabQuest тәрізді, бір физикалық шаманы үлкен
цифрмен көрсететін readout карточкасы.

Тек презентация: label мәтінін орнатады, ``value_label`` арқылы мәнді
көрсетуге мүмкіндік береді, ешбір физикалық есеп жасамайды.
``value_label`` public атрибуты арқылы ``MeasurementWorkspace``-тің
қолданыстағы ``_value_labels: dict[str, QLabel]`` контрактісіне тікелей
сәйкес келеді — ``QLabel.setText()``/``.text()`` шақырулары өзгеріссіз
қалады, card құрылымының өзгеруі тәуелді кодқа/тесттерге әсер етпейді.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QSizePolicy, QVBoxLayout, QWidget

_NO_VALUE_TEXT = "—"


class MeasurementCard(QFrame):
    """Бір readout ("КЕРНЕУ" / "5.024 V" секілді) карточкасы."""

    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("MeasurementCard")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        self._label_widget = QLabel(label.upper(), self)
        self._label_widget.setProperty("role", "cardLabel")
        self._label_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.value_label = QLabel(_NO_VALUE_TEXT, self)
        self.value_label.setProperty("role", "cardValue")
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout = QVBoxLayout(self)
        layout.addWidget(self._label_widget)
        layout.addWidget(self.value_label)
