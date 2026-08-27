"""WorkspaceBackdrop + background_category — Phase 41 юнит-тесттері.

Route/санат бейнелеу (таза функциялар, Qt-сыз) және виджеттің
өзі (мышеге мөлдірлік, санат ауысқанда қайта боялу, fallback) бөлек
тексеріледі.
"""

import sys

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from ui.navigation.background_category import (
    ALL_CATEGORIES,
    CATEGORY_DEFAULT,
    CATEGORY_ELECTRICITY,
    CATEGORY_FEEDBACK,
    CATEGORY_HELP,
    CATEGORY_HOME,
    CATEGORY_LABORATORY,
    CATEGORY_RESULTS,
    resolve_experiment_category,
    resolve_route_category,
)
from ui.themes.theme_manager import ThemeManager
from ui.widgets import motion
from ui.widgets.workspace_background import WorkspaceBackdrop


@pytest.fixture(scope="module", autouse=True)
def qt_application() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


# =====================================================================
# resolve_route_category / resolve_experiment_category (таза функциялар)
# =====================================================================


@pytest.mark.parametrize(
    ("route", "expected"),
    [
        ("home", CATEGORY_HOME),
        ("dashboard", CATEGORY_HOME),
        ("experiment_list", CATEGORY_LABORATORY),
        ("data_journal", CATEGORY_RESULTS),
        ("my_results", CATEGORY_RESULTS),
        ("results", CATEGORY_RESULTS),
        ("feedback_student", CATEGORY_FEEDBACK),
        ("feedback_teacher", CATEGORY_FEEDBACK),
        ("devices", "devices"),
        ("analytics", "analytics"),
        ("about", CATEGORY_HELP),
    ],
)
def test_resolve_route_category_known_routes(route: str, expected: str) -> None:
    assert resolve_route_category(route) == expected


@pytest.mark.parametrize(
    "route",
    ["settings", "role_selection", "student_selection", "classes", "question_bank", "unknown_route"],
)
def test_resolve_route_category_unknown_routes_fallback_to_default(route: str) -> None:
    assert resolve_route_category(route) == CATEGORY_DEFAULT


def test_resolve_experiment_category_known_module_keys() -> None:
    assert resolve_experiment_category("electricity") == CATEGORY_ELECTRICITY
    assert resolve_experiment_category("heat") == "heat"
    assert resolve_experiment_category("electromagnetism") == "electromagnetism"
    assert resolve_experiment_category("light") == "light"


def test_resolve_experiment_category_none_falls_back_to_laboratory() -> None:
    assert resolve_experiment_category(None) == CATEGORY_LABORATORY


def test_resolve_experiment_category_unknown_key_falls_back_to_laboratory() -> None:
    assert resolve_experiment_category("some-future-module") == CATEGORY_LABORATORY


# =====================================================================
# WorkspaceBackdrop widget
# =====================================================================


def test_default_category_is_valid() -> None:
    backdrop = WorkspaceBackdrop()

    assert backdrop.current_category() in ALL_CATEGORIES


def test_set_category_updates_current_category() -> None:
    backdrop = WorkspaceBackdrop()

    backdrop.set_category(CATEGORY_ELECTRICITY)

    assert backdrop.current_category() == CATEGORY_ELECTRICITY


def test_set_category_unknown_key_falls_back_to_default_without_crash() -> None:
    backdrop = WorkspaceBackdrop()

    backdrop.set_category("totally-unmapped-category")

    assert backdrop.current_category() == CATEGORY_DEFAULT


def test_set_category_same_value_is_a_noop_and_does_not_repaint() -> None:
    """Phase 41 қосымша талап: "reuse the same background across pages
    within the same major section" / "resizing must not trigger
    unnecessary background repaints" — санат ӨЗГЕРМЕГЕНДЕ update() ЕШҚАШАН
    қайта шақырылмайды."""
    backdrop = WorkspaceBackdrop()
    backdrop.set_category(CATEGORY_ELECTRICITY)
    repaint_calls = 0

    original_update = backdrop.update

    def _counting_update() -> None:
        nonlocal repaint_calls
        repaint_calls += 1
        original_update()

    backdrop.update = _counting_update  # type: ignore[method-assign]
    backdrop.set_category(CATEGORY_ELECTRICITY)

    assert repaint_calls == 0


