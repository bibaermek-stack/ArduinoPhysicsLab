"""TeacherDashboardPage юнит-тесттері: 4 summary карточка (НАҚТЫ репозиторий
сандары), "Бүгінгі белсенділік" (carousel-мен интеграция), "Жылдам
әрекеттер" (Router сигналдары), "Соңғы нәтижелер" (бос күй/нақты дерек)
(Phase 13, §18 талап тізімі).
"""

import sys
from datetime import datetime, timedelta, timezone

import pytest
from PySide6.QtWidgets import QApplication

from domain.entities.classroom import Classroom
from domain.entities.experiment_definition import ExperimentDefinition
from domain.entities.experiment_feedback_result import ExperimentFeedbackResult, TeacherAssessment
from domain.entities.experiment_session import ExperimentSession
from domain.entities.measurement import Measurement
from domain.entities.student import Student
from domain.entities.user_role import UserRole
from domain.interfaces.i_physics_module import IPhysicsModule
from infrastructure.storage.sqlite_classroom_repository import SqliteClassroomRepository
from infrastructure.storage.sqlite_feedback_repository import SqliteFeedbackRepository
from infrastructure.storage.sqlite_session_repository import SqliteSessionRepository
from infrastructure.storage.sqlite_student_progress_repository import SqliteStudentProgressRepository
from infrastructure.storage.sqlite_student_repository import SqliteStudentRepository
from modules.module_registry import ModuleRegistry
from ui.pages.teacher_dashboard_page import TeacherDashboardPage

_NOW = datetime.now(timezone.utc)
_OHMS_LAW = ExperimentDefinition(id="ohms-law", title="Ом заңы", description="", display_number=4)


class _FakeModule(IPhysicsModule):
    def get_name(self) -> str:
        return "Электр құбылыстары"

    def get_icon(self) -> str | None:
        return "⚡"

    def get_experiments(self) -> tuple[ExperimentDefinition, ...]:
        return (_OHMS_LAW,)


@pytest.fixture(scope="module", autouse=True)
def qt_application() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def _make_page() -> tuple[
    TeacherDashboardPage, SqliteClassroomRepository, SqliteStudentRepository,
    SqliteStudentProgressRepository, SqliteFeedbackRepository, SqliteSessionRepository,
]:
    classroom_repository = SqliteClassroomRepository()
    student_repository = SqliteStudentRepository()
    session_repository = SqliteSessionRepository()
    feedback_repository = SqliteFeedbackRepository()
    progress_repository = SqliteStudentProgressRepository(
        session_repository=session_repository, feedback_repository=feedback_repository,
        classroom_repository=classroom_repository, student_repository=student_repository,
    )
    module_registry = ModuleRegistry()
    module_registry.register(_FakeModule())

    page = TeacherDashboardPage(
        student_progress_repository=progress_repository,
        classroom_repository=classroom_repository,
        student_repository=student_repository,
        module_registry=module_registry,
    )
    return page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository


def _save_measured_session(session_repository: SqliteSessionRepository, session_id: str) -> None:
    session = ExperimentSession(id=session_id, experiment_id="ohms-law", started_at=_NOW)
    session.add_measurement(Measurement(timestamp=_NOW, values={"voltage": 5.0}, experiment_id="ohms-law"))
    session_repository.save_session(session)


# =====================================================================
# 4 summary карточка — ӨЗГЕРІССІЗ (§ "KEEP the existing 4 summary cards")
# =====================================================================


def test_zero_state_shows_all_zero_counts() -> None:
    page, *_rest = _make_page()

    assert page._value_labels["classrooms"].text() == "0"
    assert page._value_labels["students"].text() == "0"
    assert page._value_labels["completed"].text() == "0"
    assert page._value_labels["awaiting_review"].text() == "0"


def test_reflects_real_classroom_and_student_counts() -> None:
    page, classroom_repository, student_repository, _progress, _feedback, _sessions = _make_page()

    classroom_repository.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    student_repository.create(
        Student(id="s1", classroom_id="c1", first_name="Айдос", last_name="С",
                created_at=_NOW, updated_at=_NOW),
        UserRole.TEACHER,
    )
    page.on_enter()

    assert page._value_labels["classrooms"].text() == "1"
    assert page._value_labels["students"].text() == "1"


