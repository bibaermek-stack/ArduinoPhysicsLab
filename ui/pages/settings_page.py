"""SettingsPage — Arduino Physics Lab жүйесінің параметрлерін басқару беті
(Phase 22).

Осы бет ешбір жаңа баптау сақтау жүйесін ЖАСАМАЙДЫ — ``core/config.py``/
``infrastructure/storage/paths.py`` бос TODO stub-тар болғандықтан,
жалғыз шын мәнінде РЕСТАРТТАН аман қалатын, өзгертілетін баптау —
"Графикті автоматты масштабтау" — ``AppPreferences`` (``QSettings``-негізді
сервис) арқылы сақталады. Қалған жолдар (тіл/тема/baud rate/экспорт
пішімі/дерекқор орны) ҚАЗІР архитектурада бір ғана нақты мәнге ие,
сондықтан ТЕК ақпараттық түрде (өзгертуге болмайтын) көрсетіледі — §
"Do not fake localization/dark mode/export formats".

Әдейі ОМИТ етілген (себебі):
- "График терезесі" (10с/30с/60с) — ``LiveGraphWidget._MAX_POINTS`` тек
  НҮКТЕ санына негізделген cap, УАҚЫТ терезесі концепциясы МҮЛДЕ жоқ;
  осыны қосу графикалық рендеринг архитектурасын қайта құруды талап
  етер еді (§ "Do not rewrite the plotting architecture").
- "Өлшеу мәндерінің дәлдігі" — ``CalculationEngine``/``PacketParser``
  дисплей дәлдігін басқаратын БІРДЕЙ орталық нүкте жоқ; әр виджет өз
  пішімдеу форматын қатты кодтайды, жаһандық "дәлдік" баптауы қазір
  МАҒЫНАСЫЗ болар еді.
- "Құрылғыларды автоматты түрде жаңарту" — периодты COM-порт
  сканерлеу МҮЛДЕ жоқ (тек қолмен "↻ Жаңарту"), фондық watcher жасау
  осы Phase-тің ауқымынан тыс (§ "Do not build a background COM-port
  watcher").
- "Соңғы құрылғыны есте сақтау" — тұрақты құрылғы identity (COM
  нөмірінен бөлек) ЖОҚ; ham COM нөмірін permanent identity ретінде
  сақтау қауіпті болар еді (§ "never persist raw COM numbers as
  permanent identity").
"""

from __future__ import annotations

from PySide6.QtCore import QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from infrastructure.storage.app_preferences import AppPreferences
from infrastructure.storage.database import get_default_database_path

# § ``infrastructure/serial_comm/device_identifier.py``/``device_manager.py``/
# ``ui/pages/devices_page.py``-мен БІРДЕЙ канондық протокол мәні (§ audit —
# "do not assume 115200" тексерілді, бұл ШЫН МӘНІНДЕ протоколда бекітілген).
_CANONICAL_BAUD_RATE = 115200

_RESET_CONFIRM_TITLE = "Баптауларды қалпына келтіру"
_RESET_CONFIRM_TEXT = "Әдепкі баптауларды қалпына келтіресіз бе?"
_RESET_CONFIRM_BUTTON = "Қалпына келтіру"
_RESET_CANCEL_BUTTON = "Болдырмау"


def _make_background_transparent(widget: QWidget) -> None:
    """§ ``devices_page._make_background_transparent()``-пен БІРДЕЙ себеп —
    instance-деңгейлік ``setStyleSheet()`` ТЕК жеке ``QLabel``-ге, ЕШҚАШАН
    интерактивті балалары бар контейнерге қолданылмайды (§ Phase 20
    ``QuestionBankPage`` регрессиясы)."""
    widget.setStyleSheet("background-color: transparent;")


