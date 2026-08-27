"""ClassActivityCarousel — Teacher Dashboard "Бүгінгі белсенділік" панелінің
бір-бірден сынып көрсететін, авто-айналатын ықшам каруселі (Phase 13).

Дербес, репозиторийден МҮЛДЕ тәуелсіз презентация виджеті — тек
``ActivityCardData`` (таза, Qt-сыз, dataclass) тізімін қабылдайды
(§ "Dashboard should remain a presentation/aggregation page" — нақты
дерек жинау ``teacher_dashboard_page.py``-де, бұл виджет тек көрсетеді).

Ауысу анимациясы (§ "CAROUSEL TRANSITION"): ағымдағы карточка сәл солға
жылжып бұлыңғырланады, келесісі оң жақтан кіреді — екеуі де ФИКСТЕЛГЕН
өлшемді ``_viewport``-тың ІШІНДЕ (Qt баланы автоматты түрде ата-ана
шекарасымен қияды, сондықтан сыртқы панель өлшемі анимация кезінде
ЕШҚАШАН өзгермейді — § "Its width and height must stay constant"). Бұл —
Phase 12-нің "do not animate layout position" жалпы ережесінен ЖАЛҒЫЗ,
НАҚТЫ бекітілген ерекшелік (§ "Allowed new animation in this phase: ONLY
the Activity carousel").

``motion.MOTION_ENABLED == False`` болса, слайд ЕШҚАШАН ойналмайды —
мазмұн бірден ауысады, бірақ авто-айналу/навигация толық жұмыс істеуін
жалғастырады (§ "class switching still works... no slide/fade
animation" — Phase 12 MOTION_ENABLED-пен БІРДЕЙ жалғыз орталық сөндіргіш,
§ "Do NOT create a second independent motion setting").
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QRect, Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ui.themes.theme_manager import (
    COLOR_BORDER_SUBTLE,
    COLOR_CLASSROOM_AMBER,
    COLOR_CLASSROOM_BLUE,
    COLOR_CLASSROOM_GREEN,
    COLOR_CLASSROOM_MAGENTA,
    COLOR_CLASSROOM_TEAL,
    COLOR_CLASSROOM_VIOLET,
)
from ui.widgets import motion

CLASS_CAROUSEL_INTERVAL = 4000  # § "Preferred automatic interval: 4000 ms"
CLASS_CAROUSEL_TRANSITION = 280  # § "Recommended: CLASS_CAROUSEL_TRANSITION = 280"

# Phase 13 follow-up ("Stable Classroom Accent Colors"): тіркелу ретімен
# ЕМЕС (§ "Do NOT assign colors based only on current list index"),
# classroom_id-дің ТҰРАҚТЫ hash-ынан детерминистік таңдалады.
CLASSROOM_ACCENT_PALETTE: tuple[str, ...] = (
    COLOR_CLASSROOM_BLUE,
    COLOR_CLASSROOM_VIOLET,
    COLOR_CLASSROOM_TEAL,
    COLOR_CLASSROOM_GREEN,
    COLOR_CLASSROOM_AMBER,
    COLOR_CLASSROOM_MAGENTA,
)


def classroom_accent_color(classroom_id: str, classroom_name: str = "") -> str:
    """``classroom_id``-ден (бос болса ``classroom_name``-нан, § "fallback
    to stable classroom name hash") ДЕТЕРМИНИСТІК, тізім ретіне/индексіне
    ТӘУЕЛСІЗ accent түсін қайтарады. ``sha256`` ӘДЕЙІ қолданылады — Python-ның
    енгізілген ``hash()`` жол үшін процесс-аралық РАНДОМИЗАЦИЯЛАНҒАН
    (``PYTHONHASHSEED``), сондықтан қолданбаны қайта іске қосқанда БІРДЕЙ
    сынып БАСҚА түс алар еді (§ "Restarting the application gives the
    same classroom-color mapping").
    """
    key = classroom_id or classroom_name
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    index = digest[0] % len(CLASSROOM_ACCENT_PALETTE)
    return CLASSROOM_ACCENT_PALETTE[index]


def _accent_tint(accent_hex: str, alpha: int = 26) -> str:
    """§ "Optionally a very subtle tinted badge background" — accent
    түсінің төмен-alpha rgba() нұсқасы (badge фоны үшін)."""
    color = QColor(accent_hex)
    return f"rgba({color.red()}, {color.green()}, {color.blue()}, {alpha})"

_EMPTY_TITLE = "Бүгін белсенді зертханалық жұмыс жоқ"
_EMPTY_HINT = "Зертханалық жұмысты таңдап, жаңа сессияны бастаңыз."
_EMPTY_ACTION_TEXT = "Зертханалық жұмысты бастау"

_VIEWPORT_HEIGHT = 168
_RESUME_AFTER_HOVER_DELAY_MS = CLASS_CAROUSEL_INTERVAL  # § "sensible delay" — бір толық интервал


def _make_background_transparent(widget: QWidget) -> None:
    """``QLabel``/жай ``QWidget`` контейнерлер (``role`` property бар/жоқ
    екеуі де) глобал bare ``QWidget {{ background-color: COLOR_BACKGROUND }}``
    ережесін ӨЗ толық ЕНІМЕН (QVBoxLayout-та widget әдепкі бойынша толық
    енге созылады) мұралап, ақ ``DashboardPanel`` үстінде сұр
    тіктөртбұрыш ретінде көрінеді. Эмпирикалық түрде тексерілді:
    ``WA_StyledBackground=False`` бұл жағдайда ЕШБІР әсер етпейді — тек
    instance-деңгейлік ``setStyleSheet("background-color: transparent;")``
    жұмыс істейді (§ Phase 12 ``motion.py``-дегі БІРДЕЙ техника: instance
    stylesheet ТЕК аталған property-ні қосады, ``role``-негізді
    color/font ережелерін ЕШҚАШАН алмастырмайды/бұзбайды).
    """
    widget.setStyleSheet("background-color: transparent;")


@dataclass(frozen=True)
class ActivityCardData:
    """Бір слайдтың ТАЗА презентация мәні — ешбір domain/repository типі
    емес (§ виджет модуль docstring-і). ``accent_color`` — Phase 13
    follow-up: осы сыныптың ``classroom_accent_color()``-мен есептелген,
    тұрақты hex түсі (шақырушы, ``teacher_dashboard_page.py``, есептейді
    — виджет ӨЗІ ешбір classroom_id білмейді)."""

    classroom_name: str
    experiment_label: str
    student_count: int
    completed_count: int
    in_progress_count: int
    not_started_count: int
    percentage: int
    accent_color: str = COLOR_CLASSROOM_BLUE


class _ActivitySlide(QFrame):
    """Бір карточканың ІШКІ мазмұны (сынып атауы + тәжірибе + сан
    статистикасы + прогресс жолағы). Phase 13 follow-up: ``data.
    accent_color`` көбіне-НАЗАРЛЫ түрде тек 4 орында қолданылады (§
    "Do NOT fill the entire card with strong colors"): сол жақ 3px
    жиек, сынып-атау badge (тонирленген фон + accent мәтін), прогресс
    жолағының chunk түсі, белсенді индикатор нүктесі (соңғысы —
    ``ClassActivityCarousel._update_indicator_states()``-те)."""

    def __init__(self, data: ActivityCardData, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ActivitySlide")
        # § "1. A subtle 2-3 px accent marker on the left side" — тек
        # border-left ғана орнатылады (background/басқа жиектер
        # QFrame#ActivitySlide-тың ӨЗ "transparent"/"none" ережесінен
        # өзгеріссіз мұраланады). МАҢЫЗДЫ: селектор ``QFrame#ActivitySlide``
        # ретінде НАҚТЫ ID-мен жазылуы ШАРТ — bare (селекторсыз) property
        # ``setStyleSheet()`` арқылы орнатылса, Qt оны БҮКІЛ ІШКІ ағашқа
        # (мыс. ``_build_stat()``-тың әр QWidget контейнеріне) каскадтап,
        # әр статистика санының өз сол жақ жиегінде ҚОСЫМША жолақ пайда
        # болатыны эмпирикалық түрде табылды (регрессия, скриншот
        # аудитінде байқалды және түзетілді) — ID-негізді селектор ТЕК
        # осы нақты объектіге сәйкес келеді, ұрпақтарға ЕШҚАШАН таралмайды.
        self.setStyleSheet(f"QFrame#ActivitySlide {{ border-left: 3px solid {data.accent_color}; }}")

        classroom_label = QLabel(data.classroom_name, self)
        classroom_label.setProperty("role", "cardTitle")
        # § "2. classroom-name badge/text treatment" + "5. subtle tinted
        # badge background" — font-size/weight ӘЛІ ДЕ ``role="cardTitle"``
        # ережесінен мұраланады, тек color/background/padding осында.
        classroom_label.setStyleSheet(
            f"color: {data.accent_color}; background-color: {_accent_tint(data.accent_color)};"
            f"border-radius: {4}px; padding: 2px 8px;"
        )
        classroom_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        experiment_label = QLabel(data.experiment_label, self)
        experiment_label.setProperty("role", "secondary")
        experiment_label.setWordWrap(True)
        _make_background_transparent(experiment_label)

        stats_row = QHBoxLayout()
        stats_row.addWidget(self._build_stat("Оқушылар", data.student_count))
        stats_row.addWidget(self._build_stat("Аяқтады", data.completed_count))
        stats_row.addWidget(self._build_stat("Орындауда", data.in_progress_count))
        stats_row.addWidget(self._build_stat("Бастамады", data.not_started_count))

        layout = QVBoxLayout(self)
        layout.addWidget(classroom_label, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(experiment_label)
        layout.addSpacing(4)
        layout.addLayout(stats_row)
        layout.addSpacing(4)

        # § "EMPTY / NO-ACTIVITY CLASSROOM": "Do not show a fake progress
        # value. If no progress exists, the progress bar may be hidden."
        # (қорғаныс — қазіргі compute_classroom_activity() әрдайым >=1
        # оқушымен snapshot қайтарады, бірақ болашаққа/edge-case-ке қарсы).
        if data.student_count > 0:
            progress_bar = QProgressBar(self)
            progress_bar.setObjectName("DashboardActivityBar")
            progress_bar.setRange(0, 100)
            progress_bar.setValue(data.percentage)
            progress_bar.setTextVisible(False)
            progress_bar.setFixedHeight(8)
            # § "3. The activity progress bar" — chunk түсі accent-пен,
            # трек түсі (COLOR_BORDER_SUBTLE) app-деңгейлік ережемен БІРДЕЙ
            # қайта мәлімделеді (cascade екіұштылығын болдырмау үшін).
            progress_bar.setStyleSheet(
                f"QProgressBar#DashboardActivityBar {{ border: none; border-radius: 4px;"
                f" background-color: {COLOR_BORDER_SUBTLE}; }}"
                f"QProgressBar#DashboardActivityBar::chunk {{ background-color: {data.accent_color};"
                f" border-radius: 4px; }}"
            )
            layout.addWidget(progress_bar)

            percentage_label = QLabel(
                f"{data.completed_count} / {data.student_count}   {data.percentage}%", self
            )
            percentage_label.setProperty("role", "secondary")
            _make_background_transparent(percentage_label)
            layout.addWidget(percentage_label)

        layout.addStretch(1)

    def _build_stat(self, caption: str, value: int) -> QWidget:
        container = QWidget(self)
        _make_background_transparent(container)
        value_label = QLabel(str(value), container)
        value_label.setProperty("role", "cardValue")
        _make_background_transparent(value_label)
        caption_label = QLabel(caption, container)
        caption_label.setProperty("role", "cardLabel")
        _make_background_transparent(caption_label)
        col = QVBoxLayout(container)
        col.setContentsMargins(0, 0, 0, 0)
        col.addWidget(value_label)
        col.addWidget(caption_label)
        return container


class _EmptyActivitySlide(QFrame):
    """§3 "ACTIVITY EMPTY STATE"."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ActivitySlide")

        title_label = QLabel(_EMPTY_TITLE, self)
        title_label.setProperty("role", "cardTitle")
        _make_background_transparent(title_label)
        hint_label = QLabel(_EMPTY_HINT, self)
        hint_label.setProperty("role", "secondary")
        hint_label.setWordWrap(True)
        _make_background_transparent(hint_label)

        self.action_button = QPushButton(_EMPTY_ACTION_TEXT, self)
        self.action_button.setObjectName("DashboardQuickActionButton")
        self.action_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.addStretch(1)
        layout.addWidget(title_label)
        layout.addWidget(hint_label)
        layout.addWidget(self.action_button, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addStretch(1)


class ClassActivityCarousel(QWidget):
    """§2 "CLASS ACTIVITY CAROUSEL" — толық виджет: viewport + prev/next +
    indicator dots. ``start_lab_requested`` (Qt callback, төменде
    ``set_start_lab_callback()`` арқылы) — бос күйдегі әрекет батырмасы
    басылғанда шақырылады (Router-ге ЕШБІР тікелей сілтеме жоқ, § UI
    presentation-only қағидасы).
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ClassActivityCarousel")
        _make_background_transparent(self)
        self._items: tuple[ActivityCardData, ...] = ()
        self._current_index = 0
        self._current_slide: QWidget | None = None
        self._incoming_slide: QWidget | None = None
        self._animations: list[QPropertyAnimation] = []
        self._opacity_effects: list[QGraphicsOpacityEffect] = []
        self._start_lab_callback = None
        self._transitioning = False

        self._viewport = QWidget(self)
        self._viewport.setFixedHeight(_VIEWPORT_HEIGHT)
        _make_background_transparent(self._viewport)

        self._prev_button = QPushButton("‹", self)
        self._prev_button.setObjectName("DashboardCarouselNavButton")
        self._prev_button.setProperty("variant", "icon")
        self._prev_button.setFixedWidth(28)
        self._prev_button.clicked.connect(self._on_prev_clicked)

        self._next_button = QPushButton("›", self)
        self._next_button.setObjectName("DashboardCarouselNavButton")
        self._next_button.setProperty("variant", "icon")
        self._next_button.setFixedWidth(28)
        self._next_button.clicked.connect(self._on_next_clicked)

        self._indicator_row = QHBoxLayout()
        self._indicator_row.setSpacing(6)
        self._indicator_labels: list[QLabel] = []

        nav_row = QHBoxLayout()
        nav_row.addWidget(self._prev_button)
        nav_row.addStretch(1)
        nav_row.addLayout(self._indicator_row)
        nav_row.addStretch(1)
        nav_row.addWidget(self._next_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._viewport)
        layout.addLayout(nav_row)

        self._timer = QTimer(self)
        self._timer.setInterval(CLASS_CAROUSEL_INTERVAL)
        self._timer.timeout.connect(self._on_timer_tick)

        self._render_current(animate=False)
        self._update_controls_visibility()

    # ---- Public API -----------------------------------------------------

    def set_start_lab_callback(self, callback) -> None:
        """Бос күйдегі "Зертханалық жұмысты бастау" батырмасы басылғанда
        шақырылатын parameter-сіз callable орнатады."""
        self._start_lab_callback = callback

    def set_items(self, items: tuple[ActivityCardData, ...]) -> None:
        """Каруселдің толық тізімін алмастырады, индексті 0-ге қайтарады.
        Ешбір анимация ойналмайды (§ бетке кіру/жаңарту — көрінбейтін
        презентация жаңартуы, тек нақты қолданушы навигациясы/авто-
        айналуы анимацияланады).
        """
        self._items = items
        self._current_index = 0
        self._render_current(animate=False)
        self._update_controls_visibility()
        self._sync_timer()

    def start(self) -> None:
        """Дашборд көрінгенде шақырылады (§17 "Timer Lifecycle")."""
        self._sync_timer()

    def stop(self) -> None:
        """Дашборд жасырылғанда/беттен шыққанда шақырылады."""
        self._timer.stop()

    # ---- Qt event overrides ----------------------------------------------

    def showEvent(self, event) -> None:  # noqa: N802 (Qt override name)
        super().showEvent(event)
        self._sync_timer()

    def hideEvent(self, event) -> None:  # noqa: N802 (Qt override name)
        super().hideEvent(event)
        self._timer.stop()

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt override name)
        super().resizeEvent(event)
        # ``_viewport``-тың нақты ені тек layout біріншісінде белгілі
        # болады (§ __init__-де 0 болуы мүмкін) — ағымдағы слайдты жаңа
        # енге сай ұстау үшін, транзиция ЖҮРІП ЖАТПАСА, геометрияны
        # қайта орнатамыз (§ "outer geometry must not move" — бұл ТЕК
        # виджеттің ӨЗ ішкі мазмұнын сәйкестендіру, сыртқы панель өлшемін
        # ЕШҚАШАН өзгертпейді).
        if self._current_slide is not None and not self._transitioning:
            self._current_slide.setGeometry(0, 0, self._viewport.width(), _VIEWPORT_HEIGHT)

    def enterEvent(self, event) -> None:  # noqa: N802 (Qt override name)
        super().enterEvent(event)
        self._timer.stop()

    def leaveEvent(self, event) -> None:  # noqa: N802 (Qt override name)
        super().leaveEvent(event)
        self._sync_timer()

    # ---- Ішкі логика -------------------------------------------------

    def _sync_timer(self) -> None:
        should_run = len(self._items) > 1 and self.isVisible()
        if should_run:
            self._timer.start(CLASS_CAROUSEL_INTERVAL)
        else:
            self._timer.stop()

    def _update_controls_visibility(self) -> None:
        multiple = len(self._items) > 1
        self._prev_button.setVisible(multiple)
        self._next_button.setVisible(multiple)
        self._rebuild_indicators()

    def _rebuild_indicators(self) -> None:
        while self._indicator_row.count():
            item = self._indicator_row.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._indicator_labels = []

        if len(self._items) <= 1:
            return
        for index in range(len(self._items)):
            dot = QLabel("●", self)
            dot.setObjectName("DashboardCarouselDot")
            is_active = index == self._current_index
            dot.setProperty("active", is_active)
            _make_background_transparent(dot)
            self._indicator_row.addWidget(dot)
            self._indicator_labels.append(dot)
        self._apply_indicator_colors()

    def _update_indicator_states(self) -> None:
        for index, dot in enumerate(self._indicator_labels):
            active = index == self._current_index
            if dot.property("active") != active:
                dot.setProperty("active", active)
                dot.style().unpolish(dot)
                dot.style().polish(dot)
        self._apply_indicator_colors()

    def _apply_indicator_colors(self) -> None:
        """§ "4. The active carousel indicator dot" — ТЕК белсенді нүкте
        осы сыныптың accent түсін алады (instance-деңгейлік ``color``
        property қосымша, ``background-color: transparent`` бұрыннан
        сақталады); белсенді ЕМЕС нүктелер app-деңгейлік бейтарап
        ``QLabel#DashboardCarouselDot`` ережесіне қайтарылады (instance
        color override алынып тасталады)."""
        for index, dot in enumerate(self._indicator_labels):
            if index == self._current_index and index < len(self._items):
                accent = self._items[index].accent_color
                dot.setStyleSheet(f"background-color: transparent; color: {accent};")
            else:
                dot.setStyleSheet("background-color: transparent;")

    def _on_timer_tick(self) -> None:
        self._advance(1, reset_timer=False)

    def _on_prev_clicked(self) -> None:
        self._advance(-1, reset_timer=True)

    def _on_next_clicked(self) -> None:
        self._advance(1, reset_timer=True)

    def _advance(self, direction: int, reset_timer: bool) -> None:
        if not self._items or self._transitioning:
            return
        if len(self._items) <= 1:
            return
        self._current_index = (self._current_index + direction) % len(self._items)
        self._render_current(animate=True, direction=direction)
        self._update_indicator_states()
        if reset_timer:
            self._sync_timer()

    def _current_data(self) -> ActivityCardData | None:
        if not self._items:
            return None
        return self._items[self._current_index]

    def _build_slide_widget(self) -> QWidget:
        data = self._current_data()
        if data is None:
            slide = _EmptyActivitySlide(self._viewport)
            slide.action_button.clicked.connect(self._on_start_lab_clicked)
            return slide
        return _ActivitySlide(data, self._viewport)

    def _on_start_lab_clicked(self) -> None:
        if self._start_lab_callback is not None:
            self._start_lab_callback()

    def _render_empty_state(self) -> None:
        self._render_current(animate=False)

    def _render_current(self, animate: bool, direction: int = 1) -> None:
        new_slide = self._build_slide_widget()
        viewport_rect = QRect(0, 0, max(1, self._viewport.width()), _VIEWPORT_HEIGHT)
        new_slide.setGeometry(viewport_rect)

        old_slide = self._current_slide
        self._current_slide = new_slide
        new_slide.show()

        if old_slide is None or not animate or not motion.MOTION_ENABLED:
            new_slide.move(0, 0)
            if old_slide is not None:
                old_slide.setParent(None)
                old_slide.deleteLater()
            return

        self._animate_transition(old_slide, new_slide, direction, viewport_rect)

    def _animate_transition(
        self, old_slide: QWidget, new_slide: QWidget, direction: int, viewport_rect: QRect
    ) -> None:
        """§ "CAROUSEL TRANSITION": ағымдағы карточка сәл солға (шамамен
        ені 15%) жылжып бұлыңғырланады, келесісі толық енінен (100%)
        оң жақтан кіріп, дәл 0-ге тоқтайды. ``direction`` +1 (келесі) —
        ескісі СОЛҒА, жаңасы ОҢНАН кіреді; -1 (алдыңғы) — керісінше.
        """
        self._transitioning = True
        width = viewport_rect.width()
        new_slide.move(width * direction, 0)

        opacity_effect = QGraphicsOpacityEffect(old_slide)
        old_slide.setGraphicsEffect(opacity_effect)
        self._opacity_effects.append(opacity_effect)

        fade_anim = QPropertyAnimation(opacity_effect, b"opacity", self)
        fade_anim.setDuration(CLASS_CAROUSEL_TRANSITION)
        fade_anim.setStartValue(1.0)
        fade_anim.setEndValue(0.0)
        fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        exit_shift = int(width * 0.15) * direction
        old_move = QPropertyAnimation(old_slide, b"pos", self)
        old_move.setDuration(CLASS_CAROUSEL_TRANSITION)
        old_move.setStartValue(QPoint(0, 0))
        old_move.setEndValue(QPoint(-exit_shift, 0))
        old_move.setEasingCurve(QEasingCurve.Type.OutCubic)

        new_move = QPropertyAnimation(new_slide, b"pos", self)
        new_move.setDuration(CLASS_CAROUSEL_TRANSITION)
        new_move.setStartValue(QPoint(width * direction, 0))
        new_move.setEndValue(QPoint(0, 0))
        new_move.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._animations = [fade_anim, old_move, new_move]

        def _on_finished() -> None:
            old_slide.setGraphicsEffect(None)
            old_slide.setParent(None)
            old_slide.deleteLater()
            new_slide.move(0, 0)
            self._transitioning = False

        new_move.finished.connect(_on_finished)

        for anim in self._animations:
            anim.start()
