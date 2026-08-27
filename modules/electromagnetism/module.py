"""ElectromagnetismModule — IPhysicsModule интерфейсінің "Электромагниттік
құбылыстар" модуліне арналған іске асыруы.
"""

from domain.entities.experiment_definition import ExperimentDefinition
from domain.interfaces.i_physics_module import IPhysicsModule
from modules.electromagnetism.experiments_config import ELECTROMAGNETISM_EXPERIMENTS


class ElectromagnetismModule(IPhysicsModule):
    """"Электромагниттік құбылыстар" модулі: 2 жоспарланған зертхана
    жұмысын қамтиды.
    """

    def get_name(self) -> str:
        return "Электромагниттік құбылыстар"

    def get_icon(self) -> str | None:
        # Нақты icon resource жүйесі жоқ — қолданбада бұрыннан қалыптасқан
        # emoji-негізді визуалды тіл қолданылады (sidebar nav icons т.б.).
        return "🧲"

    def get_experiments(self) -> tuple[ExperimentDefinition, ...]:
        return ELECTROMAGNETISM_EXPERIMENTS
