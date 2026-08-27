"""ExperimentWorkspacePage — Phase 39B session-ownership/blocked-state
тесттері: белсенді оқушысыз Оқушы режимі pipeline құрмайды, сессия
байланысы session identity қалыптасқан сәтте-ақ жазылады, Мұғалім
режимінде гейт мүлде жоқ.
"""

import sys
from datetime import datetime, timezone

import pytest
from PySide6.QtWidgets import QApplication

from domain.entities.active_student_context import ActiveStudentContext
from domain.entities.experiment_definition import ExperimentDefinition
from domain.entities.user_role import UserRole
from infrastructure.serial_comm.device_scanner import DeviceScanner
from infrastructure.storage.sqlite_active_student_repository import SqliteActiveStudentRepository
from infrastructure.storage.sqlite_student_progress_repository import SqliteStudentProgressRepository
from ui.pages.experiment_workspace_page import ExperimentWorkspacePage

from tests.unit.test_experiment_workspace_page import FakeExperimentController, _make_device
from uuid import uuid4


@pytest.fixture(scope="module", autouse=True)
def qt_application() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def _make_experiment() -> ExperimentDefinition:
    return ExperimentDefinition(id="ohms-law", title="Ом заңы", description="")


def _make_unique_controller() -> FakeExperimentController:
    """Production ``ExperimentController``/``MultiSensorExperimentCoordinator``
    әр ``on_enter()``-де ЖАҢА ``uuid4()`` session.id генерациялайды —
    бөлек ID-мен ЖАҢА fake экземпляры осы шындықты қайталайды (ортақ
    ``FakeExperimentController`` бір ғана тұрақты "fake-session" ID-ін
    қолданады, switching-тестіне жарамайды).
    """
    controller = FakeExperimentController()
    controller.session.id = str(uuid4())
    return controller


def _make_page(
    role: UserRole = UserRole.STUDENT,
    active_student_repository: SqliteActiveStudentRepository | None = None,
    student_progress_repository: SqliteStudentProgressRepository | None = None,
    controller_factory=None,
) -> tuple[ExperimentWorkspacePage, FakeExperimentController, SqliteActiveStudentRepository, SqliteStudentProgressRepository]:
    fake_controller = FakeExperimentController()
    active_repository = active_student_repository or SqliteActiveStudentRepository()
    progress_repository = student_progress_repository or SqliteStudentProgressRepository()
    page = ExperimentWorkspacePage(
        device_scanner=DeviceScanner(),
        experiment_controller_factory=controller_factory or (lambda _experiment: fake_controller),
        active_student_repository=active_repository,
        student_progress_repository=progress_repository,
    )
    page.set_role(role)
    return page, fake_controller, active_repository, progress_repository


def test_student_role_without_active_student_shows_blocked_state() -> None:
    page, _fake_controller, _active, _progress = _make_page(role=UserRole.STUDENT)

    page.on_enter(_make_experiment())

    assert page._body_stack.currentWidget() is page._blocked_state_widget
    assert page._experiment_controller is None


def test_student_role_without_active_student_never_links_session() -> None:
    page, _fake_controller, _active, progress_repository = _make_page(role=UserRole.STUDENT)

    page.on_enter(_make_experiment())

    assert progress_repository.get_progress("anyone", "ohms-law").latest_session_id is None


def test_blocked_state_button_emits_student_selection_requested() -> None:
    page, _fake_controller, _active, _progress = _make_page(role=UserRole.STUDENT)
    page.on_enter(_make_experiment())

    signals: list[None] = []
    page.student_selection_requested.connect(lambda: signals.append(None))
    page._blocked_state_widget.findChild(type(page._back_button)).click()

    assert signals == [None]


def test_student_role_with_active_student_shows_measurement_workspace() -> None:
    active_repository = SqliteActiveStudentRepository()
    active_repository.set(ActiveStudentContext(classroom_id="c1", student_id="s1"))
    page, _fake_controller, _active, _progress = _make_page(
        role=UserRole.STUDENT, active_student_repository=active_repository
    )

    page.on_enter(_make_experiment())

    assert page._body_stack.currentWidget() is page._measurement_workspace
    assert page._experiment_controller is not None
    assert page._active_student_header_label.isHidden() is False


