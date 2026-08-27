"""experiments_config — "Электромагниттік құбылыстар" бөлімінің 2 зертхана
жұмысы.

Барлығы каталогта ғана — әлі workspace/sensor pipeline-і жоқ
(``is_implemented=False``). Нақты hardware/арна ойдан шығарылмайды.
"""

from domain.entities.experiment_definition import ExperimentDefinition

# 8-сынып жаңа оқу бағдарламасы: Electricity бөлімі 7-ден 6 тәжірибеге
# қысқарғандықтан (артық placeholder алынып тасталды), каталогтың
# ЖАЛПЫ 1..N сандық реті үзіліссіз қалу үшін бұл екеуі 10/11-ден
# 9/10-ға жылжытылды (тек нөмір — атау/логика өзгермеді).
PERMANENT_MAGNET_PROPERTIES_EXPERIMENT = ExperimentDefinition(
    id="permanent-magnet-properties",
    title="Тұрақты магниттің қасиеттерін зерттеу",
    description="Тұрақты магниттің магнит өрісін тәжірибе арқылы зерттеу.",
    display_number=9,
    is_implemented=False,
)

ELECTROMAGNET_CONSTRUCTION_EXPERIMENT = ExperimentDefinition(
    id="electromagnet-construction",
    title="Электромагнит құрастыру және оның әсерін зерттеу",
    description=(
        "Катушка арқылы пайда болатын магнит өрісін бақылау және ток "
        "күшінің магнит өрісіне әсерін зерттеу."
    ),
    display_number=10,
    is_implemented=False,
)

ELECTROMAGNETISM_EXPERIMENTS: tuple[ExperimentDefinition, ...] = (
    PERMANENT_MAGNET_PROPERTIES_EXPERIMENT,
    ELECTROMAGNET_CONSTRUCTION_EXPERIMENT,
)
