"""compute_student_home_summary() юнит-тесттері — таза (Qt-сыз) агрегация,
НАҚТЫ (in-memory) репозиторийлермен (Phase — Student Home Dashboard
Redesign)."""

from datetime import datetime, timedelta, timezone

from domain.entities.experiment_definition import ExperimentDefinition
from domain.entities.experiment_feedback_result import ExperimentFeedbackResult, TeacherAssessment
from domain.entities.experiment_session import ExperimentSession
from domain.entities.measurement import Measurement
from domain.entities.student_experiment_progress import ProgressStatus
from domain.entities.user_role import UserRole
from domain.interfaces.i_physics_module import IPhysicsModule
from domain.services.student_home_summary import compute_student_home_summary
from infrastructure.storage.sqlite_feedback_repository import SqliteFeedbackRepository
from infrastructure.storage.sqlite_session_repository import SqliteSessionRepository
from infrastructure.storage.sqlite_student_progress_repository import SqliteStudentProgressRepository
from modules.module_registry import ModuleRegistry

_NOW = datetime.now(timezone.utc)

_OHMS_LAW = ExperimentDefinition(id="ohms-law", title="Ом заңы", description="", display_number=4)
_CIRCUIT = ExperimentDefinition(id="circuit", title="Тізбек құрастыру", description="", display_number=3)
_ICE_MELT = ExperimentDefinition(id="ice-melt", title="Мұздың балқуы", description="", display_number=1)


class _ElectricityModule(IPhysicsModule):
    def get_name(self) -> str:
        return "Электр құбылыстары"

    def get_icon(self) -> str | None:
        return "⚡"

    def get_experiments(self) -> tuple[ExperimentDefinition, ...]:
        return (_OHMS_LAW, _CIRCUIT)


class _HeatModule(IPhysicsModule):
    def get_name(self) -> str:
        return "Жылу құбылыстары"

    def get_icon(self) -> str | None:
        return "🔥"

    def get_experiments(self) -> tuple[ExperimentDefinition, ...]:
        return (_ICE_MELT,)


def _make_repos() -> tuple[ModuleRegistry, SqliteStudentProgressRepository, SqliteSessionRepository, SqliteFeedbackRepository]:
    session_repository = SqliteSessionRepository()
    feedback_repository = SqliteFeedbackRepository()
    progress_repository = SqliteStudentProgressRepository(
        session_repository=session_repository, feedback_repository=feedback_repository,
    )
    module_registry = ModuleRegistry()
    module_registry.register(_ElectricityModule())
    module_registry.register(_HeatModule())
    return module_registry, progress_repository, session_repository, feedback_repository


def _save_measured_session(session_repository: SqliteSessionRepository, session_id: str, experiment_id: str) -> None:
    session = ExperimentSession(id=session_id, experiment_id=experiment_id, started_at=_NOW)
    session.add_measurement(Measurement(timestamp=_NOW, values={"voltage": 5.0}, experiment_id=experiment_id))
    session_repository.save_session(session)


def test_zero_state_all_zero_and_none() -> None:
    module_registry, progress_repository, _sessions, _feedback = _make_repos()

    summary = compute_student_home_summary(module_registry, progress_repository, "s1")

    assert summary.in_progress_count == 0
    assert summary.completed_count == 0
    assert summary.awaiting_review_count == 0
    assert summary.resumable is None
    assert summary.recent_results == ()
    assert {cp.module.get_name(): (cp.completed, cp.total) for cp in summary.category_progress} == {
        "Электр құбылыстары": (0, 2),
        "Жылу құбылыстары": (0, 1),
    }


def test_in_progress_status_counted_and_selected_as_resumable() -> None:
    module_registry, progress_repository, _sessions, _feedback = _make_repos()
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    # § derive_status: байланыс бар, 0 өлшеу -> IN_PROGRESS.

    summary = compute_student_home_summary(module_registry, progress_repository, "s1")

    assert summary.in_progress_count == 1
    assert summary.resumable is not None
    assert summary.resumable.experiment.id == "ohms-law"
    assert summary.resumable.module.get_name() == "Электр құбылыстары"


