"""LightModule және light/experiments_config үшін юнит-тесттер."""

from domain.interfaces.i_physics_module import IPhysicsModule
from modules.light.experiments_config import LIGHT_EXPERIMENTS
from modules.light.module import LightModule


def test_light_module_implements_interface() -> None:
    assert isinstance(LightModule(), IPhysicsModule)


def test_light_module_returns_name() -> None:
    assert LightModule().get_name() == "Жарық құбылыстары"


def test_light_module_returns_one_experiment() -> None:
    experiments = LightModule().get_experiments()

    assert len(experiments) == 1
    assert experiments == LIGHT_EXPERIMENTS


def test_light_experiment_is_planned() -> None:
    experiment = LIGHT_EXPERIMENTS[0]
    assert experiment.is_implemented is False
    assert experiment.required_channels == ()
    assert experiment.required_sensor_types == ()


def test_light_experiment_is_numbered_eleven() -> None:
    # 8-сынып жаңа оқу бағдарламасы: Electricity бөлімі қысқарғандықтан
    # (7→6), каталогтың жалпы 1..N реті үзіліссіз қалу үшін 12-ден
    # 11-ге жылжытылды.
    assert LIGHT_EXPERIMENTS[0].display_number == 11
