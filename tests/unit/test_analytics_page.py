"""AnalyticsPage юнит-тесттері (Phase 19): таза есептеу қабаты
(``compute_*``/``_filter_*``/``_apply_period``/``_build_records``) және
Qt виджет интеграциясы (бос күй, KPI, сүзгі, route/back-button).
"""

import sys
from datetime import datetime, timedelta, timezone

import pytest
from PySide6.QtWidgets import QApplication, QPushButton

from domain.entities.classroom import Classroom
from domain.entities.experiment_definition import ExperimentDefinition
from domain.entities.experiment_feedback_result import ExperimentFeedbackResult, TeacherAssessment
from domain.entities.experiment_session import ExperimentSession
from domain.entities.measurement import Measurement
from domain.entities.student import Student
from domain.entities.student_experiment_progress import ProgressStatus, StudentExperimentProgress
from domain.entities.user_role import UserRole
from domain.interfaces.i_physics_module import IPhysicsModule
from infrastructure.storage.sqlite_classroom_repository import SqliteClassroomRepository
from infrastructure.storage.sqlite_feedback_repository import SqliteFeedbackRepository
from infrastructure.storage.sqlite_session_repository import SqliteSessionRepository
from infrastructure.storage.sqlite_student_progress_repository import SqliteStudentProgressRepository
from infrastructure.storage.sqlite_student_repository import SqliteStudentRepository
from modules.module_registry import ModuleRegistry
from domain.entities.learning_analytics import TopicPerformanceLevel
from ui.pages.analytics_page import (
    AnalyticsPage,
    _apply_period,
    _build_records,
    _filter_records,
    _ProgressRecord,
    compute_activity_trend,
    compute_classroom_performance,
    compute_experiment_performance,
    compute_kpis,
    compute_work_status_counts,
    row_index_for_y,
)
from ui.widgets.class_activity_carousel import classroom_accent_color

_NOW = datetime.now(timezone.utc)
_OHMS_LAW = ExperimentDefinition(id="ohms-law", title="Ом заңы", description="", display_number=4)
_CURRENT_WORK = ExperimentDefinition(
    id="current-work", title="Ток жұмысы", description="", display_number=5
)


class _FakeModule(IPhysicsModule):
    def get_name(self) -> str:
        return "Электр құбылыстары"

    def get_icon(self) -> str | None:
        return "⚡"

    def get_experiments(self) -> tuple[ExperimentDefinition, ...]:
        return (_OHMS_LAW, _CURRENT_WORK)


def _record(
    *,
    student_id: str = "s1",
    classroom_id: str = "c1",
    classroom_name: str = "8А",
    experiment_id: str = "ohms-law",
    status: ProgressStatus = ProgressStatus.REVIEWED,
    teacher_score: int | None = 8,
    last_activity_at: datetime | None = _NOW,
) -> _ProgressRecord:
    return _ProgressRecord(
        student_id=student_id,
        classroom_id=classroom_id,
        classroom_name=classroom_name,
        experiment_id=experiment_id,
        status=status,
        teacher_score=teacher_score,
        last_activity_at=last_activity_at,
    )


# =====================================================================
# Таза есептеу қабаты — Qt-сыз
# =====================================================================


def test_compute_kpis_empty_state_shows_dash_not_zero() -> None:
    kpis = compute_kpis((), ())

    assert kpis.average_score_text == "—"
    assert kpis.completion_rate_text == "—"
    assert kpis.active_students_text == "0"
    assert kpis.waiting_review_text == "0"


def test_compute_kpis_average_uses_only_reviewed_scores() -> None:
    records = (
        _record(status=ProgressStatus.REVIEWED, teacher_score=8),
        _record(status=ProgressStatus.REVIEWED, teacher_score=6),
        _record(status=ProgressStatus.FEEDBACK_SUBMITTED, teacher_score=None),
    )

    kpis = compute_kpis(records, records)

    assert kpis.average_score_text == "7.0"