def test_backdrop_itself_has_no_mouse_handlers_but_is_not_hit_test_transparent() -> None:
    """Инцидент регрессиясы: ``WA_TransparentForMouseEvents`` БҰРЫН осында
    орнатылған еді "тінтуір оқиғасын ұстамайды" деген ниетпен, БІРАҚ бұл
    ``QSplitter`` сияқты аталық деңгейден іздегенде WorkspaceBackdrop-тың
    ТҮГЕЛ ІШКІ ағашын (self._stack және ОНЫҢ ІШІНДЕГІ БАРЛЫҚ бет/батырма)
    hit-testing-тен толығымен алып тастайтыны расталды — нақты screen-
    coordinate негізді click ЕШҚАШАН ешбір ішкі виджетке жетпеді (тек
    виджетке ТІКЕЛЕЙ бағытталған синтетикалық click бұл тексеруден
    аттап өтеді, сондықтан бұрын байқалмады). WorkspaceBackdrop ӨЗІ
    де ешбір mousePressEvent/т.б. анықтамайды (§ "decorative only,
    non-interactive"), бірақ бұған қол жеткізу үшін ЕШҚАШАН
    ``WA_TransparentForMouseEvents`` қажет ЕМЕС — parent widget өз
    аймағында ешбір handler анықтамаса, әдепкі бойынша "әрекетсіз".
    """
    backdrop = WorkspaceBackdrop()

    assert backdrop.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents) is False


def test_child_widget_remains_hit_testable_through_backdrop_inside_a_splitter() -> None:
    """Дәл нақты MainWindow композициясын қайталайтын regression тест:
    QSplitter -> WorkspaceBackdrop -> QStackedWidget -> нақты бет ->
    батырма тізбегінде, ``splitter.childAt()`` (нақты тінтуір
    жеткізуімен БІРДЕЙ hit-testing тетігі) НАҚТЫ сол батырманы табуы
    керек, ``None`` емес.
    """
    from PySide6.QtWidgets import QPushButton, QSplitter, QStackedWidget, QVBoxLayout, QWidget

    backdrop = WorkspaceBackdrop()
    stack = QStackedWidget()
    page = QWidget()
    button = QPushButton("test", page)
    QVBoxLayout(page).addWidget(button)
    stack.addWidget(page)
    stack.setCurrentWidget(page)

    backdrop_layout = QVBoxLayout(backdrop)
    backdrop_layout.setContentsMargins(0, 0, 0, 0)
    backdrop_layout.addWidget(stack)

    splitter = QSplitter()
    sidebar_stub = QWidget()
    splitter.addWidget(sidebar_stub)
    splitter.addWidget(backdrop)
    splitter.resize(600, 400)
    splitter.show()

    button_center_global = button.mapToGlobal(button.rect().center())
    splitter_local = splitter.mapFromGlobal(button_center_global)

    assert splitter.childAt(splitter_local) is button


def test_every_category_paints_without_crash() -> None:
    backdrop = WorkspaceBackdrop()
    backdrop.resize(800, 600)

    for category in ALL_CATEGORIES:
        backdrop.set_category(category)
        backdrop.repaint()  # синхронды түрде paintEvent-ті шақырады


# =====================================================================
# Phase 41 background regression fix (4-ші есеп): "always shows the same
# faint trapezoid" — категориялардың НАҚТЫ пиксель деңгейінде де
# ажыратылатынын дәлелдейтін тесттер (тек санат STRING-ін емес).
# =====================================================================


