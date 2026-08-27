"""ExperimentDiagramDialog — тәжірибенің НАҚТЫ (пайдаланушы дайындаған,
Fritzing-тәрізді) қосылым суретін көрсететін диалог (Phase 36.1).

Бұл диалог ЕШБІР сурет генерациясын/қайта салуды жасамайды — тек
``ExperimentDiagram.image_path``-тағы дайын PNG файлды ``QPixmap``-пен
жүктеп, масштабтап көрсетеді. ``LiveGraphWidget``/``MeasurementWorkspace``/
coordinator-ге ЕШБІР сілтемесі жоқ (``ExperimentGuideDialog``-пен БІРДЕЙ
оқшаулау принципі) — ашу/жабу өлшеу/график/A-B/region/zoom-pan күйіне
архитектуралық түрде тие алмайды. Тек оқу үшін (read-only) — ешбір serial
командасы жіберілмейді, ешбір өлшеу тоқтатылмайды.

``.show()`` арқылы (ЕШҚАШАН ``.exec()`` ЕМЕС) көрсетіледі.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from domain.entities.experiment_definition import ExperimentDiagram

_SUBTITLE_TEXT = "Қосылу схемасы"
_CLOSE_BUTTON_TEXT = "Жабу"
_DEFAULT_SIZE = (900, 720)

_MIN_ZOOM = 0.25
_MAX_ZOOM = 4.0
_ZOOM_STEP = 1.25


class ExperimentDiagramDialog(QDialog):
    """Бір ``ExperimentDiagram``-ге арналған, масштабталатын диалог терезесі.

    Барлық zoom операциясы ӘРҚАШАН бастапқы (``self._original_pixmap``)
    суреттен қайта масштабталады — масштабталған суретті ҚАЙТА
    масштабтау ЕШҚАШАН болмайды, сондықтан қайталап үлкейту/кішірейту
    сурет сапасын нашарлатпайды.
    """

    def __init__(
        self, experiment_title: str, diagram: ExperimentDiagram, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{_SUBTITLE_TEXT} — {experiment_title}")
        self.resize(*_DEFAULT_SIZE)

        self._original_pixmap = QPixmap(diagram.image_path)
        self._zoom_factor = 1.0
        self._has_applied_initial_fit = False

        title_label = QLabel(experiment_title, self)
        title_font = title_label.font()
        title_font.setBold(True)
        title_font.setPointSize(title_font.pointSize() + 4)
        title_label.setFont(title_font)

        subtitle_label = QLabel(_SUBTITLE_TEXT, self)
        subtitle_label.setProperty("role", "secondary")

        header_layout = QVBoxLayout()
        header_layout.addWidget(title_label)
        header_layout.addWidget(subtitle_label)

        self._zoom_out_button = QPushButton("− Кішірейту", self)
        self._zoom_out_button.setToolTip("Суретті кішірейту")
        self._zoom_out_button.clicked.connect(self._on_zoom_out_clicked)

        self._zoom_in_button = QPushButton("+ Үлкейту", self)
        self._zoom_in_button.setToolTip("Суретті үлкейту")
        self._zoom_in_button.clicked.connect(self._on_zoom_in_clicked)

        self._reset_button = QPushButton("↺ Қалпына келтіру", self)
        self._reset_button.setToolTip("Әдепкі масштабқа қайтару")
        self._reset_button.clicked.connect(self._on_fit_to_window_clicked)

        self._fit_button = QPushButton("⤢ Терезеге сыйдыру", self)
        self._fit_button.setToolTip("Суретті терезе өлшеміне сыйдыру")
        self._fit_button.clicked.connect(self._on_fit_to_window_clicked)

        toolbar_layout = QHBoxLayout()
        toolbar_layout.addWidget(self._zoom_out_button)
        toolbar_layout.addWidget(self._zoom_in_button)
        toolbar_layout.addWidget(self._reset_button)
        toolbar_layout.addWidget(self._fit_button)
        toolbar_layout.addStretch(1)

        self._image_label = QLabel(self)
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._scroll_area = QScrollArea(self)
        self._scroll_area.setWidgetResizable(False)
        self._scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._scroll_area.setWidget(self._image_label)

        self._caption_label: QLabel | None = None
        if diagram.caption:
            self._caption_label = QLabel(diagram.caption, self)
            self._caption_label.setWordWrap(True)
            self._caption_label.setProperty("role", "secondary")

        self._close_button = QPushButton(_CLOSE_BUTTON_TEXT, self)
        self._close_button.clicked.connect(self.close)

        footer_layout = QHBoxLayout()
        footer_layout.addStretch(1)
        footer_layout.addWidget(self._close_button)

        layout = QVBoxLayout(self)
        layout.addLayout(header_layout)
        layout.addLayout(toolbar_layout)
        layout.addWidget(self._scroll_area, 1)
        if self._caption_label is not None:
            layout.addWidget(self._caption_label)
        layout.addLayout(footer_layout)

        # Диалог әлі көрсетілмегенде (show() шақырылмаған) scroll area-ның
        # viewport өлшемі ЖАРАМСЫЗ болады (layout әлі activate етілмеген),
        # сондықтан fit-to-window есептеу ҚАТЕ нәтиже берер еді. Осы себепті
        # мұнда тек 1:1 (zoom=1.0) синхронды түрде көрсетіледі — сурет
        # ЕШҚАШАН бос болмайды, тіпті show() шақырылмаса да. Нақты
        # fit-to-window есебі ТЕК showEvent()-те (нақты geometry белгілі
        # болғанда) бір-ақ рет қолданылады.
        self._render_pixmap()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._has_applied_initial_fit:
            self._has_applied_initial_fit = True
            self._apply_fit_to_window()

    # ---- Ішкі логика -----------------------------------------------------

    def _on_zoom_in_clicked(self) -> None:
        self._set_zoom_factor(self._zoom_factor * _ZOOM_STEP)

    def _on_zoom_out_clicked(self) -> None:
        self._set_zoom_factor(self._zoom_factor / _ZOOM_STEP)

    def _on_fit_to_window_clicked(self) -> None:
        self._apply_fit_to_window()

    def _apply_fit_to_window(self) -> None:
        """"Қалпына келтіру" МЕН "Терезеге сыйдыру" — әдейі БІРДЕЙ
        операция (спецификация reset-ті "returns to default fit" деп
        анықтайды), жасанды айырмашылық жасалмайды.
        """
        pixmap_width = self._original_pixmap.width()
        pixmap_height = self._original_pixmap.height()
        if pixmap_width <= 0 or pixmap_height <= 0:
            return
        viewport_size = self._scroll_area.viewport().size()
        width_ratio = viewport_size.width() / pixmap_width
        height_ratio = viewport_size.height() / pixmap_height
        self._set_zoom_factor(min(width_ratio, height_ratio))

    def _set_zoom_factor(self, factor: float) -> None:
        if factor <= 0:
            return
        self._zoom_factor = max(_MIN_ZOOM, min(_MAX_ZOOM, factor))
        self._render_pixmap()

    def _render_pixmap(self) -> None:
        if self._original_pixmap.isNull():
            return
        target_width = max(1, round(self._original_pixmap.width() * self._zoom_factor))
        target_height = max(1, round(self._original_pixmap.height() * self._zoom_factor))
        scaled = self._original_pixmap.scaled(
            target_width,
            target_height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._image_label.setPixmap(scaled)
        self._image_label.resize(scaled.size())