def test_compute_kpis_completion_rate_denominator_is_all_started_pairs() -> None:
    """§ "Clearly document the exact denominator used" — бөлгіш каталог х
    оқушы емес, ТЕК НАҚТЫ басталған (session_student_link бар) жұп саны."""
    records = (
        _record(student_id="s1", status=ProgressStatus.REVIEWED),
        _record(student_id="s2", status=ProgressStatus.IN_PROGRESS),
        _record(student_id="s3", status=ProgressStatus.MEASUREMENT_COMPLETED),
        _record(student_id="s4", status=ProgressStatus.IN_PROGRESS),
    )

    kpis = compute_kpis(records, records)

    assert kpis.completion_rate_text == "50%"  # 2/4


def test_compute_kpis_waiting_review_counts_feedback_submitted_only() -> None:
    records = (
        _record(status=ProgressStatus.FEEDBACK_SUBMITTED),
        _record(status=ProgressStatus.FEEDBACK_SUBMITTED),
        _record(status=ProgressStatus.REVIEWED),
    )

    kpis = compute_kpis(records, records)

    assert kpis.waiting_review_text == "2"


def test_compute_kpis_active_students_uses_period_filtered_records_only() -> None:
    all_records = (_record(student_id="s1"), _record(student_id="s2"))
    period_records = (_record(student_id="s1"),)  # тек s1 кезең ішінде

    kpis = compute_kpis(all_records, period_records)

    assert kpis.active_students_text == "1"


def test_filter_records_applies_classroom_and_experiment_with_and_logic() -> None:
    records = (
        _record(classroom_id="c1", experiment_id="ohms-law"),
        _record(classroom_id="c1", experiment_id="current-work"),
        _record(classroom_id="c2", experiment_id="ohms-law"),
    )

    filtered = _filter_records(records, classroom_id="c1", experiment_id="ohms-law")

    assert len(filtered) == 1
    assert filtered[0].classroom_id == "c1"
    assert filtered[0].experiment_id == "ohms-law"


def test_filter_records_all_filter_is_none_and_returns_everything() -> None:
    records = (_record(classroom_id="c1"), _record(classroom_id="c2"))

    assert _filter_records(records, None, None) == records


def test_apply_period_7_days_excludes_older_activity() -> None:
    now = datetime.now(timezone.utc)
    recent = _record(last_activity_at=now - timedelta(days=2))
    old = _record(last_activity_at=now - timedelta(days=20))

    result = _apply_period((recent, old), "7d", now)

    assert result == (recent,)


def test_apply_period_all_time_keeps_everything_with_a_timestamp() -> None:
    now = datetime.now(timezone.utc)
    old = _record(last_activity_at=now - timedelta(days=400))

    result = _apply_period((old,), "all", now)

    assert result == (old,)


def test_compute_classroom_performance_marks_no_reviewed_scores_as_none() -> None:
    classrooms = (
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW),
        Classroom(id="c2", name="9Б", created_at=_NOW, updated_at=_NOW),
    )
    records = (
        _record(classroom_id="c1", status=ProgressStatus.REVIEWED, teacher_score=9),
        _record(classroom_id="c2", status=ProgressStatus.IN_PROGRESS, teacher_score=None),
    )

    rows = compute_classroom_performance(records, classrooms)

    assert len(rows) == 2
    row_by_id = {row.classroom_id: row for row in rows}
    assert row_by_id["c1"].average_score == 9.0
    assert row_by_id["c2"].average_score is None


def test_compute_classroom_performance_uses_canonical_phase13_accent_colors() -> None:
    """§18 "DO NOT create a second classroom color algorithm"."""
    classrooms = (Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW),)
    records = (_record(classroom_id="c1"),)

    rows = compute_classroom_performance(records, classrooms)

    assert rows[0].accent_color == classroom_accent_color("c1", "8А")


def test_compute_work_status_never_includes_not_started() -> None:
    records = (_record(status=ProgressStatus.IN_PROGRESS),)

    counts = compute_work_status_counts(records)

    assert ProgressStatus.NOT_STARTED not in counts
    assert counts[ProgressStatus.IN_PROGRESS] == 1