def test_all_categories_produce_pairwise_distinct_rendered_images() -> None:
    """Әр санат ӨЗ, бірегей ``QImage`` беруі керек — тек shape/color
    константалары ЕМЕС, НАҚТЫ boялған пиксельдер салыстырылады.
    """
    images = {}
    for category in ALL_CATEGORIES:
        backdrop = WorkspaceBackdrop()
        backdrop.resize(800, 600)
        backdrop.set_category(category)
        backdrop.repaint()
        images[category] = backdrop.grab().toImage()

    categories = list(ALL_CATEGORIES)
    for i, cat_a in enumerate(categories):
        for cat_b in categories[i + 1 :]:
            assert images[cat_a] != images[cat_b], (
                f"category '{cat_a}' and '{cat_b}' rendered IDENTICAL images"
            )


def test_module_categories_have_pairwise_distinct_stroke_colors() -> None:
    """heat/electricity/electromagnetism/light — ТЕК ExperimentWorkspacePage-
    те (§ resolve_experiment_category) көрінеді, тек СОЛ беттің толық
    ауданды алатын графигі/кестесі себебінен ЖІҢІШКЕ бұрыш ғана нақты
    көрінеді. Пішін геометриясы кейде сол жіңішке аймаққа жетпеуі мүмкін
    болғандықтан (§ zigzag/magnet), ТҮС өзі де міндетті түрде ажыратылуы
    керек — тек SHAPE-ге сүйенбеу.
    """
    from ui.widgets.workspace_background import _CATEGORY_STROKE_COLOR

    module_keys = ("heat", "electricity", "electromagnetism", "light")
    colors = [_CATEGORY_STROKE_COLOR[key] for key in module_keys]

    assert len(set(colors)) == len(colors)


def test_all_named_categories_have_an_explicit_stroke_color() -> None:
    """"default" категориясынан басқасының бәрі ӨЗ, нақты бекітілген
    түсі болуы керек (§ бұрын 8 санат бірдей ``_NEUTRAL_COLOR``-мен
    салынатын — 4% opacity-де әр түрлі пішіндер де бір-біріне ұқсас
    "күңгірт дақ" болып көрінетін).
    """
    from ui.widgets.workspace_background import _CATEGORY_STROKE_COLOR

    for category in ALL_CATEGORIES:
        if category == CATEGORY_DEFAULT:
            continue
        assert category in _CATEGORY_STROKE_COLOR, (
            f"category '{category}' has no explicit stroke color, falls back to neutral gray"
        )


def test_corner_anchored_module_categories_are_visible_in_a_thin_covered_margin() -> None:
    """Root cause регрессиясы (4-ші есеп): ``ExperimentWorkspacePage``-тің
    графигі/кестесі WorkspaceBackdrop-тың іс жүзінде БАРЛЫҚ ауданын
    жабады — тек шеттегі layout margin-нің ЖІҢІШКЕ жолағы (~10-20px)
    ғана нақты бос қалады. Осы тест НАҚТЫ сол сценарийді (backdrop +
    оның ҮСТІНДЕ, тек жіңішке жиек қалдыратын opaque covering widget)
    қайталайды және heat/electricity/electromagnetism/light-тің әрқайсысы
    сол жіңішке жиекте КЕМ ДЕГЕНДЕ бір НАҚТЫ БОЯЛҒАН (фон емес) пиксель
    қалдыратынын дәлелдейді — _MARGIN/_CORNER_ANCHOR_SCALE/accent dot
    константалары қайта үлкейтілсе/өшірілсе, бұл тест СӘТСІЗ болады.
    """
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QWidget

    from ui.themes.theme_manager import COLOR_BACKGROUND

    background = QColor(COLOR_BACKGROUND)
    covered_margin = 24  # ExperimentWorkspacePage-де эмпирикалық түрде расталған шамамен

    for category in ("heat", "electricity", "electromagnetism", "light"):
        backdrop = WorkspaceBackdrop()
        backdrop.resize(1200, 840)
        backdrop.set_category(category)

        covering = QWidget(backdrop)
        covering.setAutoFillBackground(True)
        palette = covering.palette()
        palette.setColor(covering.backgroundRole(), background)
        covering.setPalette(palette)
        covering.setGeometry(
            0, 0, backdrop.width() - covered_margin, backdrop.height() - covered_margin
        )
        backdrop.show()
        covering.show()
        backdrop.repaint()
        image = backdrop.grab().toImage()

        # grab() кейде device-pixel-ratio-мен масштабталған QImage қайтарады
        # (мыс. 1500x1050, ал widget өзі логикалық 1200x840) — сол
        # масштабты ескермей backdrop.width()/height()-ті пиксель индексі
        # ретінде қолдану НАҚТЫ бұрыштан алшақ, бос аймақты сканерлейді.
        scale_x = image.width() / backdrop.width()
        scale_y = image.height() / backdrop.height()
        scanned_w = max(1, int(covered_margin * scale_x))
        scanned_h = max(1, int(covered_margin * scale_y))

        found_ink = False
        for dx in range(scanned_w):
            for dy in range(scanned_h):
                x = image.width() - 1 - dx
                y = image.height() - 1 - dy
                if image.pixelColor(x, y) != background:
                    found_ink = True
                    break
            if found_ink:
                break

        assert found_ink, (
            f"category '{category}' has NO visible ink within the {covered_margin}px "
            "corner margin left uncovered by a full-bleed page (regression: watermark "
            "invisible on ExperimentWorkspacePage)"
        )


