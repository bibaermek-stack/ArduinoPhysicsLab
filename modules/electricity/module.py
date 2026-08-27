"""ElectricityModule — IPhysicsModule интерфейсінің "Электр құбылыстары"
модуліне арналған іске асыруы.
"""

from domain.entities.experiment_definition import ExperimentDefinition
from domain.interfaces.i_physics_module import IPhysicsModule
from modules.electricity.experiments_config import ELECTRICITY_EXPERIMENTS


class ElectricityModule(IPhysicsModule):
    """"Электр құбылыстары" модулі: 7 зертхана жұмысын қамтиды (5 іске
    асырылған + 2 жоспарланған)."""

    def get_name(self) -> str:
        return "Электр құбылыстары"

    def get_icon(self) -> str | None:
        # Нақты icon resource жүйесі жоқ — қолданбада бұрыннан қалыптасқан
        # emoji-негізді визуалды тіл қолданылады (sidebar nav icons т.б.).
        return "⚡"

    def get_experiments(self) -> tuple[ExperimentDefinition, ...]:
        return ELECTRICITY_EXPERIMENTS
