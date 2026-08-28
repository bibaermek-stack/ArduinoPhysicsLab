"""Laboratory Catalog — 4 бөлім / 11 зертханалық жұмыс бойынша
cross-cutting spec тексерулері.

Бұл файл жеке модульдің (Electricity/Heat/...) ішкі детальдарын емес,
ТОЛЫҚ каталогтың спецификацияға сәйкестігін тексереді: дәл 11 тәжірибе,
дәл 1..11 нөмірлер (қайталанусыз/олқысыз), дәл 4 бөлім, бөлім бойынша
саны.

8-сынып жаңа оқу бағдарламасы (curriculum rename): Electricity бөлімі
7-ден 6 тәжірибеге қысқарды (артық "Электр тізбегін құрастыру және ток
күшін өлшеу" placeholder-і алынып тасталды — оның атауы/нөмірі ЕНДІ
нақты іске асырылған current-voltage тәжірибесіне көшті), сондықтан
жалпы каталог 12-ден 11-ге, ал Electromagnetism/Light бөлімдерінің
нөмірлері (10/11/12 → 9/10/11) сандық реттің үзіліссіз қалуы үшін
жылжытылды.
"""

from modules.electricity.experiments_config import ELECTRICITY_EXPERIMENTS, OHMS_LAW_EXPERIMENT
from modules.electricity.module import ElectricityModule
from modules.electromagnetism.module import ElectromagnetismModule
from modules.heat.module import HeatModule
from modules.light.module import LightModule
from modules.module_registry import ModuleRegistry


def _make_full_registry() -> ModuleRegistry:
    registry = ModuleRegistry()
    registry.register(HeatModule())
    registry.register(ElectricityModule())
    registry.register(ElectromagnetismModule())
    registry.register(LightModule())
    return registry


def test_exactly_eleven_experiments_total() -> None:
    registry = _make_full_registry()
    total = sum(len(module.get_experiments()) for module in registry.get_all())
    assert total == 11


def test_display_numbers_are_exactly_one_to_eleven() -> None:
    registry = _make_full_registry()
    numbers = sorted(
        experiment.display_number
        for module in registry.get_all()
        for experiment in module.get_experiments()
    )
    assert numbers == list(range(1, 12))


def test_exactly_four_sections() -> None:
    registry = _make_full_registry()
    assert len(registry.get_all()) == 4


def test_section_experiment_counts() -> None:
    registry = _make_full_registry()
    counts = {module.get_name(): len(module.get_experiments()) for module in registry.get_all()}

    assert counts["Жылу құбылыстары"] == 2
    assert counts["Электр құбылыстары"] == 6
    assert counts["Электромагниттік құбылыстар"] == 2
    assert counts["Жарық құбылыстары"] == 1


def test_ohms_law_display_number_is_four() -> None:
    assert OHMS_LAW_EXPERIMENT.display_number == 4


def test_electricity_section_matches_new_curriculum_order() -> None:
    """8-сынып жаңа оқу бағдарламасы: электр бөлімінің реті ЕНДІ
    display_number-мен сәйкес (3..8), ескі "ohms-law ЕҢ СОҢЫНДА"
    ерекшелігі қолданылмайды.
    """
    assert [experiment.id for experiment in ELECTRICITY_EXPERIMENTS] == [
        "current-voltage",
        "ohms-law",
        "series-connection",
        "parallel-connection",
        "current-work-power",
        "metal-resistance-temperature",
    ]


def test_section_registration_order_matches_spec_sections_one_to_four() -> None:
    registry = _make_full_registry()
    names = [module.get_name() for module in registry.get_all()]
    assert names == [
        "Жылу құбылыстары",
        "Электр құбылыстары",
        "Электромагниттік құбылыстар",
        "Жарық құбылыстары",
    ]


def test_implemented_experiments_are_the_five_electricity_labs_with_firmware() -> None:
    registry = _make_full_registry()
    implemented_ids = {
        experiment.id
        for module in registry.get_all()
        for experiment in module.get_experiments()
        if experiment.is_implemented
    }
    assert implemented_ids == {
        "current-voltage",
        "series-connection",
        "parallel-connection",
        "current-work-power",
        "ohms-law",
    }


def test_each_module_has_a_distinct_icon() -> None:
    # Labs Page-тегі түсті header-де көрсетілетін icon — IPhysicsModule.
    # get_icon() (бұрыннан бар, бірақ V1-де қолданылмаған интерфейс
    # әдісі) арқылы беріледі, UI-де hardcode жасалмайды.
    registry = _make_full_registry()
    icons = [module.get_icon() for module in registry.get_all()]

    assert all(icon for icon in icons)
    assert len(set(icons)) == 4
