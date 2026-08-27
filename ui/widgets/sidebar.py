"""Sidebar — қолданба-деңгейлік collapsible навигация панелі.

``MainWindow`` бір рет жасайды (application lifetime бойы, беттер сияқты
қайта құрылмайды). Тек навигация ниетін ``navigate_requested`` сигналы
арқылы білдіреді — нақты ``Router.navigate()`` шақыруы ``MainWindow``-де
қалады, Sidebar Router-ді өзі білмейді.

Phase 37A: nav батырмалары ЕНДІ бір ортақ ``ui.navigation.navigation_config.
NAVIGATION_ITEMS`` кестесінен, ағымдағы ``role``-ге сай сүзгіленіп
құрастырылады (§6: "Do not fork navigation into separate Student/Teacher
Sidebar" — БІР класс, бір дерек көзі). ``set_role()`` батырма тізімін
қауіпсіз қайта құрады (ескі батырмалар жойылады, жаңасы сол ретпен
қосылады). Рөл индикаторы сайдбарда қалады; "Режимді ауыстыру"
батырмасы алынып тасталды — рөл аккаунтта бір рет таңдалады.
"""

import logging
from functools import lru_cache

from PySide6.QtCore import QByteArray, QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.resource_paths import resource_path
from domain.entities.user_role import UserRole
from infrastructure.serial_comm.device_manager import DeviceManager
from ui.navigation.navigation_config import NavigationItem, items_for_role

# УАҚЫТША ДИАГНОСТИКА (§ main.py-дегі debug.log).
_trace_logger = logging.getLogger("apl.trace")

_EXPANDED_WIDTH = 230
_COLLAPSED_WIDTH = 60
# Phase 41: QSplitter-мен сүйрелетін ені — жайылған күйде ЕНДІ setFixedWidth
# емес, осы [min, max] аралығы (splitter drag handle-ге мағына беру үшін).
# Жабылған күйде әлі де setFixedWidth(_COLLAPSED_WIDTH) — қалыпты
# "collapse батырмасы" ӘРЕКЕТІ ғана дәл сол енге бекітеді, кездейсоқ
# сүйреумен толық жабылу splitter.setChildrenCollapsible(False) арқылы
# бөлек блокталады (§ MainWindow).
_MIN_EXPANDED_WIDTH = 210
_MAX_EXPANDED_WIDTH = 380

_BRAND_EXPANDED_TEXT = "⚛ Arduino Physics Lab"
_BRAND_COLLAPSED_TEXT = "⚛"

_ROLE_INDICATOR_TEXT: dict[UserRole, str] = {
    UserRole.STUDENT: "Оқушы режимі",
    UserRole.TEACHER: "Мұғалім режимі",
}
# Phase 6 (Sidebar Icon Integration): "Оқушыны ауыстыру" батырмасы ЕНДІ
# нақты QIcon (Person) қолданады — 👤 emoji мәтіннен алынып тасталды.
# Phase 9: "Режимді ауыстыру" (🔁) батырмасы да ЕНДІ нақты QIcon
# (People Swap, Phase 8 зерттеуінде бекітілген — "адам↔адам" рөл
# ауыстыруға 10/10 сәйкестік) қолданады.
_SWITCH_ROLE_BUTTON_LABEL = "Режимді ауыстыру"
_SWITCH_STUDENT_BUTTON_LABEL = "Оқушыны ауыстыру"

