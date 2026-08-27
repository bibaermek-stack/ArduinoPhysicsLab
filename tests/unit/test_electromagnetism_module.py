"""ElectromagnetismModule және electromagnetism/experiments_config үшін
юнит-тесттер.
"""

from domain.interfaces.i_physics_module import IPhysicsModule
from modules.electromagnetism.experiments_config import ELECTROMAGNETISM_EXPERIMENTS
from modules.electromagnetism.module import ElectromagnetismModule


def test_electromagnetism_module_implements_interface() -> None:
    assert isinstance(ElectromagnetismModule(), IPhysicsModule)


def test_electromagnetism_module_returns_name() -> None:
    assert ElectromagnetismModule().get_name() == "Электромагниттік құбылыстар"


def test_electromagnetism_module_returns_two_experiments() -> None:
    experiments = ElectromagnetismModule().get_experiments()

    assert len(experiments) == 2
    assert experiments == ELECTROMAGNETISM_EXPERIMENTS


def test_all_electromagnetism_experiments_are_planned() -> None:
    for experiment in ELECTROMAGNETISM_EXPERIMENTS:
        assert experiment.is_implemented is False
        assert experiment.required_channels == ()
        assert experiment.required_sensor_types == ()


def test_electromagnetism_experiment_ids_are_unique() -> None:
    ids = [experiment.id for experiment in ELECTROMAGNETISM_EXPERIMENTS]
    assert len(ids) == len(set(ids))


def test_electromagnetism_experiments_are_numbered_nine_to_ten() -> None:
    # 8-сынып жаңа оқу бағдарламасы: Electricity бөлімі 7-ден 6
    # тәжірибеге қысқарғандықтан, каталогтың жалпы 1..N реті үзіліссіз
    # қалу үшін бұл екеуі 10/11-ден 9/10-ға жылжытылды.
    numbers = [experiment.display_number for experiment in ELECTROMAGNETISM_EXPERIMENTS]
    assert numbers == [9, 10]
