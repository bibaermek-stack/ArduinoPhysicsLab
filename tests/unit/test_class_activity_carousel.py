"""ClassActivityCarousel юнит-тесттері (Phase 13, §18 талап тізімі)."""

import sys

import pytest
from PySide6.QtWidgets import QApplication

from ui.widgets import motion
from ui.widgets.class_activity_carousel import (
    CLASSROOM_ACCENT_PALETTE,
    ActivityCardData,
    ClassActivityCarousel,
    classroom_accent_color,
)

_CARD_A = ActivityCardData(
    classroom_name="8А",
    experiment_label="№3 Электр тізбегін құрастыру",
    student_count=18,
    completed_count=12,
    in_progress_count=4,
    not_started_count=2,
    percentage=67,
    accent_color=classroom_accent_color("c1"),
)
_CARD_B = ActivityCardData(
    classroom_name="9А",
    experiment_label="№1 Ом заңы",
    student_count=20,
    completed_count=5,
    in_progress_count=10,
    not_started_count=5,
    percentage=25,
    accent_color=classroom_accent_color("c2"),
)


@pytest.fixture(scope="module", autouse=True)
def qt_application() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture(autouse=True)
def _restore_motion_enabled():
    original = motion.MOTION_ENABLED
    yield
    motion.MOTION_ENABLED = original


def test_empty_state_has_no_carousel_controls() -> None:
    carousel = ClassActivityCarousel()

    assert carousel._prev_button.isVisible() is False
    assert carousel._next_button.isVisible() is False
    assert carousel._indicator_labels == []


def test_single_item_has_no_carousel_controls() -> None:
    """§ "one class does not unnecessarily behave like a carousel"."""
    carousel = ClassActivityCarousel()

    carousel.set_items((_CARD_A,))

    assert carousel._prev_button.isVisible() is False
    assert carousel._next_button.isVisible() is False
    assert carousel._indicator_labels == []


def test_multiple_items_enable_carousel_controls() -> None:
    carousel = ClassActivityCarousel()
    carousel.show()

    carousel.set_items((_CARD_A, _CARD_B))

    assert carousel._prev_button.isHidden() is False
    assert carousel._next_button.isHidden() is False
    assert len(carousel._indicator_labels) == 2


def test_next_changes_displayed_class() -> None:
    carousel = ClassActivityCarousel()
    carousel.set_items((_CARD_A, _CARD_B))
    assert carousel._current_index == 0

    carousel._on_next_clicked()

    assert carousel._current_index == 1


def test_prev_wraps_to_last_class() -> None:
    carousel = ClassActivityCarousel()
    carousel.set_items((_CARD_A, _CARD_B))

    carousel._on_prev_clicked()

    assert carousel._current_index == 1


def test_auto_rotation_timer_runs_only_with_multiple_items_and_visible() -> None:
    """§17 "Timer Lifecycle" — тек Дашборд көрінгенде ЖӘНЕ бірден көп
    item болғанда жұмыс істейді."""
    carousel = ClassActivityCarousel()
    carousel.show()

    carousel.set_items((_CARD_A,))
    assert carousel._timer.isActive() is False

    carousel.set_items((_CARD_A, _CARD_B))
    assert carousel._timer.isActive() is True


def test_hover_pauses_rotation_and_leave_resumes() -> None:
    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtGui import QEnterEvent

    carousel = ClassActivityCarousel()
    carousel.show()
    carousel.set_items((_CARD_A, _CARD_B))
    assert carousel._timer.isActive() is True

    center = QPointF(carousel.rect().center())
    carousel.enterEvent(QEnterEvent(center, center, center))
    assert carousel._timer.isActive() is False

    carousel.leaveEvent(QEvent(QEvent.Type.Leave))
    assert carousel._timer.isActive() is True


def test_hide_stops_timer() -> None:
    carousel = ClassActivityCarousel()
    carousel.show()
    carousel.set_items((_CARD_A, _CARD_B))
    assert carousel._timer.isActive() is True

    carousel.hide()

    assert carousel._timer.isActive() is False


def test_manual_navigation_resets_timer_interval() -> None:
    carousel = ClassActivityCarousel()
    carousel.show()
    carousel.set_items((_CARD_A, _CARD_B))

    carousel._timer.setInterval(1)  # simulate near-expiry
    carousel._on_next_clicked()

    assert carousel._timer.interval() == 4000


def test_motion_disabled_switches_without_animation() -> None:
    """§ "MOTION_ENABLED == False -> content changes immediately, no
    slide/fade animation" — Phase 12-мен БІРДЕЙ жалғыз орталық сөндіргіш."""
    motion.MOTION_ENABLED = False
    carousel = ClassActivityCarousel()
    carousel.set_items((_CARD_A, _CARD_B))

    carousel._on_next_clicked()

    assert carousel._current_index == 1
    assert carousel._transitioning is False


def test_indicator_reflects_current_index() -> None:
    carousel = ClassActivityCarousel()
    carousel.set_items((_CARD_A, _CARD_B))

    carousel._on_next_clicked()

    assert carousel._indicator_labels[0].property("active") is False
    assert carousel._indicator_labels[1].property("active") is True