# Design/02_FluentIcons/svg/ — Phase 5 PoC-те расталған, MIT лицензиялы
# Fluent System Icons жиынтығы (§ Design/02_FluentIcons/SOURCE.md).
_ICON_DIR = resource_path("Design", "02_FluentIcons", "svg")
_SWITCH_STUDENT_ICON_FILE = "ic_fluent_person_24_regular.svg"
_SWITCH_ROLE_ICON_FILE = "ic_fluent_people_swap_24_regular.svg"
# SVG path fill-і түпнұсқада қатты кодталған "#212121" (currentColor
# ЕМЕС) — таңдалған (accent көк фон, ақ мәтін) SidebarNavButton-да
# қараңғы иконка ақ мәтінмен сәйкессіз көрінер еді. Осыны түзету үшін
# ЕКІ pixmap құрылады: қалыпты (қараңғы) және ақ-түсті нұсқа, ал Qt
# соңғысын АВТОМАТТЫ (``QIcon.State.On``) тек ``isChecked()``-те
# қолданады — вендорленген SVG файлдардың өзі ЕШҚАШАН өзгертілмейді
# (жады ішінде ғана, лицензияланған файлдар бүтін қалады).
_ICON_DARK_FILL = b'fill="#212121"'
_ICON_NORMAL_FILL = b'fill="#DCE4EE"'
_ICON_SELECTED_FILL = b'fill="#FFFFFF"'
# Нақты дисплей өлшемінен тәуелсіз, әрдайым жоғары ажыратымдылықта
# рендерленеді — HiDPI/масштабтауда анық қалуы үшін.
_ICON_RENDER_PX = 64
# Phase 6: "row heights өзгермеуі тиіс" талабы бойынша ЭМПИРИКАЛЫҚ
# табылған дәл мән — ``QPushButton.sizeHint()`` тексерілді: тек мәтін
# (emoji-сіз) кездегі SidebarNavButton биіктігі 28px (padding 8px×2 +
# 13px font line height). ``ThemeManager.ICON_SIZE_SM`` (16px) осы
# бюджеттен асып, батырманы 32px-ге дейін ұлғайтады (тексерілді) —
# сондықтан ЖАЛПЫ токен ЕМЕС, осы нақты контекст үшін ЭМПИРИКАЛЫҚ 12px
# қолданылады (вендорленген 24px SVG векторлық болғандықтан кез келген
# өлшемге анық кішірейеді — бөлек "12px" файл ЖОҚ, дәл сол 24px asset
# қолданылады, тек рендер нәтижесі кішірек көрсетіледі).
_SIDEBAR_ICON_PX = 12


@lru_cache(maxsize=None)
def _load_nav_icon(svg_filename: str) -> QIcon:
    """Вендорленген Fluent SVG-ден екі күйлі ``QIcon`` құрады: ``Off``
    (қалыпты, қараңғы) және ``On`` (таңдалған/checked, ақ). Нәтиже
    файл аты бойынша кэштеледі — БІРДЕЙ SVG бірнеше nav item-де (мыс.
    "home"/"dashboard" рөлге қарай өзара айрықша) қайта пайдаланылса,
    бір ғана QIcon данасы ортақ қолданылады.
    """
    svg_bytes = (_ICON_DIR / svg_filename).read_bytes()
    icon = QIcon()
    normal_svg_bytes = svg_bytes.replace(_ICON_DARK_FILL, _ICON_NORMAL_FILL)
    icon.addPixmap(_render_svg_pixmap(normal_svg_bytes), QIcon.Mode.Normal, QIcon.State.Off)
    white_svg_bytes = svg_bytes.replace(_ICON_DARK_FILL, _ICON_SELECTED_FILL)
    icon.addPixmap(_render_svg_pixmap(white_svg_bytes), QIcon.Mode.Normal, QIcon.State.On)
    return icon


def _render_svg_pixmap(svg_bytes: bytes) -> QPixmap:
    renderer = QSvgRenderer(QByteArray(svg_bytes))
    pixmap = QPixmap(_ICON_RENDER_PX, _ICON_RENDER_PX)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    # Логикалық өлшем ``_SIDEBAR_ICON_PX``-ге тең болуы үшін — button
    # ``setIconSize(_SIDEBAR_ICON_PX, _SIDEBAR_ICON_PX)`` сұрағанда Qt
    # ЖОҒАРЫ ажыратымдылықтан downscale етеді (upscale ЕМЕС, әрдайым анық).
    pixmap.setDevicePixelRatio(_ICON_RENDER_PX / _SIDEBAR_ICON_PX)
    return pixmap


