"""question_bank_assembly / question_bank_seed юнит-тесттері (Phase 20)."""

from datetime import datetime, timezone

from domain.entities.experiment_assessment import (
    ExperimentAssessmentDefinition,
    MultipleChoiceQuestion,
    OpenResponseQuestion,
    ReflectionQuestion,
)
from domain.entities.experiment_definition import ExperimentDefinition
from domain.entities.question_record import QuestionRecord
from domain.entities.user_role import UserRole
from domain.interfaces.i_physics_module import IPhysicsModule
from domain.services.question_bank_assembly import build_assessment_definition
from domain.services.question_bank_seed import seed_questions_from_catalog
from infrastructure.storage.sqlite_question_repository import SqliteQuestionRepository
from modules.module_registry import ModuleRegistry

_NOW = datetime.now(timezone.utc)


def _record(level: int, question) -> QuestionRecord:
    return QuestionRecord(
        id=question.id, experiment_id="ohms-law", level=level, question=question,
        is_active=True, created_at=_NOW,
    )


def test_build_assessment_definition_returns_fallback_when_no_records() -> None:
    fallback = ExperimentAssessmentDefinition(
        level1_questions=(MultipleChoiceQuestion(id="a", prompt="?", options=("x", "y"), correct_option_index=0),)
    )

    result = build_assessment_definition((), fallback)

    assert result is fallback


def test_build_assessment_definition_returns_none_when_no_records_and_no_fallback() -> None:
    assert build_assessment_definition((), None) is None


def test_build_assessment_definition_groups_records_by_level() -> None:
    mc = MultipleChoiceQuestion(id="m1", prompt="?", options=("x", "y"), correct_option_index=0)
    op = OpenResponseQuestion(id="o1", prompt="?")
    refl = ReflectionQuestion(id="r1", prompt="?")
    records = (_record(1, mc), _record(2, op), _record(3, refl))

    result = build_assessment_definition(records, None)

    assert result.level1_questions == (mc,)
    assert result.level2_questions == (op,)
    assert result.level3_questions == (refl,)


def test_build_assessment_definition_preserves_self_assessment_range_from_fallback() -> None:
    fallback = ExperimentAssessmentDefinition(
        level1_questions=(MultipleChoiceQuestion(id="a", prompt="?", options=("x", "y"), correct_option_index=0),),
        self_assessment_min=2, self_assessment_max=8,
    )
    mc = MultipleChoiceQuestion(id="m1", prompt="?", options=("x", "y"), correct_option_index=0)

    result = build_assessment_definition((_record(1, mc),), fallback)

    assert result.self_assessment_min == 2
    assert result.self_assessment_max == 8


class _FakeModule(IPhysicsModule):
    def __init__(self, experiments):
        self._experiments = experiments

    def get_name(self) -> str:
        return "Тест модулі"

    def get_icon(self):
        return None

    def get_experiments(self):
        return self._experiments


def _experiment_with_assessment() -> ExperimentDefinition:
    return ExperimentDefinition(
        id="ohms-law", title="Ом заңы", description="",
        assessment=ExperimentAssessmentDefinition(
            level1_questions=(
                MultipleChoiceQuestion(id="ol-l1-1", prompt="?", options=("x", "y"), correct_option_index=0),
            ),
            level2_questions=(OpenResponseQuestion(id="ol-l2-1", prompt="?"),),
            level3_questions=(ReflectionQuestion(id="ol-l3-1", prompt="?"),),
        ),
    )


def test_seed_copies_static_catalog_questions_into_empty_repository() -> None:
    repository = SqliteQuestionRepository()
    registry = ModuleRegistry()
    registry.register(_FakeModule((_experiment_with_assessment(),)))

    seed_questions_from_catalog(repository, registry)

    records = repository.list_for_experiment("ohms-law")
    assert {r.id for r in records} == {"ol-l1-1", "ol-l2-1", "ol-l3-1"}


def test_seed_skips_experiments_without_assessment() -> None:
    repository = SqliteQuestionRepository()
    registry = ModuleRegistry()
    registry.register(
        _FakeModule((ExperimentDefinition(id="no-assessment", title="X", description=""),))
    )

    seed_questions_from_catalog(repository, registry)

    assert repository.list_all() == ()


def test_seed_is_idempotent_never_overwrites_existing_data() -> None:
    """§ "Preserve existing data. No destructive migration" — репозиторий
    БОС ЕМЕС болса (тіпті бір мұрағатталған жол болса да), seed ЕШБІР
    жаңа жол қоспайды."""
    repository = SqliteQuestionRepository()
    registry = ModuleRegistry()
    registry.register(_FakeModule((_experiment_with_assessment(),)))

    manual_record = QuestionRecord(
        id="manual-1", experiment_id="ohms-law", level=1,
        question=MultipleChoiceQuestion(id="manual-1", prompt="Қолмен қосылған", options=("A", "B"), correct_option_index=0),
        is_active=True, created_at=_NOW,
    )
    repository.create(manual_record, UserRole.TEACHER)

    seed_questions_from_catalog(repository, registry)

    assert [r.id for r in repository.list_all()] == ["manual-1"]
