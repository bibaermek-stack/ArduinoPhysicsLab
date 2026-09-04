"""RoleSelectionPage — қолданбаның жалғыз, толық экрандық кіру/мод-
ауыстыру беті (Phase — Mode Switch + Student Access Screen Redesign;
Phase — Teacher Login Redesign).

**Бір ғана визуалды іске асыру** (§ "CRITICAL: There must be only ONE
visual implementation for mode selection") — осы бет ҮШ жерде де қайта
пайдаланылады, ЕШБІР екінші көшірме жасалмайды:

1. ``app.py``-де — қолданба іске қосылған сәтте, ``MainWindow``/
   ``DeviceManager`` ӘЛІ ЖОҚ кезде (родитель жоқ жоғарғы деңгей терезе
   ретінде, ``ThemeManager`` стилі ӘЛДЕҚАШАН қолданылған).
2. ``MainWindow`` ІШІНДЕ — "Режімді ауыстыру" әрекеті үшін, ``Router``-ге
   ``"role_selection"`` атауымен тіркелген бет ретінде (sidebar осы
   route-та ``MainWindow`` арқылы жасырылады, § ``_on_route_changed``).
3. ``MainWindow``-дың "Оқушыны ауыстыру" әрекеті — ДӘЛ СОЛ бет, тек
   ``on_enter(view="student_login")`` арқылы бірден кіру-код көрінісіне
   өтеді (мод таңдау экраны аттап өтіледі).

**Үш ішкі көрініс** (бір виджет ІШІНДЕ ауыстырылады, ешбір жеке
route/бет ЖОҚ):
- "mode" — Оқушы/Мұғалім таңдау карточкасы.
- "student_login" — Оқушы кіру коды формасы.
- "teacher_login" — Мұғалім PIN коды формасы (§ Teacher Login Redesign
  — бұрынғы модальды ``TeacherPinDialog.exec()`` ОРНЫНА, § "Replace the
  Teacher PIN modal/dialog completely with a full-page Teacher Login
  screen"). ``TeacherPinDialog`` класы МҮЛДЕ ЖОЙЫЛМАЙДЫ (§ өз
  оқшауланған тесттері жарамды қалады), тек бұдан былай ӨНДІРІСТІК
  ағында ЕШҚАШАН ашылмайды. § Multi-Teacher Accounts фазасы: ЕНДІ
  жалғыз ортақ PIN ЕМЕС — ``domain.services.teacher_pin.
  resolve_teacher_by_pin()`` енгізілген PIN-ге сәйкес БЕЛСЕНДІ
  ``Teacher`` жазбасын ``ITeacherRepository``-ден іздейді, табылса
  ``IActiveTeacherRepository``-ге сол мұғалімнің контексін жазады
  (§ ``ActiveStudentContext``-пен БІРДЕЙ "single canonical source"
  принципі).

**Ортақ кіру-карточка құрылысы** (§ "Prefer extracting/reusing a
shared authentication-card structure") — Оқушы/Мұғалім кіру беттері
құрылымы жағынан БІРДЕЙ (brand/title/subtitle/өріс/қате
жапсырмасы/бастапқы батырма/артқа батырмасы), тек title/subtitle/
placeholder/echo-mode/submit callback өзгереді. Осы ортақтықты дәл
СОЛ ~40 жолды екі рет жазбау үшін ``_build_login_view()`` бір рет
құрастырады — objectName-дер де БІРДЕЙ ("EntryLoginView"/"EntryTitle"/
"EntryErrorLabel"/"PrimaryButton"/"HomeModuleCardAction"), сондықтан
екі карточка да дәл БІРДЕЙ QSS-пен стильденеді, ешбір жаңа QSS ережесі
қажет ЕМЕС. Оқушы кіру бетінің ӨЗІ (визуалды/мінез-құлықтық) бұл
рефакторингте МҮЛДЕ ӨЗГЕРТІЛМЕГЕН — атрибут атаулары
(``_code_edit``/``_error_label``/``_login_button``/``_login_back_
button``), хабарлама мәтіндері, whitespace-trim/enter-key/inline-error
семантикасы дәл бұрынғыдай.

Мұғалім батырмасын басу ЕНДІ ``show_teacher_login()`` арқылы осы
беттің ІШІНДЕ PIN формасына өтеді (§ бұрын: ``TeacherPinDialog``
модальды ``.exec()``). ``role_selected`` тек PIN расталғаннан кейін
шығарылады — аутентификация СЕМАНТИКАСЫ (қай PIN дұрыс, қалай
тексеріледі) МҮЛДЕ ӨЗГЕРТІЛГЕН ЖОҚ.

Оқушы кіру коды формасы ЖАЛҒЫЗ canonical дереккөзге (``IActiveStudent
Repository``) осы беттің ӨЗІ жазады (§ ``StudentSelectionPage.
_on_continue_clicked()``-пен БІРДЕЙ, established принцип — "the page
writes state, then emits a payload-less signal") — ``MainWindow`` тек
жанама UI әсерлерін (рөл/sidebar/навигация) қолданады, ЕКІНШІ
active-student айнымалысы ЕШҚАШАН жасалмайды.

Фон — ЖЕКЕ ``QPainter`` сызбасы (фото ЕМЕС), ``WorkspaceBackdrop``-тың
``paint_atom()``-ын ҚАЙТА пайдаланады (§ "Keep it consistent with the
existing visual language"), статикалық (animated=False, § "no animation
required in this phase"), өте төмен opacity-мен (0.05-0.07). Барлық үш
көрініс (mode/student_login/teacher_login) БІРДЕЙ ``self`` деңгейіндегі
``paintEvent``-ті бөліседі — фон ЕШҚАШАН көрініске байланысты
өзгермейді (§ "Teacher login must use the same approved background").
"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.resource_paths import resource_path
from domain.entities.active_student_context import ActiveStudentContext
from domain.entities.active_teacher_context import ActiveTeacherContext
from domain.entities.user_role import UserRole
from domain.interfaces.i_active_student_repository import IActiveStudentRepository
from domain.interfaces.i_active_teacher_repository import IActiveTeacherRepository
from domain.interfaces.i_student_repository import IStudentRepository
from domain.interfaces.i_teacher_repository import ITeacherRepository
from domain.interfaces.i_classroom_repository import IClassroomRepository
from domain.services.student_session import ensure_active_student
from domain.services.teacher_pin import resolve_teacher_by_pin
from infrastructure.storage.app_preferences import AppPreferences
from infrastructure.storage.sqlite_active_student_repository import SqliteActiveStudentRepository
from infrastructure.storage.sqlite_active_teacher_repository import SqliteActiveTeacherRepository
from infrastructure.storage.sqlite_student_repository import SqliteStudentRepository
from infrastructure.storage.sqlite_teacher_repository import SqliteTeacherRepository
from ui.themes.theme_manager import COLOR_ERROR, theme_color
from ui.widgets.animated_atom_widget import paint_atom

_WINDOW_TITLE = "Arduino Physics Lab"
_TAGLINE = "Мектеп физикасына арналған цифрлық зертханалық жүйе"
_STUDENT_BUTTON_TEXT = "Оқушы режимі"
_TEACHER_BUTTON_TEXT = "Мұғалім режимі"

_LOGIN_TITLE = "Оқушы ретінде кіру"
_LOGIN_SUBTITLE = "Жеке кіру кодын енгізіңіз"
_CODE_PLACEHOLDER = "Мысалы: 482731"
_EMPTY_CODE_ERROR = "Кіру кодын енгізіңіз."
_INVALID_CODE_ERROR = "Кіру коды дұрыс емес."

_TEACHER_LOGIN_TITLE = "Мұғалім ретінде кіру"
_TEACHER_LOGIN_SUBTITLE = "Мұғалім PIN кодын енгізіңіз"
_PIN_PLACEHOLDER = "PIN коды"
_EMPTY_PIN_ERROR = "PIN кодын енгізіңіз"
_INVALID_PIN_ERROR = "PIN коды қате"

_LOGIN_BUTTON_TEXT = "Кіру →"
_BACK_BUTTON_TEXT = "← Артқа"

_CARD_WIDTH = 520

# § "Fluent-compatible icon... avoid emoji" — вендорленген жиынтықта
# арнайы "мұғалім" иконкасы ЖОҚ (§ audit) — "person"/жалғыз қолжетімді,
# семантикалық жағынан ЕҢ жақын "board" иконкасы қолданылады.
_STUDENT_ICON_FILE = "ic_fluent_person_24_regular.svg"
_TEACHER_ICON_FILE = "ic_fluent_developer_board_24_regular.svg"
_ICON_DIR = resource_path("Design", "02_FluentIcons", "svg")
_ICON_RENDER_PX = 40


def _load_entry_icon(svg_filename: str) -> QIcon:
    """§ ``ui/widgets/sidebar.py::_load_nav_icon()``-мен БІРДЕЙ рендеринг
    тәсілі, бірақ жеңілдетілген (жалғыз күй — бұл батырмалар checkable
    ЕМЕС, dark/white ауысу қажет емес)."""
    svg_bytes = (_ICON_DIR / svg_filename).read_bytes().replace(
        b'fill="#212121"', b'fill="#DCE4EE"'
    )
    renderer = QSvgRenderer(QByteArray(svg_bytes))
    pixmap = QPixmap(_ICON_RENDER_PX, _ICON_RENDER_PX)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)


def _make_background_transparent(widget: QWidget) -> None:
    """§ ``devices_page._make_background_transparent()``-мен БІРДЕЙ себеп —
    жеке (leaf) ``QLabel``/интерактивті балалары ЖОҚ ``QWidget``
    контейнерлер (``_mode_view``/``_student_login_view``/``_teacher_
    login_view``) ақ ``EntrySurfaceCard`` үстінде opaque
    ``COLOR_BACKGROUND`` тіктөртбұрышын бояп кетпеуі үшін."""
    widget.setStyleSheet("background-color: transparent;")


class RoleSelectionPage(QWidget):
    """Толық экрандық кіру/мод-ауыстыру беті — 3 ішкі көрініс (mode/
    student_login/teacher_login), сидбарсыз, орталықтандырылған
    карточка.
    """

    role_selected = Signal(object)  # UserRole.TEACHER (PIN расталғаннан кейін)
    student_login_succeeded = Signal()  # active_student_repository ЖАЗЫЛҒАН, тек хабарлайды

    def __init__(
        self,
        student_repository: IStudentRepository | None = None,
        active_student_repository: IActiveStudentRepository | None = None,
        teacher_repository: ITeacherRepository | None = None,
        active_teacher_repository: IActiveTeacherRepository | None = None,
        classroom_repository: IClassroomRepository | None = None,
        preferences: AppPreferences | None = None,
        cloud_account_mode: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(_WINDOW_TITLE)
        self._cloud_account_mode = cloud_account_mode
        self._student_repository = student_repository or SqliteStudentRepository()
        self._active_student_repository = (
            active_student_repository or SqliteActiveStudentRepository()
        )
        self._teacher_repository = teacher_repository or SqliteTeacherRepository()
        self._active_teacher_repository = (
            active_teacher_repository or SqliteActiveTeacherRepository()
        )
        self._classroom_repository = classroom_repository
        self._preferences = preferences

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        centered_row = QHBoxLayout()
        centered_row.addStretch(1)

        self._card = QFrame(self)
        self._card.setObjectName("EntrySurfaceCard")
        self._card.setFixedWidth(_CARD_WIDTH)
        card_layout = QVBoxLayout(self._card)

        self._mode_view = self._build_mode_view()
        self._student_login_view = self._build_student_login_view()
        self._teacher_login_view = self._build_teacher_login_view()
        card_layout.addWidget(self._mode_view)
        card_layout.addWidget(self._student_login_view)
        card_layout.addWidget(self._teacher_login_view)

        centered_row.addWidget(self._card, 0, Qt.AlignmentFlag.AlignVCenter)
        centered_row.addStretch(1)

        outer_layout.addStretch(1)
        outer_layout.addLayout(centered_row)
        outer_layout.addStretch(1)

        self.show_mode_selection()

    # ---- Фон -----------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override name)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor(theme_color("COLOR_BACKGROUND")))

        # § "large low-opacity atom orbit motif... opacity approximately
        # 0.04-0.08" — карточкадан аулақ, жоғарғы сол бұрышқа орналасқан
        # (§ "The central login card must remain the visual focus").
        # Үш көрініске де (mode/student_login/teacher_login) БІРДЕЙ фон.
        side = min(self.width(), self.height()) * 0.62
        if side > 0:
            atom_rect = QRectF(-side * 0.22, -side * 0.22, side, side)
            paint_atom(painter, atom_rect, 0.0, opacity=0.06, animated=False)

            bottom_side = side * 0.7
            bottom_rect = QRectF(
                self.width() - bottom_side * 0.78,
                self.height() - bottom_side * 0.78,
                bottom_side,
                bottom_side,
            )
            paint_atom(painter, bottom_rect, 0.0, opacity=0.045, animated=False)

        painter.end()

    # ---- Router интерфейсі ------------------------------------------------

    def on_enter(self, view: str = "mode") -> None:
        """§ ``Router.navigate(name, **params)`` конвенциясы (§
        ``ExperimentListPage.on_enter(module=...)``-пен БІРДЕЙ) —
        ``view="student_login"`` "Оқушыны ауыстыру" әрекетінің мод таңдау
        экранын аттап өтіп, бірден кіру формасына өтуі үшін.
        """
        if view == "student_login":
            self.show_student_login()
        else:
            self.show_mode_selection()

    # ---- Көрініс ауыстыру -------------------------------------------------

    def show_mode_selection(self) -> None:
        self._mode_view.setVisible(True)
        self._student_login_view.setVisible(False)
        self._teacher_login_view.setVisible(False)
        self._student_button.setFocus()

    def show_student_login(self) -> None:
        self._clear_login_error()
        self._code_edit.clear()
        self._mode_view.setVisible(False)
        self._student_login_view.setVisible(True)
        self._teacher_login_view.setVisible(False)
        self._code_edit.setFocus()

    def show_teacher_login(self) -> None:
        self._clear_teacher_login_error()
        self._pin_edit.clear()
        self._mode_view.setVisible(False)
        self._student_login_view.setVisible(False)
        self._teacher_login_view.setVisible(True)
        self._pin_edit.setFocus()

    # ---- "mode" көрінісі -----------------------------------------------

    def _build_mode_view(self) -> QWidget:
        # § "never apply instance-level setStyleSheet to a container with
        # a specially-styled/interactive child" (§ Phase 20 регрессиясы,
        # § HomePage-тегі status-dot регрессиясы) — бұл контейнерде
        # ``EntryModeButton`` бар, сондықтан ГЛОБАЛ QSS object-name
        # селекторы қолданылады, instance-деңгейлік fix ЕМЕС.
        view = QWidget(self._card)
        view.setObjectName("EntryModeView")
        layout = QVBoxLayout(view)
        layout.setContentsMargins(0, 0, 0, 0)

        title_label = QLabel(_WINDOW_TITLE, view)
        title_label.setObjectName("EntryTitle")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        tagline_label = QLabel(_TAGLINE, view)
        tagline_label.setProperty("role", "secondary")
        tagline_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tagline_label.setWordWrap(True)
        _make_background_transparent(tagline_label)

        self._student_button = QPushButton(_STUDENT_BUTTON_TEXT, view)
        self._student_button.setObjectName("EntryModeButton")
        self._student_button.setIcon(_load_entry_icon(_STUDENT_ICON_FILE))
        self._student_button.setIconSize(QSize(_ICON_RENDER_PX, _ICON_RENDER_PX))
        self._student_button.clicked.connect(self._on_student_mode_clicked)

        self._teacher_button = QPushButton(_TEACHER_BUTTON_TEXT, view)
        self._teacher_button.setObjectName("EntryModeButton")
        self._teacher_button.setIcon(_load_entry_icon(_TEACHER_ICON_FILE))
        self._teacher_button.setIconSize(QSize(_ICON_RENDER_PX, _ICON_RENDER_PX))
        self._teacher_button.clicked.connect(self._on_teacher_clicked)

        layout.addWidget(title_label)
        layout.addWidget(tagline_label)
        layout.addSpacing(16)
        layout.addWidget(self._student_button)
        layout.addWidget(self._teacher_button)
        return view

    def _on_student_mode_clicked(self) -> None:
        # Email/Google кіруі жергілікті кіру кодын алмастырады — мұғалім
        # PIN экраны сияқты бұл форма да қалдық.
        self._activate_default_student()
        self.student_login_succeeded.emit()

    def _on_teacher_clicked(self) -> None:
        # Cloud аккаунт (email/Google) кіруі PIN-ді алмастырады — ескі
        # жергілікті PIN экраны қалдық, мұғалім батырмасы бірден рөл береді.
        self._activate_default_teacher()
        self.role_selected.emit(UserRole.TEACHER)

    def _activate_default_student(self) -> None:
        preferences = self._preferences
        ensure_active_student(
            self._student_repository,
            self._active_student_repository,
            self._classroom_repository,
            display_name=preferences.get_account_display_name() if preferences else "",
            account_id=preferences.get_account_id() if preferences else "",
            public_id=preferences.get_account_public_id() if preferences else "",
        )

    def _activate_default_teacher(self) -> None:
        current = self._active_teacher_repository.get()
        if current is not None:
            teacher = self._teacher_repository.get(current.teacher_id)
            if teacher is not None and teacher.is_active:
                return
        teachers = self._teacher_repository.list_active()
        if teachers:
            self._active_teacher_repository.set(ActiveTeacherContext(teacher_id=teachers[0].id))

    # ---- Ортақ кіру-карточка құрылысы --------------------------------------

    def _build_login_view(
        self,
        *,
        title: str,
        subtitle: str,
        placeholder: str,
        password_mode: bool,
        on_submit,
        on_back,
    ) -> tuple[QWidget, QLineEdit, QLabel, QPushButton, QPushButton]:
        """§ "Prefer extracting/reusing a shared authentication-card
        structure" — Оқушы/Мұғалім кіру карточкалары дәл БІРДЕЙ
        құрылымды (brand/title/subtitle/өріс/қате/бастапқы+артқа
        батырма) бөліседі, тек мазмұны/аутентификация логикасы
        өзгереді. objectName-дер де БІРДЕЙ, сондықтан бірде-бір жаңа
        QSS ережесі қажет емес — екеуі де дәл БІРДЕЙ ені/padding/
        border-radius/border/spacing/typography алады.
        """
        view = QWidget(self._card)
        view.setObjectName("EntryLoginView")
        layout = QVBoxLayout(view)
        layout.setContentsMargins(0, 0, 0, 0)

        brand_label = QLabel(_WINDOW_TITLE, view)
        brand_label.setProperty("role", "secondary")
        brand_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _make_background_transparent(brand_label)

        title_label = QLabel(title, view)
        title_label.setObjectName("EntryTitle")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        subtitle_label = QLabel(subtitle, view)
        subtitle_label.setProperty("role", "secondary")
        subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _make_background_transparent(subtitle_label)

        field_edit = QLineEdit(view)
        field_edit.setPlaceholderText(placeholder)
        field_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if password_mode:
            field_edit.setEchoMode(QLineEdit.EchoMode.Password)
        field_edit.returnPressed.connect(on_submit)

        error_label = QLabel("", view)
        error_label.setObjectName("EntryErrorLabel")
        error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        error_label.setVisible(False)

        login_button = QPushButton(_LOGIN_BUTTON_TEXT, view)
        login_button.setObjectName("PrimaryButton")
        login_button.clicked.connect(on_submit)

        back_button = QPushButton(_BACK_BUTTON_TEXT, view)
        back_button.setObjectName("HomeModuleCardAction")
        back_button.clicked.connect(on_back)

        layout.addWidget(brand_label)
        layout.addSpacing(8)
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        layout.addSpacing(12)
        layout.addWidget(field_edit)
        layout.addWidget(error_label)
        layout.addSpacing(8)
        layout.addWidget(login_button)
        layout.addWidget(back_button, 0, Qt.AlignmentFlag.AlignCenter)
        return view, field_edit, error_label, login_button, back_button

    def _clear_field_error(self, error_label: QLabel, field: QLineEdit) -> None:
        error_label.setVisible(False)
        error_label.setText("")
        field.setStyleSheet("")

    def _show_field_error(self, error_label: QLabel, field: QLineEdit, message: str) -> None:
        # § "Input should receive a subtle error border" — жеке (leaf)
        # QLineEdit, интерактивті балалары жоқ, instance-деңгейлік
        # setStyleSheet() қауіпсіз (§ established leaf-widget паттерні).
        error_label.setText(message)
        error_label.setVisible(True)
        field.setStyleSheet(f"border: 1.5px solid {COLOR_ERROR};")

    # ---- "student_login" көрінісі -----------------------------------------

    def _build_student_login_view(self) -> QWidget:
        view, self._code_edit, self._error_label, self._login_button, self._login_back_button = (
            self._build_login_view(
                title=_LOGIN_TITLE,
                subtitle=_LOGIN_SUBTITLE,
                placeholder=_CODE_PLACEHOLDER,
                password_mode=False,
                on_submit=self._on_login_clicked,
                on_back=self.show_mode_selection,
            )
        )
        self._code_edit.textEdited.connect(self._on_code_edited)
        return view

    def _on_code_edited(self, _text: str) -> None:
        self._clear_login_error()

    def _on_login_clicked(self) -> None:
        code = self._code_edit.text().strip()
        if not code:
            self._show_login_error(_EMPTY_CODE_ERROR)
            return

        student = self._student_repository.get_by_code(code)
        if student is None:
            self._show_login_error(_INVALID_CODE_ERROR)
            return

        self._active_student_repository.set(
            ActiveStudentContext(classroom_id=student.classroom_id, student_id=student.id)
        )
        self._clear_login_error()
        self.student_login_succeeded.emit()

    def _show_login_error(self, message: str) -> None:
        self._show_field_error(self._error_label, self._code_edit, message)

    def _clear_login_error(self) -> None:
        self._clear_field_error(self._error_label, self._code_edit)

    # ---- "teacher_login" көрінісі -------------------------------------------

    def _build_teacher_login_view(self) -> QWidget:
        (
            view,
            self._pin_edit,
            self._pin_error_label,
            self._teacher_login_button,
            self._teacher_login_back_button,
        ) = self._build_login_view(
            title=_TEACHER_LOGIN_TITLE,
            subtitle=_TEACHER_LOGIN_SUBTITLE,
            placeholder=_PIN_PLACEHOLDER,
            password_mode=True,
            on_submit=self._on_teacher_login_clicked,
            on_back=self.show_mode_selection,
        )
        self._pin_edit.textEdited.connect(self._on_pin_edited)
        return view

    def _on_pin_edited(self, _text: str) -> None:
        self._clear_teacher_login_error()

    def _on_teacher_login_clicked(self) -> None:
        # § Multi-Teacher Accounts: "Teacher enters personal PIN ->
        # Application searches teacher accounts -> PIN identifies
        # teacher" — ``resolve_teacher_by_pin()`` БЕЛСЕНДІ мұғалімдер
        # арасында хэш бойынша іздейді (§ "disabled teacher PIN must no
        # longer allow login"). Қате болса, себебі ЕШҚАШАН ашылмайды —
        # тек жалпы "PIN коды қате" (§ "invalid login should simply
        # show... do not say Teacher X exists but PIN is incorrect").
        pin = self._pin_edit.text().strip()
        if not pin:
            self._show_teacher_login_error(_EMPTY_PIN_ERROR)
            return
        teacher = resolve_teacher_by_pin(pin, self._teacher_repository)
        if teacher is None:
            self._show_teacher_login_error(_INVALID_PIN_ERROR)
            return
        self._active_teacher_repository.set(ActiveTeacherContext(teacher_id=teacher.id))
        self._clear_teacher_login_error()
        self.role_selected.emit(UserRole.TEACHER)

    def _show_teacher_login_error(self, message: str) -> None:
        self._show_field_error(self._pin_error_label, self._pin_edit, message)

    def _clear_teacher_login_error(self) -> None:
        self._clear_field_error(self._pin_error_label, self._pin_edit)