def test_multiple_in_progress_resolves_deterministically() -> None:
    """§ "use the most recently active one if multiple are valid" — audit
    finding: ``SqliteSessionRepository.save_session()`` ӘДЕЙІ бос (0 өлшеу)
    сессияны ЕШҚАШАН сақтамайды (§8 guard), сондықтан НАҚТЫ IN_PROGRESS
    жазбаның ``last_activity_at``-ы архитектуралық түрде ӘРҚАШАН ``None``
    (сессия әлі "experiment_sessions"-ке жазылмаған). Бұл жағдайда
    ``_select_resumable`` ЕШБІР сан ойдан шығармай, каталог ретімен
    тұрақты (stable sort) таңдау жасайды — recency сигналы жоқ болғанда
    бұл ЖАЛҒЫЗ адал мінез-құлық."""
    module_registry, progress_repository, _sessions, _feedback = _make_repos()
    progress_repository.link_session("sess_a", "s1", "c1", "ohms-law")
    progress_repository.link_session("sess_b", "s1", "c1", "circuit")

    summary = compute_student_home_summary(module_registry, progress_repository, "s1")

    assert summary.resumable is not None
    assert summary.resumable.experiment.id in ("ohms-law", "circuit")
    # Қайта есептегенде де ДӘЛ СОЛ таңдау (тұрақты, ешбір кездейсоқтық жоқ).
    second_summary = compute_student_home_summary(module_registry, progress_repository, "s1")
    assert second_summary.resumable.experiment.id == summary.resumable.experiment.id


def test_reviewed_result_counts_as_completed_with_score() -> None:
    module_registry, progress_repository, session_repository, feedback_repository = _make_repos()
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1", "ohms-law")
    feedback_repository.save_submission(
        ExperimentFeedbackResult(
            experiment_id="ohms-law", session_id="sess1", is_draft=False,
            submitted_at=_NOW - timedelta(minutes=10),
        )
    )
    feedback_repository.save_teacher_assessment(
        "sess1", "ohms-law", TeacherAssessment(score=9), UserRole.TEACHER
    )

    summary = compute_student_home_summary(module_registry, progress_repository, "s1")

    assert summary.completed_count == 1
    assert summary.in_progress_count == 0
    assert summary.awaiting_review_count == 0
    assert len(summary.recent_results) == 1
    assert summary.recent_results[0].experiment.id == "ohms-law"
    assert summary.recent_results[0].teacher_score == 9
    category = {cp.module.get_name(): cp.completed for cp in summary.category_progress}
    assert category["Электр құбылыстары"] == 1


def test_feedback_submitted_awaits_review_with_no_score() -> None:
    module_registry, progress_repository, session_repository, feedback_repository = _make_repos()
    progress_repository.link_session("sess1", "s1", "c1", "ohms-law")
    _save_measured_session(session_repository, "sess1", "ohms-law")
    feedback_repository.save_submission(
        ExperimentFeedbackResult(
            experiment_id="ohms-law", session_id="sess1", is_draft=False,
            submitted_at=_NOW,
        )
    )

    summary = compute_student_home_summary(module_registry, progress_repository, "s1")

    assert summary.awaiting_review_count == 1
    assert summary.completed_count == 1  # § FEEDBACK_SUBMITTED "аяқталған" жиынтығына кіреді.
    assert summary.recent_results[0].teacher_score is None


def test_recent_results_capped_at_max_and_sorted_by_recency() -> None:
    module_registry, progress_repository, session_repository, feedback_repository = _make_repos()
    for index, experiment_id in enumerate(("ohms-law", "circuit", "ice-melt")):
        session_id = f"sess_{experiment_id}"
        progress_repository.link_session(session_id, "s1", "c1", experiment_id)
        _save_measured_session(session_repository, session_id, experiment_id)
        feedback_repository.save_submission(
            ExperimentFeedbackResult(
                experiment_id=experiment_id, session_id=session_id, is_draft=False,
                submitted_at=_NOW - timedelta(minutes=index),
            )
        )

    summary = compute_student_home_summary(module_registry, progress_repository, "s1", max_recent_results=2)

    assert len(summary.recent_results) == 2
    assert summary.recent_results[0].experiment.id == "ohms-law"
    assert summary.recent_results[1].experiment.id == "circuit"


def test_not_started_experiments_are_excluded_from_all_counts() -> None:
    module_registry, progress_repository, _sessions, _feedback = _make_repos()

    summary = compute_student_home_summary(module_registry, progress_repository, "s1")

    assert summary.recent_results == ()
    assert summary.resumable is None