def test_compute_experiment_performance_uses_module_registry_catalog() -> None:
    """§8 "experiments come from ModuleRegistry rather than hardcoded
    titles"."""
    experiments = (_OHMS_LAW, _CURRENT_WORK)
    records = (
        _record(experiment_id="ohms-law", status=ProgressStatus.REVIEWED, teacher_score=10),
    )

    rows = compute_experiment_performance(records, experiments)

    assert len(rows) == 2
    row_by_id = {row.experiment_id: row for row in rows}
    assert row_by_id["ohms-law"].title == "Ом заңы"
    assert row_by_id["ohms-law"].display_number == 4
    assert row_by_id["ohms-law"].average_score == 10.0
    assert row_by_id["current-work"].average_score is None


def test_compute_activity_trend_accepts_empty_dataset() -> None:
    now = datetime.now(timezone.utc)

    points = compute_activity_trend((), "all", now)

    assert points == ()


def test_compute_activity_trend_7_days_has_seven_zero_or_real_buckets() -> None:
    now = datetime.now(timezone.utc)
    records = (_record(last_activity_at=now),)

    points = compute_activity_trend(records, "7d", now)

    assert len(points) == 7
    assert sum(point.count for point in points) == 1


def test_compute_activity_trend_never_fabricates_points_outside_range() -> None:
    now = datetime.now(timezone.utc)
    records = (_record(last_activity_at=now - timedelta(days=100)),)

    points = compute_activity_trend(records, "7d", now)

    assert sum(point.count for point in points) == 0
    assert len(points) == 7


def test_row_index_for_y_bounds_checking() -> None:
    assert row_index_for_y(0.4, 3) == 0
    assert row_index_for_y(1.49, 3) == 1
    assert row_index_for_y(-1.0, 3) is None
    assert row_index_for_y(5.0, 3) is None
    assert row_index_for_y(0.0, 0) is None


def test_build_records_skips_orphaned_progress_without_fabricating() -> None:
    session_repository = SqliteSessionRepository()
    feedback_repository = SqliteFeedbackRepository()
    classroom_repository = SqliteClassroomRepository()
    student_repository = SqliteStudentRepository()
    progress = StudentExperimentProgress(
        student_id="ghost", experiment_id="ohms-law", status=ProgressStatus.IN_PROGRESS
    )

    records = _build_records((progress,), student_repository, classroom_repository)

    assert records == ()


# =====================================================================
# Qt виджет интеграциясы
# =====================================================================


@pytest.fixture(scope="module", autouse=True)
def qt_application() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def _make_page() -> tuple[
    AnalyticsPage, SqliteClassroomRepository, SqliteStudentRepository,
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

    page = AnalyticsPage(
        classroom_repository=classroom_repository,
        student_repository=student_repository,
        student_progress_repository=progress_repository,
        module_registry=module_registry,
    )
    return page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository


def _save_measured_session(
    session_repository: SqliteSessionRepository, session_id: str, experiment_id: str = "ohms-law"
) -> None:
    session = ExperimentSession(id=session_id, experiment_id=experiment_id, started_at=_NOW)
    session.add_measurement(Measurement(timestamp=_NOW, values={"voltage": 5.0}, experiment_id=experiment_id))
    session_repository.save_session(session)


def test_page_has_no_back_button() -> None:
    page, _c, _s, _p, _f, _sess = _make_page()

    back_buttons = [b for b in page.findChildren(QPushButton) if b.text() == "← Артқа"]

    assert back_buttons == []


def test_page_title_is_first_top_level_layout_element() -> None:
    """§2 "The Analytics title must become the first page-layout
    element" — content layout-тың 0-элементі тақырып QLabel (back button
    ЖОҚ, спейсер де ЖОҚ)."""
    page, _c, _s, _p, _f, _sess = _make_page()

    content_layout = page._content_widget.layout()
    first_widget = content_layout.itemAt(0).widget()
    assert first_widget.text() == "Аналитика"


def test_empty_state_shown_when_no_classrooms_exist() -> None:
    page, _c, _s, _p, _f, _sess = _make_page()

    assert page._stack.currentIndex() == 0
    assert page._empty_title_label.text() == "Аналитика үшін жеткілікті дерек әлі жиналған жоқ."


def test_content_shown_once_a_classroom_exists_even_without_progress() -> None:
    page, classroom_repository, student_repository, _p, _f, _sess = _make_page()
    classroom_repository.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )

    page.on_enter()

    assert page._stack.currentIndex() == 1
    assert page._value_labels["average"].text() == "—"
    assert page._value_labels["waiting"].text() == "0"


