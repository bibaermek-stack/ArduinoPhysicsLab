"""MeasurementTableWidget — таңдалған тәжірибеге бейімделетін, measurement
тарихын тек оқуға арналған кесте түрінде көрсететін widget.

Бұл виджет тек көрсетуге жауап береді — ешбір физикалық шаманы
есептемейді, тек ``Measurement.get_value()``-ден дайын мәндерді алып,
``QTableView``-ге жол ретінде қосады. Бағандар ``configure_channels()``
арқылы берілген арналарға сай динамикалық құрылады: бірінші баған
әрқашан "№", қалғандары "{display_name} ({unit})" пішімінде.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QSizePolicy,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from domain.entities.measurement import Measurement
from domain.entities.sensor_channel import SensorChannel

_ROW_NUMBER_COLUMN_TITLE = "№"
_NO_VALUE_TEXT = "—"
_DEFAULT_DECIMALS = 3


class MeasurementTableWidget(QWidget):
    """Measurement тарихын тек оқуға арналған, динамикалық бағанды кесте
    түрінде көрсететін виджет.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # Phase 32: measurement table — graph/table workspace-тің
        # primary икемді аймағы, екі бағытта да Expanding болуы тиіс
        # (терезе биіктелген сайын көбірек жол көрінуі керек).
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._row_count = 0
        self._channels: tuple[SensorChannel, ...] = ()
        self._column_index_by_key: dict[str, int] = {}

        self._model = QStandardItemModel(0, 1, self)
        self._model.setHorizontalHeaderLabels([_ROW_NUMBER_COLUMN_TITLE])

        self._table_view = QTableView(self)
        self._table_view.setObjectName("MeasurementTableView")
        self._table_view.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._table_view.setModel(self._model)
        self._table_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table_view.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._table_view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table_view.setAlternatingRowColors(True)
        self._table_view.verticalHeader().setVisible(False)
        self._table_view.verticalHeader().setDefaultSectionSize(32)
        self._table_view.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )

        layout = QVBoxLayout(self)
        layout.addWidget(self._table_view)

    # ---- Public API -----------------------------------------------------

    def configure_channels(self, channels: tuple[SensorChannel, ...]) -> None:
        """Кестені жаңа тәжірибеге бейімдейді: "№" бағанынан кейін
        ``channels`` ретімен "{display_name} ({unit})" бағандарын құрады.
        Ескі жолдар толық тазаланады.
        """
        self._channels = tuple(channels)
        headers = [_ROW_NUMBER_COLUMN_TITLE] + [
            f"{channel.display_name} ({channel.unit})" if channel.unit else channel.display_name
            for channel in self._channels
        ]
        self._column_index_by_key = {
            channel.key: index + 1 for index, channel in enumerate(self._channels)
        }

        self._model.clear()
        self._model.setColumnCount(len(headers))
        self._model.setHorizontalHeaderLabels(headers)
        self._row_count = 0

    def set_column_visible(self, key: str, visible: bool) -> None:
        """``key`` арнасының бағанын жасырады/көрсетеді (мыс. Қуат toggle).

        Тек ``QTableView``-тің view-деңгейлік hide/show механизмін
        қолданады (``setColumnHidden``) — модельдегі деректер ЕШҚАШАН
        өшірілмейді/қайта құрылмайды, сондықтан бұрын жиналған жолдар
        да toggle ON еткенде дереу дұрыс мәнмен көрінеді (backfill
        қажет емес). Белгісіз ``key`` үшін ешнәрсе істемейді.
        """
        column_index = self._column_index_by_key.get(key)
        if column_index is None:
            return
        self._table_view.setColumnHidden(column_index, not visible)

    def append_measurement(self, measurement: Measurement) -> None:
        """Бір ``Measurement``-тен кестеге, тек configured арналар
        бойынша, жаңа жол қосады. Толық refresh жасалмайды — тек бір жол
        қосылады. Соңынан автоматты scroll жасалады. Ешбір exception
        сыртқа шықпайды.
        """
        try:
            self._row_count += 1
            row_items = [self._make_item(str(self._row_count))]
            for channel in self._channels:
                value = measurement.get_value(channel.key)
                text = (
                    _NO_VALUE_TEXT
                    if value is None
                    else f"{value:.{channel.decimals}f}"
                )
                row_items.append(self._make_item(text))

            self._model.appendRow(row_items)
            self._table_view.scrollToBottom()
        except Exception:  # қорғаныс: болжанбаған қате де UI-ды құлатпайды
            return

    def clear(self) -> None:
        """Барлық жолды өшіреді. Бағандар (конфигурация) қалады."""
        self._model.removeRows(0, self._model.rowCount())
        self._row_count = 0

    @staticmethod
    def _make_item(text: str) -> QStandardItem:
        item = QStandardItem(text)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item.setEditable(False)
        return item