def confirm_reset(parent: QWidget) -> bool:
    """§ ``question_bank_page.confirm_delete()``-пен БІРДЕЙ тәсіл —
    ``QDialogButtonBox.StandardButton`` авто-мәтіні (Cancel/OK) қазақшаға
    аударылмайды, сондықтан мәтіні НАҚТЫ көрсетілген жай батырмалар
    қолданылады."""
    box = QMessageBox(parent)
    box.setWindowTitle(_RESET_CONFIRM_TITLE)
    box.setText(_RESET_CONFIRM_TEXT)
    reset_button = box.addButton(_RESET_CONFIRM_BUTTON, QMessageBox.ButtonRole.DestructiveRole)
    cancel_button = box.addButton(_RESET_CANCEL_BUTTON, QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(cancel_button)
    box.exec()
    return box.clickedButton() is reset_button


class SettingsPage(QWidget):
    """Қолданба баптауларына арналған бет — Analytics/Devices-пен БІРДЕЙ
    навигация тәртібі (тек sidebar, "← Артқа" батырмасы ЖОҚ)."""

    # § Multi-Teacher Accounts §7 "Add a teacher management section
    # inside: Баптаулар" — SettingsPage ӨЗІ навигацияны білмейді (§
    # "Sidebar-дың Router-ді өзі білмейді" принципімен БІРДЕЙ), тек
    # сұраныс сигналын шығарады, ``MainWindow`` ``router.navigate(
    # "teacher_management")``-ке аударады.
    manage_teachers_requested = Signal()

    # § Offline-First + Cloud Sync Foundation §15 "Manual Sync":
    # SettingsPage ешбір SyncEngine/SyncThreadController білмейді (§
    # "Sidebar-дың Router-ді өзі білмейді" принципімен БІРДЕЙ), тек
    # сұраныс сигналын шығарады.
    sync_now_requested = Signal()

    def __init__(
        self,
        app_preferences: AppPreferences | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._app_preferences = app_preferences or AppPreferences()
        self._confirm_reset = confirm_reset
        self._build_ui()

    # ---- UI құрылысы -----------------------------------------------------

    def _build_ui(self) -> None:
        title_label = QLabel("Баптаулар", self)
        title_font = title_label.font()
        title_font.setBold(True)
        title_font.setPointSize(title_font.pointSize() + 4)
        title_label.setFont(title_font)

        subtitle_label = QLabel(
            "Arduino Physics Lab жүйесінің параметрлерін басқару", self
        )
        subtitle_label.setProperty("role", "secondary")
        _make_background_transparent(title_label)
        _make_background_transparent(subtitle_label)

        header_layout = QVBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.addWidget(title_label)
        header_layout.addWidget(subtitle_label)

        self._auto_scale_checkbox = QCheckBox("Графикті автоматты масштабтау", self)
        self._auto_scale_checkbox.setChecked(
            self._app_preferences.get_auto_scale_default()
        )
        self._auto_scale_checkbox.setToolTip(
            "Жаңа өлшеу графигі осы күймен ашылады. Белсенді өлшеуге әсер етпейді."
        )
        self._auto_scale_checkbox.toggled.connect(self._on_auto_scale_toggled)
        _make_background_transparent(self._auto_scale_checkbox)

        self._reset_button = QPushButton("Әдепкі баптауларды қалпына келтіру", self)
        self._reset_button.clicked.connect(self._on_reset_clicked)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.addLayout(header_layout)
        layout.addWidget(self._build_general_panel())
        layout.addWidget(self._build_measurement_panel())
        layout.addWidget(self._build_devices_panel())
        layout.addWidget(self._build_data_panel())
        layout.addWidget(self._build_teachers_panel())
        layout.addWidget(self._build_sync_panel())
        layout.addWidget(self._reset_button, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addStretch(1)

    def _build_panel_frame(self, title: str) -> tuple[QFrame, QVBoxLayout]:
        """§ ``analytics_page._build_panel_frame()``-пен БІРДЕЙ
        DashboardPanel/cardTitle қайта пайдалану."""
        panel = QFrame(self)
        panel.setObjectName("DashboardPanel")

        title_label = QLabel(title, panel)
        title_label.setProperty("role", "cardTitle")
        _make_background_transparent(title_label)

        layout = QVBoxLayout(panel)
        layout.addWidget(title_label)
        layout.setSpacing(12)
        return panel, layout

    def _build_row(self, label_text: str, control: QWidget) -> QHBoxLayout:
        row = QHBoxLayout()
        label = QLabel(label_text, control.parentWidget())
        _make_background_transparent(label)
        row.addWidget(label)
        row.addStretch(1)
        control.setMinimumWidth(200)
        control.setMaximumWidth(240)
        if isinstance(control, QLabel):
            control.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            _make_background_transparent(control)
        row.addWidget(control)
        return row

    # ---- ЖАЛПЫ -------------------------------------------------------------

    def _build_general_panel(self) -> QFrame:
        panel, layout = self._build_panel_frame("ЖАЛПЫ")

        # § "informational only if no real localization exists" —
        # audit: домен/UI мәтіндерінің БАРЛЫҒЫ қазақ тілінде қатты
        # кодталған, ешбір орыс/ағылшын аудармасы ЖОҚ.
        language_value = QLabel("Қазақша", panel)
        language_value.setProperty("role", "secondary")
        layout.addLayout(self._build_row("Тіл", language_value))

        # § "theme control showing 'Ашық' only unless dark mode is
        # genuinely, fully implemented app-wide" — audit: ThemeManager-де
        # ЖАЛҒЫЗ ғана light палитра бар, dark mode МҮЛДЕ ЖОҚ.
        theme_value = QLabel("Ашық", panel)
        theme_value.setProperty("role", "secondary")
        layout.addLayout(self._build_row("Тема", theme_value))

        return panel

    # ---- ӨЛШЕУ -------------------------------------------------------------

    def _build_measurement_panel(self) -> QFrame:
        panel, layout = self._build_panel_frame("ӨЛШЕУ")

        row = QHBoxLayout()
        row.addWidget(self._auto_scale_checkbox)
        row.addStretch(1)
        layout.addLayout(row)

        hint_label = QLabel(
            "Жаңа өлшеу графигінің бастапқы масштабтау күйі.", panel
        )
        hint_label.setProperty("role", "secondary")
        hint_label.setWordWrap(True)
        _make_background_transparent(hint_label)
        layout.addWidget(hint_label)

        return panel

    # ---- ҚҰРЫЛҒЫЛАР --------------------------------------------------------

    def _build_devices_panel(self) -> QFrame:
        panel, layout = self._build_panel_frame("ҚҰРЫЛҒЫЛАР")

        baud_value = QLabel(f"{_CANONICAL_BAUD_RATE} baud", panel)
        baud_value.setProperty("role", "secondary")
        layout.addLayout(self._build_row("Әдепкі байланыс жылдамдығы", baud_value))

        return panel

    # ---- ДЕРЕКТЕР ----------------------------------------------------------

    def _build_data_panel(self) -> QFrame:
        panel, layout = self._build_panel_frame("ДЕРЕКТЕР")

        self._database_path = get_default_database_path()

        database_value = QLabel(self._database_path.name, panel)
        database_value.setProperty("role", "secondary")
        layout.addLayout(self._build_row("Дерекқор", database_value))

        # § Phase 9 (Production Deployment) Part F "Diagnostics" — "Local
        # storage: DB reachable, path". Қысқа "Қолжетімділік" мәні
        # ``_build_row``-дың тар (240px) бағанына сияды, БІРАҚ толық жол
        # ұзын болуы мүмкін болғандықтан ``_sync_status_label``-мен
        # БІРДЕЙ, толық енді wrap ететін бөлек жол ретінде көрсетіледі.
        reachable = self._database_path.is_file()
        reachability_value = QLabel(
            "Қолжетімді" if reachable else "Қолжетімді емес", panel
        )
        reachability_value.setProperty("role", "secondary")
        layout.addLayout(self._build_row("Қолжетімділік", reachability_value))

        database_path_label = QLabel(str(self._database_path), panel)
        database_path_label.setProperty("role", "secondary")
        database_path_label.setWordWrap(True)
        _make_background_transparent(database_path_label)
        layout.addWidget(database_path_label)

        # § "Results/Data Journal already has export support" — audit:
        # ``DataJournalPage`` тек ``CSVExporter`` қолданады (§
        # ``_on_export_clicked()``), сондықтан ТЕК шын жұмыс істейтін
        # пішім көрсетіледі (§ "do not show XLSX/PDF unless they
        # actually exist" — Excel/PDF exporter-лер бар, БІРАҚ Data
        # Journal экспорт жолында ЕШҚАШАН қолданылмайды).
        export_value = QLabel("CSV", panel)
        export_value.setProperty("role", "secondary")
        layout.addLayout(self._build_row("Экспорт пішімі", export_value))

        open_folder_button = QPushButton("Деректер қалтасын ашу", panel)
        open_folder_button.clicked.connect(self._on_open_data_folder_clicked)
        open_folder_row = QHBoxLayout()
        open_folder_row.addStretch(1)
        open_folder_row.addWidget(open_folder_button)
        layout.addLayout(open_folder_row)

        return panel

    # ---- МҰҒАЛІМДЕР (Multi-Teacher Accounts §7) -----------------------------

    def _build_teachers_panel(self) -> QFrame:
        panel, layout = self._build_panel_frame("МҰҒАЛІМДЕР")

        self._teacher_count_label = QLabel(panel)
        self._teacher_count_label.setProperty("role", "secondary")
        self._teacher_count_label.setWordWrap(True)
        _make_background_transparent(self._teacher_count_label)
        self._update_teacher_count_text(0)
        layout.addWidget(self._teacher_count_label)

        manage_teachers_button = QPushButton("Мұғалімдерді басқару →", panel)
        manage_teachers_button.setObjectName("PrimaryButton")
        manage_teachers_button.clicked.connect(self.manage_teachers_requested)
        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(manage_teachers_button)
        layout.addLayout(button_row)

        return panel

    # ---- БҰЛТТЫҚ СИНХРОНДАУ (§ Offline-First + Cloud Sync Foundation §15) --

    def _build_sync_panel(self) -> QFrame:
        panel, layout = self._build_panel_frame("БҰЛТТЫҚ СИНХРОНДАУ")

        self._sync_enabled_checkbox = QCheckBox("Онлайн синхрондауды қосу", panel)
        self._sync_enabled_checkbox.setChecked(self._app_preferences.get_sync_enabled())
        self._sync_enabled_checkbox.setToolTip(
            "Қосылса, қолданба ортақ сервермен дерек алмасады. Интернет жоқ кезде жергілікті жұмыс істей береді."
        )
        self._sync_enabled_checkbox.toggled.connect(self._on_sync_enabled_toggled)
        _make_background_transparent(self._sync_enabled_checkbox)
        layout.addWidget(self._sync_enabled_checkbox)

        url_label = QLabel("Сервер мекенжайы", panel)
        _make_background_transparent(url_label)
        layout.addWidget(url_label)

        self._sync_url_edit = QLineEdit(panel)
        self._sync_url_edit.setText(self._app_preferences.get_sync_api_base_url())
        self._sync_url_edit.setPlaceholderText("https://your-server.example")
        self._sync_url_edit.setClearButtonEnabled(True)
        self._sync_url_edit.editingFinished.connect(self._on_sync_url_editing_finished)
        layout.addWidget(self._sync_url_edit)

        self._sync_url_error_label = QLabel("", panel)
        self._sync_url_error_label.setProperty("role", "secondary")
        self._sync_url_error_label.setWordWrap(True)
        _make_background_transparent(self._sync_url_error_label)
        layout.addWidget(self._sync_url_error_label)

        hint_label = QLabel(
            "Осы мекенжайдағы ортақ сервер арқылы мұғалім мен оқушы деректері "
            "үндестіріледі. Интернет болмаса қолданба жергілікті жұмыс істей береді.",
            panel,
        )
        hint_label.setProperty("role", "secondary")
        hint_label.setWordWrap(True)
        _make_background_transparent(hint_label)
        layout.addWidget(hint_label)

        self._sync_status_label = QLabel(panel)
        self._sync_status_label.setProperty("role", "secondary")
        self._sync_status_label.setWordWrap(True)
        _make_background_transparent(self._sync_status_label)
        self._update_sync_status_text("")
        layout.addWidget(self._sync_status_label)

        sync_now_button = QPushButton("Қазір синхрондау", panel)
        sync_now_button.clicked.connect(self.sync_now_requested)
        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(sync_now_button)
        layout.addLayout(button_row)

        return panel

    def set_sync_status_text(self, text: str) -> None:
        """``MainWindow`` синхрондау мәртебесі өзгерген сайын осыны
        шақырады — ``set_teacher_count()``-пен БІРДЕЙ "dumb display"
        принципі (§ SettingsPage ешбір ``SyncEngine`` білмейді)."""
        self._update_sync_status_text(text)

    def _update_sync_status_text(self, text: str) -> None:
        self._sync_status_label.setText(text or "Синхрондау әлі басталған жоқ")

    def set_teacher_count(self, count: int) -> None:
        """``MainWindow`` мұғалім тізімі өзгерген сайын (§ ``Teacher
        ManagementPage.teachers_changed``) осыны шақырады — SettingsPage
        ешбір репозиторий білмейді (§ established "dumb display" принципі,
        ``Sidebar.set_active_student_text()``-пен БІРДЕЙ)."""
        self._update_teacher_count_text(count)

    def _update_teacher_count_text(self, count: int) -> None:
        self._teacher_count_label.setText(f"Жүйеде тіркелген белсенді мұғалім саны: {count}")

    # ---- Router интерфейсі --------------------------------------------------

    def on_enter(self) -> None:
        """§ Analytics/Devices-пен БІРДЕЙ конвенция — бет ашылғанда ағымдағы
        баптау мәндерін қайта синхрондайды (мыс. басқа терезеден
        өзгертілген болса)."""
        self._auto_scale_checkbox.blockSignals(True)
        self._auto_scale_checkbox.setChecked(
            self._app_preferences.get_auto_scale_default()
        )
        self._auto_scale_checkbox.blockSignals(False)
        self._reload_sync_controls()

    def _reload_sync_controls(self) -> None:
        self._sync_enabled_checkbox.blockSignals(True)
        self._sync_enabled_checkbox.setChecked(self._app_preferences.get_sync_enabled())
        self._sync_enabled_checkbox.blockSignals(False)
        self._sync_url_edit.blockSignals(True)
        self._sync_url_edit.setText(self._app_preferences.get_sync_api_base_url())
        self._sync_url_edit.blockSignals(False)
        self._sync_url_error_label.setText("")

    # ---- Пайдаланушы әрекеттері -----------------------------------------

    def _on_auto_scale_toggled(self, checked: bool) -> None:
        self._app_preferences.set_auto_scale_default(checked)

    def _on_open_data_folder_clicked(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._database_path.parent)))

    def _on_reset_clicked(self) -> None:
        if not self._confirm_reset(self):
            return
        # §11 "must NOT delete students/classrooms/experiments/results/
        # measurement data or reset database content" — ``AppPreferences.
        # reset_to_defaults()`` ТЕК ӨЗ QSettings кілттерін тазалайды,
        # дерекқорға ЕШБІР қатысы жоқ.
        self._app_preferences.reset_to_defaults()
        self._auto_scale_checkbox.blockSignals(True)
        self._auto_scale_checkbox.setChecked(
            self._app_preferences.get_auto_scale_default()
        )
        self._auto_scale_checkbox.blockSignals(False)
        self._reload_sync_controls()

    def _on_sync_enabled_toggled(self, checked: bool) -> None:
        self._app_preferences.set_sync_enabled(checked)

    def _on_sync_url_editing_finished(self) -> None:
        text = self._sync_url_edit.text().strip()
        try:
            self._app_preferences.set_sync_api_base_url(text)
            self._sync_url_error_label.setText("")
            self._sync_url_edit.setText(self._app_preferences.get_sync_api_base_url())
        except ValueError:
            self._sync_url_error_label.setText(
                "URL http:// немесе https:// схемасымен басталуы керек"
            )
            self._sync_url_edit.setText(self._app_preferences.get_sync_api_base_url())