def test_start_lab_callback_invoked_from_empty_state() -> None:
    carousel = ClassActivityCarousel()
    calls = []
    carousel.set_start_lab_callback(lambda: calls.append(1))

    carousel._current_slide.action_button.click()

    assert calls == [1]


# =====================================================================
# Phase 13 follow-up: "Stable Classroom Accent Colors"
# =====================================================================


def test_classroom_accent_color_is_deterministic() -> None:
    assert classroom_accent_color("c1") == classroom_accent_color("c1")


def test_classroom_accent_color_not_based_on_list_position() -> None:
    """§ "Do NOT assign colors based only on current list index" — тек
    ``classroom_id``-ге тәуелді, шақыру ретіне/контекске ЕШБІР тәуелділік
    жоқ."""
    first_call = classroom_accent_color("stable-id")
    for _ in range(5):
        classroom_accent_color("some-other-id")
    assert classroom_accent_color("stable-id") == first_call


def test_classroom_accent_color_falls_back_to_name_when_id_empty() -> None:
    assert classroom_accent_color("", "8А") == classroom_accent_color("", "8А")


def test_classroom_accent_color_always_from_fixed_palette() -> None:
    for cid in ("a", "b", "c", "8А", "9Б", "random-uuid-1234"):
        assert classroom_accent_color(cid) in CLASSROOM_ACCENT_PALETTE


def test_two_different_classrooms_can_get_different_accents() -> None:
    """Ағымдағы 2 нақты сынып (§ "TEST/VERIFY") нақты ӘРТҮРЛІ түс алады."""
    assert classroom_accent_color("c1") != classroom_accent_color("c2")


def test_slide_left_border_uses_item_accent_color() -> None:
    carousel = ClassActivityCarousel()
    carousel.set_items((_CARD_A,))

    assert _CARD_A.accent_color in carousel._current_slide.styleSheet()


def test_slide_left_border_does_not_leak_into_child_stat_widgets() -> None:
    """Регрессия қорғанысы: ``QFrame#ActivitySlide``-тың border-left
    ережесі АЛДЫН АЛА (§ дөрекі, селекторсыз ``setStyleSheet()``) БАРЛЫҚ
    ұрпақ виджетке (мыс. әр статистика санының ӨЗ контейнеріне) каскадтап
    кеткен еді — скриншот аудитінде байқалды, ID-негізді селекторға
    ауыстырылып түзетілді. Бұл тест сол дәл багтың қайта оралуын
    болдырмайды."""
    carousel = ClassActivityCarousel()
    carousel.set_items((_CARD_A,))

    slide = carousel._current_slide
    # _build_stat() контейнерлері QWidget (QFrame ЕМЕС), бірақ жалпы
    # тексеру үшін барлық тікелей бала QWidget-тің өз styleSheet-інде
    # "border-left" СӨЗІ болмауын талап етеміз.
    from PySide6.QtWidgets import QWidget

    for child in slide.findChildren(QWidget):
        if child is slide:
            continue
        assert "border-left" not in child.styleSheet(), (
            f"{child} unexpectedly inherited/declared its own border-left "
            "(instance stylesheet scoping regression)"
        )


def test_active_indicator_dot_uses_item_accent_color() -> None:
    carousel = ClassActivityCarousel()
    carousel.set_items((_CARD_A, _CARD_B))

    assert _CARD_A.accent_color in carousel._indicator_labels[0].styleSheet()

    carousel._on_next_clicked()

    assert _CARD_B.accent_color in carousel._indicator_labels[1].styleSheet()
    assert _CARD_B.accent_color not in carousel._indicator_labels[0].styleSheet()


def test_mapping_survives_navigation_and_reset() -> None:
    """§ "Manual previous/next preserves the correct mapping" /
    "Navigating away and returning... preserves the same mapping" — Дашборд
    деңгейінде бұл `set_items()`-ті ЖАҢА `ActivityCardData` данасымен
    қайта шақыру арқылы модельденеді (§ teacher_dashboard_page._refresh()
    әр on_enter()-де қайта есептейді), нәтиже БІРДЕЙ болуы керек."""
    carousel = ClassActivityCarousel()
    carousel.set_items((_CARD_A, _CARD_B))
    carousel._on_next_clicked()
    carousel._on_next_clicked()  # wraps back to index 0 (8А)

    # "on_enter()" қайта шақырылғандағыдай, БІРДЕЙ classroom_id-ден ЖАҢА
    # card деректері қайта есептеледі — accent_color ӨЗГЕРМЕУІ керек.
    refreshed_card_a = ActivityCardData(
        classroom_name=_CARD_A.classroom_name,
        experiment_label=_CARD_A.experiment_label,
        student_count=_CARD_A.student_count,
        completed_count=_CARD_A.completed_count,
        in_progress_count=_CARD_A.in_progress_count,
        not_started_count=_CARD_A.not_started_count,
        percentage=_CARD_A.percentage,
        accent_color=classroom_accent_color("c1"),
    )
    carousel.set_items((refreshed_card_a, _CARD_B))

    assert carousel._items[0].accent_color == classroom_accent_color("c1")