def test_session_linked_to_active_student_atomically_at_on_enter() -> None:
    """§ "Ownership begins when the experiment session starts" — байланыс
    ЕШБІР өлшеу болмаса да, ``on_enter()``-дің ӨЗІНДЕ жазылады."""
    active_repository = SqliteActiveStudentRepository()
    active_repository.set(ActiveStudentContext(classroom_id="c1", student_id="s1"))
    progress_repository = SqliteStudentProgressRepository()
    page, fake_controller, _active, _progress = _make_page(
        role=UserRole.STUDENT,
        active_student_repository=active_repository,
        student_progress_repository=progress_repository,
    )

    page.on_enter(_make_experiment())

    session_id = fake_controller.session.id
    assert progress_repository.get_student_for_session(session_id) == "s1"


def test_teacher_role_never_gated_and_never_links_session() -> None:
    progress_repository = SqliteStudentProgressRepository()
    page, fake_controller, _active, _progress = _make_page(
        role=UserRole.TEACHER, student_progress_repository=progress_repository
    )

    page.on_enter(_make_experiment())

    assert page._body_stack.currentWidget() is page._measurement_workspace
    assert page._experiment_controller is not None
    session_id = fake_controller.session.id
    assert progress_repository.get_student_for_session(session_id) is None


def test_switching_student_starts_a_fresh_session_for_new_student() -> None:
    active_repository = SqliteActiveStudentRepository()
    active_repository.set(ActiveStudentContext(classroom_id="c1", student_id="s1"))
    progress_repository = SqliteStudentProgressRepository()
    controllers = iter([_make_unique_controller(), _make_unique_controller()])
    page, _first_controller, _active, _progress = _make_page(
        role=UserRole.STUDENT,
        active_student_repository=active_repository,
        student_progress_repository=progress_repository,
        controller_factory=lambda _experiment: next(controllers),
    )
    page.on_enter(_make_experiment())
    first_session_id = page._experiment_controller.session.id

    active_repository.set(ActiveStudentContext(classroom_id="c1", student_id="s2"))
    page.refresh_active_student()

    # Ескі сессия ӘЛІ ДЕ "s1"-ге тағайындалған қалпында қалады.
    assert progress_repository.get_student_for_session(first_session_id) == "s1"
    # Жаңа сессия жаңа оқушыға (s2) тағайындалады.
    new_session_id = page._experiment_controller.session.id
    assert new_session_id != first_session_id
    assert progress_repository.get_student_for_session(new_session_id) == "s2"


def test_refresh_active_student_is_noop_without_current_experiment() -> None:
    page, _fake_controller, _active, _progress = _make_page(role=UserRole.STUDENT)
    page.refresh_active_student()  # құламауы тиіс, ешбір эксперимент ашылмаған


def test_is_measurement_running_reflects_controller_state() -> None:
    active_repository = SqliteActiveStudentRepository()
    active_repository.set(ActiveStudentContext(classroom_id="c1", student_id="s1"))
    page, fake_controller, _active, _progress = _make_page(
        role=UserRole.STUDENT, active_student_repository=active_repository
    )
    page.on_enter(_make_experiment())
    assert page.is_measurement_running() is False

    page._device_panel.device_selected.emit(_make_device())
    page._measurement_workspace._start_button.click()

    assert page.is_measurement_running() is True


def test_running_changed_signal_emitted_on_start_and_stop() -> None:
    active_repository = SqliteActiveStudentRepository()
    active_repository.set(ActiveStudentContext(classroom_id="c1", student_id="s1"))
    page, _fake_controller, _active, _progress = _make_page(
        role=UserRole.STUDENT, active_student_repository=active_repository
    )
    page.on_enter(_make_experiment())

    events: list[bool] = []
    page.measurement_running_changed.connect(events.append)

    page._device_panel.device_selected.emit(_make_device())
    page._measurement_workspace._start_button.click()
    page._measurement_workspace._stop_button.click()

    assert events == [True, False]