def test_kpi_cards_reflect_real_reviewed_score() -> None:
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
        "sess1", "ohms-law", TeacherAssessment(score=7, comment=""), UserRole.TEACHER
    )

    page.on_enter()

    assert page._value_labels["average"].text() == "7.0"
    assert page._value_labels["waiting"].text() == "0"


def test_classroom_filter_isolates_records_to_selected_classroom() -> None:
    page, classroom_repository, student_repository, progress_repository, feedback_repository, session_repository = _make_page()
    for cid, name in (("c1", "8А"), ("c2", "9Б")):
        classroom_repository.create(
            Classroom(id=cid, name=name, created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
        )
    student_repository.create(
        Student(id="s1", classroom_id="c1", first_name="Один", last_name="Т",
                created_at=_NOW, updated_at=_NOW),
        UserRole.TEACHER,
    )
    student_repository.create(
        Student(id="s2", classroom_id="c2", first_name="Екі", last_name="Т",
                created_at=_NOW, updated_at=_NOW),
        UserRole.TEACHER,
    )
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    progress_repository.link_session("sess2", "s2", "c2", "ohms-law")
    _save_measured_session(session_repository, "sess2")

    page.on_enter()
    classroom_index = page._classroom_filter_combo.findData("c1")
    page._classroom_filter_combo.setCurrentIndex(classroom_index)

    assert page._value_labels["active_students"].text() == "1"


def test_experiment_filter_populated_from_module_registry_not_hardcoded() -> None:
    page, classroom_repository, _s, _p, _f, _sess = _make_page()
    classroom_repository.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )

    page.on_enter()

    labels = [page._experiment_filter_combo.itemText(i) for i in range(page._experiment_filter_combo.count())]
    assert "Барлығы" in labels
    assert any("Ом заңы" in label for label in labels)
    assert any("Ток жұмысы" in label for label in labels)


def test_period_filter_defaults_to_30_days() -> None:
    page, _c, _s, _p, _f, _sess = _make_page()

    assert page._period_filter_combo.currentData() == "30d"


def test_graphs_accept_empty_dataset_without_raising() -> None:
    """§9 "Do not fabricate points for unavailable history beyond
    representing zero-count buckets inside a valid selected date range" —
    әдепкі "30 күн" кезеңінде тренд панелі НАҚТЫ (барлығы нөл) себеттерді
    көрсетеді (ауқымның ӨЗІ жарамды), ал "Барлық уақыт"-та дерек мүлде
    жоқ болғандықтан жарамды ауқым да жоқ — панель "дерек жоқ" күйіне
    түседі. Екі жағдайда да ЕШБІР exception шықпайды."""
    page, classroom_repository, _s, _p, _f, _sess = _make_page()
    classroom_repository.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )

    page.on_enter()  # ешбір progress жазбасы жоқ

    assert page._work_status_stack.currentIndex() == 0
    assert page._trend_stack.currentIndex() == 1  # 30 күндік ауқым жарамды, барлығы 0

    all_time_index = page._period_filter_combo.findData("all")
    page._period_filter_combo.setCurrentIndex(all_time_index)

    assert page._trend_stack.currentIndex() == 0  # дерек мүлде жоқ -> жарамды ауқым да жоқ


def test_filter_change_updates_graphs_without_new_repository_snapshot() -> None:
    """§16 "Avoid recomputation inside paintEvent" / "duplicate repository
    queries" — сүзгі ауысымы ``_all_records`` кэшін қайта пайдаланады."""
    page, classroom_repository, student_repository, progress_repository, _f, session_repository = _make_page()
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
    cached_records = page._all_records

    period_index = page._period_filter_combo.findData("7d")
    page._period_filter_combo.setCurrentIndex(period_index)

    assert page._all_records is cached_records