# =====================================================================
# Phase 41: QScrollArea transparency QSS (ThemeManager) — regression
# =====================================================================
#
# HomePage/DevicesPage/DevicePanel беттерінің мазмұны QScrollArea-мен
# оралған — scroll area-дың viewport-ы/setWidget() контейнері мөлдір
# болмаса, су таңба сол беттерде МҮЛДЕ көрінбейді (қолмен скриншот
# тексеруінде табылған нақты дефект). Түзетуде ``QScrollArea QWidget``
# (шексіз тереңдік, descendant) орнына ``QScrollArea > QWidget``/
# ``QScrollArea > QWidget > QWidget`` (тек 2 деңгей, тікелей-ұрпақ)
# қолданылды — бірінші нұсқа эмпирикалық түрде ІШКІ ``QPushButton``
# сияқты нақты стильденген виджеттердің ӨЗ ``background-color``
# ережесін specificity бойынша басып тастайтыны расталды (регрессия).


@pytest.fixture
def themed_app() -> QApplication:
    """Нақты ``ThemeManager.build_stylesheet()``-ті ағымдағы
    ``QApplication``-ға қолданып, тест соңында тазартады — бұл файлдағы
    басқа тесттерге стильдің сырғымауын (leak) болдырмау үшін.
    """
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    app.setStyleSheet(ThemeManager().build_stylesheet())
    yield app
    app.setStyleSheet("")


def test_scroll_area_content_becomes_transparent(themed_app: QApplication) -> None:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    content = QWidget()
    QVBoxLayout(content)
    scroll.setWidget(content)
    scroll.resize(200, 200)
    scroll.show()
    themed_app.processEvents()

    pixmap = content.grab()
    color = pixmap.toImage().pixelColor(190, 190)

    assert color.alpha() == 0


@pytest.mark.parametrize(
    "object_name",
    [
        "MeasurementWorkspace",
        "MeasurementWorkspaceDevicePage",
        "MeasurementWorkspaceNoDevicePage",
        "DataJournalListView",
        "DataJournalDetailView",
        "DataJournalResultsContainer",
        "TeacherFeedbackResultsContainer",
        "StudentFeedbackContentView",
        "StudentFeedbackResultsContainer",
        "StudentResultsView",
    ],
)
def test_background_pipeline_container_object_names_are_transparent(
    themed_app: QApplication, object_name: str
) -> None:
    """Phase 41 background regression fix (4-ші есеп): DataJournalPage/
    TeacherFeedbackReviewPage/StudentFeedbackPage/StudentResultsPage-тің
    ІШКІ (жасырын) QStackedWidget-індегі child view-лер мен olardың
    results container-лері — су таңба СОЛ беттерде толығымен жасырылып
    қалмауы үшін мөлдір болуы керек.
    """
    widget = QWidget()
    widget.setObjectName(object_name)
    widget.resize(100, 100)
    widget.show()
    themed_app.processEvents()

    pixmap = widget.grab()
    color = pixmap.toImage().pixelColor(50, 50)

    assert color.alpha() == 0