def test_on_enter_refreshes_counts() -> None:
    page, classroom_repository, _student, _progress, _feedback, _sessions = _make_page()
    assert page._value_labels["classrooms"].text() == "0"

    classroom_repository.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    page.on_enter()

    assert page._value_labels["classrooms"].text() == "1"


# =====================================================================
# "Бүгінгі белсенділік" — Activity carousel интеграциясы
# =====================================================================


def test_activity_panel_empty_state_when_no_activity() -> None:
    page, *_rest = _make_page()

    assert page._activity_carousel._items == ()


def test_activity_panel_populated_from_real_progress() -> None:
    page, classroom_repository, student_repository, progress_repository, _feedback, _sessions = _make_page()
    classroom_repository.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    student_repository.create(
        Student(id="s1", classroom_id="c1", first_name="Айдос", last_name="С",
                created_at=_NOW, updated_at=_NOW),
        UserRole.TEACHER,
    )
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")

    page.on_enter()

    items = page._activity_carousel._items
    assert len(items) == 1
    assert items[0].classroom_name == "8А"
    assert "Ом заңы" in items[0].experiment_label


def test_activity_panel_omits_snapshot_for_experiment_missing_from_catalog() -> None:
    """§ "DO NOT fabricate" — catalog-та жоқ experiment_id-мен snapshot
    тыныш өткізіп жіберіледі, exception шықпайды."""
    page, classroom_repository, student_repository, progress_repository, _feedback, _sessions = _make_page()
    classroom_repository.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    student_repository.create(
        Student(id="s1", classroom_id="c1", first_name="Айдос", last_name="С",
                created_at=_NOW, updated_at=_NOW),
        UserRole.TEACHER,
    )
    progress_repository.link_session("sess1", "s1", "c1", "unknown-experiment")

    page.on_enter()

    assert page._activity_carousel._items == ()


def test_on_enter_starts_activity_carousel() -> None:
    page, *_rest = _make_page()
    page.show()

    page.on_enter()

    # тек ЖАЛҒЫЗ item болғанда таймер жұмыс істемейді (§17) — бос
    # күйде де exception шықпайтынын тексереміз.
    assert page._activity_carousel._timer.isActive() is False


