"""LightModule — IPhysicsModule интерфейсінің "Жарық құбылыстары" модуліне
арналған іске асыруы.
"""

from domain.entities.experiment_definition import ExperimentDefinition
from domain.interfaces.i_physics_module import IPhysicsModule
from modules.light.experiments_config import LIGHT_EXPERIMENTS


class LightModule(IPhysicsModule):
    """"Жарық құбылыстары" модулі: 1 жоспарланған зертхана жұмысын қамтиды."""

    def get_name(self) -> str:
        return "Жарық құбылыстары"

    def get_icon(self) -> str | None:
        # Нақты icon resource жүйесі жоқ — қолданбада бұрыннан қалыптасқан
        # emoji-негізді визуалды тіл қолданылады (sidebar nav icons т.б.).
        return "💡"

    def get_experiments(self) -> tuple[ExperimentDefinition, ...]:
        return LIGHT_EXPERIMENTS