def test_empty_state_label_object_name_is_transparent(themed_app: QApplication) -> None:
    """Root cause (4-ші есеп): ``_empty_state_title_label``/
    ``_empty_state_hint_label`` кесте жасырылған кезде layout-тың бос
    жерін ТЕҢ жартыға бөліп алады (Qt-тың stretch=0 виджеттер арасында
    артық орынды тең бөлу мінез-құлқы) — НАҚТЫ мәтін өлшемінен әлдеқайда
    үлкен, толығымен opaque тіктөртбұрыш ретінде БҮКІЛ су таңбаны жауып
    тұрады.
    """
    label = QLabel("Сақталған тәжірибелер жоқ")
    label.setObjectName("WorkspaceEmptyStateLabel")
    label.resize(300, 300)
    label.show()
    themed_app.processEvents()

    pixmap = label.grab()
    color = pixmap.toImage().pixelColor(290, 290)

    assert color.alpha() == 0


def test_button_inside_scroll_area_keeps_its_own_background(themed_app: QApplication) -> None:
    """Реттелген (§ QScrollArea transparency) бұл ережелер ІШКІ
    ``QPushButton``-ды ЕШҚАШАН мөлдір етпеуі тиіс — button өз жеке
    ``QPushButton {}`` ережесін сақтауы керек.
    """
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    content = QWidget()
    layout = QVBoxLayout(content)
    button = QPushButton("Тест", content)
    layout.addWidget(button)
    scroll.setWidget(content)
    scroll.resize(200, 200)
    scroll.show()
    themed_app.processEvents()

    pixmap = button.grab()
    color = pixmap.toImage().pixelColor(10, 10)

    assert color.alpha() == 255
    assert color.name() != "#000000"


# =====================================================================
# Phase 15 ("Flask Background Animation ONLY"): "laboratory" санатының
# колба/флакон су таңбасы — "home" атомымен БІРДЕЙ ортақ таймер
# архитектурасын қайта пайдаланады, тек сұйықтық/көпіршіктер
# анимацияланады (§ paint_flask()).
# =====================================================================


@pytest.fixture(autouse=True)
def _restore_motion_enabled():
    original = motion.MOTION_ENABLED
    yield
    motion.MOTION_ENABLED = original


