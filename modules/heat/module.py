"""HeatModule — IPhysicsModule интерфейсінің "Жылу құбылыстары" модуліне
арналған іске асыруы.
"""

from domain.entities.experiment_definition import ExperimentDefinition
from domain.interfaces.i_physics_module import IPhysicsModule
from modules.heat.experiments_config import HEAT_EXPERIMENTS


class HeatModule(IPhysicsModule):
    """"Жылу құбылыстары" модулі: 2 жоспарланған зертхана жұмысын қамтиды."""

    def get_name(self) -> str:
        return "Жылу құбылыстары"

    def get_icon(self) -> str | None:
        # Нақты icon resource жүйесі жоқ (ui/resources/icons бос) —
        # қолданбада бұрыннан қалыптасқан emoji-негізді визуалды тіл
        # қолданылады (sidebar nav icons, status dots).
        return "🌡️"

    def get_experiments(self) -> tuple[ExperimentDefinition, ...]:
        return HEAT_EXPERIMENTS