# =====================================================================
# Phase 8: Оқушылар бойынша үлгерім (per-student breakdown)
# =====================================================================


def test_student_progress_panel_empty_state_by_default() -> None:
    page, classroom_repository, _s, _p, _f, _sess = _make_page()
    classroom_repository.create(
        Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
    )

    page.on_enter()

    assert page._student_stack.currentIndex() == 0
    assert page._student_export_button.isEnabled() is False


def test_student_progress_panel_populated_from_real_reviewed_score() -> None:
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
        "sess1", "ohms-law", TeacherAssessment(score=3, comment=""), UserRole.TEACHER
    )

    page.on_enter()

    assert page._student_stack.currentIndex() == 1
    assert page._student_export_button.isEnabled() is True
    assert page._student_table.rowCount() == 1
    assert page._student_table.item(0, 0).text() == "С Айдос"
    assert page._student_table.item(0, 1).text() == "8А"
    assert page._student_table.item(0, 2).text() == "3.0"
    # § "score-based proxy" — 3.0 < DEFAULT_WEAK_THRESHOLD (5.0), сондықтан
    # ЕҢ ӘЛСІЗ тақырып ретінде ДӘЛ осы тәжірибе көрсетіледі.
    assert page._student_table.item(0, 4).text() == "Ом заңы"


def test_student_row_action_button_emits_student_monitoring_requested() -> None:
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
        "sess1", "ohms-law", TeacherAssessment(score=3, comment=""), UserRole.TEACHER
    )
    page.on_enter()
    calls = []
    page.student_monitoring_requested.connect(lambda sid, eid: calls.append((sid, eid)))

    action_button = page._student_table.cellWidget(0, 6)
    action_button.click()

    assert calls == [("s1", "ohms-law")]


def test_student_progress_panel_filters_with_classroom_selection() -> None:
    page, classroom_repository, student_repository, progress_repository, _f, session_repository = _make_page()
    for cid, name in (("c1", "8А"), ("c2", "9Б")):
        classroom_repository.create(
            Classroom(id=cid, name=name, created_at=_NOW, updated_at=_NOW), UserRole.TEACHER
        )
    student_repository.create(
        Student(id="s1", classroom_id="c1", first_name="Один", last_name="Т",
                created_at=_NOW, updated_at=_NOW),
        UserRole.TEACHER,
    )
    student_repository.create(
        Student(id="s2", classroom_id="c2", first_name="Екі", last_name="Т",
                created_at=_NOW, updated_at=_NOW),
        UserRole.TEACHER,
    )
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1")
    progress_repository.link_session("sess2", "s2", "c2", "ohms-law")
    _save_measured_session(session_repository, "sess2")

    page.on_enter()
    assert page._student_table.rowCount() == 2

    classroom_index = page._classroom_filter_combo.findData("c1")
    page._classroom_filter_combo.setCurrentIndex(classroom_index)

    assert page._student_table.rowCount() == 1
    assert page._student_table.item(0, 0).text() == "Т Один"


def test_topic_level_color_dict_has_no_arbitrary_hex() -> None:
    """§ "no new hex colors" — ``_TOPIC_LEVEL_COLOR`` тек ThemeManager
    токендерінен (COLOR_ERROR/COLOR_SUCCESS/COLOR_TEXT_MUTED) құралады."""
    from ui.pages.analytics_page import _TOPIC_LEVEL_COLOR

    assert set(_TOPIC_LEVEL_COLOR.keys()) == {
        TopicPerformanceLevel.WEAK, TopicPerformanceLevel.STRONG, TopicPerformanceLevel.NEUTRAL,
    }


def test_other_routes_unchanged_placeholder_still_has_back_button() -> None:
    """§ регрессия сақтандыруы — бұл файл тек Analytics-қа қатысты,
    Question Bank placeholder мінез-құлқы ``test_main_window.py``-де
    бөлек тексеріледі."""
    from ui.pages.placeholder_page import PlaceholderPage

    placeholder = PlaceholderPage("Сұрақтар банкі", "сипаттама")

    back_buttons = [b for b in placeholder.findChildren(QPushButton) if b.text() == "← Артқа"]
    assert len(back_buttons) == 1