def test_flask_static_matches_old_baked_drawer_pixel_exact() -> None:
    """``MOTION_ENABLED=False`` (немесе ``animated=False``) кезінде
    ``paint_flask`` ЕСКІ статикалық ``_draw_laboratory`` баяу сызбасымен
    ПИКСЕЛЬ ДӘЛ БІРДЕЙ болуы керек (§ "renders as static illustration,
    no timer runs, page otherwise identical")."""
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QColor, QImage, QPainter

    from ui.widgets.workspace_background import _draw_laboratory, paint_flask

    rect = QRectF(20, 20, 280, 280)
    color = QColor("#F9A825")

    def render(drawer) -> QImage:
        image = QImage(320, 320, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(0)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        drawer(painter)
        painter.end()
        return image

    old_image = render(lambda p: _draw_laboratory(p, rect, color))
    static_image = render(
        lambda p: paint_flask(p, rect, 0.0, color=color, opacity=1.0, animated=False)
    )

    assert old_image == static_image


def test_flask_animation_phase_changes_over_elapsed_time() -> None:
    """Толқын/көпіршіктер уақыт өткен сайын НАҚТЫ өзгеруі керек (§
    "animation phase changes over time")."""
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QColor, QImage, QPainter

    from ui.widgets.workspace_background import paint_flask

    rect = QRectF(20, 20, 280, 280)
    color = QColor("#F9A825")

    def render(elapsed_ms: float) -> QImage:
        image = QImage(320, 320, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(0)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        paint_flask(painter, rect, elapsed_ms, color=color, opacity=1.0, animated=True)
        painter.end()
        return image

    frames = [render(t) for t in (0.0, 1500.0, 3000.0, 5000.0)]

    for i, frame_a in enumerate(frames):
        for frame_b in frames[i + 1 :]:
            assert frame_a != frame_b


def test_laboratory_timer_starts_when_visible_and_motion_enabled() -> None:
    motion.MOTION_ENABLED = True
    backdrop = WorkspaceBackdrop()
    backdrop.resize(400, 400)
    backdrop.show()
    backdrop.set_category(CATEGORY_LABORATORY)

    assert backdrop._atom_timer.isActive()


def test_laboratory_timer_stops_when_hidden() -> None:
    motion.MOTION_ENABLED = True
    backdrop = WorkspaceBackdrop()
    backdrop.resize(400, 400)
    backdrop.show()
    backdrop.set_category(CATEGORY_LABORATORY)
    assert backdrop._atom_timer.isActive()

    backdrop.hide()

    assert not backdrop._atom_timer.isActive()


def test_laboratory_timer_resumes_on_show() -> None:
    motion.MOTION_ENABLED = True
    backdrop = WorkspaceBackdrop()
    backdrop.resize(400, 400)
    backdrop.show()
    backdrop.set_category(CATEGORY_LABORATORY)
    backdrop.hide()
    assert not backdrop._atom_timer.isActive()

    backdrop.show()

    assert backdrop._atom_timer.isActive()


def test_motion_disabled_stops_laboratory_timer() -> None:
    """§ "when False, flask renders as static illustration, no timer
    runs" — жалғыз орталық ``MOTION_ENABLED`` сөндіргіші."""
    motion.MOTION_ENABLED = True
    backdrop = WorkspaceBackdrop()
    backdrop.resize(400, 400)
    backdrop.show()
    backdrop.set_category(CATEGORY_LABORATORY)
    assert backdrop._atom_timer.isActive()

    motion.MOTION_ENABLED = False
    backdrop.set_category(CATEGORY_RESULTS)
    backdrop.set_category(CATEGORY_LABORATORY)

    assert not backdrop._atom_timer.isActive()


def test_non_laboratory_non_home_category_never_runs_the_timer() -> None:
    motion.MOTION_ENABLED = True
    backdrop = WorkspaceBackdrop()
    backdrop.resize(400, 400)
    backdrop.show()

    backdrop.set_category(CATEGORY_RESULTS)

    assert not backdrop._atom_timer.isActive()


def test_home_atom_timer_still_works_after_flask_integration() -> None:
    """Регрессия сақтандыру: Phase 12-нің "home" атом анимациясы Phase
    15-тің ортақ таймер кеңеюінен кейін де өзгеріссіз жұмыс істеуі керек."""
    motion.MOTION_ENABLED = True
    backdrop = WorkspaceBackdrop()
    backdrop.resize(400, 400)
    backdrop.show()

    backdrop.set_category(CATEGORY_HOME)

    assert backdrop._atom_timer.isActive()


def test_flask_bounding_target_rect_unchanged_by_category() -> None:
    """§ "flask bounding geometry unchanged" — ортақ ``_compute_target_rect``
    санатқа тәуелсіз, дәл СОЛ анкерленген тіктөртбұрышты қайтарады."""
    backdrop = WorkspaceBackdrop()
    backdrop.resize(800, 600)

    backdrop.set_category(CATEGORY_LABORATORY)
    laboratory_target = backdrop._compute_target_rect()
    backdrop.set_category(CATEGORY_RESULTS)
    other_target = backdrop._compute_target_rect()

    assert laboratory_target == other_target


def test_laboratory_paints_without_crash_when_motion_disabled() -> None:
    motion.MOTION_ENABLED = False
    backdrop = WorkspaceBackdrop()
    backdrop.resize(800, 600)

    backdrop.set_category(CATEGORY_LABORATORY)
    backdrop.repaint()