def test_hide_stops_activity_carousel_timer() -> None:
    page, classroom_repository, student_repository, progress_repository, _feedback, _sessions = _make_page()
    classroom_repository.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    classroom_repository.create(
        Classroom(id="c2", name="9А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    for cid in ("c1", "c2"):
        student_repository.create(
            Student(id=f"s_{cid}", classroom_id=cid, first_name="A", last_name="B",
                    created_at=_NOW, updated_at=_NOW),
            UserRole.TEACHER,
        )
        progress_repository.link_session(f"sess_{cid}", f"s_{cid}", cid, "ohms-law")
    page.show()
    page.on_enter()
    assert page._activity_carousel._timer.isActive() is True

    page.hide()

    assert page._activity_carousel._timer.isActive() is False


# =====================================================================
# "Жылдам әрекеттер" — Router сигналдары
# =====================================================================


def test_quick_action_buttons_emit_existing_router_signals() -> None:
    page, *_rest = _make_page()

    classes_calls = []
    labs_calls = []
    devices_calls = []
    page.classes_requested.connect(lambda: classes_calls.append(1))
    page.labs_requested.connect(lambda: labs_calls.append(1))
    page.devices_requested.connect(lambda: devices_calls.append(1))

    # Тек "Жылдам әрекеттер" панеліндегі батырмалар (§ carousel-дің ӨЗ
    # бос-күй "Зертханалық жұмысты бастау" батырмасы БІРДЕЙ мәтінді
    # қолданады, сондықтан ажырату үшін objectName-мен parent-ты
    # тексереміз).
    quick_action_buttons = [
        button
        for button in page.findChildren(type(page._activity_carousel._prev_button))
        if button.objectName() == "DashboardQuickActionButton"
        and button.parentWidget() is not page._activity_carousel._current_slide
    ]
    for button in quick_action_buttons:
        if button.text() == "Сынып құру":
            button.click()
        elif button.text() == "Зертханалық жұмысты бастау":
            button.click()
        elif button.text() == "Құрылғыны қосу":
            button.click()

    assert classes_calls == [1]
    assert labs_calls == [1]
    assert devices_calls == [1]


def test_activity_empty_state_start_lab_button_emits_labs_requested() -> None:
    page, *_rest = _make_page()
    calls = []
    page.labs_requested.connect(lambda: calls.append(1))

    page._activity_carousel._current_slide.action_button.click()

    assert calls == [1]


# =====================================================================
# "Соңғы нәтижелер"
# =====================================================================


def test_recent_results_empty_state_by_default() -> None:
    page, *_rest = _make_page()

    assert page._results_table.isHidden() is True
    assert page._results_empty_title_label.isHidden() is False


def test_recent_results_uses_repository_data() -> None:
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = _make_page()
    classroom_repository.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    student_repository.create(
        Student(id="s1", classroom_id="c1", first_name="Айдос", last_name="С",
                created_at=_NOW, updated_at=_NOW),
        UserRole.TEACHER,
    )
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    feedback_repository.save_submission(
        ExperimentFeedbackResult(
            experiment_id="ohms-law", session_id="sess1", is_draft=False,
            submitted_at=_NOW - timedelta(minutes=5),
        )
    )

    page.on_enter()

    assert page._results_table.isHidden() is False
    assert page._results_empty_title_label.isHidden() is True
    assert page._results_table.rowCount() == 1
    assert page._results_table.item(0, 0).text() == "С Айдос"
    assert page._results_table.item(0, 1).text() == "8А"
    assert page._results_table.item(0, 2).text() == "Ом заңы"
    assert page._results_table.item(0, 4).text() == "Тексеруді күтуде"


def test_results_requested_signal_wired_to_view_all_button() -> None:
    page, *_rest = _make_page()
    calls = []
    page.results_requested.connect(lambda: calls.append(1))

    for button in page.findChildren(type(page._activity_carousel._prev_button)):
        if button.text() == "Барлық нәтижелерді көру →":
            button.click()

    assert calls == [1]


# =====================================================================
# Phase 13 follow-up: "Stable Classroom Accent Colors"
# =====================================================================


def test_activity_cards_carry_deterministic_classroom_accent() -> None:
    from ui.widgets.class_activity_carousel import classroom_accent_color

    page, classroom_repository, student_repository, progress_repository, _feedback, _sessions = _make_page()
    classroom_repository.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    student_repository.create(
        Student(id="s1", classroom_id="c1", first_name="Айдос", last_name="С",
                created_at=_NOW, updated_at=_NOW),
        UserRole.TEACHER,
    )
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")

    page.on_enter()

    assert page._activity_carousel._items[0].accent_color == classroom_accent_color("c1")


def test_same_classroom_keeps_same_accent_across_refreshes() -> None:
    page, classroom_repository, student_repository, progress_repository, _feedback, _sessions = _make_page()
    classroom_repository.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    student_repository.create(
        Student(id="s1", classroom_id="c1", first_name="Айдос", last_name="С",
                created_at=_NOW, updated_at=_NOW),
        UserRole.TEACHER,
    )
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")

    page.on_enter()
    first_color = page._activity_carousel._items[0].accent_color
    # § "Navigating away and returning to Dashboard preserves the same
    # mapping" — models репозиторийден ЖАҢА snapshot қайта есептелетінін
    # on_enter()-ді қайта шақыру арқылы.
    page.on_enter()
    second_color = page._activity_carousel._items[0].accent_color

    assert first_color == second_color


# =====================================================================
# Phase 8: "Ескертулер" (teacher alerts)
# =====================================================================


def test_alerts_panel_empty_state_by_default() -> None:
    page, *_rest = _make_page()

    assert page._alerts_table.isHidden() is True
    assert page._alerts_empty_title_label.isHidden() is False


def test_alerts_panel_shows_low_score_alert_from_real_reviewed_progress() -> None:
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = _make_page()
    classroom_repository.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    student_repository.create(
        Student(id="s1", classroom_id="c1", first_name="Айдос", last_name="С",
                created_at=_NOW, updated_at=_NOW),
        UserRole.TEACHER,
    )
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    feedback_repository.save_submission(
        ExperimentFeedbackResult(
            experiment_id="ohms-law", session_id="sess1", is_draft=False, submitted_at=_NOW,
        )
    )
    # DEFAULT_LOW_SCORE_THRESHOLD (5.0) - 3-ден ТӨМЕН баға § LOW_SCORE ескертуін шығарады.
    feedback_repository.save_teacher_assessment(
        "sess1", "ohms-law", TeacherAssessment(score=3, comment=""), UserRole.TEACHER
    )

    page.on_enter()

    assert page._alerts_table.isHidden() is False
    assert page._alerts_empty_title_label.isHidden() is True
    assert page._alerts_table.rowCount() == 1
    assert page._alerts_table.item(0, 0).text() == "Төмен баға"
    assert page._alerts_table.item(0, 1).text() == "С Айдос"
    assert page._alerts_table.item(0, 2).text() == "8А"


def test_alerts_panel_action_button_emits_student_monitoring_requested() -> None:
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = _make_page()
    classroom_repository.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    student_repository.create(
        Student(id="s1", classroom_id="c1", first_name="Айдос", last_name="С",
                created_at=_NOW, updated_at=_NOW),
        UserRole.TEACHER,
    )
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    feedback_repository.save_submission(
        ExperimentFeedbackResult(
            experiment_id="ohms-law", session_id="sess1", is_draft=False, submitted_at=_NOW,
        )
    )
    feedback_repository.save_teacher_assessment(
        "sess1", "ohms-law", TeacherAssessment(score=2, comment=""), UserRole.TEACHER
    )
    page.on_enter()
    calls = []
    page.student_monitoring_requested.connect(lambda sid, eid: calls.append((sid, eid)))

    action_button = page._alerts_table.cellWidget(0, 4)
    action_button.click()

    assert calls == [("s1", "ohms-law")]


def test_alerts_panel_no_alert_for_good_reviewed_score() -> None:
    """§ "no fabricated alerts" — жоғары баға ЕШБІР ескерту тудырмайды."""
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = _make_page()
    classroom_repository.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    student_repository.create(
        Student(id="s1", classroom_id="c1", first_name="Айдос", last_name="С",
                created_at=_NOW, updated_at=_NOW),
        UserRole.TEACHER,
    )
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    feedback_repository.save_submission(
        ExperimentFeedbackResult(
            experiment_id="ohms-law", session_id="sess1", is_draft=False, submitted_at=_NOW,
        )
    )
    feedback_repository.save_teacher_assessment(
        "sess1", "ohms-law", TeacherAssessment(score=9, comment=""), UserRole.TEACHER
    )

    page.on_enter()

    assert page._alerts_table.isHidden() is True
    assert page._alerts_table.rowCount() == 0


def test_two_real_classrooms_get_visibly_different_accents() -> None:
    page, classroom_repository, student_repository, progress_repository, _feedback, _sessions = _make_page()
    classroom_repository.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    classroom_repository.create(
        Classroom(id="c2", name="9А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )
    for cid, name in (("c1", "Айдос"), ("c2", "Ерлан")):
        student_repository.create(
            Student(id=f"s_{cid}", classroom_id=cid, first_name=name, last_name="Т",
                    created_at=_NOW, updated_at=_NOW),
            UserRole.TEACHER,
        )
        progress_repository.link_session(f"sess_{cid}", f"s_{cid}", cid, "ohms-law")

    page.on_enter()

    items = page._activity_carousel._items
    assert len(items) == 2
    assert items[0].accent_color != items[1].accent_color
