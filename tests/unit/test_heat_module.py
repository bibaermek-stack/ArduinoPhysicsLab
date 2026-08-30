"""HeatModule және heat/experiments_config үшін юнит-тесттер."""

from domain.interfaces.i_physics_module import IPhysicsModule
from modules.heat.experiments_config import (
    COMPARE_HEAT_QUANTITY_EXPERIMENT,
    HEAT_EXPERIMENTS,
    ICE_SPECIFIC_HEAT_OF_FUSION_EXPERIMENT,
)
from modules.heat.module import HeatModule


def test_heat_module_implements_interface() -> None:
    assert isinstance(HeatModule(), IPhysicsModule)


def test_heat_module_returns_name() -> None:
    assert HeatModule().get_name() == "Жылу құбылыстары"


def test_heat_module_returns_two_experiments() -> None:
    # Catalog order correction: "Металдардың меншікті жылу сыйымдылығын
    # анықтау" authoritative 12-work каталогтан алынып тасталды.
    experiments = HeatModule().get_experiments()

    assert len(experiments) == 2
    assert experiments == HEAT_EXPERIMENTS


def test_all_heat_experiments_are_planned() -> None:
    # kезeng 39B: is_implemented ЕКЕУІНДЕ ДЕ False (compare-heat-quantity
    # арна/UI жағынан толық дайын болса да, firmware физикалық hardware-де
    # әлі тексерілмеген) — бірақ енді екеуі бірдей "бос" емес.
    for experiment in HEAT_EXPERIMENTS:
        assert experiment.is_implemented is False


def test_compare_heat_quantity_has_real_channel_wiring() -> None:
    # kезeng 39B: TEMP= парсинг/арна/UI дайын, тек hardware-валидация
    # жетіспейді (§ experiments_config.py-дегі толық түсіндірме).
    assert COMPARE_HEAT_QUANTITY_EXPERIMENT.required_channels != ()
    assert COMPARE_HEAT_QUANTITY_EXPERIMENT.required_sensor_types == ("TEMPERATURE",)
    assert not COMPARE_HEAT_QUANTITY_EXPERIMENT.validate_configuration()


def test_ice_specific_heat_of_fusion_is_still_a_bare_catalog_entry() -> None:
    assert ICE_SPECIFIC_HEAT_OF_FUSION_EXPERIMENT.required_channels == ()
    assert ICE_SPECIFIC_HEAT_OF_FUSION_EXPERIMENT.required_sensor_types == ()


def test_heat_experiment_ids_are_unique() -> None:
    ids = [experiment.id for experiment in HEAT_EXPERIMENTS]
    assert len(ids) == len(set(ids))


def test_heat_experiments_are_numbered_one_to_two() -> None:
    numbers = [experiment.display_number for experiment in HEAT_EXPERIMENTS]
    assert numbers == [1, 2]


def test_removed_metal_specific_heat_capacity_experiment_not_in_catalog() -> None:
    from modules.heat.experiments_config import METAL_SPECIFIC_HEAT_CAPACITY_EXPERIMENT

    assert METAL_SPECIFIC_HEAT_CAPACITY_EXPERIMENT not in HEAT_EXPERIMENTS
    assert METAL_SPECIFIC_HEAT_CAPACITY_EXPERIMENT.display_number is None