class Sidebar(QWidget):
    """Жабылып/ашылатын global навигация панелі.

    ``buttons`` сөздігі әр nav item-нің ``QPushButton``-ын атауы бойынша
    ашады — ``MainWindow`` мұны ескі ``_settings_button``/``_about_button``
    атрибут келісімін сақтау үшін пайдаланады.

    Phase 39B: белсенді оқушы индикаторы + "Оқушыны ауыстыру" батырмасы
    ТЕК Оқушы режимінде көрінеді. Sidebar ешбір репозиторий білмейді —
    мәтінді ``MainWindow`` ``set_active_student_text()`` арқылы сырттан
    итереді (device summary-мен БІРДЕЙ "dumb display widget" принципі).
    """

    navigate_requested = Signal(str)
    switch_role_requested = Signal()
    switch_student_requested = Signal()
    # Phase 41: жабу/ашу батырмасы басылған сайын жаңа collapsed күйін
    # хабарлайды — MainWindow осыны splitter.setSizes(...) арқылы нақты
    # пиксель енін ЖЕДЕЛ (анимациясыз) қайта бөлу үшін тыңдайды.
    collapse_toggled = Signal(bool)

    def __init__(
        self,
        role: UserRole = UserRole.TEACHER,
        device_manager: DeviceManager | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self._device_manager = device_manager
        self._collapsed = False
        self._role = role
        self.buttons: dict[str, QPushButton] = {}
        self._nav_items: tuple[NavigationItem, ...] = ()

        self._brand_label = QLabel(_BRAND_EXPANDED_TEXT, self)
        self._brand_label.setObjectName("SidebarBrand")

        self.collapse_button = QPushButton("⮜", self)
        self.collapse_button.setObjectName("SidebarCollapseButton")
        self.collapse_button.setFixedWidth(28)
        self.collapse_button.clicked.connect(self._on_collapse_clicked)

        top_row = QHBoxLayout()
        top_row.addWidget(self._brand_label, 1)
        top_row.addWidget(self.collapse_button)

        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)

        self._nav_column = QWidget(self)
        self._nav_layout = QVBoxLayout(self._nav_column)
        self._nav_layout.setContentsMargins(0, 0, 0, 0)

        nav_scroll_area = QScrollArea(self)
        nav_scroll_area.setWidgetResizable(True)
        nav_scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        nav_scroll_area.setWidget(self._nav_column)

        self._rebuild_nav_buttons()

        self._device_summary_label = QLabel(self)
        self._device_summary_label.setObjectName("SidebarDeviceSummary")
        self._device_summary_label.setWordWrap(True)

        separator = QFrame(self)
        separator.setFrameShape(QFrame.Shape.HLine)

        role_separator = QFrame(self)
        role_separator.setFrameShape(QFrame.Shape.HLine)

        self._role_indicator_label = QLabel(self)
        self._role_indicator_label.setObjectName("SidebarRoleIndicator")

        # § Multi-Teacher Accounts: аутентификацияланған мұғалімнің аты-
        # жөні (§ "In the existing left sidebar teacher information area,
        # display... Мұғалім режимі / Айдос Нұрланұлы") — ``_active_
        # student_label``-мен БІРДЕЙ "dumb display widget" принципі,
        # Sidebar ешбір репозиторий білмейді, мәтінді ``MainWindow``
        # ``set_active_teacher_text()`` арқылы сырттан итереді.
        self._active_teacher_label = QLabel(self)
        self._active_teacher_label.setObjectName("SidebarActiveTeacher")
        self._active_teacher_label.setWordWrap(True)

        self._active_student_label = QLabel(self)
        self._active_student_label.setObjectName("SidebarActiveStudent")
        self._active_student_label.setWordWrap(True)

        # § Offline-First + Cloud Sync Foundation §14 "Sync Status UI":
        # шағын, байқалмайтын индикатор — ЕШБІР модаль/блок ЖОҚ, офлайн
        # қалыпты жағдай ретінде көрсетіледі. ``MainWindow`` мәтін/түсті
        # ``set_sync_status_text()`` арқылы сырттан итереді (§ ``set_
        # active_teacher_text()``-пен БІРДЕЙ "dumb display" принципі).
        self._sync_status_label = QLabel(self)
        self._sync_status_label.setObjectName("SidebarSyncStatus")
        self._sync_status_label.setWordWrap(True)

        self._switch_student_button = QPushButton(_SWITCH_STUDENT_BUTTON_LABEL, self)
        self._switch_student_button.setObjectName("SidebarSwitchStudentButton")
        self._switch_student_button.setIcon(_load_nav_icon(_SWITCH_STUDENT_ICON_FILE))
        self._switch_student_button.setIconSize(QSize(_SIDEBAR_ICON_PX, _SIDEBAR_ICON_PX))
        self._switch_student_button.clicked.connect(
            lambda: _trace_logger.info("14. Sidebar: switch_student_button clicked")
        )
        self._switch_student_button.clicked.connect(self.switch_student_requested)

        self._switch_role_button = QPushButton(_SWITCH_ROLE_BUTTON_LABEL, self)
        self._switch_role_button.setObjectName("SidebarSwitchRoleButton")
        self._switch_role_button.setIcon(_load_nav_icon(_SWITCH_ROLE_ICON_FILE))
        self._switch_role_button.setIconSize(QSize(_SIDEBAR_ICON_PX, _SIDEBAR_ICON_PX))
        self._switch_role_button.clicked.connect(
            lambda: _trace_logger.info("14. Sidebar: switch_role_button ('Режімді ауыстыру') clicked")
        )
        self._switch_role_button.clicked.connect(self.switch_role_requested)
        self._switch_role_button.hide()

        self._update_role_indicator()
        self._update_student_section_visibility()
        self._update_teacher_section_visibility()

        layout = QVBoxLayout(self)
        layout.addLayout(top_row)
        layout.addWidget(nav_scroll_area, 1)
        layout.addWidget(separator)
        layout.addWidget(self._device_summary_label)
        layout.addWidget(role_separator)
        layout.addWidget(self._role_indicator_label)
        layout.addWidget(self._active_teacher_label)
        layout.addWidget(self._active_student_label)
        layout.addWidget(self._switch_student_button)
        layout.addWidget(self._sync_status_label)

        self._connect_device_manager()
        self._update_device_summary()
        self.setMinimumWidth(_MIN_EXPANDED_WIDTH)
        self.setMaximumWidth(_MAX_EXPANDED_WIDTH)
        self.resize(_EXPANDED_WIDTH, self.height())

    def set_role(self, role: UserRole) -> None:
        """Ағымдағы рөлді ауыстырып, батырма тізімін ЖӘНЕ рөл
        индикаторын қауіпсіз қайта құрады (батырмалар жойылып, жаңа рөлге
        сай тізім сол ретпен қайта қосылады).
        """
        if role is self._role:
            return
        self._role = role
        self._rebuild_nav_buttons()
        self._update_role_indicator()
        self._update_student_section_visibility()
        self._update_teacher_section_visibility()

    def role(self) -> UserRole:
        return self._role

    def set_active_student_text(self, text: str | None) -> None:
        """Белсенді оқушы мәтінін орнатады (мыс. "Оқушы: Айдос С.\\nСынып:
        8А") — Sidebar-дың өзі ешбір репозиторий сұрамайды, ``MainWindow``
        осы мәтінді есептеп сырттан итереді. ``text=None`` — таңдалмаған
        (бос жол көрсетіледі, батырма өзі рөлге қарай көрінеді/жасырылады).
        """
        self._active_student_label.setText(text or "")

    def set_active_teacher_text(self, text: str | None) -> None:
        """§ Multi-Teacher Accounts: аутентификацияланған мұғалімнің
        аты-жөнін орнатады (мыс. "Айдос Нұрланұлы") — ``set_active_
        student_text()``-пен БІРДЕЙ "dumb display" принципі. ``text=None``
        — Режімді ауыстыру/logout-тан кейін (§ "no Teacher A information
        may remain visible")."""
        self._active_teacher_label.setText(text or "")

    def set_sync_status_text(self, text: str, color: str) -> None:
        """§14 "Sync Status UI": статус мәтіні мен нүкте түсін орнатады
        (мыс. "● Синхрондалды" / "#2E7D32"). Sidebar ешбір ``SyncStatus``
        enum-ды білмейді — ``MainWindow`` дайын мәтін/түс жұбын береді."""
        self._sync_status_label.setText(text)
        self._sync_status_label.setStyleSheet(f"color: {color};")

    def set_switch_student_enabled(self, enabled: bool) -> None:
        """Белсенді өлшеу жүріп жатқанда оқушыны ауыстыру батырмасын
        өшіреді (§ "switching during an active measurement is blocked").
        """
        self._switch_student_button.setEnabled(enabled)

    def _update_student_section_visibility(self) -> None:
        is_student = self._role is UserRole.STUDENT
        self._active_student_label.setVisible(is_student and not self._collapsed)
        self._switch_student_button.setVisible(is_student)

    def _update_teacher_section_visibility(self) -> None:
        is_teacher = self._role is UserRole.TEACHER
        self._active_teacher_label.setVisible(is_teacher and not self._collapsed)

    def _rebuild_nav_buttons(self) -> None:
        while self._nav_layout.count():
            item = self._nav_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        for button in self.buttons.values():
            self._nav_group.removeButton(button)
        self.buttons = {}

        self._nav_items = items_for_role(self._role)
        for nav_item in self._nav_items:
            button = self._build_nav_button(nav_item)
            self.buttons[nav_item.key] = button
            self._nav_layout.addWidget(button)
            self._nav_group.addButton(button)
        self._nav_layout.addStretch(1)

        first_key = self._nav_items[0].key if self._nav_items else None
        if first_key is not None:
            self.buttons[first_key].setChecked(True)

    def _build_nav_button(self, nav_item: NavigationItem) -> QPushButton:
        button = QPushButton(self._button_text(nav_item), self)
        button.setObjectName("SidebarNavButton")
        button.setCheckable(True)
        if nav_item.icon_svg:
            button.setIcon(_load_nav_icon(nav_item.icon_svg))
            button.setIconSize(QSize(_SIDEBAR_ICON_PX, _SIDEBAR_ICON_PX))
        button.clicked.connect(
            lambda _checked=False, k=nav_item.key: _trace_logger.info(
                "14. Sidebar: nav button '%s' clicked", k
            )
        )
        button.clicked.connect(
            lambda _checked=False, k=nav_item.key: self.navigate_requested.emit(k)
        )
        return button

    def _button_text(self, nav_item: NavigationItem) -> str:
        # Fluent SVG-і бар item — иконка ``setIcon()`` арқылы көрінеді
        # (§ _build_nav_button), мәтінде emoji ЕНДІ қайталанбайды. Лайықты
        # вендорленген иконкасы ЖОҚ item-дер ЕСКІ emoji-негізді көрінісін
        # өзгеріссіз сақтайды.
        if nav_item.icon_svg:
            return "" if self._collapsed else nav_item.title
        return nav_item.icon if self._collapsed else f"{nav_item.icon}  {nav_item.title}"

    def _update_role_indicator(self) -> None:
        self._role_indicator_label.setText(_ROLE_INDICATOR_TEXT[self._role])

    def _on_collapse_clicked(self) -> None:
        self._collapsed = not self._collapsed
        if self._collapsed:
            self.setFixedWidth(_COLLAPSED_WIDTH)
        else:
            self.setMinimumWidth(_MIN_EXPANDED_WIDTH)
            self.setMaximumWidth(_MAX_EXPANDED_WIDTH)
            self.resize(_EXPANDED_WIDTH, self.height())
        self.collapse_button.setText("⮞" if self._collapsed else "⮜")
        self._brand_label.setText(_BRAND_COLLAPSED_TEXT if self._collapsed else _BRAND_EXPANDED_TEXT)
        for nav_item in self._nav_items:
            self.buttons[nav_item.key].setText(self._button_text(nav_item))
        self._device_summary_label.setVisible(not self._collapsed)
        self._role_indicator_label.setVisible(not self._collapsed)
        # Екі батырманың да иконкасы (People Swap / Person) collapsed/
        # expanded екеуінде setIcon() арқылы тұрақты көрінеді — тек мәтін
        # ("" / толық жазба) ауысады, ескі emoji-мен алмастыру ЕНДІ қажет
        # емес.
        self._switch_role_button.hide()
        self._switch_student_button.setText(
            "" if self._collapsed else _SWITCH_STUDENT_BUTTON_LABEL
        )
        self._update_student_section_visibility()
        self._update_teacher_section_visibility()
        self.collapse_toggled.emit(self._collapsed)

    def is_collapsed(self) -> bool:
        return self._collapsed

    def _connect_device_manager(self) -> None:
        if self._device_manager is None:
            return
        self._device_manager.device_identified.connect(self._on_device_manager_changed)
        self._device_manager.port_disconnected.connect(self._on_device_manager_changed)

    def _on_device_manager_changed(self, *_args: object) -> None:
        self._update_device_summary()

    def _update_device_summary(self) -> None:
        count = 0
        if self._device_manager is not None:
            count = len(self._device_manager.get_connected_devices())
        self._device_summary_label.setText(f"🔌 Қосылған құрылғылар: {count}")
